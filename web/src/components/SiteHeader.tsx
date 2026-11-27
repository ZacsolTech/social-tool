import Link from "next/link";
import { CAPTIONS_SLUG } from "@/lib/captionTools";
import { CLIPS_SLUG } from "@/lib/clipTools";
import { REFRAME_SLUG } from "@/lib/tools";
import { Logo } from "./Logo";
import { ThemeToggle } from "./ThemeToggle";

const NAV = [
  { href: "/youtube-video-downloader", label: "YouTube" },
  { href: "/tiktok-video-downloader", label: "TikTok" },
  { href: "/instagram-reels-downloader", label: "Instagram" },
  { href: `/${CLIPS_SLUG}`, label: "AI Clips" },
  { href: `/${CAPTIONS_SLUG}`, label: "Captions" },
  { href: `/${REFRAME_SLUG}`, label: "Reframe 9:16" },
];

export function SiteHeader() {
  return (
    <header className="sticky top-0 z-40 border-b border-line/70 bg-bg/80 backdrop-blur-xl">
      <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-4 px-4 sm:h-16 sm:px-6">
        <Logo />
        <nav aria-label="Main" className="hidden items-center gap-1 text-sm md:flex">
          {NAV.map((n) => (
            <Link key={n.href} href={n.href} className="rounded-full px-3 py-1.5 text-muted transition hover:bg-line hover:text-fg">
              {n.label}
            </Link>
          ))}
        </nav>
        <div className="flex items-center gap-1">
          <Link
            href={`/${CLIPS_SLUG}`}
            className="whitespace-nowrap rounded-full bg-accent-soft px-3 py-1.5 text-sm font-medium text-accent transition hover:brightness-95 md:hidden"
          >
            AI Clips
          </Link>
          <Link
            href={`/${CAPTIONS_SLUG}`}
            className="whitespace-nowrap rounded-full px-2 py-1.5 text-sm font-medium text-muted transition hover:text-fg md:hidden"
          >
            Captions
          </Link>
          <Link
            href={`/${REFRAME_SLUG}`}
            className="hidden whitespace-nowrap rounded-full px-2 py-1.5 text-sm font-medium text-muted transition hover:text-fg min-[400px]:inline-block md:hidden"
          >
            9:16
          </Link>
          <ThemeToggle />
          <Link
            href="/#faq"
            className="hidden rounded-full border border-line-strong px-3.5 py-1.5 text-sm font-medium transition hover:border-fg sm:inline-block"
          >
            How it works
          </Link>
        </div>
      </div>
    </header>
  );
}
