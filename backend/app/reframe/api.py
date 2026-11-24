"""HTTP routes for the Reframe tool."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse
from pydantic import BaseModel, Field, field_validator

from ..config import get_settings
from ..stream import _parse_range
from . import jobs, uploads
from .detect import COCO, SYNONYMS, class_id
from .director import ASPECTS, SAFE_RIGHT, Override
from .render import Look

router = APIRouter()
Aspect = Literal["9:16", "4:5", "1:1"]


def _ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (request.client.host if request.client else "?")


_daily: dict[str, deque[float]] = defaultdict(deque)
_minute: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def _limit(request: Request, bucket: str, per_min: int) -> None:
    q = _minute[(bucket, _ip(request))]
    now = time.monotonic()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= per_min:
        raise HTTPException(429, "Too many requests. Please wait a minute and try again.")
    q.append(now)


def _daily_quota(request: Request) -> None:
    q = _daily[_ip(request)]
    now = time.time()
    while q and now - q[0] > 86400:
        q.popleft()
    if len(q) >= get_settings().reframe_daily_per_ip:
        raise HTTPException(429, "You've reached today's limit for conversions. Please come back tomorrow.")
    q.append(now)


def _upload_error(e: uploads.UploadError) -> JSONResponse:
    return JSONResponse({"detail": e.message, **e.extra}, status_code=e.status)


def _job_or_404(jid: str) -> jobs.Job:
    try:
        return jobs.get(jid)
    except jobs.JobError as e:
        raise HTTPException(e.status, e.message) from e


# ---------------------------------------------------------------- config


@router.get("/api/reframe/config")
async def config() -> dict:
    s = get_settings()
    return {
        "max_upload_mb": s.upload_max_mb,
        "chunk_mb": s.upload_chunk_mb,
        "max_duration_sec": s.reframe_max_duration_sec,
        "allow_links": s.reframe_allow_links,
        "aspects": {k: list(v) for k, v in ASPECTS.items()},
        "safe_zones": SAFE_RIGHT,
        "objects": sorted(set(COCO) - {"person"}),
        "synonyms": SYNONYMS,
        "ttl_hours": s.reframe_ttl_sec // 3600,
    }


# ---------------------------------------------------------------- uploads


class UploadIn(BaseModel):
    filename: str = Field(max_length=300)
    size: int = Field(gt=0)


@router.post("/api/uploads")
async def upload_create(body: UploadIn, request: Request):
    _limit(request, "upload", 10)
    try:
        up = uploads.create(body.filename, body.size, _ip(request))
    except uploads.UploadError as e:
        return _upload_error(e)
    return {**up.public(), "chunk_size": get_settings().upload_chunk_mb * 1024 * 1024}


@router.get("/api/uploads/{uid}")
async def upload_status(uid: str):
    try:
        return uploads.get(uid).public()
    except uploads.UploadError as e:
        return _upload_error(e)


@router.put("/api/uploads/{uid}")
async def upload_chunk(uid: str, request: Request, offset: int = Query(ge=0)):
    try:
        up = uploads.get(uid)
        if up.ip != _ip(request):
            raise uploads.UploadError("This upload belongs to someone else.", 403)
        received = await uploads.write_chunk(up, offset, request.stream())
    except uploads.UploadError as e:
        return _upload_error(e)
    return {"received": received, "size": up.size}


@router.post("/api/uploads/{uid}/complete")
async def upload_complete(uid: str):
    try:
        up = uploads.get(uid)
        await uploads.complete(up)
    except uploads.UploadError as e:
        return _upload_error(e)
    return up.public()


@router.delete("/api/uploads/{uid}")
async def upload_delete(uid: str, request: Request):
    try:
        up = uploads.get(uid)
    except uploads.UploadError:
        return {"ok": True}
    if up.ip == _ip(request):
        uploads.delete(uid)
    return {"ok": True}


# ---------------------------------------------------------------- jobs


class LookIn(BaseModel):
    background: Literal["blur", "color"] = "blur"
    color: str = Field("#000000", pattern=r"^#[0-9a-fA-F]{6}$")
    blur: int = Field(2, ge=1, le=3)
    dim: float = Field(0.15, ge=0, le=0.6)
    fg_zoom: float = Field(1.0, ge=1.0, le=1.5)


class SmartIn(BaseModel):
    style: Literal["steady", "follow"] = "steady"
    framing: float = Field(1.0, ge=1.0, le=1.6)
    dynamic_zoom: bool = False
    zoom_amount: float = Field(1.12, ge=1.05, le=1.3)
    split: bool = True
    facecam: bool = True
    text_aware: bool = True
    two_person: Literal["auto", "split", "switch"] = "auto"
    safe_zone: Literal["tiktok", "reels", "shorts", "none"] = "tiktok"
    follow: str | None = Field(None, max_length=40)

    @field_validator("follow")
    @classmethod
    def _follow(cls, v: str | None) -> str | None:
        v = (v or "").strip().lower()
        if not v or v in ("auto", "speaker", "person", "people", "face"):
            return None
        if class_id(v) is None:
            raise ValueError(f"We can't follow \"{v}\" yet. Try a ball, dog, cat, car, bike, phone, laptop and similar everyday objects, or click the object in the shot editor.")
        return v

    def options(self) -> dict:
        d = self.model_dump()
        d["follow_cls"] = class_id(d["follow"]) if d.get("follow") else None
        return d


class SourceIn(BaseModel):
    type: Literal["upload", "link", "captions"]     # captions: the video of a caption project ("Make it vertical")
    id: str | None = Field(None, max_length=64)
    token: str | None = Field(None, max_length=64)
    index: int = Field(0, ge=0, le=50)


class JobIn(BaseModel):
    source: SourceIn
    mode: Literal["smart", "blur", "crop", "fit"] = "smart"
    aspects: list[Aspect] = Field(default_factory=lambda: ["9:16"], min_length=1, max_length=3)
    quality: Literal["1080p", "720p"] = "1080p"
    smart: SmartIn = Field(default_factory=SmartIn)
    look: LookIn = Field(default_factory=LookIn)
    position: float = Field(0.5, ge=0, le=1)
    trim_start: float = Field(0.0, ge=0)
    trim_end: float | None = Field(None, gt=0)
    title: str | None = Field(None, max_length=200)

    @field_validator("aspects", mode="before")
    @classmethod
    def _unique(cls, v):
        return list(dict.fromkeys(v)) if isinstance(v, list) else v


def _detail(e: Exception) -> str:
    errs = getattr(e, "errors", lambda: [])()
    if errs:
        msg = str(errs[0].get("msg", ""))
        return msg.removeprefix("Value error, ")
    return str(e)


@router.post("/api/reframe/jobs")
async def job_create(request: Request):
    try:
        body = JobIn.model_validate(await request.json())
    except ValueError as e:
        raise HTTPException(422, _detail(e)) from e
    s = get_settings()
    _limit(request, "reframe", 6)
    _daily_quota(request)
    src = body.source
    kw: dict = {}
    if src.type == "upload":
        try:
            up = uploads.get(src.id or "")
        except uploads.UploadError as e:
            raise HTTPException(e.status, e.message) from e
        if up.info is None:
            raise HTTPException(409, "The upload isn't finished yet.")
        info = up.info
        end = min(body.trim_end or info.duration, info.duration)
        if end - body.trim_start > s.reframe_max_duration_sec + 1:
            raise HTTPException(422, f"Please choose up to {s.reframe_max_duration_sec // 60} minutes of the video (use Trim).")
        if body.trim_start >= info.duration - 0.2:
            raise HTTPException(422, "The start time is after the end of the video.")
        kw = dict(src_path=up.path, info=info, title=body.title or up.filename, source={"type": "upload", "id": up.id})
        up.used_by += 1
        kw["upload_ref"] = up.id
    elif src.type == "captions":
        from ..captions import jobs as cjobs
        try:
            cj = cjobs.get(src.id or "")
        except cjobs.JobError as e:
            raise HTTPException(e.status, e.message) from e
        if cj.ip != _ip(request):
            raise HTTPException(403, "That video belongs to someone else.")
        if cj.src_path is None or not Path(cj.src_path).exists() or cj.info is None:
            raise HTTPException(409, "That video isn't ready yet.")
        info = cj.info
        end = min(body.trim_end or info.duration, info.duration)
        if end - body.trim_start > s.reframe_max_duration_sec + 1:
            raise HTTPException(422, f"Please choose up to {s.reframe_max_duration_sec // 60} minutes of the video (use Trim).")
        kw = dict(info=info, title=body.title or cj.title, source={"type": "captions", "id": cj.id},
                  _link_from=Path(cj.src_path))
    else:
        if not s.reframe_allow_links:
            raise HTTPException(422, "Links are turned off for this tool. Please upload the file.")
        if not src.token:
            raise HTTPException(422, "Missing link.")
        if jobs.link_lookup is not None:
            try:
                r = jobs.link_lookup(src.token)
                item = r.item(src.index)
            except Exception as e:  # noqa: BLE001
                raise HTTPException(410, "This link has expired. Please paste it again.") from e
            if item.duration and min(body.trim_end or item.duration, item.duration) - body.trim_start > s.reframe_max_duration_sec + 1:
                raise HTTPException(422, f"Please choose up to {s.reframe_max_duration_sec // 60} minutes of the video (use Trim).")
            kw["title"] = body.title or item.title or r.title
        kw["source"] = {"type": "link", "token": src.token, "index": src.index}
        kw.setdefault("title", body.title or "video")
    link_from: Path | None = kw.pop("_link_from", None)
    job = jobs.new_job(
        ip=_ip(request), mode=body.mode, aspects=list(body.aspects), quality=body.quality,
        smart=body.smart.options(), look=Look(**body.look.model_dump()), position=body.position,
        trim_start=body.trim_start, trim_end=body.trim_end, **kw,
    )
    if link_from is not None:   # own copy (hard link): the caption project may be deleted first
        job.src_path = job.dir / f"source{link_from.suffix}"
        jobs.link_or_copy(link_from, job.src_path)
    try:
        jobs.submit(job)
    except jobs.JobError as e:
        jobs.delete(job)
        raise HTTPException(e.status, e.message) from e
    return job.public(jobs.position(job))


@router.get("/api/reframe/jobs/{jid}")
async def job_status(jid: str):
    job = _job_or_404(jid)
    return job.public(jobs.position(job))


class OverrideIn(BaseModel):
    layout: Literal["auto", "follow", "split", "facecam", "fit"] = "auto"
    center: float | None = Field(None, ge=0, le=1)
    track: int | None = None
    point: list[float] | None = Field(None, min_length=2, max_length=2)

    def to_override(self) -> Override | None:
        o = Override(layout=None if self.layout == "auto" else self.layout, center=self.center, track=self.track,
                     point=(min(1, max(0, self.point[0])), min(1, max(0, self.point[1]))) if self.point else None)
        return o if any(v is not None for v in o.__dict__.values()) else None


class RenderIn(BaseModel):
    overrides: dict[int, OverrideIn] = Field(default_factory=dict)
    mode: Literal["smart", "blur", "crop", "fit"] | None = None
    aspects: list[Aspect] | None = Field(None, min_length=1, max_length=3)
    quality: Literal["1080p", "720p"] | None = None
    smart: SmartIn | None = None
    look: LookIn | None = None
    position: float | None = Field(None, ge=0, le=1)


@router.post("/api/reframe/jobs/{jid}/render")
async def job_render(jid: str, request: Request):
    job = _job_or_404(jid)
    try:
        body = RenderIn.model_validate(await request.json())
    except ValueError as e:
        raise HTTPException(422, _detail(e)) from e
    if job.ip != _ip(request):
        raise HTTPException(403, "Only the person who started this job can change it.")
    if job.state not in ("done", "error", "cancelled"):
        raise HTTPException(409, "This video is still being processed.")
    if job.src_path is None or not Path(job.src_path).exists():
        raise HTTPException(410, "The original video has expired. Please start again.")
    _limit(request, "rerender", 10)
    if body.mode:
        job.mode = body.mode
    if body.aspects:
        job.aspects = list(dict.fromkeys(body.aspects))
    if body.quality:
        job.quality = body.quality
    if body.smart:
        job.smart = body.smart.options()
    if body.look:
        job.look = Look(**body.look.model_dump())
    if body.position is not None:
        job.position = body.position
    analysis = job.analysis
    overrides = {}
    for k, v in body.overrides.items():
        o = v.to_override()
        if o is not None and (analysis is None or 0 <= k < len(analysis.shots)):
            overrides[k] = o
    job.overrides = overrides
    try:
        jobs.requeue(job)
    except jobs.JobError as e:
        raise HTTPException(e.status, e.message) from e
    return job.public(jobs.position(job))


@router.delete("/api/reframe/jobs/{jid}")
async def job_cancel(jid: str, request: Request, remove: bool = False):
    job = _job_or_404(jid)
    if job.ip != _ip(request):
        raise HTTPException(403, "Only the person who started this job can cancel it.")
    if remove:
        jobs.delete(job)
        return {"ok": True}
    jobs.cancel(job)
    return job.public(jobs.position(job))


@router.get("/api/reframe/jobs/{jid}/thumb/{index}")
async def job_thumb(jid: str, index: int):
    job = _job_or_404(jid)
    p = job.dir / "thumbs" / f"shot{index:03d}.jpg"
    if not p.exists():
        raise HTTPException(404)
    return FileResponse(p, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


def _disposition(name: str, inline: bool) -> str:
    ascii_name = name.encode("ascii", "ignore").decode() or "video.mp4"
    kind = "inline" if inline else "attachment"
    return f"{kind}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"


def serve_path(request: Request, path: Path, name: str, ctype: str, inline: bool) -> Response:
    """A file with exact size and Range support (players seek, browsers and IDM resume)."""
    total = path.stat().st_size
    rng = _parse_range(request.headers.get("range"))
    start, end, status = 0, total - 1, 200
    if rng:
        start = rng[0]
        end = min(rng[1], total - 1) if rng[1] is not None else total - 1
        if start >= total or start > end:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{total}"})
        status = 206
    headers = {
        "Content-Disposition": _disposition(name, inline),
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
        "Cache-Control": "private, no-cache",
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{total}"
    if request.method == "HEAD":
        return Response(status_code=status, media_type=ctype, headers=headers)

    async def body() -> AsyncIterator[bytes]:
        with path.open("rb") as f:
            f.seek(start)
            left = end - start + 1
            while left > 0:
                chunk = await asyncio.to_thread(f.read, min(256 * 1024, left))
                if not chunk:
                    break
                left -= len(chunk)
                yield chunk

    return StreamingResponse(body(), status_code=status, media_type=ctype, headers=headers)


@router.api_route("/api/reframe/jobs/{jid}/file/{aspect}", methods=["GET", "HEAD"])
async def job_file(jid: str, aspect: str, request: Request, inline: bool = False):
    job = _job_or_404(jid)
    out = job.outputs.get(aspect.replace("x", ":"))
    if out is None or not out.path.exists():
        raise HTTPException(404, "This video isn't ready yet.")
    return serve_path(request, out.path, out.name, "video/mp4", inline)


@router.api_route("/api/reframe/jobs/{jid}/source", methods=["GET", "HEAD"])
async def job_source(jid: str, request: Request):
    job = _job_or_404(jid)
    if job.src_path is None or not Path(job.src_path).exists():
        raise HTTPException(404, "The original video isn't available.")
    ctype = "video/webm" if str(job.src_path).endswith(".webm") else "video/mp4"
    return serve_path(request, Path(job.src_path), "source.mp4", ctype, True)
