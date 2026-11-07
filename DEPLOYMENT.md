# Deploying Klypsy to Railway

The project deploys as **two Railway services** from one GitHub repo:

| Service | Folder | What it is | Public? |
|---|---|---|---|
| `backend` | `/backend` | FastAPI + yt-dlp + FFmpeg + Deno (Dockerfile) | No, private network only |
| `web` | `/web` | Next.js website (Dockerfile); forwards `/api/*` to `backend` | Yes |

Both Dockerfiles are already in the repo. They haven't been test-built locally (Docker on this PC stores data on C:), so the first Railway build is the real test. If a build fails, copy the build log and fix from there.

---

## Step 1: Put the code on GitHub

Create an **empty private** repo on github.com (no README), then:

```powershell
cd "D:\Shehryar Bhai Work\video downloader"
git init
git add .
git commit -m "Klypsy phase 1"
git branch -M main
git remote add origin https://github.com/<you>/<repo>.git
git push -u origin main
```

`.gitignore` already excludes the venv, node_modules, caches, `.tmp` and `backend/.env`.

---

## Step 2: Create the `backend` service

1. railway.com → **New Project → Deploy from GitHub repo** → pick the repo.
2. Open the service → **Settings**:
   - **Service name:** `backend` (exactly this; the web service refers to it by name)
   - **Root Directory:** `/backend` (the Dockerfile there is detected automatically)
   - **Healthcheck Path:** `/api/health`
   - **Replicas:** 1 (pasted links are remembered in memory)
3. **Variables:**

   | Name | Value | Required |
   |---|---|---|
   | `PORT` | `8000` | Yes |
   | `CF_ENABLE_YOUTUBE` | `true` / `false` | No (default `true`) |
   | `CF_COOKIES_TXT` | whole cookies.txt file (see Step 6) | Only if platforms block the server |
   | `CF_PROXY` | `http://user:pass@host:port` | Only if platforms block the server |

4. Do **not** generate a public domain for this service.

---

## Step 3: Create the `web` service

1. Same project → **+ New → GitHub Repo** → same repo.
2. **Settings:**
   - **Service name:** `web`
   - **Root Directory:** `/web`
3. **Variables:**

   | Name | Value |
   |---|---|
   | `PORT` | `3000` |
   | `API_ORIGIN` | `http://${{backend.RAILWAY_PRIVATE_DOMAIN}}:8000` |

4. **Settings → Networking → Generate Domain** (target port `3000`).
5. Copy that domain and add one more variable:

   | Name | Value |
   |---|---|
   | `NEXT_PUBLIC_SITE_URL` | `https://<the generated domain>` |

   This is baked into the build (sitemap, canonical links), so set it **before** the build runs.

---

## Step 4: Deploy and test

1. Redeploy `backend` first, then `web`.
2. Watch the build logs until both show **Active**.
3. Open the web domain and test, starting with the platforms least likely to be blocked:
   1. Pinterest or Facebook link
   2. YouTube link (try a 720p/1080p option: it should start in the browser/IDM immediately with a known size)
   3. TikTok link
4. Backend check: in the backend service's logs you should see `GET /api/health 200`.

---

## Step 5: Custom domain (klypsy.com)

0. Register `klypsy.com` first (normal price, about $10–12/year, at any registrar such as Cloudflare Registrar, Namecheap or Porkbun). Also register `klypsy.ai` so nobody else can take it.
1. `web` service → **Settings → Networking → Custom Domain** → enter `klypsy.com` (and `www.klypsy.com`).
2. Add the DNS records Railway shows at your domain registrar.
3. Change `NEXT_PUBLIC_SITE_URL` to `https://klypsy.com` and redeploy `web`.
4. Create the `support@klypsy.com` mailbox (e.g. Zoho Mail free plan or Google Workspace). The site already shows this address on the Contact, Privacy, Terms and DMCA pages.

---

## Step 6: If YouTube / TikTok / Instagram fail on Railway

Data-centre IPs (Railway, AWS, etc.) are often blocked. Typical errors: *"Sign in to confirm you're not a bot"*, *"The platform is blocking our server"*, *"This post is private or needs a login"*.

