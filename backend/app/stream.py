"""Instant downloads: one plain media file relayed byte-for-byte to the browser / IDM.

Range requests are passed through, so download managers can resume and use several
connections. The link's yt-dlp session supplies cookies and impersonation, and YouTube's
adaptive files are fetched in chunks (one big request gets throttled).
Video+audio merges are built virtually by vmux.py (exact size, resumable); MP3 and the few non-MP4
inputs use the ffmpeg streaming fallback at the bottom of this file.
"""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from yt_dlp.networking import Request
from yt_dlp.networking.exceptions import HTTPError, TransportError

from .extractor import Item, Resolved, refresh_item

CHUNK = 256 * 1024


class StreamError(Exception):
    def __init__(self, message: str, status: int = 502):
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class Upstream:
    status: int
    headers: dict[str, str]
    body: AsyncIterator[bytes]


# ---------------------------------------------------------------- relay


def _request_headers(resolved: Resolved, f: dict[str, Any]) -> dict[str, str]:
    return dict(f.get("http_headers") or resolved.http_headers or {})


def _extensions(resolved: Resolved, f: dict[str, Any]) -> dict[str, Any]:
    imp = f.get("impersonate")
    if not imp:
        return {}
    target, _ = resolved.ydl._parse_impersonate_targets(imp)
    return {"impersonate": target} if target else {}


def _wait_until_available(f: dict[str, Any]) -> None:
    """YouTube: media URLs only work after `available_at` (the length of the pre-roll ad slot).
    Requests before that get 403. yt-dlp's own downloader sleeps the same way."""
    wait = (f.get("available_at") or 0) - time.time()
    if wait > 0:
        time.sleep(min(wait, 60))


def _open(resolved: Resolved, f: dict[str, Any], rng: str | None):
    _wait_until_available(f)
    headers = _request_headers(resolved, f)
    if rng:
        headers["Range"] = rng
    req = Request(f["url"], headers=headers, extensions=_extensions(resolved, f))
    return resolved.ydl.urlopen(req)   # cookies come from the session's cookie jar


def _open_with_refresh(resolved: Resolved, item: Item, format_id: str, rng: str | None):
    """Open the media URL. A 403 is often brief (YouTube's availability window), so retry a
    few times; if it persists or the URL expired (404/410), re-extract once and retry."""
    f = item.format(format_id)
    if f is None:
        raise StreamError("Format not found", 404)
    for attempt in range(5):
        try:
            return f, _open(resolved, f, rng)
        except HTTPError as e:
            if e.status not in (403, 404, 410):
                raise StreamError(f"The platform returned an error ({e.status}).") from e
            if e.status != 403 or attempt == 4:
                break
            time.sleep(2)
        except TransportError as e:   # connection reset / timeout: these come in short bursts
            if attempt == 4:
                raise StreamError("We couldn't reach the platform. Please try again in a moment.") from e
            time.sleep(1.5 * (attempt + 1))
    try:
        refresh_item(resolved, item.index)
    except Exception as e:  # noqa: BLE001
        raise StreamError("The platform refused the download. Please paste the link again.") from e
    f = item.format(format_id)
    if f is None:
        raise StreamError("This video changed on the platform. Please paste the link again.", 410)
    try:
        return f, _open(resolved, f, rng)
    except (HTTPError, TransportError) as e:
        raise StreamError("The platform refused the download. Please paste the link again.") from e


_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)$")


def _parse_range(rng: str | None) -> tuple[int, int | None] | None:
    if not rng:
        return None
    m = _RANGE_RE.match(rng.strip())
    if not m or (not m.group(1) and not m.group(2)):
        return None
    if not m.group(1):  # suffix range "bytes=-500" -> not worth supporting, send everything
        return None
    return int(m.group(1)), int(m.group(2)) if m.group(2) else None


async def _iter_response(resp) -> AsyncIterator[bytes]:
    try:
        while True:
            chunk = await asyncio.to_thread(resp.read, CHUNK)
            if not chunk:
                break
            yield chunk
    finally:
        await asyncio.to_thread(resp.close)


