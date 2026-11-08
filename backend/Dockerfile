# Klyprima API (FastAPI + yt-dlp + FFmpeg) - built by Railway from the /backend folder.
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
COPY blocklist.txt ./

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

# "::" listens on IPv4 + IPv6 (Railway private networking). $PORT is set by Railway.
CMD ["sh", "-c", "exec uvicorn app.main:app --host :: --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
