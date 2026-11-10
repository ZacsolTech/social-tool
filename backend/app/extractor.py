"""Resolve a social link into a clean list of download options using yt-dlp."""

from __future__ import annotations

import logging
import re
import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import yt_dlp
from yt_dlp.utils import DownloadError, ExtractorError

from . import fallback
from .config import Settings, get_settings
from .platforms import Platform

log = logging.getLogger("uvicorn.error")


class ResolveError(Exception):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.message = message
        self.status = status


@dataclass
class Option:
    id: str
    label: str
    kind: str                     # "video" | "audio" | "image"
    ext: str                      # extension of the file the user receives
    formats: list[str]            # yt-dlp format ids to fetch (1 = single file, 2 = video+audio merge)
    transcode: str | None = None  # "mp3" = convert audio, "remux" = pack an HLS/DASH stream into MP4,
                                  # "h264" = re-encode video to H.264 + AAC (Facebook VP9/AV1)
    image_url: str | None = None  # for kind == "image"
    quality: int = 0              # short side in px (video) or kbps (audio)
    size: int | None = None       # bytes (estimate)
    note: str | None = None
    has_audio: bool = True
    best: bool = False
    rank: int = 0                 # internal: yt-dlp order, worst -> best

    @property
    def direct(self) -> bool:
        """Single file, no processing: relayed byte-for-byte (resumable, multi-connection)."""
        return len(self.formats) == 1 and self.transcode is None

    def public(self) -> dict[str, Any]:
        return {
            "id": self.id, "label": self.label, "kind": self.kind, "ext": self.ext,
            "quality": self.quality, "size": self.size, "note": self.note,
            "has_audio": self.has_audio, "best": self.best,
            # MP3 / ffmpeg fallbacks take a few seconds before bytes flow; the UI says so.
            "instant": self.kind == "image" or self.direct or (len(self.formats) == 2 and self.transcode is None),
            # Converted by ffmpeg: the page prepares the file first (POST /api/prepare), then downloads it.
            "prepare": self.transcode is not None,
        }


@dataclass
class Item:
    index: int
    title: str
    duration: float | None
    thumbnail: str | None
    width: int | None
    height: int | None
    info: dict[str, Any]
    options: list[Option] = field(default_factory=list)
    error: str | None = None

    def format(self, format_id: str) -> dict[str, Any] | None:
        return next((f for f in self.info.get("formats") or [self.info] if f.get("format_id") == format_id), None)


@dataclass
class Resolved:
    token: str
    platform: Platform
    url: str
    title: str
    uploader: str | None
    webpage_url: str
    items: list[Item]
    created: float
    http_headers: dict[str, str]
    # The yt-dlp session that extracted this link. Kept open so downloads reuse its
    # cookies (TikTok/Instagram media URLs need them) and network settings.
    ydl: Any = None
    lock: threading.Lock = field(default_factory=threading.Lock)
    active: int = 0               # downloads streaming right now (don't expire mid-download)
    vmux: dict = field(default_factory=dict)   # (item, option) -> planned virtual MP4 (or None)
    source: str = "ytdlp"         # "ytdlp" or "api" (fallback.py): decides how expired URLs are refreshed

    def item(self, index: int) -> Item:
        if not 0 <= index < len(self.items):
            raise ResolveError("Item not found", 404)
        return self.items[index]

    def close(self) -> None:
        if self.ydl is not None:
            try:
                self.ydl.close()
            except Exception:  # noqa: BLE001
                pass
            self.ydl = None


def ydl_params(settings: Settings, **extra: Any) -> dict[str, Any]:
    params: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "socket_timeout": 15,
        "retries": 3,
        "extractor_retries": 0,      # resolve() retries network errors itself, within a time budget
        "playlistend": 12,            # carousels / multi-video posts, but never whole profiles
        "noplaylist": False,
        # Node is installed on this machine; deno is yt-dlp's default if present.
        "js_runtimes": {"deno": {}, "node": {}},
        # yt-dlp caches YouTube player code; keep it inside the project (D:), not in the user profile.
        "cachedir": str(settings.ytdlp_cache_dir),
    }
    if settings.ffmpeg_location:
        params["ffmpeg_location"] = settings.ffmpeg_location
    if settings.proxy:
        params["proxy"] = settings.proxy
    if settings.cookies_file:
        params["cookiefile"] = str(settings.cookies_file)
    params.update(extra)
    return params


