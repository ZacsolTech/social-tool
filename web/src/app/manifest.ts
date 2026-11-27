import type { MetadataRoute } from "next";
import { TOOLS } from "@/lib/catalog";
import { SITE } from "@/lib/site";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: `${SITE.name}: AI Clips & Video Tools`,
    short_name: SITE.name,
    description: SITE.description,
    start_url: "/?source=pwa",
    scope: "/",
    display: "standalone",
    background_color: "#f7f6f2",
    theme_color: "#ff4f1f",
    categories: ["photo", "productivity", "utilities"],
    icons: [
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml" },
      { src: "/pwa-icon/192", sizes: "192x192", type: "image/png" },
      { src: "/pwa-icon/512", sizes: "512x512", type: "image/png" },
      { src: "/pwa-icon/maskable-512", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    // Android share sheet: "Share → Klyprima" opens the downloader with ?url=…&text=… and it starts by itself.
    share_target: {
      action: "/video-downloader",
      method: "GET",
      params: { title: "title", text: "text", url: "url" },
    },
    shortcuts: TOOLS.map((t) => ({ name: t.name, short_name: t.short, description: t.tagline, url: t.href })),
  };
}
