"""HTTP routes for AI Clips (/api/clips/...)."""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, field_validator

from ..captions import languages, llm, stt
from ..captions.styles import Style, preset_style, presets_public
from ..config import get_settings
from ..reframe import jobs as rjobs
from ..reframe import uploads
from ..reframe.api import _disposition, _ip, serve_path
from . import finder, jobs
from .render import ClipLook

router = APIRouter()

_minute: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_window: dict[tuple[str, str], deque[float]] = defaultdict(deque)

Aspect = Literal["9:16", "1:1", "4:5", "original"]
Layout = Literal["smart", "blur", "fit"]
Length = Literal["auto", "short", "medium", "long", "xl"]


def _limit(request: Request, bucket: str, per_min: int) -> None:
    q = _minute[(bucket, _ip(request))]
    now = time.monotonic()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= per_min:
        raise HTTPException(429, "Too many requests. Please wait a minute and try again.")
    q.append(now)


def _quota(request: Request, bucket: str, limit: int, seconds: int, message: str) -> None:
    q = _window[(bucket, _ip(request))]
    now = time.time()
    while q and now - q[0] > seconds:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, message)
    q.append(now)


def _job(jid: str) -> jobs.Job:
    try:
        return jobs.get(jid)
    except jobs.JobError as e:
        raise HTTPException(e.status, e.message) from e


def _owned(jid: str, request: Request) -> jobs.Job:
    job = _job(jid)
    if job.ip != _ip(request):
        raise HTTPException(403, "Only the person who made these clips can change them.")
    return job


def _clip(job: jobs.Job, cid: str) -> jobs.Clip:
    try:
        return jobs.clip(job, cid)
    except jobs.JobError as e:
        raise HTTPException(e.status, e.message) from e


def _submit(job: jobs.Job, task: str, params: dict | None = None, new: bool = False) -> dict:
    try:
        jobs.submit(job, task, params, new=new)
    except jobs.JobError as e:
        raise HTTPException(e.status, e.message) from e
    return job.public(jobs.position(job))


def _detail(e: Exception) -> str:
    errs = getattr(e, "errors", lambda: [])()
    if errs:
        loc = ".".join(str(x) for x in errs[0].get("loc", []) if x != "body")
        msg = str(errs[0].get("msg", "")).removeprefix("Value error, ")
        return f"{msg} ({loc})" if loc and "Value error" not in str(errs[0].get("msg", "")) else msg
    return str(e)


async def _body(request: Request, model: type[BaseModel]):
    try:
        return model.model_validate(await request.json())
    except ValueError as e:
        raise HTTPException(422, _detail(e)) from e


# ---------------------------------------------------------------- config


@router.get("/api/clips/config")
async def config() -> dict:
    s = get_settings()
    return {
        "languages": [lang.public() for lang in languages.LANGS],
        "presets": presets_public(),
        "lengths": {k: {"min": v[0], "max": v[1], "ideal": v[2]} for k, v in finder.LENGTHS.items()},
        "max_clips": finder.MAX_CLIPS,
        "features": {"ai": llm.available(), "ai_provider": llm.provider(), "stt": stt.provider_name()},
        "max_duration_sec": s.clips_max_duration_sec,
        "max_upload_mb": s.upload_max_mb,
        "allow_links": s.reframe_allow_links,
        "ttl_hours": s.reframe_ttl_sec // 3600,
        "daily_limit": s.clips_daily_per_ip,
        "watermark": s.captions_watermark,
    }


# ---------------------------------------------------------------- jobs


class LookIn(BaseModel):
    aspect: Aspect = "9:16"
    layout: Layout = "smart"
    captions: bool = True
    preset: str = Field("bold-pop", max_length=40)
    style: Style | None = None
    hook: bool = True
    remove_fillers: bool = False
    remove_silences: bool = False
    progress_bar: bool = False
    watermark: bool = False
    quality: Literal["1080p", "720p"] = "1080p"

    def to_look(self) -> ClipLook:
        style = self.style or preset_style(self.preset)
        if self.style is None and self.aspect in ("1:1", "original"):
            style = style.model_copy(update={"y": 0.80})
        return ClipLook(aspect=self.aspect, layout=self.layout, captions=self.captions, style=style, hook=self.hook,
                        remove_fillers=self.remove_fillers, remove_silences=self.remove_silences,
                        progress_bar=self.progress_bar, watermark=self.watermark, quality=self.quality)


class FindIn(BaseModel):
    length: Length = "auto"
    count: int | None = Field(None, ge=1, le=finder.MAX_CLIPS)
    topic: str | None = Field(None, max_length=200)
    look: LookIn = Field(default_factory=LookIn)


class SourceIn(BaseModel):
    type: Literal["upload", "link"]
    id: str | None = Field(None, max_length=64)
    token: str | None = Field(None, max_length=64)
    index: int = Field(0, ge=0, le=50)


