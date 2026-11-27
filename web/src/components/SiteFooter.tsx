import Link from "next/link";
import { TOOLS } from "@/lib/catalog";
import { SITE } from "@/lib/site";
import { Logo } from "./Logo";
import { ToolTile } from "./ToolIcon";

export function SiteFooter() {
  return (
    <footer className="mt-24 border-t border-line">
      <div className="mx-auto grid max-w-6xl gap-10 px-4 py-12 sm:grid-cols-2 sm:px-6 lg:grid-cols-[1.5fr_repeat(5,1fr)]">
        <div className="max-w-sm">
          <Logo />
          <p className="mt-3 text-sm text-muted">{SITE.tagline}</p>
          <p className="mt-4 text-xs leading-relaxed text-subtle">
            {SITE.name} is not affiliated with YouTube, Google, TikTok, Instagram, Meta, X, Reddit, Pinterest or any other platform. Only
            download or edit content you own or have permission to use.
          </p>
        </div>
        {TOOLS.map((t) => (
          <div key={t.id}>
            <h2 className="flex items-center gap-2 text-sm font-semibold">
              <ToolTile tool={t} size="sm" />
              <Link href={t.href} className="transition hover:text-accent">
                {t.name}
              </Link>
            </h2>
            <ul className="mt-3 space-y-2 text-sm text-muted">
              {t.pages.map((p) => (
                <li key={p.href}>
                  <Link href={p.href} className="transition hover:text-fg">
                    {p.label}
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        ))}
        <div>
          <h2 className="flex h-8 items-center text-sm font-semibold">Company</h2>
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
          © {SITE.year} {SITE.name}. Free video tools for creators. Downloads stream straight to you; uploaded videos are deleted
          automatically within 24 hours.
        </p>
      </div>
    </footer>
  );
}
