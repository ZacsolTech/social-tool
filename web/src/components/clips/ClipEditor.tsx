"use client";

import clsx from "clsx";
import { ChevronLeft, ChevronRight, LoaderCircle, Pause, Play, Save, X } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import type { Preset } from "@/lib/captions";
import { type Clip, type ClipAspect, type ClipLayout, type ClipLook, type ClipPatch, type KTranscript, getClipsTranscript } from "@/lib/clips";
import { clampRange, clock, needsRender, parseClock, parseHashtags, stepEdge } from "@/lib/clipsCore";
import { Field, Segmented, Toggle } from "../captions/ui";

type Tab = "trim" | "text" | "look";

export function ClipEditor({
  clip,
  sourceUrl,
  transcriptUrl,
  duration,
  presets,
  busy,
  onSave,
  onClose,
}: {
  clip: Clip;
  sourceUrl: string;
  transcriptUrl: string | null;
  duration: number;
  presets: Preset[];
  busy: boolean;
  onSave: (patch: ClipPatch) => Promise<void>;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<Tab>("trim");
  const [range, setRange] = useState({ start: clip.start, end: clip.end });
  const [startText, setStartText] = useState(clock(clip.start, true));
  const [endText, setEndText] = useState(clock(clip.end, true));
  const [hook, setHook] = useState(clip.hook);
  const [title, setTitle] = useState(clip.title);
  const [description, setDescription] = useState(clip.description);
  const [tags, setTags] = useState(clip.hashtags.join(" "));
  const [look, setLook] = useState<ClipLook>(clip.look);
  const [transcript, setTranscript] = useState<KTranscript | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [playing, setPlaying] = useState(false);
  const video = useRef<HTMLVideoElement>(null);
  const dialog = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (transcriptUrl) getClipsTranscript(transcriptUrl).then(setTranscript).catch(() => undefined);
  }, [transcriptUrl]);

  useEffect(() => {
    setStartText(clock(range.start, true));
    setEndText(clock(range.end, true));
  }, [range]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    dialog.current?.focus();
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      window.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [onClose]);

  // Play only the chosen range of the original video.
  useEffect(() => {
    const v = video.current;
    if (!v) return;
    const tick = () => {
      if (v.currentTime >= range.end) {
        v.pause();
        v.currentTime = range.start;
      }
    };
    v.addEventListener("timeupdate", tick);
    return () => v.removeEventListener("timeupdate", tick);
  }, [range]);

  const lines = transcript?.lines ?? [];
  const visible = useMemo(() => lines.filter((l) => l.end > range.start - 45 && l.start < range.end + 45), [lines, range]);

  function set(r: { start: number; end: number }) {
    setRange(clampRange(r, duration));
  }

  function togglePlay() {
    const v = video.current;
    if (!v) return;
    if (v.paused) {
      if (v.currentTime < range.start || v.currentTime >= range.end - 0.1) v.currentTime = range.start;
      void v.play();
    } else v.pause();
  }

  function seek(t: number) {
    const v = video.current;
    if (v) v.currentTime = t;
  }

  const patch: ClipPatch = {};
  if (Math.abs(range.start - clip.start) > 0.01) patch.start = range.start;
  if (Math.abs(range.end - clip.end) > 0.01) patch.end = range.end;
  if (hook.trim() !== clip.hook) patch.hook = hook.trim();
  if (title.trim() !== clip.title) patch.title = title.trim();
  if (description.trim() !== clip.description) patch.description = description.trim();
  const newTags = parseHashtags(tags);
  if (newTags.join(" ") !== clip.hashtags.join(" ")) patch.hashtags = newTags;
  const lookPatch: Partial<ClipLook> = {};
  for (const k of Object.keys(look) as (keyof ClipLook)[]) {
    if (JSON.stringify(look[k]) !== JSON.stringify(clip.look[k])) (lookPatch as Record<string, unknown>)[k] = look[k];
  }
  if (Object.keys(lookPatch).length) patch.look = lookPatch;
  const changed = Object.keys(patch).length > 0;
  const rerender = needsRender(patch as Record<string, unknown>);

  async function save() {
    setError(null);
    try {
      await onSave(patch);
      onClose();
    } catch (e) {
      setError((e as Error).message || "Couldn't save the changes.");
    }
  }

  const inRange = (l: { start: number; end: number }) => l.end > range.start + 0.05 && l.start < range.end - 0.05;

  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-0 backdrop-blur-sm sm:items-center sm:p-6" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div
        ref={dialog}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-label={`Edit clip ${clip.rank}`}
        className="flex max-h-[94vh] w-full max-w-5xl flex-col overflow-hidden rounded-t-3xl bg-elev shadow-2xl outline-none sm:rounded-3xl"
      >
        <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-3 sm:px-6">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wider text-muted">Edit clip #{clip.rank}</p>
            <p className="truncate font-semibold">{clip.title}</p>
          </div>
          <button type="button" onClick={onClose} aria-label="Close" className="grid size-9 place-items-center rounded-full text-muted transition hover:bg-line hover:text-fg">
            <X className="size-5" />
          </button>
        </header>

        <div className="grid min-h-0 flex-1 gap-0 overflow-y-auto lg:grid-cols-[minmax(0,1fr)_380px] lg:overflow-hidden">
          <div className="space-y-3 p-4 sm:p-6 lg:overflow-y-auto">
            <div className="relative overflow-hidden rounded-2xl bg-black">
              <video
                ref={video}
                src={`${sourceUrl}#t=${range.start}`}
                playsInline
                preload="auto"
                onPlay={() => setPlaying(true)}
                onPause={() => setPlaying(false)}
                className="aspect-video w-full object-contain"
              />
              <button
                type="button"
                onClick={togglePlay}
                className="absolute bottom-3 left-3 inline-flex items-center gap-1.5 rounded-full bg-white/90 px-3 py-1.5 text-xs font-semibold text-black"
              >
                {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />} {playing ? "Pause" : "Play this clip"}
              </button>
              <span className="absolute bottom-3 right-3 rounded-full bg-black/70 px-2 py-1 font-mono text-xs text-white">{clock(range.end - range.start, true)}</span>
            </div>
            <p className="text-xs text-muted">
              The original video, playing only the part you chose. {rerender ? "Saving makes the clip again with your changes." : ""}
            </p>
            <RangeBar duration={duration} range={range} onSeek={seek} />
          </div>

          <div className="flex min-h-0 flex-col border-t border-line lg:border-l lg:border-t-0">
            <div className="p-4 pb-0 sm:px-6">
              <Segmented<Tab>
                label="Editor section"
                value={tab}
                onChange={setTab}
                options={[
                  { id: "trim", label: "Trim" },
                  { id: "text", label: "Hook & text" },
                  { id: "look", label: "Look" },
                ]}
              />
            </div>
            <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4 sm:px-6">
              {tab === "trim" && (
                <>
                  <div className="grid grid-cols-2 gap-3">
                    {(["start", "end"] as const).map((edge) => (
                      <Field key={edge} label={edge === "start" ? "Starts at" : "Ends at"}>
                        <div className="flex items-center gap-1">
                          <button
                            type="button"
                            title="One sentence earlier"
                            aria-label={`${edge}: one sentence earlier`}
                            onClick={() => set({ ...range, [edge]: stepEdge(lines, edge, range[edge], -1) })}
                            disabled={!lines.length}
                            className="grid size-8 shrink-0 place-items-center rounded-lg border border-line text-muted transition hover:text-fg disabled:opacity-40"
                          >
                            <ChevronLeft className="size-4" />
                          </button>
                          <input
                            aria-label={edge === "start" ? "Start time" : "End time"}
                            value={edge === "start" ? startText : endText}
                            onChange={(e) => (edge === "start" ? setStartText(e.target.value) : setEndText(e.target.value))}
                            onBlur={(e) => {
                              const v = parseClock(e.target.value);
                              if (v === null) setRange({ ...range });
                              else set({ ...range, [edge]: v });
                            }}
                            onKeyDown={(e) => e.key === "Enter" && (e.target as HTMLInputElement).blur()}
                            className="w-full min-w-0 rounded-lg border border-line bg-bg px-2 py-1.5 text-center font-mono text-sm"
                          />
                          <button
                            type="button"
                            title="One sentence later"
                            aria-label={`${edge}: one sentence later`}
                            onClick={() => set({ ...range, [edge]: stepEdge(lines, edge, range[edge], 1) })}
                            disabled={!lines.length}
                            className="grid size-8 shrink-0 place-items-center rounded-lg border border-line text-muted transition hover:text-fg disabled:opacity-40"
                          >
                            <ChevronRight className="size-4" />
                          </button>
                        </div>
                        <div className="flex justify-center gap-1 text-[11px]">
                          {[-0.5, 0.5].map((d) => (
                            <button key={d} type="button" onClick={() => set({ ...range, [edge]: range[edge] + d })} className="rounded px-1.5 py-0.5 text-muted hover:bg-line hover:text-fg">
                              {d > 0 ? "+" : "−"}0.5 s
                            </button>
                          ))}
                        </div>
                      </Field>
                    ))}
                  </div>
                  <p className="text-xs text-muted">Tap a sentence to start or end the clip there. Edges are kept clear of words, so nothing gets cut in half.</p>
                  <ol className="space-y-1" dir={transcript?.rtl ? "rtl" : undefined}>
                    {!transcript && transcriptUrl && (
                      <li className="flex items-center gap-2 text-sm text-muted">
                        <LoaderCircle className="size-4 animate-spin" /> Loading the transcript…
                      </li>
                    )}
                    {visible.map((l) => (
                      <li key={l.i} className={clsx("group rounded-xl border p-2 text-sm transition", inRange(l) ? "border-accent/40 bg-accent-soft/40" : "border-transparent text-muted")}>
                        <button type="button" onClick={() => seek(l.start)} className="w-full text-start">
                          <span className="mr-1.5 font-mono text-[10px] text-subtle" dir="ltr">
                            {clock(l.start)}
                          </span>
                          {l.text}
                        </button>
                        <div className="mt-1 flex gap-2 text-[11px] opacity-80 group-hover:opacity-100" dir="ltr">
                          <button type="button" onClick={() => set({ start: Math.max(0, l.start - 0.15), end: Math.max(range.end, l.end + 0.25) })} className="rounded-full bg-line px-2 py-0.5 font-medium hover:bg-line-strong">
                            Start here
                          </button>
                          <button type="button" onClick={() => set({ start: Math.min(range.start, l.start - 0.15), end: l.end + 0.25 })} className="rounded-full bg-line px-2 py-0.5 font-medium hover:bg-line-strong">
                            End here
                          </button>
                        </div>
                      </li>
                    ))}
                  </ol>
                </>
              )}

              {tab === "text" && (
                <>
                  <Field label="Hook title" hint="On screen for the first 4 s">
                    <input value={hook} onChange={(e) => setHook(e.target.value)} maxLength={140} className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm" placeholder="e.g. Nobody tells you this about money" />
                  </Field>
                  <Toggle checked={look.hook} onChange={(v) => setLook({ ...look, hook: v })} label="Show the hook title" />
                  <Field label="Title">
                    <input value={title} onChange={(e) => setTitle(e.target.value)} maxLength={200} className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm" />
                  </Field>
                  <Field label="Post text">
                    <textarea value={description} onChange={(e) => setDescription(e.target.value)} maxLength={1000} rows={3} className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm" />
                  </Field>
                  <Field label="Hashtags">
                    <input value={tags} onChange={(e) => setTags(e.target.value)} className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm" placeholder="#money #podcast" />
                  </Field>
                  <p className="text-xs text-muted">Title, post text and hashtags are saved instantly. Changing the hook makes the video again.</p>
                </>
              )}

              {tab === "look" && <LookControls look={look} setLook={setLook} presets={presets} />}
            </div>
            <footer className="space-y-2 border-t border-line p-4 sm:px-6">
              {error && <p className="text-sm text-danger">{error}</p>}
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={save}
                  disabled={!changed || busy}
                  className="inline-flex flex-1 items-center justify-center gap-2 rounded-full bg-accent px-5 py-3 text-sm font-semibold text-accent-fg transition hover:brightness-105 disabled:opacity-50"
                >
                  {busy ? <LoaderCircle className="size-4 animate-spin" /> : <Save className="size-4" />}
                  {!changed ? "No changes" : rerender ? "Save & make the clip again" : "Save"}
                </button>
                <button type="button" onClick={onClose} className="rounded-full px-4 py-3 text-sm font-medium text-muted transition hover:text-fg">
                  Cancel
                </button>
              </div>
            </footer>
          </div>
        </div>
      </div>
    </div>
  );
}

