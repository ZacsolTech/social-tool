import { BadgeCheck, Clock3, Languages, ShieldCheck, Sparkles, Timer, UserX } from "lucide-react";
import { SITE } from "@/lib/site";
import { SectionHeading } from "./sections";

/* ------------------------------------------------------------- trust row */

/** Plain facts under the main tool. Every item is true of the service (no invented numbers). */
export function TrustRow() {
  const items = [
    { icon: BadgeCheck, text: "No watermark" },
    { icon: UserX, text: "No sign-up" },
    { icon: Languages, text: "40+ languages" },
    { icon: Timer, text: "Videos up to 90 min" },
    { icon: ShieldCheck, text: "Deleted within 24 h" },
  ];
  return (
    <ul className="mx-auto mt-6 flex max-w-4xl flex-wrap items-center justify-center gap-x-5 gap-y-2 text-sm text-muted">
      {items.map((it) => (
        <li key={it.text} className="inline-flex items-center gap-1.5">
          <it.icon className="size-4 text-ok" /> {it.text}
        </li>
      ))}
    </ul>
  );
}

/* ------------------------------------------------------------- use cases */

const USE_CASES = [
  "Podcasts",
  "Interviews",
  "Livestreams",
  "Lectures",
  "Webinars",
  "Islamic talks",
  "Vlogs",
  "Gaming",
  "Sports talk",
  "Online courses",
  "News shows",
  "Motivational talks",
  "Product demos",
  "Urdu & Hindi shows",
];

