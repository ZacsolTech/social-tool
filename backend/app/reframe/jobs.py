"""Reframe jobs: a small queue with worker threads, progress/ETA, cancel, re-render and cleanup."""

from __future__ import annotations

import logging
import os
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

from .. import jobs as dl_jobs
from ..config import DATA_DIR, get_settings
from . import uploads
from .analyze import Analysis, Cancelled, analyze, focus_pass, track_point
from .director import Options, Override, describe, plan
from .media import MediaError, MediaInfo, probe
from .render import Look, RenderError, render_smart_multi, render_static

log = logging.getLogger("uvicorn.error")
JOBS_DIR = DATA_DIR / "reframe"
_ID = re.compile(r"^[A-Za-z0-9_-]{12,40}$")


class JobError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class Output:
    aspect: str
    path: Path
    size: int
    name: str


@dataclass
class Job:
    id: str
    ip: str
    mode: str                         # smart | blur | crop | fit
    aspects: list[str]
    quality: str
    smart: dict[str, Any]
    look: Look
    position: float
    trim_start: float
    trim_end: float | None
    source: dict[str, Any]            # {"type": "upload", "id"} | {"type": "link", "token", "index"}
    title: str
    dir: Path
    created: float = field(default_factory=time.time)
    src_path: Path | None = None
    info: MediaInfo | None = None
    state: str = "queued"             # queued | importing | analysing | rendering | done | error | cancelled
    stage: str = "Waiting in line"
    progress: float = 0.0
    started: float | None = None
    finished: float | None = None
    error: str | None = None
    outputs: dict[str, Output] = field(default_factory=dict)
    shots: dict[str, list[dict]] = field(default_factory=dict)
    overrides: dict[int, Override] = field(default_factory=dict)
    analysis: Analysis | None = None
    points: dict[tuple, list] = field(default_factory=dict)       # (shot, x, y) -> tracked boxes
    version: int = 0
    cancel: threading.Event = field(default_factory=threading.Event)
    upload_ref: str | None = None

    # ---- derived
    @property
    def start(self) -> float:
        return self.trim_start

    @property
    def duration(self) -> float:
        assert self.info is not None
        end = min(self.trim_end or self.info.duration, self.info.duration)
        return max(0.1, end - self.trim_start)

    def eta(self) -> float | None:
        if self.state not in ("analysing", "rendering", "importing") or not self.started or self.progress < 0.04:
            return None
        spent = time.time() - self.started
        return max(1.0, spent / self.progress * (1 - self.progress))

    def public(self, position: int | None = None) -> dict[str, Any]:
        base = f"/api/reframe/jobs/{self.id}"
        return {
            "id": self.id,
            "state": self.state,
            "stage": self.stage,
            "progress": round(1.0 if self.state == "done" else self.progress, 4),
            "eta": round(self.eta()) if self.eta() else None,
            "queue_position": position,
            "error": self.error,
            "mode": self.mode,
            "aspects": self.aspects,
            "quality": self.quality,
            "smart": self.smart,
            "look": self.look.__dict__,
            "position": self.position,
            "trim": [self.trim_start, self.trim_end],
            "title": self.title,
            "source": {"type": self.source.get("type"), "url": f"{base}/source",
                       **({"captions": self.source.get("id")} if self.source.get("type") == "captions" else {})},
            "info": self.info.public() if self.info else None,
            "version": self.version,
            "outputs": [
                {"aspect": o.aspect, "size": o.size, "name": o.name,
                 "url": f"{base}/file/{o.aspect.replace(':', 'x')}?v={self.version}"}
                for a in self.aspects if (o := self.outputs.get(a))
            ],
            "shots": {a: [{**s, "thumb": f"{base}/thumb/{s['index']}"} for s in v] for a, v in self.shots.items()},
            "overrides": {str(k): {kk: vv for kk, vv in v.__dict__.items() if vv is not None} for k, v in self.overrides.items()},
            "editable": self.mode == "smart" and self.analysis is not None and self.state in ("done", "error"),
            "created": self.created,
        }


_jobs: dict[str, Job] = {}
_queue: queue.Queue[Job] = queue.Queue()
_waiting: list[str] = []
_lock = threading.Lock()
_workers: list[threading.Thread] = []
link_lookup: Callable[[str], Any] | None = None   # set by main.py: token -> Resolved (the downloader's cache)


def get(jid: str) -> Job:
    job = _jobs.get(jid) if _ID.match(jid or "") else None
    if job is None:
        raise JobError("This job has expired. Please start again.", 404)
    return job


def position(job: Job) -> int | None:
    with _lock:
        return _waiting.index(job.id) + 1 if job.id in _waiting else None


def _ensure_workers() -> None:
    with _lock:
        alive = [w for w in _workers if w.is_alive()]
        _workers[:] = alive
        for _ in range(max(1, get_settings().reframe_workers) - len(alive)):
            t = threading.Thread(target=_worker, daemon=True, name="reframe-worker")
            t.start()
            _workers.append(t)


