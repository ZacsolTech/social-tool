import { Columns2, Crosshair, Gamepad2, ScanFace, ShieldCheck, Sparkles, Type, ZoomIn } from "lucide-react";
import { ClosingCta } from "@/components/marketing";
import { FaqSection, HowItWorks, PageLinks, SectionHeading, Tips, ToolHero, ToolJsonLd, ToolsShowcase } from "@/components/sections";
import type { ToolPage } from "@/lib/tools";
import { ReframeTool } from "./ReframeTool";

export function ToolLanding({ page }: { page: ToolPage }) {
  return (
    <>
      <ToolJsonLd name="Reframe" slug={page.slug} description={page.description} howTo={page.howTo} faqs={page.faqs} h1={page.h1} />
      <ToolHero tool="reframe" slug={page.slug} label={page.nav} h1={page.h1} highlight={page.highlight} intro={page.intro}>
        <ReframeTool preset={page.preset} />
      </ToolHero>

      <HowItWorks steps={page.howTo} title="Vertical video in three steps" />
      <Tips tips={page.tips} />
      <Layouts />
      <FaqSection faqs={page.faqs} title="Reframe FAQ" />
      <PageLinks tool="reframe" current={page.slug} />
      <ToolsShowcase exclude="reframe" eyebrow="More tools" title="Make the vertical video even better" />
      <ClosingCta href="#tool" label="Make it vertical" title="One upload. Every vertical size, speaker in frame." body="9:16, 4:5 and 1:1 from a single analysis, with smart layouts for every shot. Free, no watermark, no sign-up." />
    </>
  );
}

function Layouts() {
  const items = [
    { icon: ScanFace, title: "Follow", body: "Full-screen crop on the active speaker, eyes on the upper third, smooth like a camera operator." },
    { icon: Columns2, title: "Split screen", body: "Two people talking back and forth, stacked top and bottom, each in their own crop." },
    { icon: Gamepad2, title: "Screen + Facecam", body: "Your webcam box is found automatically and stacked above the gameplay or screen." },
    { icon: Type, title: "Text-aware", body: "Slides, lower-thirds and big on-screen text are kept whole instead of cut in half." },
    { icon: Crosshair, title: "Follow anything", body: "Type “ball” or “dog”, or tap any object in the shot editor, and the crop follows it." },
    { icon: ZoomIn, title: "Dynamic zoom", body: "Optional subtle punch-ins on emphasised moments, found from the audio." },
    { icon: ShieldCheck, title: "Private", body: "Processed on our servers by open-source models, never sent to an AI company, deleted within 24 hours." },
    { icon: Sparkles, title: "One analysis, every size", body: "9:16, 4:5 and 1:1 rendered from a single analysis. Fix a shot and re-render in seconds." },
  ];
  return (
    <section className="mx-auto max-w-6xl px-4 pt-24 sm:px-6">
      <SectionHeading eyebrow="The AI director" title="Picks the right layout for every shot" />
      <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {items.map((it) => (
          <div key={it.title} className="rounded-3xl border border-line bg-elev p-5">
            <span className="grid size-10 place-items-center rounded-xl bg-accent-soft text-accent">
              <it.icon className="size-5" />
            </span>
            <h3 className="mt-4 font-semibold tracking-tight">{it.title}</h3>
            <p className="mt-1 text-sm leading-relaxed text-muted">{it.body}</p>
          </div>
        ))}
      </div>
    </section>
  );
}
