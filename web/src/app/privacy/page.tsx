import type { Metadata } from "next";
import { LegalPage } from "@/components/LegalPage";
import { SITE } from "@/lib/site";

export const metadata: Metadata = { title: "Privacy Policy", description: `How ${SITE.name} handles your data: downloads are never stored, uploads are deleted within 24 hours and never used to train AI.`, alternates: { canonical: "/privacy" } };

export default function Page() {
  return (
    <LegalPage title="Privacy Policy" updated="November 27, 2026">
      <p>This policy explains what {SITE.name} collects when you use the site and what we do with it. The short version: as little as possible.</p>
      <h2>Links and files</h2>
      <p>
        When you paste a link, our server fetches the public post to list download options. If you choose a download, the file is
        streamed straight to your device. <strong>We never save the file on our servers</strong>. We don&apos;t keep copies, build
        galleries or index what you download.
      </p>
      <h2>Videos you upload (Reframe)</h2>
      <p>
        The Reframe tool needs your video on our server to convert it. Uploads and finished videos are stored privately, are never
        shared, listed or used to train AI, and are <strong>deleted automatically within 24 hours</strong>. The AI that frames your video
        (face, object, text and speech detection) runs on our own servers. Your video is not sent to any AI company.
      </p>
      <h2>Videos you upload (Captions and AI Clips)</h2>
      <p>
        To write captions, the <strong>sound</strong> of your video is turned into text by speech recognition. Depending on our
        setup this runs on our own servers or at our speech-to-text providers (Groq, Cloudflare), which process the audio only to
        return the text. To make captions more accurate, the sound may be transcribed twice, by two different models.
      </p>
      <p>
        The <strong>caption text</strong> (never the video or audio) is sent to our AI text provider (Anthropic or Groq) to check
        and correct the captions, to pick the best moments for AI Clips and write their titles and hashtags, and when you use AI
        translation, Roman Urdu, highlights or hook ideas. Our providers process this data to deliver the service to us and
        don&apos;t use it to train their models. Your video, audio, captions, clips and finished videos are stored privately and
        are <strong> deleted automatically within 24 hours</strong>.
      </p>
      <p>
        Styles you save with &quot;Save as my style&quot; and your last-used style are kept only in your browser (local storage).
      </p>
      <h2>Your recent links</h2>
      <p>The &quot;Recent&quot; list is stored only in your browser (local storage). It is never sent to us, and you can clear it anytime.</p>
      <h2>Logs</h2>
      <p>
        Like most websites, our servers keep short-lived technical logs (IP address, time, request path, error messages) to prevent
        abuse and fix problems. These are kept for up to 14 days.
      </p>
      <h2>Cookies and advertising</h2>
      <p>
        We may show ads from Google AdSense or similar partners. These partners may use cookies to show relevant ads and measure
        them. Where required by law (for example in the EU/UK), we ask for your consent first. You can manage Google ad
        personalisation at <a href="https://adssettings.google.com" rel="noopener">adssettings.google.com</a>.
      </p>
      <h2>Children</h2>
      <p>{SITE.name} is not directed at children under 13, and we don&apos;t knowingly collect their data.</p>
      <h2>Contact</h2>
      <p>
        Questions about privacy? Email <a href={`mailto:${SITE.email}`}>{SITE.email}</a>.
      </p>
    </LegalPage>
  );
}
