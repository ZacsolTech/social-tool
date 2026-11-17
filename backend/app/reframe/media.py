"""ffprobe / ffmpeg helpers: read a file's facts, decode frames and audio into numpy."""

from __future__ import annotations

import json
import shutil
import subprocess
import threading
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from fractions import Fraction
from functools import lru_cache
from pathlib import Path

import numpy as np

from ..config import get_settings


class MediaError(Exception):
    """A file we can't use, with a message the visitor can read."""


def ffmpeg_bin() -> str:
    loc = get_settings().ffmpeg_location
    if loc:
        return loc if loc.lower().endswith(("ffmpeg", "ffmpeg.exe")) else str(Path(loc) / "ffmpeg")
    return shutil.which("ffmpeg") or "ffmpeg"


def ffprobe_bin() -> str:
    loc = get_settings().ffmpeg_location
    if loc:
        base = Path(loc).parent if loc.lower().endswith(("ffmpeg", "ffmpeg.exe")) else Path(loc)
        return str(base / "ffprobe")
    return shutil.which("ffprobe") or "ffprobe"


@lru_cache
def has_filter(name: str) -> bool:
    try:
        out = subprocess.run([ffmpeg_bin(), "-hide_banner", "-filters"], capture_output=True, timeout=20).stdout.decode(errors="replace")
    except Exception:  # noqa: BLE001
        return False
    return any(line.split()[1:2] == [name] for line in out.splitlines() if len(line.split()) > 2)


@dataclass
class MediaInfo:
    duration: float
    width: int            # display size: rotation and non-square pixels already applied
    height: int
    fps: float            # frame rate we decode and render at (capped at 60)
    fps_str: str          # same, as a fraction ffmpeg understands exactly ("30000/1001")
    has_audio: bool
    vcodec: str
    rotation: int
    hdr: bool
    size: int
    colors: str = "bt709"   # colour standard to tag the output with: bt709 (HD) or smpte170m (SD)
    square: bool = True     # square pixels (no resize needed to show it at its display size)

    @property
    def landscape(self) -> bool:
        return self.width > self.height

    def public(self) -> dict:
        d = asdict(self)
        d.pop("fps_str")
        d.pop("colors")
        d.pop("square")
        return d


def _rate(s: str | None) -> Fraction | None:
    try:
        f = Fraction(s or "0")
    except (ValueError, ZeroDivisionError):
        return None
    return f if f > 0 else None


