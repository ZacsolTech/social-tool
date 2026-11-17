"use client";

import clsx from "clsx";
import { Crop, Droplets, PaintBucket, Scissors, SlidersHorizontal, Sparkles } from "lucide-react";
import { useId } from "react";
import type { Aspect, Config, Look, Mode, Settings, SmartOptions } from "@/lib/reframe";
import { ASPECTS, formatClock, parseTime } from "@/lib/reframe";

const MODES: { id: Mode; title: string; body: string; icon: React.ComponentType<{ className?: string }>; badge?: string }[] = [
  { id: "smart", title: "Smart Reframe", body: "AI follows speakers and picks a layout for every shot.", icon: Sparkles, badge: "AI" },
  { id: "blur", title: "Blur Fill", body: "The whole video, with a blurred copy behind it.", icon: Droplets },
  { id: "crop", title: "Crop", body: "Full-screen crop at a position you choose.", icon: Crop },
  { id: "fit", title: "Fit + Colour", body: "The whole video on a solid colour.", icon: PaintBucket },
];

export function SettingsPanel({
  s,
  set,
  config,
  duration,
  disabled,
}: {
  s: Settings;
  set: (patch: Partial<Settings>) => void;
  config: Config | null;
  duration: number | null;
  disabled?: boolean;
}) {
  const smart = (patch: Partial<SmartOptions>) => set({ smart: { ...s.smart, ...patch } });
  const look = (patch: Partial<Look>) => set({ look: { ...s.look, ...patch } });
  const toggleAspect = (a: Aspect) => {
    const has = s.aspects.includes(a);
    if (has && s.aspects.length === 1) return;
    set({ aspects: ASPECTS.map((x) => x.id).filter((x) => (x === a ? !has : s.aspects.includes(x))) });
  };

  return (
    <fieldset disabled={disabled} className="space-y-6 disabled:opacity-60">
      <Section title="Style">
        <div className="grid grid-cols-2 gap-2">
          {MODES.map((m) => (
            <button
              key={m.id}
              type="button"
              aria-pressed={s.mode === m.id}
              onClick={() =>
                // Blur Fill is always blurred and Fit + Colour always uses the colour, whatever was picked before.
                set({ mode: m.id, look: { ...s.look, background: m.id === "blur" ? "blur" : m.id === "fit" ? "color" : s.look.background } })
              }
              className={clsx(
                "relative flex flex-col items-start gap-1 rounded-2xl border p-3 text-left transition",
                s.mode === m.id ? "border-accent bg-accent-soft/60 shadow-card" : "border-line-strong hover:border-fg",
              )}
            >
              <span className="flex w-full items-center gap-2">
                <m.icon className={clsx("size-4", s.mode === m.id ? "text-accent" : "text-muted")} />
                <span className="font-semibold">{m.title}</span>
                {m.badge && <span className="ml-auto rounded-full bg-accent px-1.5 py-px text-[10px] font-bold text-accent-fg">{m.badge}</span>}
              </span>
              <span className="text-xs leading-snug text-muted">{m.body}</span>
            </button>
          ))}
        </div>
      </Section>

      <Section title="Formats" hint="Pick one or more: each is a separate download.">
        <div className="grid grid-cols-3 gap-2">
          {ASPECTS.map((a) => {
            const on = s.aspects.includes(a.id);
            return (
              <button
                key={a.id}
                type="button"
                aria-pressed={on}
                onClick={() => toggleAspect(a.id)}
                className={clsx(
                  "flex flex-col items-center gap-1.5 rounded-2xl border p-2.5 text-center transition",
                  on ? "border-accent bg-accent-soft/60" : "border-line-strong hover:border-fg",
                )}
              >
                <span
                  className={clsx("block rounded-sm border-2", on ? "border-accent" : "border-subtle")}
                  style={{ width: Math.round(22 * Math.min(1, a.ratio)), height: Math.round(22 * Math.min(1, 1 / a.ratio) * (a.ratio === 1 ? 0.9 : 1)) }}
                />
                <span className="text-sm font-semibold">{a.label}</span>
                <span className="text-[11px] leading-tight text-muted">{a.hint}</span>
              </button>
            );
          })}
        </div>
      </Section>

      {s.mode === "smart" && <SmartOptionsSection s={s} smart={smart} look={look} config={config} />}
      {s.mode === "blur" && <BlurOptions look={s.look} set={look} />}
      {s.mode === "crop" && (
        <Section title="Crop position">
          <Range label="Left ↔ Right" min={0} max={1} step={0.01} value={s.position} onChange={(v) => set({ position: v })} display={`${Math.round(s.position * 100)}%`} />
          <Range label="Zoom" min={1} max={1.6} step={0.05} value={s.smart.framing} onChange={(v) => smart({ framing: v })} display={`${Math.round(s.smart.framing * 100)}%`} />
        </Section>
      )}
      {s.mode === "fit" && (
        <Section title="Background colour">
          <ColorPicker value={s.look.color} onChange={(c) => look({ color: c, background: "color" })} />
          <Range label="Video size" min={1} max={1.5} step={0.05} value={s.look.fg_zoom} onChange={(v) => look({ fg_zoom: v })} display={`${Math.round(s.look.fg_zoom * 100)}%`} />
        </Section>
      )}

      <details className="group rounded-2xl border border-line-strong">
        <summary className="flex items-center gap-2 px-4 py-3 text-sm font-medium">
          <Scissors className="size-4 text-muted" /> Trim &amp; quality
          <span className="ml-auto text-xs text-subtle">
            {s.trimStart || s.trimEnd ? `${formatClock(s.trimStart)} – ${s.trimEnd ? formatClock(s.trimEnd) : "end"}` : "Whole video"} · {s.quality}
          </span>
        </summary>
        <div className="space-y-4 border-t border-line px-4 py-4">
          <div className="grid grid-cols-2 gap-3">
            <TimeInput label="Start" value={s.trimStart} onChange={(v) => set({ trimStart: v ?? 0 })} />
            <TimeInput label="End" value={s.trimEnd} placeholder={duration ? formatClock(duration) : "end"} onChange={(v) => set({ trimEnd: v })} />
          </div>
          {config && (
            <p className="text-xs text-muted">Up to {Math.round(config.max_duration_sec / 60)} minutes per conversion.</p>
          )}
          <Segmented
            label="Quality"
            value={s.quality}
            options={[
              { id: "1080p", label: "1080p (best)" },
              { id: "720p", label: "720p (faster)" },
            ]}
            onChange={(v) => set({ quality: v as Settings["quality"] })}
          />
        </div>
      </details>
    </fieldset>
  );
}

