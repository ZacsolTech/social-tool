import type { MetadataRoute } from "next";
import { SITE } from "@/lib/site";

export default function manifest(): MetadataRoute.Manifest {
  return {
    name: `${SITE.name}: Video Downloader`,
    short_name: SITE.name,
    description: SITE.description,
    start_url: "/?source=pwa",
    scope: "/",
    display: "standalone",
    background_color: "#f7f6f2",
    theme_color: "#ff4f1f",
    categories: ["utilities", "productivity", "photo"],
    icons: [
      { src: "/icon.svg", sizes: "any", type: "image/svg+xml" },
      { src: "/pwa-icon/192", sizes: "192x192", type: "image/png" },
      { src: "/pwa-icon/512", sizes: "512x512", type: "image/png" },
      { src: "/pwa-icon/maskable-512", sizes: "512x512", type: "image/png", purpose: "maskable" },
    ],
    // Android share sheet: "Share → Klypsy" opens /?url=…&text=… and the download starts by itself.
    share_target: {
      action: "/",
      method: "GET",
      params: { title: "title", text: "text", url: "url" },
    },
    shortcuts: [
      { name: "TikTok downloader", url: "/tiktok-video-downloader" },
      { name: "Instagram downloader", url: "/instagram-reels-downloader" },
    ],
  };
}
