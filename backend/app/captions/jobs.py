"""Caption jobs: one per video. Tasks (transcribe, translate, romanise, highlights, render) run one at a
time per job on a small worker pool; the transcript stays editable between tasks."""

from __future__ import annotations

import logging
import queue
import re
import secrets
import shutil
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..config import DATA_DIR, get_settings
from ..reframe import jobs as rjobs
from ..reframe import uploads
from ..reframe.analyze import Cancelled as ReframeCancelled
from ..reframe.media import MediaError, MediaInfo, probe
from . import ass as assmod
from . import cuts as cutmod
from . import enhance, languages, llm, render, stt, translit
from .styles import Style
from .transcript import (Line, Transcript, Word, build_lines, from_dict, normalize, parse_subtitles, retime, split_text,
                         to_srt, to_txt, to_vtt)

log = logging.getLogger("uvicorn.error")
JOBS_DIR = DATA_DIR / "captions"
_ID = re.compile(r"^[A-Za-z0-9_-]{12,40}$")
ACTIVE = ("queued", "importing", "transcribing", "processing", "rendering")


class JobError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class RenderSpec:
    style: Style
    extras: assmod.Extras
    quality: str = "1080p"
    remove_fillers: bool = False
    remove_silences: bool = False
    logo: render.Logo | None = None


@dataclass
class Output:
    path: Path
    size: int
    name: str
    duration: float


@dataclass
class Job:
    id: str
    ip: str
    dir: Path
    title: str
    source: dict[str, Any]
    language: str                       # what the visitor chose: "auto", "ur", "ur-Latn", ...
    prompt: str | None = None           # names / words to help speech recognition
    created: float = field(default_factory=time.time)
    src_path: Path | None = None
    info: MediaInfo | None = None
    audio: Path | None = None
    transcript: Transcript | None = None
    hooks: list[str] = field(default_factory=list)
    state: str = "queued"
    task: str | None = "transcribe"
    stage: str = "Waiting in line"
    progress: float = 0.0
    error: str | None = None
    started: float | None = None
    finished: float | None = None
    output: Output | None = None
    render_version: int = 0
    provider: str | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    upload_ref: str | None = None
    pending: dict[str, Any] = field(default_factory=dict)     # parameters of the queued task
    logo: Path | None = None

    def eta(self) -> float | None:
        if self.state not in ACTIVE or self.state == "queued" or not self.started or self.progress < 0.05:
            return None
        spent = time.time() - self.started
        return max(1.0, spent / self.progress * (1 - self.progress))

    def public(self, position: int | None = None, since_rev: int | None = None) -> dict[str, Any]:
        base = f"/api/captions/jobs/{self.id}"
        t = self.transcript
        lang = languages.info(t.language if t else (self.language if self.language != "auto" else None))
        d: dict[str, Any] = {
            "id": self.id, "state": self.state, "task": self.task, "stage": self.stage,
            "progress": round(self.progress, 4), "eta": round(e) if (e := self.eta()) else None,
            "queue_position": position, "error": self.error, "title": self.title,
            "language": self.language, "detected_language": t.language if t else None,
            "rtl": lang.rtl and not (t and t.language.endswith("-Latn")),
            "source": {"type": self.source.get("type"), "url": f"{base}/source"},
            "info": self.info.public() if self.info else None,
            "provider": self.provider, "hooks": self.hooks,
            "transcript_rev": t.rev if t else None,
            "has_logo": self.logo is not None and self.logo.exists(),
            "output": ({"url": f"{base}/file/video?v={self.render_version}", "size": self.output.size,
                        "name": self.output.name, "duration": round(self.output.duration, 2),
                        "version": self.render_version} if self.output and self.output.path.exists() else None),
            "files": {k: f"{base}/file/{k}" for k in ("srt", "vtt", "txt")} if t else None,
            "created": self.created,
        }
        if t is not None and (since_rev is None or since_rev != t.rev):
            d["transcript"] = t.to_dict()
        return d


