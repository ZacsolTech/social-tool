"""HTTP routes for the caption tool (/api/captions/...)."""

from __future__ import annotations

import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Literal

import cv2
import numpy as np
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field, field_validator

from ..config import get_settings
from ..reframe import jobs as rjobs
from ..reframe import uploads
from ..reframe.api import _disposition, _ip, serve_path
from ..reframe.media import MediaError, probe
from . import ass as assmod
from . import fonts, jobs, languages, llm, render, stt
from .styles import HEX, Style, presets_public

router = APIRouter()

_minute: dict[tuple[str, str], deque[float]] = defaultdict(deque)
_window: dict[tuple[str, str], deque[float]] = defaultdict(deque)


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
        raise HTTPException(403, "Only the person who started these captions can change them.")
    return job


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


# ---------------------------------------------------------------- config + fonts


@router.get("/api/captions/config")
async def config() -> dict:
    s = get_settings()
    return {
        "languages": [lang.public() for lang in languages.LANGS],
        "translate_targets": [languages.info(c).public() for c in languages.TRANSLATE_TARGETS],
        "presets": presets_public(),
        "fonts": [{"key": f.key, "label": f.label, "family": f.family, "kind": f.kind, "scripts": list(f.scripts),
                   "url": f"/api/captions/fonts/{f.file}"} for f in fonts.registry().values()],
        "script_fonts": fonts.SCRIPT_FONT,
        "features": {"ai": llm.available(), "stt": stt.provider_name(), "translate_any": llm.available(),
                     "ai_provider": llm.provider(), "stt_providers": stt.providers()},
        "max_duration_sec": s.captions_max_duration_sec,
        "max_upload_mb": s.upload_max_mb,
        "allow_links": s.reframe_allow_links,
        "ttl_hours": s.reframe_ttl_sec // 3600,
        "watermark": s.captions_watermark,
        "daily_limit": s.captions_daily_per_ip,
    }


@router.get("/api/captions/fonts/{name}")
async def font_file(name: str):
    f = next((f for f in fonts.registry().values() if f.file == name), None)
    if f is None:
        raise HTTPException(404)
    return FileResponse(fonts.FONTS_DIR / f.file, media_type="font/ttf",
                        headers={"Cache-Control": "public, max-age=31536000, immutable",
                                 "Access-Control-Allow-Origin": "*"})


# ---------------------------------------------------------------- jobs


class SourceIn(BaseModel):
    type: Literal["upload", "link", "reframe", "clip"]     # clip: one clip of an AI Clips project
    id: str | None = Field(None, max_length=64)
    clip: str | None = Field(None, max_length=16)
    token: str | None = Field(None, max_length=64)
    index: int = Field(0, ge=0, le=50)
    aspect: str | None = Field(None, max_length=8)


class JobIn(BaseModel):
    source: SourceIn
    language: str = Field("auto", max_length=10)
    prompt: str | None = Field(None, max_length=400)
    subtitles: str | None = Field(None, max_length=2_000_000)   # import an SRT/VTT instead of AI captions
    reuse: str | None = Field(None, max_length=64)              # carry captions over from another caption job
    title: str | None = Field(None, max_length=200)

    @field_validator("language")
    @classmethod
    def _lang(cls, v: str) -> str:
        if v != "auto" and languages.get(v) is None:
            raise ValueError("That language isn't supported yet.")
        return v


