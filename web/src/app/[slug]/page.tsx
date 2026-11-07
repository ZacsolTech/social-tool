import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { JsonLd } from "@/components/JsonLd";
import { ComingSoon, FaqSection, Features, Hero, HowItWorks, PlatformStrip, Tips, faqJsonLd } from "@/components/sections";
import { CONTENT } from "@/lib/content";
import { PLATFORMS, bySlug } from "@/lib/platforms";
import { SITE } from "@/lib/site";

export function generateStaticParams() {
  return PLATFORMS.map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({ params }: PageProps<"/[slug]">): Promise<Metadata> {
  const { slug } = await params;
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

export default async function PlatformPage({ params }: PageProps<"/[slug]">) {
  const { slug } = await params;
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

      <Hero title={c.h1} highlight={c.highlight} subtitle={c.intro} platformHint={p.id} />
      <PlatformStrip current={p.id} />
      <HowItWorks steps={c.howTo} platformName={p.short} />
      <Tips tips={c.tips} />
      <Features />
      <ComingSoon />
      <FaqSection faqs={c.faqs} title={`${p.short} downloader FAQ`} />
    </>
  );
}