function SmartOptionsSection({
  s,
  smart,
  look,
  config,
}: {
  s: Settings;
  smart: (p: Partial<SmartOptions>) => void;
  look: (p: Partial<Look>) => void;
  config: Config | null;
}) {
  const listId = useId();
  const following = s.smart.follow !== null;
  return (
    <>
      <Section title="Who to follow">
        <Segmented
          value={following ? "object" : "auto"}
          options={[
            { id: "auto", label: "People (auto)" },
            { id: "object", label: "An object…" },
          ]}
          onChange={(v) => smart({ follow: v === "object" ? (s.smart.follow ?? "") : null })}
        />
        {following && (
          <div className="mt-2">
            <input
              list={listId}
              value={s.smart.follow ?? ""}
              onChange={(e) => smart({ follow: e.target.value })}
              placeholder="e.g. ball, dog, car, phone"
              maxLength={40}
              className="w-full rounded-xl border border-line-strong bg-bg px-3 py-2 text-sm outline-none focus:border-accent"
            />
            <datalist id={listId}>
              {(config?.objects ?? []).concat(Object.keys(config?.synonyms ?? {})).map((o) => (
                <option key={o} value={o} />
              ))}
            </datalist>
            <p className="mt-1 text-xs text-muted">Or tap anything in the shot editor after converting.</p>
          </div>
        )}
      </Section>

      <Section title="Camera">
        <Segmented
          label="Movement"
          value={s.smart.style}
          options={[
            { id: "steady", label: "Steady" },
            { id: "follow", label: "Follow closely" },
          ]}
          onChange={(v) => smart({ style: v as SmartOptions["style"] })}
        />
        <Segmented
          label="Framing"
          value={String(s.smart.framing)}
          options={[
            { id: "1", label: "Wide" },
            { id: "1.15", label: "Medium" },
            { id: "1.3", label: "Tight" },
          ]}
          onChange={(v) => smart({ framing: Number(v) })}
        />
        <Toggle label="Dynamic zoom" hint="Subtle punch-ins on emphasised moments" checked={s.smart.dynamic_zoom} onChange={(v) => smart({ dynamic_zoom: v })} />
      </Section>

      <details className="group rounded-2xl border border-line-strong">
        <summary className="flex items-center gap-2 px-4 py-3 text-sm font-medium">
          <SlidersHorizontal className="size-4 text-muted" /> Layouts &amp; safe zone
        </summary>
        <div className="space-y-4 border-t border-line px-4 py-4">
          <Segmented
            label="Two people talking"
            value={s.smart.two_person}
            options={[
              { id: "auto", label: "Auto" },
              { id: "switch", label: "Switch" },
              { id: "split", label: "Split screen" },
            ]}
            onChange={(v) => smart({ two_person: v as SmartOptions["two_person"] })}
          />
          <Toggle label="Split screen" hint="Allowed for two people far apart" checked={s.smart.split} onChange={(v) => smart({ split: v })} />
          <Toggle label="Screen + Facecam" hint="Webcam on top, gameplay or screen below" checked={s.smart.facecam} onChange={(v) => smart({ facecam: v })} />
          <Toggle label="Keep on-screen text" hint="Slides and big text are never cut in half" checked={s.smart.text_aware} onChange={(v) => smart({ text_aware: v })} />
          <Segmented
            label="Keep faces clear of the buttons on"
            value={s.smart.safe_zone}
            options={[
              { id: "tiktok", label: "TikTok" },
              { id: "reels", label: "Reels" },
              { id: "shorts", label: "Shorts" },
              { id: "none", label: "None" },
            ]}
            onChange={(v) => smart({ safe_zone: v as SmartOptions["safe_zone"] })}
          />
          <Segmented
            label="Shots kept whole use"
            value={s.look.background}
            options={[
              { id: "blur", label: "Blurred background" },
              { id: "color", label: "Colour" },
            ]}
            onChange={(v) => look({ background: v as Look["background"] })}
          />
          {s.look.background === "color" && <ColorPicker value={s.look.color} onChange={(c) => look({ color: c })} />}
        </div>
      </details>
    </>
  );
}

