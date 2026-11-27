import { Suspense } from "react";
import { ClipWhy } from "@/components/clips/ClipLanding";
import { ClipTool } from "@/components/clips/ClipTool";
import { ShareRedirect } from "@/components/downloader/ShareRedirect";
import { JsonLd } from "@/components/JsonLd";
import { ClipsDemo, ClosingCta, TrustRow, UseCaseMarquee } from "@/components/marketing";
import {
  FaqSection,
  HowItWorks,
  StudioComparison,
  StudioFeatures,
  ToolChips,
  ToolsShowcase,
  Workflow,
  faqJsonLd,
} from "@/components/sections";
import { ToolTile } from "@/components/ToolIcon";
import { FEATURED, TOOLS } from "@/lib/catalog";
import { CLIP_PAGES } from "@/lib/clipTools";
import { HOME_FAQS } from "@/lib/content";
import { SITE } from "@/lib/site";

const clips = CLIP_PAGES[0];

export default function Home() {
  return (
    <>
      <Suspense>
        <ShareRedirect />
      </Suspense>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "WebSite",
          name: SITE.name,
          url: SITE.url,
          description: SITE.description,
        }}
      />
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "ItemList",
          name: `${SITE.name} video tools`,
          itemListElement: TOOLS.map((t, i) => ({
            "@type": "ListItem",
            position: i + 1,
            item: {
              "@type": "WebApplication",
              name: `${SITE.name} ${t.name}`,
              url: `${SITE.url}${t.href}`,
              description: t.body,
              applicationCategory: "MultimediaApplication",
              operatingSystem: "Any",
              offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
            },
          })),
        }}
      />
      <JsonLd data={faqJsonLd(HOME_FAQS)} />

      <section className="relative overflow-hidden">
        <div aria-hidden className="aurora pointer-events-none absolute inset-0" />
        <div aria-hidden className="grid-dots pointer-events-none absolute inset-0 opacity-60" />
        <div className="relative mx-auto max-w-6xl px-4 pb-8 pt-10 sm:px-6 sm:pt-16">
          <div className="mx-auto max-w-3xl text-center">
            <span className="inline-flex max-w-full items-center gap-2 rounded-full border border-line bg-elev/80 py-1 pl-1 pr-3 text-xs font-medium text-muted backdrop-blur">
              <ToolTile tool={FEATURED} size="sm" />
              <span className="truncate">
                <span className="font-semibold text-fg">
                  {SITE.name} {FEATURED.name}
                </span>{" "}
                · Free · No watermark · No sign-up
              </span>
            </span>
            <h1 className="mt-5 text-balance text-4xl font-semibold leading-[1.05] tracking-[-0.035em] sm:text-6xl">
              Long videos in.{" "}
              <span className="text-gradient font-display text-[1.08em] font-normal italic tracking-[-0.01em]">Viral Shorts out.</span>
            </h1>
            <p className="mx-auto mt-4 max-w-2xl text-pretty text-base text-muted sm:text-lg">
              Drop a podcast, interview or stream, or paste a YouTube link. AI finds the best moments, scores them, keeps the speaker in
              frame and adds accurate captions. Ready to post on TikTok, Reels and Shorts.
            </p>
          </div>
          <div id="tool" className="mt-8 scroll-mt-24">
            <ClipTool />
          </div>
          <TrustRow />
          <ToolChips />
        </div>
      </section>

      <UseCaseMarquee />
      <HowItWorks steps={clips.howTo} title="Long video to viral clips in three steps" />
      <ClipsDemo />
      <ClipWhy />
      <ToolsShowcase exclude="clips" eyebrow="More free tools" title="Everything else your Shorts need" />
      <Workflow />
      <StudioFeatures />
      <StudioComparison />
      <FaqSection faqs={HOME_FAQS} />
      <ClosingCta
        href="#tool"
        label="Find my viral clips"
        title="Your next viral Short is already inside your video."
        body="Drop it in. In a few minutes you have scored, captioned, vertical clips ready to post. Free, no sign-up."
      />
    </>
  );
}
