import { Captions, Highlighter, Languages, Palette, Rocket, Scissors, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";
import { JsonLd } from "@/components/JsonLd";
import { FaqSection, HowItWorks, SectionHeading, Tips, faqJsonLd } from "@/components/sections";
import { CAPTION_PAGES, type CaptionPage } from "@/lib/captionTools";
import { SITE } from "@/lib/site";
import { CaptionTool } from "./CaptionTool";

export function CaptionLanding({ page }: { page: CaptionPage }) {
  const [before, after] = page.h1.split(page.highlight);
  return (
    <>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "WebApplication",
          name: `${SITE.name} Captions`,
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
              <Sparkles className="size-3.5 text-accent" /> {SITE.name} Captions · Free · No sign-up · Urdu, Hindi & 40+ languages
            </span>
            <h1 className="mt-5 text-balance text-4xl font-semibold leading-[1.05] tracking-[-0.035em] sm:text-6xl">
              {before}
              {after !== undefined && <span className="font-display text-[1.08em] font-normal italic tracking-[-0.01em] text-accent">{page.highlight}</span>}
              {after}
            </h1>
            <p className="mx-auto mt-4 max-w-2xl text-pretty text-base text-muted sm:text-lg">{page.intro}</p>
          </div>
          <div className="mt-8">
            <CaptionTool preset={page.preset} />
          </div>
        </div>
      </section>

      <HowItWorks steps={page.howTo} title="Captions in three steps" />
      <Tips tips={page.tips} />
      <Why />
      <FaqSection faqs={page.faqs} title="Captions FAQ" />
      <ToolLinks current={page.slug} />
    </>
  );
}

function Why() {
  const items = [
    { icon: Captions, title: "Word-perfect timing", body: "Every word is timed, so highlights land exactly when it's said." },
    { icon: Languages, title: "Urdu, Roman Urdu, Hindi", body: "Nastaliq, Roman Urdu, Hinglish, Arabic right-to-left and 40+ languages, done properly." },
    { icon: Highlighter, title: "Viral styles", body: "14 presets: Bold Pop, Karaoke, One Word, Highlight Box, Story and more. Save your own." },
    { icon: Sparkles, title: "AI highlights & emojis", body: "Key words light up, emojis appear on the right moments, hook titles suggested for you." },
    { icon: Rocket, title: "Hook + progress bar", body: "The two tricks that keep viewers watching, built in." },
    { icon: Scissors, title: "Cut ums & pauses", body: "Filler words and long silences removed when you export. Captions follow." },
    { icon: Palette, title: "Your brand", body: "Add your logo, pick your colours and fonts, save them as your style." },
    { icon: ShieldCheck, title: "Private & free", body: "No sign-up, no forced watermark. Files deleted within 24 hours." },
  ];
  return (
    <section className="mx-auto max-w-6xl px-4 pt-24 sm:px-6">
      <SectionHeading eyebrow="Why creators switch" title="Everything paid caption apps do, free" />
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
    <section aria-label="More caption tools" className="mx-auto max-w-5xl px-4 pt-16 sm:px-6">
      <div className="flex flex-wrap justify-center gap-2">
        {CAPTION_PAGES.filter((t) => t.slug !== current).map((t) => (
          <Link key={t.slug} href={`/${t.slug}`} className="rounded-full border border-line bg-elev px-3.5 py-1.5 text-sm transition hover:border-line-strong">
            {t.nav}
          </Link>
        ))}
      </div>
    </section>
  );
}
