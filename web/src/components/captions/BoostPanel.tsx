"use client";

import clsx from "clsx";
import { ImagePlus, Languages, LoaderCircle, Scissors, Sparkles, Type, WandSparkles, X } from "lucide-react";
import { useRef, useState } from "react";
import type { CConfig, CJob, Extras, Mode } from "@/lib/captions";
import type { CTranscript } from "@/lib/captionsCore";
import { Badge, ColorInput, Field, Segmented, Slider, Toggle } from "./ui";

export function BoostPanel({
  job,
  config,
  transcript,
  extras,
  setExtras,
  busy,
  onEnhance,
  onTranslate,
  onRomanize,
  onLogo,
  onLogoRemove,
}: {
  job: CJob;
  config: CConfig | null;
  transcript: CTranscript;
  extras: Extras;
  setExtras: (x: Extras) => void;
  busy: string | null;
  onEnhance: () => void;
  onTranslate: (target: string) => void;
  onRomanize: () => void;
  onLogo: (f: File) => void;
  onLogoRemove: () => void;
}) {
  const set = (patch: Partial<Extras>) => setExtras({ ...extras, ...patch });
  const ai = !!config?.features.ai;
  const lang = transcript.language;
  const base = lang.split("-")[0];
  const canRoman = !lang.endsWith("-Latn") && ["ur", "hi", "pa", "sd"].includes(base);
  const targets = (config?.translate_targets ?? []).filter((l) => l.code !== lang && (ai || l.code === "en"));
  const [target, setTarget] = useState(base === "en" ? "ur" : "en");
  const logoInput = useRef<HTMLInputElement>(null);
  const working = job.state !== "ready";
  const tr = transcript.translation_lang;
  const trName = config?.translate_targets.find((l) => l.code === tr)?.name ?? tr;

  return (
    <div className="space-y-6">
      <Card
        icon={WandSparkles}
        title="Highlights, emojis & hook ideas"
        badge={ai ? <Badge>AI</Badge> : <Badge tone="muted">Smart</Badge>}
        body="Picks the most important word in each line, adds a fitting emoji and suggests scroll-stopping hook titles."
      >
        <button type="button" onClick={onEnhance} disabled={working} className={primary}>
          {busy === "enhance" ? <LoaderCircle className="size-4 animate-spin" /> : <Sparkles className="size-4" />} Auto-highlight
        </button>
      </Card>

      <Card icon={Type} title="Hook title" body="Big text at the top for the first seconds. The #1 trick to stop the scroll.">
        <input
          value={extras.hook}
          onChange={(e) => set({ hook: e.target.value.slice(0, 140) })}
          dir="auto"
          placeholder="e.g. 3 money mistakes to avoid"
          aria-label="Hook title"
          className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
        />
        {job.hooks.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {job.hooks.map((h) => (
              <button key={h} type="button" dir="auto" onClick={() => set({ hook: h })} className="rounded-full border border-accent/40 bg-accent-soft/50 px-3 py-1 text-xs transition hover:border-accent">
                {h}
              </button>
            ))}
          </div>
        )}
        {extras.hook && (
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Show for">
              <Segmented
                label="Show hook for"
                value={String(extras.hook_seconds)}
                onChange={(v) => set({ hook_seconds: Number(v) })}
                options={[
                  { id: "3", label: "3s" },
                  { id: "5", label: "5s" },
                  { id: "0", label: "Whole" },
                ]}
              />
            </Field>
            <ColorInput label="Text" value={extras.hook_color} onChange={(v) => set({ hook_color: v })} />
            <ColorInput label="Background" value={extras.hook_bg} onChange={(v) => set({ hook_bg: v })} />
          </div>
        )}
      </Card>

      <Card
        icon={Languages}
        title="Translate"
        badge={ai ? <Badge>AI</Badge> : <Badge tone="muted">English</Badge>}
        body={ai ? "Reach more people: captions in another language, or both languages at once." : "Translate the speech into English captions, or show both languages at once."}
      >
        {targets.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            <select value={targets.some((l) => l.code === target) ? target : targets[0].code} onChange={(e) => setTarget(e.target.value)} aria-label="Translate to" className="min-w-0 flex-1 rounded-xl border border-line bg-bg px-3 py-2 text-sm">
              {targets.map((l) => (
                <option key={l.code} value={l.code}>
                  {l.name}
                  {l.native !== l.name ? ` · ${l.native}` : ""}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={() => onTranslate(targets.some((l) => l.code === target) ? target : targets[0].code)}
              disabled={working}
              className={secondary}
            >
              {busy === "translate" ? <LoaderCircle className="size-4 animate-spin" /> : <Languages className="size-4" />} Translate
            </button>
          </div>
        ) : (
          <p className="rounded-xl bg-bg p-3 text-sm text-muted">Your captions are already in English. Translation into other languages is coming soon.</p>
        )}
        {tr && (
          <Field label={`Show (${trName} added)`}>
            <Segmented<Mode>
              label="Which captions to show"
              value={extras.mode}
              onChange={(v) => set({ mode: v })}
              options={[
                { id: "original", label: "Original" },
                { id: "translation", label: trName ?? "Translation" },
                { id: "dual", label: "Both" },
              ]}
            />
          </Field>
        )}
        {canRoman && (
          <div className="flex items-center justify-between gap-3 rounded-xl bg-bg p-3">
            <p className="text-sm">
              <span className="font-medium">{base === "hi" ? "Hinglish" : "Roman Urdu"}</span>
              <span className="block text-xs text-muted">Write the captions in English letters, like “kya haal hai”.</span>
            </p>
            <button type="button" onClick={onRomanize} disabled={working} className={secondary}>
              {busy === "romanize" ? <LoaderCircle className="size-4 animate-spin" /> : "Aa"} Convert
            </button>
          </div>
        )}
      </Card>

      <Card icon={Scissors} title="Tighter edit" body="Cut “um”, “uh” and long pauses from the video when you export. Captions follow automatically.">
        <Toggle label="Remove filler words" hint="um, uh, hmm…" checked={extras.remove_fillers} onChange={(v) => set({ remove_fillers: v })} />
        <Toggle label="Remove long pauses" hint="Silences longer than 0.6 s" checked={extras.remove_silences} onChange={(v) => set({ remove_silences: v })} />
      </Card>

      <Card icon={ImagePlus} title="Brand & extras" body="Your logo, a progress bar that keeps people watching, and an optional credit.">
        <div className="flex flex-wrap items-center gap-2">
          <input
            ref={logoInput}
            type="file"
            accept="image/png,image/jpeg,image/webp"
            className="sr-only"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onLogo(f);
              e.target.value = "";
            }}
          />
          <button type="button" onClick={() => logoInput.current?.click()} disabled={working} className={secondary}>
            <ImagePlus className="size-4" /> {job.has_logo ? "Change logo" : "Add logo"}
          </button>
          {job.has_logo && (
            <button type="button" onClick={onLogoRemove} className="inline-flex items-center gap-1 text-sm text-muted hover:text-fg">
              <X className="size-4" /> Remove
            </button>
          )}
        </div>
        {job.has_logo && extras.logo && (
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Corner">
              <Segmented
                label="Logo corner"
                value={extras.logo.corner}
                onChange={(v) => set({ logo: { ...extras.logo!, corner: v } })}
                options={[
                  { id: "tl", label: "↖" },
                  { id: "tr", label: "↗" },
                  { id: "bl", label: "↙" },
                  { id: "br", label: "↘" },
                ]}
              />
            </Field>
            <Slider label="Logo size" value={extras.logo.scale} min={0.06} max={0.35} step={0.01} onChange={(v) => set({ logo: { ...extras.logo!, scale: v } })} format={(v) => `${Math.round(v * 100)}%`} />
            <Slider label="Opacity" value={extras.logo.opacity} min={0.2} max={1} step={0.05} onChange={(v) => set({ logo: { ...extras.logo!, opacity: v } })} format={(v) => `${Math.round(v * 100)}%`} />
          </div>
        )}
        <Field label="Progress bar">
          <div className="flex items-center gap-2">
            <div className="flex-1">
              <Segmented
                label="Progress bar"
                value={extras.progress_bar}
                onChange={(v) => set({ progress_bar: v })}
                options={[
                  { id: "none", label: "Off" },
                  { id: "top", label: "Top" },
                  { id: "bottom", label: "Bottom" },
                ]}
              />
            </div>
            {extras.progress_bar !== "none" && (
              <input type="color" aria-label="Progress bar colour" value={extras.progress_color} onChange={(e) => set({ progress_color: e.target.value.toUpperCase() })} className="size-8 cursor-pointer rounded border-0 bg-transparent" />
            )}
          </div>
        </Field>
        <Toggle
          label={`Small “${config?.watermark ?? "klyprima.com"}” credit`}
          hint="Optional. Helps us keep the tool free."
          checked={extras.watermark}
          onChange={(v) => set({ watermark: v })}
        />
      </Card>
    </div>
  );
}

const primary =
  "inline-flex items-center justify-center gap-1.5 rounded-full bg-accent px-4 py-2 text-sm font-semibold text-accent-fg transition hover:brightness-105 disabled:opacity-50";
const secondary =
  "inline-flex shrink-0 items-center justify-center gap-1.5 rounded-full border border-line-strong px-4 py-2 text-sm font-medium transition hover:border-fg disabled:opacity-50";

function Card({
  icon: Icon,
  title,
  body,
  badge,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  body: string;
  badge?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-3 rounded-2xl border border-line p-4">
      <div className="flex items-start gap-3">
        <span className={clsx("grid size-9 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent")}>
          <Icon className="size-4" />
        </span>
        <div className="min-w-0">
          <h3 className="flex items-center gap-2 font-semibold tracking-tight">
            {title} {badge}
          </h3>
          <p className="text-sm text-muted">{body}</p>
        </div>
      </div>
      {children}
    </section>
  );
}
