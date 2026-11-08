"""Klyprima API - Phase 1: social video downloader."""

from __future__ import annotations

import asyncio
import html
import json
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import quote

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, Field
from starlette.background import BackgroundTask

from . import platforms
from .config import get_settings
from .extractor import Option, Resolved, ResolveError, resolve, safe_filename
from . import vmux
from .stream import RELAY_KEY, StreamError, _parse_range, open_ffmpeg, open_relay

settings = get_settings()
cache: dict[str, Resolved] = {}


async def _janitor() -> None:
    while True:
        await asyncio.sleep(60)
        _prune_cache()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.http = httpx.AsyncClient(follow_redirects=True, timeout=30)
    janitor = asyncio.create_task(_janitor())
    yield
    janitor.cancel()
    for r in cache.values():
        r.close()
    await app.state.http.aclose()


app = FastAPI(title="Klyprima API", version="0.2.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST", "HEAD"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------- helpers

_hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)


def _client_ip(request: Request) -> str:
    return request.headers.get("x-forwarded-for", "").split(",")[0].strip() or (
        request.client.host if request.client else "?"
    )


def rate_limit(request: Request, bucket: str, per_min: int) -> None:
    q = _hits[(bucket, _client_ip(request))]
    now = time.monotonic()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= per_min:
        raise HTTPException(429, "Too many requests. Please wait a minute and try again.")
    q.append(now)


def _prune_cache() -> None:
    now = time.time()
    for k, v in list(cache.items()):
        if now - v.created > settings.info_ttl_sec and v.active == 0:
            cache.pop(k, None)
            v.close()


def _get_resolved(token: str) -> Resolved:
    r = cache.get(token)
    if not r or time.time() - r.created > settings.info_ttl_sec:
        raise HTTPException(410, "This link has expired. Please paste it again.")
    return r


def _is_blocked(url: str) -> bool:
    """DMCA blocklist, re-read on every request so takedowns apply without a restart."""
    try:
        lines = settings.blocklist_file.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return False
    u = url.lower()
    return any(entry and not entry.startswith("#") and entry in u for entry in (line.strip().lower() for line in lines))


async def _tracked(r: Resolved, body: AsyncIterator[bytes]) -> AsyncIterator[bytes]:
    """Keeps the link's yt-dlp session alive while bytes are flowing."""
    r.active += 1
    try:
        async for chunk in body:
            yield chunk
    finally:
        r.active -= 1
        await body.aclose()


def _disposition(name: str) -> str:
    ascii_name = name.encode("ascii", "ignore").decode() or "download"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}"


def _error_page(message: str, rid: str | None, status: int) -> HTMLResponse:
    """Downloads start in a hidden iframe. On failure this page tells the parent window,
    so the site shows the error on the button instead of the browser saving a broken file."""
    payload = json.dumps({"type": "cf-download-error", "rid": rid, "message": message})
    body = f"""<!doctype html><meta charset="utf-8"><title>Download problem</title>
<body style="font-family:system-ui;padding:2rem;max-width:32rem;margin:auto">
<h1 style="font-size:1.2rem">Download problem</h1><p>{html.escape(message)}</p><p><a href="/">Back to Klyprima</a></p>
<script>try{{parent!==window&&parent.postMessage({payload},location.origin)}}catch(e){{}}</script>"""
    return HTMLResponse(body, status_code=status)


# ---------------------------------------------------------------- schemas


class ResolveIn(BaseModel):
    url: str = Field(min_length=8, max_length=2048)


# ---------------------------------------------------------------- routes


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"ok": True, "cached": len(cache)}


@app.get("/api/platforms")
async def list_platforms() -> list[dict[str, Any]]:
    return [{"id": p.id, "name": p.name, "domains": p.domains} for p in platforms.enabled(settings.enable_youtube)]