_jobs: dict[str, Job] = {}
_queue: queue.Queue[Job] = queue.Queue()
_waiting: list[str] = []
_lock = threading.Lock()
_workers: list[threading.Thread] = []


def get(jid: str) -> Job:
    job = _jobs.get(jid) if _ID.match(jid or "") else None
    if job is None:
        raise JobError("This caption project has expired. Please start again.", 404)
    return job


def position(job: Job) -> int | None:
    with _lock:
        return _waiting.index(job.id) + 1 if job.id in _waiting else None


def new_job(**kw: Any) -> Job:
    jid = secrets.token_urlsafe(12)
    d = JOBS_DIR / jid
    d.mkdir(parents=True, exist_ok=True)
    return Job(id=jid, dir=d, **kw)


def register(job: Job) -> None:
    with _lock:
        _jobs[job.id] = job


def _ensure_workers() -> None:
    with _lock:
        alive = [w for w in _workers if w.is_alive()]
        _workers[:] = alive
        for _ in range(max(1, get_settings().captions_workers) - len(alive)):
            t = threading.Thread(target=_worker, daemon=True, name="captions-worker")
            t.start()
            _workers.append(t)


def submit(job: Job, task: str, params: dict[str, Any] | None = None, *, new: bool = False) -> None:
    s = get_settings()
    with _lock:
        if job.state in ACTIVE and not new:
            raise JobError("Please wait for the current step to finish.", 409)
        if len(_waiting) >= s.captions_queue_max:
            raise JobError("Lots of people are making captions right now. Please try again in a few minutes.", 503)
        if new:
            mine = [j for j in _jobs.values() if j.ip == job.ip and j.state in ACTIVE]
            if len(mine) >= 2:
                raise JobError("You already have 2 videos being processed. Please wait for one to finish.", 429)
        _jobs[job.id] = job
        _waiting.append(job.id)
        job.task, job.pending = task, dict(params or {})
        job.state, job.stage, job.progress, job.error = "queued", "Waiting in line", 0.0, None
        job.started = None
    job.cancel.clear()
    _queue.put(job)
    _ensure_workers()


def cancel(job: Job) -> None:
    job.cancel.set()
    with _lock:
        if job.id in _waiting:
            _waiting.remove(job.id)
            _settle(job, cancelled=True)


def delete(job: Job) -> None:
    cancel(job)
    with _lock:
        _jobs.pop(job.id, None)
    _release_upload(job)
    shutil.rmtree(job.dir, ignore_errors=True)


def _settle(job: Job, cancelled: bool = False) -> None:
    """After a task: back to an editable state (or error/cancelled when there's nothing to edit)."""
    job.task = None
    job.finished = time.time()
    if job.transcript is not None:
        job.state, job.stage = "ready", "Ready"
        if cancelled:
            job.error = None
    else:
        job.state, job.stage = ("cancelled", "Cancelled") if cancelled else ("error", "Failed")


def _release_upload(job: Job) -> None:
    if job.upload_ref:
        try:
            up = uploads.get(job.upload_ref)
            up.used_by = max(0, up.used_by - 1)
        except uploads.UploadError:
            pass
        job.upload_ref = None


# ---------------------------------------------------------------- worker


def _worker() -> None:
    while True:
        job = _queue.get()
        with _lock:
            if job.id in _waiting:
                _waiting.remove(job.id)
        if job.cancel.is_set() or job.id not in _jobs or job.state != "queued":
            continue
        job.started = time.time()
        task = job.task
        try:
            TASKS[task](job, **job.pending)
            _settle(job)
        except (Cancelled, stt.Cancelled, render.Cancelled, ReframeCancelled):
            _settle(job, cancelled=True)
        except (JobError, rjobs.JobError, stt.SttError, llm.LlmError, render.RenderError, MediaError) as e:
            job.error = str(getattr(e, "message", None) or e)
            if isinstance(e, render.RenderError):
                log.warning("captions %s render failed: %s", job.id, e)
                job.error = "The captions couldn't be added to this video. Please try again."
            _settle(job)
            log.info("captions %s %s failed: %s", job.id, task, job.error)
        except Exception as e:  # noqa: BLE001
            log.exception("captions %s %s crashed: %s", job.id, task, e)
            job.error = "Something went wrong. Please try again."
            _settle(job)


