/** The Klyprima tool catalog: one place that the header, footer, home page and "more tools" cards read from. */

import { CAPTION_PAGES, CAPTIONS_SLUG } from "./captionTools";
import { CLIP_PAGES, CLIPS_SLUG } from "./clipTools";
import { PLATFORMS } from "./platforms";
import { REFRAME_SLUG, TOOL_PAGES } from "./tools";

export type ToolId = "download" | "clips" | "captions" | "reframe";

export type CatalogTool = {
  id: ToolId;
  name: string;            // full name: "AI Clips"
  short: string;           // in the header: "Clips"
  href: string;
  /** one line under the name */
  tagline: string;
  /** a short paragraph for tool cards */
  body: string;
  points: string[];
  cta: string;
  /** the main tool we lead with (AI Clips): shown first and bigger everywhere */
  featured?: boolean;
  /** Tailwind classes for the tool's colour (icon tile, dots); each tool has its own so they're easy to tell apart */
  tone: { tile: string; text: string; ring: string; dot: string };
  pages: { href: string; label: string }[];
};

export const TOOLS: CatalogTool[] = [
  {
    id: "clips",
    featured: true,
    name: "AI Clips",
    short: "AI Clips",
    href: `/${CLIPS_SLUG}`,
    tagline: "Long video to viral Shorts",
    body: "Drop a podcast, interview or stream. The AI finds the best moments, scores them, cuts them on full sentences and makes captioned vertical clips.",
    points: ["Virality score with the reason", "Speaker kept in frame", "Captions + hook title", "Download all as ZIP"],
    cta: "Find viral clips",
    tone: { tile: "bg-violet-500/12 text-violet-600 dark:text-violet-300", text: "text-violet-600 dark:text-violet-300", ring: "hover:border-violet-500/60", dot: "bg-violet-500" },
    pages: CLIP_PAGES.map((p) => ({ href: `/${p.slug}`, label: p.nav })),
  },
  {
    id: "captions",
    name: "AI Captions",
    short: "Captions",
    href: `/${CAPTIONS_SLUG}`,
    tagline: "Word-by-word animated captions",
    body: "Accurate captions in 40+ languages, checked twice by AI. Urdu in Nastaliq, Roman Urdu, Hindi, Arabic. Style them, then export MP4 or SRT.",
    points: ["Heard twice, AI-checked", "14 styles, 9 animations", "Urdu, Roman Urdu, Hindi", "MP4, SRT, VTT, TXT"],
    cta: "Add captions",
    tone: { tile: "bg-amber-400/15 text-amber-600 dark:text-amber-300", text: "text-amber-600 dark:text-amber-300", ring: "hover:border-amber-500/60", dot: "bg-amber-400" },
    pages: CAPTION_PAGES.map((p) => ({ href: `/${p.slug}`, label: p.nav })),
  },
  {
    id: "reframe",
    name: "Smart Reframe",
    short: "Reframe",
    href: `/${REFRAME_SLUG}`,
    tagline: "Landscape to 9:16, speaker in frame",
    body: "Turn 16:9 into vertical for TikTok, Reels and Shorts. The AI follows whoever talks, splits two people and keeps slides whole.",
    points: ["Follows the speaker", "Split screen & facecam", "Blur or fit fill", "Up to 1080p, no watermark"],
    cta: "Make it vertical",
    tone: { tile: "bg-sky-500/12 text-sky-600 dark:text-sky-300", text: "text-sky-600 dark:text-sky-300", ring: "hover:border-sky-500/60", dot: "bg-sky-500" },
    pages: TOOL_PAGES.map((p) => ({ href: `/${p.slug}`, label: p.nav })),
  },
  {
    id: "download",
    name: "Video Downloader",
    short: "Downloader",
    href: "/video-downloader",
    tagline: "Save any social video in HD",
    body: "Paste a YouTube, TikTok, Instagram, Facebook or X link. HD MP4 with no watermark, MP3 or the cover image. No pop-ups, no sign-up.",
    points: ["No watermark, HD", "MP3 & cover image", "Carousels & threads", "Share-to-app on phones"],
    cta: "Paste a link",
    tone: { tile: "bg-accent-soft text-accent", text: "text-accent", ring: "hover:border-accent/60", dot: "bg-accent" },
    pages: [{ href: "/video-downloader", label: "All sites" }, ...PLATFORMS.map((p) => ({ href: `/${p.slug}`, label: `${p.short} downloader` }))],
  },
];

/** Tools in the order a creator uses them: get the video, find clips, frame them, caption them. */
export const WORKFLOW: ToolId[] = ["download", "clips", "reframe", "captions"];

export const toolById = (id: ToolId) => TOOLS.find((t) => t.id === id)!;

export const FEATURED = TOOLS.find((t) => t.featured)!;
/** Everything except the main tool. */
export const SECONDARY = TOOLS.filter((t) => !t.featured);

/** Upcoming tools, shown as "Soon". */
export const UPCOMING = [
  { name: "Split", body: "Cut at exact times or every N seconds, without losing quality." },
  { name: "Merge", body: "Join clips into one, matched in size and frame rate." },
];

/** Which tool a page belongs to (for "more tools" sections and breadcrumbs). */
export function toolOfSlug(slug: string): ToolId | null {
  if (CLIP_PAGES.some((p) => p.slug === slug)) return "clips";
  if (CAPTION_PAGES.some((p) => p.slug === slug)) return "captions";
  if (TOOL_PAGES.some((p) => p.slug === slug)) return "reframe";
  if (slug === "video-downloader" || PLATFORMS.some((p) => p.slug === slug)) return "download";
  return null;
}
