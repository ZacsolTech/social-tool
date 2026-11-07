# Video Tools Website: Proposal & Feasibility Report

> **Brand name:** Klypsy (klypsy.com) · Slogan: "Grab it. Clip it. Post it."
> **One-line idea:** Paste a link or upload a video and get ready-to-post short clips with captions, resized for TikTok, Reels and Shorts, in one flow.

---

## 1. The Honest Summary (Read This First)

| Question | Answer |
|---|---|
| Is the idea feasible? | **Yes**, but only if it is positioned as an **AI video editing / repurposing tool**, not as "just another downloader". |
| Will Google AdSense approve it? | **The editing tools: yes, likely. The downloader: high risk.** Google's publisher policies do not allow ads on content that helps people infringe copyright. YouTube downloaders in particular are often rejected or banned. Details in Section 6. |
| Expected AdSense RPM | **$0.30 – $1.50** if traffic is mostly from Asia. **$3 – $8** if traffic is from the US/UK/EU. Details in Section 7. |
| Can ads alone pay the bills? | Only at large scale (500k+ monthly visits). The real money is **paid plans** for the AI tools (captions and long-to-short clips). |
| Biggest risks | 1) AdSense rejection or ban caused by the downloader 2) platforms blocking the downloader 3) GPU/server cost of the AI tools on a free plan. |

**Recommendation:** Build the site around the AI tools, which are safe, valuable and can be monetised. Treat the downloader only as an **input step** ("import from link") and not as the headline product.

---

## 2. Tools & How Each One Works

All tools run on a **Python backend**. The core engine is **FFmpeg**, which is free and is the industry standard.

| # | Tool | What the user does | How it works (behind the scenes) | AI used? |
|---|---|---|---|---|
| 1 | **Social Video Downloader** | Pastes a TikTok/Instagram/Facebook/X/YouTube link | `yt-dlp` (Python library) gets the direct video URL. The user downloads it straight from the source, so our server bandwidth stays near zero. | No |
| 2 | **Caption Generator** | **Either** uploads a video **or** pastes a video link (TikTok/Instagram/Facebook/X/YouTube), then picks a language | **Input:** an upload goes straight to storage. A link is fetched by `yt-dlp` on the server (audio-only where possible, so it is fast and cheap). **Then the same pipeline for both:** `faster-whisper` (OpenAI Whisper model) converts speech to text with word timings. The user edits the text and picks a style. FFmpeg burns the captions in, or exports `.srt`. | **Yes**, speech-to-text |
| 3 | **Combine Videos (up to 4)** | Uploads 2–4 clips and reorders them | FFmpeg converts all clips to the same size/FPS, then joins them. Optional transitions. | No |
| 4 | **Video Splitter** | Uploads a video and sets cut points or "split every X sec" | FFmpeg cuts the video without re-encoding where possible, so it is very fast. | Optional: auto-split on scene change (`PySceneDetect`) |
| 5 | **Long Video → Short Clips** | Uploads a 10–60 min video | 1) Whisper transcribes it 2) an LLM reads the transcript and picks the 5–10 most engaging 30–60s moments ("hooks") 3) FFmpeg cuts them 4) captions and portrait resize are added automatically | **Yes**, transcription + LLM clip picking |
| 6 | **Landscape → Portrait Resize** | Uploads a 16:9 video | **Smart reframe:** AI face/subject tracking (`MediaPipe` / `YOLO`) keeps the speaker in the centre of the 9:16 frame. Fallback: a blurred background fill. | **Yes**, subject tracking |

### The flow that sets us apart (Link → Shorts)
```
Paste link / Upload  →  Transcribe (AI)  →  AI picks best moments
      →  Auto-reframe to 9:16 (AI)  →  Add styled captions  →  Download / Export
```
Competitors make users go to 3–4 different websites to do this. **We do it in one click.**

---

## 3. Technical Architecture (Simple View)

