"use client";

import clsx from "clsx";
import {
  ArrowRight,
  Check,
  CircleAlert,
  CloudUpload,
  FileVideo,
  FolderDown,
  Link2,
  LoaderCircle,
  RefreshCw,
  Search,
  SlidersHorizontal,
  Sparkles,
  Wand2,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, formatBytes, formatDuration, resolveUrl, type Resolved } from "@/lib/api";
import { CAPTIONS_HANDOFF_KEY, type CaptionsHandoff } from "@/lib/captions";
import { CAPTIONS_SLUG } from "@/lib/captionTools";
import type { ClipPreset } from "@/lib/clipTools";
import {
  ACTIVE,
  CLIPS_HANDOFF_KEY,
  CLIPS_JOB_KEY,
  type Clip,
  type ClipPatch,
  type ClipsHandoff,
  DEFAULT_LOOK,
  type FindOptions,
  type KConfig,
  type KJob,
  type KSource,
  cancelClipsJob,
  createClipsJob,
  editClip,
  findAgain,
  getClipsConfig,
  getClipsJob,
} from "@/lib/clips";
import { LENGTH_OPTIONS, type LengthId, clock, overallProgress, parseClock } from "@/lib/clipsCore";
import { extractUrl } from "@/lib/platforms";
import { type MediaInfo, formatEta, readSession, uploadFile, writeSession } from "@/lib/reframe";
import { Field, Segmented } from "../captions/ui";
import { ClipCard } from "./ClipCard";
import { ClipEditor, LookControls } from "./ClipEditor";

type FileSource = { kind: "file"; file: File; url: string; progress: number; uploadId: string | null; info: MediaInfo | null; error: string | null };
type LinkSource = { kind: "link"; link: ClipsHandoff };
type SourceState = FileSource | LinkSource | null;

const COUNTS: { id: string; label: string }[] = [
  { id: "auto", label: "Auto" },
  { id: "3", label: "3" },
  { id: "5", label: "5" },
  { id: "8", label: "8" },
  { id: "10", label: "10" },
];

function initialOptions(preset?: ClipPreset): FindOptions {
  return {
    length: preset?.length ?? "auto",
    count: null,
    topic: "",
    look: { ...DEFAULT_LOOK, aspect: preset?.aspect ?? DEFAULT_LOOK.aspect, preset: preset?.style ?? DEFAULT_LOOK.preset },
  };
}

