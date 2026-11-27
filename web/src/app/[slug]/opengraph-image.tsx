import { ImageResponse } from "next/og";
import { CAPTION_PAGES } from "@/lib/captionTools";
import { CLIP_PAGES } from "@/lib/clipTools";
import { CONTENT } from "@/lib/content";
import { PLATFORMS } from "@/lib/platforms";
import { SITE } from "@/lib/site";
import { TOOL_PAGES } from "@/lib/tools";

export const alt = `${SITE.name}: free AI video tools`;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

type Card = { tool: string; color: string; h1: string; highlight: string; points: string[] };

const CARDS: Record<string, Card> = {};
for (const p of CLIP_PAGES)
  CARDS[p.slug] = { tool: "AI Clips", color: "#8b5cf6", h1: p.h1, highlight: p.highlight, points: ["Virality score", "Speaker in frame", "Captions + hook", "No watermark"] };
for (const p of CAPTION_PAGES)
  CARDS[p.slug] = { tool: "AI Captions", color: "#f59e0b", h1: p.h1, highlight: p.highlight, points: ["Checked twice by AI", "40+ languages", "MP4 & SRT", "Free"] };
for (const p of TOOL_PAGES)
  CARDS[p.slug] = { tool: "Smart Reframe", color: "#0ea5e9", h1: p.h1, highlight: p.highlight, points: ["Follows the speaker", "9:16, 4:5, 1:1", "Up to 1080p", "No watermark"] };
for (const p of PLATFORMS) {
  const c = CONTENT[p.id];
  CARDS[p.slug] = { tool: `${p.short} Downloader`, color: "#ff6a3d", h1: c.h1, highlight: c.highlight, points: ["HD MP4", "MP3", "No watermark", "No sign-up"] };
}

export function generateStaticParams() {
  return Object.keys(CARDS).map((slug) => ({ slug }));
}

export default async function OgImage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const c = CARDS[slug] ?? { tool: SITE.name, color: "#ff6a3d", h1: SITE.slogan, highlight: "", points: [] };
  // Word by word (Satori drops spaces at the edges of inline pieces), the highlighted words in the tool's colour.
  const [before, after] = c.highlight ? c.h1.split(c.highlight) : [c.h1, ""];
  const words = [
    ...before.split(" ").filter(Boolean).map((w) => ({ w, hi: false })),
    ...(c.highlight ? c.highlight.split(" ").map((w) => ({ w, hi: true })) : []),
    ...(after ?? "").split(" ").filter(Boolean).map((w) => ({ w, hi: false })),
  ];
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: 72,
          background: `radial-gradient(70% 60% at 85% 0%, ${c.color}40, transparent 70%), #0b0b0d`,
          color: "#f4f3ef",
        }}
      >
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 18, fontSize: 36, fontWeight: 600 }}>
            <svg width="56" height="56" viewBox="0 0 32 32">
              <rect width="32" height="32" rx="9" fill="#ff6a3d" />
              <path d="M12 9.5v13l11-6.5-11-6.5Z" fill="#160803" />
            </svg>
            {SITE.name}
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12, padding: "10px 22px", borderRadius: 999, border: `2px solid ${c.color}`, fontSize: 28, fontWeight: 600 }}>
            <div style={{ width: 14, height: 14, borderRadius: 7, background: c.color }} />
            {c.tool}
          </div>
        </div>
        <div style={{ display: "flex", flexWrap: "wrap", fontSize: 72, fontWeight: 700, letterSpacing: -2.5, lineHeight: 1.05, maxWidth: 1050 }}>
          {words.map(({ w, hi }, i) => (
            <span key={i} style={{ marginRight: 20, color: hi ? c.color : "#f4f3ef" }}>
              {w}
            </span>
          ))}
        </div>
        <div style={{ display: "flex", gap: 14, fontSize: 26, color: "#d4d4dc" }}>
          {c.points.map((pt) => (
            <div key={pt} style={{ display: "flex", alignItems: "center", gap: 10, padding: "10px 20px", borderRadius: 999, background: "#18181c", border: "1px solid #2a2a31" }}>
              <div style={{ width: 10, height: 10, borderRadius: 5, background: c.color }} />
              {pt}
            </div>
          ))}
        </div>
      </div>
    ),
    size,
  );
}
