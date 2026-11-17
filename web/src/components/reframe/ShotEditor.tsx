"use client";

import clsx from "clsx";
import { Crosshair, LoaderCircle, MousePointerClick, RotateCcw, Wand2 } from "lucide-react";
import { useMemo, useRef, useState } from "react";
import type { Job, Layout, Override, ShotDesc } from "@/lib/reframe";
import { formatClock } from "@/lib/reframe";

const LAYOUT_LABEL: Record<Layout, string> = {
  follow: "Follow",
  split: "Split screen",
  facecam: "Screen + Facecam",
  fit: "Keep whole",
};

type Overrides = Record<number, Override>;

function fromJob(job: Job): Overrides {
  const out: Overrides = {};
  for (const [k, v] of Object.entries(job.overrides ?? {})) out[Number(k)] = v;
  return out;
}

const clean = (o: Overrides): Overrides =>
  Object.fromEntries(Object.entries(o).filter(([, v]) => v && Object.values(v).some((x) => x !== undefined && x !== "auto"))) as Overrides;

export function ShotEditor({ job, onApply, busy }: { job: Job; onApply: (o: Overrides) => void; busy: boolean }) {
  const shots = useMemo(() => job.shots[job.aspects[0]] ?? Object.values(job.shots)[0] ?? [], [job]);
  const [ov, setOv] = useState<Overrides>(() => fromJob(job));
  const [picking, setPicking] = useState<number | null>(null);
  const ratio = job.info ? job.info.width / job.info.height : 16 / 9;
  const dirty = JSON.stringify(clean(ov)) !== JSON.stringify(clean(fromJob(job)));
  const changed = Object.keys(clean(ov)).filter((k) => JSON.stringify(clean(ov)[Number(k)]) !== JSON.stringify(clean(fromJob(job))[Number(k)])).length
    + Object.keys(clean(fromJob(job))).filter((k) => !(Number(k) in clean(ov))).length;

  if (!shots.length) return null;

  const update = (i: number, patch: Override | null) =>
    setOv((cur) => {
      const next = { ...cur };
      if (patch === null) delete next[i];
      else next[i] = { ...patch };
      return next;
    });

  return (
    <section className="rounded-3xl border border-line bg-elev p-4 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h3 className="flex items-center gap-2 text-lg font-semibold tracking-tight">
            <Wand2 className="size-5 text-accent" /> Shot editor
          </h3>
          <p className="mt-0.5 text-sm text-muted">
            {shots.length} shot{shots.length === 1 ? "" : "s"}. Drag a crop, tap a face to follow it, or change a shot&apos;s layout. Applying re-renders in seconds.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {dirty && (
            <button type="button" onClick={() => setOv(fromJob(job))} className="rounded-full px-3 py-2 text-sm text-muted transition hover:text-fg">
              Discard
            </button>
          )}
          <button
            type="button"
            disabled={!dirty || busy}
            onClick={() => onApply(clean(ov))}
            className="inline-flex items-center gap-1.5 rounded-full bg-accent px-4 py-2 text-sm font-semibold text-accent-fg shadow-[0_6px_20px_-8px_var(--accent)] transition hover:brightness-105 disabled:opacity-50"
          >
            {busy && <LoaderCircle className="size-4 animate-spin" />}
            {dirty ? `Apply (${changed} shot${changed === 1 ? "" : "s"})` : "Apply changes"}
          </button>
        </div>
      </div>

      <div className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {shots.map((shot) => (
          <ShotCard
            key={shot.index}
            shot={shot}
            ratio={ratio}
            o={ov[shot.index]}
            picking={picking === shot.index}
            onPick={() => setPicking(picking === shot.index ? null : shot.index)}
            onChange={(p) => {
              update(shot.index, p);
              setPicking(null);
            }}
          />
        ))}
      </div>
    </section>
  );
}

