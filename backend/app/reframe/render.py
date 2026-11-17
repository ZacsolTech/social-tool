"""Stage D: draw the plan and encode the MP4.

Smart Reframe: ffmpeg decodes the source -> Python composes every output frame (sub-pixel crops with
cv2.warpAffine, split/facecam stacks, blur fill) -> a second ffmpeg encodes H.264 + the original audio.
Blur Fill / Crop / Fit + Colour: a single ffmpeg filter graph (no AI, about twice as fast).
"""

from __future__ import annotations

import queue
import re
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

from ..config import get_settings
from .analyze import Analysis, Cancelled
from .director import ASPECTS, Plan, ShotPlan, crop_w, max_ch
from .media import FrameReader, MediaInfo, even, ffmpeg_bin, probe, scaled_size, tonemap_prefix


class RenderError(Exception):
    pass


@dataclass
class Look:
    """How empty space is filled (Fit layout, Blur Fill and Fit + Colour modes)."""
    background: str = "blur"     # blur | color
    color: str = "#000000"
    blur: int = 2                # 1 low, 2 medium, 3 high
    dim: float = 0.15            # 0..0.6 darken the blurred background
    fg_zoom: float = 1.0         # 1.0..1.3 enlarge the foreground video

    def bgr(self) -> tuple[int, int, int]:
        h = self.color.lstrip("#")
        if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
            return (0, 0, 0)
        return (int(h[4:6], 16), int(h[2:4], 16), int(h[0:2], 16))


def output_size(aspect: str, quality: str) -> tuple[int, int]:
    w, h = ASPECTS[aspect]
    if quality == "720p":
        return even(w * 2 / 3), even(h * 2 / 3)
    return w, h


def _encode_args(out: Path, info: MediaInfo, start: float, duration: float, fps: str) -> list[str]:
    args: list[str] = []
    if info.has_audio:
        args += ["-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", "{SRC}"]
    args += ["-map", "0:v:0"]
    if info.has_audio:
        args += ["-map", "1:a:0?", "-c:a", "aac", "-b:a", "160k", "-ac", "2"]
    args += [
        "-r", fps, "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
        *_color_tags(info),
        "-movflags", "+faststart", "-shortest", "-f", "mp4", "-y", str(out),
    ]
    return args


def _color_tags(info: MediaInfo) -> list[str]:
    c = info.colors
    trc = "smpte170m" if c == "smpte170m" else "bt709"
    return ["-colorspace", c, "-color_primaries", c, "-color_trc", trc, "-color_range", "tv"]


def _setparams(info: MediaInfo) -> str:
    """Label frames with the colour standard we tag the output with. Without it, ffmpeg 8 'helpfully'
    converts between an untagged source and the tagged output, shifting every colour."""
    c = info.colors
    trc = "smpte170m" if c == "smpte170m" else "bt709"
    return f"setparams=colorspace={c}:color_primaries={c}:color_trc={trc}:range=tv"


def _drain(stream, sink: list[bytes]) -> None:
    for line in iter(stream.readline, b""):
        sink.append(line)
        del sink[:-20]


def _check_output(out: Path, expected: float) -> None:
    if not out.exists() or out.stat().st_size < 1000:
        raise RenderError("The video couldn't be created.")
    got = probe(out).duration
    if got < expected * 0.95 - 0.5:
        raise RenderError(f"The video ended early ({got:.0f}s of {expected:.0f}s).")


# ---------------------------------------------------------------- frame composer