class JobIn(FindIn):
    source: SourceIn
    language: str = Field("auto", max_length=10)
    range_start: float = Field(0.0, ge=0)
    range_end: float | None = Field(None, gt=0)
    title: str | None = Field(None, max_length=200)

    @field_validator("language")
    @classmethod
    def _lang(cls, v: str) -> str:
        if v != "auto" and languages.get(v) is None:
            raise ValueError("That language isn't supported yet.")
        return v


def _too_long(s, seconds: float) -> HTTPException:
    return HTTPException(422, f"This video is {seconds / 60:.0f} minutes long. Please choose up to "
                              f"{s.clips_max_duration_sec // 60} minutes of it (set Start and End).")


@router.post("/api/clips/jobs")
async def job_create(request: Request):
    body: JobIn = await _body(request, JobIn)
    s = get_settings()
    _limit(request, "clips-new", 6)
    src = body.source
    ip = _ip(request)
    if body.range_end is not None and body.range_end <= body.range_start + 5:
        raise HTTPException(422, "The end time must be at least 5 seconds after the start.")
    kw: dict = {"source": {"type": src.type}}
    up = None
    if src.type == "upload":
        try:
            up = uploads.get(src.id or "")
        except uploads.UploadError as e:
            raise HTTPException(e.status, e.message) from e
        if up.info is None:
            raise HTTPException(409, "The upload isn't finished yet.")
        if up.ip != ip:
            raise HTTPException(403, "This upload belongs to someone else.")
        info = up.info
        if not info.has_audio:
            raise HTTPException(422, "This video has no sound. AI Clips finds the best moments from what is said.")
        end = min(body.range_end or info.duration, info.duration)
        if body.range_start >= info.duration - 1:
            raise HTTPException(422, "The start time is after the end of the video.")
        if end - body.range_start > s.clips_max_duration_sec + 1:
            raise _too_long(s, end - body.range_start)
        kw.update(src_path=up.path, info=info, title=body.title or up.filename)
        kw["source"]["id"] = up.id
    else:
        if not s.reframe_allow_links:
            raise HTTPException(422, "Links are turned off. Please upload the file.")
        if not src.token:
            raise HTTPException(422, "Missing link.")
        if rjobs.link_lookup is not None:
            try:
                r = rjobs.link_lookup(src.token)
                item = r.item(src.index)
            except Exception as e:  # noqa: BLE001
                raise HTTPException(410, "This link has expired. Please paste it again.") from e
            if item.duration:
                end = min(body.range_end or item.duration, item.duration)
                if end - body.range_start > s.clips_max_duration_sec + 1:
                    raise _too_long(s, end - body.range_start)
            kw["title"] = body.title or item.title or r.title or "video"
        kw["source"].update(token=src.token, index=src.index)
    kw.setdefault("title", body.title or "video")
    _quota(request, "clips-day", s.clips_daily_per_ip, 86400,
           "You've reached today's limit for AI Clips. Please come back tomorrow.")
    settings = jobs.Settings(language=body.language, topic=(body.topic or "").strip() or None, length=body.length,
                             count=body.count, range_start=body.range_start, range_end=body.range_end,
                             look=body.look.to_look())
    job = jobs.new_job(ip=ip, settings=settings, **kw)
    if up is not None:
        up.used_by += 1
        job.upload_ref = up.id
    try:
        return _submit(job, "process", new=True)
    except HTTPException:
        jobs.delete(job)
        raise


@router.get("/api/clips/jobs/{jid}")
async def job_status(jid: str):
    job = _job(jid)
    return job.public(jobs.position(job))


@router.post("/api/clips/jobs/{jid}/find")
async def job_find(jid: str, request: Request):
    """Search the same video again with another length / number / topic (no new speech-to-text)."""
    body: FindIn = await _body(request, FindIn)
    job = _owned(jid, request)
    if job.transcript is None:
        raise HTTPException(409, "Please wait until the video has been listened to.")
    s = get_settings()
    _limit(request, "clips-find", 6)
    _quota(request, "clips-find", s.clips_finds_per_day, 86400,
           "You've searched for clips a lot today. Please come back tomorrow.")
    old = job.settings
    settings = jobs.Settings(language=old.language, topic=(body.topic or "").strip() or None, length=body.length,
                             count=body.count, range_start=old.range_start, range_end=old.range_end,
                             look=body.look.to_look())
    return _submit(job, "find", {"settings": settings})


class LookPatch(BaseModel):
    aspect: Aspect | None = None
    layout: Layout | None = None
    captions: bool | None = None
    style: Style | None = None
    hook: bool | None = None
    remove_fillers: bool | None = None
    remove_silences: bool | None = None
    progress_bar: bool | None = None
    watermark: bool | None = None
    quality: Literal["1080p", "720p"] | None = None


