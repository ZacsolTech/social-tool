import type { Metadata } from "next";
import Link from "next/link";
import { LegalPage } from "@/components/LegalPage";
import { TOOLS } from "@/lib/catalog";
import { SITE } from "@/lib/site";

export const metadata: Metadata = {
  title: "About",
  description: `${SITE.name} is a free AI studio for creators: AI Clips turns long videos into Shorts, plus AI Captions, Smart Reframe and a video downloader.`,
  alternates: { canonical: "/about" },
};

export default function Page() {
  return (
    <LegalPage title={`About ${SITE.name}`}>
      <p>
        {SITE.name} is a free studio of video tools for creators. Our slogan is the whole workflow: <strong>grab it, clip it, post
        it</strong>. Get a video from a link, find the moments worth posting, make them vertical, caption them, and post. All without
        a sign-up, a watermark or a pop-up.
      </p>
      <h2>The tools</h2>
      <ul>
        {TOOLS.map((t) => (
          <li key={t.id}>
            <Link href={t.href}>{t.name}</Link>: {t.body}
          </li>
        ))}
      </ul>
      <p>
        The tools hand off to each other. A downloaded video opens in AI Clips or Reframe with one click, and a clip opens in the
        caption editor with its words already there. Coming next: splitting and merging clips.
      </p>
      <h2>Built for every language</h2>
      <p>
        Most creator apps treat anything other than English as an afterthought. We don&apos;t. Urdu is written in proper Nastaliq,
        Roman Urdu the way people actually type it, and Hindi, Hinglish and Arabic (right-to-left) work just as well as English,
        along with 40+ other languages.
      </p>
      <h2>Our principles</h2>
      <ul>
        <li>One clear action per page. No dark patterns, no fake buttons.</li>
        <li>Free means free: no watermark on what you make, no &quot;upgrade to export&quot;.</li>
        <li>Accuracy you can check: the AI tells you when it isn&apos;t sure, instead of guessing silently.</li>
        <li>Private by design: downloads are never stored, uploads are deleted within 24 hours and never used to train AI.</li>
        <li>Respect creators: only download or edit content you own or have permission to use.</li>
      </ul>
    </LegalPage>
  );
}