async def open_relay(resolved: Resolved, item: Item, format_id: str, client_range: str | None) -> Upstream:
    f = item.format(format_id)
    if f is None:
        raise StreamError("Format not found", 404)
    chunk_size = (f.get("downloader_options") or {}).get("http_chunk_size")
    total = f.get("filesize")

    if not chunk_size:
        # Simple case: one upstream request, client's Range passed through.
        f, resp = await asyncio.to_thread(_open_with_refresh, resolved, item, format_id, client_range)
        h = {k.lower(): v for k, v in resp.headers.items()}
        out = {"Accept-Ranges": "bytes" if h.get("accept-ranges") == "bytes" or resp.status == 206 else "none"}
        for k in ("content-length", "content-range", "content-type"):
            if h.get(k):
                out[k.title()] = h[k]
        return Upstream(resp.status, out, _iter_response(resp))

    # YouTube adaptive streams: a single big request is throttled, so fetch in chunks.
    rng = _parse_range(client_range)
    start = rng[0] if rng else 0
    if total is None:
        f, probe = await asyncio.to_thread(_open_with_refresh, resolved, item, format_id, "bytes=0-0")
        cr = probe.headers.get("Content-Range", "")
        await asyncio.to_thread(probe.close)
        total = int(cr.rsplit("/", 1)[-1]) if "/" in cr and cr.rsplit("/", 1)[-1].isdigit() else None
    if total is None:
        raise StreamError("Couldn't read the file size from the platform.")
    end = min(rng[1], total - 1) if rng and rng[1] is not None else total - 1
    if start > end:
        raise StreamError("Requested range not satisfiable", 416)

    async def body() -> AsyncIterator[bytes]:
        pos, stalls = start, 0
        while pos <= end:
            stop = min(pos + chunk_size - 1, end)
            _, resp = await asyncio.to_thread(_open_with_refresh, resolved, item, format_id, f"bytes={pos}-{stop}")
            got = 0
            async for piece in _iter_response(resp):
                got += len(piece)
                pos += len(piece)
                yield piece
            # An early close just means the next request continues from `pos`.
            stalls = stalls + 1 if got == 0 else 0
            if stalls >= 3:
                return

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
        "Content-Type": "audio/mp4" if f.get("ext") == "m4a" else "video/mp4" if f.get("ext") == "mp4" else "application/octet-stream",
    }
    status = 200
    if rng:
        status = 206
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
    return Upstream(status, headers, body())


# ---------------------------------------------------------------- ffmpeg (MP3, HLS, non-MP4 merges)
#
# Used only when the virtual muxer can't build the file (MP3 needs re-encoding; VP9/WebM and
# HLS inputs have no byte-exact layout). The download still starts at once, but the size is
# unknown, so it can't be resumed. ffmpeg reads its inputs from the relay on localhost
# (GET /api/raw/...), which adds cookies, impersonation and YouTube-style chunked requests.

import secrets  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import threading  # noqa: E402
from pathlib import Path  # noqa: E402

from .config import Settings  # noqa: E402
from .extractor import Option  # noqa: E402

RELAY_KEY = secrets.token_urlsafe(18)   # only ffmpeg on this machine knows it; changes every start


class _Slots:
    """Caps concurrent ffmpeg processes (CPU / bandwidth)."""

    def __init__(self, n: int):
        self._sem = threading.BoundedSemaphore(n)

    def take(self) -> bool:
        return self._sem.acquire(blocking=False)

    def give(self) -> None:
        self._sem.release()


_slots: _Slots | None = None


def _ffmpeg_bin(settings: Settings) -> str:
    if settings.ffmpeg_location:
        loc = settings.ffmpeg_location
        return loc if loc.lower().endswith(("ffmpeg", "ffmpeg.exe")) else str(Path(loc) / "ffmpeg")
    return shutil.which("ffmpeg") or "ffmpeg"


def _input_args(resolved: Resolved, item: Item, format_id: str, settings: Settings) -> list[str]:
    f = item.format(format_id)
    if f is None:
        raise StreamError("Format not found", 404)
    if str(f.get("protocol") or "").startswith("m3u8"):
        headers = _request_headers(resolved, f)
        cookie = resolved.ydl.cookiejar.get_cookie_header(f["url"])
        if cookie:
            headers["Cookie"] = cookie
        return ["-headers", "".join(f"{k}: {v}\r\n" for k, v in headers.items()), "-i", f["url"]]
    # Reconnect if the relay's stream drops midway (it resumes with a Range request).
    return ["-reconnect", "1", "-reconnect_on_network_error", "1", "-reconnect_delay_max", "4",
            "-i", f"{settings.internal_api}/api/raw/{resolved.token}/{item.index}/{format_id}?key={RELAY_KEY}"]


