"""Convert-then-download for options that need ffmpeg (Facebook H.264, MP3, fallback merges).

Streaming ffmpeg's output straight to the browser works, but the size is unknown until the end:
no Content-Length (the browser shows "unknown size", no progress bar), no resume, no IDM
multi-connection. Instead the page asks the server to prepare the file (POST /api/prepare/...),
shows the conversion progress, and then downloads the finished file with its exact size.
"""

from __future__ import annotations

import logging
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

log = logging.getLogger("uvicorn.error")
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
    threading.Thread(target=_run, args=(r, opt, job, cmd, tmp, slots), daemon=True).start()
    return job


ATTEMPTS = 2   # platforms (YouTube on data-centre IPs) refuse requests in short bursts: retry once


def _run(r: Resolved, opt: Option, job: Job, cmd: list[str], tmp: Path, slots) -> None:
    try:
        for attempt in range(ATTEMPTS):
            for fid in opt.formats:
                r.relay_errors.pop(fid, None)
            job.progress = 0.0 if job.duration else None
            detail = _convert(job, cmd, tmp)
            if detail is None:
                return
            relay = next((r.relay_errors[f] for f in opt.formats if f in r.relay_errors), None)
            log.warning("prepare %s/%s attempt %d failed: %s | relay: %s", r.platform.id, opt.id, attempt + 1, detail, relay)
            if attempt + 1 < ATTEMPTS:
                time.sleep(3)
                continue
            # The relay's reason ("platform refused...") is clearer than ffmpeg's "Input/output error".
            job.error = relay or ("Couldn't prepare this file." + (f" ({detail[:160]})" if detail else ""))
            job.state = "error"
    finally:
        r.active -= 1
        slots.give()
        job.proc = None


def _convert(job: Job, cmd: list[str], tmp: Path) -> str | None:
    """Run ffmpeg once. None on success (job is done), else the last line ffmpeg printed."""
    try:
        proc = job.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL)
    except Exception as e:  # noqa: BLE001
        return f"couldn't start ffmpeg: {e}"
    err: list[bytes] = []

    def drain() -> None:
        for line in iter(proc.stderr.readline, b""):
            err.append(line)
            del err[:-20]

    drainer = threading.Thread(target=drain, daemon=True)
    drainer.start()
    out_sec = 0.0
    for line in iter(proc.stdout.readline, b""):
        m = _OUT_TIME.match(line)
        if m:
            out_sec = max(out_sec, int(m.group(1)) / 1e6)
            if job.duration:
                job.progress = min(0.99, out_sec / job.duration)
    code = proc.wait()
    drainer.join(timeout=2)
    # If the platform keeps refusing, ffmpeg gives up reconnecting and ends the file early
    # *successfully*: never hand out a cut-off video.
    if code == 0 and job.duration and out_sec < job.duration * 0.97 - 1:
        tmp.unlink(missing_ok=True)
        return f"file ended early ({out_sec:.0f}s of {job.duration:.0f}s)"
    if code == 0 and tmp.exists() and tmp.stat().st_size > 0:
        tmp.replace(job.path)
        job.size = job.path.stat().st_size
        job.state = "done"
        return None
    tmp.unlink(missing_ok=True)
    lines = b"".join(err).decode(errors="replace").strip().splitlines()
    return lines[-1] if lines else f"ffmpeg exited with code {code}"


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