# ---------------------------------------------------------------- errors

_FRIENDLY = [
    # YouTube's bot check on data-centre IPs (Railway etc.). Its text also says "sign in" and
    # "cookies", so it must be matched before the "private" rule or users see a wrong reason.
    (r"not a bot|confirm you.?re not|bot detection",
     "YouTube is blocking our server right now. Please try again later."),
    # Instagram's login wall for data-centre IPs ("redirected to the login page ... rate-limit").
    (r"redirected to the login page|rate.?limit (reached|for accessing)|exceeded the rate.?limit",
     "Instagram is limiting our server right now. Please try again in a few minutes."),
    (r"private|login required|log in|sign in|authenticat|cookies", "This post is private or needs a login. Only public posts can be downloaded."),
    (r"no video|There is no video", "This post has no video in it (it may be photos only)."),
    (r"not available in your country|geo.?restrict", "This video is blocked in the server's region."),
    (r"removed|deleted|does not exist|not found|404|unavailable", "This video is unavailable. It may have been deleted."),
    (r"unsupported url", "This link is not a video page. Copy the link of the post itself."),
    (r"rate.?limit|429|too many requests", "The platform is limiting requests right now. Please try again in a minute."),
    (r"HTTP Error 403|ip address is blocked", "The platform is blocking our server right now. Please try again in a minute."),
    (r"timed out|timeout|connection|transport|failed to perform|universal data|rehydration",
     "We couldn't reach the platform just now. Please try again in a few seconds."),
]


def friendly_error(exc: Exception) -> str:
    msg = str(exc)
    for pattern, text in _FRIENDLY:
        if re.search(pattern, msg, re.I):
            return text
    return "We couldn't read this link. Check that the post is public and try again."


# ---------------------------------------------------------------- options


def _short_side(f: dict[str, Any]) -> int:
    w, h = f.get("width"), f.get("height")
    if w and h:
        return min(w, h)
    return h or 0


_VIDEO_EXTS = {"mp4", "webm", "mov", "mkv", "flv", "3gp", "m4v", "ts"}


def _has_video(f: dict[str, Any]) -> bool:
    vc = f.get("vcodec")
    if vc == "none":
        return False
    if vc or f.get("height") or f.get("width"):
        return True
    # Facebook/X often give plain "hd"/"sd" MP4 links with no codec metadata.
    return f.get("ext") in _VIDEO_EXTS or str(f.get("protocol", "")).startswith("m3u8")


def _has_audio(f: dict[str, Any]) -> bool:
    ac = f.get("acodec")
    if ac == "none":
        return False
    if ac:
        return True
    # Unknown codec info: a format with no video info is probably audio,
    # and most direct MP4s from social sites are muxed.
    return f.get("vcodec") != "none" or not _has_video(f)


def _size(f: dict[str, Any], duration: float | None) -> int | None:
    s = f.get("filesize") or f.get("filesize_approx")
    if s:
        return int(s)
    if f.get("tbr") and duration:
        return int(f["tbr"] * 1000 / 8 * duration)
    return None


def _is_watermarked(f: dict[str, Any]) -> bool:
    text = f"{f.get('format_note') or ''} {f.get('format_id') or ''}".lower()
    return "watermark" in text


def _quality_label(px: int) -> str:
    for std in (2160, 1440, 1080, 720, 540, 480, 360, 240, 144):
        if px >= std * 0.9:
            return {2160: "4K", 1440: "2K"}.get(std, f"{std}p")
    return f"{px}p" if px else "SD"