class Cancelled(Exception):
    pass


def _phase(job: Job, lo: float, hi: float) -> Callable[[float], None]:
    def report(p: float) -> None:
        job.progress = lo + (hi - lo) * max(0.0, min(1.0, p))
    return report


def _check(job: Job) -> None:
    if job.cancel.is_set():
        raise Cancelled()


# ---------------------------------------------------------------- tasks


def _prepare_source(job: Job) -> None:
    s = get_settings()
    if job.src_path is None:
        if job.source.get("type") != "link":
            raise JobError("The video file is missing. Please upload it again.")
        job.state, job.stage = "importing", "Fetching the video"
        path, title = rjobs.fetch_link(job.source["token"], int(job.source.get("index", 0)), job.dir, job.cancel,
                                       _phase(job, 0.0, 0.25))
        job.src_path = path
        job.title = title or job.title
    if job.info is None:
        job.info = probe(job.src_path)
    if job.info.duration > s.captions_max_duration_sec + 1:
        raise JobError(f"This video is longer than {s.captions_max_duration_sec // 60} minutes. "
                       f"Please cut out the part you need first.")


def _audio(job: Job) -> Path:
    if job.audio is None or not job.audio.exists():
        if job.info is not None and not job.info.has_audio:
            raise JobError("This video has no sound, so there's nothing to caption. You can still import "
                           "an SRT file.")
        job.audio = stt.extract_audio(job.src_path, job.dir / "audio.mp3")
    return job.audio


def task_transcribe(job: Job, subtitles: str | None = None, reuse: dict | None = None) -> None:
    _prepare_source(job)
    _check(job)
    if reuse is not None:                      # captions carried over (e.g. from before Make it vertical)
        t = from_dict(reuse)
        t.source = "reused"
        job.transcript = normalize(t, job.info.duration)
        job.transcript.rev += 1
        return
    if subtitles is not None:
        lang = job.language if job.language != "auto" else "en"
        lines = parse_subtitles(subtitles, lang)
        if not lines:
            raise JobError("We couldn't read that subtitle file. Please use an SRT or VTT file.")
        job.transcript = normalize(Transcript(language=lang, lines=lines, source="srt", rev=1), job.info.duration)
        return
    audio = _audio(job)
    job.state, job.stage = "transcribing", "AI is listening"
    lo = 0.25 if job.source.get("type") == "link" else 0.05
    choice = languages.get(job.language)
    roman = job.language in ("ur-Latn", "hi-Latn")
    # Roman Urdu / Hinglish: transcribe as Hindi (Devanagari writes every vowel), then romanise word by word.
    stt_lang = "hi" if roman else (choice.stt if choice else None)
    res = stt.transcribe(audio, stt_lang, job.prompt, job.cancel.is_set, _phase(job, lo, 0.95))
    job.provider = res.provider
    if not res.words:
        raise JobError("We couldn't hear any speech in this video. If it has speech, try choosing the language.")
    lang = job.language if (choice and job.language != "auto") else (res.language or "en")
    lines = build_lines(res.words, lang)
    t = Transcript(language=lang, lines=lines, source="ai", rev=1)
    if roman:
        _romanize_words(t, "urdu" if job.language == "ur-Latn" else "hindi", allow_ai=True)
        t.language = job.language
    job.transcript = normalize(t, job.info.duration)
    job.progress = 1.0


def _romanize_words(t: Transcript, style: str, allow_ai: bool) -> None:
    """Word-for-word romanisation, keeping timings. AI first (better spelling), offline as the fallback."""
    done: dict[str, list[str]] = {}
    if allow_ai and llm.available():
        try:
            done = llm.romanize([(ln.id, [w.text for w in ln.words]) for ln in t.lines], style)
        except llm.LlmError as e:
            log.info("AI romanisation failed, using offline: %s", e)
    for ln in t.lines:
        new = done.get(ln.id)
        if new and len(new) == len(ln.words):
            for w, x in zip(ln.words, new):
                w.text = x
        else:
            for w in ln.words:
                w.text = translit.to_roman(w.text, style)


