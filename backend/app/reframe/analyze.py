"""Stage A: understand the video.

One decode pass at 640 px wide and the source frame rate:
  * every frame:      scene-cut check (exact cut frames)
  * ~10 per second:   faces (+ mouth movement, head direction), tracked into "Person A", "Person B", ...
  * ~2 per second:    people / objects
  * every 2 seconds:  on-screen text
  * per shot:         static-edge map to find a webcam box (facecam), a thumbnail for the shot editor
Plus the audio: speech probability and loudness, ~10 values per second.
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import cv2
import numpy as np

from . import detect
from .media import FrameReader, MediaInfo, even, read_audio

AN_W = 640            # analysis width (px)
DETECT_FPS = 10.0     # face samples per second
OBJ_EVERY = 5         # people/objects every 5th sample (2 per second)
TEXT_EVERY = 20       # text every 20th sample (every 2 s)
EDGE_EVERY = 3        # facecam edge map every 3rd sample
MIN_SHOT = 0.8        # seconds: shorter "shots" are flashes, not cuts
CUT_THRESHOLD = 30.0  # mean HSV change (0..255) that counts as a cut (PySceneDetect's default is 27)


class Cancelled(Exception):
    pass


@dataclass
class Det:
    """A face, person or object in one sample. Coordinates are 0..1 of the frame."""
    track: int
    x: float
    y: float
    w: float
    h: float
    score: float
    cls: int = -1            # -1 = face, else COCO class id
    mouth: float = 0.0       # mouth movement since the previous sample (faces)
    yaw: float = 0.0         # -1 facing left ... +1 facing right (faces)

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2

    def to_list(self) -> list:
        return [self.track, round(self.x, 4), round(self.y, 4), round(self.w, 4), round(self.h, 4), round(self.score, 3)]


@dataclass
class Shot:
    index: int
    start: float
    end: float
    s0: int = 0                                  # samples [s0, s1) belong to this shot
    s1: int = 0
    thumb: str | None = None
    thumb_t: float = 0.0
    facecam: tuple[float, float, float, float] | None = None
    text_cover: float = 0.0                      # mean share of the frame covered by text
    text_span: tuple[float, float] | None = None  # horizontal extent of the text (0..1)
    motion: float = 0.0                          # mean frame-to-frame change (0..255)

    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class Analysis:
    duration: float
    width: int                  # source display size
    height: int
    an_size: tuple[int, int]    # analysis frame size
    sample_fps: float
    faces: list[list[Det]] = field(default_factory=list)     # per sample
    objects: list[list[Det]] = field(default_factory=list)   # per sample (empty between object samples)
    speech: np.ndarray = field(default_factory=lambda: np.zeros(0, np.float32))   # per sample, 0..1
    loud: np.ndarray = field(default_factory=lambda: np.zeros(0, np.float32))     # per sample, dBFS
    shots: list[Shot] = field(default_factory=list)
    focus: dict[int, list[list[Det]]] = field(default_factory=dict)   # class id -> per-sample detections (Follow this…)
    thumbs_dir: Path | None = None

    @property
    def n(self) -> int:
        return len(self.faces)

    def t(self, i: int) -> float:
        return i / self.sample_fps

    def sample_at(self, t: float) -> int:
        return int(min(max(0, round(t * self.sample_fps)), max(0, self.n - 1)))

    @property
    def aspect(self) -> float:
        return self.width / self.height


# ---------------------------------------------------------------- tracking


_ids = itertools.count(1)


def _iou(a: Det, b: Det) -> float:
    x0, y0 = max(a.x, b.x), max(a.y, b.y)
    x1, y1 = min(a.x + a.w, b.x + b.w), min(a.y + a.h, b.y + b.h)
    inter = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    union = a.w * a.h + b.w * b.h - inter
    return inter / union if union > 0 else 0.0


class Tracker:
    """Links detections across samples into tracks (greedy IoU + distance matching, short gaps bridged)."""

    def __init__(self, max_gap: int = 12):
        self.max_gap = max_gap
        self.active: dict[int, tuple[Det, int]] = {}

    def reset(self) -> None:
        self.active.clear()

    def update(self, dets: list[Det], i: int) -> None:
        self.active = {k: v for k, v in self.active.items() if i - v[1] <= self.max_gap}
        pairs = []
        for di, d in enumerate(dets):
            for tid, (prev, _) in self.active.items():
                iou = _iou(d, prev)
                dist = math.hypot(d.cx - prev.cx, d.cy - prev.cy) / max(prev.w, prev.h, 1e-6)
                size = max(d.w, prev.w) / max(min(d.w, prev.w), 1e-6)
                if (iou > 0.15 or dist < 0.9) and size < 2.0:
                    pairs.append((iou - 0.1 * dist, di, tid))
        pairs.sort(reverse=True)
        used_d, used_t = set(), set()
        for _, di, tid in pairs:
            if di in used_d or tid in used_t:
                continue
            dets[di].track = tid
            used_d.add(di)
            used_t.add(tid)
        for d in dets:
            if d.track == 0:
                d.track = next(_ids)
            self.active[d.track] = (d, i)


# ---------------------------------------------------------------- per-frame features


def _hsv_small(frame: np.ndarray) -> np.ndarray:
    return cv2.cvtColor(cv2.resize(frame, (64, 36), interpolation=cv2.INTER_AREA), cv2.COLOR_BGR2HSV).astype(np.int16)


def _patch(gray: np.ndarray, x0: float, y0: float, x1: float, y1: float, size: tuple[int, int]) -> np.ndarray | None:
    h, w = gray.shape
    x0, y0, x1, y1 = int(max(0, x0)), int(max(0, y0)), int(min(w, x1)), int(min(h, y1))
    if x1 - x0 < 4 or y1 - y0 < 3:
        return None
    return cv2.resize(gray[y0:y1, x0:x1], size, interpolation=cv2.INTER_AREA).astype(np.float32)


def _mouth_and_face(gray: np.ndarray, f: detect.Face) -> tuple[np.ndarray | None, np.ndarray | None, float]:
    lm = f.lm
    mc = (lm[3] + lm[4]) / 2
    mw = float(np.linalg.norm(lm[3] - lm[4]))
    eye_d = float(np.linalg.norm(lm[0] - lm[1])) or 1.0
    yaw = float(np.clip((lm[2][0] - (lm[0][0] + lm[1][0]) / 2) / eye_d * 2.2, -1, 1))
    if mw < 5:
        return None, None, yaw
    mouth = _patch(gray, mc[0] - 0.8 * mw, mc[1] - 0.45 * mw, mc[0] + 0.8 * mw, mc[1] + 0.75 * mw, (24, 16))
    upper = _patch(gray, f.x, f.y, f.x + f.w, f.y + f.h * 0.5, (24, 12))   # forehead + eyes: head motion / blur reference
    return mouth, upper, yaw


def _diff(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.mean(np.abs(a - b)) / (np.std(b) + 6.0))


# ---------------------------------------------------------------- facecam


def _find_border(profile: np.ndarray, lo: int, hi: int) -> int | None:
    lo, hi = max(0, lo), min(len(profile) - 1, hi)
    if hi - lo < 3:
        return None
    seg = profile[lo:hi + 1]
    k = int(np.argmax(seg))
    if seg[k] > 3.0 * (np.median(seg) + 1.0) and seg[k] > 12:
        return lo + k
    return None


def _facecam(shot_faces: list[list[Det]], gx: np.ndarray | None, gy: np.ndarray | None, motion: np.ndarray | None,
             size: tuple[int, int]) -> tuple[float, float, float, float] | None:
    """A webcam box over gameplay / a screen recording: a small face that doesn't move, inside a
    rectangle whose edges stay put (and usually with lots of movement outside it)."""
    if gx is None or not shot_faces:
        return None
    W, H = size
    by_track: dict[int, list[Det]] = {}
    for dets in shot_faces:
        for d in dets:
            by_track.setdefault(d.track, []).append(d)
    if not by_track:
        return None
    tid, dets = max(by_track.items(), key=lambda kv: len(kv[1]))
    if len(dets) < 0.6 * len(shot_faces) or len(shot_faces) < 5:
        return None
    hs = np.array([d.h for d in dets])
    cx = np.array([d.cx for d in dets])
    cy = np.array([d.cy for d in dets])
    if np.median(hs) > 0.24 or cx.std() > 0.025 or cy.std() > 0.025:
        return None
    fx, fy = float(np.median([d.x for d in dets])) * W, float(np.median([d.y for d in dets])) * H
    fw, fh = float(np.median([d.w for d in dets])) * W, float(np.median(hs)) * H

    rows = slice(int(max(0, fy - 1.2 * fh)), int(min(H, fy + 2.2 * fh)))
    cols = slice(int(max(0, fx - 1.5 * fw)), int(min(W, fx + 2.5 * fw)))
    col_prof = gx[rows].mean(0)
    row_prof = gy[:, cols].mean(1)
    left = _find_border(col_prof, int(fx - 4 * fw), int(fx - 0.25 * fw))
    right = _find_border(col_prof, int(fx + 1.25 * fw), int(fx + 5 * fw))
    top = _find_border(row_prof, int(fy - 3 * fh), int(fy - 0.2 * fh))
    bottom = _find_border(row_prof, int(fy + 1.3 * fh), int(fy + 4 * fh))
    borders = sum(v is not None for v in (left, right, top, bottom))

    # Frame edges count as borders for a cam tucked into a corner.
    x0 = left if left is not None else (0 if fx < 2.2 * fw else fx - 1.3 * fw)
    x1 = right if right is not None else (W if W - (fx + fw) < 2.2 * fw else fx + fw + 1.3 * fw)
    y0 = top if top is not None else (0 if fy < 1.8 * fh else fy - 0.9 * fh)
    y1 = bottom if bottom is not None else (H if H - (fy + fh) < 2.0 * fh else fy + fh + 1.5 * fh)
    x0, y0, x1, y1 = max(0.0, x0), max(0.0, y0), min(float(W), x1), min(float(H), y1)
    rw, rh = x1 - x0, y1 - y0
    if rw <= 0 or rh <= 0:
        return None
    area = rw * rh / (W * H)
    aspect = rw / rh
    if not (0.01 < area < 0.3 and 0.6 < aspect < 2.6):
        return None

    inside = outside = 0.0
    if motion is not None:
        mask = np.zeros(motion.shape, bool)
        mask[int(y0):int(y1), int(x0):int(x1)] = True
        inside = float(motion[mask].mean()) if mask.any() else 0.0
        outside = float(motion[~mask].mean()) if (~mask).any() else 0.0
    busy_outside = outside > 4.0 and outside > 1.8 * (inside + 0.5)
    # A screen recording (code, slides, UI) is full of edges even when nothing moves; a plain wall isn't.
    edges = gx + gy
    emask = np.zeros(edges.shape, bool)
    emask[int(y0):int(y1), int(x0):int(x1)] = True
    e_in = float(edges[emask].mean()) if emask.any() else 0.0
    e_out = float(edges[~emask].mean()) if (~emask).any() else 0.0
    screen_like = busy_outside or (e_out > 6.0 and e_out > 0.5 * e_in)
    corner = (fx + fw / 2) / W < 0.33 or (fx + fw / 2) / W > 0.67 or (fy + fh / 2) / H > 0.6 or (fy + fh / 2) / H < 0.3
    if not screen_like:
        return None
    if busy_outside:
        if borders < 1 and not (corner and np.median(hs) < 0.16):
            return None
    elif borders < 3 or not corner:     # nothing moves around it: only a clearly boxed-in corner cam counts
        return None
    return (x0 / W, y0 / H, rw / W, rh / H)


# ---------------------------------------------------------------- audio


def _audio_features(path: Path, info: MediaInfo, start: float, duration: float, n: int, sample_fps: float,
                    vad: detect.SpeechDetector | None) -> tuple[np.ndarray, np.ndarray]:
    speech = np.zeros(n, np.float32)
    loud = np.full(n, -90.0, np.float32)
    if not info.has_audio or n == 0:
        return speech, loud
    audio = read_audio(path, start, duration)
    if audio.size < 1600:
        return speech, loud
    sr = detect.SpeechDetector.SR
    probs = vad(audio) if vad is not None else np.zeros(0, np.float32)
    chunk_t = detect.SpeechDetector.CHUNK / sr
    half = 0.5 / sample_fps
    for i in range(n):
        t = i / sample_fps
        a, b = int(max(0, (t - half) * sr)), int(min(len(audio), (t + half) * sr))
        if b > a:
            rms = float(np.sqrt(np.mean(audio[a:b] ** 2)) + 1e-9)
            loud[i] = 20 * math.log10(rms)
        if probs.size:
            ca, cb = int((t - half) / chunk_t), int((t + half) / chunk_t) + 1
            seg = probs[max(0, ca):min(len(probs), cb)]
            speech[i] = float(seg.max()) if seg.size else 0.0
    return speech, loud


# ---------------------------------------------------------------- main pass


def analyze(path: Path, info: MediaInfo, start: float, duration: float, thumbs_dir: Path,
            progress: Callable[[float], None] = lambda p: None,
            cancelled: Callable[[], bool] = lambda: False) -> Analysis:
    an_w = min(AN_W, info.width)
    an_h = even(an_w * info.height / info.width)
    an_w = even(an_w)
    size = (an_w, an_h)
    fps = info.fps
    k = max(1, round(fps / DETECT_FPS))
    sample_fps = fps / k
    thumbs_dir.mkdir(parents=True, exist_ok=True)

    an = Analysis(duration=duration, width=info.width, height=info.height, an_size=size, sample_fps=sample_fps,
                  thumbs_dir=thumbs_dir)
    faces_det = detect.FaceDetector(size)
    obj_det = detect.ObjectDetector()
    text_det = detect.TextDetector(size)
    face_tracker, obj_tracker = Tracker(max_gap=int(1.2 * sample_fps)), Tracker(max_gap=3)

    total_frames = max(1, int(duration * fps))
    shots: list[Shot] = []
    shot_start, cut_frames = 0.0, 0
    prev_hsv, recent = None, []
    last_frame = None
    patches: dict[int, tuple[int, np.ndarray, np.ndarray]] = {}
    gx = gy = mot = None
    edge_n = 0
    prev_gray_small = None
    text_samples: list[list[tuple[float, float, float, float]]] = []
    motion_vals: list[float] = []
    thumb_at: float | None = None      # time of the current shot's saved thumbnail

    def finish_shot(end_t: float, frame: np.ndarray | None) -> None:
        nonlocal gx, gy, mot, edge_n, text_samples, motion_vals, thumb_at
        s = Shot(index=len(shots), start=shot_start, end=end_t)
        s.s0 = int(math.ceil(shot_start * sample_fps - 1e-6))
        s.s1 = max(s.s0, int(math.ceil(end_t * sample_fps - 1e-6)))
        s.s1 = min(s.s1, len(an.faces))
        name = f"shot{s.index:03d}.jpg"
        if thumb_at is None and frame is not None:
            cv2.imwrite(str(thumbs_dir / name), frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
            thumb_at = max(shot_start, end_t - 1 / fps)
        s.thumb_t = thumb_at if thumb_at is not None else shot_start
        s.thumb = name if (thumbs_dir / name).exists() else None
        thumb_at = None
        if not text_samples and frame is not None:
            text_samples = [text_det(frame)]
        covers, spans = [], []
        for boxes in text_samples:
            area = sum(b[2] * b[3] for b in boxes) / (an_w * an_h)
            covers.append(min(1.0, area))
            if area > 0.004:
                spans.append((min(b[0] for b in boxes) / an_w, max(b[0] + b[2] for b in boxes) / an_w))
        s.text_cover = float(np.mean(covers)) if covers else 0.0
        if spans and len(spans) >= max(1, len(text_samples) // 2):
            s.text_span = (float(np.median([a for a, _ in spans])), float(np.median([b for _, b in spans])))
        s.motion = float(np.mean(motion_vals)) if motion_vals else 0.0
        s.facecam = _facecam(an.faces[s.s0:s.s1],
                             gx / edge_n if edge_n else None, gy / edge_n if edge_n else None,
                             mot / edge_n if edge_n else None, size)
        shots.append(s)
        gx = gy = mot = None
        edge_n = 0
        text_samples, motion_vals = [], []

    progress(0.0)
    with FrameReader(path, info, size, info.fps_str, start, duration) as reader:
        for fi, frame in enumerate(reader):
            if cancelled():
                raise Cancelled()
            t = fi / fps
            hsv = _hsv_small(frame)
            if prev_hsv is not None:
                delta = float(np.mean(np.abs(hsv - prev_hsv)))
                motion_vals.append(delta)
                recent.append(delta)
                del recent[:-30]
                base = float(np.median(recent)) if len(recent) > 5 else 0.0
                if delta > CUT_THRESHOLD and delta > 2.5 * base + 5 and t - shot_start >= MIN_SHOT:
                    face_tracker.reset()
                    obj_tracker.reset()
                    patches.clear()
                    finish_shot(t, last_frame)
                    shot_start = t
                    cut_frames += 1
            prev_hsv = hsv

            if fi % k == 0:
                si = len(an.faces)
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                fdets: list[Det] = []
                raw_faces = faces_det(frame)
                for f in raw_faces:
                    fdets.append(Det(0, f.x / an_w, f.y / an_h, f.w / an_w, f.h / an_h, f.score))
                face_tracker.update(fdets, si)
                for d, f in zip(fdets, raw_faces):
                    mouth, upper, d.yaw = _mouth_and_face(gray, f)
                    prev = patches.get(d.track)
                    if mouth is not None and upper is not None:
                        if prev is not None and prev[0] == si - 1 and prev[1].shape == mouth.shape:
                            d.mouth = max(0.0, _diff(mouth, prev[1]) - 0.7 * _diff(upper, prev[2]))
                        patches[d.track] = (si, mouth, upper)
                an.faces.append(fdets)

                odets: list[Det] = []
                if si % OBJ_EVERY == 0:
                    for o in obj_det(frame):
                        odets.append(Det(0, o.x / an_w, o.y / an_h, o.w / an_w, o.h / an_h, o.score, cls=o.cls))
                    obj_tracker.update(odets, si)
                an.objects.append(odets)

                if si % TEXT_EVERY == 0:
                    text_samples.append(text_det(frame))

                if si % EDGE_EVERY == 0:
                    g = gray.astype(np.float32)
                    sx = np.abs(cv2.Sobel(g, cv2.CV_32F, 1, 0, ksize=3))
                    sy = np.abs(cv2.Sobel(g, cv2.CV_32F, 0, 1, ksize=3))
                    small = cv2.GaussianBlur(g, (5, 5), 0)
                    m = np.abs(small - prev_gray_small) if prev_gray_small is not None and prev_gray_small.shape == small.shape else np.zeros_like(small)
                    prev_gray_small = small
                    gx = sx if gx is None else gx + sx
                    gy = sy if gy is None else gy + sy
                    mot = m if mot is None else mot + m
                    edge_n += 1

                if thumb_at is None and t - shot_start >= 0.4:
                    cv2.imwrite(str(thumbs_dir / f"shot{len(shots):03d}.jpg"), frame, [cv2.IMWRITE_JPEG_QUALITY, 82])
                    thumb_at = t
            last_frame = frame
            if fi % 15 == 0:
                progress(min(0.9, 0.9 * fi / total_frames))
        err = reader.error()

    if not an.faces:
        raise RuntimeError("Couldn't read the video frames" + (f": {err[-200:]}" if err else "."))
    real_end = len(an.faces) / sample_fps
    an.duration = min(duration, max(real_end, (fi + 1) / fps))
    finish_shot(an.duration, last_frame)
    an.shots = shots
    progress(0.92)
    vad = detect.SpeechDetector() if info.has_audio else None
    an.speech, an.loud = _audio_features(path, info, start, duration, an.n, sample_fps, vad)
    progress(1.0)
    return an


# ---------------------------------------------------------------- extra passes (Shot editor / Follow this…)


def focus_pass(path: Path, info: MediaInfo, an: Analysis, start: float, cls: int,
               cancelled: Callable[[], bool] = lambda: False, progress: Callable[[float], None] = lambda p: None) -> list[list[Det]]:
    """Detect one object class on every sample (10/s): used by "Follow this: ball / dog / …"."""
    if cls in an.focus:
        return an.focus[cls]
    det = detect.ObjectDetector()
    tracker = Tracker(max_gap=max(3, int(an.sample_fps)))
    out: list[list[Det]] = []
    shot_starts = {s.s0 for s in an.shots}
    with FrameReader(path, info, an.an_size, f"{an.sample_fps:.6f}", start, an.duration) as reader:
        for i, frame in enumerate(reader):
            if cancelled():
                raise Cancelled()
            if i in shot_starts:
                tracker.reset()
            dets = [Det(0, o.x / an.an_size[0], o.y / an.an_size[1], o.w / an.an_size[0], o.h / an.an_size[1], o.score, cls=o.cls)
                    for o in det(frame, {cls}, conf=0.25)]
            tracker.update(dets, i)
            out.append(dets)
            if i % 10 == 0:
                progress(min(1.0, i / max(1, an.n)))
    out += [[] for _ in range(an.n - len(out))]
    an.focus[cls] = out[:an.n]
    return an.focus[cls]


def _make_tracker():
    for name in ("TrackerCSRT", "TrackerKCF"):
        t = getattr(cv2, name, None)
        if t is not None and hasattr(t, "create"):
            return t.create()
    legacy = getattr(cv2, "TrackerCSRT_create", None)
    if legacy is not None:
        return legacy()
    raise RuntimeError("No OpenCV tracker available")


def track_point(path: Path, info: MediaInfo, an: Analysis, start: float, shot: Shot, px: float, py: float,
                cancelled: Callable[[], bool] = lambda: False) -> list[tuple[float, float, float, float] | None]:
    """Click-to-follow: track whatever is under (px, py) on the shot's thumbnail until the shot ends.
    Returns one box (0..1) per sample of the shot, None where the tracker lost it."""
    W, H = an.an_size
    i0 = an.sample_at(shot.thumb_t)
    candidates = an.faces[i0] + [o for j in range(max(shot.s0, i0 - 5), min(shot.s1, i0 + 6)) for o in an.objects[j]]
    hit = [d for d in candidates if d.x <= px <= d.x + d.w and d.y <= py <= d.y + d.h]
    if hit:
        d = min(hit, key=lambda d: d.w * d.h)
        box = (d.x * W, d.y * H, d.w * W, d.h * H)
    else:
        side = 0.2 * H
        box = (px * W - side / 2, py * H - side / 2, side, side)
    box = (max(0, box[0]), max(0, box[1]), min(box[2], W - max(0, box[0])), min(box[3], H - max(0, box[1])))
    n = shot.s1 - shot.s0
    out: list[tuple[float, float, float, float] | None] = [None] * n
    t0 = an.t(i0)
    tracker = None
    kind = (hit and min(hit, key=lambda d: d.w * d.h).cls) if hit else None
    since_snap = 0
    with FrameReader(path, info, an.an_size, f"{an.sample_fps:.6f}", start + t0, max(0.1, shot.end - t0)) as reader:
        for j, frame in enumerate(reader):
            if cancelled():
                raise Cancelled()
            idx = i0 - shot.s0 + j
            if idx >= n:
                break
            if tracker is None:
                tracker = _make_tracker()
                tracker.init(frame, tuple(int(v) for v in box))
                b = box
            else:
                ok, b = tracker.update(frame)
                if not ok:
                    break
            # Snap to a detection of the same kind when one overlaps: the tracker alone slowly drifts.
            si = i0 + j
            cur = Det(0, b[0] / W, b[1] / H, b[2] / W, b[3] / H, 1.0)
            pool = (an.faces[si] if si < an.n else []) + (an.objects[si] if si < an.n else [])
            if kind is not None:
                pool = [d for d in pool if d.cls == kind]
            best = max(pool, key=lambda d: _iou(cur, d), default=None)
            if best is not None and (_iou(cur, best) > 0.25 or (best.x <= cur.cx <= best.x + best.w and best.y <= cur.cy <= best.y + best.h)):
                b = (best.x * W, best.y * H, best.w * W, best.h * H)
                since_snap += 1
                if since_snap % 10 == 0:
                    tracker = _make_tracker()
                    tracker.init(frame, tuple(int(v) for v in b))
            out[idx] = (b[0] / W, b[1] / H, b[2] / W, b[3] / H)
    first = next((b for b in out if b is not None), None)
    for j in range(n):           # before the click: hold the first position
        if out[j] is not None:
            break
        out[j] = first
    return out
