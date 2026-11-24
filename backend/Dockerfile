# Klyprima API (FastAPI + yt-dlp + FFmpeg + Reframe AI models) - built by Railway from the /backend folder.
FROM python:3.14-slim

# uv (same version as local dev) and Deno (yt-dlp's preferred JS runtime for YouTube challenges).
COPY --from=ghcr.io/astral-sh/uv:0.11.26 /uv /usr/local/bin/uv
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno

RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_CACHE_DIR=/tmp/uv-cache \
    PYTHONUNBUFFERED=1

# Dependencies first (cached between deploys), then the app code.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project && rm -rf /tmp/uv-cache
COPY app ./app
COPY models ./models
COPY fonts ./fonts
COPY blocklist.txt ./

ENV PATH="/app/.venv/bin:$PATH"
# Fail the build (not the first visitor) if an AI model file or a caption font is missing or damaged.
RUN python -c "from app.reframe import models; [models.path(k) for k in models.MODELS]" \
 && python -c "from app.captions import fonts; r = fonts.registry(); assert len(r) >= 20 and r['nastaliq'].family == 'Noto Nastaliq Urdu', r"

# Captions: the local speech-to-text model (used when CF_GROQ_API_KEY isn't set, or Groq fails).
# Baked into the image so the first visitor doesn't wait for a download. Build with
# --build-arg WHISPER_PRELOAD= to skip it (smaller image; it then downloads on first use).
ARG WHISPER_PRELOAD=small
RUN if [ -n "$WHISPER_PRELOAD" ]; then \
      python -c "from faster_whisper.utils import download_model; download_model('$WHISPER_PRELOAD', cache_dir='/app/whisper-models')" \
      && rm -rf /root/.cache; \
    fi
ENV CF_LOCAL_WHISPER_MODEL=${WHISPER_PRELOAD:-small}
EXPOSE 8000

# "::" for Railway private networking. $PORT is set by Railway. asyncio binds "::" as IPv6-only,
# so ffmpeg must reach this API at [::1] (127.0.0.1 is refused): see CF_INTERNAL_API / config.py.
CMD ["sh", "-c", "export CF_INTERNAL_API=${CF_INTERNAL_API:-http://[::1]:${PORT:-8000}}; exec uvicorn app.main:app --host :: --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
