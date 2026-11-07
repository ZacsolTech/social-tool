import type { Metadata } from "next";
import { LegalPage } from "@/components/LegalPage";
import { SITE } from "@/lib/site";

export const metadata: Metadata = { title: "Contact", description: `Contact the ${SITE.name} team.`, alternates: { canonical: "/contact" } };

export default function Page() {
  return (
    <LegalPage title="Contact">
      <p>
        Questions, feedback or a link that doesn&apos;t work? Email us at <a href={`mailto:${SITE.email}`}>{SITE.email}</a>. We
        usually reply within two working days.
      </p>
      <p>
        For copyright notices, please follow the steps on our <a href="/dmca">Copyright &amp; DMCA</a> page so we can act quickly.
      </p>
    </LegalPage>
  );
}