def _usable(f: dict[str, Any]) -> bool:
    if f.get("ext") in ("mhtml", "json") or "storyboard" in (f.get("format_note") or "").lower():
        return False
    # YouTube "-sr" = AI super-resolution upscale; "-drc" audio handled by _audio_score.
    if str(f.get("format_id") or "").endswith("-sr"):
        return False
    if f.get("protocol") in ("http_dash_segments", "f4m", "ism", "mhtml", "rtmp", "rtsp"):
        return False  # fragment lists we can't stream; every platform also offers plain/HLS files
    return bool(f.get("url") or f.get("fragments") or f.get("manifest_url"))


def _is_plain_http(f: dict[str, Any]) -> bool:
    """One plain file at one URL (can be relayed as-is), as opposed to HLS/DASH fragments."""
    return f.get("protocol") in ("http", "https", None) and bool(f.get("url")) and not f.get("fragments")


def _audio_score(f: dict[str, Any]) -> tuple:
    note = f"{f.get('format_id') or ''} {f.get('format_note') or ''}".lower()
    return (
        (f.get("ext") == "m4a") or str(f.get("acodec") or "").startswith("mp4a"),  # AAC plays in every MP4 player
        "drc" not in note,                            # YouTube: skip dynamic-range-compressed copies
        (f.get("audio_channels") or 2) <= 2,          # stereo over 5.1 (phones, social re-uploads)
        f.get("language_preference") or 0,            # YouTube: original-language track first
        f.get("abr") or f.get("tbr") or 0,
    )


def _is_h264(f: dict[str, Any]) -> bool:
    return str(f.get("vcodec") or "").startswith(("avc", "h264"))


def build_options(info: dict[str, Any], max_bytes: int | None = None, platform_id: str | None = None) -> list[Option]:
    duration = info.get("duration")
    # Facebook serves VP9/AV1 video (stutters and drifts out of sync in many players) and its
    # plain "hd"/"sd" files often have no audio track despite giving no codec info.
    facebook = platform_id == "facebook"
    formats = [f for f in (info.get("formats") or [info]) if _usable(f)]

    clean = [f for f in formats if not _is_watermarked(f)]
    if clean:  # TikTok: always prefer the no-watermark files
        formats = clean

    audio_only = [f for f in formats if _has_audio(f) and not _has_video(f)]
    best_audio = max(audio_only, key=_audio_score) if audio_only else None

    # one best candidate per quality bucket
    buckets: dict[str, dict[str, Any]] = {}
    for rank, f in enumerate(formats):   # yt-dlp lists formats worst -> best
        if not _has_video(f):
            continue
        px = _short_side(f)
        if px:
            label = _quality_label(px)
        else:
            fid = str(f.get("format_id") or "")
            label = {"hd": "HD", "sd": "SD"}.get(fid.lower(), (f.get("format_note") or fid or "Video")[:12])
        score = (
            _has_audio(f) or best_audio is not None,                 # must end up with sound
            str(f.get("vcodec") or "").startswith(("avc", "h264")),  # plays everywhere
            f.get("ext") == "mp4",                                   # MP4 DASH -> instant, resumable merge
            _is_plain_http(f),                                       # plain file beats HLS: faster, exact size
            _has_audio(f),                                           # single file = instant, resumable
            f.get("tbr") or 0,
            px,
            rank,
        )
        cur = buckets.get(label)
        if cur is None or score > cur["score"]:
            buckets[label] = {"f": f, "score": score, "px": px, "rank": rank}

    options: list[Option] = []
    for label, b in buckets.items():
        f = b["f"]
        muxed = _has_audio(f)
        if facebook and best_audio is not None and f.get("acodec") is None:
            muxed = False   # unknown audio: add the DASH audio track rather than risk a silent file
        transcode = None
        if muxed or best_audio is None:
            ids = [f["format_id"]]
            size = _size(f, duration)
            has_audio = muxed
            if _is_plain_http(f):
                # A single progressive file keeps its own container (almost always mp4).
                ext = f.get("ext") if f.get("ext") in ("mp4", "webm", "mov", "m4v") else "mp4"
            else:
                ext, transcode = "mp4", "remux"   # HLS/DASH stream -> ffmpeg packs it into one MP4
        else:
            ids = [f["format_id"], best_audio["format_id"]]
            vs, as_ = _size(f, duration), _size(best_audio, duration)
            size = vs + (as_ or 0) if vs else None   # unknown video size: show none, not just the audio's
            has_audio, ext = True, "mp4"
        if facebook and not _is_h264(f):
            transcode = "h264"   # re-encode to H.264 + AAC-LC: plays smoothly and in sync everywhere
        if max_bytes and size and size > max_bytes:
            continue  # e.g. YouTube 4K: over the server file-size limit
        options.append(Option(
            id="v" + (str(b["px"]) if b["px"] else re.sub(r"\W", "", label.lower()) or str(b["rank"])),
            label=label, kind="video", ext=ext, formats=ids, transcode=transcode,
            quality=b["px"], size=size, has_audio=has_audio, rank=b["rank"],
            note=None if has_audio else "No sound",
        ))
    options.sort(key=lambda o: (o.has_audio, o.quality, o.rank), reverse=True)
    if options:
        # "Best" = sharpest version up to 1080p: 4K/2K files are huge and most phones can't show them.
        best = next((o for o in options if o.has_audio and o.quality <= 1080), options[0])
        best.best = True
        options.remove(best)
        options.insert(0, best)

    # Audio: from the best audio-only stream, or from the smallest muxed file.
    audio_src = best_audio
    if audio_src is None:
        muxed = [f for f in formats if _has_audio(f)]
        audio_src = min(muxed, key=lambda f: _size(f, duration) or 1 << 60) if muxed else None
    if audio_src is not None:
        options.append(Option(
            id="mp3", label="MP3", kind="audio", ext="mp3", formats=[audio_src["format_id"]], transcode="mp3",
            quality=192, size=int(192_000 / 8 * duration) if duration else None, note="192 kbps",
        ))
        if best_audio is not None and best_audio.get("ext") == "m4a" and _is_plain_http(best_audio):
            options.append(Option(
                id="m4a", label="M4A", kind="audio", ext="m4a", formats=[best_audio["format_id"]],
                quality=int(best_audio.get("abr") or 0), size=_size(best_audio, duration), note="Original quality",
            ))

    thumb = info.get("thumbnail")
    if thumb:
        options.append(Option(
            id="thumb", label="Cover", kind="image", ext="jpg", formats=[], image_url=thumb, note="Thumbnail",
        ))
    return options


