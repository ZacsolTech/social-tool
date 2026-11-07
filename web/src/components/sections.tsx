import {
  AudioLines,
  Ban,
  Check,
  ChevronDown,
  ClipboardPaste,
  Combine,
  Crop,
  Gauge,
  Layers,
  MousePointerClick,
  Scissors,
  Share2,
  ShieldCheck,
  Sparkles,
  Subtitles,
  Wand2,
  X as XIcon,
  Zap,
} from "lucide-react";
import Link from "next/link";
import type { Faq } from "@/lib/content";
import { PLATFORMS, type PlatformId } from "@/lib/platforms";
import { SITE } from "@/lib/site";
import { Downloader } from "./downloader/Downloader";
import { PlatformBadge } from "./PlatformBadge";

/* ------------------------------------------------------------------ hero */

export function Hero({
  title,
  highlight,
  subtitle,
  platformHint,
}: {
  title: string;
  highlight: string;
  subtitle: string;
  platformHint?: PlatformId;
}) {
  const [before, after] = title.split(highlight);
  return (
    <section className="relative overflow-hidden">
      <div aria-hidden className="aurora pointer-events-none absolute inset-0" />
      <div aria-hidden className="grid-dots pointer-events-none absolute inset-0 opacity-60" />
      <div className="relative mx-auto max-w-3xl px-4 pb-10 pt-12 sm:px-6 sm:pt-20">
        <div className="flex justify-center">
          <span className="inline-flex items-center gap-2 rounded-full border border-line bg-elev/80 px-3 py-1 text-xs font-medium text-muted backdrop-blur">
            <span className="size-1.5 rounded-full bg-ok" />
            Free · No watermark · No sign-up · No pop-ups
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

export function HowItWorks({ steps, platformName }: { steps?: string[]; platformName?: string }) {
  const defaults = [
    "Copy the link of any public video from YouTube, TikTok, Instagram, Facebook, X and more.",
    "Paste it above, or press Ctrl+V anywhere. We detect the platform instantly.",
    "Pick HD MP4, MP3 or cover image. It downloads straight to your browser or IDM.",
  ];
  const icons = [MousePointerClick, ClipboardPaste, Zap];
  const list = steps ?? defaults;
  return (
    <section className="mx-auto max-w-6xl px-4 pt-24 sm:px-6">
      <SectionHeading eyebrow="How it works" title={platformName ? `Download ${platformName} videos in 3 steps` : "Three steps. About five seconds."} />
      <ol className="mt-10 grid gap-4 md:grid-cols-3">
        {list.map((s, i) => {
          const Icon = icons[i] ?? Zap;
          return (
            <li key={i} className="relative rounded-3xl border border-line bg-elev p-6">
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
    <div className={`rounded-3xl border border-line bg-elev p-6 ${className}`}>
      <span className="grid size-10 place-items-center rounded-xl bg-accent-soft text-accent">
        <Icon className="size-5" />
      </span>
      <h3 className="mt-4 text-lg font-semibold tracking-tight">{title}</h3>
      <div className="mt-1.5 text-pretty text-[15px] leading-relaxed text-muted">{children}</div>
    </div>
  );
}

/* ------------------------------------------------------------- comparison */

export function Comparison() {
  const rows: [string, boolean | string, boolean | string][] = [
    ["Pop-up & redirect ads", false, "Common"],
    ["Fake download buttons", false, "Common"],
    ["No watermark (TikTok)", true, "Sometimes"],
    ["Works with IDM & download managers", true, "Sometimes"],
    ["Carousel / multi-video posts", true, "Rare"],
    ["Reddit videos with sound", true, "Rare"],
    ["Share-to-app on mobile", true, false],
    ["Stores your files", false, "Often"],
  ];
  const cell = (v: boolean | string, good: boolean) =>
    typeof v === "string" ? (
      <span className={good ? "font-medium" : "text-muted"}>{v}</span>
    ) : v ? (
      <Check className="mx-auto size-5 text-ok" aria-label="Yes" />
    ) : (
      <XIcon className={`mx-auto size-5 ${good ? "text-ok" : "text-subtle"}`} aria-label="No" />
    );
  return (
    <section className="mx-auto max-w-4xl px-4 pt-24 sm:px-6">
      <SectionHeading eyebrow="Compared" title={`${SITE.name} vs. typical downloader sites`} />
      <div className="mt-10 overflow-hidden rounded-3xl border border-line bg-elev">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left">
              <th className="p-4 font-medium text-muted">Feature</th>
              <th className="w-28 p-4 text-center font-semibold sm:w-36">{SITE.name}</th>
              <th className="w-28 p-4 text-center font-medium text-muted sm:w-36">Others</th>
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

/* -------------------------------------------------------------- coming soon */

export function ComingSoon() {
  const tools = [
    { icon: Subtitles, name: `${SITE.name} Captions`, body: "Auto captions from an upload or a link, with Urdu, Hindi and Arabic support." },
    { icon: Crop, name: `${SITE.name} Reframe`, body: "Landscape to 9:16. AI keeps the speaker centred for Shorts, Reels and TikTok." },
    { icon: Wand2, name: `${SITE.name} Shorts`, body: "Long video to Shorts. AI finds the best moments and cuts them into captioned clips." },
    { icon: Scissors, name: `${SITE.name} Split`, body: "Cut at exact times or split every N seconds, without losing quality." },
    { icon: Combine, name: `${SITE.name} Merge`, body: "Join up to 4 clips into one, auto-matched in size and frame rate." },
  ];
  return (
    <section id="tools" className="mx-auto max-w-6xl scroll-mt-24 px-4 pt-24 sm:px-6">
      <SectionHeading eyebrow="Coming next" title="From link to ready-to-post Short, in one place." />
      <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
        {tools.map((t) => (
          <div key={t.name} className="relative rounded-3xl border border-dashed border-line-strong p-5">
            <span className="absolute right-4 top-4 rounded-full bg-line px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider text-muted">
              Soon
            </span>
            <t.icon className="size-6 text-accent" />
            <h3 className="mt-4 font-semibold tracking-tight">{t.name}</h3>
            <p className="mt-1 text-sm leading-relaxed text-muted">{t.body}</p>
          </div>
        ))}
      </div>
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

/* ------------------------------------------------------------------ shared */

export function SectionHeading({ eyebrow, title }: { eyebrow: string; title: string }) {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <p className="text-xs font-semibold uppercase tracking-[0.18em] text-accent">{eyebrow}</p>
      <h2 className="mt-3 text-balance text-3xl font-semibold tracking-[-0.03em] sm:text-4xl">{title}</h2>
    </div>
  );
}
