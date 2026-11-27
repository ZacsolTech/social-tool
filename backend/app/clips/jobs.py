"""AI Clips jobs: one per long video.

Pipeline (one task on a small worker pool): get the video -> speech to text (word timings) -> find the best
moments -> render each clip (best first, each downloadable as soon as it's ready). Afterwards every clip can
be edited (trim, hook, style, layout) and re-rendered on its own, or the whole video searched again with
other settings without listening to it again.
"""

from __future__ import annotations

import logging
import queue
import re
import secrets
import shutil
import threading
import time
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..captions import jobs as cjobs
from ..captions import languages, stt, verify
from ..captions.styles import Style
from ..captions.transcript import Transcript, build_lines, normalize, to_srt
from ..config import DATA_DIR, get_settings
from ..reframe import jobs as rjobs
from ..reframe import uploads
from ..reframe.analyze import Cancelled as ReframeCancelled
from ..reframe.media import MediaError, MediaInfo, probe
from ..reframe.render import RenderError
from . import finder
from ..captions import render as caprender
from . import render as crender

log = logging.getLogger("uvicorn.error")
JOBS_DIR = DATA_DIR / "clips"
_ID = re.compile(r"^[A-Za-z0-9_-]{12,40}$")
ACTIVE = ("queued", "importing", "transcribing", "finding", "rendering")
MIN_CLIP, MAX_CLIP = 3.0, 300.0


class JobError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.message = message
        self.status = status


class Cancelled(Exception):
    pass


@dataclass
class Clip:
    id: str
    start: float
    end: float
    title: str
    hook: str
    description: str
    hashtags: list[str]
    scores: dict[str, int]
    reason: str
    method: str
    look: crender.ClipLook
    status: str = "queued"            # queued | rendering | done | error | pending (not made yet)
    progress: float = 0.0
    error: str | None = None
    version: int = 0
    output: Path | None = None
    size: int = 0
    duration: float = 0.0
    base: Path | None = None          # framed clip without captions (reused when only the words/style change)
    base_key: tuple | None = None
    thumb: Path | None = None

    @property
    def score(self) -> int:
        return finder.total_score(self.scores)

    def public(self, base: str, rank: int, t: Transcript | None) -> dict[str, Any]:
        url = f"{base}/clips/{self.id}"
        ready = self.status == "done" and self.output is not None and self.output.exists()
        text = ""
        if t is not None:
            lang = t.language
            text = " ".join(ln.text(lang) for ln in t.lines if ln.end > self.start + 0.05 and ln.start < self.end - 0.05)
        return {
            "id": self.id, "rank": rank, "start": round(self.start, 3), "end": round(self.end, 3),
            "duration": round(self.duration if ready else self.end - self.start, 2),
            "title": self.title, "hook": self.hook, "description": self.description, "hashtags": self.hashtags,
            "score": self.score, "scores": self.scores, "reason": self.reason, "method": self.method,
            "status": self.status, "progress": round(self.progress, 3), "error": self.error, "version": self.version,
            "look": look_public(self.look),
            "text": text[:3000],
            "video": f"{url}/file?v={self.version}" if ready else None,
            "thumb": f"{url}/thumb?v={self.version}" if ready and self.thumb and self.thumb.exists() else None,
            "srt": f"{url}/srt" if t is not None else None,
            "size": self.size if ready else None,
        }


def look_public(lk: crender.ClipLook) -> dict[str, Any]:
    return {"aspect": lk.aspect, "layout": lk.layout, "captions": lk.captions,
            "style": (lk.style or crender.default_style(lk.aspect)).model_dump(), "hook": lk.hook,
            "remove_fillers": lk.remove_fillers, "remove_silences": lk.remove_silences,
            "progress_bar": lk.progress_bar, "watermark": lk.watermark, "quality": lk.quality}


@dataclass
class Settings:
    language: str = "auto"
    topic: str | None = None
    length: str = "auto"
    count: int | None = None           # None = decide from the video's length
    range_start: float = 0.0
    range_end: float | None = None
    look: crender.ClipLook = field(default_factory=crender.ClipLook)

    def public(self) -> dict[str, Any]:
        return {"language": self.language, "topic": self.topic, "length": self.length, "count": self.count,
                "range": [self.range_start, self.range_end], "look": look_public(self.look)}


