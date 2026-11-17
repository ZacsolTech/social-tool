"""Stages B and C: the "Auto Director".

For every shot it decides a layout (Follow / Split Screen / Screen + Facecam / Fit) and then plans the
camera: who to frame, where their eyes sit, how the crop moves (dead zone, speed limit, easing),
speaker switches and dynamic-zoom punch-ins. Everything here is plain numbers; render.py draws it.

Coordinates are fractions of the source frame (0..1). A crop is (cx, cy, ch): its centre and its
height as a fraction of the source height; its width follows from the pane's shape.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from .analyze import Analysis, Det, Shot
from .detect import COCO, PERSON

ASPECTS = {"9:16": (1080, 1920), "4:5": (1080, 1350), "1:1": (1080, 1080)}
LAYOUTS = ("follow", "split", "facecam", "fit")

# Share of the output width on the right covered by each app's like/comment/share buttons.
SAFE_RIGHT = {"tiktok": 0.13, "reels": 0.12, "shorts": 0.12, "none": 0.0}

EYE_LINE = 0.38       # eyes this far down the frame (rule of thirds, clear of the caption area)


@dataclass
class Options:
    aspect: str = "9:16"
    style: str = "steady"            # steady | follow
    framing: float = 1.0             # 1.0 = whole height; up to 1.6 = tighter
    dynamic_zoom: bool = False
    zoom_amount: float = 1.12
    split: bool = True               # allow Split Screen
    facecam: bool = True             # allow Screen + Facecam
    text_aware: bool = True          # never cut slides / big on-screen text
    two_person: str = "auto"         # auto | split | switch
    safe_zone: str = "tiktok"        # tiktok | reels | shorts | none
    focus_cls: int | None = None     # "Follow this…" object class (COCO id)


@dataclass
class Override:
    layout: str | None = None
    center: float | None = None      # fixed crop centre (manual drag), 0..1
    track: int | None = None         # follow this person / object track
    point: tuple[float, float] | None = None   # click-to-follow position on the thumbnail


@dataclass
class Pane:
    dst: tuple[int, int, int, int]   # x, y, w, h in output pixels
    cx: np.ndarray                   # per sample of the shot
    cy: np.ndarray
    ch: np.ndarray

    @property
    def aspect(self) -> float:
        return self.dst[2] / self.dst[3]


@dataclass
class ShotPlan:
    shot: Shot
    layout: str
    reason: str
    panes: list[Pane] = field(default_factory=list)
    cuts: np.ndarray | None = None   # bool per sample: a hard cut (speaker switch) happens at this sample
    subjects: list[int] = field(default_factory=list)


@dataclass
class Plan:
    aspect: str
    size: tuple[int, int]
    shots: list[ShotPlan]


# ---------------------------------------------------------------- helpers


def max_ch(an: Analysis, pane_aspect: float) -> float:
    """Tallest crop (fraction of source height) whose width still fits in the source."""
    return float(min(1.0, an.width / (an.height * pane_aspect)))


def crop_w(an: Analysis, ch: float, pane_aspect: float) -> float:
    return ch * an.height * pane_aspect / an.width


def clamp_center(c: np.ndarray | float, size: np.ndarray | float) -> np.ndarray:
    size = np.minimum(size, 1.0)
    return np.clip(c, size / 2, 1 - size / 2)


def _ffill(a: np.ndarray) -> np.ndarray | None:
    a = a.astype(np.float64).copy()
    ok = ~np.isnan(a)
    if not ok.any():
        return None
    idx = np.where(ok, np.arange(len(a)), 0)
    np.maximum.accumulate(idx, out=idx)
    a = a[idx]
    first = int(np.argmax(ok))
    a[:first] = a[first]
    return a


def _median(a: np.ndarray, win: int) -> np.ndarray:
    if len(a) < 3 or win < 3:
        return a
    pad = win // 2
    p = np.pad(a, pad, mode="edge")
    return np.array([np.median(p[i:i + win]) for i in range(len(a))])


def _ema_zero_phase(a: np.ndarray, alpha: float) -> np.ndarray:
    if len(a) < 2:
        return a
    f = a.copy()
    for i in range(1, len(f)):
        f[i] = f[i - 1] + alpha * (f[i] - f[i - 1])
    for i in range(len(f) - 2, -1, -1):
        f[i] = f[i + 1] + alpha * (f[i] - f[i + 1])
    return f


def camera_path(raw: np.ndarray, sf: float, style: str, span: float) -> np.ndarray | None:
    """Turn a jumpy target (NaN = unknown) into a camera move a human operator would make.
    `span` is the crop size in the same units (dead zone and speed scale with it)."""
    a = _ffill(raw)
    if a is None:
        return None
    a = _median(a, max(3, int(0.5 * sf) | 1))
    steady = style != "follow"
    dz = (0.14 if steady else 0.035) * span
    vmax = (0.75 if steady else 1.8) * span / sf
    settle = 0.2 * dz
    head = a[: max(1, int(sf))]
    p = float(np.median(head))
    moving = False
    out = np.empty_like(a)
    for i, x in enumerate(a):
        d = x - p
        if abs(d) > dz:
            moving = True
        if moving:
            step = np.clip(d, -vmax, vmax)
            p += step
            if abs(x - p) < settle:
                moving = False
        out[i] = p
    return _ema_zero_phase(out, 0.22 if steady else 0.35)


# ---------------------------------------------------------------- subjects


@dataclass
class TrackSummary:
    track: int
    kind: str          # face | person | object
    cls: int
    count: int
    cx: float
    cy: float
    w: float
    h: float
    x0: float
    x1: float
    dets: dict[int, Det]   # sample index -> detection


def _summaries(per_sample: list[list[Det]], s0: int, s1: int, kind: str, cls: int | None = None) -> list[TrackSummary]:
    by: dict[int, dict[int, Det]] = {}
    for i in range(s0, s1):
        for d in per_sample[i] if i < len(per_sample) else []:
            if cls is not None and d.cls != cls:
                continue
            by.setdefault(d.track, {})[i] = d
    out = []
    for tid, dets in by.items():
        ds = list(dets.values())
        out.append(TrackSummary(
            track=tid, kind=kind, cls=ds[0].cls, count=len(ds),
            cx=float(np.median([d.cx for d in ds])), cy=float(np.median([d.cy for d in ds])),
            w=float(np.median([d.w for d in ds])), h=float(np.median([d.h for d in ds])),
            x0=float(np.median([d.x for d in ds])), x1=float(np.median([d.x + d.w for d in ds])), dets=dets,
        ))
    return out


def main_faces(an: Analysis, shot: Shot) -> list[TrackSummary]:
    n = max(1, shot.s1 - shot.s0)
    tracks = _summaries(an.faces, shot.s0, shot.s1, "face")
    need = max(2, int(0.25 * n)) if n >= 8 else 1
    tracks = [t for t in tracks if t.count >= need]
    if not tracks:
        return []
    big = max(t.h for t in tracks)
    tracks = [t for t in tracks if t.h >= 0.35 * big]   # drop tiny background faces
    tracks.sort(key=lambda t: t.count * t.h, reverse=True)
    return tracks[:4]


def _object_tracks(an: Analysis, shot: Shot, cls: int, source: list[list[Det]] | None = None) -> list[TrackSummary]:
    tracks = _summaries(source if source is not None else an.objects, shot.s0, shot.s1, "person" if cls == PERSON else "object", cls)
    tracks.sort(key=lambda t: t.count * (t.w * t.h) ** 0.5, reverse=True)
    return tracks


def _eye_y(d: Det, kind: str) -> float:
    if kind == "face":
        return d.y + 0.4 * d.h
    if kind == "person":
        return d.y + 0.1 * d.h
    return d.cy


def _target_series(an: Analysis, shot: Shot, ts: TrackSummary, cw: float, safe: float) -> tuple[np.ndarray, np.ndarray]:
    n = shot.s1 - shot.s0
    xs, ys = np.full(n, np.nan), np.full(n, np.nan)
    for i, d in ts.dets.items():
        j = i - shot.s0
        if 0 <= j < n:
            look = 0.10 * cw * d.yaw if ts.kind == "face" else 0.0
            xs[j] = d.cx + look + safe * cw
            ys[j] = _eye_y(d, ts.kind)
    return xs, ys


# ---------------------------------------------------------------- active speaker


def speaker_timeline(an: Analysis, shot: Shot, tracks: list[TrackSummary]) -> tuple[np.ndarray, np.ndarray, dict[int, float]]:
    """Who is talking at each sample. Returns (track per sample, cut flags, speaking share per track).

    Mouth movement (from the face landmarks) is compared between people only while the audio says
    someone is speaking. A new speaker takes over after leading for 1 s, the current one is held for
    at least 1.5 s, and the cut is placed where the new speaker started, like an editor would."""
    n = shot.s1 - shot.s0
    sf = an.sample_fps
    ids = [t.track for t in tracks]
    m = np.full((len(ids), n), np.nan)
    for k, t in enumerate(tracks):
        for i, d in t.dets.items():
            j = i - shot.s0
            if 0 <= j < n:
                m[k, j] = d.mouth
    present = ~np.isnan(m)
    win = max(3, int(0.6 * sf))
    kernel = np.ones(win) / win
    sm = np.vstack([np.convolve(np.nan_to_num(row), kernel, mode="same") for row in m])
    cover = np.vstack([np.convolve(p.astype(float), kernel, mode="same") for p in present])
    sm = np.where(cover > 0.3, sm / np.maximum(cover, 1e-6), -1.0)
    speech = an.speech[shot.s0:shot.s1] if an.speech.size >= shot.s1 else np.ones(n)
    talking = speech > 0.45

    lead_need, hold_need = int(1.0 * sf), int(1.5 * sf)
    first = slice(0, max(1, int(1.5 * sf)))
    cur = int(np.argmax(np.nanmean(np.where(sm[:, first] >= 0, sm[:, first], 0), axis=1) + 0.001 * present[:, first].sum(1)))
    sel = np.zeros(n, int)
    cuts = np.zeros(n, bool)
    last_switch, lead_k, lead_start, lead_len = 0, -1, 0, 0
    for j in range(n):
        best = int(np.argmax(sm[:, j]))
        challenger = (
            best != cur and sm[best, j] > 0 and talking[j]
            and sm[best, j] > 1.3 * max(sm[cur, j], 0) + 0.03
        )
        lost = not present[cur, max(0, j - int(sf)):j + 1].any() and present[:, j].any()
        if lost:
            other = int(np.argmax(np.where(present[:, j], sm[:, j] + 1, -1)))
            if other != cur and j - last_switch >= hold_need // 2:
                cur, last_switch = other, j
                cuts[j] = True
                lead_len = 0
        elif challenger:
            if best != lead_k:
                lead_k, lead_start, lead_len = best, j, 0
            lead_len += 1
            if lead_len >= lead_need and lead_start - last_switch >= hold_need:
                cur = best
                sel[lead_start:j + 1] = cur
                cuts[lead_start] = True
                last_switch, lead_len, lead_k = lead_start, 0, -1
        elif talking[j]:
            lead_len, lead_k = 0, -1
        sel[j] = cur
    share: dict[int, float] = {}
    total = max(1, int(talking.sum()))
    for k, tid in enumerate(ids):
        share[tid] = float(((sel == k) & talking).sum()) / total
    return np.array([ids[k] for k in sel]), cuts, share


# ---------------------------------------------------------------- zoom


def zoom_curve(an: Analysis, opts: Options, s0: int, s1: int, avoid: np.ndarray, state: dict) -> np.ndarray:
    """Short punch-ins on loud, emphasised moments (only where someone is speaking)."""
    n = s1 - s0
    z = np.ones(n)
    if not opts.dynamic_zoom or an.loud.size < s1 or n < 3:
        return z
    sf = an.sample_fps
    if "thr" not in state:
        voiced = an.loud[an.speech > 0.5] if an.speech.size == an.loud.size else an.loud
        # Loud = top 12% of the speech AND clearly (6 dB) above the typical level, so flat audio never zooms.
        state["thr"] = max(float(np.percentile(voiced, 88)), float(np.median(voiced)) + 6.0) if voiced.size > 20 else 1e9
        state["last"] = -1e9
    thr = state["thr"]
    attack, hold, release = int(0.25 * sf), int(1.0 * sf), int(0.5 * sf)
    nb = max(1, int(0.5 * sf))
    loud = an.loud[s0:s1]
    speech = an.speech[s0:s1] if an.speech.size >= s1 else np.ones(n)
    for j in range(int(0.6 * sf), n - attack - hold - release):
        t = (s0 + j) / sf
        if loud[j] < thr or speech[j] < 0.5 or t - state["last"] < 4.0:
            continue
        if loud[j] < loud[max(0, j - nb):j + nb + 1].max():
            continue
        if avoid[max(0, j - int(0.6 * sf)):j + attack + hold + release].any():
            continue
        amt = opts.zoom_amount - 1
        for a in range(attack):
            k = j + a
            e = (a + 1) / attack
            z[k] = max(z[k], 1 + amt * (e * e * (3 - 2 * e)))
        z[j + attack:j + attack + hold] = 1 + amt
        for r in range(release):
            k = j + attack + hold + r
            e = 1 - (r + 1) / release
            z[k] = max(z[k], 1 + amt * (e * e * (3 - 2 * e)))
        state["last"] = t
    return z


# ---------------------------------------------------------------- layouts


def _follow(an: Analysis, opts: Options, shot: Shot, dst: tuple[int, int, int, int], subject_x: np.ndarray,
            eye_y: np.ndarray, subject_h: float, kind: str, cuts: np.ndarray, zoom_state: dict) -> Pane:
    n = shot.s1 - shot.s0
    aspect = dst[2] / dst[3]
    mc = max_ch(an, aspect)
    ch = mc / max(1.0, opts.framing)
    if kind == "face":
        ch = max(ch, min(mc, subject_h * 2.4))   # a close-up must not cut the face
    cw = crop_w(an, ch, aspect)
    cx = np.empty(n)
    ey = np.empty(n)
    bounds = [0, *[int(i) for i in np.flatnonzero(cuts) if i > 0], n]
    for a, b in zip(bounds[:-1], bounds[1:]):
        px = camera_path(subject_x[a:b], an.sample_fps, opts.style, cw)
        py = camera_path(eye_y[a:b], an.sample_fps, opts.style, ch)
        cx[a:b] = px if px is not None else 0.5
        ey[a:b] = py if py is not None else 0.5 - (0.5 - EYE_LINE) * ch
    z = zoom_curve(an, opts, shot.s0, shot.s1, cuts, zoom_state)
    chs = ch / z
    cws = crop_w(an, chs, aspect)
    cys = ey + (0.5 - EYE_LINE) * chs
    return Pane(dst, clamp_center(cx, cws), clamp_center(cys, chs), chs)


def _static(an: Analysis, dst: tuple[int, int, int, int], n: int, cx: float, cy: float, ch: float) -> Pane:
    aspect = dst[2] / dst[3]
    ch = min(ch, max_ch(an, aspect))
    cw = crop_w(an, ch, aspect)
    return Pane(dst, clamp_center(np.full(n, cx), cw), clamp_center(np.full(n, cy), ch), np.full(n, ch))


def _split(an: Analysis, opts: Options, shot: Shot, a: TrackSummary, b: TrackSummary, size: tuple[int, int],
           safe: float) -> list[Pane]:
    OW, OH = size
    top, bottom = sorted([a, b], key=lambda t: t.cx)
    half = OH // 2
    panes = []
    for ts, dst in ((top, (0, 0, OW, half)), (bottom, (0, half, OW, OH - half))):
        aspect = dst[2] / dst[3]
        mc = max_ch(an, aspect)
        ch = float(np.clip(ts.h / 0.34, 0.3, mc))
        cw = crop_w(an, ch, aspect)
        xs, ys = _target_series(an, shot, ts, cw, safe * 0.5)
        px = camera_path(xs, an.sample_fps, "steady", cw)
        py = camera_path(ys, an.sample_fps, "steady", ch)
        n = shot.s1 - shot.s0
        cx = px if px is not None else np.full(n, ts.cx)
        ey = py if py is not None else np.full(n, ts.cy)
        cy = ey + (0.5 - 0.42) * ch
        panes.append(Pane(dst, clamp_center(cx, cw), clamp_center(cy, np.full(n, ch)), np.full(n, ch)))
    return panes


def _facecam(an: Analysis, shot: Shot, rect: tuple[float, float, float, float], size: tuple[int, int]) -> list[Pane]:
    OW, OH = size
    n = shot.s1 - shot.s0
    rx, ry, rw, rh = rect
    cam_aspect = (rw * an.width) / (rh * an.height)
    top_h = int(np.clip(OW / cam_aspect, 0.30 * OH, 0.42 * OH)) // 2 * 2
    top = (0, 0, OW, top_h)
    bottom = (0, top_h, OW, OH - top_h)
    ta = OW / top_h
    # Fit the pane's shape inside the webcam box.
    ch = rh
    if crop_w(an, ch, ta) > rw:
        ch = rw * an.width / (an.height * ta)
    cam = _static(an, top, n, rx + rw / 2, ry + rh / 2, ch)
    # Screen / gameplay: the full height, centred on the widest area not covered by the webcam.
    ba = bottom[2] / bottom[3]
    bch = max_ch(an, ba)
    bcw = crop_w(an, bch, ba)
    left_gap, right_gap = rx, 1 - (rx + rw)
    centre = (rx + rw + 1) / 2 if right_gap >= left_gap else rx / 2
    centre = float(np.clip(centre, 0.38, 0.62)) if bcw < 1 else 0.5
    screen = _static(an, bottom, n, centre, 0.5, bch)
    return [cam, screen]


# ---------------------------------------------------------------- the director


def _text_heavy(shot: Shot, cw: float) -> bool:
    if shot.text_cover >= 0.12:
        return True
    if shot.text_cover >= 0.03 and shot.text_span is not None:
        return (shot.text_span[1] - shot.text_span[0]) > cw * 1.05
    return False


def plan_shot(an: Analysis, opts: Options, shot: Shot, ov: Override, size: tuple[int, int], zoom_state: dict,
              point_boxes: list | None = None, focus: list[list[Det]] | None = None) -> ShotPlan:
    OW, OH = size
    n = max(0, shot.s1 - shot.s0)
    full = (0, 0, OW, OH)
    aspect = OW / OH
    mc = max_ch(an, aspect)
    base_ch = mc / max(1.0, opts.framing)
    cw = crop_w(an, base_ch, aspect)
    safe = SAFE_RIGHT.get(opts.safe_zone, 0.0) / 2
    no_cuts = np.zeros(n, bool)

    if n == 0:
        return ShotPlan(shot, "fit", "Very short shot", [], no_cuts)

    forced = ov.layout if ov.layout in LAYOUTS else None
    faces = main_faces(an, shot)

    if forced == "fit":
        return ShotPlan(shot, "fit", "Chosen in the editor", [], no_cuts)
    if ov.center is not None and forced in (None, "follow"):
        return ShotPlan(shot, "follow", "Position set in the editor",
                        [_static(an, full, n, ov.center, 0.5, base_ch)], no_cuts)
    if forced == "facecam" or (forced is None and opts.facecam and shot.facecam):
        rect = shot.facecam
        if rect is None and faces:
            f = faces[0]
            rect = (max(0, f.cx - 1.6 * f.w), max(0, f.cy - 1.2 * f.h), min(1, 3.2 * f.w), min(1, 2.8 * f.h))
        if rect is not None:
            return ShotPlan(shot, "facecam", "Webcam over a screen recording" if shot.facecam else "Chosen in the editor",
                            _facecam(an, shot, rect, size), no_cuts, [faces[0].track] if faces else [])

    # Who to follow.
    subject: TrackSummary | None = None
    label = "person"
    if point_boxes:
        xs = np.array([np.nan if b is None else b[0] + b[2] / 2 for b in point_boxes], float)
        ys = np.array([np.nan if b is None else b[1] + b[3] / 2 for b in point_boxes], float)
        if not np.isnan(xs).all():
            pane = _follow(an, opts, shot, full, xs + safe * cw, ys, 0.0, "object", no_cuts, zoom_state)
            return ShotPlan(shot, "follow", "Following what you clicked", [pane], no_cuts)
    if ov.track is not None:
        pool = _summaries(an.faces, shot.s0, shot.s1, "face") + _summaries(an.objects, shot.s0, shot.s1, "object")
        if focus is not None:
            pool += _summaries(focus, shot.s0, shot.s1, "object")
        subject = next((t for t in pool if t.track == ov.track), None)
        if subject is not None and subject.kind == "object" and subject.cls == PERSON:
            subject.kind = "person"
        label = "chosen person" if subject and subject.kind != "object" else "chosen object"
    if subject is None and opts.focus_cls is not None and focus is not None:
        objs = _object_tracks(an, shot, opts.focus_cls, focus)
        if objs:
            subject = objs[0]
            label = COCO[opts.focus_cls]
    if subject is not None:
        xs, ys = _target_series(an, shot, subject, cw, safe)
        pane = _follow(an, opts, shot, full, xs, ys, subject.h, subject.kind, no_cuts, zoom_state)
        return ShotPlan(shot, "follow", f"Following the {label}", [pane], no_cuts, [subject.track])

    if faces and opts.text_aware and forced is None and _text_heavy(shot, cw):
        return ShotPlan(shot, "fit", "Keeps on-screen text readable", [], no_cuts)

    if len(faces) >= 2:
        group = faces[:4]
        span = max(t.x1 for t in group) - min(t.x0 for t in group)
        if span <= 0.85 * cw and forced != "split":
            xs = np.full(n, np.nan)
            ys = np.full(n, np.nan)
            for j in range(n):
                ds = [t.dets.get(shot.s0 + j) for t in group]
                ds = [d for d in ds if d is not None]
                if ds:
                    xs[j] = (min(d.x for d in ds) + max(d.x + d.w for d in ds)) / 2 + safe * cw
                    ys[j] = float(np.mean([_eye_y(d, "face") for d in ds]))
            pane = _follow(an, opts, shot, full, xs, ys, max(t.h for t in group), "face", no_cuts, zoom_state)
            return ShotPlan(shot, "follow", "Keeping everyone in frame", [pane], no_cuts, [t.track for t in group])

        sel, cuts, share = speaker_timeline(an, shot, group)
        a, b = group[0], group[1]
        rapid = cuts.sum() / max(1e-6, shot.duration / 60) > 8
        both = min(share.get(a.track, 0), share.get(b.track, 0)) >= 0.2
        want_split = forced == "split" or (
            forced is None and opts.split and len(group) == 2 and shot.duration >= 3
            and (opts.two_person == "split" or (opts.two_person == "auto" and both and rapid))
        )
        if want_split:
            return ShotPlan(shot, "split", "Two people talking" if forced is None else "Chosen in the editor",
                            _split(an, opts, shot, a, b, size, safe), no_cuts, [a.track, b.track])
        if forced is None and len(group) >= 3 and max(share.values() or [0]) < 0.45:
            return ShotPlan(shot, "fit", "Group shot: everyone stays in frame", [], no_cuts)
        by_id = {t.track: t for t in group}
        xs = np.full(n, np.nan)
        ys = np.full(n, np.nan)
        for j in range(n):
            d = by_id[int(sel[j])].dets.get(shot.s0 + j)
            if d is not None:
                xs[j] = d.cx + 0.10 * cw * d.yaw + safe * cw
                ys[j] = _eye_y(d, "face")
        # camera_path fills gaps per speaker segment, so a missing sample never pulls toward the other person.
        pane = _follow(an, opts, shot, full, xs, ys, max(t.h for t in group[:2]), "face", cuts, zoom_state)
        return ShotPlan(shot, "follow", "Following whoever is speaking", [pane], cuts, [t.track for t in group])

    if len(faces) == 1:
        xs, ys = _target_series(an, shot, faces[0], cw, safe)
        pane = _follow(an, opts, shot, full, xs, ys, faces[0].h, "face", no_cuts, zoom_state)
        return ShotPlan(shot, "follow", "Following the speaker", [pane], no_cuts, [faces[0].track])

    people = _object_tracks(an, shot, PERSON)
    if people and forced != "fit":
        p = people[0]
        if opts.text_aware and forced is None and _text_heavy(shot, cw):
            return ShotPlan(shot, "fit", "Keeps on-screen text readable", [], no_cuts)
        xs, ys = _target_series(an, shot, p, cw, safe)
        pane = _follow(an, opts, shot, full, xs, ys, p.h, "person", no_cuts, zoom_state)
        return ShotPlan(shot, "follow", "Following the person", [pane], no_cuts, [p.track])

    if forced in ("follow", "split"):
        return ShotPlan(shot, "follow", "No person found: centred",
                        [_static(an, full, n, 0.5, 0.5, base_ch)], no_cuts)
    return ShotPlan(shot, "fit", "No person found: whole frame kept", [], no_cuts)


def plan(an: Analysis, opts: Options, overrides: dict[int, Override] | None = None,
         point_boxes: dict[int, list] | None = None, focus: list[list[Det]] | None = None) -> Plan:
    size = ASPECTS[opts.aspect]
    overrides = overrides or {}
    zoom_state: dict = {}
    shots = [plan_shot(an, opts, s, overrides.get(s.index, Override()), size, zoom_state,
                       (point_boxes or {}).get(s.index), focus) for s in an.shots]
    return Plan(opts.aspect, size, shots)


# ---------------------------------------------------------------- for the shot editor


def describe(an: Analysis, p: Plan) -> list[dict]:
    """What the editor shows per shot: thumbnail, layout, crop boxes and the people it can pick."""
    out = []
    W, H = p.size
    for sp in p.shots:
        s = sp.shot
        j = max(0, min(s.s1 - s.s0 - 1, an.sample_at(s.thumb_t) - s.s0))
        crops = []
        for pane in sp.panes:
            if len(pane.cx) == 0:
                continue
            ch = float(pane.ch[j])
            cw = crop_w(an, ch, pane.aspect)
            crops.append({
                "box": [round(float(pane.cx[j]) - cw / 2, 4), round(float(pane.cy[j]) - ch / 2, 4), round(cw, 4), round(ch, 4)],
                "dst": [round(pane.dst[0] / W, 4), round(pane.dst[1] / H, 4), round(pane.dst[2] / W, 4), round(pane.dst[3] / H, 4)],
            })
        i = s.s0 + j
        faces = sorted(an.faces[i] if i < an.n else [], key=lambda d: d.cx)
        near = [o for k in range(max(s.s0, i - 3), min(s.s1, i + 4)) for o in an.objects[k]]
        seen, objs = set(), []
        for o in sorted(near, key=lambda d: -d.score):
            if o.track not in seen:
                seen.add(o.track)
                objs.append(o)
        out.append({
            "index": s.index,
            "start": round(s.start, 3),
            "end": round(s.end, 3),
            "thumb_t": round(s.thumb_t, 3),
            "layout": sp.layout,
            "reason": sp.reason,
            "crops": crops,
            "faces": [{"track": d.track, "label": chr(65 + k), "box": d.to_list()[1:5]} for k, d in enumerate(faces[:6])],
            "objects": [{"track": o.track, "label": COCO[o.cls], "box": o.to_list()[1:5]} for o in objs[:8]],
            "subjects": sp.subjects,
            "facecam": [round(v, 4) for v in s.facecam] if s.facecam else None,
            "has_text": s.text_cover >= 0.03,
        })
    return out
