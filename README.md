# Klyprima: Social Video Downloader + Reframe (landscape → portrait) + Captions + AI Clips

1. **Downloader**: paste a YouTube / TikTok / Instagram / Facebook / X / Reddit / Pinterest / Dailymotion / Twitch link → get HD MP4 (no watermark), MP3, or the cover image.
2. **Reframe**: upload a video or paste a link → get 9:16 / 4:5 / 1:1 versions. An AI "Auto Director" follows the speaker, switches between people, uses split screen, stacks a facecam over gameplay, and keeps slides whole. Or Blur Fill / Crop / Fit + Colour. Spec: `landscape-to-portrait-proposal.md`.

3. **Captions**: upload a video or paste a link → AI captions with word-level timing in 40+ languages (Urdu in Nastaliq, Roman Urdu, Hindi, Hinglish, Arabic right-to-left) → edit, style (14 presets, 9 animations), add highlights, emojis, a hook title, a progress bar and a logo, translate or show two languages, cut "um"s and pauses → burned-in MP4, SRT, VTT, TXT. Spec: `video-tools-proposal.md` and the Caption Generator proposal doc.

4. **AI Clips**: upload a long video (up to 90 min) or paste a link → AI listens, picks the best moments (hook, flow, value, shareability → virality score), cuts them on sentence edges, reframes to 9:16 / 4:5 / 1:1 with Smart Reframe, burns in animated captions and a hook title → MP4s, SRTs, titles, post text and hashtags, one by one or as a ZIP. Every clip can be trimmed, restyled and re-made on its own.

## Stack (Nov 2026)

| Layer | Tech |
|---|---|
| Frontend | **Next.js 16.4** (App Router, React 19.3, Turbopack, Cache Components / PPR), TypeScript, **Tailwind CSS v4**, lucide icons |
| Backend | **FastAPI 0.162** (streaming responses), **yt-dlp 2026.10.26** + curl-cffi (browser impersonation), FFmpeg |
| Reframe AI | **OpenCV 5** (YuNet faces, PP-OCR text detector, CSRT tracker), **onnxruntime** (YOLOX-nano objects, Silero speech). All CPU, all commercial-use licences, model files in `backend/models/` |
| Captions | **Groq Whisper** + **Cloudflare Workers AI** free tiers (or **faster-whisper** on CPU), **Groq gpt-oss-120b** (free) or **Claude** (paid, optional) for translation / Roman Urdu / highlights, **libass** via FFmpeg, OFL fonts in `backend/fonts` |
| Python env | **uv**, venv at `backend/.venv` |

Everything (venv, uv cache, npm cache, yt-dlp cache, temp) lives inside this folder on D:.

## Run

```powershell
./dev.ps1          # installs deps if needed, opens backend (:8000) and frontend (:3000)
```

Or manually:

```powershell
cd backend; uv sync; uv run uvicorn app.main:app --reload --reload-dir app --port 8000
cd web;     npm install; npm run dev
```

API docs: http://localhost:8000/docs. The site proxies `/api/*` to the backend (`web/next.config.ts`, set `API_ORIGIN` to change).

## How it works

1. `POST /api/resolve {url}` → platform allowlist check (SSRF-safe) → DMCA blocklist → yt-dlp extracts info → clean options (one per quality, H.264+AAC preferred, TikTok watermarked files dropped).
2. Every click opens `GET /api/download/{token}/{item}/{option}` in a hidden iframe, so the **browser's download bar or IDM takes over immediately**. Nothing is pre-downloaded or stored on the server:
   - **Single file** (most TikTok/Instagram/Facebook/X/Pinterest videos, YouTube 360p, M4A): relayed byte-for-byte with Range support.
   - **Video + audio** (YouTube HD, 2K/4K in AV1, Reddit): the **virtual muxer** (`backend/app/vmux.py`) reads only the first 256 KB of each DASH file (header + `sidx` segment index), computes the exact layout of one combined MP4 (video + audio fragments interleaved by time), and serves any byte range on demand by fetching the matching source bytes and patching 8 bytes per fragment. Result: exact `Content-Length`, Range/resume, IDM multi-connection, first byte in ~0.2 s.
   - **MP3** (and the rare non-MP4 merge such as VP9/WebM or HLS): FFmpeg converts on the fly while downloading. Starts at once, but size is unknown so it can't be resumed. FFmpeg reads inputs from the key-protected internal relay `GET /api/raw/...`.
   - Errors return a small page that `postMessage`s the reason to the site, so the button shows the error instead of the browser saving a broken file.
   - YouTube only serves media after `available_at` (its pre-roll ad slot, usually a few seconds). The API returns `ready_in` and the buttons count down ("Ready in 4s"); the backend also waits/retries briefly on 403.