@dataclass
class Job:
    id: str
    ip: str
    dir: Path
    title: str
    source: dict[str, Any]
    settings: Settings
    created: float = field(default_factory=time.time)
    src_path: Path | None = None
    info: MediaInfo | None = None
    audio: Path | None = None
    transcript: Transcript | None = None
    provider: str | None = None
    method: str | None = None          # ai | auto: how the clips were found
    clips: list[Clip] = field(default_factory=list)
    state: str = "queued"
    task: str | None = "process"
    stage: str = "Waiting in line"
    progress: float = 0.0
    error: str | None = None
    started: float | None = None
    finished: float | None = None
    cancel: threading.Event = field(default_factory=threading.Event)
    lock: threading.RLock = field(default_factory=threading.RLock)
    upload_ref: str | None = None
    pending: dict[str, Any] = field(default_factory=dict)
    zip_key: tuple | None = None
    heard: Any = None                  # the speech-to-text result (for the second listen of the accuracy check)
    checked: set[str] = field(default_factory=set)   # transcript lines the accuracy check already looked at

    @property
    def end(self) -> float:
        d = self.info.duration if self.info else 0.0
        return min(self.settings.range_end or d, d) if d else (self.settings.range_end or 0.0)

    def eta(self) -> float | None:
        if self.state not in ACTIVE or self.state == "queued" or not self.started or self.progress < 0.04:
            return None
        spent = time.time() - self.started
        return max(1.0, spent / self.progress * (1 - self.progress))

    def ranked(self) -> list[Clip]:
        return sorted(self.clips, key=lambda c: (-c.score, c.start))

    def public(self, position: int | None = None) -> dict[str, Any]:
        base = f"/api/clips/jobs/{self.id}"
        t = self.transcript
        with self.lock:
            clips = [c.public(base, i + 1, t) for i, c in enumerate(self.ranked())]
        done = sum(1 for c in clips if c["video"])
        return {
            "id": self.id, "state": self.state, "task": self.task, "stage": self.stage,
            "progress": round(1.0 if self.state == "ready" else self.progress, 4),
            "eta": round(e) if (e := self.eta()) else None, "queue_position": position, "error": self.error,
            "title": self.title, "source": {"type": self.source.get("type"), "url": f"{base}/source"},
            "info": self.info.public() if self.info else None, "settings": self.settings.public(),
            "detected_language": t.language if t else None, "provider": self.provider, "method": self.method,
            "clips": clips, "ready_count": done,
            "zip": f"{base}/zip" if done else None,
            "transcript": f"{base}/transcript" if t else None,
            "created": self.created,
        }


_jobs: dict[str, Job] = {}
_queue: queue.Queue[Job] = queue.Queue()
_waiting: list[str] = []
_lock = threading.Lock()
_workers: list[threading.Thread] = []


def get(jid: str) -> Job:
    job = _jobs.get(jid) if _ID.match(jid or "") else None
    if job is None:
        raise JobError("This clips project has expired. Please start again.", 404)
    return job


def clip(job: Job, cid: str) -> Clip:
    c = next((c for c in job.clips if c.id == cid), None)
    if c is None:
        raise JobError("That clip doesn't exist any more.", 404)
    return c


def position(job: Job) -> int | None:
    with _lock:
        return _waiting.index(job.id) + 1 if job.id in _waiting else None


def new_job(**kw: Any) -> Job:
    jid = secrets.token_urlsafe(12)
    d = JOBS_DIR / jid
    d.mkdir(parents=True, exist_ok=True)
    return Job(id=jid, dir=d, **kw)


def _ensure_workers() -> None:
    with _lock:
        alive = [w for w in _workers if w.is_alive()]
        _workers[:] = alive
        for _ in range(max(1, get_settings().clips_workers) - len(alive)):
            t = threading.Thread(target=_worker, daemon=True, name="clips-worker")
            t.start()
            _workers.append(t)


