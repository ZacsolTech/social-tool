export const SITE = {
  name: "Klyprima",
  domain: "klyprima.com",
  url: process.env.NEXT_PUBLIC_SITE_URL ?? "http://localhost:3000",
  slogan: "Grab it. Clip it. Post it.",
  tagline:
    "Grab it. Clip it. Post it. Turn long videos into viral Shorts with AI, then caption, reframe and download. Free, no watermark, no sign-up.",
  description:
    "Free AI clip generator: turn podcasts and YouTube videos into viral Shorts, Reels and TikToks with captions. Plus captions, 9:16 reframe and a downloader.",
  email: "support@klyprima.com",
  year: 2026,
} as const;
