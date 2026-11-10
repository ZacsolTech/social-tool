"""Convert-then-download for options that need ffmpeg (Facebook H.264, MP3, fallback merges).

Streaming ffmpeg's output straight to the browser works, but the size is unknown until the end:
no Content-Length (the browser shows "unknown size", no progress bar), no resume, no IDM
multi-connection. Instead the page asks the server to prepare the file (POST /api/prepare/...),
shows the conversion progress, and then downloads the finished file with its exact size.
"""

from __future__ import annotations

import re
import secrets
import subprocess
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

from .config import DATA_DIR, Settings
from .extractor import Item, Option, Resolved
from .stream import _ffmpeg_cmd, ffmpeg_slots

JOBS_DIR = DATA_DIR / "jobs"
_OUT_TIME = re.compile(rb"^out_time_us=(\d+)")


@dataclass
class Job:
    path: Path
    duration: float | None
    created: float = field(default_factory=time.time)
    state: str = "running"          # running | done | error
    progress: float | None = None   # 0..1, None if the duration is unknown
    size: int | None = None
    error: str | None = None
    serving: int = 0                # downloads reading the file right now (don't delete it)
    proc: subprocess.Popen | None = None

    def public(self) -> dict:
        return {"state": self.state, "progress": 1.0 if self.state == "done" else self.progress,
                "size": self.size, "error": self.error}


_jobs: dict[tuple[str, int, str], Job] = {}
_lock = threading.Lock()


def get(r: Resolved, item: Item, opt: Option) -> Job | None:
    job = _jobs.get((r.token, item.index, opt.id))
    if job and job.state == "done" and not job.path.exists():   # deleted underneath us: start over
        _jobs.pop((r.token, item.index, opt.id), None)
        return None
    return job


def start(r: Resolved, item: Item, opt: Option, settings: Settings) -> Job:
    """Start (or return the running / finished) conversion of this option. Idempotent."""
    key = (r.token, item.index, opt.id)
    with _lock:
        job = get(r, item, opt)
        if job and job.state != "error":
            return job
        JOBS_DIR.mkdir(parents=True, exist_ok=True)
        path = JOBS_DIR / f"{secrets.token_hex(8)}.{opt.ext}"
        job = Job(path=path, duration=item.duration)
        slots = ffmpeg_slots(settings)
        if not slots.take():
            job.state, job.error = "error", "The server is busy right now. Please try again in a minute."
            return job   # not stored: the next click retries
        _jobs[key] = job
    tmp = path.with_suffix(path.suffix + ".part")
    cmd = _ffmpeg_cmd(r, item, opt, settings, dest=str(tmp), extra=["-progress", "pipe:1", "-nostats"])
    r.active += 1   # keep the link's session (cookies, relay) alive while ffmpeg reads from it
    try:
        job.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
    except Exception:  # noqa: BLE001
        r.active -= 1
        slots.give()
        job.state, job.error = "error", "Couldn't start the converter. Please try again."
        return job
    threading.Thread(target=_run, args=(r, job, tmp, slots), daemon=True).start()
    return job


def _run(r: Resolved, job: Job, tmp: Path, slots) -> None:
    proc = job.proc
    assert proc is not None
    err: list[bytes] = []

    def drain() -> None:
        for line in iter(proc.stderr.readline, b""):
            err.append(line)
            del err[:-20]

    threading.Thread(target=drain, daemon=True).start()
    try:
        for line in iter(proc.stdout.readline, b""):
            m = _OUT_TIME.match(line)
            if m and job.duration:
                job.progress = min(0.99, int(m.group(1)) / 1e6 / job.duration)
        code = proc.wait()
        if code == 0 and tmp.exists() and tmp.stat().st_size > 0:
            tmp.replace(job.path)
            job.size = job.path.stat().st_size
            job.state = "done"
        else:
            detail = b"".join(err).decode(errors="replace").strip().splitlines()
            job.error = "Couldn't prepare this file." + (f" ({detail[-1][:160]})" if detail else "")
            job.state = "error"
            tmp.unlink(missing_ok=True)
    finally:
        r.active -= 1
        slots.give()
        job.proc = None


def prune(max_age: float) -> None:
    """Delete finished files nobody is downloading, and stop conversions nobody came back for."""
    now = time.time()
    with _lock:
        for key, job in list(_jobs.items()):
            if now - job.created < max_age or job.serving:
                continue
            if job.proc is not None and job.proc.poll() is None:
                job.proc.kill()
            job.path.unlink(missing_ok=True)
            _jobs.pop(key, None)
    # Leftovers from a previous run of the server.
    if JOBS_DIR.exists():
        known = {j.path.name for j in _jobs.values()}
        for p in JOBS_DIR.iterdir():
            if p.name.split(".part")[0] not in known and now - p.stat().st_mtime > max_age:
                p.unlink(missing_ok=True)