def submit(job: Job) -> None:
    s = get_settings()
    with _lock:
        if len(_waiting) >= s.reframe_queue_max:
            raise JobError("Lots of people are converting right now. Please try again in a few minutes.", 503)
        mine = [j for j in _jobs.values() if j.ip == job.ip and j.state in ("queued", "importing", "analysing", "rendering")]
        if len(mine) >= 2:
            raise JobError("You already have 2 videos converting. Please wait for one to finish.", 429)
        _jobs[job.id] = job
        _waiting.append(job.id)
    job.state, job.stage, job.progress, job.error = "queued", "Waiting in line", 0.0, None
    job.cancel.clear()
    _queue.put(job)
    _ensure_workers()


def requeue(job: Job) -> None:
    with _lock:
        if job.id in _waiting or job.state in ("queued", "importing", "analysing", "rendering"):
            raise JobError("This video is still being processed.", 409)
        _waiting.append(job.id)
    job.state, job.stage, job.progress, job.error = "queued", "Waiting in line", 0.0, None
    job.cancel.clear()
    job.version += 1
    _queue.put(job)
    _ensure_workers()


def cancel(job: Job) -> None:
    job.cancel.set()
    with _lock:
        if job.id in _waiting:
            _waiting.remove(job.id)
            job.state, job.stage = "cancelled", "Cancelled"


def delete(job: Job) -> None:
    cancel(job)
    with _lock:
        _jobs.pop(job.id, None)
    _release_upload(job)
    shutil.rmtree(job.dir, ignore_errors=True)


def new_job(**kw: Any) -> Job:
    jid = secrets.token_urlsafe(12)
    d = JOBS_DIR / jid
    d.mkdir(parents=True, exist_ok=True)
    return Job(id=jid, dir=d, **kw)


# ---------------------------------------------------------------- worker


def _worker() -> None:
    while True:
        job = _queue.get()
        with _lock:
            if job.id in _waiting:
                _waiting.remove(job.id)
        if job.cancel.is_set() or job.id not in _jobs:
            continue
        job.started = time.time()
        try:
            _run(job)
            job.state, job.stage, job.progress = "done", "Ready", 1.0
        except Cancelled:
            job.state, job.stage = "cancelled", "Cancelled"
        except (JobError, MediaError, RenderError) as e:
            job.state, job.stage, job.error = "error", "Failed", str(getattr(e, "message", None) or e)
            log.warning("reframe %s failed: %s", job.id, job.error)
        except Exception as e:  # noqa: BLE001
            job.state, job.stage = "error", "Failed"
            job.error = "Something went wrong while converting this video. Please try again."
            log.exception("reframe %s crashed: %s", job.id, e)
        finally:
            job.finished = time.time()


def _phase(job: Job, lo: float, hi: float) -> Callable[[float], None]:
    def report(p: float) -> None:
        job.progress = lo + (hi - lo) * max(0.0, min(1.0, p))
    return report


def fetch_link(token: str, index: int, dest_dir: Path, cancel: threading.Event,
               report: Callable[[float], None]) -> tuple[Path, str | None]:
    """Download a link pasted in the downloader (its cached token) into dest_dir. Shared with the caption tool.
    Returns (file, title)."""
    if link_lookup is None:
        raise JobError("Links can't be used right now. Please upload the file instead.")
    try:
        r = link_lookup(token)
        item = r.item(int(index))
    except Exception as e:  # noqa: BLE001
        raise JobError("This link has expired. Please paste it again.", 410) from e
    if item.error:
        raise JobError(item.error)
    opts = [o for o in item.options if o.kind == "video"]
    opt = next((o for o in opts if o.best), None) or next((o for o in opts if o.has_audio), None) or (opts[0] if opts else None)
    if opt is None:
        raise JobError("This post has no video we can use.")
    s = get_settings()
    dl = None
    for _ in range(30):
        dl = dl_jobs.start(r, item, opt, s)
        if dl.state != "error" or "busy" not in (dl.error or ""):
            break
        if cancel.wait(4):
            raise Cancelled()
    while dl is not None and dl.state == "running":
        if cancel.wait(0.5):
            raise Cancelled()
        report(dl.progress or 0.0)
    if dl is None or dl.state != "done":
        raise JobError((dl.error if dl else None) or "Couldn't fetch this video. Please try again.")
    dest = dest_dir / f"source.{opt.ext}"
    link_or_copy(Path(dl.path), dest)
    return dest, item.title or r.title


def link_or_copy(src: Path, dest: Path) -> None:
    """Hard link (instant, no extra disk) when possible, else copy."""
    dest.unlink(missing_ok=True)
    try:
        os.link(src, dest)
    except OSError:
        shutil.copyfile(src, dest)


def _import_link(job: Job) -> None:
    job.state, job.stage = "importing", "Fetching the video"
    path, title = fetch_link(job.source["token"], int(job.source.get("index", 0)), job.dir, job.cancel,
                             _phase(job, 0.0, 0.15))
    job.src_path = path
    job.title = title or job.title


