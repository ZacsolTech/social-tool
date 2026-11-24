"use client";

import clsx from "clsx";
import { type CSSProperties, type RefObject, useEffect, useMemo, useRef, useState } from "react";
import { type CConfig, type Extras, fontStack, cssFamily } from "@/lib/captions";
import {
  type CStyle,
  type CTranscript,
  type CWord,
  activeWord,
  buildPages,
  displayTranscript,
  hexToRgba,
  joiner,
  pageAt,
} from "@/lib/captionsCore";

export type PreviewHandle = { seek: (t: number) => void; play: () => void };

/**
 * The video with captions drawn on top by the browser, using the same fonts, paging and timing as the
 * export (backend/app/captions/ass.py), so what you see here is what you download.
 */
export function CaptionPreview({
  src,
  width,
  height,
  duration,
  transcript,
  style,
  extras,
  config,
  rtl,
  logoUrl,
  handle,
  onTime,
  result,
}: {
  src: string | null;
  width: number;
  height: number;
  duration: number | null;
  transcript: CTranscript | null;
  style: CStyle;
  extras: Extras;
  config: CConfig | null;
  rtl: boolean;
  logoUrl: string | null;
  handle?: RefObject<PreviewHandle | null>;
  onTime?: (t: number) => void;
  result?: string | null;
}) {
  const video = useRef<HTMLVideoElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const [t, setT] = useState(0);
  const [boxSize, setBoxSize] = useState({ w: 320, h: 568 });
  const ratio = width && height ? width / height : 9 / 16;
  const portrait = ratio < 1;

  useEffect(() => {
    if (!handle) return;
    handle.current = {
      seek: (time) => {
        const v = video.current;
        if (v) {
          v.currentTime = Math.max(0, time);
          setT(v.currentTime);
        }
      },
      play: () => void video.current?.play().catch(() => undefined),
    };
  }, [handle]);

  // Follow the playhead smoothly while playing (timeupdate alone is only ~4 times a second).
  useEffect(() => {
    const v = video.current;
    if (!v) return;
    let raf = 0;
    const tick = () => {
      setT(v.currentTime);
      onTime?.(v.currentTime);
      if (!v.paused && !v.ended) raf = requestAnimationFrame(tick);
    };
    const start = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(tick);
    };
    const once = () => {
      setT(v.currentTime);
      onTime?.(v.currentTime);
    };
    v.addEventListener("play", start);
    v.addEventListener("seeked", once);
    v.addEventListener("timeupdate", once);
    return () => {
      cancelAnimationFrame(raf);
      v.removeEventListener("play", start);
      v.removeEventListener("seeked", once);
      v.removeEventListener("timeupdate", once);
    };
  }, [onTime, src, result]);

  useEffect(() => {
    const el = box.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setBoxSize({ w: e.contentRect.width, h: e.contentRect.height }));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const shown = useMemo(() => (transcript ? displayTranscript(transcript, extras.mode) : null), [transcript, extras.mode]);
  const pagesList = useMemo(() => (shown ? buildPages(shown, style, duration) : []), [shown, style, duration]);
  const page = result ? null : pageAt(pagesList, t);
  const scale = Math.min(boxSize.w, boxSize.h) / 1080;
  const lang = shown?.language ?? "en";

  return (
    <div className={clsx("mx-auto w-full", portrait ? "max-w-[340px]" : "max-w-full")}>
      <div
        ref={box}
        className="relative w-full overflow-hidden rounded-2xl bg-neutral-950 shadow-card"
        style={{ aspectRatio: String(ratio), maxHeight: "72vh" }}
      >
        {result ? (
          <video key={result} ref={video} src={result} controls playsInline className="absolute inset-0 size-full object-contain" />
        ) : src ? (
          <video ref={video} src={src} controls playsInline preload="metadata" className="absolute inset-0 size-full object-contain" />
        ) : (
          <div className="absolute inset-0 grid place-items-center p-6 text-center text-xs text-white/60">Your video appears here</div>
        )}
        {!result && src && (
          <div aria-hidden className="pointer-events-none absolute inset-0 select-none">
            {page && shown && (
              <Caption
                key={`${page.start}-${style.animation}`}
                words={page.words}
                active={activeWord(page, t)}
                t={t}
                translation={extras.mode === "dual" ? (page.line.translation ?? null) : null}
                style={style}
                scale={scale}
                font={fontStack(config, style.font, lang)}
                translationFont={fontStack(config, style.font, shown.translation_lang ?? "en")}
                lang={lang}
                rtl={rtl && extras.mode !== "translation"}
              />
            )}
            {extras.hook.trim() && (extras.hook_seconds <= 0 || t < extras.hook_seconds) && (
              <div className="absolute inset-x-0 flex justify-center px-[6%]" style={{ top: `${extras.hook_y * 100}%` }}>
                <span
                  className="kly-pop rounded-md text-center font-bold leading-tight"
                  style={{
                    fontFamily: fontStack(config, style.font, lang),
                    fontSize: style.size * 0.95 * scale,
                    color: extras.hook_color,
                    background: extras.hook_bg,
                    padding: `${8 * scale}px ${16 * scale}px`,
                    textTransform: style.uppercase ? "uppercase" : undefined,
                    boxDecorationBreak: "clone",
                    WebkitBoxDecorationBreak: "clone",
                  }}
                >
                  {extras.hook}
                </span>
              </div>
            )}
            {extras.progress_bar !== "none" && duration ? (
              <div
                className={clsx("absolute left-0", extras.progress_bar === "top" ? "top-0" : "bottom-0")}
                style={{ height: Math.max(3, boxSize.h * 0.006), width: `${Math.min(100, (t / duration) * 100)}%`, background: extras.progress_color }}
              />
            ) : null}
            {extras.watermark && config?.watermark && (
              <span
                className="absolute text-white/65"
                style={{ left: "4%", top: "3%", fontSize: 22 * scale, fontFamily: `"${cssFamily("notosans")}", sans-serif`, textShadow: "0 1px 2px rgba(0,0,0,.6)" }}
              >
                {config.watermark}
              </span>
            )}
            {logoUrl && extras.logo && (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={logoUrl}
                alt=""
                className="absolute"
                style={{
                  width: `${extras.logo.scale * 100}%`,
                  opacity: extras.logo.opacity,
                  [extras.logo.corner.startsWith("t") ? "top" : "bottom"]: "3.5%",
                  [extras.logo.corner.endsWith("l") ? "left" : "right"]: "3.5%",
                }}
              />
            )}
          </div>
        )}
      </div>
    </div>
  );
}

