"""Burn captions into the video with FFmpeg + libass (plus optional cuts and a brand logo)."""

from __future__ import annotations

import re
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..reframe.media import MediaInfo, even, ffmpeg_bin, probe, tonemap_prefix
from . import cuts as cutmod
from .fonts import FONTS_DIR


class RenderError(Exception):
    pass


class Cancelled(Exception):
    pass


@dataclass
class Logo:
    path: Path
    corner: str = "tr"          # tl | tr | bl | br
    scale: float = 0.16         # logo width / video width
    opacity: float = 0.9


def output_size(info: MediaInfo, quality: str) -> tuple[int, int]:
    """Keep the shape; the short side is at most 1080 (or 720). Never upscale."""
    short = 720 if quality == "720p" else 1080
    s = min(1.0, short / min(info.width, info.height))
    return even(info.width * s), even(info.height * s)


def filter_path(p: Path) -> str:
    """A path as an FFmpeg filter option value (Windows drive colons and quotes escaped)."""
    v = p.resolve().as_posix().replace("'", r"'\''").replace(":", r"\:")
    return f"'{v}'"


def _colors(info: MediaInfo) -> tuple[str, list[str]]:
    c = info.colors
    trc = "smpte170m" if c == "smpte170m" else "bt709"
    return (f"setparams=colorspace={c}:color_primaries={c}:color_trc={trc}:range=tv",
            ["-colorspace", c, "-color_primaries", c, "-color_trc", trc, "-color_range", "tv"])


_OUT_TIME = re.compile(rb"^out_time_us=(\d+)")


def render(src: Path, info: MediaInfo, ass_text: str, out: Path, quality: str,
           keep: list[tuple[float, float]] | None, logo: Logo | None,
           progress: Callable[[float], None], cancelled: Callable[[], bool]) -> None:
    work = out.parent
    ass_path = work / "captions.ass"
    ass_path.write_text(ass_text, encoding="utf-8")
    W, H = output_size(info, quality)
    setparams, color_args = _colors(info)
    cut = keep is not None and not (len(keep) == 1 and keep[0][0] <= 0.01 and keep[0][1] >= info.duration - 0.05)
    expected = cutmod.kept_duration(keep) if cut and keep else info.duration

    v = "[0:v]"
    chain = []
    if cut:
        expr = cutmod.select_expr(keep)
        chain.append(f"fps={info.fps_str},select='{expr}',setpts=N/FRAME_RATE/TB")
    chain.append(f"{tonemap_prefix(info)}scale={W}:{H}:flags=lanczos:out_range=tv,setsar=1,{setparams}")
    chain.append(f"ass=filename={filter_path(ass_path)}:fontsdir={filter_path(FONTS_DIR)}:shaping=complex")
    graph = [f"{v}{','.join(chain)}[cap]"]
    vout = "[cap]"
    if logo is not None and logo.path.exists():
        lw = even(W * logo.scale)
        m = int(round(W * 0.035))
        x = {"tl": f"{m}", "bl": f"{m}"}.get(logo.corner, f"W-w-{m}")
        y = {"tl": f"{m}", "tr": f"{m}"}.get(logo.corner, f"H-h-{m}")
        graph.append(f"[1:v]format=rgba,scale={lw}:-1,colorchannelmixer=aa={logo.opacity:.2f}[lg]")
        graph.append(f"{vout}[lg]overlay={x}:{y}:format=auto,format=yuv420p[v]")
        vout = "[v]"
    aout = None
    if info.has_audio:
        if cut:
            graph.append(f"[0:a]aselect='{cutmod.select_expr(keep)}',asetpts=N/SR/TB[a]")
            aout = "[a]"
        else:
            aout = "0:a:0?"
    graph_file = work / "graph.txt"
    graph_file.write_text(";\n".join(graph), encoding="utf-8")

    tmp = out.with_suffix(".part.mp4")
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-nostdin", "-progress", "pipe:1", "-nostats",
           "-i", str(src)]
    if logo is not None and logo.path.exists():
        cmd += ["-i", str(logo.path)]
    cmd += ["-/filter_complex", str(graph_file), "-map", vout]
    if aout:
        cmd += ["-map", aout, "-c:a", "aac", "-b:a", "160k", "-ac", "2"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p", *color_args,
            "-movflags", "+faststart", "-f", "mp4", "-y", str(tmp)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, cwd=str(work))
    err: list[bytes] = []

    def drain() -> None:
        for line in iter(proc.stderr.readline, b""):
            err.append(line)
            del err[:-30]
    threading.Thread(target=drain, daemon=True).start()
    try:
        for line in iter(proc.stdout.readline, b""):
            if cancelled():
                raise Cancelled()
            m = _OUT_TIME.match(line)
            if m:
                progress(min(0.99, int(m.group(1)) / 1e6 / max(0.1, expected)))
        if proc.wait() != 0:
            msg = b"".join(err).decode(errors="replace")[-400:]
            raise RenderError("The captions couldn't be added to this video. " + msg)
        if not tmp.exists() or tmp.stat().st_size < 1000:
            raise RenderError("The video couldn't be created.")
        got = probe(tmp).duration
        if got < expected * 0.95 - 0.5:
            raise RenderError(f"The video ended early ({got:.0f}s of {expected:.0f}s).")
        tmp.replace(out)
        progress(1.0)
    except BaseException:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        tmp.unlink(missing_ok=True)
        raise
