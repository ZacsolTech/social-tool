import type { Metadata } from "next";
import { LegalPage } from "@/components/LegalPage";
import { SITE } from "@/lib/site";

export const metadata: Metadata = { title: "Terms of Service", description: `The terms for using ${SITE.name} AI Clips, Captions, Reframe and the video downloader: fair use, your content and AI results.`, alternates: { canonical: "/terms" } };

export default function Page() {
  return (
    <LegalPage title="Terms of Service" updated="November 27, 2026">
      <p>By using {SITE.name} you agree to these terms.</p>
      <h2>Use content you have the right to use</h2>
      <p>
        <strong>Only download or process content that you own or that you have permission to use.</strong> You are responsible for
        how you use any file you download, including following the terms of the platform it came from and the creator&apos;s
        rights.
      </p>
      <h2>Uploads and the AI tools</h2>
      <p>
        When you upload a video, or send a link to AI Clips, Captions or Reframe, you confirm you have the right to edit and repost
        it. We process it only to create what you asked for (clips, captions, vertical videos), keep the files only so you can
        download them, and delete them automatically within 24 hours. Fair-use limits (file size, video length and uses per day)
        keep the service fast and free for everyone.
      </p>
      <h2>AI results</h2>
      <p>
        Clip choices, scores, titles, captions and translations are made by AI and can contain mistakes. The caption editor marks
        lines the AI wasn&apos;t sure about, but please check what you post. You are responsible for the content you publish.
      </p>
      <h2>Acceptable use</h2>
      <ul>
        <li>No automated or bulk scraping of the service.</li>
        <li>No attempts to bypass rate limits, access private content or disrupt the service.</li>
        <li>No use of the service to infringe copyright or other rights.</li>
      </ul>
      <h2>No affiliation</h2>
      <p>
        {SITE.name} is an independent tool and is not affiliated with, endorsed by or sponsored by YouTube, Google, TikTok, Instagram, Meta, X,
        Reddit, Pinterest, Dailymotion, Twitch or any other platform. All trademarks belong to their owners.
      </p>
      <h2>No warranty</h2>
      <p>
        The service is provided &quot;as is&quot;. Platforms change often, so some links may stop working at times. We may
        change, limit or stop features at any time.
      </p>
      <h2>Contact</h2>
      <p>
        <a href={`mailto:${SITE.email}`}>{SITE.email}</a>
      </p>
    </LegalPage>
  );
}