function RangeBar({ duration, range, onSeek }: { duration: number; range: { start: number; end: number }; onSeek: (t: number) => void }) {
  const left = (range.start / Math.max(1, duration)) * 100;
  const width = Math.max(0.6, ((range.end - range.start) / Math.max(1, duration)) * 100);
  return (
    <div>
      <button
        type="button"
        aria-label="Position of the clip in the video"
        onClick={(e) => {
          const r = e.currentTarget.getBoundingClientRect();
          onSeek(((e.clientX - r.left) / r.width) * duration);
        }}
        className="relative block h-3 w-full overflow-hidden rounded-full bg-line"
      >
        <span className="absolute inset-y-0 rounded-full bg-accent" style={{ left: `${left}%`, width: `${width}%` }} />
      </button>
      <div className="mt-1 flex justify-between font-mono text-[10px] text-subtle">
        <span>0:00</span>
        <span>
          {clock(range.start)} – {clock(range.end)}
        </span>
        <span>{clock(duration)}</span>
      </div>
    </div>
  );
}

type LookBase = Pick<ClipLook, "aspect" | "layout" | "captions" | "hook" | "remove_fillers" | "remove_silences" | "progress_bar" | "watermark" | "quality"> & {
  style?: ClipLook["style"];
  preset?: string;
};

