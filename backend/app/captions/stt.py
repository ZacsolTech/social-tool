"""Speech to text with word timings.

Providers are tried in order; when one fails or its free quota is used up, the next takes over and the
first is retried later:
1. Groq: Whisper large-v3-turbo in the cloud (CF_GROQ_API_KEY). Free tier: about 8 hours of audio a day.
2. Cloudflare Workers AI: the same model (CF_CLOUDFLARE_ACCOUNT_ID + CF_CLOUDFLARE_API_TOKEN). Free tier:
   about 3.5 hours of audio a day.
3. faster-whisper on our own CPU: always available, slower and less accurate (smaller model).
"""

from __future__ import annotations

import base64
import logging
import os
import subprocess
import threading
import time
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


class QuotaError(SttError):
    """The provider's (free) limit is used up for now: try the next one, come back after retry_after."""
    def __init__(self, message: str, retry_after: float = 600):
        super().__init__(message, 503)
        self.retry_after = retry_after


class Cancelled(Exception):
    pass


# Short phrases in each language, written the way captions should look. Whisper continues the style of
# its prompt: right script (Urdu stays in Urdu letters, not Hindi), punctuation and casing.
STYLE_PROMPTS = {
    "en": "Hello everyone, welcome back. Today, we're going to talk about it.",
    "ur": "السلام علیکم دوستو، آج ہم اس بارے میں بات کریں گے۔",
    "hi": "नमस्ते दोस्तों, आज हम इसके बारे में बात करेंगे।",
    "ar": "مرحباً بكم، اليوم سنتحدث عن هذا الموضوع.",
    "bn": "সবাইকে স্বাগতম, আজ আমরা এই বিষয়ে কথা বলব।",
    "pa": "ਸਤ ਸ੍ਰੀ ਅਕਾਲ ਦੋਸਤੋ, ਅੱਜ ਅਸੀਂ ਇਸ ਬਾਰੇ ਗੱਲ ਕਰਾਂਗੇ।",
    "fa": "سلام دوستان، امروز درباره این موضوع صحبت می‌کنیم.",
    "es": "Hola a todos, bienvenidos. Hoy vamos a hablar de esto.",
    "pt": "Olá a todos, bem-vindos. Hoje vamos falar sobre isso.",
    "fr": "Bonjour à tous, bienvenue. Aujourd'hui, nous allons en parler.",
    "id": "Halo semuanya, selamat datang. Hari ini kita akan membahasnya.",
    "tr": "Herkese merhaba, hoş geldiniz. Bugün bunu konuşacağız.",
}


def build_prompt(language: str | None, user: str | None) -> str | None:
    """Style phrase for the language (only when it's known: it would bias auto-detection) + the visitor's
    names and special words."""
    parts = []
    if language and language in STYLE_PROMPTS:
        parts.append(STYLE_PROMPTS[language])
    if user and user.strip():
        parts.append(user.strip())
    return " ".join(parts)[:800] or None


def _filter(segs: list[dict], words: list[dict], offset: float) -> tuple[list[Word], list[tuple[float, float, str]]]:
    """Keep the words inside segments Whisper is confident are speech; shift by the piece's offset."""
    kept = [s for s in segs if _keep_segment(s)]
    spans = [(float(s["start"]), float(s["end"])) for s in kept]
    out: list[Word] = []
    for w in words:
        s, e = float(w.get("start", 0)), float(w.get("end", 0))
        mid = (s + e) / 2
        if spans and not any(a - 0.3 <= mid <= b + 0.3 for a, b in spans):
            continue
        text = str(w.get("word", "")).strip()
        if text:
            out.append(Word(text=text, start=s + offset, end=max(e, s + 0.04) + offset))
    segments = [(float(s["start"]) + offset, float(s["end"]) + offset, str(s.get("text", "")).strip()) for s in kept]
    return out, segments


def _retry_after(r: httpx.Response, default: float) -> float:
    try:
        return max(5.0, float(r.headers.get("retry-after", default)))
    except ValueError:
        return default


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
        raise QuotaError("Groq's limit is reached for now.", _retry_after(r, 600))
    if r.status_code >= 400:
        log.warning("groq %s %s: %s", endpoint, r.status_code, r.text[:300])
        raise SttError("The speech-to-text service had a problem.", 502)
    body = r.json()
    words, segments = _filter(body.get("segments") or [], body.get("words") or [], offset)
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


# ---------------------------------------------------------------- Cloudflare Workers AI

CF_PART_SEC = 600      # 10-minute pieces keep each request small (audio is sent base64 in JSON)


def _cf_creds() -> tuple[str, str] | None:
    s = get_settings()
    acct = (s.cloudflare_account_id or "").strip().strip("\"'")
    tok = (s.cloudflare_api_token or "").strip().strip("\"'")
    return (acct, tok) if acct and tok else None


def _seconds_to_utc_midnight() -> float:
    now = time.time()
    return 86400 - now % 86400 + 60