def fit_frame(frame: np.ndarray, OW: int, OH: int, look: Look) -> np.ndarray:
    RH, RW = frame.shape[:2]
    scale = min(OW / RW, OH / RH) * max(1.0, min(1.5, look.fg_zoom))
    fw, fh = max(2, int(round(RW * scale))), max(2, int(round(RH * scale)))
    fg = cv2.resize(frame, (fw, fh), interpolation=cv2.INTER_AREA if scale < 0.5 else cv2.INTER_LINEAR)
    if fw > OW:
        x = (fw - OW) // 2
        fg, fw = fg[:, x:x + OW], OW
    if fh > OH:
        y = (fh - OH) // 2
        fg, fh = fg[y:y + OH], OH
    if look.background == "color":
        out = np.empty((OH, OW, 3), np.uint8)
        out[:] = look.bgr()
    else:
        # Background: built from the (already small) foreground at 1/8 size, blurred and darkened there,
        # then scaled up once. Same look as blurring at full size, ~5x cheaper.
        sw, sh = max(8, OW // 8), max(8, OH // 8)
        cs = max(sw / fw, sh / fh)
        small = cv2.resize(fg, (max(sw, int(np.ceil(fw * cs))), max(sh, int(np.ceil(fh * cs)))), interpolation=cv2.INTER_AREA)
        y0, x0 = (small.shape[0] - sh) // 2, (small.shape[1] - sw) // 2
        small = small[y0:y0 + sh, x0:x0 + sw]
        sigma = {1: 2.5, 2: 4.5, 3: 7.0}.get(look.blur, 4.5)
        small = cv2.GaussianBlur(small, (0, 0), sigma)
        if look.dim > 0:
            small = cv2.convertScaleAbs(small, alpha=1.0 - min(0.8, look.dim))
        out = cv2.resize(small, (OW, OH), interpolation=cv2.INTER_LINEAR)
    y, x = (OH - fh) // 2, (OW - fw) // 2
    out[y:y + fh, x:x + fw] = fg
    return out


def _at(arr: np.ndarray, f: float, cuts: np.ndarray | None) -> float:
    n = len(arr)
    if n == 1 or f <= 0:
        return float(arr[0])
    if f >= n - 1:
        return float(arr[-1])
    j = int(f)
    if cuts is not None and j + 1 < len(cuts) and cuts[j + 1]:
        return float(arr[j])          # hard cut: no sliding between two speakers
    a = f - j
    return float(arr[j] * (1 - a) + arr[j + 1] * a)


def compose(frame: np.ndarray, an: Analysis, sp: ShotPlan, f: float, OW: int, OH: int, look: Look,
            base: tuple[int, int]) -> np.ndarray:
    """One output frame. Panes are planned at `base` size (1080 wide) and scaled to OW x OH (720p)."""
    if sp.layout == "fit" or not sp.panes:
        return fit_frame(frame, OW, OH, look)
    RH, RW = frame.shape[:2]
    sx, sy = OW / base[0], OH / base[1]
    out = np.empty((OH, OW, 3), np.uint8)
    for pane in sp.panes:
        px, py, pw, ph = pane.dst
        x, y, w, h = int(round(px * sx)), int(round(py * sy)), int(round(pw * sx)), int(round(ph * sy))
        w, h = min(w, OW - x), min(h, OH - y)
        cx, cy, ch = _at(pane.cx, f, sp.cuts), _at(pane.cy, f, sp.cuts), _at(pane.ch, f, sp.cuts)
        ch_px = ch * RH
        cw_px = crop_w(an, ch, pane.aspect) * RW
        s = w / cw_px
        x0, y0 = cx * RW - cw_px / 2, cy * RH - ch_px / 2
        j = min(max(0, int(f)), len(pane.cx) - 2) if len(pane.cx) > 1 else 0
        moving = len(pane.cx) > 1 and (
            abs(pane.cx[j + 1] - pane.cx[j]) * RW > 0.05 or abs(pane.cy[j + 1] - pane.cy[j]) * RH > 0.05
            or abs(pane.ch[j + 1] - pane.ch[j]) * RH > 0.05)
        if moving:
            # Sub-pixel crop while the camera moves: no 1-pixel stepping on slow pans.
            m = np.float32([[s, 0, -x0 * s], [0, s, -y0 * s]])
            out[y:y + h, x:x + w] = cv2.warpAffine(frame, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
        else:
            # Still camera: whole-pixel crop + high-quality resize (sharper and ~3x faster).
            xi = int(round(min(max(0.0, x0), RW - cw_px)))
            yi = int(round(min(max(0.0, y0), RH - ch_px)))
            roi = frame[yi:yi + max(1, int(round(ch_px))), xi:xi + max(1, int(round(cw_px)))]
            interp = cv2.INTER_CUBIC if s > 1.0 else cv2.INTER_AREA
            out[y:y + h, x:x + w] = cv2.resize(roi, (w, h), interpolation=interp)
    if len(sp.panes) > 1:
        for pane in sp.panes[1:]:
            yb = int(round(pane.dst[1] * sy))
            out[max(0, yb - 2):yb + 2] = (18, 18, 18)
    return out


class _Encoder:
    """One ffmpeg encoder fed from its own thread, so composing the next frame overlaps writing this one."""

    def __init__(self, src: Path, info: MediaInfo, start: float, duration: float, size: tuple[int, int], out: Path):
        OW, OH = size
        self.tmp = out.with_suffix(".part.mp4")
        self.out = out
        # Frames arrive as YUV 4:2:0 that went through OpenCV's YUV->BGR->YUV round trip, so they carry the
        # source's own colour values: tag them with the source's colour standard.
        cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-nostdin",
               "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{OW}x{OH}", "-r", info.fps_str, *_color_tags(info),
               "-i", "pipe:0"]
        args = [a if a != "{SRC}" else str(src) for a in _encode_args(self.tmp, info, start, duration, info.fps_str)]
        self.proc = subprocess.Popen(cmd + args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                     bufsize=OW * OH * 3 // 2)
        self.err: list[bytes] = []
        self.failed = False
        self.q: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=6)
        threading.Thread(target=_drain, args=(self.proc.stderr, self.err), daemon=True).start()
        self.thread = threading.Thread(target=self._write, daemon=True)
        self.thread.start()

    def _write(self) -> None:
        while True:
            img = self.q.get()
            if img is None:
                break
            if self.failed:
                continue
            try:
                self.proc.stdin.write(memoryview(img).cast("B"))
            except (BrokenPipeError, OSError, ValueError):
                self.failed = True
        try:
            self.proc.stdin.close()
        except OSError:
            pass

    def message(self) -> str:
        return b"".join(self.err).decode(errors="replace")[-300:]

    def put(self, img: np.ndarray) -> None:
        if self.failed:
            raise RenderError("The encoder stopped: " + self.message())
        self.q.put(img)

    def finish(self, expected: float) -> None:
        self.q.put(None)
        self.thread.join()
        code = self.proc.wait()
        if code != 0 or self.failed:
            raise RenderError("The encoder failed: " + self.message())
        _check_output(self.tmp, expected)
        self.tmp.replace(self.out)

    def abort(self) -> None:
        self.failed = True
        try:
            while True:
                self.q.get_nowait()
        except queue.Empty:
            pass
        self.q.put(None)
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()
        self.thread.join(timeout=5)
        self.tmp.unlink(missing_ok=True)


def _prefetch(reader: FrameReader, q: queue.Queue, stop: threading.Event) -> None:
    """Decode ahead on another thread (pipe reads release the GIL)."""
    try:
        for frame in reader:
            while not stop.is_set():
                try:
                    q.put(frame, timeout=0.2)
                    break
                except queue.Full:
                    continue
            if stop.is_set():
                return
    finally:
        q.put(None)


def render_smart_multi(src: Path, info: MediaInfo, an: Analysis, targets: list[tuple[Plan, Path]], start: float,
                       quality: str, look: Look, progress: Callable[[float], None], cancelled: Callable[[], bool]) -> None:
    """Render every format from ONE decode of the source: decode, compose and encode run in parallel."""
    s = get_settings()
    rsize = scaled_size(info, max_h=min(s.reframe_render_max_height, info.height))
    duration = an.duration
    total = max(1, int(duration * info.fps))
    sf = an.sample_fps
    sizes = [output_size(p.aspect, quality) for p, _ in targets]
    encoders: list[_Encoder] = []
    stop = threading.Event()
    try:
        encoders = [_Encoder(src, info, start, duration, size, out) for size, (_, out) in zip(sizes, targets)]
        with FrameReader(src, info, rsize, info.fps_str, start, duration, pix="yuv420p") as reader:
            frames: queue.Queue[np.ndarray | None] = queue.Queue(maxsize=6)
            threading.Thread(target=_prefetch, args=(reader, frames, stop), daemon=True).start()
            ks = [0] * len(targets)
            fi = 0
            while True:
                yuv = frames.get()
                if yuv is None:
                    break
                frame = cv2.cvtColor(yuv, cv2.COLOR_YUV2BGR_I420)
                if cancelled():
                    raise Cancelled()
                t = fi / info.fps
                if t >= duration:
                    break
                for n, ((plan, _), (OW, OH), enc) in enumerate(zip(targets, sizes, encoders)):
                    shots = plan.shots
                    while ks[n] + 1 < len(shots) and t >= shots[ks[n]].shot.end - 1e-6:
                        ks[n] += 1
                    sp = shots[ks[n]]
                    img = compose(frame, an, sp, t * sf - sp.shot.s0, OW, OH, look, plan.size)
                    enc.put(cv2.cvtColor(img, cv2.COLOR_BGR2YUV_I420))
                fi += 1
                if fi % 10 == 0:
                    progress(min(0.99, fi / total))
            stop.set()
        for enc in encoders:
            enc.finish(duration)
        progress(1.0)
    except BaseException:
        stop.set()
        for enc in encoders:
            enc.abort()
        raise


def render_smart(src: Path, info: MediaInfo, an: Analysis, plan: Plan, out: Path, start: float, quality: str,
                 look: Look, progress: Callable[[float], None], cancelled: Callable[[], bool]) -> None:
    render_smart_multi(src, info, an, [(plan, out)], start, quality, look, progress, cancelled)


# ---------------------------------------------------------------- simple modes (one ffmpeg command)


def static_filter(info: MediaInfo, mode: str, aspect: str, quality: str, look: Look, position: float = 0.5,
                  framing: float = 1.0) -> str:
    OW, OH = output_size(aspect, quality)
    W, H = info.width, info.height
    pre = f"{tonemap_prefix(info)}fps={info.fps_str},scale={W}:{H}:out_range=tv,setsar=1,{_setparams(info)}"
    if mode == "crop":
        ch = max_ch_px(W, H, OW / OH) / max(1.0, framing)
        cw = ch * OW / OH
        x = min(max(0.0, position * W - cw / 2), W - cw)
        y = (H - ch) / 2
        return f"[0:v]{pre},crop={even(cw)}:{even(ch)}:{even(x)}:{even(y)},scale={OW}:{OH}:flags=bicubic,format=yuv420p[v]"
    scale = min(OW / W, OH / H) * max(1.0, min(1.5, look.fg_zoom))
    fw, fh = even(W * scale), even(H * scale)
    fg = f"scale={fw}:{fh}:flags=bicubic"
    if fw > OW or fh > OH:
        fg += f",crop={min(fw, OW)}:{min(fh, OH)}"
    if mode == "fit":   # Blur Fill is always blurred; the colour choice only applies to Fit + Colour
        color = look.color.lstrip("#") if re.fullmatch(r"#?[0-9a-fA-F]{6}", look.color) else "000000"
        return (f"[0:v]{pre},{fg},pad={OW}:{OH}:(ow-iw)/2:(oh-ih)/2:color=0x{color},format=yuv420p[v]")
    bw, bh = even(OW / 4), even(OH / 4)
    sigma = {1: 6, 2: 12, 3: 20}.get(look.blur, 12)
    bright = -min(0.6, max(0.0, look.dim)) * 0.6
    return (f"[0:v]{pre},split=2[bg][fg];"
            f"[bg]scale={bw}:{bh}:force_original_aspect_ratio=increase,crop={bw}:{bh},gblur=sigma={sigma},"
            f"eq=brightness={bright:.3f},scale={OW}:{OH}[bgb];"
            f"[fg]{fg}[fgs];[bgb][fgs]overlay=(W-w)/2:(H-h)/2,format=yuv420p[v]")


def max_ch_px(W: int, H: int, aspect: float) -> float:
    return min(float(H), W / aspect)


_OUT_TIME = re.compile(rb"^out_time_us=(\d+)")


def render_static(src: Path, info: MediaInfo, mode: str, aspect: str, quality: str, look: Look, out: Path,
                  start: float, duration: float, position: float, framing: float,
                  progress: Callable[[float], None], cancelled: Callable[[], bool]) -> None:
    tmp = out.with_suffix(".part.mp4")
    graph = static_filter(info, mode, aspect, quality, look, position, framing)
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-nostdin", "-progress", "pipe:1", "-nostats",
           "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(src), "-filter_complex", graph, "-map", "[v]"]
    if info.has_audio:
        cmd += ["-map", "0:a:0?", "-c:a", "aac", "-b:a", "160k", "-ac", "2"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            *_color_tags(info), "-movflags", "+faststart", "-f", "mp4", "-y", str(tmp)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
    err: list[bytes] = []
    threading.Thread(target=_drain, args=(proc.stderr, err), daemon=True).start()
    try:
        for line in iter(proc.stdout.readline, b""):
            if cancelled():
                raise Cancelled()
            m = _OUT_TIME.match(line)
            if m:
                progress(min(0.99, int(m.group(1)) / 1e6 / max(0.1, duration)))
        code = proc.wait()
        if code != 0:
            raise RenderError("The video couldn't be converted: " + b"".join(err).decode(errors="replace")[-300:])
        _check_output(tmp, duration)
        tmp.replace(out)
        progress(1.0)
    except BaseException:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        tmp.unlink(missing_ok=True)
        raise


__all__ = ["Look", "RenderError", "render_smart", "render_smart_multi", "render_static", "output_size", "fit_frame", "compose", "max_ch"]