3. Expired media URLs (TikTok's expire within minutes) are re-extracted once automatically. Thumbnails are proxied because platforms block hot-linking.

## Reframe tool (`backend/app/reframe/`, `web/src/components/reframe/`)

Pipeline, all on the CPU:

| Stage | File | What happens |
|---|---|---|
| Upload | `uploads.py` | Chunked, resumable upload (4 MB pieces, 409 = "continue from here"), ffprobe check |
| A. Understand | `analyze.py` | One decode at 640 px: exact scene cuts (every frame), faces + mouth movement + head direction (10/s), people/objects (2/s), on-screen text (every 2 s), facecam box (static-edge map), Silero speech + loudness |
| B. Decide | `director.py` | Layout per shot: Follow / Split / Screen + Facecam / Fit; active speaker with 1 s lead + 1.5 s hold, cut placed where the new speaker started |
| C. Camera | `director.py` | Eye-line at 38 %, app safe zones, looking room, dead zone + speed limit + zero-phase easing, dynamic-zoom punch-ins |
| D. Render | `render.py` | One decode feeds every format; YUV frames composed in OpenCV (sub-pixel while moving), encoded H.264/AAC with the source's colour tags. Blur/Crop/Fit modes are a single ffmpeg graph |
| Jobs | `jobs.py` | Queue + workers, progress/ETA, cancel, re-render from the saved analysis (shot editor), link import via the downloader's cache, 24 h cleanup |

API: `POST /api/uploads`, `PUT /api/uploads/{id}?offset=`, `POST /api/uploads/{id}/complete`, `GET /api/reframe/config`, `POST /api/reframe/jobs`, `GET /api/reframe/jobs/{id}`, `POST /api/reframe/jobs/{id}/render` (shot-editor overrides / new settings), `DELETE /api/reframe/jobs/{id}`, `GET /api/reframe/jobs/{id}/file/{9x16|4x5|1x1}` (Range, `?inline=1` for the player), `/thumb/{shot}`, `/source`.

Pages: `/landscape-to-portrait-video-converter` plus 7 SEO landing pages with presets (`web/src/lib/tools.ts`). The downloader's result card has **Make it vertical**, which hands the resolved link to the tool.

## Captions tool (`backend/app/captions/`, `web/src/components/captions/`)

| Stage | File | What happens |
|---|---|---|
| Source | `api.py`, `jobs.py` | Upload (shared chunked uploads), a downloader link, or a Reframe result (carries the captions over: "Make it vertical" and back). Or import an SRT/VTT |
| Speech to text | `stt.py` | 16 kHz mono MP3 → provider chain: **Groq** Whisper large-v3-turbo (free tier, `CF_GROQ_API_KEY`) → **Cloudflare Workers AI** (same model, free tier) → **faster-whisper** on the CPU. A provider whose free limit is used up is skipped until it resets. Per-language style prompts (keeps Urdu in Urdu script), VAD, multi-part language detection, hallucination filters |
| Accuracy check | `verify.py`, `stt.second_listen`, `llm.verify` | (1) The audio is heard a second time by a **different** model (Groq turbo ↔ large-v3, else Cloudflare); lines where both agree and the first model was confident are kept as they are. (2) An **AI judge** gets only the other lines (the two versions, neighbouring lines, title, the visitor's names) and writes what was most likely said: fixes misheard words and names, puts back dropped words and skipped sentences, removes invented ones. (3) Guards drop answers that paraphrase or translate; kept words keep their exact timing, new words take the second listen's timing. (4) Lines the judge wasn't sure about are flagged **Check** in the editor ("N lines to check" jumps between them). Videos over `CF_CAPTIONS_VERIFY_LISTEN_MAX_SEC` skip the second listen (quota). Any failure only means fewer checks |
| Roman Urdu / Hinglish | `translit.py`, `llm.py` | Speech is transcribed as Hindi (Devanagari writes every vowel) and romanised word by word, keeping timings; Claude polishes the spelling when `CF_ANTHROPIC_API_KEY` is set |
| Transcript | `transcript.py` | Words → editor lines → on-screen pages; SRT/VTT/TXT import and export |
| AI extras | `llm.py`, `enhance.py` | Translation (25 languages), keyword + emoji picks, hook ideas via Claude (`CF_ANTHROPIC_API_KEY`, paid) or **Groq's free gpt-oss-120b** (same Groq key); with no key: Whisper's English translation and heuristics |
| Styles | `styles.py`, `fonts.py` | 14 presets; 27 OFL fonts in `backend/fonts` (Nastaliq, Naskh, Devanagari, Bengali… CJK, Noto Emoji). Sizes are em sizes, converted per font for libass so the browser preview and the export match |
| Render | `ass.py`, `render.py`, `cuts.py` | ASS script (pages, spoken-word highlight, karaoke, pop, one-word, reveal, bounce/slide/fade, keyword colours, emojis, dual-language line, hook, progress bar, credit) burned in with FFmpeg + libass; optional filler/silence cuts (frame-accurate select/aselect) and logo overlay |

API: `GET /api/captions/config`, `GET /api/captions/fonts/{file}`, `POST /api/captions/jobs`, `GET /api/captions/jobs/{id}?since_rev=`, `PUT …/transcript`, `POST …/translate`, `POST …/romanize`, `POST …/enhance`, `POST …/render`, `PUT|DELETE …/logo`, `GET …/file/{video|srt|vtt|txt}?mode=original|translation|dual`, `GET …/source`, `DELETE …/{id}`.

Pages: `/auto-caption-generator` plus 11 SEO landing pages (`web/src/lib/captionTools.ts`). The downloader's result card and Reframe's results have **Add captions**; the caption editor has **Make it vertical**.

Re-download the fonts (only to add new ones): `uv run python scripts/fetch_fonts.py`.

## Tests

```powershell
cd backend
uv run pytest                      # ~130 tests: Reframe + Captions logic, real-video pipelines, full API (≈4 min)
$env:KLY_LIVE_STT="1"; uv run pytest tests/test_captions_live.py   # real speech-to-text (Windows TTS speech, tiny model)
# + CF_GROQ_API_KEY / CF_ANTHROPIC_API_KEY set: also tests the real Groq and Claude calls
# Browser end-to-end (start backend + `npm run build; npm start` first):
$env:KLY_E2E_URL="http://localhost:3000"; uv run pytest tests/e2e
$env:KLY_E2E_LINK="https://www.youtube.com/watch?v=jNQXAC9IVRw"   # optional: downloader → Make it vertical
```

Captions browser test (uses real local Whisper; start the backend with `CF_LOCAL_WHISPER_MODEL=tiny` for speed): `uv run pytest tests/e2e/test_captions_browser.py`. Web unit tests: `cd web; npm test` (caption paging/editing logic, Node's test runner).

Test videos are generated on the fly; one public sample photo from the OpenCV repo is cached in `.tmp/test-assets`. pytest's temp folder is `.tmp/pytest` (D:). The browser tests use Playwright with the installed Edge if Playwright's own Chromium isn't downloaded.

## Features that beat the competition

- No pop-ups, redirects or fake buttons. Clean light and dark UI.
- Platform auto-detect, **paste-to-start**, **Ctrl+V anywhere**, clipboard Paste & go button.
- **Native downloads**: browser download bar / IDM, exact size, resume and multi-connection, even for merged YouTube HD. Carousel / multi-video posts with **Download all**, MP3 / M4A / cover image.
- **PWA share target**: install on Android, then Share → Klyprima in TikTok/Instagram and the download starts automatically.
- Recent links stored only in the browser.
- SEO: 8 platform landing pages, JSON-LD (WebApplication, HowTo, FAQPage), sitemap, robots, OG image, canonical URLs.
- AdSense-ready legal pages: About, Contact, Privacy, Terms, DMCA (+ working blocklist in `backend/blocklist.txt`).

## Config

See `backend/.env.example`. YouTube is **on** (videos, Shorts, up to 4K, MP3). It is the main AdSense risk (proposal §6): set `CF_ENABLE_YOUTUBE=false` to turn it off, or serve it from a separate domain. Files over `CF_MAX_FILESIZE_MB` (1 GB) are hidden from the options.

## Known limits / before launch

- **TikTok blocks some IPs.** From the dev machine it intermittently returns "IP blocked" or connection resets. Production needs a residential proxy (`CF_PROXY`), as budgeted in the proposal.
- **Instagram and X**: public posts work via yt-dlp, but Instagram often requires cookies from server IPs (`CF_COOKIES_FILE`).
- Vimeo now needs a login and Threads has no yt-dlp extractor, so both are excluded.
- uvicorn `--reload` on Windows sometimes stops picking up changes; restart the backend window if an edit doesn't apply.
- Rate limiting and the link cache are in-memory (single process). Move them to Redis when scaling to several workers (proposal §3).
- Replace `SITE.email` / `NEXT_PUBLIC_SITE_URL` in `web/src/lib/site.ts` with the real domain.

## Deploy (Railway)

Two services from this repo, both built from their Dockerfiles:

| Service | Root directory | Variables | Public domain |
|---|---|---|---|
| `backend` | `/backend` | `PORT=8000`, optional `CF_PROXY`, `CF_COOKIES_TXT`, `CF_ENABLE_YOUTUBE`, `CF_REFRAME_*`, `CF_GROQ_API_KEY` + `CF_ANTHROPIC_API_KEY` (Captions, recommended), `CF_CAPTIONS_*` (see `.env.example`) | No (private only) |
| `web` | `/web` | `PORT=3000`, `API_ORIGIN=http://${{backend.RAILWAY_PRIVATE_DOMAIN}}:8000`, `NEXT_PUBLIC_SITE_URL=https://<your domain>` | Yes |

Backend health check: `/api/health`. Keep 1 replica (link cache and Reframe jobs are in memory). Update yt-dlp regularly: `uv lock --upgrade-package yt-dlp`, commit, push.
#   s o c i a l - t o o l 
 
 #   s o c i a l - t o o l 
 
 #   s o c i a l - t o o l 
 
 
## AI Clips tool (`backend/app/clips/`, `web/src/components/clips/`)

| Stage | File | What happens |
|---|---|---|
| Source | `api.py`, `jobs.py` | Upload (shared chunked uploads) or a downloader link ("Find viral clips" on long videos). Optional start/end to search only part of a long video |
| Listen | `jobs.py` | The caption tool's speech-to-text chain (Groq → Cloudflare → local Whisper), word timings, Roman Urdu / Hinglish |
| Find | `finder.py` | Transcript lines with times → text AI (Claude, or Groq's free model in windows that fit its token limit) returns ranges + title, hook, post text, hashtags and four scores. Offline scorer (hook phrases, questions, numbers, pacing, sentence edges, emotion) when there's no key or the AI fails, and to top up. Then every clip is refined: fitted to the length on sentence edges, padded without cutting a word, no overlaps. Only the chosen clips go through the caption accuracy check (their audio heard again + AI judge) |
| Render | `render.py` | Step 1, the frame: Smart Reframe (analyze + plan + render) or Blur / Fit, or a plain cut for Original. Step 2, the words: the caption tool's ASS + libass burn-in with the hook, keywords, emojis, optional filler/silence cuts. Step 1 is kept, so caption-only edits take seconds. Best clip first; each is downloadable as soon as it's ready |
| Edit | `jobs.py` | Per clip: trim (snapped to word edges), hook, title, post text, hashtags, shape, framing, caption style. Search again with another length / count / topic without listening again. "Edit captions word by word" opens the clip in the caption editor with its words |

API: `GET /api/clips/config`, `POST /api/clips/jobs`, `GET /api/clips/jobs/{id}`, `POST …/find`, `PATCH …/clips/{clip}`, `DELETE …/{id}`, `GET …/clips/{clip}/file|thumb|srt`, `GET …/zip`, `GET …/transcript`, `GET …/source`. Captions accept `source: {type: "clip", id, clip}`.

Pages: `/ai-clip-generator` plus 5 SEO landing pages (`web/src/lib/clipTools.ts`).

Tests: `tests/test_clips_unit.py` (finder, refinement, AI parsing/windows/fallback, snapping), `tests/test_clips_api.py` (system tests through the API with real FFmpeg/Reframe rendering), `tests/e2e/test_clips_browser.py` (real site + API + speech-to-text; `KLY_E2E_URL=...`), `web/src/lib/clipsCore.test.ts` (`npm test`).
