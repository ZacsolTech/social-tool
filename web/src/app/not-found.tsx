import Link from "next/link";
import { ToolTile } from "@/components/ToolIcon";
import { TOOLS } from "@/lib/catalog";

export default function NotFound() {
  return (
    <div className="mx-auto max-w-3xl px-4 py-24 text-center sm:py-32">
      <p className="font-display text-7xl italic text-accent">404</p>
      <h1 className="mt-4 text-2xl font-semibold tracking-tight">This page doesn&apos;t exist</h1>
      <p className="mt-2 text-muted">Maybe the link was mistyped. Every tool is one click away.</p>
      <div className="mt-10 grid gap-3 text-left sm:grid-cols-2">
        {TOOLS.map((t) => (
          <Link key={t.id} href={t.href} className={`flex items-center gap-3 rounded-2xl border border-line bg-elev p-4 transition hover:-translate-y-0.5 ${t.tone.ring}`}>
            <ToolTile tool={t} />
            <span>
              <span className="block font-semibold tracking-tight">{t.name}</span>
              <span className="block text-sm text-muted">{t.tagline}</span>
            </span>
          </Link>
        ))}
      </div>
    </div>
  );
}