/** Shape, framing, captions and extras. Used before the search (preset id) and per clip (full style). */
export function LookControls<L extends LookBase>({ look, setLook, presets }: { look: L; setLook: (l: L) => void; presets: Preset[] }) {
  const presetId = look.style?.preset ?? look.preset ?? "bold-pop";
  return (
    <div className="space-y-4">
      <Field label="Shape">
        <Segmented<ClipAspect>
          label="Shape"
          value={look.aspect}
          onChange={(v) => setLook({ ...look, aspect: v })}
          options={[
            { id: "9:16", label: "9:16", title: "TikTok, Reels, Shorts" },
            { id: "4:5", label: "4:5", title: "Instagram & Facebook feed" },
            { id: "1:1", label: "1:1", title: "Square" },
            { id: "original", label: "Original", title: "Keep the video's shape" },
          ]}
        />
      </Field>
      {look.aspect !== "original" && (
        <Field label="Framing">
          <Segmented<ClipLayout>
            label="Framing"
            value={look.layout}
            onChange={(v) => setLook({ ...look, layout: v })}
            options={[
              { id: "smart", label: "Follow speaker", title: "AI keeps whoever talks in frame" },
              { id: "blur", label: "Blur fill", title: "Whole picture over a blurred copy" },
              { id: "fit", label: "Fit", title: "Whole picture with bars" },
            ]}
          />
        </Field>
      )}
      <Toggle checked={look.captions} onChange={(v) => setLook({ ...look, captions: v })} label="Animated captions" hint="Every word timed, keywords highlighted" />
      {look.captions && (
        <Field label="Caption style">
          <PresetChips
            presets={presets}
            value={presetId}
            onChange={(id) => {
              const p = presets.find((x) => x.id === id);
              if (!p) return;
              if (look.style) setLook({ ...look, style: { ...p.style, y: look.aspect === "9:16" || look.aspect === "4:5" ? p.style.y : 0.8 } });
              else setLook({ ...look, preset: id });
            }}
          />
        </Field>
      )}
      <Toggle checked={look.hook} onChange={(v) => setLook({ ...look, hook: v })} label="Hook title" hint="Bold text at the top for the first seconds" />
      <Toggle checked={look.remove_fillers} onChange={(v) => setLook({ ...look, remove_fillers: v })} label="Remove ums & uhs" />
      <Toggle checked={look.remove_silences} onChange={(v) => setLook({ ...look, remove_silences: v })} label="Remove long pauses" hint="Tighter, faster clips" />
      <Toggle checked={look.progress_bar} onChange={(v) => setLook({ ...look, progress_bar: v })} label="Progress bar" hint="Keeps viewers to the end" />
      <Toggle checked={look.watermark} onChange={(v) => setLook({ ...look, watermark: v })} label="Small klyprima.com credit" hint="Optional, thank you if you keep it" />
      <Field label="Quality">
        <Segmented<"1080p" | "720p">
          label="Quality"
          value={look.quality}
          onChange={(v) => setLook({ ...look, quality: v })}
          options={[
            { id: "1080p", label: "1080p" },
            { id: "720p", label: "720p (faster)" },
          ]}
        />
      </Field>
    </div>
  );
}