```
[ User Browser ]  Next.js / React website (fast, SEO-friendly, mobile-first)
        │
        ▼
[ API Server ]    Python FastAPI
        │
        ▼
[ Job Queue ]     Redis + Celery (heavy video jobs run in the background)
        │
        ▼
[ Workers ]       Python + FFmpeg + yt-dlp + Whisper + AI models
        │
        ▼
[ Storage ]       Cloudflare R2 / S3. Files are auto-deleted after 24 hours.
```

| Part | Technology | Why |
|---|---|---|
| Frontend | Next.js + Tailwind | Fast pages that rank well on Google |
| Backend | Python FastAPI | Fits well with the AI and video libraries |
| Video processing | FFmpeg | Free and handles everything |
| Downloader | yt-dlp | Supports 1000+ sites and is actively maintained |
| Captions | faster-whisper (self-hosted) **or** Groq/OpenAI Whisper API | Self-hosted is cheap at scale. The API is cheaper at the start. |
| Clip selection | Claude / GPT API on the transcript text | Low cost per video because it only reads text |
| Reframe | MediaPipe face detection | Runs on CPU, no GPU needed |
| Hosting | Hetzner / DigitalOcean + Cloudflare | Low cost, with DDoS and CDN included |

---

## 4. Competitors & How We Beat Them

| Competitor | What they do | Their weakness | Our edge |
|---|---|---|---|
| SnapTik, SSSTik, SaveFrom, Y2mate | Download only | Spammy ads and pop-ups, no editing, legal trouble | Clean user experience and real editing tools |
| Opus Clip, Vizard, Submagic | AI long-to-short + captions | Expensive ($15–$30/mo), weak free plan | Generous free plan, one-click flow from a link |
| Kapwing, VEED, CapCut | Full online editor | Too complex for a quick job, many features locked | Single-purpose fast tools, no learning curve |

### Differentiation ideas (to avoid looking generic)
1. **Regional language captions**: excellent Urdu, Hindi, Arabic, Punjabi, Bengali and Roman-Urdu captions. Big Western tools do these poorly. This is an underserved market of hundreds of millions of creators.
2. **Link → Shorts in one click**: no other free tool does the full pipeline.
3. **Viral score**: the AI rates each clip 1–100 for "hook strength" and explains why.
4. **Caption style templates** that copy trending creator styles (bold word-by-word, emoji highlights).
5. **No signup for basic tools**: a big conversion advantage over VEED and Kapwing.
6. **Mobile-first PWA**: most short-form creators edit on their phones.
7. **WhatsApp / Telegram bot**: send a link and get the clip back. A strong growth channel in South Asia.

---

## 5. Traffic Plan: How to Get Users

| Channel | What to do | Expected impact |
|---|---|---|
| **SEO: tool pages** | One page per tool, per platform and per language, e.g. "Instagram reel to MP4", "add Urdu subtitles to video", "convert YouTube video to TikTok format". Aim for 100–300 pages. | **Main channel** (60–70% of traffic over time) |
| **SEO: blog** | How-to guides: "how to make Shorts from a podcast", "best caption styles 2026" | Long-term traffic and backlinks |
| **YouTube / TikTok channel** | Post clips made **with our own tool** and show the process | Free demo + traffic |
| **Chrome extension** | "Clip this video" button on YouTube | Low-cost, steady installs |
| **Product Hunt, Reddit, Indie Hackers** | Launch posts in r/NewTubers, r/podcasting, r/socialmedia | First 5–20k users |
| **Creator partnerships** | Give free Pro accounts to small/mid creators in exchange for a mention | Trust + traffic |
| **WhatsApp/Telegram bot** | Viral sharing inside groups | Strong in Pakistan, India, Indonesia |
| **Embeddable "Made with Klypsy"** | Small watermark on free exports that links back | Built-in viral loop |

**Realistic traffic timeline (with consistent SEO work):**

| Month | Monthly visits |
|---|---|
| 1–3 | 2k – 15k |
| 4–6 | 20k – 80k |
| 7–12 | 100k – 400k |
| 12+ | 500k+ is possible if SEO pages rank |

---