/** An endless strip of what people clip. */
export function UseCaseMarquee() {
  const row = [...USE_CASES, ...USE_CASES];
  return (
    <section aria-label="What creators clip" className="mx-auto max-w-6xl px-4 pt-16 sm:px-6">
      <p className="text-center text-xs font-semibold uppercase tracking-[0.16em] text-subtle">Made for every kind of long video</p>
      <div className="marquee-mask mt-4 overflow-hidden">
        <ul className="marquee flex w-max gap-2">
          {row.map((u, i) => (
            <li
              key={`${u}-${i}`}
              aria-hidden={i >= USE_CASES.length || undefined}
              className="whitespace-nowrap rounded-full border border-line bg-elev px-4 py-1.5 text-sm text-muted"
            >
              {u}
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

/* ------------------------------------------------------------- the demo */

const DEMO_LINES = [
  { t: "12:04", text: "So the question everyone asks me is how to start saving.", pick: false },
  { t: "12:09", text: "Nobody tells you this, but saving isn't about what's left.", pick: true },
  { t: "12:14", text: "You save twenty percent the day you get paid. First.", pick: true },
  { t: "12:19", text: "That one change made me debt free in three years.", pick: true },
  { t: "12:25", text: "Anyway, let's take a quick break and come back.", pick: false },
];

const DEMO_CLIPS = [
  { score: 94, title: "Nobody tells you this about saving", tone: "from-violet-500 to-fuchsia-500", scores: [96, 91, 92, 90] },
  { score: 88, title: "Debt free in 3 years", tone: "from-amber-400 to-orange-500", scores: [90, 87, 88, 84] },
  { score: 81, title: "Save first, spend later", tone: "from-sky-500 to-indigo-500", scores: [82, 84, 80, 76] },
];

/** A looping picture of how AI Clips works: it reads the transcript, picks the strong moments, scores them. */
export function ClipsDemo() {
  return (
    <section className="mx-auto max-w-6xl px-4 pt-24 sm:px-6">
      <SectionHeading eyebrow="See it work" title="It reads your video like an editor, then cuts the moments that travel." />
      <div className="reveal mt-10 grid gap-4 rounded-[2rem] border border-line bg-elev p-4 shadow-card sm:p-6 lg:grid-cols-[1.05fr_1fr]">
        <div className="rounded-3xl border border-line bg-bg p-4 sm:p-5">
          <div className="flex items-center justify-between">
            <p className="inline-flex items-center gap-2 text-sm font-semibold">
              <Clock3 className="size-4 text-subtle" /> Transcript, every word timed
            </p>
            <span className="inline-flex items-center gap-1 rounded-full bg-accent-soft px-2 py-0.5 text-[11px] font-semibold text-accent">
              <Sparkles className="size-3" /> AI reading
            </span>
          </div>
          <ol className="mt-4 space-y-1.5">
            {DEMO_LINES.map((l, i) => (
              <li
                key={l.t}
                className={`flex gap-3 rounded-xl px-2.5 py-2 text-[15px] leading-snug ${l.pick ? "demo-line" : "text-muted"}`}
                style={l.pick ? { animationDelay: `${(i - 1) * 0.45}s` } : undefined}
              >
                <span className="mt-0.5 shrink-0 font-mono text-xs text-subtle">{l.t}</span>
                <span>{l.text}</span>
              </li>
            ))}
          </ol>
          <p className="mt-4 text-xs leading-relaxed text-subtle">
            Each candidate is scored on hook, flow, value and shareability, then cut on full sentences, never mid-word.
          </p>
        </div>
        <div className="grid grid-cols-3 items-end gap-3">
          {DEMO_CLIPS.map((c, i) => (
            <div key={c.score} className="demo-clip" style={{ animationDelay: `${i * 0.35}s` }}>
              <div className={`relative aspect-[9/16] overflow-hidden rounded-2xl bg-gradient-to-br ${c.tone} shadow-card`}>
                <span className="absolute left-2 top-2 grid size-9 place-items-center rounded-full bg-black/55 text-xs font-bold text-white ring-2 ring-white/70">
                  {c.score}
                </span>
                <span className="absolute inset-x-2 top-14 text-center text-[11px] font-extrabold uppercase leading-tight text-white drop-shadow sm:text-xs">
                  {c.title}
                </span>
                <span className="absolute inset-x-3 bottom-8 rounded bg-black/55 py-1 text-center text-[10px] font-bold text-amber-300">
                  word by word
                </span>
              </div>
              <dl className="mt-2 grid grid-cols-4 gap-1 text-center text-[10px] text-subtle">
                {["Hook", "Flow", "Value", "Share"].map((k, j) => (
                  <div key={k}>
                    <dt>{k}</dt>
                    <dd className="font-semibold text-fg">{c.scores[j]}</dd>
                  </div>
                ))}
              </dl>
            </div>
          ))}
        </div>
      </div>
      <p className="mt-4 text-center text-xs text-subtle">Example of the result. Your clips, titles and scores come from your own video.</p>
    </section>
  );
}

/* ------------------------------------------------------------- closing call to action */

export function ClosingCta({ href, label, title, body }: { href: string; label: string; title: string; body: string }) {
  return (
    <section className="mx-auto max-w-6xl px-4 pt-24 sm:px-6">
      <div className="glow-card reveal relative overflow-hidden rounded-[2rem] px-6 py-12 text-center shadow-card sm:px-12 sm:py-16">
        <div aria-hidden className="aurora pointer-events-none absolute inset-0 opacity-80" />
        <div className="relative">
          <h2 className="mx-auto max-w-3xl text-balance text-3xl font-semibold tracking-[-0.03em] sm:text-5xl">{title}</h2>
          <p className="mx-auto mt-4 max-w-xl text-pretty text-muted sm:text-lg">{body}</p>
          <a
            href={href}
            className="mt-8 inline-flex items-center gap-2 rounded-full bg-accent px-7 py-3.5 text-base font-semibold text-accent-fg shadow-[0_14px_40px_-12px_var(--accent)] transition hover:-translate-y-px hover:brightness-105"
          >
            <Sparkles className="size-4" /> {label}
          </a>
          <p className="mt-4 text-xs text-subtle">Free · No watermark · No sign-up · {SITE.name}</p>
        </div>
      </div>
    </section>
  );
}