**Easiest fix for YouTube and Instagram: the fallback API.** Add these to the **backend** variables, then redeploy:

- **`CF_RAPIDAPI_KEY`**: your key from RapidAPI, from the "Social Media Video Downloader" API (publisher `emmanueldavidyou`). It is the `x-rapidapi-key` value in that API's Code snippet tab.
- **`CF_RAPIDAPI_HOST`**: `social-media-video-downloader.p.rapidapi.com`. This is the default, so this variable is optional.

How it works (`backend/app/fallback.py`): yt-dlp still runs first, for free. If YouTube or Instagram blocks it (bot check, login wall, 403), the link is extracted through the API instead. After a block, that platform goes straight to the API for 10 minutes. Each link costs 1 API credit. Downloads, MP3, merging and resume all work the same way. Keep an eye on usage in the RapidAPI dashboard.

Other options (no API cost, more upkeep):

1. **`CF_COOKIES_TXT`**
   - Log in to YouTube (and/or Instagram) in a browser with a **throwaway account**. Never use your main account: it can get flagged.
   - Export cookies in Netscape format with a "Get cookies.txt LOCALLY"-type extension.
   - Paste the whole file contents as the variable value.
2. **`CF_PROXY`**
   - A residential proxy, in the form `http://user:pass@host:port`.
   - Cookies alone often aren't enough from cloud IPs; a residential proxy is what works reliably. It is the proxy cost already budgeted in the proposal (§9).

---

## Step 7: Updating

- Every `git push` to `main` redeploys automatically.
- YouTube breaks yt-dlp regularly. About **once a week**:

  ```powershell
  cd "D:\Shehryar Bhai Work\video downloader\backend"
  uv lock --upgrade-package yt-dlp
  cd ..
  git commit -am "Update yt-dlp"
  git push
  ```

- DMCA takedowns: add the URL or video ID to `backend/blocklist.txt`, commit and push.

---

## Costs and limits

| Item | Detail |
|---|---|
| Plan | Hobby plan (about $5/month, includes $5 of usage) |
| Bandwidth | About **$0.05 per GB** sent out. Every downloaded byte passes through the server. Example: 1,000 downloads/day × 30 MB ≈ 900 GB/month ≈ **$45/month** extra. |
| Request length | Railway cuts any request at **15 minutes**. Video downloads can be resumed by the browser/IDM; MP3 can't. |
| Idle cutoff | Requests that send nothing for **60 seconds** are cancelled. The app is already tuned to stay under this. |
| Replicas | Keep **1** backend replica. |

**Recommendation:** Railway is good for launch and testing. When traffic grows, move to a VPS (e.g. Hetzner, ~20 TB bandwidth included). The same Dockerfiles work there.

---

## Before launch checklist

- [ ] `klypsy.com` bought and connected
- [ ] `NEXT_PUBLIC_SITE_URL` set to `https://klypsy.com`
- [ ] `support@klypsy.com` mailbox created and receiving mail
- [ ] YouTube, TikTok and Instagram tested from the Railway server (cookies/proxy added if needed)
- [ ] Decide on YouTube before applying for AdSense (`CF_ENABLE_YOUTUBE=false`, or a separate domain; see proposal §6)
- [ ] yt-dlp updated within the last week

## Sources

- [Railway private networking](https://docs.railway.com/private-networking)
- [Railway specs & limits](https://docs.railway.com/networking/public-networking/specs-and-limits.md)
- [Railway 60 s idle cutoff](https://station.railway.com/questions/edge-kills-requests-with-no-response-byt-c65210de)
- [Railway video egress costs](https://station.railway.com/questions/huge-egress-costs-for-video-streaming-d51e2c9d)
- [Railway pricing breakdown](https://www.withorb.com/pricing-atlas/railway)
- [yt-dlp data-centre bot-check issue](https://github.com/yt-dlp/yt-dlp/issues/10128)
- [Cookies vs proxies from cloud servers](https://dev.to/osovsky/i-was-building-a-cloud-video-service-youtube-turned-me-into-an-ip-trafficker-1l9o)