def submit(job: Job, task: str, params: dict[str, Any] | None = None, *, new: bool = False) -> None:
    s = get_settings()
    with _lock:
        if job.state in ACTIVE and not new:
            raise JobError("Please wait for the current step to finish.", 409)
        if len(_waiting) >= s.clips_queue_max:
            raise JobError("Lots of people are making clips right now. Please try again in a few minutes.", 503)
        if new:
            mine = [j for j in _jobs.values() if j.ip == job.ip and j.state in ACTIVE]
            if len(mine) >= s.clips_active_per_ip:
                raise JobError("You already have a video being clipped. Please wait for it to finish.", 429)
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


def _settle(job: Job, cancelled: bool = False, ok: bool = False) -> None:
    """After a task. ok: it finished normally (a clip queued by an edit at that moment stays queued)."""
    job.task = None
    job.finished = time.time()
    with job.lock:
        for c in job.clips:
            made = c.output is not None and c.output.exists()
            if c.status == "rendering":
                c.status = "done" if made else "error"
                if c.status == "error":
                    c.error = c.error or "This clip wasn't made. Press Render to try again."
            elif c.status == "queued" and not ok:
                c.status = "done" if made else "pending"
            c.progress = 0.0 if c.status != "done" else 1.0
    if job.transcript is not None and job.clips:
        job.state, job.stage = "ready", "Ready"
        if cancelled:
            job.error = None
    elif job.transcript is not None and not cancelled:
        job.state, job.stage = "error", "Failed"
        job.error = job.error or "We couldn't find a clip in this video."
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
            _settle(job, ok=True)
            if any(c.status == "queued" for c in job.clips):
                try:
                    submit(job, "render")      # an edit arrived just as this task ended
                except JobError:
                    _settle(job)
            continue
        except (Cancelled, stt.Cancelled, ReframeCancelled, cjobs.Cancelled):
            _settle(job, cancelled=True)
        except (JobError, rjobs.JobError, stt.SttError, MediaError, cjobs.JobError) as e:
            job.error = str(getattr(e, "message", None) or e)
            log.info("clips %s %s failed: %s", job.id, task, job.error)
            _settle(job)
        except Exception as e:  # noqa: BLE001
            log.exception("clips %s %s crashed: %s", job.id, task, e)
            job.error = "Something went wrong. Please try again."
            _settle(job)


def _phase(job: Job, lo: float, hi: float) -> Callable[[float], None]:
    def report(p: float) -> None:
        job.progress = lo + (hi - lo) * max(0.0, min(1.0, p))
    return report


def _check(job: Job) -> None:
    if job.cancel.is_set():
        raise Cancelled()


# ---------------------------------------------------------------- stages


def _prepare_source(job: Job) -> None:
    s = get_settings()
    if job.src_path is None:
        if job.source.get("type") != "link":
            raise JobError("The video file is missing. Please upload it again.")
        job.state, job.stage = "importing", "Fetching the video"
        path, title = rjobs.fetch_link(job.source["token"], int(job.source.get("index", 0)), job.dir, job.cancel,
                                       _phase(job, 0.0, 0.08))
        job.src_path = path
        job.title = title or job.title
    if job.info is None:
        job.info = probe(job.src_path)
    if not job.info.has_audio:
        raise JobError("This video has no sound. AI Clips finds the best moments from what is said.")
    st = job.settings
    if st.range_start >= job.info.duration - 1:
        raise JobError("The start time is after the end of the video.")
    if job.end - st.range_start > s.clips_max_duration_sec + 1:
        raise JobError(f"Please choose up to {s.clips_max_duration_sec // 60} minutes of the video.")


