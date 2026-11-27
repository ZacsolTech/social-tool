import { Captions, Crop, FolderDown, Gauge, Languages, Scissors, ShieldCheck, Wand2 } from "lucide-react";
import { ClosingCta } from "@/components/marketing";
import { FaqSection, HowItWorks, PageLinks, SectionHeading, Tips, ToolHero, ToolJsonLd, ToolsShowcase } from "@/components/sections";
import type { ClipPage } from "@/lib/clipTools";
import { ClipTool } from "./ClipTool";

export function ClipLanding({ page }: { page: ClipPage }) {
  return (
    <>
      <ToolJsonLd name="AI Clips" slug={page.slug} description={page.description} howTo={page.howTo} faqs={page.faqs} h1={page.h1} />
      <ToolHero tool="clips" slug={page.slug} label={page.nav} h1={page.h1} highlight={page.highlight} intro={page.intro}>
        <ClipTool preset={page.preset} />
      </ToolHero>

      <HowItWorks steps={page.howTo} title="Long video to clips in three steps" />
      <Tips tips={page.tips} />
      <ClipWhy />
      <FaqSection faqs={page.faqs} title="AI Clips FAQ" />
      <PageLinks tool="clips" current={page.slug} />
      <ToolsShowcase exclude="clips" eyebrow="More tools" title="More free tools for your clips" />
      <ClosingCta href="#tool" label="Find my viral clips" title="Your next viral Short is already inside your video." body="Drop it in. In a few minutes you have scored, captioned, vertical clips ready to post. Free, no sign-up." />
    </>
  );
}

export function ClipWhy() {
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
