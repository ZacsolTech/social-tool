import { JsonLd } from "@/components/JsonLd";
import { ComingSoon, Comparison, FaqSection, Features, Hero, HowItWorks, PlatformStrip, faqJsonLd } from "@/components/sections";
import { HOME_FAQS } from "@/lib/content";
import { SITE } from "@/lib/site";

export default function Home() {
  return (
    <>
      <JsonLd
        data={{
          "@context": "https://schema.org",
          "@type": "WebApplication",
          name: SITE.name,
          url: SITE.url,
          applicationCategory: "MultimediaApplication",
          operatingSystem: "Any",
          description: SITE.description,
          offers: { "@type": "Offer", price: "0", priceCurrency: "USD" },
        }}
      />
      <JsonLd data={faqJsonLd(HOME_FAQS)} />

      <Hero
        title="Download any social video, without the junk."
        highlight="without the junk."
        subtitle="Paste a YouTube, TikTok, Instagram, Facebook or X link. Get HD MP4 with no watermark, or MP3, in seconds."
      />
      <PlatformStrip />
      <HowItWorks />
      <Features />
      <Comparison />
      <ComingSoon />
      <FaqSection faqs={HOME_FAQS} />
    </>
  );
}