@router.post("/api/captions/jobs")
async def job_create(request: Request):
    body: JobIn = await _body(request, JobIn)
    s = get_settings()
    _limit(request, "captions-new", 8)
    src = body.source
    ip = _ip(request)
    kw: dict = {"source": {"type": src.type}}
    reuse = None
    if body.reuse:
        other = _job(body.reuse)
        if other.ip != ip or other.transcript is None:
            raise HTTPException(403, "Those captions belong to someone else.")
        reuse = other.transcript.to_dict()
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
        if up.info.duration > s.captions_max_duration_sec + 1:
            raise HTTPException(422, f"This video is longer than {s.captions_max_duration_sec // 60} minutes. "
                                     f"Please cut out the part you need first.")
        kw.update(src_path=up.path, info=up.info, title=body.title or up.filename)
        kw["source"]["id"] = up.id
    elif src.type == "link":
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
            if item.duration and item.duration > s.captions_max_duration_sec + 1:
                raise HTTPException(422, f"This video is longer than {s.captions_max_duration_sec // 60} minutes.")
            kw["title"] = body.title or item.title or r.title or "video"
        kw["source"].update(token=src.token, index=src.index)
    elif src.type == "clip":
        from ..clips import jobs as kjobs
        try:
            kj = kjobs.get(src.id or "")
            kc = kjobs.clip(kj, src.clip or "")
            if kj.ip != ip:
                raise HTTPException(403, "That clip belongs to someone else.")
            clip_path, clip_title, clip_words = kjobs.for_captions(kj, kc)
        except kjobs.JobError as e:
            raise HTTPException(e.status, e.message) from e
        kw["title"] = body.title or clip_title
        kw["source"].update(id=kj.id, clip=kc.id)
        if body.subtitles is None:
            reuse = clip_words
    else:
        try:
            rj = rjobs.get(src.id or "")
        except rjobs.JobError as e:
            raise HTTPException(e.status, e.message) from e
        if rj.ip != ip:
            raise HTTPException(403, "That video belongs to someone else.")
        out = rj.outputs.get((src.aspect or "9:16").replace("x", ":"))
        if out is None or not out.path.exists():
            raise HTTPException(404, "That vertical video isn't ready.")
        kw["title"] = body.title or rj.title
        kw["source"].update(id=rj.id, aspect=out.aspect)
        if reuse is not None and (rj.trim_start > 0.05):
            reuse = None      # the vertical video starts later than the captions: transcribe again
    will_transcribe = body.subtitles is None and reuse is None
    if will_transcribe:
        _quota(request, "captions-day", s.captions_daily_per_ip, 86400,
               "You've reached today's limit for AI captions. Please come back tomorrow.")
    kw.setdefault("title", body.title or "video")
    job = jobs.new_job(ip=ip, language=body.language, prompt=(body.prompt or "").strip() or None, **kw)
    copy_from = out.path if src.type == "reframe" else clip_path if src.type == "clip" else None
    if copy_from is not None:
        dest = job.dir / f"source{copy_from.suffix}"
        rjobs.link_or_copy(copy_from, dest)
        job.src_path = dest
        try:
            job.info = probe(dest)
        except MediaError as e:
            jobs.delete(job)
            raise HTTPException(422, str(e)) from e
    if up is not None:
        up.used_by += 1
        job.upload_ref = up.id
    params: dict = {}
    if body.subtitles is not None:
        params["subtitles"] = body.subtitles
    elif reuse is not None:
        params["reuse"] = reuse
    try:
        return _submit(job, "transcribe", params, new=True)
    except HTTPException:
        jobs.delete(job)
        raise


@router.get("/api/captions/jobs/{jid}")
async def job_status(jid: str, since_rev: int | None = None):
    job = _job(jid)
    return job.public(jobs.position(job), since_rev)


class WordIn(BaseModel):
    text: str = Field(max_length=200)
    start: float = Field(ge=0)
    end: float = Field(ge=0)
    keyword: bool = False
    emoji: str | None = Field(None, max_length=16)


class LineIn(BaseModel):
    id: str | None = Field(None, max_length=32)
    words: list[WordIn] = Field(max_length=400)
    translation: str | None = Field(None, max_length=1000)


class TranscriptIn(BaseModel):
    rev: int | None = None
    lines: list[LineIn] = Field(max_length=6000)
    translation_lang: str | None = Field(None, max_length=10)


@router.put("/api/captions/jobs/{jid}/transcript")
async def transcript_save(jid: str, request: Request):
    body: TranscriptIn = await _body(request, TranscriptIn)
    job = _owned(jid, request)
    _limit(request, "captions-save", 90)
    try:
        jobs.apply_edit(job, body.model_dump(exclude={"rev"}), body.rev)
    except jobs.JobError as e:
        raise HTTPException(e.status, e.message) from e
    return job.public(jobs.position(job))


