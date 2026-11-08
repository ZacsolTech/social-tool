"""Fallback extractor: a paid API used when yt-dlp is blocked on the server's IP.

Data-centre IPs (Railway, AWS, ...) get YouTube's "confirm you're not a bot" check and
Instagram's login wall. The RapidAPI "Social Media Video Downloader" API extracts the
video on its own network and returns media links that work from anywhere. Its answer is
turned into a yt-dlp style info dict, so options, virtual MP4 merging, MP3 and resumable
downloads work exactly as with yt-dlp.

Costs 1 API credit per call, so it only runs when yt-dlp fails (see extractor.resolve).
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from .config import Settings

log = logging.getLogger("uvicorn.error")

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
TIMEOUT = 30

_YT_ID = re.compile(r"(?:[?&]v=|youtu\.be/|/shorts/|/live/|/embed/|/v/)([\w-]{11})")
_IG_CODE = re.compile(r"(?:instagram\.com|instagr\.am)/(?:[\w.]+/)?(?:p|reels?|tv)/([\w-]+)")


class FallbackError(Exception):
    pass


def available(platform_id: str, settings: Settings) -> bool:
    return bool(settings.rapidapi_key) and platform_id in ("youtube", "instagram")


def _call(path: str, params: dict[str, str], settings: Settings) -> dict[str, Any]:
    host = settings.rapidapi_host
    try:
        r = httpx.get(f"https://{host}{path}", params=params, timeout=TIMEOUT,
                      headers={"x-rapidapi-key": settings.rapidapi_key or "", "x-rapidapi-host": host})
    except httpx.HTTPError as e:
        raise FallbackError(f"API unreachable: {e}") from e
    if r.status_code != 200:
        key = settings.rapidapi_key or ""
        # Key fingerprint (never the key itself) so a wrong/old key is easy to spot in host logs.
        raise FallbackError(f"API HTTP {r.status_code}: {r.text[:200]} (key ...{key[-4:]}, {len(key)} chars)")
    data = r.json()
    if data.get("error"):
        err = data["error"]
        raise FallbackError(err.get("message") if isinstance(err, dict) else str(err))
    if not data.get("contents"):
        raise FallbackError("API returned no media")
    return data


# ---------------------------------------------------------------- format mapping


def _mime(md: dict[str, Any]) -> tuple[str, str | None]:
    """'video/mp4; codecs="avc1.4D401F"' -> ('video/mp4', 'avc1.4D401F')."""
    raw = md.get("mime_type") or ""
    mime = raw.split(";")[0].strip().lower()
    m = re.search(r'codecs="?([^";]+)', raw)
    return mime, (m.group(1) if m else md.get("codecs"))


_EXT = {"video/mp4": "mp4", "audio/mp4": "m4a", "video/webm": "webm", "audio/webm": "webm"}


def _format(f: dict[str, Any], fid: str, is_audio: bool, chunked: bool, post_has_audio: bool | None) -> dict[str, Any] | None:
    md = f.get("metadata") or {}
    if not f.get("url") or md.get("is_sr"):
        return None
    mime, codecs = _mime(md)
    if is_audio:
        vcodec, acodec = "none", codecs or "mp4a"
    elif codecs and not md.get("has_audio"):
        vcodec, acodec = codecs, "none"           # DASH video-only track
    elif md.get("has_audio"):
        vcodec, acodec = codecs, None              # muxed, codec names unknown
    else:
        # Instagram's progressive MP4 (no codec info): carries the sound, if the post has any.
        # It is H.264 (checked with ffprobe), so it ranks as a "plays everywhere" single file.
        vcodec = codecs or ("avc1" if mime == "video/mp4" else None)
        acodec = "none" if post_has_audio is False else None
    bitrate = md.get("bitrate") or md.get("average_bitrate") or md.get("bandwidth")
    out = {
        "format_id": fid,
        "url": f["url"],
        "ext": _EXT.get(mime, "m4a" if is_audio else "mp4"),
        "protocol": "https",
        "vcodec": vcodec,
        "acodec": acodec,
        "width": md.get("width") if not is_audio else None,
        "height": md.get("height") if not is_audio else None,
        "fps": md.get("fps") or md.get("frame_rate"),
        "filesize": md.get("content_length"),
        "tbr": bitrate / 1000 if bitrate else None,
        "abr": bitrate / 1000 if is_audio and bitrate else None,
        "format_note": f.get("label"),
        "http_headers": {"User-Agent": UA},
    }
    if chunked:  # YouTube throttles single big requests; same as yt-dlp's default for YouTube
        out["downloader_options"] = {"http_chunk_size": 10 * 1024 * 1024}
    return out


def _formats(content: dict[str, Any], prefix: str, chunked: bool, post_has_audio: bool | None) -> list[dict[str, Any]]:
    fmts = []
    for i, f in enumerate(content.get("videos") or []):
        x = _format(f, f"{prefix}v{i}", False, chunked, post_has_audio)
        if x:
            fmts.append(x)
    for i, f in enumerate(content.get("audios") or []):
        x = _format(f, f"{prefix}a{i}", True, chunked, post_has_audio)
        if x:
            fmts.append(x)
    # yt-dlp lists formats worst -> best; build_options relies on that order for ties.
    fmts.reverse()
    return fmts


def _size_fields(formats: list[dict[str, Any]]) -> dict[str, Any]:
    """Top-level width/height (the UI shows the aspect ratio) from the largest video format."""
    vids = [f for f in formats if f.get("width") and f.get("height")]
    if not vids:
        return {}
    best = max(vids, key=lambda f: f["width"] * f["height"])
    return {"width": best["width"], "height": best["height"]}


# ---------------------------------------------------------------- platforms


def _youtube(url: str, settings: Settings) -> dict[str, Any]:
    m = _YT_ID.search(url)
    if not m:
        raise FallbackError("no YouTube video id in link")
    vid = m.group(1)
    data = _call("/youtube/v3/video/details", {"videoId": vid}, settings)
    md = data.get("metadata") or {}
    content = data["contents"][0]
    formats = _formats(content, "", True, None)
    dur_ms = next((f.get("metadata", {}).get("approx_duration_ms") for f in content.get("videos") or []
                   if f.get("metadata", {}).get("approx_duration_ms")), None)
    author = md.get("author") if isinstance(md.get("author"), dict) else {}
    return {
        "id": vid,
        "title": md.get("title") or "YouTube video",
        "uploader": author.get("name"),
        "webpage_url": f"https://www.youtube.com/watch?v={vid}",
        "thumbnail": md.get("thumbnailUrl") or f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
        "duration": int(dur_ms) / 1000 if dur_ms else None,
        "formats": formats,
        "http_headers": {"User-Agent": UA},
        **_size_fields(formats),
    }


def _instagram(url: str, settings: Settings) -> dict[str, Any]:
    m = _IG_CODE.search(url)
    if not m:
        raise FallbackError("no Instagram post code in link")
    code = m.group(1)
    data = _call("/instagram/v3/media/post/details", {"shortcode": code}, settings)
    md = data.get("metadata") or {}
    extra = md.get("additionalData") if isinstance(md.get("additionalData"), dict) else {}
    author = md.get("author") if isinstance(md.get("author"), dict) else {}
    caption = (md.get("title") or "").strip()
    title = caption.splitlines()[0][:100] if caption else f"Instagram post by {author.get('username') or code}"
    page = f"https://www.instagram.com/p/{code}/"

    entries = []
    contents = data["contents"]
    for i, c in enumerate(contents):
        vids = c.get("videos") or []
        imgs = c.get("images") or []
        thumb = next((v.get("metadata", {}).get("thumbnailUrl") for v in vids if v.get("metadata", {}).get("thumbnailUrl")), None)
        if not thumb and imgs:
            thumb = imgs[0].get("url") if isinstance(imgs[0], dict) else imgs[0]
        formats = _formats(c, f"{i}", False, extra.get("has_audio") if len(contents) == 1 else None)
        entries.append({
            "id": f"{code}_{i}",
            "title": title if len(contents) == 1 else f"{title} ({i + 1})",
            "uploader": author.get("username"),
            "webpage_url": page,
            "thumbnail": thumb or md.get("thumbnailUrl"),
            "duration": None,
            "formats": formats,
            "http_headers": {"User-Agent": UA},
            **_size_fields(formats),
        })
    if len(entries) == 1:
        return entries[0]
    return {"_type": "playlist", "id": code, "title": title, "uploader": author.get("username"),
            "webpage_url": page, "entries": entries}


def fetch(url: str, platform_id: str, settings: Settings) -> dict[str, Any]:
    """Extract `url` through the API. Returns a yt-dlp style info dict; raises FallbackError."""
    if platform_id == "youtube":
        return _youtube(url, settings)
    if platform_id == "instagram":
        return _instagram(url, settings)
    raise FallbackError(f"no API fallback for {platform_id}")
