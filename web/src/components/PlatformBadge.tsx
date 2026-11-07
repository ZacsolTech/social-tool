import type { Platform } from "@/lib/platforms";

const MARK: Record<string, string> = {
  youtube: "Yt",
  tiktok: "Tk",
  instagram: "Ig",
  facebook: "f",
  x: "X",
  reddit: "R",
  pinterest: "P",
  dailymotion: "D",
  twitch: "Tw",
};

/** Simple monogram badge (we don't ship platform logos). */
export function PlatformBadge({ platform, size = 28 }: { platform: Pick<Platform, "id" | "color" | "name">; size?: number }) {
  return (
    <span
      aria-hidden
      className="inline-grid shrink-0 place-items-center rounded-lg font-semibold text-white"
      style={{
        width: size,
        height: size,
        background: platform.color,
        fontSize: size * 0.42,
        letterSpacing: "-0.02em",
        boxShadow: "inset 0 0 0 1px rgba(255,255,255,0.12)",
      }}
    >
      {MARK[platform.id] ?? platform.name[0]}
    </span>
  );
}
