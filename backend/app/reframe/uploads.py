"""Chunked, resumable uploads.

The browser asks for an upload slot (POST), sends the file in pieces (PUT ?offset=N; a piece sent
twice or out of order gets 409 with the size we have, so the browser just continues from there),
then completes it (POST .../complete), which checks the file with ffprobe.
"""

from __future__ import annotations

import asyncio
import re
import secrets
import shutil
import threading
import time
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path

from ..config import DATA_DIR, get_settings
from .media import MediaError, MediaInfo, probe

UPLOADS_DIR = DATA_DIR / "uploads"
_ID = re.compile(r"^[A-Za-z0-9_-]{16,40}$")


class UploadError(Exception):
    def __init__(self, message: str, status: int = 422, extra: dict | None = None):
        super().__init__(message)
        self.message = message
        self.status = status
        self.extra = extra or {}


@dataclass
class Upload:
    id: str
    path: Path
    filename: str
    size: int
    ip: str
    created: float = field(default_factory=time.time)
    received: int = 0
    info: MediaInfo | None = None
    used_by: int = 0                     # jobs using this file (not deleted while > 0)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def public(self) -> dict:
        return {"id": self.id, "filename": self.filename, "size": self.size, "received": self.received,
                "complete": self.info is not None, "info": self.info.public() if self.info else None}


_uploads: dict[str, Upload] = {}
_guard = threading.Lock()


def free_gb() -> float:
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    return shutil.disk_usage(UPLOADS_DIR).free / 1024 ** 3


def clean_name(name: str) -> str:
    base = Path(name or "video").name
    base = re.sub(r"[^\w .()-]", "", base, flags=re.UNICODE).strip() or "video"
    return base[:120]


def create(filename: str, size: int, ip: str) -> Upload:
    s = get_settings()
    if size <= 0:
        raise UploadError("This file is empty.")
    if size > s.upload_max_mb * 1024 * 1024:
        raise UploadError(f"This file is too big. The limit is {s.upload_max_mb} MB.", 413)
    if free_gb() - size / 1024 ** 3 < s.reframe_min_free_gb:
        raise UploadError("The server is very busy right now. Please try again in a few minutes.", 503)
    with _guard:
        mine = [u for u in _uploads.values() if u.ip == ip and u.info is None and time.time() - u.created < 3600]
        if len(mine) >= 3:
            raise UploadError("You already have uploads in progress. Please finish or cancel those first.", 429)
        uid = secrets.token_urlsafe(18)
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        up = Upload(id=uid, path=UPLOADS_DIR / f"{uid}.bin", filename=clean_name(filename), size=size, ip=ip)
        up.path.touch()
        _uploads[uid] = up
    return up


def get(uid: str) -> Upload:
    up = _uploads.get(uid) if _ID.match(uid or "") else None
    if up is None or not up.path.exists():
        raise UploadError("This upload has expired. Please choose the file again.", 404)
    return up


async def write_chunk(up: Upload, offset: int, body: AsyncIterator[bytes]) -> int:
    limit = get_settings().upload_chunk_mb * 1024 * 1024 + 1024
    async with up.lock:
        if up.info is not None:
            raise UploadError("This upload is already finished.", 409, {"received": up.received})
        if offset != up.received:
            raise UploadError("Out of order piece.", 409, {"received": up.received})
        written = 0
        with up.path.open("r+b") as f:
            f.seek(offset)
            try:
                async for piece in body:
                    if not piece:
                        continue
                    written += len(piece)
                    if written > limit or offset + written > up.size:
                        raise UploadError("This piece is bigger than expected.", 413)
                    await asyncio.to_thread(f.write, piece)
            except UploadError:
                f.truncate(offset)
                raise
            except Exception as e:   # client disconnected mid-piece: keep only what's complete
                f.truncate(offset)
                raise UploadError("The upload was interrupted.", 400, {"received": up.received}) from e
        up.received = offset + written
        return up.received


async def complete(up: Upload) -> MediaInfo:
    async with up.lock:
        if up.info is not None:
            return up.info
        if up.received != up.size:
            raise UploadError("The upload isn't finished yet.", 409, {"received": up.received})
        try:
            info = await asyncio.to_thread(probe, up.path)
        except MediaError as e:
            raise UploadError(str(e)) from e
        # Longer videos are accepted: the visitor then picks (trims) a part up to the limit.
        if info.duration > 4 * 3600:
            raise UploadError("This video is longer than 4 hours. Please cut out the part you need first.")
        up.info = info
        return info


def delete(uid: str) -> None:
    with _guard:
        up = _uploads.pop(uid, None)
    if up is not None and up.used_by == 0:
        up.path.unlink(missing_ok=True)


def prune(max_age: float) -> None:
    now = time.time()
    with _guard:
        for uid, up in list(_uploads.items()):
            stale_partial = up.info is None and now - up.created > 3 * 3600
            if (now - up.created > max_age or stale_partial) and up.used_by == 0:
                _uploads.pop(uid, None)
                up.path.unlink(missing_ok=True)
        known = {u.path.name for u in _uploads.values()}
    if UPLOADS_DIR.exists():
        for p in UPLOADS_DIR.iterdir():
            if p.name not in known and now - p.stat().st_mtime > max_age:
                p.unlink(missing_ok=True)