# ---------------------------------------------------------------- resolve


def _make_item(i: int, e: dict[str, Any], settings: Settings, platform_id: str | None = None) -> Item:
    item = Item(
        index=i,
        title=e.get("title") or e.get("description") or f"Video {i + 1}",
        duration=e.get("duration"),
        thumbnail=e.get("thumbnail"),
        width=e.get("width"),
        height=e.get("height"),
        info=e,
    )
    if item.duration and item.duration > settings.max_duration_sec:
        item.error = f"Too long (max {settings.max_duration_sec // 60} min)."
    else:
        item.options = build_options(e, settings.max_filesize_mb * 1024 * 1024, platform_id)
        if not item.options:
            item.error = "No downloadable formats found."
    return item


_NET_RETRIES = 5
_NET_BUDGET = 25   # seconds of retrying; keeps the whole request under hosts' 60 s idle cutoff (Railway)
_NET_ERR = re.compile(
    r"connection (was )?reset|forcibly closed|connection aborted|timed out|recv failure|"
    r"failed to perform|ssl|universal data|rehydration|remote end closed",
    re.I,
)


# yt-dlp errors that mean "the platform is blocking this server", not "this post is gone".
# These switch to the fallback API (fallback.py).
_BLOCKED_ERR = re.compile(
    r"not a bot|sign in|log ?in|cookies|rate.?limit|429|403|blocked|private|"
    r"empty media response|unable to extract|requested content is not available",
    re.I,
)
_API_FIRST_SEC = 10 * 60
_api_first_until: dict[str, float] = {}   # platform id -> monotonic time: skip yt-dlp until then


def _api_fetch(url: str, platform: Platform, settings: Settings) -> dict[str, Any] | None:
    try:
        info = fallback.fetch(url, platform.id, settings)
        log.info("resolved via fallback API: %s", url)
        return info
    except fallback.FallbackError as e:
        log.warning("fallback API failed for %s: %s", url, e)
        return None


