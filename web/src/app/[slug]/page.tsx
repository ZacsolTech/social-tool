import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Suspense } from "react";
import { CaptionLanding } from "@/components/captions/CaptionLanding";
import { ClipLanding } from "@/components/clips/ClipLanding";
import { JsonLd } from "@/components/JsonLd";
import { ClosingCta } from "@/components/marketing";
import { ToolLanding } from "@/components/reframe/ToolLanding";
import { FaqSection, Features, Hero, HowItWorks, PlatformStrip, Tips, ToolsShowcase, faqJsonLd } from "@/components/sections";
import { CAPTION_PAGES, captionPageBySlug } from "@/lib/captionTools";
import { CLIP_PAGES, clipPageBySlug } from "@/lib/clipTools";
import { CONTENT } from "@/lib/content";
import { PLATFORMS, bySlug } from "@/lib/platforms";
import { SITE } from "@/lib/site";
import { TOOL_PAGES, toolBySlug } from "@/lib/tools";

export function generateStaticParams() {
  return [...PLATFORMS.map((p) => ({ slug: p.slug })), ...TOOL_PAGES.map((t) => ({ slug: t.slug })), ...CAPTION_PAGES.map((t) => ({ slug: t.slug })), ...CLIP_PAGES.map((t) => ({ slug: t.slug }))];
}

export async function generateMetadata({ params }: PageProps<"/[slug]">): Promise<Metadata> {
  const { slug } = await params;
  const tool = toolBySlug(slug) ?? captionPageBySlug(slug) ?? clipPageBySlug(slug);
  if (tool) {
    return {
      title: { absolute: `${tool.title} | ${SITE.name}` },
      description: tool.description,
      alternates: { canonical: `/${tool.slug}` },
      openGraph: { title: tool.title, description: tool.description, url: `/${tool.slug}` },
    };
  }
  const p = bySlug(slug);
  if (!p) return {};
  const c = CONTENT[p.id];
  return {
    title: { absolute: `${c.title} | ${SITE.name}` },
    description: c.description,
    alternates: { canonical: `/${p.slug}` },
    openGraph: { title: c.title, description: c.description, url: `/${p.slug}` },
  };
}

/** Every slug is prerendered (generateStaticParams). Reading `params` inside a Suspense boundary keeps
 * client navigations between these pages instant: the shell shows at once, the page streams in. */
export default function SlugPage({ params }: PageProps<"/[slug]">) {
  return (
    <Suspense fallback={<div className="min-h-[80vh]" aria-busy="true" />}>
      <SlugContent params={params} />
    </Suspense>
  );
}

async function SlugContent({ params }: { params: PageProps<"/[slug]">["params"] }) {
  const { slug } = await params;
  const tool = toolBySlug(slug);
  if (tool) return <ToolLanding page={tool} />;
  const captions = captionPageBySlug(slug);
  if (captions) return <CaptionLanding page={captions} />;
  const clips = clipPageBySlug(slug);
  if (clips) return <ClipLanding page={clips} />;

  const p = bySlug(slug);
  if (!p) notFound();
  const c = CONTENT[p.id];

  return (
    <>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "WebApplication",
          name: `${SITE.name} ${p.name} Downloader`,
          url: `${SITE.url}/${p.slug}`,
          applicationCategory: "MultimediaApplication",
          operatingSystem: "Any",
          description: c.description,
          offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
        }}
      />
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "HowTo",
          name: `How to download ${p.noun}`,
          step: c.howTo.map((text, i) => ({ "@type": "HowToStep", position: i + 1, text })),
        }}
      />
      <JsonLd data={faqJsonLd(c.faqs)} />

      <Hero title={c.h1} highlight={c.highlight} subtitle={c.intro} platformHint={p.id} crumbs={[{ href: `/${p.slug}`, label: `${p.short} downloader` }]} />
      <PlatformStrip current={p.id} />
      <HowItWorks steps={c.howTo} platformName={p.short} />
      <Tips tips={c.tips} />
      <Features />
      <ToolsShowcase exclude="download" eyebrow="Do more with it" title={`Turn ${p.short} videos into ready-to-post Shorts`} />
      <FaqSection faqs={c.faqs} title={`${p.short} downloader FAQ`} />
      <ClosingCta
        href="/ai-clip-generator"
        label="Try AI Clips free"
        title="Got a long video? Turn it into Shorts."
        body="AI Clips finds the best moments, frames the speaker and captions every word. Paste the same link, no re-uploading."
      />
    </>
  );
}
