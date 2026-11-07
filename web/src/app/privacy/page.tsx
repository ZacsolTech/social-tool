import type { Metadata } from "next";
import { LegalPage } from "@/components/LegalPage";
import { SITE } from "@/lib/site";

export const metadata: Metadata = { title: "Privacy Policy", description: `How ${SITE.name} handles your data.`, alternates: { canonical: "/privacy" } };

export default function Page() {
  return (
    <LegalPage title="Privacy Policy" updated="November 5, 2026">
      <p>This policy explains what {SITE.name} collects when you use the site and what we do with it. The short version: as little as possible.</p>
      <h2>Links and files</h2>
      <p>
        When you paste a link, our server fetches the public post to list download options. If you choose a download, the file is
        streamed straight to your device. <strong>We never save the file on our servers</strong>. We don&apos;t keep copies, build
        galleries or index what you download.
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
