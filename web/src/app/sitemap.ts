import type { MetadataRoute } from "next";
import { PLATFORMS } from "@/lib/platforms";
import { SITE } from "@/lib/site";

const UPDATED = new Date("2026-11-05");

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: SITE.url, lastModified: UPDATED, changeFrequency: "weekly", priority: 1 },
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