def task_romanize(job: Job) -> None:
    t = job.transcript
    if t is None:
        raise JobError("There are no captions yet.")
    base = t.language.split("-")[0]
    style = "hindi" if base == "hi" else "urdu"
    target = "hi-Latn" if base == "hi" else "ur-Latn"
    job.state, job.stage = "processing", "Converting to Roman letters"
    if base == "ur" and not llm.available() and job.transcript.source == "ai":
        # Urdu script hides short vowels; without AI, listen again as Hindi and romanise that instead.
        old_lang, job.language, job.transcript = job.language, target, None
        try:
            task_transcribe(job)
        except BaseException:
            job.transcript, job.language = t, old_lang
            raise
        job.transcript.rev = t.rev + 1
        return
    new = t.copy()
    _romanize_words(new, style, allow_ai=True)
    new.language = target
    new.rev = t.rev + 1
    job.transcript = new
    job.language = target


def align_segments(lines: list[Line], segments: list[tuple[float, float, str]]) -> dict[str, str]:
    """Spread translated segments (with their own times) over our caption lines by time."""
    out: dict[str, list[str]] = {ln.id: [] for ln in lines}
    if not lines:
        return {}
    for s, e, text in segments:
        words = text.split()
        if not words:
            continue
        dur = max(0.01, e - s)
        for i, w in enumerate(words):
            t = s + dur * (i + 0.5) / len(words)
            best = min(lines, key=lambda ln: 0 if ln.start <= t <= ln.end else min(abs(t - ln.start), abs(t - ln.end)))
            out[best.id].append(w)
    return {k: " ".join(v) for k, v in out.items() if v}


def task_translate(job: Job, target: str) -> None:
    t = job.transcript
    if t is None:
        raise JobError("There are no captions yet.")
    job.state, job.stage = "processing", f"Translating to {languages.info(target).name}"
    if llm.available():
        res = llm.translate([(ln.id, ln.text(t.language)) for ln in t.lines], languages.info(t.language).name,
                            languages.info(target).name)
    elif target == "en":
        segs = stt.translate_to_english(_audio(job), job.prompt, job.cancel.is_set)
        res = align_segments(t.lines, segs)
    else:
        raise JobError("Only English translation is available right now.")
    _check(job)
    new = t.copy()
    for ln in new.lines:
        ln.translation = res.get(ln.id) or None
    new.translation_lang = target
    new.rev = t.rev + 1
    job.transcript = new


def task_enhance(job: Job, keywords: bool = True, emojis: bool = True, hooks: bool = True, ai: bool = True) -> None:
    t = job.transcript
    if t is None:
        raise JobError("There are no captions yet.")
    job.state, job.stage = "processing", "AI is picking highlights"
    new = t.copy()
    hook_list: list[str] = []
    used_ai = False
    if ai and llm.available():
        try:
            picks, hook_list = llm.enhance([(ln.id, [w.text for w in ln.words]) for ln in new.lines],
                                           languages.info(new.language).name)
            for ln in new.lines:
                k, e = picks.get(ln.id, (-1, ""))
                for i, w in enumerate(ln.words):
                    if keywords:
                        w.keyword = i == k
                    if emojis:
                        w.emoji = None
                if emojis and e and ln.words:
                    idx = k if 0 <= k < len(ln.words) else len(ln.words) - 1
                    ln.words[idx].emoji = e
            used_ai = True
        except llm.LlmError as e:
            log.info("AI highlights failed, using heuristics: %s", e)
    if not used_ai:
        enhance.auto_highlight(new, keywords=keywords, emojis=emojis)
        hook_list = enhance.suggest_hooks(new)
    if hooks:
        job.hooks = hook_list
    new.rev = t.rev + 1
    job.transcript = new