@app.post("/api/resolve")
async def resolve_link(body: ResolveIn, request: Request) -> dict[str, Any]:
    url = body.url.strip()
    platform = platforms.detect(url, settings.enable_youtube)
    if platform is None:
        if platforms.detect(url, True) is not None:
            raise HTTPException(422, "YouTube downloads are turned off on this server.")
        raise HTTPException(422, "This site isn't supported. Try a YouTube, TikTok, Instagram, Facebook, X, Reddit or Pinterest link.")
    rate_limit(request, "resolve", settings.resolve_rate_per_min)
    if _is_blocked(url):
        raise HTTPException(451, "This content can't be downloaded here because of a copyright request.")
    try:
        r = await asyncio.to_thread(resolve, url, platform, settings)
    except ResolveError as exc:
        raise HTTPException(exc.status, exc.message) from exc
    _prune_cache()
    cache[r.token] = r
    return {
        "token": r.token,
        "platform": {"id": platform.id, "name": platform.name},
        "title": r.title,
        "uploader": r.uploader,
        "webpage_url": r.webpage_url,
        "items": [
            {
                "index": it.index,
                "title": it.title,
                "duration": it.duration,
                "width": it.width,
                "height": it.height,
                "thumbnail": f"/api/thumb/{r.token}/{it.index}" if it.thumbnail else None,
                "error": it.error,
                "options": [o.public() for o in it.options],
                "download_base": f"/api/download/{r.token}/{it.index}",
                # YouTube: media URLs only work after a short wait; the UI counts down (seconds, not a clock
                # time, so the visitor's clock doesn't matter).
                "ready_in": max(0.0, max((f.get("available_at") or 0) for f in it.info.get("formats") or [it.info]) - time.time()),
            }
            for it in r.items
        ],
    }


async def _fetch_image(request: Request, r: Resolved, url: str) -> httpx.Response:
    client: httpx.AsyncClient = request.app.state.http
    req = client.build_request("GET", url, headers={"User-Agent": r.http_headers.get("User-Agent", "Mozilla/5.0")})
    resp = await client.send(req, stream=True)
    if resp.status_code >= 400:
        await resp.aclose()
        raise StreamError("The platform refused the image. Please paste the link again.")
    return resp


@app.get("/api/thumb/{token}/{index}")
async def thumbnail(token: str, index: int, request: Request):
    """Thumbnail proxy: TikTok/Instagram block hot-linking, so the browser can't load them directly."""
    r = _get_resolved(token)
    item = r.item(index)
    if not item.thumbnail:
        raise HTTPException(404)
    try:
        resp = await _fetch_image(request, r, item.thumbnail)
    except StreamError as e:
        raise HTTPException(502, e.message) from e
    return StreamingResponse(
        resp.aiter_bytes(), media_type=resp.headers.get("content-type", "image/jpeg"),
        headers={"Cache-Control": "private, max-age=900"},
        background=BackgroundTask(resp.aclose),
    )


