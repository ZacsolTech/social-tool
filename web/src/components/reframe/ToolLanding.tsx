import { Columns2, Crosshair, Gamepad2, ScanFace, ShieldCheck, Sparkles, Type, ZoomIn } from "lucide-react";
import Link from "next/link";
import { JsonLd } from "@/components/JsonLd";
import { FaqSection, HowItWorks, SectionHeading, Tips, faqJsonLd } from "@/components/sections";
import { SITE } from "@/lib/site";
import { TOOL_PAGES, type ToolPage } from "@/lib/tools";
import { ReframeTool } from "./ReframeTool";

export function ToolLanding({ page }: { page: ToolPage }) {
  const [before, after] = page.h1.split(page.highlight);
  return (
    <>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "WebApplication",
          name: `${SITE.name} Reframe`,
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
              <Sparkles className="size-3.5 text-accent" /> {SITE.name} Reframe · Free · No watermark · No sign-up
            </span>
            <h1 className="mt-5 text-balance text-4xl font-semibold leading-[1.05] tracking-[-0.035em] sm:text-6xl">
              {before}
              {after !== undefined && <span className="font-display text-[1.08em] font-normal italic tracking-[-0.01em] text-accent">{page.highlight}</span>}
              {after}
            </h1>
            <p className="mx-auto mt-4 max-w-2xl text-pretty text-base text-muted sm:text-lg">{page.intro}</p>
          </div>
          <div className="mt-8">
            <ReframeTool preset={page.preset} />
          </div>
        </div>
      </section>

      <HowItWorks steps={page.howTo} title="Vertical video in three steps" />
      <Tips tips={page.tips} />
      <Layouts />
      <FaqSection faqs={page.faqs} title="Reframe FAQ" />
      <ToolLinks current={page.slug} />
    </>
  );
}

function Layouts() {
  const items = [
    { icon: ScanFace, title: "Follow", body: "Full-screen crop on the active speaker, eyes on the upper third, smooth like a camera operator." },
    { icon: Columns2, title: "Split screen", body: "Two people talking back and forth, stacked top and bottom, each in their own crop." },
    { icon: Gamepad2, title: "Screen + Facecam", body: "Your webcam box is found automatically and stacked above the gameplay or screen." },
    { icon: Type, title: "Text-aware", body: "Slides, lower-thirds and big on-screen text are kept whole instead of cut in half." },
    { icon: Crosshair, title: "Follow anything", body: "Type “ball” or “dog”, or tap any object in the shot editor, and the crop follows it." },
    { icon: ZoomIn, title: "Dynamic zoom", body: "Optional subtle punch-ins on emphasised moments, found from the audio." },
    { icon: ShieldCheck, title: "Private", body: "Processed on our servers by open-source models, never sent to an AI company, deleted within 24 hours." },
    { icon: Sparkles, title: "One analysis, every size", body: "9:16, 4:5 and 1:1 rendered from a single analysis. Fix a shot and re-render in seconds." },
  ];
  return (
    <section className="mx-auto max-w-6xl px-4 pt-24 sm:px-6">
      <SectionHeading eyebrow="The AI director" title="Picks the right layout for every shot" />
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
    <section aria-label="More reframe tools" className="mx-auto max-w-5xl px-4 pt-16 sm:px-6">
      <div className="flex flex-wrap justify-center gap-2">
        {TOOL_PAGES.filter((t) => t.slug !== current).map((t) => (
          <Link key={t.slug} href={`/${t.slug}`} className="rounded-full border border-line bg-elev px-3.5 py-1.5 text-sm transition hover:border-line-strong">
            {t.nav}
          </Link>
        ))}
      </div>
    </section>
  );
}
