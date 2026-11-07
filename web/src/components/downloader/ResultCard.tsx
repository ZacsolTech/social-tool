"use client";

import clsx from "clsx";
import {
  ArrowDownToLine,
  AudioLines,
  Check,
  CircleAlert,
  Crop,
  Download,
  ImageIcon,
  Layers,
  LoaderCircle,
  Music,
  RotateCcw,
  Sparkles,
  Subtitles,
  Video,
  VolumeX,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { formatBytes, formatDuration, type Item, type Option, type Resolved } from "@/lib/api";
import { byId } from "@/lib/platforms";
import { PlatformBadge } from "../PlatformBadge";
import { dlKey, type DownloadStatus, useDownloads } from "./useDownloads";

export function ResultCard({ data, onReset }: { data: Resolved; onReset: () => void }) {
  const { status, start } = useDownloads(data.token);
  const [active, setActive] = useState(0);
  const [bulk, setBulk] = useState<"idle" | "running" | "done">("idle");
  const platform = byId(data.platform.id);
  const item = data.items[active] ?? data.items[0];
  const multi = data.items.length > 1;
  const anyStarted = Object.values(status).some((s) => s.state !== "error");
  const waitLeft = useReadyCountdown(data);

  async function downloadAll() {
    setBulk("running");
    for (const it of data.items) {
      const best = it.options.find((o) => o.best) ?? it.options[0];
      if (!best || it.error) continue;
      setActive(it.index);
      start(it, best);
      // Small gap so the browser doesn't treat it as a burst of pop-up downloads.
      await new Promise((r) => setTimeout(r, 1200));
    }
    setBulk("done");
  }

  return (
    <div className="animate-in rounded-3xl border border-line bg-elev p-3 shadow-card sm:p-4">
      {/* Mobile: small thumb beside the title, options full-width below. Desktop: thumb column on the left. */}
      <div className="grid grid-cols-[96px_minmax(0,1fr)] gap-x-4 gap-y-1 sm:grid-cols-[200px_minmax(0,1fr)] sm:gap-x-6">
        <div className="sm:row-span-2">
          <Thumb item={item} />
        </div>

        <div className="min-w-0 self-center py-1 sm:self-start">
          <div className="flex items-center gap-2 text-sm text-muted">
            {platform && <PlatformBadge platform={platform} size={20} />}
            <span className="font-medium text-fg">{data.platform.name}</span>
            {data.uploader && (
              <>
                <span aria-hidden>·</span>
                <span className="truncate">{data.uploader}</span>
              </>
            )}
          </div>
          <h2 className="mt-1.5 line-clamp-3 text-base font-semibold leading-snug tracking-tight sm:mt-2 sm:line-clamp-2 sm:text-xl">
            {item.title || data.title}
          </h2>
          {item.duration ? <p className="mt-1 font-mono text-xs text-subtle sm:hidden">{formatDuration(item.duration)}</p> : null}
        </div>

        <div className="col-span-2 min-w-0 sm:col-span-1 sm:col-start-2">
          {multi && (
            <div className="mt-4">
              <div className="mb-2 flex items-center justify-between gap-3">
                <p className="flex items-center gap-1.5 text-sm text-muted">
                  <Layers className="size-4" /> {data.items.length} items in this post
                </p>
                <button
                  type="button"
                  onClick={downloadAll}
                  disabled={bulk === "running"}
                  className="inline-flex items-center gap-1.5 rounded-full border border-line-strong px-3 py-1.5 text-sm font-medium transition hover:border-fg disabled:opacity-60"
                >
                  {bulk === "running" ? <LoaderCircle className="size-4 animate-spin" /> : bulk === "done" ? <Check className="size-4 text-ok" /> : <Download className="size-4" />}
                  {bulk === "done" ? "All started" : "Download all"}
                </button>
              </div>
              <div className="flex gap-2 overflow-x-auto pb-1 [scrollbar-width:thin]">
                {data.items.map((it) => (
                  <button
                    key={it.index}
                    type="button"
                    onClick={() => setActive(it.index)}
                    aria-label={`Item ${it.index + 1}`}
                    aria-pressed={it.index === active}
                    className={clsx(
                      "relative h-16 w-12 shrink-0 overflow-hidden rounded-lg border-2 bg-line transition",
                      it.index === active ? "border-accent" : "border-transparent opacity-70 hover:opacity-100",
                    )}
                  >
                    {it.thumbnail && (
                      // eslint-disable-next-line @next/next/no-img-element
                      <img src={it.thumbnail} alt="" className="size-full object-cover" loading="lazy" />
                    )}
                    <span className="absolute bottom-0.5 left-0.5 rounded bg-black/70 px-1 text-[10px] font-medium text-white">
                      {it.index + 1}
                    </span>
                  </button>
                ))}
              </div>
            </div>
          )}

          {item.error ? (
            <p className="mt-4 flex items-start gap-2 rounded-xl bg-danger/10 p-3 text-sm text-danger">
              <CircleAlert className="mt-0.5 size-4 shrink-0" /> {item.error}
            </p>
          ) : (
            <OptionGroups item={item} status={status} waitLeft={waitLeft[item.index] ?? 0} onStart={(o) => start(item, o)} />
          )}
        </div>
      </div>

      {anyStarted && <AfterDownload onReset={onReset} />}
    </div>
  );
}

function Thumb({ item }: { item: Item }) {
  const ratio = item.width && item.height ? item.width / item.height : 9 / 16;
  return (
    <div
      className="relative w-full overflow-hidden rounded-xl bg-line sm:rounded-2xl"
      style={{ aspectRatio: String(Math.min(Math.max(ratio, 9 / 16), 16 / 9)) }}
    >
      {item.thumbnail ? (
        // Thumbnails come through our API proxy (platforms block hot-linking), so plain <img> is right here.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={item.thumbnail} alt="" className="size-full object-cover" />
      ) : (
        <div className="grid size-full place-items-center text-subtle">
          <Video className="size-8" />
        </div>
      )}
      {item.duration ? (
        <span className="absolute bottom-2 right-2 hidden rounded-md bg-black/75 px-1.5 py-0.5 font-mono text-xs text-white sm:block">
          {formatDuration(item.duration)}
        </span>
      ) : null}
    </div>
  );
}

function OptionGroups({
  item,
  status,
  waitLeft,
  onStart,
}: {
  item: Item;
  status: Record<string, DownloadStatus>;
  waitLeft: number;
  onStart: (o: Option) => void;
}) {
  const groups = useMemo(
    () => ({
      video: item.options.filter((o) => o.kind === "video"),
      audio: item.options.filter((o) => o.kind === "audio"),
      image: item.options.filter((o) => o.kind === "image"),
    }),
    [item.options],
  );
  const btn = (o: Option) => (
    <OptionButton key={o.id} o={o} s={status[dlKey(item.index, o.id)]} waitLeft={o.kind === "image" ? 0 : waitLeft} onStart={onStart} />
  );

  return (
    <div className="mt-5 space-y-4">
      {groups.video.length > 0 && (
        <Group icon={<Video className="size-4" />} label="Video · MP4">
          {groups.video.map(btn)}
        </Group>
      )}
      {(groups.audio.length > 0 || groups.image.length > 0) && (
        <div className="grid gap-4 sm:grid-cols-2">
          {groups.audio.length > 0 && (
            <Group icon={<AudioLines className="size-4" />} label="Audio">
              {groups.audio.map(btn)}
            </Group>
          )}
          {groups.image.length > 0 && (
            <Group icon={<ImageIcon className="size-4" />} label="Image">
              {groups.image.map(btn)}
            </Group>
          )}
        </div>
      )}
    </div>
  );
}

function Group({ icon, label, children }: { icon: React.ReactNode; label: string; children: React.ReactNode }) {
  return (
    <section>
      <h3 className="mb-2 flex items-center gap-1.5 text-xs font-medium uppercase tracking-wider text-subtle">
        {icon}
        {label}
      </h3>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-[repeat(auto-fill,minmax(150px,1fr))]">{children}</div>
    </section>
  );
}

function OptionButton({
  o,
  s,
  waitLeft,
  onStart,
}: {
  o: Option;
  s?: DownloadStatus;
  waitLeft: number;
  onStart: (o: Option) => void;
}) {
  const waiting = waitLeft > 0 && !s;
  const starting = s?.state === "starting";
  const started = s?.state === "started";
  const failed = s?.state === "error";
  const highlight = o.best && !s;

  let sub: string = [formatBytes(o.size) && `~${formatBytes(o.size)}`, o.note].filter(Boolean).join(" · ") || o.ext.toUpperCase();
  if (waiting) sub = `Ready in ${waitLeft}s…`;
  else if (starting) sub = o.instant ? "Starting download…" : "Converting, starts in a moment…";
  else if (started) sub = "Started · tap to download again";
  else if (failed) sub = s?.error ?? "Failed · tap to retry";

  const Icon = waiting ? LoaderCircle : started ? Check : failed ? RotateCcw : starting ? LoaderCircle : o.kind === "audio" ? Music : o.kind === "image" ? ImageIcon : !o.has_audio ? VolumeX : ArrowDownToLine;

  return (
    <button
      type="button"
      disabled={starting || waiting}
      title={failed ? s?.error : `Download ${o.label} ${o.ext.toUpperCase()}`}
      onClick={() => onStart(o)}
      className={clsx(
        "group relative flex min-h-14 items-center justify-between gap-2 overflow-hidden rounded-xl border px-3 py-2 text-left transition duration-150",
        "active:scale-[0.98] focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent",
        highlight
          ? "border-accent bg-accent text-accent-fg shadow-[0_6px_20px_-6px_var(--accent)] hover:-translate-y-px hover:brightness-105"
          : "border-line-strong bg-bg hover:-translate-y-px hover:border-fg hover:shadow-card",
        started && "border-ok/50",
        failed && "border-danger/50",
        (starting || waiting) && "cursor-progress",
      )}
    >
      {starting && <span aria-hidden className="shimmer absolute inset-0 opacity-40" />}
      <span className="relative min-w-0">
        <span className="flex items-center gap-1.5 font-semibold">
          {o.label}
          {highlight && <span className="rounded-full bg-white/20 px-1.5 py-px text-[10px] font-medium uppercase tracking-wide">Best</span>}
        </span>
        <span
          className={clsx(
            "block text-xs",
            failed ? "line-clamp-2 text-danger" : "truncate",
            highlight ? "text-accent-fg/80" : started ? "text-ok" : !failed && "text-muted",
          )}
          aria-live="polite"
        >
          {sub}
        </span>
      </span>
      <Icon
        className={clsx(
          "relative size-4 shrink-0 transition-transform",
          (starting || waiting) && "animate-spin",
          started && "text-ok",
          !s && "group-hover:translate-y-0.5",
        )}
      />
    </button>
  );
}

function AfterDownload({ onReset }: { onReset: () => void }) {
  return (
    <div className="mt-4 space-y-3">
      <p className="flex items-start gap-2 rounded-xl bg-ok/10 px-3 py-2.5 text-sm text-fg">
        <Check className="mt-0.5 size-4 shrink-0 text-ok" />
        <span>
          Your download runs in your browser&apos;s download bar (or your download manager, like IDM) with full size and resume
          support for videos. You can keep using this page.
        </span>
      </p>
      <div className="flex flex-col gap-3 rounded-2xl border border-dashed border-line-strong p-3 sm:flex-row sm:items-center sm:justify-between sm:p-4">
        <div className="flex items-start gap-3">
          <span className="grid size-9 shrink-0 place-items-center rounded-xl bg-accent-soft text-accent">
            <Sparkles className="size-4" />
          </span>
          <div className="text-sm">
            <p className="font-medium">Turn it into a Short next</p>
            <p className="text-muted">
              <Subtitles className="mr-1 inline size-3.5" />
              Auto-captions and <Crop className="mx-1 inline size-3.5" />9:16 resize are coming soon.
            </p>
          </div>
        </div>
        <button
          type="button"
          onClick={onReset}
          className="inline-flex items-center justify-center gap-1.5 rounded-full bg-fg px-4 py-2 text-sm font-medium text-bg transition hover:opacity-90"
        >
          <Download className="size-4" /> Download another
        </button>
      </div>
    </div>
  );
}

/**
 * YouTube only serves a video a few seconds after the link is read (its pre-roll ad slot).
 * Count that down per item so buttons unlock exactly when the download can start instantly.
 */
function useReadyCountdown(data: Resolved): Record<number, number> {
  const [targets] = useState(() => Object.fromEntries(data.items.map((it) => [it.index, Date.now() + (it.ready_in ?? 0) * 1000])));
  const [now, setNow] = useState(() => Date.now());
  const pending = Object.values(targets).some((t) => t > now);
  useEffect(() => {
    if (!pending) return;
    const id = setInterval(() => setNow(Date.now()), 250);
    return () => clearInterval(id);
  }, [pending]);
  return Object.fromEntries(Object.entries(targets).map(([k, t]) => [Number(k), Math.max(0, Math.ceil((t - now) / 1000))]));
}