function ShotCard({
  shot,
  ratio,
  o,
  picking,
  onPick,
  onChange,
}: {
  shot: ShotDesc;
  ratio: number;
  o: Override | undefined;
  picking: boolean;
  onPick: () => void;
  onChange: (o: Override | null) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const drag = useRef<{ x: number; center: number } | null>(null);
  const [dragCenter, setDragCenter] = useState<number | null>(null);
  const layout: Layout = o?.layout && o.layout !== "auto" ? o.layout : shot.layout;
  const single = shot.crops.length === 1 && layout === "follow" && shot.layout === "follow";
  const center = dragCenter ?? o?.center ?? null;

  const crops = shot.crops.map((c) => {
    if (!single || center === null) return c.box;
    const [, y, w, h] = c.box;
    const x = Math.min(Math.max(center - w / 2, 0), 1 - w);
    return [x, y, w, h] as [number, number, number, number];
  });

  const pos = (e: React.PointerEvent | React.MouseEvent) => {
    const r = ref.current!.getBoundingClientRect();
    return [Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), Math.min(1, Math.max(0, (e.clientY - r.top) / r.height))] as const;
  };

  return (
    <article className={clsx("overflow-hidden rounded-2xl border bg-bg", o ? "border-accent/60" : "border-line")}>
      <div
        ref={ref}
        className={clsx("relative w-full select-none overflow-hidden bg-neutral-900", picking && "cursor-crosshair")}
        style={{ aspectRatio: String(ratio) }}
        onClick={(e) => {
          if (!picking) return;
          const [x, y] = pos(e);
          onChange({ point: [Number(x.toFixed(4)), Number(y.toFixed(4))] });
        }}
      >
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img src={shot.thumb} alt={`Shot ${shot.index + 1}`} className="absolute inset-0 size-full object-cover" draggable={false} loading="lazy" />
        {layout !== "fit" &&
          !o?.point &&
          crops.map((b, i) => (
            <div
              key={i}
              className={clsx(
                "absolute rounded-sm border-2 border-accent",
                single && !picking && "cursor-ew-resize touch-none",
                crops.length === 1 && "shadow-[0_0_0_9999px_rgba(0,0,0,0.45)]",
              )}
              style={{ left: `${b[0] * 100}%`, top: `${b[1] * 100}%`, width: `${b[2] * 100}%`, height: `${b[3] * 100}%` }}
              onPointerDown={(e) => {
                if (!single || picking) return;
                e.currentTarget.setPointerCapture(e.pointerId);
                drag.current = { x: e.clientX, center: b[0] + b[2] / 2 };
              }}
              onPointerMove={(e) => {
                if (!drag.current || !ref.current) return;
                const dx = (e.clientX - drag.current.x) / ref.current.getBoundingClientRect().width;
                setDragCenter(Math.min(1, Math.max(0, drag.current.center + dx)));
              }}
              onPointerUp={() => {
                if (drag.current && dragCenter !== null) onChange({ layout: "follow", center: Number(dragCenter.toFixed(4)) });
                drag.current = null;
                setDragCenter(null);
              }}
            />
          ))}
        {layout === "fit" && (
          <span className="absolute inset-x-0 bottom-0 bg-black/60 px-2 py-1 text-center text-[11px] text-white">Whole frame kept (blurred background)</span>
        )}
        {shot.faces.map((f) => {
          const chosen = o?.track === f.track || (!o?.track && shot.subjects.includes(f.track) && shot.faces.length > 1);
          return (
            <button
              key={f.track}
              type="button"
              title={`Follow person ${f.label}`}
              onClick={(e) => {
                e.stopPropagation();
                onChange({ layout: "follow", track: f.track });
              }}
              className={clsx(
                "absolute grid place-items-start rounded-md border-2 transition",
                chosen ? "border-ok" : "border-white/80 hover:border-ok",
              )}
              style={{ left: `${f.box[0] * 100}%`, top: `${f.box[1] * 100}%`, width: `${f.box[2] * 100}%`, height: `${f.box[3] * 100}%` }}
            >
              <span className={clsx("-translate-y-full rounded-t px-1 text-[10px] font-bold", chosen ? "bg-ok text-white" : "bg-white text-black")}>{f.label}</span>
            </button>
          );
        })}
        {picking &&
          shot.objects.map((b) => (
            <button
              key={b.track}
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                onChange({ layout: "follow", track: b.track });
              }}
              className="absolute rounded border border-dashed border-yellow-300 text-left"
              style={{ left: `${b.box[0] * 100}%`, top: `${b.box[1] * 100}%`, width: `${b.box[2] * 100}%`, height: `${b.box[3] * 100}%` }}
            >
              <span className="bg-yellow-300 px-1 text-[10px] font-semibold text-black">{b.label}</span>
            </button>
          ))}
        {o?.point && (
          <span
            className="absolute size-6 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-accent bg-accent/30"
            style={{ left: `${o.point[0] * 100}%`, top: `${o.point[1] * 100}%` }}
          />
        )}
        <span className="absolute left-2 top-2 rounded bg-black/65 px-1.5 py-0.5 font-mono text-[10px] text-white">
          {formatClock(shot.start)}–{formatClock(shot.end)}
        </span>
        {picking && (
          <span className="absolute inset-x-0 top-0 bg-accent px-2 py-1 text-center text-[11px] font-medium text-accent-fg">Tap what to follow</span>
        )}
      </div>

      <div className="space-y-2 p-3">
        <p className="text-xs text-muted">
          <span className="font-medium text-fg">AI:</span> {shot.reason}
        </p>
        <div className="flex items-center gap-2">
          <select
            aria-label={`Layout for shot ${shot.index + 1}`}
            value={o?.layout ?? "auto"}
            onChange={(e) => {
              const v = e.target.value as Override["layout"];
              onChange(v === "auto" && !o?.center && o?.track === undefined && !o?.point ? null : { ...o, layout: v });
            }}
            className="min-w-0 flex-1 rounded-lg border border-line-strong bg-elev px-2 py-1.5 text-sm"
          >
            <option value="auto">Auto ({LAYOUT_LABEL[shot.layout]})</option>
            <option value="follow">Follow</option>
            <option value="split">Split screen</option>
            <option value="facecam">Screen + Facecam</option>
            <option value="fit">Keep whole</option>
          </select>
          <button
            type="button"
            onClick={onPick}
            title="Tap something in the picture to follow it"
            aria-pressed={picking}
            className={clsx("grid size-9 place-items-center rounded-lg border transition", picking ? "border-accent bg-accent text-accent-fg" : "border-line-strong hover:border-fg")}
          >
            {picking ? <Crosshair className="size-4" /> : <MousePointerClick className="size-4" />}
          </button>
          {o && (
            <button type="button" title="Back to the AI's choice" onClick={() => onChange(null)} className="grid size-9 place-items-center rounded-lg border border-line-strong transition hover:border-fg">
              <RotateCcw className="size-4" />
            </button>
          )}
        </div>
      </div>
    </article>
  );
}