def display_transcript(t: Transcript, mode: str) -> Transcript:
    """mode translation: captions show the translated text, spread over each line's time."""
    if mode != "translation" or not t.translation_lang:
        return t
    out = t.copy()
    for ln in out.lines:
        if ln.translation:
            ln.words = retime(ln.words, split_text(ln.translation, t.translation_lang), ln.start, ln.end)
        ln.translation = None
    out.language = t.translation_lang
    return out


def task_render(job: Job, spec: RenderSpec) -> None:
    t = job.transcript
    if t is None:
        raise JobError("There are no captions yet.")
    if job.src_path is None or not job.src_path.exists():
        raise JobError("The original video has expired. Please start again.", 410)
    job.state, job.stage = "rendering", "Adding captions to the video"
    info = job.info or probe(job.src_path)
    shown = display_transcript(t, spec.extras.mode)
    keep = None
    duration = info.duration
    if spec.remove_fillers or spec.remove_silences:
        keep = cutmod.plan(shown, info.duration, info.fps, fillers=spec.remove_fillers, silences=spec.remove_silences)
        shown = cutmod.remap(shown, keep, drop_fillers=spec.remove_fillers)
        duration = cutmod.kept_duration(keep)
    W, H = render.output_size(info, spec.quality)
    ass_text = assmod.build_ass(shown, spec.style, W, H, duration, spec.extras)
    job.render_version += 1
    stem = rjobs._safe_stem(job.title)
    out = job.dir / f"{stem}-captions-v{job.render_version}.mp4"
    old = job.output
    render.render(job.src_path, info, ass_text, out, spec.quality, keep, spec.logo, _phase(job, 0.0, 1.0),
                  job.cancel.is_set)
    job.output = Output(path=out, size=out.stat().st_size, name=f"{stem}-klyprima-captions.mp4", duration=duration)
    if old and old.path != out:
        old.path.unlink(missing_ok=True)


TASKS: dict[str, Callable[..., None]] = {
    "transcribe": task_transcribe, "romanize": task_romanize, "translate": task_translate,
    "enhance": task_enhance, "render": task_render,
}


# ---------------------------------------------------------------- edits


def apply_edit(job: Job, data: dict[str, Any], base_rev: int | None) -> Transcript:
    """Replace the transcript with the editor's version (word timings checked and cleaned)."""
    if job.state in ACTIVE:
        raise JobError("Please wait for the current step to finish.", 409)
    cur = job.transcript
    if cur is None:
        raise JobError("There are no captions yet.", 409)
    if base_rev is not None and base_rev != cur.rev:
        raise JobError("These captions changed in another tab. Please reload.", 409)
    new = from_dict({**data, "rev": cur.rev + 1, "source": cur.source,
                     "language": data.get("language") or cur.language,
                     "translation_lang": data.get("translation_lang", cur.translation_lang)})
    if sum(len(ln.words) for ln in new.lines) > 40000:
        raise JobError("These captions are too long.", 413)
    job.transcript = normalize(new, job.info.duration if job.info else None)
    return job.transcript


def export(job: Job, kind: str, mode: str = "original") -> tuple[str, str]:
    t = job.transcript
    if t is None:
        raise JobError("There are no captions yet.", 404)
    text = {"srt": to_srt, "vtt": to_vtt, "txt": to_txt}[kind](t, mode)
    return text, f"{rjobs._safe_stem(job.title)}-captions.{kind}"


# ---------------------------------------------------------------- cleanup


def prune(max_age: float) -> None:
    now = time.time()
    with _lock:
        stale = [j for j in _jobs.values() if now - j.created > max_age and j.state not in ACTIVE]
        for j in stale:
            _jobs.pop(j.id, None)
        known = set(_jobs)
    for j in stale:
        _release_upload(j)
        shutil.rmtree(j.dir, ignore_errors=True)
    if JOBS_DIR.exists():
        for d in JOBS_DIR.iterdir():
            if d.name not in known and now - d.stat().st_mtime > max_age:
                shutil.rmtree(d, ignore_errors=True)


__all__ = ["Job", "JobError", "RenderSpec", "Word"]
