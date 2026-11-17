import type { MetadataRoute } from "next";
import { PLATFORMS } from "@/lib/platforms";
import { SITE } from "@/lib/site";
import { TOOL_PAGES } from "@/lib/tools";

const UPDATED = new Date("2026-11-05");
const TOOLS_UPDATED = new Date("2026-11-17");

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: SITE.url, lastModified: UPDATED, changeFrequency: "weekly", priority: 1 },
    ...TOOL_PAGES.map((t) => ({
      url: `${SITE.url}/${t.slug}`,
      lastModified: TOOLS_UPDATED,
      changeFrequency: "weekly" as const,
      priority: 0.9,
    })),
    ...PLATFORMS.map((p) => ({
      url: `${SITE.url}/${p.slug}`,
      lastModified: UPDATED,
      changeFrequency: "weekly" as const,
      priority: 0.9,
    })),
    ...["about", "contact", "privacy", "terms", "dmca"].map((s) => ({
      url: `${SITE.url}/${s}`,
      lastModified: UPDATED,
      changeFrequency: "yearly" as const,
      priority: 0.3,
    })),
  ];
}