def probe(path: Path) -> MediaInfo:
    try:
        res = subprocess.run(
            [ffprobe_bin(), "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
            capture_output=True, timeout=60,
        )
    except subprocess.TimeoutExpired as e:
        raise MediaError("We couldn't read this file. Please try a different video.") from e
    if res.returncode != 0:
        raise MediaError("This file isn't a video we can read. Please upload an MP4, MOV, WebM or MKV.")
    data = json.loads(res.stdout or b"{}")
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video" and not (s.get("disposition") or {}).get("attached_pic")), None)
    if video is None:
        raise MediaError("This file has no video in it.")
    w, h = int(video.get("width") or 0), int(video.get("height") or 0)
    if w < 32 or h < 32:
        raise MediaError("This video is too small to work with.")

    sar = _rate(video.get("sample_aspect_ratio")) or Fraction(1)
    if Fraction(1, 4) <= sar <= 4 and sar != 1:
        w = int(round(w * sar))

    rotation = 0
    for sd in video.get("side_data_list") or []:
        if "rotation" in sd:
            rotation = int(round(float(sd["rotation"])))
    if not rotation and (video.get("tags") or {}).get("rotate"):
        rotation = int((video.get("tags") or {})["rotate"])
    if abs(rotation) % 180 == 90:
        w, h = h, w

    rate = _rate(video.get("avg_frame_rate")) or _rate(video.get("r_frame_rate")) or Fraction(30)
    if rate > 60:
        rate = Fraction(60) if rate > 90 or rate.denominator == 1 else rate / 2
    if rate < 5:
        rate = Fraction(30)
    rate = rate.limit_denominator(1001)

    duration = float((data.get("format") or {}).get("duration") or video.get("duration") or 0)
    if duration <= 0:
        raise MediaError("We couldn't read how long this video is. Please try a different file.")

    transfer = str(video.get("color_transfer") or "")
    space = str(video.get("color_space") or "")
    hdr = transfer in ("smpte2084", "arib-std-b67")
    sd = not hdr and (space in ("smpte170m", "bt470bg") or (not space and h <= 576 and w <= 1024))
    return MediaInfo(
        duration=duration,
        width=w - w % 2,
        height=h - h % 2,
        fps=float(rate),
        fps_str=f"{rate.numerator}/{rate.denominator}",
        has_audio=any(s.get("codec_type") == "audio" for s in streams),
        vcodec=str(video.get("codec_name") or ""),
        rotation=rotation,
        hdr=hdr,
        size=path.stat().st_size,
        colors="smpte170m" if sd else "bt709",
        square=sar == 1 and w % 2 == 0 and h % 2 == 0,
    )


def tonemap_prefix(info: MediaInfo) -> str:
    """HDR phone videos look grey and washed out when squeezed into normal (SDR) video: tone-map them."""
    if info.hdr and has_filter("zscale") and has_filter("tonemap"):
        return ("zscale=t=linear:npl=100,format=gbrpf32le,zscale=p=bt709,"
                "tonemap=hable:desat=0,zscale=t=bt709:m=bt709:r=tv,")
    return ""


def even(v: float) -> int:
    return max(2, int(round(v / 2)) * 2)


def scaled_size(info: MediaInfo, max_w: int | None = None, max_h: int | None = None) -> tuple[int, int]:
    """Fit the display size inside max_w x max_h, keeping the shape (even numbers, never upscaled)."""
    s = 1.0
    if max_w:
        s = min(s, max_w / info.width)
    if max_h:
        s = min(s, max_h / info.height)
    return even(info.width * s), even(info.height * s)


class FrameReader:
    """Decode a file to BGR frames of a fixed size at a fixed rate (ffmpeg does rotation, SAR, HDR)."""

    def __init__(self, path: Path, info: MediaInfo, size: tuple[int, int], fps: str | float,
                 start: float = 0.0, duration: float | None = None, pix: str = "bgr24"):
        """pix="bgr24": H x W x 3 colour frames. pix="yuv420p": raw (H*3/2) x W planes, half the bytes,
        no colour conversion in ffmpeg (the renderer converts with OpenCV and back, losslessly)."""
        self.w, self.h = size
        self.pix = pix
        self.shape = (self.h, self.w, 3) if pix == "bgr24" else (self.h * 3 // 2, self.w)
        self.frame_bytes = self.w * self.h * 3 if pix == "bgr24" else self.w * self.h * 3 // 2
        same = (self.w, self.h) == (info.width, info.height) and info.square
        # Limited ("TV") range always: phone videos are often full range and would look washed out or crushed.
        scale = f"scale={self.w}:{self.h}:out_range=tv" + ("" if same else ":flags=area")
        vf = f"{tonemap_prefix(info)}fps={fps},{scale},setsar=1,format={pix}"
        cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-nostdin"]
        if start > 0:
            cmd += ["-ss", f"{start:.3f}"]
        if duration is not None:
            cmd += ["-t", f"{duration:.3f}"]
        cmd += ["-i", str(path), "-an", "-sn", "-dn", "-vf", vf, "-f", "rawvideo", "-pix_fmt", pix, "pipe:1"]
        self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                                     bufsize=self.frame_bytes * 2)
        self._err: list[bytes] = []
        threading.Thread(target=self._drain, daemon=True).start()

    def _drain(self) -> None:
        for line in iter(self.proc.stderr.readline, b""):
            self._err.append(line)
            del self._err[:-10]

    def __iter__(self) -> Iterator[np.ndarray]:
        out = self.proc.stdout
        while True:
            frame = np.empty(self.shape, np.uint8)   # read straight into the array: no extra copy
            mv = memoryview(frame).cast("B")
            got = 0
            while got < self.frame_bytes:
                n = out.readinto(mv[got:])
                if not n:
                    return
                got += n
            yield frame

    def error(self) -> str:
        return b"".join(self._err).decode(errors="replace").strip()

    def close(self) -> None:
        if self.proc.poll() is None:
            self.proc.kill()
        self.proc.wait()
        for s in (self.proc.stdout, self.proc.stderr):
            try:
                s.close()
            except Exception:  # noqa: BLE001
                pass

    def __enter__(self) -> FrameReader:
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def read_audio(path: Path, start: float = 0.0, duration: float | None = None, sr: int = 16000) -> np.ndarray:
    """Mono float32 audio at `sr` Hz (empty if the file has no sound)."""
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-nostdin"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    if duration is not None:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-i", str(path), "-vn", "-ac", "1", "-ar", str(sr), "-f", "f32le", "pipe:1"]
    res = subprocess.run(cmd, capture_output=True, timeout=600)
    if res.returncode != 0:
        return np.zeros(0, np.float32)
    return np.frombuffer(res.stdout, np.float32).copy()
