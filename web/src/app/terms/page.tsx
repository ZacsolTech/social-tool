import type { Metadata } from "next";
import { LegalPage } from "@/components/LegalPage";
import { SITE } from "@/lib/site";

export const metadata: Metadata = { title: "Terms of Service", description: `The rules for using ${SITE.name}.`, alternates: { canonical: "/terms" } };

export default function Page() {
  return (
    <LegalPage title="Terms of Service" updated="November 5, 2026">
      <p>By using {SITE.name} you agree to these terms.</p>
      <h2>Use content you have the right to use</h2>
      <p>
        <strong>Only download or process content that you own or that you have permission to use.</strong> You are responsible for
        how you use any file you download, including following the terms of the platform it came from and the creator&apos;s
        rights.
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