function Caption({
  words,
  active,
  t,
  translation,
  style,
  scale,
  font,
  translationFont,
  lang,
  rtl,
}: {
  words: CWord[];
  active: number;
  t: number;
  translation: string | null;
  style: CStyle;
  scale: number;
  font: string;
  translationFont: string;
  lang: string;
  rtl: boolean;
}) {
  const urdu = lang.split("-")[0] === "ur" && !lang.endsWith("-Latn");
  // style.size is the em size in px at 1080 (the export converts it per font for libass); Urdu gets the same boost.
  const size = style.size * scale * (urdu ? 1.15 : 1);
  const stroke = style.outline * scale;
  const anim = style.animation;
  const sep = joiner(lang);
  const emoji = style.emoji ? words.find((w) => w.emoji)?.emoji : null;
  const showUpTo = anim === "reveal" ? active : words.length - 1;

  const textStyle: CSSProperties = {
    fontFamily: font,
    fontSize: size,
    lineHeight: urdu ? 1.75 : 1.2,
    color: style.color,
    letterSpacing: style.spacing * scale,
    textTransform: style.uppercase ? "uppercase" : undefined,
    textShadow: style.shadow && !style.box ? `${style.shadow * scale}px ${style.shadow * scale}px 0 rgba(0,0,0,.45)` : undefined,
    WebkitTextStroke: !style.box && stroke ? `${stroke * 2}px ${style.outline_color}` : undefined,
    paintOrder: "stroke fill",
  };
  const boxStyle: CSSProperties = style.box
    ? {
        background: hexToRgba(style.box_color, style.box_opacity),
        padding: `${Math.max(6, style.outline) * scale * 0.6}px ${Math.max(6, style.outline) * scale}px`,
        borderRadius: 6 * scale,
        boxDecorationBreak: "clone",
        WebkitBoxDecorationBreak: "clone",
      }
    : {};

  const entrance =
    anim === "fade" ? "kly-fade" : anim === "bounce" ? "kly-bounce" : anim === "slide" ? "kly-slide" : anim === "pop" ? "kly-pop" : anim === "word" ? "kly-bounce" : "";

  return (
    <div className="absolute inset-x-0 flex justify-center px-[6%]" style={{ top: `${style.y * 100}%`, transform: "translateY(-50%)" }}>
      <div dir={rtl ? "rtl" : "ltr"} className={clsx("text-center", entrance)} style={{ maxWidth: "100%" }}>
        <span style={{ ...textStyle, ...boxStyle }}>
          {words.map((w, i) => {
            const isActive = i === active && ["highlight", "pop", "reveal"].includes(anim);
            const sung = anim === "karaoke" && (i < active || (i === active && t >= w.start));
            const hidden = i > showUpTo;
            const ws: CSSProperties = { visibility: hidden ? "hidden" : undefined };
            if (isActive || sung) {
              if (style.highlight_mode === "box" && !sung) {
                Object.assign(ws, {
                  background: style.highlight,
                  borderRadius: 8 * scale,
                  padding: `0 ${6 * scale}px`,
                  WebkitTextStroke: "0px transparent",
                  boxDecorationBreak: "clone",
                });
              } else {
                ws.color = style.highlight;
                if (style.highlight_mode === "scale" && !sung) Object.assign(ws, { display: "inline-block", transform: "scale(1.12)" });
              }
            } else if (style.keywords && w.keyword) {
              ws.color = style.keyword_color;
            }
            return (
              <span key={`${i}-${w.start}`}>
                {i > 0 && sep}
                <span style={ws}>{w.text}</span>
              </span>
            );
          })}
          {emoji && (anim !== "reveal" || words.slice(0, active + 1).some((w) => w.emoji)) && (
            <span style={{ fontFamily: `"${cssFamily("emoji")}", sans-serif`, color: style.highlight }}> {emoji}</span>
          )}
        </span>
        {translation && (
          <div
            dir="auto"
            style={{
              ...textStyle,
              ...boxStyle,
              fontFamily: translationFont,
              fontSize: size * style.translation_scale,
              color: style.translation_color,
              marginTop: 4 * scale,
              display: "inline-block",
            }}
          >
            {translation}
          </div>
        )}
      </div>
    </div>
  );
}
