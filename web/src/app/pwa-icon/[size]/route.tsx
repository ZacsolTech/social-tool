import { ImageResponse } from "next/og";

const SIZES = ["192", "512", "maskable-512", "apple-180"] as const;

export function generateStaticParams() {
  return SIZES.map((size) => ({ size }));
}

/** PNG app icons for the PWA manifest / iOS home screen, generated at build time. */
export async function GET(_req: Request, ctx: RouteContext<"/pwa-icon/[size]">) {
  const { size } = await ctx.params;
  if (!SIZES.includes(size as (typeof SIZES)[number])) return new Response("Not found", { status: 404 });
  const px = size === "apple-180" ? 180 : size === "192" ? 192 : 512;
  const maskable = size.startsWith("maskable") || size.startsWith("apple");
  const inner = maskable ? px * 0.62 : px;
  return new ImageResponse(
    (
      <div style={{ width: px, height: px, display: "flex", alignItems: "center", justifyContent: "center", background: maskable ? "#ff4f1f" : "transparent" }}>
        <svg width={inner} height={inner} viewBox="0 0 32 32">
          {!maskable && <rect width="32" height="32" rx="9" fill="#ff4f1f" />}
          <path d="M12 9.5v13l11-6.5-11-6.5Z" fill="#fff" />
          <path d="M8 24.5h16" stroke="#fff" strokeWidth="2.2" strokeLinecap="round" opacity=".55" />
        </svg>
      </div>
    ),
    { width: px, height: px },
  );
}
