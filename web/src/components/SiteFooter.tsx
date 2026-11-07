import Link from "next/link";
import { PLATFORMS } from "@/lib/platforms";
import { SITE } from "@/lib/site";
import { Logo } from "./Logo";

export function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-line">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-12 sm:px-6 md:grid-cols-[1.4fr_1fr_1fr]">
        <div className="max-w-sm">
          <Logo />
          <p className="mt-3 text-sm text-muted">{SITE.tagline}</p>
          <p className="mt-4 text-xs leading-relaxed text-subtle">
            {SITE.name} is not affiliated with YouTube, Google, TikTok, Instagram, Meta, X, Reddit, Pinterest or any other platform. Only
            download content you own or have permission to use.
          </p>
        </div>
        <div>
          <h2 className="text-sm font-semibold">Downloaders</h2>
          <ul className="mt-3 space-y-2 text-sm text-muted">
            {PLATFORMS.map((p) => (
              <li key={p.id}>
                <Link href={`/${p.slug}`} className="transition hover:text-fg">
                  {p.name} downloader
                </Link>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h2 className="text-sm font-semibold">Company</h2>
          <ul className="mt-3 space-y-2 text-sm text-muted">
            {[
              ["/about", "About"],
              ["/contact", "Contact"],
              ["/privacy", "Privacy policy"],
              ["/terms", "Terms of service"],
              ["/dmca", "Copyright & DMCA"],
            ].map(([href, label]) => (
              <li key={href}>
                <Link href={href} className="transition hover:text-fg">
                  {label}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </div>
      <div className="border-t border-line">
        <p className="mx-auto max-w-6xl px-4 py-5 text-xs text-subtle sm:px-6">
          © {SITE.year} {SITE.name}. Downloads stream straight to you. We never store your files.
        </p>
      </div>
    </footer>
  );
}
