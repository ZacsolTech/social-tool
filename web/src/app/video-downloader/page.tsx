import type { Metadata } from "next";
import { JsonLd } from "@/components/JsonLd";
import { ClosingCta } from "@/components/marketing";
import { Comparison, FaqSection, Features, Hero, HowItWorks, PlatformStrip, ToolsShowcase, faqJsonLd } from "@/components/sections";
import { DOWNLOADER_FAQS } from "@/lib/content";
import { SITE } from "@/lib/site";

const TITLE = "Free Video Downloader: No Watermark, HD & MP3";
const DESCRIPTION =
  "Download YouTube, TikTok, Instagram, Facebook and X videos in HD without watermark, or as MP3. One paste, no sign-up, no pop-up ads. Free.";

export const metadata: Metadata = {
  title: { absolute: `${TITLE} | ${SITE.name}` },
  description: DESCRIPTION,
  alternates: { canonical: "/video-downloader" },
  openGraph: { title: TITLE, description: DESCRIPTION, url: "/video-downloader" },
};

export default function Page() {
  return (
    <>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "WebApplication",
          name: `${SITE.name} Video Downloader`,
          url: `${SITE.url}/video-downloader`,
          applicationCategory: "MultimediaApplication",
          operatingSystem: "Any",
          description: DESCRIPTION,
          offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
        }}
      />
      <JsonLd data={faqJsonLd(DOWNLOADER_FAQS)} />

      <Hero
        title="Download any social video, without the junk."
        highlight="without the junk."
        subtitle="Paste a YouTube, TikTok, Instagram, Facebook or X link. Get HD MP4 with no watermark, or MP3, in seconds."
        crumbs={[{ href: "/video-downloader", label: "Video Downloader" }]}
      />
      <PlatformStrip />
      <HowItWorks />
      <Features />
      <Comparison />
      <ToolsShowcase exclude="download" eyebrow="Do more with it" title="Turn the video into ready-to-post Shorts" />
      <FaqSection faqs={DOWNLOADER_FAQS} title="Video downloader FAQ" />
      <ClosingCta
        href="/ai-clip-generator"
        label="Try AI Clips free"
        title="Got a long video? Turn it into Shorts."
        body="AI Clips finds the best moments, frames the speaker and captions every word. Paste the same link, no re-uploading."
      />
    </>
  );
}