export function ClipTool({ preset }: { preset?: ClipPreset }) {
  const router = useRouter();
  const [config, setConfig] = useState<KConfig | null>(null);
  const [source, setSource] = useState<SourceState>(null);
  const [language, setLanguage] = useState(preset?.language ?? "auto");
  const [options, setOptions] = useState<FindOptions>(() => initialOptions(preset));
  const [part, setPart] = useState({ start: "", end: "" });
  const [job, setJob] = useState<KJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [refind, setRefind] = useState(false);
  const [editing, setEditing] = useState<string | null>(null);
  const uploadAbort = useRef<AbortController | null>(null);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getClipsConfig().then(setConfig).catch(() => undefined);
  }, []);

  // A link handed over by the downloader, or resume after a reload.
  useEffect(() => {
    const from = new URLSearchParams(window.location.search).get("from");
    const handoff = readSession<ClipsHandoff>(CLIPS_HANDOFF_KEY);
    if (handoff && from === "link") {
      writeSession(CLIPS_HANDOFF_KEY, null);
      writeSession(CLIPS_JOB_KEY, null);
      setJob(null);
      setSource({ kind: "link", link: handoff });
      return;
    }
    const saved = readSession<string>(CLIPS_JOB_KEY);
    if (saved) {
      getClipsJob(saved)
        .then(setJob)
        .catch(() => writeSession(CLIPS_JOB_KEY, null));
    }
  }, []);

  // Poll while the server works (also while any single clip is being re-made).
  const active = job ? ACTIVE.includes(job.state) : false;
  useEffect(() => {
    if (!job || !active) return;
    let stop = false;
    const id = setInterval(async () => {
      try {
        const j = await getClipsJob(job.id);
        if (!stop) setJob(j);
      } catch (e) {
        if (!stop && e instanceof ApiError && /expired/i.test(e.message)) {
          setJob(null);
          setError(e.message);
          writeSession(CLIPS_JOB_KEY, null);
        }
      }
    }, 1200);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [job?.id, active]); // eslint-disable-line react-hooks/exhaustive-deps

  /* --------------------------------------------------------------- source */

  const startUpload = useCallback(
    (file: File) => {
      uploadAbort.current?.abort();
      const max = (config?.max_upload_mb ?? 1024) * 1024 * 1024;
      setError(null);
      setJob(null);
      writeSession(CLIPS_JOB_KEY, null);
      if (file.size > max) {
        setError(`This file is ${formatBytes(file.size)}. The limit is ${config?.max_upload_mb ?? 1024} MB.`);
        return;
      }
      if (file.type && !file.type.startsWith("video/") && !/\.(mkv|mov|mp4|webm|m4v|avi|3gp)$/i.test(file.name)) {
        setError("Please choose a video file (MP4, MOV, WebM, MKV).");
        return;
      }
      const url = URL.createObjectURL(file);
      const ctrl = new AbortController();
      uploadAbort.current = ctrl;
      setSource({ kind: "file", file, url, progress: 0, uploadId: null, info: null, error: null });
      setPart({ start: "", end: "" });
      uploadFile(file, (p) => setSource((c) => (c?.kind === "file" && c.file === file ? { ...c, progress: p } : c)), ctrl.signal)
        .then((res) => {
          setSource((c) => (c?.kind === "file" && c.file === file ? { ...c, uploadId: res.id, info: res.info, progress: 1 } : c));
          const maxDur = config?.max_duration_sec ?? 5400;
          if (res.info.duration > maxDur) setPart({ start: "0:00", end: clock(maxDur) });
        })
        .catch((e) => {
          if ((e as Error)?.name === "AbortError") return;
          setSource((c) => (c?.kind === "file" && c.file === file ? { ...c, error: e instanceof ApiError ? e.message : "Upload failed. Please try again." } : c));
        });
    },
    [config],
  );

  function reset() {
    uploadAbort.current?.abort();
    if (source?.kind === "file") URL.revokeObjectURL(source.url);
    setSource(null);
    setJob(null);
    setError(null);
    setRefind(false);
    setEditing(null);
    setPart({ start: "", end: "" });
    writeSession(CLIPS_JOB_KEY, null);
  }

  /* ---------------------------------------------------------------- start */

  const duration = source?.kind === "file" ? (source.info?.duration ?? null) : source?.kind === "link" ? source.link.duration : null;
  const ready = source?.kind === "link" || (source?.kind === "file" && !!source.uploadId);

  async function start() {
    if (!source) return;
    const rs = part.start ? parseClock(part.start) : 0;
    const re = part.end ? parseClock(part.end) : null;
    if (rs === null || (part.end && re === null)) {
      setError("Please write the start and end like 1:30 or 12:05.");
      return;
    }
    let src: KSource;
    let title: string;
    if (source.kind === "file") {
      if (!source.uploadId) return;
      src = { type: "upload", id: source.uploadId };
      title = source.file.name;
    } else {
      src = { type: "link", token: source.link.token, index: source.link.index };
      title = source.link.title;
    }
    setSubmitting(true);
    setError(null);
    try {
      const j = await createClipsJob({ source: src, language, options, range_start: rs ?? 0, range_end: re, title });
      setJob(j);
      writeSession(CLIPS_JOB_KEY, j.id);
      root.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function searchAgain() {
    if (!job) return;
    setSubmitting(true);
    setError(null);
    try {
      setJob(await findAgain(job.id, options));
      setRefind(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function saveClip(clip: Clip, patch: ClipPatch) {
    if (!job) return;
    setSubmitting(true);
    try {
      setJob(await editClip(job.id, clip.id, patch));
    } catch (e) {
      throw new Error(e instanceof ApiError ? e.message : "Couldn't save the changes.");
    } finally {
      setSubmitting(false);
    }
  }

  async function retry(clip: Clip) {
    try {
      await saveClip(clip, { render: true });
    } catch (e) {
      setError((e as Error).message);
    }
  }

  async function cancel() {
    if (!job) return;
    try {
      const j = await cancelClipsJob(job.id);
      if ("id" in j) setJob(j);
    } catch {
      /* the next poll shows the real state */
    }
  }

  function openCaptions(clip: Clip) {
    if (!job) return;
    const h: CaptionsHandoff = { kind: "clip", job: job.id, clip: clip.id, title: clip.title, aspect: clip.look.aspect };
    writeSession(CAPTIONS_HANDOFF_KEY, h);
    router.push(`/${CAPTIONS_SLUG}?from=clip`);
  }

  const editingClip = job?.clips.find((c) => c.id === editing) ?? null;
  const sourceAspect = job?.info ? job.info.width / job.info.height : 16 / 9;
  const presets = config?.presets ?? [];

  /* ---------------------------------------------------------------- views */

  return (
    <div ref={root} className="scroll-mt-24 space-y-6">
      <div className="mx-auto max-w-3xl space-y-5 rounded-3xl border border-line bg-elev p-4 shadow-card sm:p-6">
        {!source && !job && <SourcePicker config={config} onFile={startUpload} onLink={(l) => setSource({ kind: "link", link: l })} />}
        {(source || job) && <SourceCard source={source} job={job} onClear={reset} />}

        {error && (
          <p role="alert" className="flex items-start gap-2 rounded-xl bg-danger/10 p-3 text-sm text-danger">
            <CircleAlert className="mt-0.5 size-4 shrink-0" /> {error}
          </p>
        )}

        {source && !job && (
          <>
            <Settings
              config={config}
              options={options}
              setOptions={setOptions}
              language={language}
              setLanguage={setLanguage}
              part={part}
              setPart={setPart}
              duration={duration}
              presets={presets}
            />
            <button
              type="button"
              onClick={start}
              disabled={!ready || submitting}
              className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-accent px-6 py-3.5 text-base font-semibold text-accent-fg shadow-[0_10px_30px_-10px_var(--accent)] transition hover:-translate-y-px hover:brightness-105 disabled:translate-y-0 disabled:opacity-60"
            >
              {submitting || (source.kind === "file" && !source.uploadId && !source.error) ? <LoaderCircle className="size-5 animate-spin" /> : <Wand2 className="size-5" />}
              {source.kind === "file" && !source.uploadId
                ? source.error
                  ? "Upload failed"
                  : `Uploading… ${Math.round(source.progress * 100)}%`
                : "Find viral clips"}
            </button>
            <p className="text-center text-xs text-subtle">
              Only use videos you own or have permission to use. Files are deleted automatically within {config?.ttl_hours ?? 24} hours.
            </p>
          </>
        )}

        {job && active && <ProgressCard job={job} onCancel={cancel} />}

        {job && !active && job.state !== "ready" && (
          <div className="space-y-3">
            <p className="flex items-start gap-2 rounded-xl bg-danger/10 p-3 text-sm text-danger">
              <CircleAlert className="mt-0.5 size-4 shrink-0" /> {job.state === "cancelled" ? "Cancelled." : job.error}
            </p>
            <button type="button" onClick={reset} className="inline-flex items-center gap-1.5 rounded-full bg-fg px-4 py-2 text-sm font-medium text-bg">
              <RefreshCw className="size-4" /> Try another video
            </button>
          </div>
        )}

        {job?.state === "ready" && !refind && (
          <ReadyBar
            job={job}
            onRefind={() => {
              setOptions((o) => ({ ...o, length: job.settings.length, count: job.settings.count, topic: job.settings.topic ?? "" }));
              setRefind(true);
            }}
            onNew={reset}
          />
        )}

        {job && refind && (
          <div className="space-y-4">
            <p className="text-sm text-muted">Search the same video again with other settings. The AI doesn&apos;t need to listen again, so it&apos;s quick. Your current clips are replaced.</p>
            <SearchSettings options={options} setOptions={setOptions} presets={presets} />
            <div className="flex gap-2">
              <button
                type="button"
                onClick={searchAgain}
                disabled={submitting || active}
                className="inline-flex flex-1 items-center justify-center gap-2 rounded-full bg-accent px-5 py-3 text-sm font-semibold text-accent-fg transition hover:brightness-105 disabled:opacity-60"
              >
                {submitting ? <LoaderCircle className="size-4 animate-spin" /> : <Search className="size-4" />} Search again
              </button>
              <button type="button" onClick={() => setRefind(false)} className="rounded-full px-4 py-3 text-sm font-medium text-muted hover:text-fg">
                Cancel
              </button>
            </div>
          </div>
        )}
      </div>

      {job && job.clips.length > 0 && (
        <section aria-label="Your clips" className="space-y-4">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <h2 className="text-xl font-semibold tracking-tight">
                {job.clips.length} clip{job.clips.length === 1 ? "" : "s"}, best first
              </h2>
              <p className="text-sm text-muted">
                {job.method === "ai" ? "Picked by AI from the full transcript." : "Picked by our moment scorer from the full transcript."} {job.ready_count < job.clips.length && active ? `${job.ready_count} of ${job.clips.length} ready, the rest are on the way.` : ""}
              </p>
            </div>
            {job.zip && (
              <a href={job.zip} className="inline-flex items-center gap-1.5 rounded-full bg-fg px-4 py-2 text-sm font-semibold text-bg transition hover:opacity-90">
                <FolderDown className="size-4" /> Download all ({job.ready_count}) · ZIP
              </a>
            )}
          </div>
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {job.clips.map((c) => (
              <ClipCard key={c.id} clip={c} sourceAspect={sourceAspect} busy={submitting} onEdit={() => setEditing(c.id)} onRetry={() => retry(c)} onCaptions={() => openCaptions(c)} />
            ))}
          </div>
        </section>
      )}

      {job && editingClip && job.info && (
        <ClipEditor
          key={`${editingClip.id}-${editingClip.version}`}
          clip={editingClip}
          sourceUrl={job.source.url}
          transcriptUrl={job.transcript}
          duration={job.info.duration}
          presets={presets}
          busy={submitting}
          onSave={(patch) => saveClip(editingClip, patch)}
          onClose={() => setEditing(null)}
        />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ settings */

function SearchSettings({ options, setOptions, presets }: { options: FindOptions; setOptions: (o: FindOptions) => void; presets: KConfig["presets"] }) {
  const [more, setMore] = useState(false);
  return (
    <div className="space-y-4">
      <Field label="Clip length" hint={LENGTH_OPTIONS.find((l) => l.id === options.length)?.hint}>
        <Segmented<LengthId> label="Clip length" value={options.length} onChange={(v) => setOptions({ ...options, length: v })} options={LENGTH_OPTIONS.map((l) => ({ id: l.id, label: l.label, title: l.hint }))} />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="How many clips">
          <Segmented<string>
            label="How many clips"
            value={options.count ? String(options.count) : "auto"}
            onChange={(v) => setOptions({ ...options, count: v === "auto" ? null : Number(v) })}
            options={COUNTS}
          />
        </Field>
        <Field label="Only clips about" hint="Optional">
          <input
            value={options.topic}
            onChange={(e) => setOptions({ ...options, topic: e.target.value })}
            maxLength={200}
            placeholder="e.g. money, marriage, cricket"
            className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm"
          />
        </Field>
      </div>
      <button type="button" onClick={() => setMore((v) => !v)} aria-expanded={more} className="inline-flex items-center gap-1.5 text-sm font-medium text-muted transition hover:text-fg">
        <SlidersHorizontal className="size-4" /> {more ? "Hide look options" : "Look: shape, framing, caption style"}
      </button>
      {more && <LookControls look={options.look} setLook={(l) => setOptions({ ...options, look: l })} presets={presets} />}
    </div>
  );
}

function Settings({
  config,
  options,
  setOptions,
  language,
  setLanguage,
  part,
  setPart,
  duration,
  presets,
}: {
  config: KConfig | null;
  options: FindOptions;
  setOptions: (o: FindOptions) => void;
  language: string;
  setLanguage: (v: string) => void;
  part: { start: string; end: string };
  setPart: (p: { start: string; end: string }) => void;
  duration: number | null;
  presets: KConfig["presets"];
}) {
  const langs = config?.languages ?? [];
  const tooLong = duration && config && duration > config.max_duration_sec;
  return (
    <div className="space-y-4">
      <Field label="Language spoken">
        <select value={language} onChange={(e) => setLanguage(e.target.value)} className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm">
          <option value="auto">Detect automatically</option>
          <optgroup label="Popular">
            {langs.filter((l) => l.popular).map((l) => (
              <option key={l.code} value={l.code}>
                {l.name}
                {l.native !== l.name ? ` · ${l.native}` : ""}
              </option>
            ))}
          </optgroup>
          <optgroup label="More">
            {langs.filter((l) => !l.popular).map((l) => (
              <option key={l.code} value={l.code}>
                {l.name}
              </option>
            ))}
          </optgroup>
        </select>
      </Field>
      <SearchSettings options={options} setOptions={setOptions} presets={presets} />
      <details className="group rounded-2xl border border-line p-3" open={!!tooLong}>
        <summary className="cursor-pointer text-sm font-medium">Search only part of the video {tooLong ? `(up to ${Math.round(config!.max_duration_sec / 60)} min)` : ""}</summary>
        <div className="mt-3 grid grid-cols-2 gap-3">
          <Field label="From">
            <input value={part.start} onChange={(e) => setPart({ ...part, start: e.target.value })} placeholder="0:00" className="w-full rounded-xl border border-line bg-bg px-3 py-2 font-mono text-sm" />
          </Field>
          <Field label="To">
            <input value={part.end} onChange={(e) => setPart({ ...part, end: e.target.value })} placeholder={duration ? clock(duration) : "end"} className="w-full rounded-xl border border-line bg-bg px-3 py-2 font-mono text-sm" />
          </Field>
        </div>
      </details>
    </div>
  );
}

/* ------------------------------------------------------------------ source */

function SourcePicker({ config, onFile, onLink }: { config: KConfig | null; onFile: (f: File) => void; onLink: (l: ClipsHandoff) => void }) {
  const [tab, setTab] = useState<"upload" | "link">("upload");
  const [over, setOver] = useState(false);
  return (
    <div>
      {config?.allow_links !== false && (
        <div role="tablist" className="mb-4 flex gap-1 rounded-xl bg-line/60 p-1">
          {(
            [
              ["upload", "Upload a video", CloudUpload],
              ["link", "Paste a link", Link2],
            ] as const
          ).map(([id, label, Icon]) => (
            <button
              key={id}
              role="tab"
              type="button"
              aria-selected={tab === id}
              onClick={() => setTab(id)}
              className={clsx("flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-sm font-medium transition", tab === id ? "bg-elev shadow-card" : "text-muted hover:text-fg")}
            >
              <Icon className="size-4" /> {label}
            </button>
          ))}
        </div>
      )}
      {tab === "upload" ? (
        <label
          onDragOver={(e) => {
            e.preventDefault();
            setOver(true);
          }}
          onDragLeave={() => setOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setOver(false);
            const f = e.dataTransfer.files?.[0];
            if (f) onFile(f);
          }}
          className={clsx(
            "flex cursor-pointer flex-col items-center justify-center gap-3 rounded-2xl border-2 border-dashed px-6 py-14 text-center transition",
            over ? "border-accent bg-accent-soft/50" : "border-line-strong hover:border-fg",
          )}
        >
          <span className="grid size-14 place-items-center rounded-2xl bg-accent-soft text-accent">
            <CloudUpload className="size-7" />
          </span>
          <span className="text-lg font-semibold">Drop your long video here</span>
          <span className="text-sm text-muted">
            or <span className="font-medium text-accent underline underline-offset-2">choose a file</span> · podcast, interview, stream, lecture · up to{" "}
            {Math.round((config?.max_duration_sec ?? 5400) / 60)} min
          </span>
          <input
            type="file"
            accept="video/*,.mkv,.mov,.m4v"
            className="sr-only"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onFile(f);
              e.target.value = "";
            }}
          />
        </label>
      ) : (
        <LinkInput onLink={onLink} />
      )}
    </div>
  );
}

function LinkInput({ onLink }: { onLink: (l: ClipsHandoff) => void }) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [choices, setChoices] = useState<Resolved | null>(null);

  const pick = (r: Resolved, index: number) => {
    const it = r.items[index];
    onLink({ token: r.token, index, title: it.title || r.title, thumbnail: it.thumbnail, duration: it.duration });
  };

  async function go(e: React.FormEvent) {
    e.preventDefault();
    const url = extractUrl(value) ?? value.trim();
    if (!url) return;
    setBusy(true);
    setErr(null);
    setChoices(null);
    try {
      const r = await resolveUrl(url);
      const usable = r.items.filter((it) => !it.error && it.options.some((o) => o.kind === "video"));
      if (!usable.length) throw new ApiError(r.items[0]?.error ?? "This post has no video we can use.");
      if (usable.length === 1) pick(r, usable[0].index);
      else setChoices(r);
    } catch (e2) {
      setErr(e2 instanceof ApiError ? e2.message : "Couldn't read this link.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-3">
      <form onSubmit={go} className="flex gap-2 rounded-2xl border border-line-strong bg-bg p-1.5 focus-within:border-accent">
        <input
          value={value}
          onChange={(e) => setValue(e.target.value)}
          aria-label="Video link"
          placeholder="Paste a YouTube, Facebook, Instagram or X video link"
          inputMode="url"
          className="min-w-0 flex-1 bg-transparent px-3 py-2.5 text-sm outline-none"
        />
        <button type="submit" disabled={busy || !value.trim()} className="inline-flex items-center gap-1.5 rounded-xl bg-fg px-4 text-sm font-medium text-bg disabled:opacity-50">
          {busy ? <LoaderCircle className="size-4 animate-spin" /> : <ArrowRight className="size-4" />} Use
        </button>
      </form>
      {err && <p className="text-sm text-danger">{err}</p>}
      {choices && (
        <div>
          <p className="mb-2 text-sm text-muted">This post has several videos. Pick one:</p>
          <div className="flex gap-2 overflow-x-auto pb-1">
            {choices.items
              .filter((it) => !it.error)
              .map((it) => (
                <button key={it.index} type="button" onClick={() => pick(choices, it.index)} className="relative h-24 w-16 shrink-0 overflow-hidden rounded-lg border-2 border-transparent bg-line hover:border-accent">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  {it.thumbnail && <img src={it.thumbnail} alt="" className="size-full object-cover" />}
                  <span className="absolute bottom-0.5 left-0.5 rounded bg-black/70 px-1 text-[10px] text-white">{it.index + 1}</span>
                </button>
              ))}
          </div>
        </div>
      )}
      <p className="text-xs text-subtle">Only use videos you own or have permission to repost.</p>
    </div>
  );
}

function SourceCard({ source, job, onClear }: { source: SourceState; job: KJob | null; onClear: () => void }) {
  const title = source?.kind === "file" ? source.file.name : source?.kind === "link" ? source.link.title : (job?.title ?? "Video");
  const info = source?.kind === "file" ? source.info : (job?.info ?? null);
  const duration = info?.duration ?? (source?.kind === "link" ? source.link.duration : null);
  const uploading = source?.kind === "file" && !source.uploadId && !source.error;
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-line bg-bg p-3">
      <span className="grid size-11 shrink-0 place-items-center overflow-hidden rounded-xl bg-accent-soft text-accent">
        {source?.kind === "link" && source.link.thumbnail ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={source.link.thumbnail} alt="" className="size-full object-cover" />
        ) : source?.kind === "link" ? (
          <Link2 className="size-5" />
        ) : (
          <FileVideo className="size-5" />
        )}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{title}</p>
        <p className="truncate text-xs text-muted">
          {[info && `${info.width}×${info.height}`, duration && formatDuration(duration), source?.kind === "file" && formatBytes(source.file.size)].filter(Boolean).join(" · ") ||
            (source?.kind === "link" ? "From link" : "")}
        </p>
        {uploading && (
          <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-line">
            <div className="h-full rounded-full bg-accent transition-[width] duration-300" style={{ width: `${Math.round(source.progress * 100)}%` }} />
          </div>
        )}
        {source?.kind === "file" && source.error && <p className="mt-1 text-xs text-danger">{source.error}</p>}
      </div>
      <button type="button" onClick={onClear} aria-label="Use another video" className="grid size-9 shrink-0 place-items-center rounded-full text-muted transition hover:bg-line hover:text-fg">
        <X className="size-4" />
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ status */

const STEPS: { states: KJob["state"][]; label: string }[] = [
  { states: ["queued"], label: "In line" },
  { states: ["importing"], label: "Fetching" },
  { states: ["transcribing"], label: "Listening" },
  { states: ["finding"], label: "Finding moments" },
  { states: ["rendering"], label: "Making clips" },
];

function ProgressCard({ job, onCancel }: { job: KJob; onCancel: () => void }) {
  const pct = Math.round(overallProgress(job.state, job.progress) * 100);
  const steps = STEPS.filter((s) => (s.states[0] === "importing" ? job.source.type === "link" : s.states[0] === "transcribing" || s.states[0] === "finding" ? job.task !== "render" : true));
  const current = steps.findIndex((s) => s.states.includes(job.state));
  return (
    <div className="space-y-4 rounded-2xl border border-line bg-bg p-4" aria-live="polite">
      <div className="flex items-center justify-between gap-3">
        <p className="flex items-center gap-2 font-semibold">
          <LoaderCircle className="size-5 animate-spin text-accent" />
          {job.state === "queued" && job.queue_position ? `Waiting in line (#${job.queue_position})` : job.stage}
        </p>
        <span className="font-mono text-sm text-muted">{pct}%</span>
      </div>
      <div className="h-2.5 overflow-hidden rounded-full bg-line">
        <div className="h-full rounded-full bg-accent transition-[width] duration-700 ease-out" style={{ width: `${Math.max(2, pct)}%` }} />
      </div>
      <ol className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
        {steps.map((s, i) => (
          <li key={s.label} className={clsx("flex items-center gap-1", i < current ? "text-ok" : i === current ? "font-medium text-fg" : "text-subtle")}>
            {i < current ? <Check className="size-3.5" /> : <span className="size-1.5 rounded-full bg-current" />} {s.label}
          </li>
        ))}
      </ol>
      <div className="flex items-center justify-between text-xs text-muted">
        <span>{formatEta(job.eta) || "Clips appear below as soon as each one is ready. You can keep this tab open and do other things."}</span>
        <button type="button" onClick={onCancel} className="rounded-full px-3 py-1 font-medium transition hover:bg-line hover:text-fg">
          Stop
        </button>
      </div>
    </div>
  );
}

function ReadyBar({ job, onRefind, onNew }: { job: KJob; onRefind: () => void; onNew: () => void }) {
  const failed = job.clips.filter((c) => c.status === "error" || c.status === "pending").length;
  return (
    <div className="space-y-3">
      <p className="flex items-center gap-2 rounded-xl bg-ok/10 px-3 py-2.5 text-sm">
        <Sparkles className="size-4 shrink-0 text-ok" />
        {job.ready_count} clip{job.ready_count === 1 ? " is" : "s are"} ready.{failed ? ` ${failed} still need${failed === 1 ? "s" : ""} making, press its button below.` : " Play them below, tweak any one, then download."}
      </p>
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={onRefind} className="inline-flex items-center gap-1.5 rounded-full border border-line-strong px-4 py-2 text-sm font-medium transition hover:border-fg">
          <Search className="size-4" /> Find different clips
        </button>
        <button type="button" onClick={onNew} className="inline-flex items-center gap-1.5 rounded-full border border-line-strong px-4 py-2 text-sm font-medium transition hover:border-fg">
          <RefreshCw className="size-4" /> New video
        </button>
      </div>
    </div>
  );
}
