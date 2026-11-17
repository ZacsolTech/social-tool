import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]   # .../backend (locally) or /app (in Docker)
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = PROJECT_ROOT / ".tmp"                     # D:\...\video downloader\.tmp locally, /.tmp in Docker


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CF_", extra="ignore")

    # YouTube is ON. It is the main AdSense risk (see proposal §6): set CF_ENABLE_YOUTUBE=false
    # to turn it off. yt-dlp needs a JS runtime (deno or node) to solve YouTube challenges.
    enable_youtube: bool = True

    # Limits that keep server costs predictable.
    max_duration_sec: int = 60 * 60          # 1 hour
    max_filesize_mb: int = 1024              # 1 GB
    max_concurrent_jobs: int = 4
    resolve_rate_per_min: int = 20           # per IP
    jobs_rate_per_min: int = 15              # downloads per IP per minute (x4 for multi-connection managers)

    info_ttl_sec: int = 30 * 60              # a pasted link's download buttons stay valid this long
    # How ffmpeg reaches this API from the same machine (MP3 and fallback merges).
    # Follows $PORT, which Railway and most hosts set.
    internal_api: str = f"http://127.0.0.1:{os.environ.get('PORT', '8000')}"
    ytdlp_cache_dir: Path = DATA_DIR / "yt-dlp-cache"

    ffmpeg_location: str | None = None      # None = use ffmpeg from PATH
    proxy: str | None = None                 # e.g. http://user:pass@host:port (residential proxy)
    cookies_file: Path | None = None         # optional Netscape cookies.txt
    # Same thing as text (paste the whole cookies.txt into a host variable such as Railway's).
    cookies_txt: str | None = None
    # Fallback API for when YouTube / Instagram block the server's IP (see app/fallback.py).
    # Empty key = no fallback. 1 credit per call, used only when yt-dlp fails.
    rapidapi_key: str | None = None
    rapidapi_host: str = "social-media-video-downloader.p.rapidapi.com"
    cors_origins: list[str] = ["http://localhost:3000"]
    # One URL (or URL fragment, e.g. a video id) per line. Used for DMCA takedowns.
    blocklist_file: Path = BACKEND_DIR / "blocklist.txt"

    # ---- Reframe tool (landscape -> portrait). See app/reframe/.
    upload_max_mb: int = 1024                # biggest file a visitor can upload
    upload_chunk_mb: int = 4                 # browser sends the file in pieces this size (under proxy body limits)
    reframe_max_duration_sec: int = 30 * 60 # longest video the tool accepts
    reframe_allow_links: bool = True         # "paste a link" / "Make it vertical" from the downloader
    reframe_workers: int = 1                 # videos processed at the same time (CPU heavy: ~1 per 4 vCPU)
    reframe_queue_max: int = 25              # waiting jobs before new ones are refused
    reframe_daily_per_ip: int = 40           # new jobs per visitor per 24 h (re-renders don't count)
    reframe_ttl_sec: int = 24 * 3600         # uploads and results are deleted after this long
    reframe_min_free_gb: float = 2.0         # refuse new uploads below this much free disk
    reframe_render_max_height: int = 1440    # source frames are decoded at most this tall (4K -> 1440p)
    reframe_threads: int = 2                 # CPU threads for the AI models (ffmpeg uses its own)
    models_dir: Path = BACKEND_DIR / "models"


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    if s.rapidapi_key:
        # Host dashboards (Railway) keep quotes typed around a value; RapidAPI then answers 403.
        s.rapidapi_key = s.rapidapi_key.strip().strip("\"'").strip() or None
    if s.cookies_txt and not s.cookies_file:
        # yt-dlp reads cookies from a file, so write the variable's contents to one.
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        path = DATA_DIR / "cookies.txt"
        path.write_text(s.cookies_txt.replace("\\n", "\n").strip() + "\n", encoding="utf-8")
        s.cookies_file = path
    return s
