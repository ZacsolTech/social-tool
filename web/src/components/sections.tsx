import {
  ArrowRight,
  AudioLines,
  Ban,
  Check,
  ChevronDown,
  ChevronRight,
  ClipboardPaste,
  Gauge,
  Languages,
  Layers,
  MousePointerClick,
  Share2,
  ShieldCheck,
  Smartphone,
  Sparkles,
  Workflow as WorkflowIcon,
  X as XIcon,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { type CatalogTool, FEATURED, SECONDARY, type ToolId, UPCOMING, WORKFLOW, toolById } from "@/lib/catalog";
import type { Faq } from "@/lib/content";
import { PLATFORMS, type PlatformId } from "@/lib/platforms";
import { SITE } from "@/lib/site";
import { Downloader } from "./downloader/Downloader";
import { JsonLd } from "./JsonLd";
import { PlatformBadge } from "./PlatformBadge";
import { TrustRow } from "./marketing";
import { TOOL_ICONS, ToolTile } from "./ToolIcon";

/* ------------------------------------------------------------------ hero */

export function Hero({
  title,
  highlight,
  subtitle,
  platformHint,
  badge = "Free · No watermark · No sign-up · No pop-ups",
  crumbs,
  children,
}: {
  title: string;
  highlight: string;
  subtitle: string;
  platformHint?: PlatformId;
  badge?: string;
  /** breadcrumbs above the badge (downloader pages) */
  crumbs?: { href: string; label: string }[];
  /** shown under the downloader (the home page lists the other tools there) */
  children?: React.ReactNode;
}) {
  const [before, after] = title.split(highlight);
  return (
    <section className="relative overflow-hidden">
      <div aria-hidden className="aurora pointer-events-none absolute inset-0" />
      <div aria-hidden className="grid-dots pointer-events-none absolute inset-0 opacity-60" />
      <div className={`relative mx-auto max-w-3xl px-4 pb-10 sm:px-6 ${crumbs ? "pt-6 sm:pt-10" : "pt-12 sm:pt-20"}`}>
        {crumbs && (
          <div className="mb-6 sm:mb-8">
            <Breadcrumbs items={crumbs} />
          </div>
        )}
        <div className="flex justify-center">
          <span className="inline-flex items-center gap-2 rounded-full border border-line bg-elev/80 px-3 py-1 text-xs font-medium text-muted backdrop-blur">
            <span className="size-1.5 rounded-full bg-ok" />
            {badge}
          </span>
        </div>
        <h1 className="mt-5 text-balance text-center text-4xl font-semibold leading-[1.05] tracking-[-0.035em] sm:text-6xl">
          {before}
          {after !== undefined && (
            <span className="font-display text-[1.08em] font-normal italic tracking-[-0.01em] text-accent">{highlight}</span>
          )}
          {after}
        </h1>
        <p className="mx-auto mt-4 max-w-xl text-pretty text-center text-base text-muted sm:text-lg">{subtitle}</p>

        <div className="mt-8">
          <Downloader platformHint={platformHint} />
        </div>

        <div className="mt-6 flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-xs text-subtle">
          <span className="inline-flex items-center gap-1.5">
            <kbd className="rounded border border-line-strong bg-elev px-1.5 py-0.5 font-mono text-[11px] text-muted">Ctrl</kbd>
            <kbd className="rounded border border-line-strong bg-elev px-1.5 py-0.5 font-mono text-[11px] text-muted">V</kbd>
            anywhere to paste & go
          </span>
          <span aria-hidden className="hidden sm:inline">·</span>
          <span className="inline-flex items-center gap-1.5">
            <Share2 className="size-3.5" /> On mobile: Install, then share links straight to {SITE.name}
          </span>
        </div>
        {children}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------- platforms */

export function PlatformStrip({ current }: { current?: PlatformId }) {
  return (
    <section aria-label="Supported platforms" className="mx-auto max-w-5xl px-4 sm:px-6">
      <div className="flex flex-wrap justify-center gap-2">
        {PLATFORMS.map((p) => (
          <Link
            key={p.id}
            href={`/${p.slug}`}
            aria-current={current === p.id ? "page" : undefined}
            className="inline-flex items-center gap-2 rounded-full border border-line bg-elev py-1 pl-1 pr-3.5 text-sm transition hover:border-line-strong aria-[current=page]:border-fg"
          >
            <PlatformBadge platform={p} size={24} />
            {p.short}
          </Link>
        ))}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------ how it works */

export function HowItWorks({ steps, platformName, title }: { steps?: string[]; platformName?: string; title?: string }) {
  const defaults = [
    "Copy the link of any public video from YouTube, TikTok, Instagram, Facebook, X and more.",
    "Paste it above, or press Ctrl+V anywhere. We detect the platform instantly.",
    "Pick HD MP4, MP3 or cover image. It downloads straight to your browser or IDM.",
  ];
  const icons = [MousePointerClick, ClipboardPaste, Zap];
  const list = steps ?? defaults;
  return (
    <section className="mx-auto max-w-6xl px-4 pt-24 sm:px-6">
      <SectionHeading
        eyebrow="How it works"
        title={title ?? (platformName ? `Download ${platformName} videos in 3 steps` : "Three steps. About five seconds.")}
      />
      <ol className="mt-10 grid gap-4 md:grid-cols-3">
        {list.map((s, i) => {
          const Icon = icons[i] ?? Zap;
          return (
            <li key={i} className="reveal relative rounded-3xl border border-line bg-elev p-6">
              <span className="font-display text-5xl italic leading-none text-accent/30">{i + 1}</span>
              <Icon className="absolute right-6 top-6 size-5 text-subtle" />
              <p className="mt-4 text-pretty text-[15px] leading-relaxed">{s}</p>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

/* --------------------------------------------------------------- features */

/** What the downloader does better (downloader pages). */
export function Features() {
  return (
    <section className="mx-auto max-w-6xl px-4 pt-24 sm:px-6">
      <SectionHeading eyebrow={`Why ${SITE.name}`} title="Everything the other sites get wrong, fixed." />
      <div className="mt-10 grid auto-rows-[minmax(170px,auto)] gap-4 md:grid-cols-6">
        <Bento className="md:col-span-4" icon={Ban} title="No pop-ups. No fake buttons. Ever.">
          Most downloader sites hide the real button between ads and redirect you to spam. Here there is one input and your file.
          That&apos;s it.
          <div className="mt-5 flex flex-wrap gap-2 text-xs">
            {["0 pop-unders", "0 redirects", "0 fake download buttons", "No sign-up"].map((t) => (
              <span key={t} className="inline-flex items-center gap-1 rounded-full bg-ok/10 px-2.5 py-1 font-medium text-ok">
                <Check className="size-3" /> {t}
              </span>
            ))}
          </div>
        </Bento>
        <Bento className="md:col-span-2" icon={Sparkles} title="No watermark, HD">
          We pick the original, highest-quality file that plays on every phone.
        </Bento>
        <Bento className="md:col-span-2" icon={Gauge} title="Instant, native downloads">
          Files go straight to your browser&apos;s download bar or IDM. No waiting on our page, resume supported.
        </Bento>
        <Bento className="md:col-span-2" icon={Layers} title="Carousels & threads">
          Posts with several videos? Download one, or all of them in one tap.
        </Bento>
        <Bento className="md:col-span-2" icon={AudioLines} title="MP3 & cover image">
          Save the sound as 192 kbps MP3 or grab the cover image in full size.
        </Bento>
        <Bento className="md:col-span-3" icon={Share2} title={`Share from the app, straight to ${SITE.name}`}>
          Install {SITE.name} on your phone (a tiny web app, no app store needed). Then in TikTok or Instagram tap Share → {SITE.name}. The download
          starts on its own.
        </Bento>
        <Bento className="md:col-span-3" icon={ShieldCheck} title="Private by design">
          Downloads stream straight to you and are never stored on our servers. Your recent links stay in your browser only. We don&apos;t keep galleries and we
          don&apos;t track what you download.
        </Bento>
      </div>
    </section>
  );
}

/** What all the tools share (home page). */
export function StudioFeatures() {
  return (
    <section className="mx-auto max-w-6xl px-4 pt-24 sm:px-6">
      <SectionHeading eyebrow={`Why ${SITE.name}`} title="What paid creator apps charge for. Free." />
      <div className="mt-10 grid auto-rows-[minmax(170px,auto)] gap-4 md:grid-cols-6">
        <Bento className="md:col-span-4" icon={Ban} title="No watermark. No sign-up. No pop-ups.">
          Every tool is free to use without an account, and nothing you make gets our logo stamped on it. No fake download buttons, no
          redirects, no &quot;upgrade to export&quot;.
          <div className="mt-5 flex flex-wrap gap-2 text-xs">
            {["0 watermarks", "0 pop-ups", "No account", "HD exports"].map((t) => (
              <span key={t} className="inline-flex items-center gap-1 rounded-full bg-ok/10 px-2.5 py-1 font-medium text-ok">
                <Check className="size-3" /> {t}
              </span>
            ))}
          </div>
        </Bento>
        <Bento className="md:col-span-2" icon={Sparkles} title="Captions heard twice">
          Two AI models listen, an AI judge settles where they differ and flags anything still unsure. You fix a line, not the whole
          video.
        </Bento>
        <Bento className="md:col-span-2" icon={Languages} title="Urdu & Hindi, first-class">
          Nastaliq, Roman Urdu, Hindi, Hinglish and Arabic right-to-left, plus 40+ languages. Titles in your own language.
        </Bento>
        <Bento className="md:col-span-2" icon={WorkflowIcon} title="Tools that hand off">
          Download, clip, reframe and caption in one flow. The video and its words move along with you.
        </Bento>
        <Bento className="md:col-span-2" icon={Gauge} title="Fast on any device">
          The heavy AI work runs on our servers. Your phone or old laptop only uploads and downloads.
        </Bento>
        <Bento className="md:col-span-3" icon={Smartphone} title="Works like an app on your phone">
          Install {SITE.name} from the browser (no app store). Then in TikTok or Instagram tap Share → {SITE.name} and it opens here.
        </Bento>
        <Bento className="md:col-span-3" icon={ShieldCheck} title="Private by design">
          Downloads stream straight to you and are never stored. Videos you upload are processed privately, never used to train AI, and
          deleted automatically within 24 hours.
        </Bento>
      </div>
    </section>
  );
}

function Bento({
  icon: Icon,
  title,
  children,
  className = "",
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <div className={`reveal rounded-3xl border border-line bg-elev p-6 ${className}`}>
      <span className="grid size-10 place-items-center rounded-xl bg-accent-soft text-accent">
        <Icon className="size-5" />
      </span>
      <h3 className="mt-4 text-lg font-semibold tracking-tight">{title}</h3>
      <div className="mt-1.5 text-pretty text-[15px] leading-relaxed text-muted">{children}</div>
    </div>
  );
}

/* ------------------------------------------------------------- comparison */

type Row = [string, boolean | string, boolean | string];

/** The downloader against typical downloader sites (downloader pages). */
export function Comparison() {
  const rows: Row[] = [
    ["Pop-up & redirect ads", false, "Common"],
    ["Fake download buttons", false, "Common"],
    ["No watermark (TikTok)", true, "Sometimes"],
    ["Works with IDM & download managers", true, "Sometimes"],
    ["Carousel / multi-video posts", true, "Rare"],
    ["Reddit videos with sound", true, "Rare"],
    ["Share-to-app on mobile", true, false],
    ["Turn the video into Shorts with AI", true, false],
    ["Stores your files", false, "Often"],
  ];
  return <CompareTable title={`${SITE.name} vs. typical downloader sites`} rows={rows} other="Others" />;
}

/** Klyprima against typical paid clipping and caption apps (home page). */
export function StudioComparison() {
  const rows: Row[] = [
    ["Price", "Free", "$10–30 / month"],
    ["Watermark on free exports", false, "Usually"],
    ["Account needed", false, true],
    ["Long video → scored viral clips", true, "Paid plans"],
    ["Captions checked by two AI models", true, false],
    ["Urdu Nastaliq & Roman Urdu captions", true, "Rare"],
    ["Speaker-tracking 9:16 reframe", true, "Paid plans"],
    ["Downloader built in", true, false],
  ];
  return <CompareTable title={`${SITE.name} vs. paid clipping apps`} rows={rows} other="Typical apps" />;
}

function CompareTable({ title, rows, other }: { title: string; rows: Row[]; other: string }) {
  const cell = (v: boolean | string, good: boolean) =>
    typeof v === "string" ? (
      <span className={good ? "font-medium" : "text-muted"}>{v}</span>
    ) : v ? (
      <Check className={`mx-auto size-5 ${good ? "text-ok" : "text-muted"}`} aria-label="Yes" />
    ) : (
      <XIcon className={`mx-auto size-5 ${good ? "text-ok" : "text-subtle"}`} aria-label="No" />
    );
  return (
    <section className="mx-auto max-w-4xl px-4 pt-24 sm:px-6">
      <SectionHeading eyebrow="Compared" title={title} />
      <div className="mt-10 overflow-hidden rounded-3xl border border-line bg-elev">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left">
              <th className="p-4 font-medium text-muted">Feature</th>
              <th className="w-28 p-4 text-center font-semibold sm:w-36">{SITE.name}</th>
              <th className="w-28 p-4 text-center font-medium text-muted sm:w-36">{other}</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(([label, ours, theirs]) => (
              <tr key={label} className="border-b border-line last:border-0">
                <td className="p-4">{label}</td>
                <td className="bg-accent-soft/40 p-4 text-center">{cell(ours, true)}</td>
                <td className="p-4 text-center">{cell(theirs, false)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------- the tools */

/** The secondary tools as compact cards (under the home hero). */
export function ToolChips({ title = `Also free on ${SITE.name}` }: { title?: string }) {
  return (
    <div className="mx-auto mt-10 max-w-4xl border-t border-line/70 pt-6">
      <p className="text-center text-xs font-semibold uppercase tracking-[0.16em] text-subtle">{title}</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-3">
        {SECONDARY.map((t) => (
          <Link
            key={t.id}
            href={t.href}
            className={`group flex items-center gap-3 rounded-2xl border border-line bg-elev/80 p-3 backdrop-blur transition hover:-translate-y-0.5 ${t.tone.ring}`}
          >
            <ToolTile tool={t} />
            <span className="min-w-0 flex-1">
              <span className="block text-sm font-semibold tracking-tight">{t.name}</span>
              <span className="block text-xs leading-snug text-muted">{t.tagline}</span>
            </span>
            <ChevronRight className="size-4 shrink-0 text-subtle transition group-hover:translate-x-0.5" />
          </Link>
        ))}
      </div>
    </div>
  );
}

/** A small picture of what AI Clips makes: three vertical clips with their virality scores. */
function ClipsMock() {
  const clips = [
    { score: 94, hook: "Nobody tells you this", g: "from-violet-500 to-fuchsia-500" },
    { score: 88, hook: "The rule that changed everything", g: "from-amber-400 to-orange-500" },
    { score: 81, hook: "Never hire your friends", g: "from-sky-500 to-indigo-500" },
  ];
  return (
    <div aria-hidden className="flex items-end justify-center gap-3">
      {clips.map((c, i) => (
        <div
          key={c.score}
          className={`relative aspect-[9/16] w-[30%] max-w-36 overflow-hidden rounded-2xl bg-gradient-to-br ${c.g} shadow-card ${i === 1 ? "-translate-y-4" : ""}`}
        >
          <span className="absolute left-2 top-2 rounded-full bg-black/55 px-2 py-0.5 text-[11px] font-bold text-white">{c.score}</span>
          <span className="absolute inset-x-2 top-9 text-center text-[11px] font-extrabold uppercase leading-tight text-white drop-shadow">{c.hook}</span>
          <span className="absolute inset-x-3 bottom-8 rounded bg-black/55 py-1 text-center text-[10px] font-bold text-amber-300">word by word</span>
          <span className="absolute inset-x-0 bottom-0 h-1 bg-white/30">
            <span className="block h-full w-2/3 bg-white" />
          </span>
        </div>
      ))}
    </div>
  );
}

/** The main tool, big: what it does, why, and a picture of the result. */
function FeaturedCard({ tool }: { tool: CatalogTool }) {
  return (
    <Link
      href={tool.href}
      className={`glow-card reveal group grid gap-8 overflow-hidden rounded-[2rem] p-6 shadow-card transition hover:-translate-y-0.5 sm:p-8 lg:grid-cols-[1.1fr_1fr] lg:items-center`}
    >
      <div>
        <div className="flex flex-wrap items-center gap-3">
          <ToolTile tool={tool} size="lg" />
          <span className="rounded-full bg-violet-500/12 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-violet-600 dark:text-violet-300">
            Our main tool
          </span>
          <span className="rounded-full bg-ok/15 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-ok">Free</span>
        </div>
        <h3 className="mt-5 text-3xl font-semibold tracking-tight sm:text-4xl">{tool.name}</h3>
        <p className={`mt-1 text-lg font-medium ${tool.tone.text}`}>{tool.tagline}</p>
        <p className="mt-3 max-w-xl text-pretty text-[15px] leading-relaxed text-muted">{tool.body}</p>
        <ul className="mt-5 grid gap-2 text-sm sm:grid-cols-2">
          {tool.points.map((pt) => (
            <li key={pt} className="flex items-center gap-2">
              <Check className="size-4 shrink-0 text-ok" /> {pt}
            </li>
          ))}
        </ul>
        <span className="mt-7 inline-flex items-center gap-1.5 rounded-full bg-accent px-5 py-2.5 text-sm font-semibold text-accent-fg transition group-hover:brightness-105">
          {tool.cta} <ArrowRight className="size-4 transition group-hover:translate-x-0.5" />
        </span>
      </div>
      <ClipsMock />
    </Link>
  );
}

function ToolCard({ tool }: { tool: CatalogTool }) {
  return (
    <Link
      href={tool.href}
      className={`reveal group flex flex-col rounded-3xl border border-line bg-elev p-6 shadow-card transition hover:-translate-y-0.5 ${tool.tone.ring}`}
    >
      <div className="flex items-start justify-between gap-3">
        <ToolTile tool={tool} size="lg" />
        <span className="rounded-full bg-ok/15 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-ok">Free</span>
      </div>
      <h3 className="mt-5 text-xl font-semibold tracking-tight">{tool.name}</h3>
      <p className={`text-sm font-medium ${tool.tone.text}`}>{tool.tagline}</p>
      <p className="mt-2 text-pretty text-[15px] leading-relaxed text-muted">{tool.body}</p>
      <ul className="mt-4 grid gap-1.5 text-sm">
        {tool.points.map((pt) => (
          <li key={pt} className="flex items-center gap-2">
            <Check className="size-3.5 shrink-0 text-ok" /> {pt}
          </li>
        ))}
      </ul>
      <span className="mt-auto inline-flex items-center gap-1 pt-5 text-sm font-semibold">
        {tool.cta} <ArrowRight className="size-4 transition group-hover:translate-x-0.5" />
      </span>
    </Link>
  );
}

/** The tools: the main one (AI Clips) big on top, the others below. `exclude` leaves the current tool out. */
export function ToolsShowcase({
  exclude,
  eyebrow = "The tools",
  title = "One studio, from long video to ready-to-post Shorts.",
}: {
  exclude?: ToolId;
  eyebrow?: string;
  title?: string;
}) {
  const featured = FEATURED.id !== exclude ? FEATURED : null;
  const others = SECONDARY.filter((t) => t.id !== exclude);
  return (
    <section id="tools" className="mx-auto max-w-6xl scroll-mt-24 px-4 pt-24 sm:px-6">
      <SectionHeading eyebrow={eyebrow} title={title} />
      {featured && (
        <div className="mt-10">
          <FeaturedCard tool={featured} />
        </div>
      )}
      {featured && others.length > 0 && (
        <p className="mt-10 text-center text-xs font-semibold uppercase tracking-[0.16em] text-subtle">More free tools</p>
      )}
      <div className={`grid gap-4 sm:grid-cols-2 ${others.length >= 3 ? "lg:grid-cols-3" : ""} ${featured ? "mt-4" : "mt-10"}`}>
        {others.map((t) => (
          <ToolCard key={t.id} tool={t} />
        ))}
      </div>
      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        {UPCOMING.map((u) => (
          <div key={u.name} className="flex min-w-0 items-center gap-3 rounded-2xl border border-dashed border-line-strong px-4 py-3 text-sm">
            <span className="rounded-full bg-line px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted">Soon</span>
            <span className="shrink-0 font-medium">
              {SITE.name} {u.name}
            </span>
            <span className="truncate text-muted">{u.body}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

/** The creator workflow: each tool hands its video to the next, no re-uploading. */
export function Workflow() {
  const steps: Record<ToolId, string> = {
    download: "Paste a link. Save it in HD, or send it straight on.",
    clips: "AI picks the moments worth posting and scores them.",
    reframe: "Every clip goes 9:16 with the speaker in frame.",
    captions: "Accurate, animated captions in your language.",
  };
  return (
    <section className="mx-auto max-w-6xl px-4 pt-24 sm:px-6">
      <SectionHeading eyebrow="How it fits together" title="Link in. Shorts out. No re-uploading." />
      <ol className="mt-10 grid gap-3 md:grid-cols-4">
        {WORKFLOW.map((id, i) => {
          const t = toolById(id);
          const Icon = TOOL_ICONS[id];
          return (
            <li key={id} className="relative">
              <Link
                href={t.href}
                className={`group flex h-full flex-col rounded-3xl border bg-elev p-5 transition ${t.tone.ring} ${t.featured ? "border-violet-500/50 shadow-card" : "border-line"}`}
              >
                <div className="flex items-center justify-between">
                  <span className="font-display text-4xl italic leading-none text-subtle/60">{i + 1}</span>
                  <span className={`grid size-9 place-items-center rounded-xl ${t.tone.tile}`}>
                    <Icon className="size-4" />
                  </span>
                </div>
                <h3 className="mt-4 flex items-center gap-2 font-semibold tracking-tight">
                  {t.name}
                  {t.featured && (
                    <span className="rounded-full bg-violet-500/12 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-violet-600 dark:text-violet-300">
                      Main
                    </span>
                  )}
                </h3>
                <p className="mt-1 text-sm leading-relaxed text-muted">{steps[id]}</p>
              </Link>
              {i < WORKFLOW.length - 1 && (
                <ArrowRight
                  aria-hidden
                  className="absolute -right-3 top-1/2 z-10 hidden size-6 -translate-y-1/2 rounded-full border border-line bg-bg p-1 text-subtle md:block"
                />
              )}
            </li>
          );
        })}
      </ol>
      <p className="mx-auto mt-5 max-w-2xl text-pretty text-center text-sm text-muted">
        Every result has a button for the next step: a downloaded video opens in AI Clips or Reframe, a clip opens in the caption editor
        with its words already there.
      </p>
    </section>
  );
}

/* --------------------------------------------------------------------- tips */

export function Tips({ tips }: { tips: { title: string; body: string }[] }) {
  return (
    <section className="mx-auto max-w-6xl px-4 pt-24 sm:px-6">
      <div className="grid gap-4 md:grid-cols-3">
        {tips.map((t) => (
          <div key={t.title} className="rounded-3xl border border-line bg-elev p-6">
            <h3 className="font-semibold tracking-tight">{t.title}</h3>
            <p className="mt-1.5 text-[15px] leading-relaxed text-muted">{t.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

/* ---------------------------------------------------------------------- faq */

export function FaqSection({ faqs, title = "Questions, answered" }: { faqs: Faq[]; title?: string }) {
  return (
    <section id="faq" className="mx-auto max-w-3xl scroll-mt-24 px-4 pt-24 sm:px-6">
      <SectionHeading eyebrow="FAQ" title={title} />
      <div className="mt-10 divide-y divide-line rounded-3xl border border-line bg-elev">
        {faqs.map((f) => (
          <details key={f.q} className="group px-5 sm:px-6">
            <summary className="flex cursor-pointer items-center justify-between gap-4 py-5 font-medium">
              {f.q}
              <ChevronDown className="size-4 shrink-0 text-subtle transition group-open:rotate-180" />
            </summary>
            <p className="-mt-1 pb-5 text-[15px] leading-relaxed text-muted">{f.a}</p>
          </details>
        ))}
      </div>
    </section>
  );
}

export function faqJsonLd(faqs: Faq[]) {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: faqs.map((f) => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: f.a } })),
  };
}

/* ------------------------------------------------------------ tool pages */

/** Breadcrumbs (Klyprima › Tool › Page) with their structured data. */
export function Breadcrumbs({ items }: { items: { href: string; label: string }[] }) {
  const all = [{ href: "/", label: SITE.name }, ...items];
  return (
    <>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "BreadcrumbList",
          itemListElement: all.map((it, i) => ({ "@type": "ListItem", position: i + 1, name: it.label, item: `${SITE.url}${it.href}` })),
        }}
      />
      <nav aria-label="Breadcrumb" className="flex flex-wrap items-center justify-center gap-1 text-xs text-subtle">
        {all.map((it, i) => (
          <span key={it.href} className="inline-flex items-center gap-1">
            {i > 0 && <ChevronRight aria-hidden className="size-3" />}
            {i < all.length - 1 ? (
              <Link href={it.href} className="transition hover:text-fg">
                {it.label}
              </Link>
            ) : (
              <span aria-current="page" className="text-muted">
                {it.label}
              </span>
            )}
          </span>
        ))}
      </nav>
    </>
  );
}

/** Top of every AI tool page: breadcrumbs, the tool's badge, the headline, then the tool itself. */
export function ToolHero({
  tool,
  slug,
  label,
  h1,
  highlight,
  intro,
  children,
}: {
  tool: ToolId;
  slug: string;
  label: string;
  h1: string;
  highlight: string;
  intro: string;
  children: React.ReactNode;
}) {
  const t = toolById(tool);
  const [before, after] = h1.split(highlight);
  const href = `/${slug}`;
  const crumbs = href === t.href ? [{ href, label: t.name }] : [{ href: t.href, label: t.name }, { href, label }];
  return (
    <section className="relative overflow-hidden">
      <div aria-hidden className="aurora pointer-events-none absolute inset-0" />
      <div aria-hidden className="grid-dots pointer-events-none absolute inset-0 opacity-60" />
      <div className="relative mx-auto max-w-6xl px-4 pb-8 pt-6 sm:px-6 sm:pt-10">
        <Breadcrumbs items={crumbs} />
        <div className="mx-auto mt-6 max-w-3xl text-center sm:mt-8">
          <span className="inline-flex max-w-full items-center gap-2 rounded-full border border-line bg-elev/80 py-1 pl-1 pr-3 text-xs font-medium text-muted backdrop-blur">
            <ToolTile tool={t} size="sm" />
            <span className="truncate">
              <span className="font-semibold text-fg">
                {SITE.name} {t.name}
              </span>{" "}
              · Free · No watermark · No sign-up
            </span>
          </span>
          <h1 className="mt-5 text-balance text-4xl font-semibold leading-[1.05] tracking-[-0.035em] sm:text-6xl">
            {before}
            {after !== undefined && <span className="font-display text-[1.08em] font-normal italic tracking-[-0.01em] text-accent">{highlight}</span>}
            {after}
          </h1>
          <p className="mx-auto mt-4 max-w-2xl text-pretty text-base text-muted sm:text-lg">{intro}</p>
        </div>
        <div id="tool" className="mt-8 scroll-mt-24">
          {children}
        </div>
        {tool === "clips" && <TrustRow />}
      </div>
    </section>
  );
}

/** JSON-LD every tool page carries: the app, its how-to, its FAQ. */
export function ToolJsonLd({ name, slug, description, howTo, faqs, h1 }: { name: string; slug: string; description: string; howTo: string[]; faqs: Faq[]; h1: string }) {
  return (
    <>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "WebApplication",
          name: `${SITE.name} ${name}`,
          url: `${SITE.url}/${slug}`,
          applicationCategory: "MultimediaApplication",
          operatingSystem: "Any",
          description,
          offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
        }}
      />
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "HowTo",
          name: h1,
          step: howTo.map((text, i) => ({ "@type": "HowToStep", position: i + 1, text })),
        }}
      />
      <JsonLd data={faqJsonLd(faqs)} />
    </>
  );
}

/** Pills linking the tool's other pages (bottom of its landing pages). */
export function PageLinks({ tool, current }: { tool: ToolId; current: string }) {
  const t = toolById(tool);
  return (
    <section aria-label={`More ${t.name} pages`} className="mx-auto max-w-5xl px-4 pt-16 sm:px-6">
      <p className="text-center text-xs font-semibold uppercase tracking-[0.16em] text-subtle">More {t.name} pages</p>
      <div className="mt-3 flex flex-wrap justify-center gap-2">
        {t.pages
          .filter((p) => p.href !== `/${current}`)
          .map((p) => (
            <Link key={p.href} href={p.href} className="rounded-full border border-line bg-elev px-3.5 py-1.5 text-sm transition hover:border-line-strong">
              {p.label}
            </Link>
          ))}
      </div>
    </section>
  );
}

/* ------------------------------------------------------------------ shared */

export function SectionHeading({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div className="reveal mx-auto max-w-2xl text-center">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">{eyebrow}</p>
      <h2 className="mt-3 text-balance text-3xl font-semibold tracking-[-0.03em] sm:text-4xl">{title}</h2>
    </div>
  );
}