def _transcribe(job: Job) -> None:
    st = job.settings
    if job.audio is None or not job.audio.exists():
        job.state, job.stage = "transcribing", "Getting the sound"
        length = job.end - st.range_start
        job.audio = stt.extract_audio(job.src_path, job.dir / "audio.mp3", st.range_start,
                                      length if job.end < job.info.duration - 0.05 or st.range_start > 0 else None)
    _check(job)
    job.state, job.stage = "transcribing", "AI is listening"
    choice = languages.get(st.language)
    roman = st.language in ("ur-Latn", "hi-Latn")
    stt_lang = "hi" if roman else (choice.stt if choice else None)
    res = stt.transcribe(job.audio, stt_lang, None, job.cancel.is_set, _phase(job, 0.1, 0.5),
                         stage=lambda x: setattr(job, "stage", x))
    job.provider = res.provider
    if not res.words:
        raise JobError("We couldn't hear any speech in this video. If it has speech, try choosing the language.")
    job.heard = stt.SttResult(res.language, [], res.provider, [], res.model)
    job.checked = set()
    off = st.range_start
    if off:
        for w in res.words:
            w.start += off
            w.end += off
    lang = st.language if (choice and st.language != "auto") else (res.language or "en")
    lines = build_lines(res.words, lang, breaks=[s + off for s, _, _ in res.segments])
    t = Transcript(language=lang, lines=lines, source="ai", rev=1)
    if roman:
        cjobs._romanize_words(t, "urdu" if st.language == "ur-Latn" else "hindi", allow_ai=True)
        t.language = st.language
    job.transcript = normalize(t, job.info.duration)


def _proofread_clips(job: Job) -> None:
    """Accuracy check (captions/verify.py) on the chosen clips only: their stretches of audio are heard a
    second time by another model and an AI judge settles the differences. Cheap: minutes, not the hour."""
    t = job.transcript
    if not (t and job.clips) or t.language.endswith("-Latn"):
        return
    lines = [ln for ln in t.lines if ln.id not in job.checked
             and any(ln.end > c.start and ln.start < c.end for c in job.clips)]
    if not lines:
        return
    spans = verify.merge_ranges([(c.start, c.end) for c in job.clips])
    try:
        verify.run(t, job.audio, job.heard, stt_lang=job.heard.language if job.heard else None,
                   hints=job.settings.topic, title=job.title, only=lines, ranges=spans,
                   audio_offset=job.settings.range_start, cancelled=job.cancel.is_set,
                   stage=lambda x: setattr(job, "stage", x))
    except stt.Cancelled:
        raise Cancelled() from None
    except Exception as e:  # noqa: BLE001
        log.warning("clips caption check failed for %s: %s", job.id, e)
        return
    job.checked.update(ln.id for ln in t.lines if any(ln.end > c.start and ln.start < c.end for c in job.clips))
    job.transcript = normalize(t, job.info.duration if job.info else None)
    t.rev += 1


def _find(job: Job) -> None:
    st = job.settings
    job.state, job.stage = "finding", "AI is picking the best moments"
    _check(job)
    cands, method = finder.find(job.transcript, job.info.duration, st.length, st.count, st.topic, job.title,
                                cancelled=job.cancel.is_set, progress=_phase(job, 0.5, 0.58))
    _check(job)
    if not cands:
        raise JobError("We couldn't find a clip in this video. Try a longer part, or another clip length.")
    old = job.clips
    with job.lock:
        job.clips = [Clip(id=secrets.token_hex(4), start=c.start, end=c.end, title=c.title or "Clip",
                          hook=c.hook or c.title, description=c.description, hashtags=c.hashtags, scores=c.scores,
                          reason=c.reason, method=c.source, look=_copy_look(st.look)) for c in cands]
        job.method = method
        job.zip_key = None
    for c in old:
        shutil.rmtree(job.dir / f"clip-{c.id}", ignore_errors=True)
    _proofread_clips(job)


def _copy_look(lk: crender.ClipLook) -> crender.ClipLook:
    return crender.ClipLook(**{**lk.__dict__, "style": lk.style.model_copy() if lk.style else None})


def _render_queued(job: Job, lo: float) -> None:
    """Render every queued clip, best first. Clips queued meanwhile (edits) are picked up too."""
    done_ids: set[str] = set()
    while True:
        _check(job)
        with job.lock:
            todo = [c for c in job.ranked() if c.status == "queued"]
            total = len(done_ids) + len(todo)
        if not todo:
            break
        c = todo[0]
        job.state = "rendering"
        n = len(done_ids) + 1
        job.stage = f"Making clip {n} of {total}" if total > 1 else "Making your clip"

        def prog(p: float, c: Clip = c, k: int = len(done_ids), total: int = total) -> None:
            c.progress = p
            job.progress = lo + (1 - lo) * min(1.0, (k + p) / max(1, total))
        render_clip(job, c, prog)
        done_ids.add(c.id)
    job.progress = 1.0


