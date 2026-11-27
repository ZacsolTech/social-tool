import type { Metadata } from "next";
import { LegalPage } from "@/components/LegalPage";
import { SITE } from "@/lib/site";

export const metadata: Metadata = { title: "Copyright & DMCA", description: `How to send a copyright or DMCA notice to ${SITE.name}, what to include, and how we act on valid notices quickly.`, alternates: { canonical: "/dmca" } };

export default function Page() {
  return (
    <LegalPage title="Copyright & DMCA" updated="November 27, 2026">
      <p>
        {SITE.name} does not host or publish videos. Downloads are streamed from public posts only when a user asks, and are
        never stored on our servers. Videos people upload to our AI tools (AI Clips, Captions, Reframe) are private to them,
        never listed or shared, and deleted automatically within 24 hours. We respect creators&apos; rights and respond quickly
        to valid notices.
      </p>
      <h2>Sending a notice</h2>
      <p>
        Email <a href={`mailto:${SITE.email}`}>{SITE.email}</a> with the subject &quot;Copyright notice&quot; and include:
      </p>
      <ul>
        <li>Your name, address and contact details.</li>
        <li>The work you own, and the URL(s) of the content on the original platform.</li>
        <li>A statement that you believe in good faith the use is not authorised.</li>
        <li>A statement, under penalty of perjury, that the notice is accurate and you are the owner or authorised to act for them.</li>
        <li>Your physical or electronic signature.</li>
      </ul>
      <h2>What we do</h2>
      <p>
        On a valid notice we block the listed URLs from being processed by {SITE.name}. Repeat abuse of the service leads to
        blocking.
      </p>
    </LegalPage>
  );
}
