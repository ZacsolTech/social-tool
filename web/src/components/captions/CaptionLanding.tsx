import { Captions, Highlighter, Languages, Palette, Rocket, Scissors, ShieldCheck, Sparkles } from "lucide-react";
import { ClosingCta } from "@/components/marketing";
import { FaqSection, HowItWorks, PageLinks, SectionHeading, Tips, ToolHero, ToolJsonLd, ToolsShowcase } from "@/components/sections";
import type { CaptionPage } from "@/lib/captionTools";
import { CaptionTool } from "./CaptionTool";

export function CaptionLanding({ page }: { page: CaptionPage }) {
  return (
    <>
      <ToolJsonLd name="Captions" slug={page.slug} description={page.description} howTo={page.howTo} faqs={page.faqs} h1={page.h1} />
      <ToolHero tool="captions" slug={page.slug} label={page.nav} h1={page.h1} highlight={page.highlight} intro={page.intro}>
        <CaptionTool preset={page.preset} />
      </ToolHero>

      <HowItWorks steps={page.howTo} title="Captions in three steps" />
      <Tips tips={page.tips} />
      <Why />
      <FaqSection faqs={page.faqs} title="Captions FAQ" />
      <PageLinks tool="captions" current={page.slug} />
      <ToolsShowcase exclude="captions" eyebrow="More tools" title="More free tools for your video" />
      <ClosingCta href="#tool" label="Caption my video" title="Captions that match every word you say." body="Heard twice by AI, styled in one click, exported as MP4 or SRT. Urdu, Hindi, English and 40+ languages. Free." />
    </>
  );
}

function Why() {
  const items = [
    { icon: Captions, title: "Heard twice, AI-checked", body: "Two speech models listen, an AI judge fixes where they differ, unsure lines are marked for you. Every word is timed." },
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