## 6. Google AdSense: The Research

### What the policy says
- Google's **Publisher Policies** do not allow ads on pages that **infringe copyright or help users infringe it**.
- **YouTube's Terms of Service** ban downloading videos without a download button or YouTube's permission. Google owns both YouTube and AdSense, so **YouTube downloader sites are a known rejection reason**, and many have had their AdSense accounts disabled.
- TikTok, Instagram and Facebook downloaders are a grey area. Some get approved, but they can be **banned later** after a policy review. A ban can mean **losing unpaid earnings**.

### What this means for us
| Part of site | AdSense risk | Plan |
|---|---|---|
| Captions, Combine, Split, Resize, Long→Short | **Low**. These are genuine editing tools working on the user's own uploads. | Apply for AdSense with these. |
| Captions **from a link** | **Medium**. The tool fetches the video from a link, so it touches the same copyright question as the downloader. | Return only captions/`.srt` or the captioned video, never the raw downloaded file. Block YouTube links on AdSense pages (or keep link import behind login). Show the "only use content you own or have permission to use" notice next to the link box. |
| Downloader | **High** | Option A (safest): remove YouTube and allow only platforms/content the user owns. Option B: move the downloader to a **separate domain** monetised with non-Google networks. |

### AdSense approval checklist
- Domain with 15–30 quality pages of **original content** (tool guides and blog posts)
- About, Contact, Privacy Policy, Terms, DMCA/Copyright pages
- Clean design, no broken pages, fast loading
- No pop-ups or forced redirects
- Note: Pakistan/India accounts sometimes need the **domain to be some months old** before approval

### Alternative / backup ad networks
| Network | Accepts downloaders? | Typical RPM (Asia traffic) |
|---|---|---|
| Adsterra | Yes | $0.30 – $1.50 |
| Monetag (PropellerAds) | Yes | $0.30 – $2.00 (pop-unders hurt the user experience) |
| Ezoic | Case by case (uses Google demand) | $1 – $4 |
| Mediavine / Raptive | Needs 50k–100k sessions plus mostly Tier-1 traffic | $10 – $25 (Tier-1 only) |

---

## 7. RPM: How Much Will We Earn per 1,000 Page Views?

RPM depends mostly on **where visitors come from**. Downloader and tool sites usually get most of their traffic from South Asia, Southeast Asia and Latin America.

| Visitor country | Estimated AdSense page RPM (tool sites) |
|---|---|
| USA, UK, Canada, Australia | $3 – $8 |
| Western Europe | $2 – $5 |
| Middle East (UAE, Saudi) | $1 – $3 |
| Pakistan, India, Bangladesh | $0.20 – $0.80 |
| Indonesia, Philippines, Brazil | $0.30 – $1.00 |
| **Blended (typical tool site mix)** | **$0.50 – $1.50** |

> Tool pages earn less than blog pages because users stay focused on the task and rarely click ads. These are estimates. Real RPM is only known after 1–2 months of live traffic.

### Ad income projection (blended RPM ≈ $1, ~2 page views per visit)

| Monthly visits | Page views | Monthly ad income |
|---|---|---|
| 50k | 100k | ~$100 |
| 200k | 400k | ~$400 |
| 500k | 1M | ~$1,000 |
| 2M | 4M | ~$4,000 |

**Conclusion:** ads cover hosting costs. **Paid plans are what make this a business.**

---

## 8. Business Model: Free First, Paid Later

### Phase 1: Fully free (months 1–6)
- Every feature is free so we can grow users and gain SEO authority
- Soft limits keep server costs under control (e.g. max 30 min video, 5 AI jobs/day)
- Collect emails (optional login with Google) so we can convert users later

### Phase 2: Freemium (month 6+)
| Plan | Price | Includes |
|---|---|---|
| **Free** | $0 | Downloader, split, combine, resize, 3 AI jobs/day, small watermark, ads shown |
| **Creator** | $7 – $9 /month | No watermark, no ads, 1080p, 60 AI min/month, all caption styles |
| **Pro** | $19 – $24 /month | 300 AI min/month, 4K, priority queue, brand kit, bulk clips |
| **Local pricing** | e.g. PKR 999 / INR 399 | Local payments: JazzCash, Easypaisa, UPI (big conversion boost) |

