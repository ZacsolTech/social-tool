"use client";

import clsx from "clsx";
import { Check, ChevronDown, CircleAlert, Copy, Download, FileText, LoaderCircle, Pencil, RotateCcw, Sparkles, Subtitles } from "lucide-react";
import { useState } from "react";
import { formatBytes } from "@/lib/api";
import type { Clip } from "@/lib/clips";
import { SCORE_LABELS, type ScoreKey, TIER_LABEL, clock, postText, scoreTier } from "@/lib/clipsCore";

const ASPECT_CLASS: Record<string, string> = { "9:16": "aspect-[9/16]", "1:1": "aspect-square", "4:5": "aspect-[4/5]" };

export function ScoreRing({ score, size = 52 }: { score: number; size?: number }) {
  const tier = scoreTier(score);
  const r = size / 2 - 4;
  const c = 2 * Math.PI * r;
  return (
    <div className="relative grid shrink-0 place-items-center" style={{ width: size, height: size }} title={`${TIER_LABEL[tier]}: ${score}/100`}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="currentColor" strokeWidth={4} className="text-line" />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke="currentColor"
          strokeWidth={4}
          strokeLinecap="round"
          strokeDasharray={`${(c * score) / 100} ${c}`}
          className={clsx(tier === "viral" ? "text-ok" : tier === "strong" ? "text-accent" : tier === "good" ? "text-amber-500" : "text-subtle")}
        />
      </svg>
      <span className="absolute font-mono text-sm font-semibold tabular-nums">{score}</span>
    </div>
  );
}

function ScoreBars({ clip }: { clip: Clip }) {
  return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-2">
      {(Object.keys(SCORE_LABELS) as ScoreKey[]).map((k) => (
        <div key={k} title={SCORE_LABELS[k].hint}>
          <div className="flex justify-between text-[11px]">
            <dt className="text-muted">{SCORE_LABELS[k].label}</dt>
            <dd className="font-mono tabular-nums">{clip.scores[k]}</dd>
          </div>
          <div className="mt-0.5 h-1.5 overflow-hidden rounded-full bg-line">
            <div className="h-full rounded-full bg-accent" style={{ width: `${clip.scores[k]}%` }} />
          </div>
        </div>
      ))}
    </dl>
  );
}

