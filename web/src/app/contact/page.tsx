import type { Metadata } from "next";
import { LegalPage } from "@/components/LegalPage";
import { SITE } from "@/lib/site";

export const metadata: Metadata = { title: "Contact", description: `Contact the ${SITE.name} team: questions, feedback or a problem with AI Clips, Captions, Reframe or the video downloader. We reply within two days.`, alternates: { canonical: "/contact" } };

export default function Page() {
  return (
    <LegalPage title="Contact">
      <p>
        Questions, feedback, a link that doesn&apos;t work, a clip the AI picked badly or a caption it got wrong? Email us at{" "}
        <a href={`mailto:${SITE.email}`}>{SITE.email}</a>. We usually reply within two working days. If it&apos;s about a
        video, tell us which tool you used and the link (if any): it helps us fix it faster.
      </p>
      <p>
        For copyright notices, please follow the steps on our <a href="/dmca">Copyright &amp; DMCA</a> page so we can act quickly.
      </p>
    </LegalPage>
  );
}
