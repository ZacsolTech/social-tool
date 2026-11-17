"use client";

import clsx from "clsx";
import { Heart, MessageCircle, Music2, Send, Sparkles } from "lucide-react";
import type { CSSProperties } from "react";
import type { Aspect, Look, Mode, SmartOptions } from "@/lib/reframe";
import { ASPECTS } from "@/lib/reframe";

export type PreviewSource = { kind: "video"; url: string } | { kind: "image"; url: string } | null;

/**
 * Live preview, drawn by the browser (no server work): the same layout maths as the backend's
 * Blur Fill / Crop / Fit modes. Smart Reframe shows a centre crop until the AI result is ready.
 */
export function PhonePreview({
  source,
  aspect,
  mode,
  look,
  position,
  framing,
  safeZone,
  showSafe,
  result,
}: {
  source: PreviewSource;
  aspect: Aspect;
  mode: Mode;
  look: Look;
  position: number;
  framing: number;
  safeZone: SmartOptions["safe_zone"];
  showSafe: boolean;
  result?: string | null;
}) {
  const ratio = ASPECTS.find((a) => a.id === aspect)?.ratio ?? 9 / 16;
  const blurPx = { 1: 10, 2: 18, 3: 30 }[look.blur];

  const media = (style: CSSProperties, className: string, muted = true) =>
    source?.kind === "video" ? (
      <video src={source.url} muted={muted} autoPlay loop playsInline className={className} style={style} aria-hidden />
    ) : source?.kind === "image" ? (
      // eslint-disable-next-line @next/next/no-img-element
      <img src={source.url} alt="" className={className} style={style} aria-hidden />
    ) : null;

  let body: React.ReactNode;
  if (result) {
    body = <video key={result} src={result} controls autoPlay muted loop playsInline className="absolute inset-0 size-full object-cover" />;
  } else if (!source) {
    body = (
      <div className="absolute inset-0 grid place-items-center p-6 text-center text-xs text-white/60">
        Your vertical preview appears here
      </div>
    );
  } else if (mode === "crop" || mode === "smart") {
    body = (
      <>
        {media(
          { objectPosition: `${position * 100}% 50%`, transform: `scale(${framing})`, transformOrigin: `${position * 100}% 50%` },
          "absolute inset-0 size-full object-cover",
        )}
        {mode === "smart" && (
          <span className="absolute left-1/2 top-10 inline-flex -translate-x-1/2 items-center gap-1 whitespace-nowrap rounded-full bg-black/60 px-2.5 py-1 text-[10px] font-medium text-white backdrop-blur">
            <Sparkles className="size-3" /> AI picks the framing per shot
          </span>
        )}
      </>
    );
  } else {
    body = (
      <>
        {mode === "blur" ? (
          media(
            { filter: `blur(${blurPx}px) brightness(${1 - look.dim})`, transform: "scale(1.15)" },
            "absolute inset-0 size-full object-cover",
          )
        ) : (
          <div className="absolute inset-0" style={{ background: look.color }} />
        )}
        <div className="absolute inset-0 flex items-center justify-center overflow-hidden">
          {media({ width: `${look.fg_zoom * 100}%`, maxWidth: "none" }, "relative h-auto shrink-0")}
        </div>
      </>
    );
  }

  return (
    <div className="mx-auto w-full max-w-[300px]">
      <div
        className="relative w-full overflow-hidden rounded-[28px] border-[6px] border-neutral-900 bg-neutral-950 shadow-card dark:border-neutral-700"
        style={{ aspectRatio: String(ratio) }}
      >
        {body}
        {showSafe && !result && source && <SafeZone app={safeZone} aspect={aspect} />}
      </div>
      <p className="mt-2 text-center text-xs text-subtle">
        {aspect} · {aspect === "9:16" ? "1080×1920" : aspect === "4:5" ? "1080×1350" : "1080×1080"}
      </p>
    </div>
  );
}

function SafeZone({ app, aspect }: { app: SmartOptions["safe_zone"]; aspect: Aspect }) {
  if (app === "none" || aspect !== "9:16") return null;
  const icons = [Heart, MessageCircle, Send, Music2];
  return (
    <div aria-hidden className="pointer-events-none absolute inset-0 text-white">
      <div className="absolute inset-x-0 top-0 h-[8%] bg-gradient-to-b from-black/40 to-transparent" />
      <div className={clsx("absolute right-[3%] flex flex-col items-center gap-3", app === "shorts" ? "bottom-[16%]" : "bottom-[22%]")}>
        {icons.map((I, i) => (
          <span key={i} className="grid size-7 place-items-center rounded-full bg-black/35">
            <I className="size-3.5" />
          </span>
        ))}
      </div>
      <div className="absolute inset-x-0 bottom-0 h-[20%] bg-gradient-to-t from-black/60 to-transparent" />
      <div className="absolute bottom-[5%] left-[4%] right-[22%] space-y-1">
        <div className="h-2 w-1/2 rounded bg-white/70" />
        <div className="h-1.5 w-4/5 rounded bg-white/45" />
      </div>
      <span className="absolute left-2 top-2 rounded bg-black/50 px-1.5 py-0.5 text-[9px] font-medium uppercase tracking-wider">
        {app} safe zone
      </span>
    </div>
  );
}