export function ClipCard({
  clip,
  sourceAspect,
  busy,
  onEdit,
  onRetry,
  onCaptions,
}: {
  clip: Clip;
  sourceAspect: number;
  busy: boolean;
  onEdit: () => void;
  onRetry: () => void;
  onCaptions: () => void;
}) {
  const [open, setOpen] = useState(false);
  const [copied, setCopied] = useState(false);
  const tier = scoreTier(clip.score);
  const ready = clip.status === "done" && !!clip.video;
  const working = clip.status === "queued" || clip.status === "rendering";
  const aspectClass = ASPECT_CLASS[clip.look.aspect];

  async function copy() {
    try {
      await navigator.clipboard.writeText(postText(clip));
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      /* clipboard blocked: nothing to do */
    }
  }

  return (
    <article className="flex flex-col overflow-hidden rounded-3xl border border-line bg-elev shadow-card" aria-label={`Clip ${clip.rank}: ${clip.title}`}>
      <div className="relative bg-black">
        <div className={clsx("relative mx-auto w-full", aspectClass ?? "")} style={aspectClass ? undefined : { aspectRatio: String(sourceAspect || 16 / 9) }}>
          {ready ? (
            <video
              key={clip.video}
              src={`${clip.video}&inline=1`}
              poster={clip.thumb ?? undefined}
              controls
              playsInline
              preload="none"
              className="absolute inset-0 size-full object-contain"
            />
          ) : (
            <div className="absolute inset-0 grid place-items-center p-4 text-center text-white">
              {clip.thumb && (
                // eslint-disable-next-line @next/next/no-img-element
                <img src={clip.thumb} alt="" className="absolute inset-0 size-full object-cover opacity-30" />
              )}
              <div className="relative space-y-2">
                {working ? (
                  <>
                    <LoaderCircle className="mx-auto size-7 animate-spin" />
                    <p className="text-sm font-medium">{clip.status === "queued" ? "Waiting…" : `Making it… ${Math.round(clip.progress * 100)}%`}</p>
                    {clip.status === "rendering" && (
                      <div className="mx-auto h-1.5 w-28 overflow-hidden rounded-full bg-white/20">
                        <div className="h-full rounded-full bg-white transition-[width] duration-500" style={{ width: `${Math.max(3, clip.progress * 100)}%` }} />
                      </div>
                    )}
                  </>
                ) : (
                  <>
                    <CircleAlert className="mx-auto size-7" />
                    <p className="text-sm">{clip.error ?? "Not made yet."}</p>
                    <button type="button" onClick={onRetry} disabled={busy} className="inline-flex items-center gap-1.5 rounded-full bg-white px-3 py-1.5 text-xs font-semibold text-black disabled:opacity-60">
                      <RotateCcw className="size-3.5" /> {clip.status === "pending" ? "Make this clip" : "Try again"}
                    </button>
                  </>
                )}
              </div>
            </div>
          )}
        </div>
        <span className="absolute left-3 top-3 rounded-full bg-black/70 px-2 py-0.5 font-mono text-xs font-semibold text-white">#{clip.rank}</span>
        <span className="absolute right-3 top-3 rounded-full bg-black/70 px-2 py-0.5 font-mono text-xs text-white">{clock(clip.end - clip.start)}</span>
      </div>

      <div className="flex flex-1 flex-col gap-3 p-4">
        <div className="flex items-start gap-3">
          <ScoreRing score={clip.score} />
          <div className="min-w-0 flex-1">
            <p className={clsx("text-[11px] font-semibold uppercase tracking-wider", tier === "viral" ? "text-ok" : tier === "strong" ? "text-accent" : "text-muted")}>
              {TIER_LABEL[tier]}
              {clip.method === "ai" && (
                <span className="ml-1.5 inline-flex items-center gap-0.5 normal-case tracking-normal text-subtle">
                  <Sparkles className="size-3" /> AI pick
                </span>
              )}
            </p>
            <h3 className="mt-0.5 line-clamp-2 font-semibold leading-snug tracking-tight">{clip.title}</h3>
            <p className="mt-0.5 text-xs text-muted">
              {clock(clip.start)} – {clock(clip.end)}
              {clip.size ? ` · ${formatBytes(clip.size)}` : ""}
            </p>
          </div>
        </div>

        {clip.hook && clip.look.hook && (
          <p className="rounded-xl bg-accent-soft/60 px-3 py-2 text-sm">
            <span className="mr-1 text-[10px] font-semibold uppercase tracking-wider text-accent">Hook</span>
            {clip.hook}
          </p>
        )}

        <button type="button" onClick={() => setOpen((v) => !v)} aria-expanded={open} className="flex items-center justify-between text-left text-xs font-medium text-muted transition hover:text-fg">
          Why this clip
          <ChevronDown className={clsx("size-4 transition", open && "rotate-180")} />
        </button>
        {open && (
          <div className="space-y-3">
            {clip.reason && <p className="text-sm text-muted">{clip.reason}</p>}
            <ScoreBars clip={clip} />
            {clip.text && <p className="line-clamp-6 rounded-xl bg-bg p-3 text-xs leading-relaxed text-muted">{clip.text}</p>}
          </div>
        )}

        {clip.description || clip.hashtags.length ? (
          <div className="rounded-xl border border-line p-3 text-xs">
            {clip.description && <p className="line-clamp-3">{clip.description}</p>}
            {clip.hashtags.length > 0 && <p className="mt-1 text-accent">{clip.hashtags.join(" ")}</p>}
            <button type="button" onClick={copy} className="mt-2 inline-flex items-center gap-1 font-medium text-muted transition hover:text-fg">
              {copied ? <Check className="size-3.5 text-ok" /> : <Copy className="size-3.5" />} {copied ? "Copied" : "Copy title, text & hashtags"}
            </button>
          </div>
        ) : null}

        <div className="mt-auto flex flex-wrap gap-2 pt-1">
          {ready ? (
            <a
              href={clip.video!}
              download
              className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-full bg-accent px-4 py-2 text-sm font-semibold text-accent-fg transition hover:brightness-105"
            >
              <Download className="size-4" /> Download
            </a>
          ) : (
            <span className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-full bg-line px-4 py-2 text-sm font-semibold text-muted">
              <Download className="size-4" /> Download
            </span>
          )}
          <button
            type="button"
            onClick={onEdit}
            disabled={busy}
            className="inline-flex items-center gap-1.5 rounded-full border border-line-strong px-3.5 py-2 text-sm font-medium transition hover:border-fg disabled:opacity-60"
          >
            <Pencil className="size-4" /> Edit
          </button>
        </div>
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {clip.srt && (
            <a href={clip.srt} className="inline-flex items-center gap-1 text-muted transition hover:text-fg">
              <FileText className="size-3.5" /> SRT
            </a>
          )}
          {ready && (
            <button type="button" onClick={onCaptions} className="inline-flex items-center gap-1 text-muted transition hover:text-fg">
              <Subtitles className="size-3.5" /> Edit captions word by word
            </button>
          )}
        </div>
      </div>
    </article>
  );
}