def render_clip(job: Job, c: Clip, progress: Callable[[float], None]) -> None:
    s = get_settings()
    with job.lock:
        c.status, c.error, c.progress = "rendering", None, 0.0
        start, end, look = c.start, c.end, _copy_look(c.look)
    d = job.dir / f"clip-{c.id}"
    d.mkdir(parents=True, exist_ok=True)
    try:
        key = look.frame_key(start, end)
        t = crender.clip_transcript(job.transcript, start, end)
        burn = crender.needs_burn(look, c.hook, bool(t.lines))
        split = 0.7 if burn else 1.0
        if c.base is None or c.base_key != key or not c.base.exists():
            base = d / f"frame-{secrets.token_hex(3)}.mp4"
            crender.make_frame(job.src_path, job.info, start, end - start, look, base, d,
                               lambda p: progress(p * split), job.cancel.is_set)
            if c.base is not None and c.base != base:
                c.base.unlink(missing_ok=True)
            c.base, c.base_key = base, key
        version = c.version + 1
        stem = rjobs._safe_stem(c.title or job.title)
        out = d / f"{stem}-v{version}.mp4"
        if burn:
            crender.burn(c.base, t, look, c.hook, out, s.captions_watermark,
                         lambda p: progress(split + (1 - split) * p), job.cancel.is_set)
        else:
            rjobs.link_or_copy(c.base, out)
        info = probe(out)
        thumb = crender.thumbnail(out, d / f"thumb-v{version}.jpg", min(1.2, info.duration / 3))
        with job.lock:
            old_out, old_thumb = c.output, c.thumb
            c.output, c.size, c.duration, c.thumb = out, out.stat().st_size, info.duration, thumb
            c.version = version
            # A newer edit may have queued this clip again while it rendered: keep it queued.
            c.status = "queued" if c.status == "queued" else "done"
            c.progress = 1.0
            job.zip_key = None
        for p in (old_out, old_thumb):
            if p is not None and p not in (out, thumb):
                p.unlink(missing_ok=True)
    except (ReframeCancelled, Cancelled, cjobs.Cancelled):
        with job.lock:
            c.status = "done" if c.output is not None and c.output.exists() else "queued"
        raise
    except (RenderError, MediaError, caprender.RenderError, caprender.Cancelled) as e:
        if isinstance(e, caprender.Cancelled):
            with job.lock:
                c.status = "done" if c.output is not None and c.output.exists() else "queued"
            raise Cancelled() from e
        log.warning("clips %s clip %s failed: %s", job.id, c.id, e)
        with job.lock:
            c.status, c.error = "error", "This clip couldn't be made. Press Render to try again."


def task_process(job: Job) -> None:
    _prepare_source(job)
    _check(job)
    if job.transcript is None:
        _transcribe(job)
    _check(job)
    _find(job)
    _render_queued(job, 0.6)


def task_find(job: Job, settings: Settings) -> None:
    if job.transcript is None:
        raise JobError("There's no transcript yet.", 409)
    job.settings = settings
    _find(job)
    _render_queued(job, 0.1)


def task_render(job: Job) -> None:
    if job.src_path is None or not Path(job.src_path).exists():
        raise JobError("The original video has expired. Please start again.", 410)
    _render_queued(job, 0.0)


TASKS: dict[str, Callable[..., None]] = {"process": task_process, "find": task_find, "render": task_render}


# ---------------------------------------------------------------- edits


def snap(t: Transcript | None, start: float, end: float, duration: float) -> tuple[float, float]:
    """Never cut a word in half: move each edge just outside the word it falls in."""
    start = max(0.0, min(start, duration))
    end = max(0.0, min(end, duration))
    if t is not None:
        words = t.words()
        for i, w in enumerate(words):
            if w.start < start < w.end:
                prev = words[i - 1].end if i else 0.0
                start = max(prev, w.start - 0.15)
                break
        for i, w in enumerate(words):
            if w.start < end < w.end:
                nxt = words[i + 1].start if i + 1 < len(words) else duration
                end = min(nxt, w.end + 0.25, duration)
                break
    return round(start, 3), round(end, 3)


