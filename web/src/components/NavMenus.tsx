"use client";

import clsx from "clsx";
import { ChevronDown, Menu, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { FEATURED, TOOLS, type ToolId, toolOfSlug } from "@/lib/catalog";
import { TOOL_ICONS, ToolTile } from "./ToolIcon";

/** Phone menu: a button that opens every tool with its pages. */
export function MobileMenu() {
  const [open, setOpen] = useState(false);
  const path = usePathname();
  useEffect(() => setOpen(false), [path]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("keydown", onKey);
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = "";
    };
  }, [open]);

  return (
    <>
      <button
        type="button"
        aria-label={open ? "Close menu" : "Open menu"}
        aria-expanded={open}
        aria-controls="mobile-menu"
        onClick={() => setOpen((v) => !v)}
        className="grid size-9 place-items-center rounded-full border border-line text-muted transition hover:text-fg md:hidden"
      >
        {open ? <X className="size-4" /> : <Menu className="size-4" />}
      </button>
      {open &&
        createPortal(
          <div
            id="mobile-menu"
            className="animate-in fixed inset-x-0 bottom-0 top-14 z-30 overflow-y-auto border-t border-line bg-bg px-4 pb-10 pt-4 sm:top-16 md:hidden"
          >
            <nav aria-label="Tools" className="space-y-2">
              {TOOLS.map((t) => (
                <details
                  key={t.id}
                  open={t.featured}
                  className={clsx(
                    "group rounded-2xl border bg-elev",
                    t.featured ? "border-violet-500/50" : "border-line",
                  )}
                >
                  <summary className="flex cursor-pointer items-center gap-3 p-3">
                    <ToolTile tool={t} />
                    <span className="min-w-0 flex-1">
                      <span className="block font-semibold tracking-tight">
                        {t.name}
                      </span>
                      <span className="block text-xs text-muted">
                        {t.tagline}
                      </span>
                    </span>
                    <ChevronDown className="size-4 shrink-0 text-subtle transition group-open:rotate-180" />
                  </summary>
                  <div className="border-t border-line px-3 pb-3 pt-2">
                    <Link
                      href={t.href}
                      onClick={() => setOpen(false)}
                      className={clsx(
                        "mb-2 block rounded-xl px-3 py-2 text-center text-sm font-medium",
                        t.featured ? "bg-accent text-accent-fg" : "bg-fg text-bg",
                      )}
                    >
                      {t.cta}
                    </Link>
                    <ul className="grid grid-cols-2 gap-1 text-sm">
                      {t.pages.map((p) => (
                        <li key={p.href}>
                          <Link
                            href={p.href}
                            onClick={() => setOpen(false)}
                            className="block truncate rounded-lg px-2 py-1.5 text-muted hover:bg-bg hover:text-fg"
                          >
                            {p.label}
                          </Link>
                        </li>
                      ))}
                    </ul>
                  </div>
                </details>
              ))}
            </nav>
            <div className="mt-6 flex flex-wrap gap-x-5 gap-y-2 px-1 text-sm text-muted">
              {[
                ["/about", "About"],
                ["/contact", "Contact"],
                ["/privacy", "Privacy"],
                ["/terms", "Terms"],
              ].map(([href, label]) => (
                <Link
                  key={href}
                  href={href}
                  onClick={() => setOpen(false)}
                  className="hover:text-fg"
                >
                  {label}
                </Link>
              ))}
            </div>
          </div>,
          document.body,
        )}
    </>
  );
}

/** The tools as header links: the main one (AI Clips) as a filled pill, the page you're on marked. */
export function NavLinks() {
  const path = usePathname();
  const current = toolOfSlug(path.replace(/^\//, "")) ?? (path === "/" ? "clips" : null);
  return (
    <>
      {TOOLS.map((t) =>
        t.featured ? (
          <Link
            key={t.id}
            href={t.href}
            aria-current={current === t.id ? "page" : undefined}
            className="mr-1 inline-flex items-center gap-1.5 rounded-full bg-accent px-3.5 py-1.5 font-medium text-accent-fg shadow-sm transition hover:brightness-105"
          >
            <ToolIcon id={t.id} className="size-3.5" />
            {t.name}
          </Link>
        ) : (
          <Link
            key={t.id}
            href={t.href}
            aria-current={current === t.id ? "page" : undefined}
            className="inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-muted transition hover:bg-line hover:text-fg aria-[current=page]:bg-line aria-[current=page]:text-fg"
          >
            <span aria-hidden className={clsx("size-1.5 rounded-full", t.tone.dot)} />
            {t.short}
          </Link>
        ),
      )}
    </>
  );
}

/** Phone header: the main tool, always one tap away. */
export function MobileFeatured() {
  const t = FEATURED;
  return (
    <Link
      href={t.href}
      className="inline-flex items-center gap-1.5 whitespace-nowrap rounded-full bg-accent px-3 py-1.5 text-sm font-medium text-accent-fg md:hidden"
    >
      <ToolIcon id={t.id} className="size-3.5" />
      {t.name}
    </Link>
  );
}

function ToolIcon({ id, className }: { id: ToolId; className?: string }) {
  const Icon = TOOL_ICONS[id];
  return <Icon className={className} />;
}