function BlurOptions({ look, set }: { look: Look; set: (p: Partial<Look>) => void }) {
  return (
    <Section title="Background">
      <Segmented
        label="Blur"
        value={String(look.blur)}
        options={[
          { id: "1", label: "Low" },
          { id: "2", label: "Medium" },
          { id: "3", label: "High" },
        ]}
        onChange={(v) => set({ blur: Number(v) as Look["blur"], background: "blur" })}
      />
      <Range label="Darken" min={0} max={0.6} step={0.05} value={look.dim} onChange={(v) => set({ dim: v })} display={`${Math.round(look.dim * 100)}%`} />
      <Range label="Video size" min={1} max={1.5} step={0.05} value={look.fg_zoom} onChange={(v) => set({ fg_zoom: v })} display={`${Math.round(look.fg_zoom * 100)}%`} />
    </Section>
  );
}

/* ------------------------------------------------------------------ controls */

function Section({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <section className="space-y-3">
      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wider text-subtle">{title}</h3>
        {hint && <p className="mt-0.5 text-xs text-muted">{hint}</p>}
      </div>
      {children}
    </section>
  );
}

export function Segmented({
  label,
  value,
  options,
  onChange,
}: {
  label?: string;
  value: string;
  options: { id: string; label: string }[];
  onChange: (v: string) => void;
}) {
  return (
    <div>
      {label && <p className="mb-1.5 text-sm text-muted">{label}</p>}
      <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-1 rounded-xl bg-line/60 p-1">
        {options.map((o) => (
          <button
            key={o.id}
            type="button"
            role="radio"
            aria-checked={value === o.id}
            onClick={() => onChange(o.id)}
            className={clsx(
              "min-w-0 flex-1 rounded-lg px-2.5 py-1.5 text-sm font-medium transition",
              value === o.id ? "bg-elev text-fg shadow-card" : "text-muted hover:text-fg",
            )}
          >
            {o.label}
          </button>
        ))}
      </div>
    </div>
  );
}

function Toggle({ label, hint, checked, onChange }: { label: string; hint?: string; checked: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex cursor-pointer items-center justify-between gap-4">
      <span>
        <span className="block text-sm font-medium">{label}</span>
        {hint && <span className="block text-xs text-muted">{hint}</span>}
      </span>
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} className="peer sr-only" />
      <span className="relative h-6 w-10 shrink-0 rounded-full bg-line-strong transition peer-checked:bg-accent peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-accent after:absolute after:left-0.5 after:top-0.5 after:size-5 after:rounded-full after:bg-white after:shadow after:transition peer-checked:after:translate-x-4" />
    </label>
  );
}

function Range({
  label,
  min,
  max,
  step,
  value,
  onChange,
  display,
}: {
  label: string;
  min: number;
  max: number;
  step: number;
  value: number;
  onChange: (v: number) => void;
  display: string;
}) {
  return (
    <label className="block">
      <span className="mb-1 flex justify-between text-sm text-muted">
        {label} <span className="font-mono text-xs">{display}</span>
      </span>
      <input type="range" min={min} max={max} step={step} value={value} onChange={(e) => onChange(Number(e.target.value))} className="w-full accent-accent" />
    </label>
  );
}

const SWATCHES = ["#000000", "#ffffff", "#ff4f1f", "#1d4ed8", "#16a34a", "#f5d0fe", "#facc15"];

function ColorPicker({ value, onChange }: { value: string; onChange: (c: string) => void }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {SWATCHES.map((c) => (
        <button
          key={c}
          type="button"
          aria-label={`Colour ${c}`}
          aria-pressed={value.toLowerCase() === c}
          onClick={() => onChange(c)}
          className={clsx("size-8 rounded-full border-2 transition", value.toLowerCase() === c ? "border-accent scale-110" : "border-line-strong")}
          style={{ background: c }}
        />
      ))}
      <input type="color" value={value} onChange={(e) => onChange(e.target.value)} aria-label="Custom colour" className="h-8 w-10 cursor-pointer rounded border border-line-strong bg-transparent" />
    </div>
  );
}

function TimeInput({ label, value, placeholder, onChange }: { label: string; value: number | null; placeholder?: string; onChange: (v: number | null) => void }) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm text-muted">{label}</span>
      <input
        key={value ?? "none"}
        defaultValue={value ? formatClock(value) : ""}
        placeholder={placeholder ?? "0:00"}
        inputMode="numeric"
        onBlur={(e) => {
          const v = parseTime(e.target.value);
          onChange(v);
        }}
        className="w-full rounded-xl border border-line-strong bg-bg px-3 py-2 font-mono text-sm outline-none focus:border-accent"
      />
    </label>
  );
}
