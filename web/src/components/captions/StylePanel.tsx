"use client";

import clsx from "clsx";
import { BookmarkPlus, Check, X } from "lucide-react";
import { useEffect, useState } from "react";
import { CAPTIONS_BRAND_KEY, type CConfig, cssFamily, readLocal, writeLocal } from "@/lib/captions";
import type { Animation, CStyle } from "@/lib/captionsCore";
import { ColorInput, Field, Segmented, Slider, Toggle } from "./ui";

const ANIMATIONS: { id: Animation; label: string; hint: string }[] = [
  { id: "pop", label: "Pop", hint: "Spoken word pops" },
  { id: "highlight", label: "Highlight", hint: "Spoken word changes colour" },
  { id: "karaoke", label: "Karaoke", hint: "Colour fills as words are said" },
  { id: "word", label: "One word", hint: "One big word at a time" },
  { id: "reveal", label: "Reveal", hint: "Words appear as they're said" },
  { id: "bounce", label: "Bounce", hint: "Each caption bounces in" },
  { id: "slide", label: "Slide up", hint: "Each caption slides in" },
  { id: "fade", label: "Fade", hint: "Soft fade in and out" },
  { id: "none", label: "None", hint: "Plain subtitles" },
];

type Saved = { name: string; style: CStyle };

