"""Turn one chosen moment into a finished clip.

Step 1, the frame: the moment is cut from the source and reframed (Smart Reframe follows the speaker,
Blur Fill / Fit keep the whole picture, Original keeps the shape). Step 2, the words: the clip's own
transcript (times relative to the clip) is burned in with the caption tool's renderer, with the hook title,
keyword colours, emojis and optional filler/silence cuts. Step 1's file is kept, so caption-only changes
re-render in seconds.
"""

from __future__ import annotations

import re
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..captions import ass as assmod
from ..captions import cuts as cutmod
from ..captions import enhance
from ..captions import render as crender
from ..captions.styles import Style
from ..captions.transcript import Line, Transcript, Word, normalize
from ..reframe.analyze import analyze
from ..reframe.director import ASPECTS, Options, plan
from ..reframe.media import MediaInfo, even, ffmpeg_bin, probe, tonemap_prefix
from ..reframe.render import Look, RenderError, render_smart_multi, render_static

ASPECT_CHOICES = ("9:16", "1:1", "4:5", "original")
LAYOUTS = ("smart", "blur", "fit")


@dataclass
class ClipLook:
    """What a clip looks like. Everything here can change per clip in the editor."""
    aspect: str = "9:16"
    layout: str = "smart"
    captions: bool = True
    style: Style | None = None
    hook: bool = True
    hook_seconds: float = 4.0
    remove_fillers: bool = False
    remove_silences: bool = False
    progress_bar: bool = False
    watermark: bool = False
    quality: str = "1080p"

    def frame_key(self, start: float, end: float) -> tuple:
        return (round(start, 3), round(end, 3), self.aspect, self.layout, self.quality)


def _phase(progress: Callable[[float], None], lo: float, hi: float) -> Callable[[float], None]:
    return lambda p: progress(lo + (hi - lo) * max(0.0, min(1.0, p)))


def effective_aspect(info: MediaInfo, aspect: str) -> str:
    """'original' when the source already has (about) the shape asked for: nothing to reframe."""
    if aspect == "original":
        return "original"
    w, h = ASPECTS[aspect]
    return "original" if abs(info.width / info.height - w / h) < 0.04 else aspect


_OUT_TIME = re.compile(rb"^out_time_us=(\d+)")


def _run(cmd: list[str], expected: float, out: Path, progress: Callable[[float], None],
         cancelled: Callable[[], bool]) -> None:
    tmp = out.with_suffix(".part.mp4")
    cmd = [*cmd[:-1], str(tmp)]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
    err: list[bytes] = []

    def drain() -> None:
        for line in iter(proc.stderr.readline, b""):
            err.append(line)
            del err[:-20]
    threading.Thread(target=drain, daemon=True).start()
    try:
        for line in iter(proc.stdout.readline, b""):
            if cancelled():
                from ..reframe.analyze import Cancelled
                raise Cancelled()
            m = _OUT_TIME.match(line)
            if m:
                progress(min(0.99, int(m.group(1)) / 1e6 / max(0.1, expected)))
        if proc.wait() != 0:
            raise RenderError("The clip couldn't be cut: " + b"".join(err).decode(errors="replace")[-300:])
        if not tmp.exists() or tmp.stat().st_size < 1000:
            raise RenderError("The clip couldn't be created.")
        tmp.replace(out)
        progress(1.0)
    except BaseException:
        if proc.poll() is None:
            proc.kill()
        proc.wait()
        tmp.unlink(missing_ok=True)
        raise


def cut(src: Path, info: MediaInfo, start: float, duration: float, out: Path, quality: str,
        progress: Callable[[float], None], cancelled: Callable[[], bool]) -> None:
    """Frame-accurate cut, original shape, short side at most 1080 (or 720)."""
    W, H = crender.output_size(info, quality)
    c = info.colors
    trc = "smpte170m" if c == "smpte170m" else "bt709"
    vf = (f"{tonemap_prefix(info)}fps={info.fps_str},scale={W}:{H}:flags=lanczos:out_range=tv,setsar=1,"
          f"setparams=colorspace={c}:color_primaries={c}:color_trc={trc}:range=tv,format=yuv420p")
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-nostdin", "-progress", "pipe:1", "-nostats",
           "-ss", f"{start:.3f}", "-t", f"{duration:.3f}", "-i", str(src), "-map", "0:v:0", "-vf", vf]
    if info.has_audio:
        cmd += ["-map", "0:a:0?", "-c:a", "aac", "-b:a", "160k", "-ac", "2"]
    cmd += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
            "-colorspace", c, "-color_primaries", c, "-color_trc", trc, "-color_range", "tv",
            "-movflags", "+faststart", "-f", "mp4", "-y", str(out)]
    _run(cmd, duration, out, progress, cancelled)


