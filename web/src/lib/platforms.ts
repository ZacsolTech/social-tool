export type PlatformId =
  | "youtube"
  | "tiktok"
  | "instagram"
  | "facebook"
  | "x"
  | "reddit"
  | "pinterest"
  | "dailymotion"
  | "twitch";

export type Platform = {
  id: PlatformId;
  name: string;
  short: string;
  slug: string;
  color: string;
  domains: string[];
  example: string;
  /** what people call the content on this platform */
  noun: string;
};

export const PLATFORMS: Platform[] = [
  { id: "youtube", name: "YouTube", short: "YouTube", slug: "youtube-video-downloader", color: "#FF0033", domains: ["youtube.com", "youtu.be"], example: "https://www.youtube.com/watch?v=…", noun: "YouTube videos and Shorts" },
  { id: "tiktok", name: "TikTok", short: "TikTok", slug: "tiktok-video-downloader", color: "#111111", domains: ["tiktok.com"], example: "https://www.tiktok.com/@user/video/…", noun: "TikTok videos" },
  { id: "instagram", name: "Instagram", short: "Instagram", slug: "instagram-reels-downloader", color: "#E1306C", domains: ["instagram.com", "instagr.am"], example: "https://www.instagram.com/reel/…", noun: "Reels, videos and carousels" },
  { id: "facebook", name: "Facebook", short: "Facebook", slug: "facebook-video-downloader", color: "#1877F2", domains: ["facebook.com", "fb.watch", "fb.com"], example: "https://www.facebook.com/watch/?v=…", noun: "Facebook videos and Reels" },
  { id: "x", name: "X (Twitter)", short: "X", slug: "twitter-video-downloader", color: "#111111", domains: ["x.com", "twitter.com"], example: "https://x.com/user/status/…", noun: "X / Twitter videos and GIFs" },
  { id: "reddit", name: "Reddit", short: "Reddit", slug: "reddit-video-downloader", color: "#FF4500", domains: ["reddit.com", "redd.it"], example: "https://www.reddit.com/r/…/comments/…", noun: "Reddit videos with sound" },
  { id: "pinterest", name: "Pinterest", short: "Pinterest", slug: "pinterest-video-downloader", color: "#E60023", domains: ["pinterest.com", "pin.it"], example: "https://www.pinterest.com/pin/…", noun: "Pinterest video pins" },
  { id: "dailymotion", name: "Dailymotion", short: "Dailymotion", slug: "dailymotion-video-downloader", color: "#0A64F5", domains: ["dailymotion.com", "dai.ly"], example: "https://www.dailymotion.com/video/…", noun: "Dailymotion videos" },
  { id: "twitch", name: "Twitch", short: "Twitch", slug: "twitch-clip-downloader", color: "#9146FF", domains: ["twitch.tv"], example: "https://clips.twitch.tv/…", noun: "Twitch clips" },
];

export const bySlug = (slug: string) => PLATFORMS.find((p) => p.slug === slug);
export const byId = (id: string) => PLATFORMS.find((p) => p.id === id);

const URL_RE = /https?:\/\/[^\s<>"']+/i;

/** Pull the first link out of any text (share sheets often send "Check this out https://…"). */
export function extractUrl(text: string): string | null {
  const m = text.match(URL_RE);
  return m ? m[0].replace(/[),.]+$/, "") : null;
}

export function detectPlatform(url: string): Platform | null {
  try {
    const host = new URL(url.trim()).hostname.toLowerCase();
    if (host.startsWith("pinterest.") || host.includes(".pinterest.")) return byId("pinterest")!;
    return PLATFORMS.find((p) => p.domains.some((d) => host === d || host.endsWith("." + d))) ?? null;
  } catch {
    return null;
  }
}
