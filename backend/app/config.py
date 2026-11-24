import os
from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]   # .../backend (locally) or /app (in Docker)
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = PROJECT_ROOT / ".tmp"                     # D:\...\video downloader\.tmp locally, /.tmp in Docker


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="CF_", extra="ignore", populate_by_name=True)

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

    # ---- Captions tool. See app/captions/.
    # Speech to text: Groq's hosted Whisper when a key is set (fast, most accurate), else faster-whisper on
    # this server's CPU. GROQ_API_KEY works too.
    groq_api_key: str | None = Field(None, validation_alias=AliasChoices("CF_GROQ_API_KEY", "GROQ_API_KEY"))
    groq_model: str = "whisper-large-v3-turbo"
    # Low-resource languages lose accuracy in "turbo" (its decoder was cut down): use the full model for them.
    groq_model_accurate: str = "whisper-large-v3"
    groq_accurate_languages: list[str] = ["ur", "hi", "pa", "sd", "ps", "bn", "fa", "ne", "mr", "gu", "ta", "te"]
    # After speech-to-text, a text AI fixes misheard words using the whole transcript (same word count, so the
    # timings stay). Free with the Groq key.
    captions_ai_proofread: bool = True
    groq_translate_model: str = "whisper-large-v3"        # speech -> English translation
    # Free text model on the same Groq key: AI translation / Roman Urdu / highlights when there's no Anthropic key.
    groq_llm_model: str = "openai/gpt-oss-120b"
    # Second free speech-to-text: Cloudflare Workers AI (same Whisper large-v3-turbo, free daily allowance).
    # Token needs the "Workers AI" permission. CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN work too.
    cloudflare_account_id: str | None = Field(None, validation_alias=AliasChoices("CF_CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_ACCOUNT_ID"))
    cloudflare_api_token: str | None = Field(None, validation_alias=AliasChoices("CF_CLOUDFLARE_API_TOKEN", "CLOUDFLARE_API_TOKEN"))
    cloudflare_whisper_model: str = "@cf/openai/whisper-large-v3-turbo"
    local_whisper_model: str = "small"                     # tiny | base | small | medium (CPU)
    local_whisper_fallback: bool = True                    # use the local model when Groq fails
    captions_warm_model: bool = True                       # no Groq key: download/load the local model at start-up
    whisper_dir: Path = BACKEND_DIR / "whisper-models"
    # AI text features (translation, Roman Urdu polish, highlights, hook titles). ANTHROPIC_API_KEY works too.
    anthropic_api_key: str | None = Field(None, validation_alias=AliasChoices("CF_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"))
    anthropic_model: str = "claude-opus-5-5"
    captions_max_duration_sec: int = 60 * 60    # longest video the caption tool accepts
    captions_daily_per_ip: int = 30             # new transcriptions per visitor per 24 h
    captions_ai_daily_per_ip: int = 60          # AI text actions (translate, highlights...) per visitor per 24 h
    captions_renders_per_hour: int = 40         # burned-in exports per visitor per hour
    captions_workers: int = 2                   # jobs worked on at the same time
    captions_queue_max: int = 40
    captions_threads: int = 4                   # CPU threads for the local speech model
    captions_watermark: str = "klyprima.com"    # text of the optional credit on exported videos


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