def _release_upload(job: Job) -> None:
    if job.upload_ref:
        try:
            up = uploads.get(job.upload_ref)
            up.used_by = max(0, up.used_by - 1)
        except uploads.UploadError:
            pass
        job.upload_ref = None


def _safe_stem(title: str) -> str:
    base = re.sub(r"[^\w\s-]", "", Path(title).stem, flags=re.UNICODE).strip()
    return re.sub(r"[\s_-]+", "-", base)[:50].strip("-") or "video"


def _run(job: Job) -> None:
    s = get_settings()
    cancelled = job.cancel.is_set
    if job.src_path is None:
        if job.source.get("type") == "link":
            _import_link(job)
        else:
            raise JobError("The uploaded file is missing. Please upload it again.")
    if job.info is None:
        job.info = probe(job.src_path)
    info = job.info
    if job.trim_start >= info.duration - 0.2:
        raise JobError("The start time is after the end of the video.")
    if job.duration > s.reframe_max_duration_sec + 1:
        raise JobError(f"Please choose up to {s.reframe_max_duration_sec // 60} minutes of the video (use Trim).")

    begin = 0.15 if job.source.get("type") == "link" and job.version == 0 else 0.0
    stem = _safe_stem(job.title)
    old = dict(job.outputs)
    job.outputs = {}

    if job.mode == "smart":
        render_lo = begin
        if job.analysis is None:
            job.state, job.stage = "analysing", "AI is watching the video"
            render_lo = begin + (1 - begin) * 0.45
            job.analysis = analyze(job.src_path, info, job.start, job.duration, job.dir / "thumbs",
                                   _phase(job, begin, render_lo), cancelled)
        an = job.analysis
        opts_kw = dict(job.smart)
        follow = opts_kw.pop("follow_cls", None)
        opts_kw.pop("follow", None)
        focus = None
        if follow is not None:
            job.state, job.stage = "analysing", "Finding what to follow"
            focus = focus_pass(job.src_path, info, an, job.start, int(follow), cancelled,
                               _phase(job, render_lo, render_lo + 0.1))
            render_lo += 0.1
        points: dict[int, list] = {}
        for idx, ov in job.overrides.items():
            if ov.point is not None and 0 <= idx < len(an.shots):
                key = (idx, round(ov.point[0], 3), round(ov.point[1], 3))
                if key not in job.points:
                    job.stage = "Tracking what you clicked"
                    job.points[key] = track_point(job.src_path, info, an, job.start, an.shots[idx], ov.point[0], ov.point[1], cancelled)
                points[idx] = job.points[key]
        targets = []
        job.shots = {}
        for aspect in job.aspects:
            p = plan(an, Options(aspect=aspect, focus_cls=follow, **opts_kw), job.overrides, points, focus)
            job.shots[aspect] = describe(an, p)
            targets.append((p, job.dir / f"{stem}-{aspect.replace(':', 'x')}-v{job.version}.mp4"))
        job.state, job.stage = "rendering", "Rendering " + " + ".join(job.aspects)
        # One decode of the source feeds every format.
        render_smart_multi(job.src_path, info, an, targets, job.start, job.quality, job.look,
                           _phase(job, render_lo, 1.0), cancelled)
        for (p, out), aspect in zip(targets, job.aspects):
            job.outputs[aspect] = Output(aspect, out, out.stat().st_size, f"{stem}-klyprima-{aspect.replace(':', 'x')}.mp4")
    else:
        share = (1 - begin) / len(job.aspects)
        for k, aspect in enumerate(job.aspects):
            job.state, job.stage = "rendering", f"Converting to {aspect}" + (f" ({k + 1} of {len(job.aspects)})" if len(job.aspects) > 1 else "")
            out = job.dir / f"{stem}-{aspect.replace(':', 'x')}-v{job.version}.mp4"
            lo = begin + k * share
            render_static(job.src_path, info, job.mode, aspect, job.quality, job.look, out, job.start, job.duration,
                          job.position, float(job.smart.get("framing", 1.0)), _phase(job, lo, lo + share), cancelled)
            job.outputs[aspect] = Output(aspect, out, out.stat().st_size, f"{stem}-klyprima-{aspect.replace(':', 'x')}.mp4")

    for o in old.values():
        if all(o.path != n.path for n in job.outputs.values()):
            o.path.unlink(missing_ok=True)


# ---------------------------------------------------------------- cleanup


EDIT_WINDOW_SEC = 3 * 3600   # the shot editor works this long after a job; then its analysis is freed


def prune(max_age: float) -> None:
    now = time.time()
    for j in list(_jobs.values()):
        if j.analysis is not None and j.finished and j.state in ("done", "error", "cancelled")                 and now - j.finished > EDIT_WINDOW_SEC:
            j.analysis = None      # results stay downloadable; only re-editing needs a new conversion
            j.points.clear()
    with _lock:
        stale = [j for j in _jobs.values()
                 if now - j.created > max_age and j.state not in ("queued", "importing", "analysing", "rendering")]
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