**Payments:** Stripe / Paddle / Lemon Squeezy for international customers, local gateways for Pakistan/India.

### Revenue projection (Phase 2, conservative)
| Monthly visits | Paid conversion (1–2%) | Avg $8/user | + Ads | **Total/month** |
|---|---|---|---|---|
| 100k | 1,000–2,000 signups → ~150 paid | $1,200 | $200 | **~$1,400** |
| 500k | ~700 paid | $5,600 | $1,000 | **~$6,600** |
| 1M | ~1,500 paid | $12,000 | $2,000 | **~$14,000** |

---

## 9. Costs

### One-time (build)
| Item | Estimate |
|---|---|
| Development (in-house team, 3–4 months) | Team salary |
| Domain + branding/logo | $50 – $300 |
| UI design | $0 – $1,000 |

### Monthly (running)
| Item | Early stage | At 500k visits |
|---|---|---|
| Servers (CPU workers for FFmpeg) | $40 – $100 | $300 – $800 |
| GPU / Whisper API for captions | $20 – $100 | $300 – $1,000 |
| LLM API for clip picking | $10 – $30 | $100 – $300 |
| Storage + CDN (Cloudflare R2, egress is free) | $5 – $20 | $50 – $150 |
| Proxies for the downloader (platforms block servers) | $0 – $50 | $100 – $500 |
| **Total** | **~$100 – $300** | **~$900 – $2,800** |

> The AI tools are the most expensive part. That is why the free plan needs daily limits even in the "fully free" phase.

---

## 10. Legal & Safety Checklist
- Terms of Service: "Only download or process content you own or have permission to use"
- DMCA / copyright takedown page with a contact email
- Do not store user videos: **auto-delete after 24 hours**
- Do not host or index other people's videos (no public galleries)
- Privacy Policy plus GDPR cookie banner (required for AdSense in the EU)
- Rate limiting and CAPTCHA to stop bots and abuse

---

## 11. Roadmap

| Phase | Time | Deliverables |
|---|---|---|
| **1. MVP** | Month 1–2 | Downloader (non-YouTube), Splitter, Combine, Resize (blur fill), basic website + 20 SEO pages |
| **2. AI Tools** | Month 2–3 | Caption Generator from upload or link (incl. Urdu/Hindi), Smart Reframe, legal pages → **apply for AdSense** |
| **3. Hero Feature** | Month 3–4 | Long → Short Clips with AI viral score, the full Link → Shorts pipeline |
| **4. Growth** | Month 4–6 | 100+ SEO pages, Chrome extension, Telegram/WhatsApp bot, Product Hunt launch |
| **5. Monetise** | Month 6+ | Login, paid plans, local payments, remove ads for paying users |

---

## 12. Final Verdict

| Factor | Score |
|---|---|
| Market demand | ⭐⭐⭐⭐⭐ Huge and growing (short-form video) |
| Competition | ⭐⭐ Very crowded, so the niche angle matters |
| Technical difficulty | ⭐⭐⭐ Medium. All tools rely on proven open-source libraries |
| AdSense potential | ⭐⭐ Low RPM, and the downloader is risky |
| Subscription potential | ⭐⭐⭐⭐ Strong for the AI tools |
| **Overall** | **Feasible. Go ahead, with an AI-repurposing focus.** |

### Three things that decide success
1. **Lead with AI tools, not downloading.** This makes the site safe for AdSense and gives it real value.
2. **Own a niche** with regional-language captions and the one-click Link → Shorts flow.
3. **SEO from day one.** Plan for 100+ tool and landing pages, because free tools only survive on organic traffic.

---
*Note: RPM figures, costs and traffic numbers are industry estimates for 2025–2026 and will vary. Review the latest Google AdSense Publisher Policies before applying.*