def _cf_call(audio: Path, language: str | None, prompt: str | None, task: str, offset: float):
    acct, tok = _cf_creds()  # type: ignore[misc]
    s = get_settings()
    body: dict = {"audio": base64.b64encode(audio.read_bytes()).decode(), "task": task, "vad_filter": True,
                  "beam_size": 5, "condition_on_previous_text": False}
    if task == "transcribe":
        body["hallucination_silence_threshold"] = 2
    if language:
        body["language"] = language
    if prompt:
        body["initial_prompt"] = prompt
    url = f"https://api.cloudflare.com/client/v4/accounts/{acct}/ai/run/{s.cloudflare_whisper_model}"
    try:
        r = httpx.post(url, headers={"Authorization": f"Bearer {tok}"}, json=body, timeout=httpx.Timeout(300, connect=20))
    except httpx.HTTPError as e:
        raise SttError("The speech-to-text service didn't answer.", 502) from e
    text = r.text[:400]
    if r.status_code == 429 or (r.status_code >= 400 and any(k in text.lower() for k in ("neuron", "allocation", "quota", "limit"))):
        # The free allocation resets at 00:00 UTC.
        raise QuotaError("Cloudflare's daily limit is reached.", _seconds_to_utc_midnight() if r.status_code != 429 else _retry_after(r, 900))
    if r.status_code >= 400:
        log.warning("cloudflare %s: %s", r.status_code, text)
        raise SttError("The speech-to-text service had a problem.", 502)
    data = r.json()
    res = data.get("result", data) if isinstance(data, dict) else {}
    segs = res.get("segments") or []
    words = [w for seg in segs for w in (seg.get("words") or [])]
    info = res.get("transcription_info") or {}
    got_words, segments = _filter(segs, words, offset)
    return info.get("language"), got_words, segments


def _cf_parts(audio: Path) -> list[tuple[Path, float]]:
    return split_audio(audio, CF_PART_SEC) if audio.stat().st_size > CF_PART_SEC * 4000 else [(audio, 0.0)]


def _cf_transcribe(audio: Path, language: str | None, prompt: str | None, cancelled: Callable[[], bool],
                   progress: Callable[[float], None]) -> SttResult:
    parts = _cf_parts(audio)
    lang, words, segments = None, [], []
    for k, (path, offset) in enumerate(parts):
        if cancelled():
            raise Cancelled()
        got_lang, w, seg = _cf_call(path, language or lang, prompt, "transcribe", offset)
        lang = lang or got_lang
        words += w
        segments += seg
        progress((k + 1) / len(parts))
    return SttResult(languages.normalize(language or lang), words, "cloudflare", segments)


def _cf_translate(audio: Path, prompt: str | None, cancelled: Callable[[], bool]) -> list[tuple[float, float, str]]:
    segments: list[tuple[float, float, str]] = []
    for path, offset in _cf_parts(audio):
        if cancelled():
            raise Cancelled()
        _, _, seg = _cf_call(path, None, prompt, "translate", offset)
        segments += seg
    return segments


# ---------------------------------------------------------------- local (faster-whisper)

_model_lock = threading.Lock()
_models: dict[str, object] = {}
_download: threading.Thread | None = None
DOWNLOAD_WAIT_SEC = 15 * 60


def local_model_dir() -> Path:
    return get_settings().whisper_dir


def _hf_env() -> None:
    """Model downloads: plain HTTP with timeouts (the default "xet" transfer can stall forever) and every
    cache under the model folder (not the user's profile on C:). Read by huggingface_hub at import."""
    d = local_model_dir()
    os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
    os.environ.setdefault("HF_HOME", str(d / "hf-home"))
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "60")
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "20")
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")


_hf_env()


def _model_files(name: str) -> str | None:
    """Local folder of a downloaded model, None if it isn't fully downloaded yet."""
    from faster_whisper.utils import download_model
    try:
        return download_model(name, local_files_only=True, cache_dir=str(local_model_dir()))
    except Exception:  # noqa: BLE001
        return None


def _fetch(name: str) -> None:
    from faster_whisper.utils import download_model
    try:
        download_model(name, cache_dir=str(local_model_dir()))
        log.info("speech model %s downloaded", name)
    except Exception as e:  # noqa: BLE001
        log.warning("speech model %s download failed: %s", name, e)


def ensure_local_model(stage: Callable[[str], None] = lambda s: None, cancelled: Callable[[], bool] = lambda: False) -> str:
    """Make sure the local model is on disk (downloading it once, in the background) and return its folder."""
    global _download
    name = get_settings().local_whisper_model
    path = _model_files(name)
    if path:
        return path
    stage("Getting the speech model ready (first time only)")
    with _model_lock:
        if _download is None or not _download.is_alive():
            local_model_dir().mkdir(parents=True, exist_ok=True)
            _download = threading.Thread(target=_fetch, args=(name,), daemon=True, name="whisper-download")
            _download.start()
        t = _download
    waited = 0.0
    while t.is_alive() and waited < DOWNLOAD_WAIT_SEC:
        if cancelled():
            raise Cancelled()
        t.join(1.0)
        waited += 1.0
    path = _model_files(name)
    if not path:
        raise SttError("Speech-to-text is still starting up. Please try again in a few minutes.", 503)
    return path