export function PresetChips({ presets, value, onChange }: { presets: Preset[]; value: string; onChange: (id: string) => void }) {
  return (
    <div role="radiogroup" aria-label="Caption style" className="grid grid-cols-2 gap-2 sm:grid-cols-3">
      {presets.map((p) => (
        <button
          key={p.id}
          type="button"
          role="radio"
          aria-checked={value === p.id}
          onClick={() => onChange(p.id)}
          className={clsx(
            "flex h-14 flex-col items-center justify-center rounded-xl border bg-neutral-900 px-2 text-center transition",
            value === p.id ? "border-accent ring-2 ring-accent/40" : "border-line hover:border-line-strong",
          )}
        >
          <span
            className="block max-w-full truncate text-sm font-extrabold leading-tight"
            style={{
              color: p.style.color,
              textTransform: p.style.uppercase ? "uppercase" : "none",
              WebkitTextStroke: p.style.box ? undefined : `${Math.min(1.5, p.style.outline / 4)}px ${p.style.outline_color}`,
              background: p.style.box ? p.style.box_color : undefined,
              padding: p.style.box ? "0 4px" : undefined,
              borderRadius: 4,
            }}
          >
            Aa <span style={{ color: p.style.highlight }}>Bb</span>
          </span>
          <span className="mt-1 block truncate text-[10px] font-medium text-white/70">{p.label}</span>
        </button>
      ))}
    </div>
  );
}