def _ffmpeg_cmd(resolved: Resolved, item: Item, opt: Option, settings: Settings, dest: str | None = None,
                extra: list[str] | None = None) -> list[str]:
    """dest=None streams to stdout; a path writes a finished file (jobs.py: exact size, resumable)."""
    cmd = [_ffmpeg_bin(settings), "-hide_banner", "-loglevel", "error", "-nostdin", *(extra or [])]
    for fid in opt.formats:
        cmd += _input_args(resolved, item, fid, settings)
    if opt.transcode == "mp3":
        return cmd + ["-vn", "-c:a", "libmp3lame", "-b:a", "192k", "-f", "mp3", dest or "pipe:1"]
    if dest:   # a regular MP4 with the index up front: plays everywhere, even before it's fully saved
        out = ["-movflags", "+faststart", "-f", "mp4", "-y", dest]
    else:      # fragmented MP4 can be written to a pipe and plays fine once saved
        out = ["-movflags", "frag_keyframe+empty_moov+default_base_moof", "-f", "mp4", "pipe:1"]
    if opt.transcode == "h264":
        # Facebook VP9/AV1 -> H.264 + AAC-LC: smooth, in-sync playback on every phone, PC and editor.
        cmd += ["-map", "0:v:0", "-map", "1:a:0"] if len(opt.formats) == 2 else ["-map", "0:v:0", "-map", "0:a:0?"]
        # -bf 0: B-frames would shift the video ~2 frames after the audio (no edit list in a piped MP4).
        return cmd + ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-bf", "0", "-pix_fmt", "yuv420p",
                      "-c:a", "aac", "-b:a", "128k", "-ac", "2", *out]
    cmd += ["-map", "0:v:0", "-map", "1:a:0"] if len(opt.formats) == 2 else ["-map", "0"]
    return cmd + ["-c", "copy", *out]


def ffmpeg_slots(settings: Settings) -> _Slots:
    """One shared cap for streamed (open_ffmpeg) and file (jobs.py) conversions."""
    global _slots
    if _slots is None:
        _slots = _Slots(settings.max_concurrent_jobs * 2)
    return _slots


async def open_ffmpeg(resolved: Resolved, item: Item, opt: Option, settings: Settings) -> Upstream:
    slots = ffmpeg_slots(settings)
    if not slots.take():
        raise StreamError("The server is busy right now. Please try again in a minute.", 503)
    try:
        proc = subprocess.Popen(_ffmpeg_cmd(resolved, item, opt, settings), stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, bufsize=0)
    except Exception:
        slots.give()
        raise

    stderr_tail: list[bytes] = []

    def drain_stderr() -> None:  # keep stderr from filling up and blocking ffmpeg
        for line in iter(proc.stderr.readline, b""):
            stderr_tail.append(line)
            del stderr_tail[:-20]

    threading.Thread(target=drain_stderr, daemon=True).start()

    def cleanup() -> None:
        if proc.poll() is None:
            proc.kill()
        slots.give()

    # Wait for the first bytes so a failure becomes a clear error instead of an empty file.
    try:
        first = await asyncio.wait_for(asyncio.to_thread(proc.stdout.read, CHUNK), timeout=45)  # < 60 s host idle cutoff
    except asyncio.TimeoutError:
        cleanup()
        raise StreamError("The platform is too slow right now. Please try again.", 504) from None
    if not first:
        await asyncio.to_thread(proc.wait)
        cleanup()
        detail = b"".join(stderr_tail).decode(errors="replace").strip().splitlines()
        raise StreamError("Couldn't prepare this file." + (f" ({detail[-1][:160]})" if detail else ""))

    async def body() -> AsyncIterator[bytes]:
        try:
            yield first
            while chunk := await asyncio.to_thread(proc.stdout.read, CHUNK):
                yield chunk
        finally:
            cleanup()   # also runs when the user cancels the download

    ctype = "audio/mpeg" if opt.transcode == "mp3" else "video/mp4"
    return Upstream(200, {"Content-Type": ctype, "Accept-Ranges": "none"}, body())