def _ai_quota(request: Request) -> None:
    s = get_settings()
    _quota(request, "captions-ai", s.captions_ai_daily_per_ip, 86400,
           "You've reached today's limit for AI actions. Please come back tomorrow.")


class TranslateIn(BaseModel):
    target: str = Field(max_length=10)

    @field_validator("target")
    @classmethod
    def _t(cls, v: str) -> str:
        if v not in languages.TRANSLATE_TARGETS:
            raise ValueError("We can't translate into that language yet.")
        return v


@router.post("/api/captions/jobs/{jid}/translate")
async def job_translate(jid: str, request: Request):
    body: TranslateIn = await _body(request, TranslateIn)
    job = _owned(jid, request)
    if not llm.available() and body.target != "en":
        raise HTTPException(422, "Only English translation is available right now.")
    _limit(request, "captions-ai", 10)
    _ai_quota(request)
    return _submit(job, "translate", {"target": body.target})


@router.post("/api/captions/jobs/{jid}/romanize")
async def job_romanize(jid: str, request: Request):
    job = _owned(jid, request)
    t = job.transcript
    if t is None or t.language.split("-")[0] not in ("ur", "hi", "pa", "sd") or t.language.endswith("-Latn"):
        raise HTTPException(422, "Roman letters are available for Urdu and Hindi captions.")
    _limit(request, "captions-ai", 10)
    _ai_quota(request)
    return _submit(job, "romanize")


class EnhanceIn(BaseModel):
    keywords: bool = True
    emojis: bool = True
    hooks: bool = True
    ai: bool = True


@router.post("/api/captions/jobs/{jid}/enhance")
async def job_enhance(jid: str, request: Request):
    body: EnhanceIn = await _body(request, EnhanceIn)
    job = _owned(jid, request)
    _limit(request, "captions-ai", 10)
    if body.ai and llm.available():
        _ai_quota(request)
    return _submit(job, "enhance", body.model_dump())


class LogoIn(BaseModel):
    corner: Literal["tl", "tr", "bl", "br"] = "tr"
    scale: float = Field(0.16, ge=0.05, le=0.4)
    opacity: float = Field(0.9, ge=0.1, le=1.0)


class RenderIn(BaseModel):
    style: Style = Field(default_factory=Style)
    mode: Literal["original", "translation", "dual"] = "original"
    quality: Literal["1080p", "720p"] = "1080p"
    hook: str | None = Field(None, max_length=140)
    hook_seconds: float = Field(4.0, ge=0, le=60)
    hook_y: float = Field(0.12, ge=0.03, le=0.9)
    hook_color: str = Field("#FFFFFF", pattern=HEX)
    hook_bg: str = Field("#FF4F1F", pattern=HEX)
    progress_bar: Literal["none", "top", "bottom"] = "none"
    progress_color: str = Field("#FF4F1F", pattern=HEX)
    watermark: bool = False
    remove_fillers: bool = False
    remove_silences: bool = False
    logo: LogoIn | None = None
    transcript: TranscriptIn | None = None          # save these edits first (one request from the editor)


