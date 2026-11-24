"""Speech to text with word timings.

1. Groq's hosted Whisper (large-v3-turbo) when CF_GROQ_API_KEY is set: seconds per video, best accuracy.
2. faster-whisper on our own CPU otherwise, or when Groq fails: free, slower, smaller model.
"""

from __future__ import annotations

import logging
import subprocess
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from ..config import get_settings
from ..reframe.media import ffmpeg_bin, read_audio
from . import languages
from .transcript import Word

log = logging.getLogger("uvicorn.error")
GROQ_URL = "https://api.groq.com/openai/v1/audio"
GROQ_MAX_BYTES = 24 * 1024 * 1024


class SttError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.message = message
        self.status = status


class Cancelled(Exception):
    pass


@dataclass
class SttResult:
    language: str | None
    words: list[Word]
    provider: str
    segments: list[tuple[float, float, str]] = field(default_factory=list)


# ---------------------------------------------------------------- audio


def extract_audio(src: Path, dest: Path, start: float = 0.0, duration: float | None = None) -> Path:
    """16 kHz mono MP3 at 32 kbps: ~14 MB per hour, the size speech-to-text services like."""
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]
    if duration:
        cmd += ["-t", f"{duration:.3f}"]
    cmd += ["-i", str(src), "-vn", "-sn", "-dn", "-map", "0:a:0", "-ac", "1", "-ar", "16000",
            "-c:a", "libmp3lame", "-b:a", "32k", str(dest)]
    res = subprocess.run(cmd, capture_output=True, timeout=900)
    if res.returncode != 0 or not dest.exists() or dest.stat().st_size < 200:
        raise SttError("We couldn't read the sound of this video.")
    return dest


def split_audio(audio: Path, seconds: int = 1200) -> list[tuple[Path, float]]:
    """Cut a long audio file into pieces (for API size limits). Returns (path, start offset)."""
    out_dir = audio.parent / "audio-parts"
    out_dir.mkdir(exist_ok=True)
    subprocess.run([ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-nostdin", "-y", "-i", str(audio),
                    "-f", "segment", "-segment_time", str(seconds), "-c", "copy", str(out_dir / "part%03d.mp3")],
                   capture_output=True, timeout=600, check=False)
    parts = sorted(out_dir.glob("part*.mp3"))
    return [(p, i * float(seconds)) for i, p in enumerate(parts)] or [(audio, 0.0)]


# ---------------------------------------------------------------- Groq


def _groq_key() -> str | None:
    import os
    k = (get_settings().groq_api_key or os.environ.get("GROQ_API_KEY") or "").strip().strip("\"'")
    return k or None


def _keep_segment(seg: dict) -> bool:
    """Whisper invents text over silence and music ("Thanks for watching"). Drop segments it's unsure are speech."""
    nsp = float(seg.get("no_speech_prob") or 0)
    lp = float(seg.get("avg_logprob") or 0)
    comp = float(seg.get("compression_ratio") or 1)
    return not ((nsp > 0.6 and lp < -0.8) or comp > 2.6)


def _groq_call(endpoint: str, audio: Path, data: dict, offset: float) -> tuple[str | None, list[Word], list[tuple[float, float, str]]]:
    key = _groq_key()
    files = {"file": (audio.name, audio.read_bytes(), "audio/mpeg")}
    try:
        r = httpx.post(f"{GROQ_URL}/{endpoint}", headers={"Authorization": f"Bearer {key}"}, data=data, files=files,
                       timeout=httpx.Timeout(300, connect=20))
    except httpx.HTTPError as e:
        raise SttError("The speech-to-text service didn't answer.", 502) from e
    if r.status_code == 429:
        raise SttError("The speech-to-text service is busy.", 503)
    if r.status_code >= 400:
        log.warning("groq %s %s: %s", endpoint, r.status_code, r.text[:300])
        raise SttError("The speech-to-text service had a problem.", 502)
    body = r.json()
    segs = [s for s in body.get("segments") or [] if _keep_segment(s)]
    spans = [(float(s["start"]), float(s["end"])) for s in segs]
    words: list[Word] = []
    for w in body.get("words") or []:
        s, e = float(w.get("start", 0)), float(w.get("end", 0))
        mid = (s + e) / 2
        if spans and not any(a - 0.3 <= mid <= b + 0.3 for a, b in spans):
            continue
        words.append(Word(text=str(w.get("word", "")).strip(), start=s + offset, end=max(e, s + 0.04) + offset))
    segments = [(float(s["start"]) + offset, float(s["end"]) + offset, str(s.get("text", "")).strip()) for s in segs]
    return body.get("language"), words, segments


