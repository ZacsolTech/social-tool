"use client";

import clsx from "clsx";
import type { ReactNode } from "react";

export function Field({ label, hint, children, className }: { label: string; hint?: ReactNode; children: ReactNode; className?: string }) {
  return (
    <div className={clsx("space-y-1.5", className)}>
      <div className="flex items-baseline justify-between gap-2">
        <span className="text-xs font-semibold uppercase tracking-wider text-muted">{label}</span>
        {hint && <span className="text-xs text-subtle">{hint}</span>}
      </div>
      {children}
    </div>
  );
}

export function Toggle({ checked, onChange, label, hint, disabled }: { checked: boolean; onChange: (v: boolean) => void; label: string; hint?: string; disabled?: boolean }) {
  return (
    <label className={clsx("flex cursor-pointer items-start justify-between gap-3 rounded-xl px-1 py-1.5", disabled && "cursor-not-allowed opacity-50")}>
      <span className="min-w-0">
        <span className="block text-sm font-medium">{label}</span>
        {hint && <span className="block text-xs text-muted">{hint}</span>}
      </span>
      <input type="checkbox" className="peer sr-only" checked={checked} disabled={disabled} onChange={(e) => onChange(e.target.checked)} />
      <span
        aria-hidden
        className={clsx(
          "relative mt-0.5 h-6 w-10 shrink-0 rounded-full transition peer-focus-visible:ring-2 peer-focus-visible:ring-accent",
          checked ? "bg-accent" : "bg-line-strong",
        )}
      >
        <span className={clsx("absolute top-0.5 size-5 rounded-full bg-white shadow transition-all", checked ? "left-[18px]" : "left-0.5")} />
      </span>
    </label>
  );
}

export function Slider({
  value,
  onChange,
  min,
  max,
  step = 1,
  label,
  format,
}: {
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step?: number;
  label: string;
  format?: (v: number) => string;
}) {
  return (
    <Field label={label} hint={format ? format(value) : String(value)}>
      <input
        type="range"
        aria-label={label}
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-[var(--accent)]"
      />
    </Field>
  );
}

export function ColorInput({ value, onChange, label }: { value: string; onChange: (v: string) => void; label: string }) {
  return (
    <label className="flex items-center gap-2 rounded-xl border border-line bg-bg px-2 py-1.5 text-sm">
      <input type="color" aria-label={label} value={value} onChange={(e) => onChange(e.target.value.toUpperCase())} className="size-6 cursor-pointer rounded border-0 bg-transparent p-0" />
      <span className="min-w-0 flex-1 truncate">{label}</span>
    </label>
  );
}

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { id: T; label: ReactNode; title?: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="radiogroup" aria-label={label} className="flex gap-1 rounded-xl bg-line/60 p-1">
      {options.map((o) => (
        <button
          key={o.id}
          type="button"
          role="radio"
          aria-checked={value === o.id}
          title={o.title}
          onClick={() => onChange(o.id)}
          className={clsx(
            "flex flex-1 items-center justify-center gap-1 rounded-lg px-2 py-1.5 text-xs font-medium transition",
            value === o.id ? "bg-elev text-fg shadow-card" : "text-muted hover:text-fg",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Badge({ children, tone = "accent" }: { children: ReactNode; tone?: "accent" | "ok" | "muted" }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
        tone === "accent" && "bg-accent-soft text-accent",
        tone === "ok" && "bg-ok/15 text-ok",
        tone === "muted" && "bg-line text-muted",
      )}
    >
      {children}
    </span>
  );
}