@router.post("/api/captions/jobs/{jid}/render")
async def job_render(jid: str, request: Request):
    body: RenderIn = await _body(request, RenderIn)
    job = _owned(jid, request)
    s = get_settings()
    if body.style.font not in fonts.registry():
        raise HTTPException(422, "Unknown font.")
    if job.src_path is None or not Path(job.src_path).exists():
        raise HTTPException(410, "The original video has expired. Please start again.")
    if body.transcript is not None:
        try:
            jobs.apply_edit(job, body.transcript.model_dump(exclude={"rev"}), body.transcript.rev)
        except jobs.JobError as e:
            raise HTTPException(e.status, e.message) from e
    if body.mode != "original" and not (job.transcript and job.transcript.translation_lang):
        raise HTTPException(422, "Translate the captions first.")
    _limit(request, "captions-render", 6)
    _quota(request, "captions-render", s.captions_renders_per_hour, 3600,
           "You've made a lot of videos this hour. Please wait a little and try again.")
    extras = assmod.Extras(hook=(body.hook or "").strip() or None, hook_seconds=body.hook_seconds, hook_y=body.hook_y,
                           hook_color=body.hook_color, hook_bg=body.hook_bg, progress_bar=body.progress_bar,
                           progress_color=body.progress_color,
                           watermark=s.captions_watermark if body.watermark else None, mode=body.mode)
    logo = None
    if body.logo is not None and job.logo is not None and job.logo.exists():
        logo = render.Logo(path=job.logo, corner=body.logo.corner, scale=body.logo.scale, opacity=body.logo.opacity)
    spec = jobs.RenderSpec(style=body.style, extras=extras, quality=body.quality, remove_fillers=body.remove_fillers,
                           remove_silences=body.remove_silences, logo=logo)
    return _submit(job, "render", {"spec": spec})


@router.put("/api/captions/jobs/{jid}/logo")
async def logo_upload(jid: str, request: Request):
    job = _owned(jid, request)
    _limit(request, "captions-logo", 10)
    data = await request.body()
    if not data or len(data) > 3 * 1024 * 1024:
        raise HTTPException(413, "Please use an image under 3 MB.")
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_UNCHANGED)
    if img is None or img.ndim < 2 or min(img.shape[:2]) < 8:
        raise HTTPException(422, "Please use a PNG, JPG or WebP image.")
    if max(img.shape[:2]) > 1200:
        f = 1200 / max(img.shape[:2])
        img = cv2.resize(img, None, fx=f, fy=f, interpolation=cv2.INTER_AREA)
    path = job.dir / "logo.png"
    cv2.imwrite(str(path), img)
    job.logo = path
    return job.public(jobs.position(job))


@router.delete("/api/captions/jobs/{jid}/logo")
async def logo_delete(jid: str, request: Request):
    job = _owned(jid, request)
    if job.logo:
        job.logo.unlink(missing_ok=True)
    job.logo = None
    return job.public(jobs.position(job))


@router.delete("/api/captions/jobs/{jid}")
async def job_cancel(jid: str, request: Request, remove: bool = False):
    job = _owned(jid, request)
    if remove:
        jobs.delete(job)
        return {"ok": True}
    jobs.cancel(job)
    return job.public(jobs.position(job))


@router.api_route("/api/captions/jobs/{jid}/file/{kind}", methods=["GET", "HEAD"])
async def job_file(jid: str, kind: str, request: Request, inline: bool = False,
                   mode: Literal["original", "translation", "dual"] = "original"):
    job = _job(jid)
    if kind == "video":
        if job.output is None or not job.output.path.exists():
            raise HTTPException(404, "This video isn't ready yet.")
        return serve_path(request, job.output.path, job.output.name, "video/mp4", inline)
    if kind not in ("srt", "vtt", "txt"):
        raise HTTPException(404)
    try:
        text, name = jobs.export(job, kind, mode)
    except jobs.JobError as e:
        raise HTTPException(e.status, e.message) from e
    ctype = {"srt": "application/x-subrip", "vtt": "text/vtt", "txt": "text/plain"}[kind] + "; charset=utf-8"
    return Response(("﻿" if kind == "srt" else "") + text, media_type=ctype,
                    headers={"Content-Disposition": _disposition(name, inline), "Cache-Control": "no-store"})


@router.api_route("/api/captions/jobs/{jid}/source", methods=["GET", "HEAD"])
async def job_source(jid: str, request: Request):
    job = _job(jid)
    if job.src_path is None or not Path(job.src_path).exists():
        raise HTTPException(404, "The original video isn't available.")
    ctype = "video/webm" if str(job.src_path).endswith(".webm") else "video/mp4"
    return serve_path(request, Path(job.src_path), "source.mp4", ctype, True)
