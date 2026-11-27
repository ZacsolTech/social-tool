import { Captions, Crop, FolderDown, Gauge, Languages, Scissors, ShieldCheck, Wand2 } from "lucide-react";
import Link from "next/link";
import { JsonLd } from "@/components/JsonLd";
import { FaqSection, HowItWorks, SectionHeading, Tips, faqJsonLd } from "@/components/sections";
import { CLIP_PAGES, type ClipPage } from "@/lib/clipTools";
import { SITE } from "@/lib/site";
import { ClipTool } from "./ClipTool";

export function ClipLanding({ page }: { page: ClipPage }) {
  const [before, after] = page.h1.split(page.highlight);
  return (
    <>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "WebApplication",
          name: `${SITE.name} AI Clips`,
          url: `${SITE.url}/${page.slug}`,
          applicationCategory: "MultimediaApplication",
          operatingSystem: "Any",
          description: page.description,
          offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
        }}
      />
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "HowTo",
          name: page.h1,
          step: page.howTo.map((text, i) => ({ "@type": "HowToStep", position: i + 1, text })),
        }}
      />
      <JsonLd data={faqJsonLd(page.faqs)} />

      <section className="relative overflow-hidden">
        <div aria-hidden className="aurora pointer-events-none absolute inset-0" />
        <div aria-hidden className="grid-dots pointer-events-none absolute inset-0 opacity-60" />
        <div className="relative mx-auto max-w-6xl px-4 pb-8 pt-10 sm:px-6 sm:pt-16">
          <div className="mx-auto max-w-3xl text-center">
            <span className="inline-flex items-center gap-2 rounded-full border border-line bg-elev/80 px-3 py-1 text-xs font-medium text-muted backdrop-blur">
              <Wand2 className="size-3.5 text-accent" /> {SITE.name} AI Clips · Free · No watermark · No sign-up
            </span>
            <h1 className="mt-5 text-balance text-4xl font-semibold leading-[1.05] tracking-[-0.035em] sm:text-6xl">
              {before}
              {after !== undefined && <span className="font-display text-[1.08em] font-normal italic tracking-[-0.01em] text-accent">{page.highlight}</span>}
              {after}
            </h1>
            <p className="mx-auto mt-4 max-w-2xl text-pretty text-base text-muted sm:text-lg">{page.intro}</p>
          </div>
          <div className="mt-8">
            <ClipTool preset={page.preset} />
          </div>
        </div>
      </section>

      <HowItWorks steps={page.howTo} title="Long video to clips in three steps" />
      <Tips tips={page.tips} />
      <Why />
      <FaqSection faqs={page.faqs} title="AI Clips FAQ" />
      <ToolLinks current={page.slug} />
    </>
  );
}

function Why() {
  const items = [
    { icon: Gauge, title: "Virality score you can read", body: "Every clip is scored on hook, flow, value and shareability, with the reason in one line." },
    { icon: Scissors, title: "Cut on sentences", body: "Clips start and end on full sentences with a breath of room. Never mid-word." },
    { icon: Crop, title: "Speaker always in frame", body: "Smart Reframe follows whoever talks, splits two people, keeps slides whole." },
    { icon: Captions, title: "Captions + hook built in", body: "Animated word-by-word captions, keyword colours, emojis and a hook title on top." },
    { icon: Languages, title: "Urdu, Hindi & 40+ languages", body: "Roman Urdu, Nastaliq, Hindi, Arabic right-to-left. Titles in your own language." },
    { icon: Wand2, title: "Edit any clip", body: "Move the start or end by a sentence, rewrite the hook, change the style. Only that clip is re-made." },
    { icon: FolderDown, title: "Download all at once", body: "One ZIP with every clip, its SRT and the titles, post text and hashtags." },
    { icon: ShieldCheck, title: "Free & private", body: "No sign-up, no forced watermark. Files deleted within 24 hours." },
  ];
  return (
    <section className="mx-auto max-w-6xl px-4 pt-24 sm:px-6">
      <SectionHeading eyebrow="Why creators switch" title="What paid clipping apps do, free" />
      <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {items.map((it) => (
          <div key={it.title} className="rounded-3xl border border-line bg-elev p-5">
            <span className="grid size-10 place-items-center rounded-xl bg-accent-soft text-accent">
              <it.icon className="size-5" />
            </span>
            <h3 className="mt-4 font-semibold tracking-tight">{it.title}</h3>
            <p className="mt-1 text-sm leading-relaxed text-muted">{it.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}

function ToolLinks({ current }: { current: string }) {
  return (
    <section aria-label="More clip tools" className="mx-auto max-w-5xl px-4 pt-16 sm:px-6">
      <div className="flex flex-wrap justify-center gap-2">
        {CLIP_PAGES.filter((t) => t.slug !== current).map((t) => (
          <Link key={t.slug} href={`/${t.slug}`} className="rounded-full border border-line bg-elev px-3.5 py-1.5 text-sm transition hover:border-line-strong">
            {t.nav}
          </Link>
        ))}
      </div>
    </section>
  );
}