def _groq_transcribe(audio: Path, language: str | None, prompt: str | None, cancelled: Callable[[], bool],
                     progress: Callable[[float], None]) -> SttResult:
    s = get_settings()
    parts = split_audio(audio) if audio.stat().st_size > GROQ_MAX_BYTES else [(audio, 0.0)]
    lang, words, segments = None, [], []
    for k, (path, offset) in enumerate(parts):
        if cancelled():
            raise Cancelled()
        data: dict = {"model": s.groq_model, "response_format": "verbose_json", "temperature": "0",
                      "timestamp_granularities[]": ["word", "segment"]}
        if language:
            data["language"] = language
        if prompt:
            data["prompt"] = prompt[:800]
        got_lang, w, seg = _groq_call("transcriptions", path, data, offset)
        lang = lang or got_lang
        words += w
        segments += seg
        progress((k + 1) / len(parts))
    return SttResult(languages.normalize(language or lang), words, "groq", segments)


def _groq_translate(audio: Path, prompt: str | None, cancelled: Callable[[], bool]) -> list[tuple[float, float, str]]:
    s = get_settings()
    parts = split_audio(audio) if audio.stat().st_size > GROQ_MAX_BYTES else [(audio, 0.0)]
    segments: list[tuple[float, float, str]] = []
    for path, offset in parts:
        if cancelled():
            raise Cancelled()
        data = {"model": s.groq_translate_model, "response_format": "verbose_json", "temperature": "0"}
        if prompt:
            data["prompt"] = prompt[:800]
        _, _, seg = _groq_call("translations", path, data, offset)
        segments += seg
    return segments


# ---------------------------------------------------------------- local (faster-whisper)

_model_lock = threading.Lock()
_models: dict[str, object] = {}


def local_model_dir() -> Path:
    return get_settings().whisper_dir


def _local_model():
    from faster_whisper import WhisperModel
    s = get_settings()
    name = s.local_whisper_model
    with _model_lock:
        if name not in _models:
            d = local_model_dir()
            d.mkdir(parents=True, exist_ok=True)
            _models[name] = WhisperModel(name, device="cpu", compute_type="int8", cpu_threads=max(1, s.captions_threads),
                                         download_root=str(d))
        return _models[name]


def _local_run(audio: Path, language: str | None, prompt: str | None, task: str, cancelled: Callable[[], bool],
               progress: Callable[[float], None]) -> tuple[str | None, list[Word], list[tuple[float, float, str]]]:
    try:
        model = _local_model()
    except Exception as e:  # noqa: BLE001
        log.exception("local whisper unavailable: %s", e)
        raise SttError("Speech-to-text isn't available right now. Please try again later.", 503) from e
    # Decode with FFmpeg ourselves (16 kHz mono float32): faster-whisper's PyAV decoder breaks on newer PyAV.
    samples = read_audio(audio, sr=16000)
    if samples.size < 1600:
        raise SttError("We couldn't hear any speech in this video.")
    segs_iter, info = model.transcribe(samples, language=language, task=task, word_timestamps=(task == "transcribe"),
                                       vad_filter=True, initial_prompt=prompt or None, beam_size=5,
                                       condition_on_previous_text=False)
    total = max(1.0, float(getattr(info, "duration", 0) or 1))
    words: list[Word] = []
    segments: list[tuple[float, float, str]] = []
    for seg in segs_iter:
        if cancelled():
            raise Cancelled()
        progress(min(0.99, seg.end / total))
        if seg.no_speech_prob > 0.6 and seg.avg_logprob < -0.8 or seg.compression_ratio > 2.6:
            continue
        segments.append((seg.start, seg.end, seg.text.strip()))
        for w in seg.words or []:
            words.append(Word(text=w.word.strip(), start=w.start, end=max(w.end, w.start + 0.04)))
    return getattr(info, "language", None), words, segments


# ---------------------------------------------------------------- public


def provider_name() -> str:
    return "groq" if _groq_key() else "local"


def transcribe(audio: Path, language: str | None, prompt: str | None = None,
               cancelled: Callable[[], bool] = lambda: False, progress: Callable[[float], None] = lambda p: None) -> SttResult:
    """language: a Whisper code ("ur", "hi", ...) or None to detect it."""
    if _groq_key():
        try:
            return _groq_transcribe(audio, language, prompt, cancelled, progress)
        except SttError as e:
            if not get_settings().local_whisper_fallback:
                raise
            log.warning("groq failed (%s); using local whisper", e.message)
    lang, words, segments = _local_run(audio, language, prompt, "transcribe", cancelled, progress)
    return SttResult(languages.normalize(language or lang), words, "local", segments)


def translate_to_english(audio: Path, prompt: str | None = None,
                         cancelled: Callable[[], bool] = lambda: False) -> list[tuple[float, float, str]]:
    """Whisper's own speech -> English translation (segments with times, no word timings)."""
    if _groq_key():
        try:
            return _groq_translate(audio, prompt, cancelled)
        except SttError as e:
            if not get_settings().local_whisper_fallback:
                raise
            log.warning("groq translate failed (%s); using local whisper", e.message)
    _, _, segments = _local_run(audio, None, prompt, "translate", cancelled, lambda p: None)
    return segments
