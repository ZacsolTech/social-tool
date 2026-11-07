import Link from "next/link";
import { Logo } from "./Logo";
import { ThemeToggle } from "./ThemeToggle";

const NAV = [
  { href: "/youtube-video-downloader", label: "YouTube" },
  { href: "/tiktok-video-downloader", label: "TikTok" },
  { href: "/instagram-reels-downloader", label: "Instagram" },
  { href: "/facebook-video-downloader", label: "Facebook" },
  { href: "/twitter-video-downloader", label: "X" },
  { href: "/#tools", label: "Tools" },
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