@app.api_route("/api/download/{token}/{index}/{option}", methods=["GET", "HEAD"])
async def download(token: str, index: int, option: str, request: Request, rid: str | None = None):
    """The one download URL the browser (or IDM) opens. Always a real file response or an error page."""
    try:
        r = _get_resolved(token)
        item = r.item(index)
    except (HTTPException, ResolveError):
        return _error_page("This link has expired. Please paste it again.", rid, 410)
    opt: Option | None = next((o for o in item.options if o.id == option), None)
    if opt is None:
        return _error_page("That quality option is not available.", rid, 404)

    title = item.title or r.title
    is_head = request.method == "HEAD"
    try:
        rate_limit(request, "download", settings.jobs_rate_per_min * 4)  # IDM opens several connections
    except HTTPException as e:
        return _error_page(e.detail, rid, 429)

    try:
        if opt.kind == "image":
            resp = await _fetch_image(request, r, opt.image_url or "")
            ctype = resp.headers.get("content-type", "image/jpeg")
            ext = "png" if "png" in ctype else "webp" if "webp" in ctype else "jpg"
            headers = {"Content-Disposition": _disposition(safe_filename(f"{r.platform.name} {title}", "cover", ext))}
            if resp.headers.get("content-length"):
                headers["Content-Length"] = resp.headers["content-length"]
            if is_head:
                await resp.aclose()
                return Response(status_code=200, media_type=ctype, headers=headers)
            return StreamingResponse(resp.aiter_bytes(), media_type=ctype, headers=headers, background=BackgroundTask(resp.aclose))

        name = safe_filename(f"{r.platform.name} {title}", opt.label.lower().replace(" ", ""), opt.ext)
        if opt.direct:
            up = await open_relay(r, item, opt.formats[0], request.headers.get("range"))
        elif len(opt.formats) == 2 and opt.transcode is None:
            # Video + audio: virtual MP4 with exact size and Range support (resume, IDM multi-connection).
            vm = await _virtual_mp4(r, item, opt)
            if vm is not None:
                return _serve_virtual(request, r, item, vm, name, is_head)
            if is_head:
                return Response(status_code=200, media_type="video/mp4", headers={"Content-Disposition": _disposition(name), "Accept-Ranges": "none"})
            up = await open_ffmpeg(r, item, opt, settings)
        else:
            if is_head:  # don't start ffmpeg just to answer a HEAD
                ctype = "audio/mpeg" if opt.transcode == "mp3" else "video/mp4"
                return Response(status_code=200, media_type=ctype, headers={"Content-Disposition": _disposition(name), "Accept-Ranges": "none"})
            up = await open_ffmpeg(r, item, opt, settings)
    except StreamError as e:
        return _error_page(e.message, rid, e.status)

    headers = {**up.headers, "Content-Disposition": _disposition(name), "Cache-Control": "no-store"}
    if opt.transcode is None and opt.ext in ("mp4", "m4a", "webm"):
        headers["Content-Type"] = {"mp4": "video/mp4", "m4a": "audio/mp4", "webm": "video/webm"}[opt.ext]
    if is_head:
        await up.body.aclose()
        return Response(status_code=up.status, headers=headers)
    return StreamingResponse(_tracked(r, up.body), status_code=up.status, headers=headers)


async def _virtual_mp4(r: Resolved, item, opt: Option) -> vmux.VirtualMp4 | None:
    """Plan (once per link + option) the combined MP4; None if the inputs can't be muxed virtually."""
    key = (item.index, opt.id)
    if key not in r.vmux:
        try:
            r.vmux[key] = await vmux.build(r, item, opt.formats[0], opt.formats[1])
        except vmux.NotMuxable:
            r.vmux[key] = None
    return r.vmux[key]


def _serve_virtual(request: Request, r: Resolved, item, vm: vmux.VirtualMp4, name: str, is_head: bool) -> Response:
    rng = _parse_range(request.headers.get("range"))
    start, end, status = 0, vm.total - 1, 200
    if rng:
        start = rng[0]
        end = min(rng[1], vm.total - 1) if rng[1] is not None else vm.total - 1
        if start >= vm.total or start > end:
            return Response(status_code=416, headers={"Content-Range": f"bytes */{vm.total}"})
        status = 206
    headers = {
        "Content-Disposition": _disposition(name),
        "Accept-Ranges": "bytes",
        "Content-Length": str(end - start + 1),
        "Cache-Control": "no-store",
    }
    if status == 206:
        headers["Content-Range"] = f"bytes {start}-{end}/{vm.total}"
    if is_head:
        return Response(status_code=status, media_type="video/mp4", headers=headers)
    body = vmux.stream_range(r, item, vm, start, end)
    return StreamingResponse(_tracked(r, body), status_code=status, media_type="video/mp4", headers=headers)


@app.get("/api/raw/{token}/{index}/{format_id}")
async def raw(token: str, index: int, format_id: str, request: Request, key: str = ""):
    """Internal relay used by ffmpeg (adds cookies, impersonation, chunked YouTube requests)."""
    if key != RELAY_KEY:
        raise HTTPException(404)
    r = _get_resolved(token)
    item = r.item(index)
    try:
        up = await open_relay(r, item, format_id, request.headers.get("range"))
    except StreamError as e:
        raise HTTPException(e.status, e.message) from e
    return StreamingResponse(_tracked(r, up.body), status_code=up.status, headers=up.headers)