def make_frame(src: Path, info: MediaInfo, start: float, duration: float, look: ClipLook, out: Path, work: Path,
               progress: Callable[[float], None], cancelled: Callable[[], bool]) -> None:
    """Step 1: the moment, cut and reframed, no captions."""
    aspect = effective_aspect(info, look.aspect)
    if aspect == "original":
        cut(src, info, start, duration, out, look.quality, progress, cancelled)
    elif look.layout == "smart":
        an = analyze(src, info, start, duration, work / "thumbs", _phase(progress, 0.0, 0.5), cancelled)
        p = plan(an, Options(aspect=aspect))
        render_smart_multi(src, info, an, [(p, out)], start, look.quality, Look(), _phase(progress, 0.5, 1.0), cancelled)
    else:
        render_static(src, info, look.layout if look.layout in ("blur", "fit") else "blur", aspect, look.quality,
                      Look(background="blur" if look.layout == "blur" else "color"), out, start, duration, 0.5, 1.0,
                      progress, cancelled)


def clip_transcript(full: Transcript, start: float, end: float) -> Transcript:
    """The words spoken inside [start, end], with times relative to the clip start."""
    lines: list[Line] = []
    for ln in full.lines:
        if ln.end <= start or ln.start >= end:
            continue
        words = [Word(w.text, w.start - start, w.end - start, w.keyword, w.emoji) for w in ln.words
                 if w.end > start + 0.05 and w.start < end - 0.05]
        if words:
            lines.append(Line(words=words, translation=None))
    t = Transcript(language=full.language, lines=lines, source="reused", rev=1)
    return normalize(t, end - start)


def default_style(aspect: str) -> Style:
    from ..captions.styles import preset_style
    st = preset_style("bold-pop")
    if aspect in ("1:1", "original"):
        st = st.model_copy(update={"y": 0.80})
    return st


def burn(base: Path, t: Transcript, look: ClipLook, hook: str | None, out: Path, watermark_text: str | None,
         progress: Callable[[float], None], cancelled: Callable[[], bool]) -> float:
    """Step 2: captions + hook on the framed clip. Returns the final duration."""
    info = probe(base)
    style = look.style or default_style(look.aspect)
    shown = t.copy()
    if look.captions and (style.keywords or style.emoji) and not any(w.keyword or w.emoji for w in shown.words()):
        enhance.auto_highlight(shown, keywords=style.keywords, emojis=style.emoji)
    if not look.captions:
        shown = Transcript(language=t.language, lines=[], source=t.source)
    keep = None
    duration = info.duration
    if look.remove_fillers or look.remove_silences:
        keep = cutmod.plan(t, info.duration, info.fps, fillers=look.remove_fillers, silences=look.remove_silences)
        shown = cutmod.remap(shown, keep, drop_fillers=look.remove_fillers) if shown.lines else shown
        duration = cutmod.kept_duration(keep)
    hook_text = (hook or "").strip() if look.hook else ""
    extras = assmod.Extras(hook=hook_text or None, hook_seconds=look.hook_seconds,
                           hook_y=0.13 if look.aspect != "original" else 0.08,
                           progress_bar="bottom" if look.progress_bar else "none",
                           watermark=watermark_text if look.watermark else None)
    W, H = crender.output_size(info, look.quality)
    ass_text = assmod.build_ass(shown, style, W, H, duration, extras)
    crender.render(base, info, ass_text, out, look.quality, keep, None, progress, cancelled)
    return duration


def needs_burn(look: ClipLook, hook: str | None, has_words: bool) -> bool:
    return (look.captions and has_words) or bool(look.hook and (hook or "").strip()) or look.progress_bar \
        or look.watermark or look.remove_fillers or look.remove_silences


def thumbnail(video: Path, out: Path, at: float) -> Path | None:
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-ss", f"{max(0.0, at):.2f}",
           "-i", str(video), "-frames:v", "1", "-vf", "scale=360:-2", "-q:v", "4", str(out)]
    try:
        subprocess.run(cmd, capture_output=True, timeout=60, check=False)
    except subprocess.TimeoutExpired:
        return None
    return out if out.exists() and out.stat().st_size > 500 else None


__all__ = ["ASPECT_CHOICES", "LAYOUTS", "ClipLook", "RenderError", "burn", "clip_transcript", "cut", "make_frame",
           "needs_burn", "thumbnail", "effective_aspect", "even"]
