"""Supported platforms. The domain allowlist also protects against SSRF:
we never hand an arbitrary user URL to yt-dlp or httpx."""

from dataclasses import dataclass
from urllib.parse import urlparse


@dataclass(frozen=True)
class Platform:
    id: str
    name: str
    domains: tuple[str, ...]


PLATFORMS: tuple[Platform, ...] = (
    Platform("tiktok", "TikTok", ("tiktok.com", "vm.tiktok.com", "vt.tiktok.com")),
    Platform("instagram", "Instagram", ("instagram.com", "instagr.am")),
    Platform("facebook", "Facebook", ("facebook.com", "fb.watch", "fb.com")),
    Platform("x", "X (Twitter)", ("x.com", "twitter.com")),
    Platform("reddit", "Reddit", ("reddit.com", "redd.it", "v.redd.it")),
    Platform("pinterest", "Pinterest", ("pinterest.com", "pin.it")),
    Platform("dailymotion", "Dailymotion", ("dailymotion.com", "dai.ly")),
    Platform("twitch", "Twitch", ("twitch.tv",)),
    Platform("youtube", "YouTube", ("youtube.com", "youtu.be")),
)


def _host_matches(host: str, domain: str) -> bool:
    return host == domain or host.endswith("." + domain)


def detect(url: str, enable_youtube: bool) -> Platform | None:
    try:
        parsed = urlparse(url.strip())
    except ValueError:
        return None
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return None
    host = parsed.hostname.lower()
    for p in PLATFORMS:
        if p.id == "youtube" and not enable_youtube:
            continue
        # Pinterest has many country TLDs (pinterest.co.uk, pinterest.de, ...)
        if p.id == "pinterest" and (host.startswith("pinterest.") or ".pinterest." in host):
            return p
        if any(_host_matches(host, d) for d in p.domains):
            return p
    return None


def enabled(enable_youtube: bool) -> list[Platform]:
    return [p for p in PLATFORMS if p.id != "youtube" or enable_youtube]