def edit_clip(job: Job, c: Clip, patch: dict[str, Any]) -> bool:
    """Apply editor changes. Returns True when the clip has to be rendered again."""
    if job.info is None:
        raise JobError("This video isn't ready yet.", 409)
    rerender = False
    with job.lock:
        for k in ("title", "description"):
            if patch.get(k) is not None:
                setattr(c, k, str(patch[k]).strip()[:400])
        if patch.get("hashtags") is not None:
            c.hashtags = finder._tags(patch["hashtags"])
        if patch.get("hook") is not None and patch["hook"].strip() != c.hook:
            c.hook = patch["hook"].strip()[:140]
            rerender = rerender or c.look.hook
        if patch.get("start") is not None or patch.get("end") is not None:
            s0 = float(patch["start"]) if patch.get("start") is not None else c.start
            e0 = float(patch["end"]) if patch.get("end") is not None else c.end
            s0, e0 = snap(job.transcript, s0, e0, job.info.duration)
            if e0 - s0 < MIN_CLIP:
                raise JobError(f"A clip needs to be at least {MIN_CLIP:.0f} seconds long.")
            if e0 - s0 > MAX_CLIP:
                raise JobError(f"A clip can be up to {MAX_CLIP / 60:.0f} minutes long.")
            if (s0, e0) != (c.start, c.end):
                c.start, c.end = s0, e0
                rerender = True
        look = patch.get("look") or {}
        if look:
            new = _copy_look(c.look)
            for k, v in look.items():
                if v is None or not hasattr(new, k):
                    continue
                if k == "style":
                    v = v if isinstance(v, Style) else Style.model_validate(v)
                setattr(new, k, v)
            if new.__dict__ != c.look.__dict__:
                c.look = new
                rerender = True
        if patch.get("render"):
            rerender = True
        if rerender:
            c.status, c.error, c.progress = "queued", None, 0.0
            job.zip_key = None
    return rerender


# ---------------------------------------------------------------- exports


def clip_srt(job: Job, c: Clip) -> tuple[str, str]:
    if job.transcript is None:
        raise JobError("There's no transcript yet.", 404)
    t = crender.clip_transcript(job.transcript, c.start, c.end)
    return to_srt(t), f"{rjobs._safe_stem(c.title or job.title)}.srt"


def post_text(c: Clip) -> str:
    return "\n".join(x for x in (c.title, "", c.description, "", " ".join(c.hashtags)) if x is not None).strip() + "\n"


def build_zip(job: Job) -> Path:
    """Every finished clip (MP4 + SRT) and a text file with titles, descriptions and hashtags."""
    with job.lock:
        ready = [(i + 1, c) for i, c in enumerate(job.ranked()) if c.status == "done" and c.output and c.output.exists()]
        key = tuple((c.id, c.version) for _, c in ready)
    if not ready:
        raise JobError("No clip is ready yet.", 404)
    path = job.dir / "clips.zip"
    if job.zip_key == key and path.exists():
        return path
    tmp = path.with_suffix(".part")
    notes = []
    with zipfile.ZipFile(tmp, "w", compression=zipfile.ZIP_STORED) as z:
        for rank, c in ready:
            stem = f"{rank:02d}-{rjobs._safe_stem(c.title or job.title)}"
            z.write(c.output, f"{stem}.mp4")
            if job.transcript is not None:
                z.writestr(f"{stem}.srt", "﻿" + clip_srt(job, c)[0])
            notes.append(f"#{rank}  score {c.score}/100  ({_clock(c.start)}-{_clock(c.end)})\n{post_text(c)}")
        z.writestr("clips.txt", ("\n" + "-" * 40 + "\n").join(notes))
    tmp.replace(path)
    job.zip_key = key
    return path


def _clock(t: float) -> str:
    t = int(max(0, t))
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def for_captions(job: Job, c: Clip) -> tuple[Path, str, dict]:
    """The framed clip (no burned captions) and its words, for the full caption editor."""
    if c.base is None or not c.base.exists() or job.transcript is None:
        raise JobError("That clip isn't ready yet.", 409)
    t = crender.clip_transcript(job.transcript, c.start, c.end)
    return c.base, c.title or job.title, t.to_dict()


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