class ClipPatch(BaseModel):
    start: float | None = Field(None, ge=0)
    end: float | None = Field(None, gt=0)
    title: str | None = Field(None, max_length=200)
    hook: str | None = Field(None, max_length=140)
    description: str | None = Field(None, max_length=1000)
    hashtags: list[str] | None = Field(None, max_length=12)
    look: LookPatch | None = None
    render: bool = False          # render again even if nothing changed (after an error)


@router.patch("/api/clips/jobs/{jid}/clips/{cid}")
async def clip_edit(jid: str, cid: str, request: Request):
    body: ClipPatch = await _body(request, ClipPatch)
    job = _owned(jid, request)
    c = _clip(job, cid)
    s = get_settings()
    if job.src_path is None or not Path(job.src_path).exists():
        raise HTTPException(410, "The original video has expired. Please start again.")
    patch = body.model_dump(exclude_none=True)
    if body.look is not None:
        patch["look"] = {k: getattr(body.look, k) for k in body.look.model_fields_set if getattr(body.look, k) is not None}
    _limit(request, "clips-edit", 30)
    will_render = body.render or body.start is not None or body.end is not None or body.look is not None \
        or body.hook is not None
    if will_render:
        _quota(request, "clips-render", s.clips_renders_per_hour, 3600,
               "You've re-rendered a lot of clips this hour. Please wait a little and try again.")
    try:
        rerender = jobs.edit_clip(job, c, patch)
    except jobs.JobError as e:
        raise HTTPException(e.status, e.message) from e
    if rerender and job.state not in jobs.ACTIVE:
        return _submit(job, "render")
    return job.public(jobs.position(job))


@router.delete("/api/clips/jobs/{jid}")
async def job_cancel(jid: str, request: Request, remove: bool = False):
    job = _owned(jid, request)
    if remove:
        jobs.delete(job)
        return {"ok": True}
    jobs.cancel(job)
    return job.public(jobs.position(job))


# ---------------------------------------------------------------- files


@router.api_route("/api/clips/jobs/{jid}/clips/{cid}/file", methods=["GET", "HEAD"])
async def clip_file(jid: str, cid: str, request: Request, inline: bool = False):
    job = _job(jid)
    c = _clip(job, cid)
    if c.output is None or not c.output.exists():
        raise HTTPException(404, "This clip isn't ready yet.")
    rank = next((i + 1 for i, x in enumerate(job.ranked()) if x.id == c.id), 1)
    name = f"{rank:02d}-{rjobs._safe_stem(c.title or job.title)}-klyprima.mp4"
    return serve_path(request, c.output, name, "video/mp4", inline)


@router.get("/api/clips/jobs/{jid}/clips/{cid}/thumb")
async def clip_thumb(jid: str, cid: str):
    c = _clip(_job(jid), cid)
    if c.thumb is None or not c.thumb.exists():
        raise HTTPException(404)
    return FileResponse(c.thumb, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


@router.get("/api/clips/jobs/{jid}/clips/{cid}/srt")
async def clip_srt(jid: str, cid: str, inline: bool = False):
    job = _job(jid)
    c = _clip(job, cid)
    try:
        text, name = jobs.clip_srt(job, c)
    except jobs.JobError as e:
        raise HTTPException(e.status, e.message) from e
    return Response("﻿" + text, media_type="application/x-subrip; charset=utf-8",
                    headers={"Content-Disposition": _disposition(name, inline), "Cache-Control": "no-store"})


@router.get("/api/clips/jobs/{jid}/zip")
async def job_zip(jid: str, request: Request):
    job = _job(jid)
    try:
        path = await asyncio.to_thread(jobs.build_zip, job)
    except jobs.JobError as e:
        raise HTTPException(e.status, e.message) from e
    name = f"{rjobs._safe_stem(job.title)}-klyprima-clips.zip"
    return serve_path(request, path, name, "application/zip", False)


@router.get("/api/clips/jobs/{jid}/transcript")
async def job_transcript(jid: str):
    """Sentence lines with times, for the clip editor's "start here / end here" picker."""
    job = _job(jid)
    t = job.transcript
    if t is None:
        raise HTTPException(404, "There's no transcript yet.")
    return {"language": t.language, "rtl": languages.info(t.language).rtl and not t.language.endswith("-Latn"),
            "lines": [{"i": i, "start": round(ln.start, 3), "end": round(ln.end, 3), "text": ln.text(t.language)}
                      for i, ln in enumerate(t.lines)]}


@router.api_route("/api/clips/jobs/{jid}/source", methods=["GET", "HEAD"])
async def job_source(jid: str, request: Request):
    job = _job(jid)
    if job.src_path is None or not Path(job.src_path).exists():
        raise HTTPException(404, "The original video isn't available.")
    ctype = "video/webm" if str(job.src_path).endswith(".webm") else "video/mp4"
    return serve_path(request, Path(job.src_path), "source.mp4", ctype, True)