export function StylePanel({ style, setStyle, config }: { style: CStyle; setStyle: (s: CStyle) => void; config: CConfig | null }) {
  const set = (patch: Partial<CStyle>) => setStyle({ ...style, ...patch, preset: patch.preset ?? "custom" });
  const display = config?.fonts.filter((f) => f.kind === "display") ?? [];
  const [saved, setSaved] = useState<Saved[]>([]);
  const [naming, setNaming] = useState<string | null>(null);
  useEffect(() => setSaved(readLocal<Saved[]>(CAPTIONS_BRAND_KEY) ?? []), []);

  function save() {
    const name = (naming ?? "").trim() || `My style ${saved.length + 1}`;
    const next = [{ name, style: { ...style, preset: "custom" } }, ...saved.filter((s) => s.name !== name)].slice(0, 12);
    setSaved(next);
    writeLocal(CAPTIONS_BRAND_KEY, next);
    setNaming(null);
  }

  return (
    <div className="space-y-6">
      <Field label="Presets" hint="Tap one, then fine-tune">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {config?.presets.map((p) => (
            <button
              key={p.id}
              type="button"
              onClick={() => setStyle({ ...p.style, y: style.y })}
              aria-pressed={style.preset === p.id}
              className={clsx(
                "relative grid h-[72px] place-items-center overflow-hidden rounded-xl border-2 bg-neutral-900 px-2 transition",
                style.preset === p.id ? "border-accent" : "border-transparent hover:border-line-strong",
              )}
            >
              <PresetSample style={p.style} label={p.label} />
              <span className="absolute bottom-1 left-2 text-[10px] font-medium text-white/60">{p.label}</span>
            </button>
          ))}
        </div>
      </Field>

      {saved.length > 0 && (
        <Field label="My styles" hint="Saved in this browser">
          <div className="flex flex-wrap gap-2">
            {saved.map((s) => (
              <span key={s.name} className="inline-flex items-center overflow-hidden rounded-full border border-line-strong text-sm">
                <button type="button" onClick={() => setStyle(s.style)} className="px-3 py-1.5 hover:bg-line">
                  {s.name}
                </button>
                <button
                  type="button"
                  aria-label={`Delete ${s.name}`}
                  onClick={() => {
                    const next = saved.filter((x) => x.name !== s.name);
                    setSaved(next);
                    writeLocal(CAPTIONS_BRAND_KEY, next);
                  }}
                  className="border-l border-line px-2 py-1.5 text-muted hover:bg-line hover:text-fg"
                >
                  <X className="size-3.5" />
                </button>
              </span>
            ))}
          </div>
        </Field>
      )}

      <div className="grid gap-5 sm:grid-cols-2">
        <Field label="Font">
          <select
            value={style.font}
            onChange={(e) => set({ font: e.target.value })}
            aria-label="Font"
            className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm"
            style={{ fontFamily: `"${cssFamily(style.font)}", sans-serif` }}
          >
            {display.map((f) => (
              <option key={f.key} value={f.key}>
                {f.label}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Animation">
          <select value={style.animation} onChange={(e) => set({ animation: e.target.value as Animation })} aria-label="Animation" className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm">
            {ANIMATIONS.map((a) => (
              <option key={a.id} value={a.id}>
                {a.label} · {a.hint}
              </option>
            ))}
          </select>
        </Field>
        <Slider label="Size" value={style.size} min={14} max={120} onChange={(v) => set({ size: v })} />
        <Slider label="Words per caption" value={style.max_words} min={1} max={12} onChange={(v) => set({ max_words: v, max_chars: Math.max(14, Math.min(60, v * 8)) })} />
        <Field label="Position">
          <div className="space-y-2">
            <Segmented
              label="Position"
              value={style.y < 0.34 ? "top" : style.y < 0.62 ? "middle" : "bottom"}
              onChange={(v) => set({ y: v === "top" ? 0.2 : v === "middle" ? 0.5 : 0.75 })}
              options={[
                { id: "top", label: "Top" },
                { id: "middle", label: "Middle" },
                { id: "bottom", label: "Bottom" },
              ]}
            />
            <input type="range" aria-label="Vertical position" min={0.05} max={0.95} step={0.01} value={style.y} onChange={(e) => set({ y: Number(e.target.value) })} className="w-full accent-[var(--accent)]" />
          </div>
        </Field>
        <Field label="Spoken word">
          <div className="space-y-2">
            <Segmented
              label="Spoken word"
              value={style.highlight_mode}
              onChange={(v) => set({ highlight_mode: v })}
              options={[
                { id: "color", label: "Colour" },
                { id: "box", label: "Box" },
                { id: "scale", label: "Bigger" },
              ]}
            />
            <ColorInput label="Highlight colour" value={style.highlight} onChange={(v) => set({ highlight: v })} />
          </div>
        </Field>
      </div>

      <div className="grid gap-2 sm:grid-cols-2">
        <ColorInput label="Text colour" value={style.color} onChange={(v) => set({ color: v })} />
        <ColorInput label="Keyword colour" value={style.keyword_color} onChange={(v) => set({ keyword_color: v })} />
        <ColorInput label="Outline colour" value={style.outline_color} onChange={(v) => set({ outline_color: v })} />
        <ColorInput label="Translation colour" value={style.translation_color} onChange={(v) => set({ translation_color: v })} />
      </div>

      <div className="grid gap-5 sm:grid-cols-3">
        <Slider label="Outline" value={style.outline} min={0} max={16} step={0.5} onChange={(v) => set({ outline: v })} />
        <Slider label="Shadow" value={style.shadow} min={0} max={12} step={0.5} onChange={(v) => set({ shadow: v })} />
        <Slider label="Letter spacing" value={style.spacing} min={0} max={12} step={0.5} onChange={(v) => set({ spacing: v })} />
      </div>

      <div className="grid gap-x-6 sm:grid-cols-2">
        <Toggle label="UPPERCASE" checked={style.uppercase} onChange={(v) => set({ uppercase: v })} />
        <Toggle label="Emojis" hint="One per line, from the highlights" checked={style.emoji} onChange={(v) => set({ emoji: v })} />
        <Toggle label="Keyword colours" hint="Important words stand out" checked={style.keywords} onChange={(v) => set({ keywords: v })} />
        <Toggle label="Background box" checked={style.box} onChange={(v) => set({ box: v })} />
      </div>
      {style.box && (
        <div className="grid gap-3 sm:grid-cols-2">
          <ColorInput label="Box colour" value={style.box_color} onChange={(v) => set({ box_color: v })} />
          <Slider label="Box opacity" value={style.box_opacity} min={0.2} max={1} step={0.05} onChange={(v) => set({ box_opacity: v })} format={(v) => `${Math.round(v * 100)}%`} />
        </div>
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4">
        {naming === null ? (
          <button type="button" onClick={() => setNaming("")} className="inline-flex items-center gap-1.5 rounded-full border border-line-strong px-3.5 py-1.5 text-sm font-medium transition hover:border-fg">
            <BookmarkPlus className="size-4" /> Save as my style
          </button>
        ) : (
          <form
            onSubmit={(e) => {
              e.preventDefault();
              save();
            }}
            className="flex items-center gap-2"
          >
            <input autoFocus value={naming} onChange={(e) => setNaming(e.target.value)} placeholder="Style name (e.g. My brand)" maxLength={30} className="rounded-full border border-line-strong bg-bg px-3 py-1.5 text-sm outline-none focus:border-accent" />
            <button type="submit" aria-label="Save style" className="grid size-8 place-items-center rounded-full bg-accent text-accent-fg">
              <Check className="size-4" />
            </button>
          </form>
        )}
        <span className="text-xs text-subtle">Your brand look, one tap away next time.</span>
      </div>
    </div>
  );
}

function PresetSample({ style, label }: { style: CStyle; label: string }) {
  const word = style.uppercase ? "CAPTIONS" : "Captions";
  return (
    <span
      className="whitespace-nowrap text-center leading-none"
      style={{
        fontFamily: `"${cssFamily(style.font)}", sans-serif`,
        fontSize: style.animation === "word" ? 22 : 18,
        color: style.color,
        WebkitTextStroke: style.box ? undefined : `${Math.min(3, style.outline / 2.5)}px ${style.outline_color}`,
        paintOrder: "stroke fill",
        background: style.box ? style.box_color : undefined,
        padding: style.box ? "3px 6px" : undefined,
        borderRadius: 4,
        letterSpacing: style.spacing / 2,
      }}
      aria-label={label}
    >
      {word.slice(0, 4)}
      <span style={{ color: style.highlight, ...(style.highlight_mode === "box" ? { background: style.highlight, color: style.color, borderRadius: 4, padding: "0 3px" } : {}) }}>
        {word.slice(4)}
      </span>
    </span>
  );
}