def _ytdlp_extract(ydl: Any, url: str) -> dict[str, Any]:
    deadline = time.monotonic() + _NET_BUDGET
    for attempt in range(_NET_RETRIES):
        try:
            return ydl.sanitize_info(ydl.extract_info(url, download=False))
        except (DownloadError, ExtractorError) as exc:
            # Connection resets / timeouts come in short bursts on some networks (seen with
            # TikTok): retry a few times before giving up. Real errors (private, deleted) don't retry.
            if attempt == _NET_RETRIES - 1 or not _NET_ERR.search(str(exc)) or time.monotonic() > deadline:
                raise
            log.info("resolve retry %d for %s: %s", attempt + 1, url, str(exc)[:120])
            time.sleep(1.0)
    raise AssertionError("unreachable")


def resolve(url: str, platform: Platform, settings: Settings) -> Resolved:
    # YouTube "watch?v=…&list=…" links: just the video, not the whole playlist.
    # The session is kept even when the API extracts: downloads are relayed through it.
    ydl = yt_dlp.YoutubeDL(ydl_params(settings, noplaylist=platform.id == "youtube"))
    use_api = fallback.available(platform.id, settings)
    info, source = None, "ytdlp"
    try:
        # yt-dlp was blocked recently on this platform: go straight to the API (saves ~5 s per link).
        if use_api and _api_first_until.get(platform.id, 0) > time.monotonic():
            info = _api_fetch(url, platform, settings)
            source = "api"
        if info is None:
            try:
                info, source = _ytdlp_extract(ydl, url), "ytdlp"
            except (DownloadError, ExtractorError) as exc:
                log.warning("resolve failed for %s: %s", url, exc)
                if use_api and source != "api" and _BLOCKED_ERR.search(str(exc)):
                    _api_first_until[platform.id] = time.monotonic() + _API_FIRST_SEC
                    info, source = _api_fetch(url, platform, settings), "api"
                if info is None:
                    raise ResolveError(friendly_error(exc)) from exc
    except BaseException:
        ydl.close()
        raise

    if not info:
        ydl.close()
        raise ResolveError("Nothing to download was found at this link.")

    entries = (
        [e for e in info.get("entries") or [] if e]
        if info.get("_type") in ("playlist", "multi_video")
        else [info]
    )
    if not entries:
        ydl.close()
        raise ResolveError("Nothing to download was found at this link.")

    first = entries[0]
    return Resolved(
        token=secrets.token_urlsafe(12),
        platform=platform,
        url=url,
        title=info.get("title") or first.get("title") or platform.name + " video",
        uploader=info.get("uploader") or info.get("channel") or first.get("uploader"),
        webpage_url=info.get("webpage_url") or url,
        items=[_make_item(i, e, settings, platform.id) for i, e in enumerate(entries)],
        created=time.time(),
        http_headers=dict(first.get("http_headers") or {}),
        ydl=ydl,
        source=source,
    )


def refresh_item(resolved: Resolved, index: int) -> None:
    """Media URLs expire (TikTok within minutes). Re-extract one item, keeping option ids stable."""
    item = resolved.item(index)
    page = item.info.get("webpage_url") or resolved.webpage_url
    with resolved.lock:
        if resolved.source == "api":
            info = fallback.fetch(resolved.url, resolved.platform.id, get_settings())
        else:
            info = resolved.ydl.sanitize_info(resolved.ydl.extract_info(page, download=False))
    if info.get("_type") in ("playlist", "multi_video"):
        entries = [e for e in info.get("entries") or [] if e]
        info = entries[index] if index < len(entries) else entries[0]
    item.info = info


def safe_filename(title: str, suffix: str, ext: str) -> str:
    base = re.sub(r"[^\w\s-]", "", title, flags=re.UNICODE).strip()
    base = re.sub(r"[\s_-]+", "-", base)[:60].strip("-") or "video"
    return f"{base}-{suffix}.{ext}"