def warm_local_model() -> None:
    """At start-up without a Groq key: download the local model now so the first visitor doesn't wait."""
    if _groq_key() or not get_settings().captions_warm_model:
        return
    try:
        ensure_local_model()
        _local_model()
    except Exception as e:  # noqa: BLE001
        log.warning("speech model warm-up failed: %s", e)


def _local_model(stage: Callable[[str], None] = lambda s: None, cancelled: Callable[[], bool] = lambda: False):
    from faster_whisper import WhisperModel
    s = get_settings()
    name = s.local_whisper_model
    if name in _models:
        return _models[name]
    path = ensure_local_model(stage, cancelled)
    with _model_lock:
        if name not in _models:
            _models[name] = WhisperModel(path, device="cpu", compute_type="int8", cpu_threads=max(1, s.captions_threads))
        return _models[name]


def _local_run(audio: Path, language: str | None, prompt: str | None, task: str, cancelled: Callable[[], bool],
               progress: Callable[[float], None], stage: Callable[[str], None] = lambda s: None,
               ) -> tuple[str | None, list[Word], list[tuple[float, float, str]]]:
    try:
        model = _local_model(stage, cancelled)
        stage("AI is listening")
    except (SttError, Cancelled):
        raise
    except Exception as e:  # noqa: BLE001
        log.exception("local whisper unavailable: %s", e)
        raise SttError("Speech-to-text isn't available right now. Please try again later.", 503) from e
    # Decode with FFmpeg ourselves (16 kHz mono float32): faster-whisper's PyAV decoder breaks on newer PyAV.
    samples = read_audio(audio, sr=16000)
    if samples.size < 1600:
        raise SttError("We couldn't hear any speech in this video.")
    words_on = task == "transcribe"
    segs_iter, info = model.transcribe(
        samples, language=language, task=task, word_timestamps=words_on, initial_prompt=prompt or None,
        beam_size=5, condition_on_previous_text=False,
        vad_filter=True, vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 300},
        hallucination_silence_threshold=2 if words_on else None,
        # Detect the language from several parts of the video, not only the first 30 s (intro music).
        language_detection_segments=4, language_detection_threshold=0.6)
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

_cooldown: dict[str, float] = {}     # provider -> time it may be used again


def providers() -> list[str]:
    s = get_settings()
    out = []
    if _groq_key():
        out.append("groq")
    if _cf_creds():
        out.append("cloudflare")
    if not out or s.local_whisper_fallback:
        out.append("local")
    return out


def provider_name() -> str:
    """The provider that would be used right now (for the config endpoint)."""
    now = time.time()
    return next((p for p in providers() if _cooldown.get(p, 0) <= now), providers()[-1])


def _chain(run: dict[str, Callable[[], object]]):
    """Try each provider in order; skip ones cooling down after a quota error."""
    last: SttError | None = None
    now = time.time()
    names = providers()
    usable = [p for p in names if _cooldown.get(p, 0) <= now] or names[-1:]
    for name in usable:
        try:
            return run[name]()
        except QuotaError as e:
            _cooldown[name] = time.time() + e.retry_after
            log.warning("%s quota reached; next provider for %.0f s", name, e.retry_after)
            last = e
        except SttError as e:
            if name != "local":
                _cooldown[name] = time.time() + 60      # brief pause after an outage
            log.warning("%s speech-to-text failed: %s", name, e.message)
            last = e
    raise last or SttError("Speech-to-text isn't available right now. Please try again later.", 503)


def transcribe(audio: Path, language: str | None, prompt: str | None = None,
               cancelled: Callable[[], bool] = lambda: False, progress: Callable[[float], None] = lambda p: None,
               stage: Callable[[str], None] = lambda s: None) -> SttResult:
    """language: a Whisper code ("ur", "hi", ...) or None to detect it. prompt: the visitor's special words."""
    p = build_prompt(language, prompt)

    def local() -> SttResult:
        lang, words, segments = _local_run(audio, language, p, "transcribe", cancelled, progress, stage)
        return SttResult(languages.normalize(language or lang), words, "local", segments)
    return _chain({  # type: ignore[return-value]
        "groq": lambda: _groq_transcribe(audio, language, p, cancelled, progress),
        "cloudflare": lambda: _cf_transcribe(audio, language, p, cancelled, progress),
        "local": local,
    })


def translate_to_english(audio: Path, prompt: str | None = None,
                         cancelled: Callable[[], bool] = lambda: False) -> list[tuple[float, float, str]]:
    """Whisper's own speech -> English translation (segments with times, no word timings)."""
    return _chain({  # type: ignore[return-value]
        "groq": lambda: _groq_translate(audio, prompt, cancelled),
        "cloudflare": lambda: _cf_translate(audio, prompt, cancelled),
        "local": lambda: _local_run(audio, None, prompt, "translate", cancelled, lambda p: None)[2],
    })
