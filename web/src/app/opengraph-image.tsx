import { ImageResponse } from "next/og";
import { SITE } from "@/lib/site";

export const alt = `${SITE.name}: download social videos without watermark`;
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

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
        <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
          <div style={{ fontSize: 84, fontWeight: 700, letterSpacing: -3, lineHeight: 1.02 }}>Download any social video.</div>
          <div style={{ fontSize: 84, fontWeight: 700, letterSpacing: -3, lineHeight: 1.02, color: "#ff6a3d" }}>Without the junk.</div>
        </div>
        <div style={{ display: "flex", gap: 16, fontSize: 28, color: "#a3a3ad" }}>
          YouTube · TikTok · Instagram · Facebook · X · Reddit · No watermark · No pop-ups
        </div>
      </div>
    ),
    size,
  );
}
