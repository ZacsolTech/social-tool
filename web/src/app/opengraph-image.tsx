import { ImageResponse } from "next/og";
import { SITE } from "@/lib/site";

export const alt = `${SITE.name} AI Clips: turn long videos into viral Shorts, free`;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

const TOOLS = [
  { name: "AI Clips", line: "Long video to Shorts", color: "#8b5cf6" },
  { name: "Captions", line: "Checked twice", color: "#fbbf24" },
  { name: "Reframe", line: "16:9 → 9:16", color: "#0ea5e9" },
  { name: "Downloader", line: "HD, no watermark", color: "#ff6a3d" },
];

export default function OgImage() {
  return new ImageResponse(
    (
      <div style={{ width: "100%", height: "100%", display: "flex", flexDirection: "column", justifyContent: "space-between", padding: 72, background: "#0b0b0d", color: "#f4f3ef" }}>
        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 18, fontSize: 40, fontWeight: 600 }}>
            <svg width="64" height="64" viewBox="0 0 32 32">
              <rect width="32" height="32" rx="9" fill="#ff6a3d" />
              <path d="M12 9.5v13l11-6.5-11-6.5Z" fill="#160803" />
            </svg>
            {SITE.name}
          </div>
          <div style={{ display: "flex", fontSize: 30, color: "#a3a3ad" }}>{SITE.slogan}</div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ fontSize: 68, fontWeight: 700, letterSpacing: -2.5, lineHeight: 1.02 }}>Long videos in.</div>
          <div style={{ fontSize: 68, fontWeight: 700, letterSpacing: -2.5, lineHeight: 1.02, color: "#ff6a3d" }}>Viral Shorts out. Free.</div>
        </div>
        <div style={{ display: "flex", gap: 16 }}>
          {TOOLS.map((t) => (
            <div key={t.name} style={{ display: "flex", flexDirection: "column", flex: 1, gap: 6, padding: "18px 22px", borderRadius: 22, background: "#141417", border: "1px solid #24242a" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 30, fontWeight: 600 }}>
                <div style={{ width: 14, height: 14, borderRadius: 7, background: t.color }} />
                {t.name}
              </div>
              <div style={{ display: "flex", fontSize: 22, color: "#a3a3ad" }}>{t.line}</div>
            </div>
          ))}
        </div>
      </div>
    ),
    size,
  );
}
