import type { Metadata } from "next";
import { LegalPage } from "@/components/LegalPage";
import { SITE } from "@/lib/site";

export const metadata: Metadata = { title: "About", description: `What ${SITE.name} is and why we built it.`, alternates: { canonical: "/about" } };

export default function Page() {
  return (
    <LegalPage title={`About ${SITE.name}`}>
      <p>
        {SITE.name} is a set of fast, simple video tools for creators. We started with the thing everyone needs first: getting a
        video from a link onto your device. We do it <strong>without pop-ups, fake buttons or sign-ups</strong>.
      </p>
      <p>
        Next we&apos;re adding the tools that turn a video into a ready-to-post Short: auto-captions (including Urdu, Hindi and
        Arabic), 9:16 resizing that keeps the speaker in frame, splitting, combining, and AI that finds the best moments in long
        videos.
      </p>
      <h2>Our principles</h2>
      <ul>
        <li>One clear action per page. No dark patterns.</li>
        <li>Downloads stream straight to you. We never store your files.</li>
        <li>Respect creators: only download content you own or have permission to use.</li>
      </ul>
    </LegalPage>
  );
}
