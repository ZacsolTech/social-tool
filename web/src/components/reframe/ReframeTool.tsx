"use client";

import clsx from "clsx";
import {
  ArrowRight,
  Check,
  CircleAlert,
  CloudUpload,
  Download,
  Eye,
  EyeOff,
  FileVideo,
  Link2,
  LoaderCircle,
  RefreshCw,
  Settings2,
  Sparkles,
  Subtitles,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, formatBytes, formatDuration, resolveUrl, type Resolved } from "@/lib/api";
import { extractUrl } from "@/lib/platforms";
import {
  ACTIVE,
  type Aspect,
  type Config,
  DEFAULT_LOOK,
  DEFAULT_SMART,
  type Job,
  CAPTIONS_REFRAME_KEY,
  type CaptionsReframeHandoff,
  HANDOFF_KEY,
  JOB_KEY,
  type LinkHandoff,
  type MediaInfo,
  type Override,
  type Settings,
  type Source,
  cancelJob,
  createJob,
  formatClock,
  formatEta,
  getConfig,
  getJob,
  readSession,
  rerender,
  uploadFile,
  writeSession,
} from "@/lib/reframe";
import { CAPTIONS_HANDOFF_KEY, type CaptionsHandoff } from "@/lib/captions";
import { CAPTIONS_SLUG } from "@/lib/captionTools";
import type { ToolPreset } from "@/lib/tools";
import { PhonePreview, type PreviewSource } from "./PhonePreview";
import { SettingsPanel } from "./SettingsPanel";
import { ShotEditor } from "./ShotEditor";

type FileSource = {
  kind: "file";
  file: File;
  url: string;
  progress: number;
  uploadId: string | null;
  info: MediaInfo | null;
  error: string | null;
};
type LinkSource = { kind: "link"; link: LinkHandoff };
type CaptionsSource = { kind: "captions"; handoff: CaptionsReframeHandoff };
type SourceState = FileSource | LinkSource | CaptionsSource | null;

function initialSettings(preset?: ToolPreset): Settings {
  return {
    mode: preset?.mode ?? "smart",
    aspects: preset?.aspects ?? ["9:16"],
    quality: "1080p",
    smart: { ...DEFAULT_SMART, ...preset?.smart },
    look: { ...DEFAULT_LOOK, ...preset?.look },
    position: 0.5,
    trimStart: 0,
    trimEnd: null,
  };
}

export function ReframeTool({ preset }: { preset?: ToolPreset }) {
  const router = useRouter();
  const [config, setConfig] = useState<Config | null>(null);
  const [settings, setSettings] = useState<Settings>(() => initialSettings(preset));
  const [source, setSource] = useState<SourceState>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [editing, setEditing] = useState(false);     // changing settings of a finished job
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [showSafe, setShowSafe] = useState(true);
  const [previewAspect, setPreviewAspect] = useState<Aspect>(settings.aspects[0]);
  const uploadAbort = useRef<AbortController | null>(null);
  const rootRef = useRef<HTMLDivElement>(null);

  const set = useCallback((patch: Partial<Settings>) => setSettings((s) => ({ ...s, ...patch })), []);

  useEffect(() => {
    getConfig().then(setConfig).catch(() => undefined);
  }, []);

  // Resume a job after a reload, or pick up a link handed over by the downloader ("Make it vertical").
  useEffect(() => {
    const from = new URLSearchParams(window.location.search).get("from");
    const handoff = readSession<LinkHandoff>(HANDOFF_KEY);
    if (handoff && from === "link") {
      writeSession(HANDOFF_KEY, null);
      writeSession(JOB_KEY, null);
      setJob(null);
      setEditing(false);
      setSource({ kind: "link", link: handoff });
      return;
    }
    const fromCaptions = readSession<CaptionsReframeHandoff>(CAPTIONS_REFRAME_KEY);
    if (fromCaptions && from === "captions") {
      writeSession(CAPTIONS_REFRAME_KEY, null);
      writeSession(JOB_KEY, null);
      setJob(null);              // Next keeps visited pages alive: drop an earlier conversion
      setEditing(false);
      setError(null);
      setSource({ kind: "captions", handoff: fromCaptions });
      return;
    }
    const saved = readSession<string>(JOB_KEY);
    if (saved) {
      getJob(saved)
        .then((j) => {
          setJob(j);
          setSettings((s) => ({ ...s, mode: j.mode, aspects: j.aspects, quality: j.quality, smart: j.smart, look: j.look, position: j.position }));
          setPreviewAspect(j.aspects[0]);
        })
        .catch(() => writeSession(JOB_KEY, null));
    }
  }, []);

  useEffect(() => {
    if (!settings.aspects.includes(previewAspect)) setPreviewAspect(settings.aspects[0]);
  }, [settings.aspects, previewAspect]);

  // Poll while the job is working.
  const active = job ? ACTIVE.includes(job.state) : false;
  useEffect(() => {
    if (!job || !active) return;
    let stop = false;
    const tick = async () => {
      try {
        const j = await getJob(job.id);
        if (!stop) setJob(j);
      } catch (e) {
        if (!stop && e instanceof ApiError && /expired/i.test(e.message)) {
          setJob(null);
          setError(e.message);
          writeSession(JOB_KEY, null);
        }
      }
    };
    const id = setInterval(tick, 1000);
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
      setEditing(false);
      writeSession(JOB_KEY, null);
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
      const base: FileSource = { kind: "file", file, url, progress: 0, uploadId: null, info: null, error: null };
      setSource(base);
      setSettings((s) => ({ ...s, trimStart: 0, trimEnd: null }));
      uploadFile(file, (p) => setSource((cur) => (cur?.kind === "file" && cur.file === file ? { ...cur, progress: p } : cur)), ctrl.signal)
        .then((res) => {
          setSource((cur) => (cur?.kind === "file" && cur.file === file ? { ...cur, uploadId: res.id, info: res.info, progress: 1 } : cur));
          const maxDur = config?.max_duration_sec ?? 1800;
          if (res.info.duration > maxDur) setSettings((s) => ({ ...s, trimEnd: maxDur }));
        })
        .catch((e) => {
          if ((e as Error)?.name === "AbortError") return;
          setSource((cur) => (cur?.kind === "file" && cur.file === file ? { ...cur, error: e instanceof ApiError ? e.message : "Upload failed. Please try again." } : cur));
        });
    },
    [config],
  );

  function clearSource() {
    uploadAbort.current?.abort();
    if (source?.kind === "file") URL.revokeObjectURL(source.url);
    setSource(null);
    setJob(null);
    setEditing(false);
    setError(null);
    writeSession(JOB_KEY, null);
    setSettings((s) => ({ ...s, trimStart: 0, trimEnd: null }));
  }

  /* -------------------------------------------------------------- convert */

  const ready = editing ? !!job : source?.kind === "link" || source?.kind === "captions" || (source?.kind === "file" && !!source.uploadId);

  async function convert() {
    setError(null);
    setSubmitting(true);
    try {
      let j: Job;
      if (editing && job) {
        j = await rerender(job.id, { settings, overrides: settings.mode === "smart" ? numKeys(job.overrides) : {} });
      } else {
        let src: Source;
        let title: string | undefined;
        if (source?.kind === "file" && source.uploadId) {
          src = { type: "upload", id: source.uploadId };
          title = source.file.name;
        } else if (source?.kind === "link") {
          src = { type: "link", token: source.link.token, index: source.link.index };
          title = source.link.title;
        } else if (source?.kind === "captions") {
          src = { type: "captions", id: source.handoff.captions };
          title = source.handoff.title;
        } else return;
        j = await createJob(src, settings, title);
      }
      setJob(j);
      setEditing(false);
      setPreviewAspect(j.aspects[0]);
      writeSession(JOB_KEY, j.id);
      rootRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function applyEdits(overrides: Record<number, Override>) {
    if (!job) return;
    setSubmitting(true);
    setError(null);
    try {
      setJob(await rerender(job.id, { overrides }));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Couldn't apply the changes. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  async function cancel() {
    if (!job) return;
    try {
      const j = await cancelJob(job.id);
      if ("id" in j) setJob(j);
    } catch {
      /* the next poll shows the real state */
    }
  }

  /* -------------------------------------------------------------- preview */

  const preview: PreviewSource = useMemo(() => {
    if (source?.kind === "file") return { kind: "video", url: source.url };
    if (source?.kind === "link") return source.link.thumbnail ? { kind: "image", url: source.link.thumbnail } : null;
    if (source?.kind === "captions") return { kind: "video", url: `/api/captions/jobs/${source.handoff.captions}/source` };
    if (job) return { kind: "video", url: job.source.url };
    return null;
  }, [source, job]);

  const resultUrl =
    job?.state === "done" && !editing ? (job.outputs.find((o) => o.aspect === previewAspect)?.url ?? null) : null;
  const shownAspects = job && !editing ? job.aspects : settings.aspects;
  const duration =
    source?.kind === "file"
      ? (source.info?.duration ?? null)
      : source?.kind === "link"
        ? source.link.duration
        : source?.kind === "captions"
          ? source.handoff.duration
          : (job?.info?.duration ?? null);
  const showSettings = (!job || editing) && (source || editing);

  return (
    <div ref={rootRef} className="scroll-mt-24">
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_320px] lg:items-start">
        <div className="min-w-0 space-y-5 rounded-3xl border border-line bg-elev p-4 shadow-card sm:p-6">
          {!source && !job && <SourcePicker config={config} onFile={startUpload} onLink={(l) => setSource({ kind: "link", link: l })} />}

          {(source || job) && (
            <SourceCard source={source} job={job} onClear={clearSource} lockedTrim={!!job} />
          )}

          {error && (
            <p role="alert" className="flex items-start gap-2 rounded-xl bg-danger/10 p-3 text-sm text-danger">
              <CircleAlert className="mt-0.5 size-4 shrink-0" /> {error}
            </p>
          )}

          {showSettings && (
            <>
              <SettingsPanel s={settings} set={set} config={config} duration={duration} disabled={submitting} />
              {editing && <p className="text-xs text-muted">Trim can&apos;t change for this video. Start a new conversion to pick a different part.</p>}
              <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                <button
                  type="button"
                  onClick={convert}
                  disabled={!ready || submitting}
                  className="inline-flex flex-1 items-center justify-center gap-2 rounded-full bg-accent px-6 py-3.5 text-base font-semibold text-accent-fg shadow-[0_10px_30px_-10px_var(--accent)] transition hover:-translate-y-px hover:brightness-105 disabled:translate-y-0 disabled:opacity-60"
                >
                  {submitting ? (
                    <LoaderCircle className="size-5 animate-spin" />
                  ) : source?.kind === "file" && !source.uploadId && !source.error && !editing ? (
                    <LoaderCircle className="size-5 animate-spin" />
                  ) : (
                    <Sparkles className="size-5" />
                  )}
                  {source?.kind === "file" && !source.uploadId && !editing
                    ? source.error
                      ? "Upload failed"
                      : `Uploading… ${Math.round(source.progress * 100)}%`
                    : editing
                      ? "Re-render with these settings"
                      : `Convert to ${settings.aspects.join(" + ")}`}
                </button>
                {editing && (
                  <button type="button" onClick={() => setEditing(false)} className="rounded-full px-4 py-3 text-sm font-medium text-muted transition hover:text-fg">
                    Cancel
                  </button>
                )}
              </div>
              <p className="text-center text-xs text-subtle">
                Only convert videos you own or have permission to use. Files are deleted automatically within {config?.ttl_hours ?? 24} hours.
              </p>
            </>
          )}

          {job && !editing && ACTIVE.includes(job.state) && <ProgressCard job={job} onCancel={cancel} />}

          {job && !editing && (job.state === "error" || job.state === "cancelled") && (
            <div className="space-y-3">
              <p className="flex items-start gap-2 rounded-xl bg-danger/10 p-3 text-sm text-danger">
                <CircleAlert className="mt-0.5 size-4 shrink-0" /> {job.state === "cancelled" ? "Conversion cancelled." : job.error}
              </p>
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => setEditing(true)} className="inline-flex items-center gap-1.5 rounded-full bg-fg px-4 py-2 text-sm font-medium text-bg">
                  <RefreshCw className="size-4" /> Try again
                </button>
                <button type="button" onClick={clearSource} className="rounded-full border border-line-strong px-4 py-2 text-sm font-medium">
                  Use another video
                </button>
              </div>
            </div>
          )}

          {job?.state === "done" && !editing && (
            <Results
              job={job}
              previewAspect={previewAspect}
              setPreviewAspect={setPreviewAspect}
              onEdit={() => setEditing(true)}
              onNew={clearSource}
              onCaptions={() => {
                const h: CaptionsHandoff = { kind: "reframe", job: job.id, aspect: previewAspect, title: job.title, reuse: job.source.captions ?? null };
                writeSession(CAPTIONS_HANDOFF_KEY, h);
                router.push(`/${CAPTIONS_SLUG}?from=reframe`);
              }}
            />
          )}
        </div>

        <aside className={clsx("space-y-3 lg:sticky lg:top-24", !preview && !resultUrl && "hidden lg:block")}>
          {shownAspects.length > 1 && (
            <div role="tablist" aria-label="Preview format" className="flex justify-center gap-1">
              {shownAspects.map((a) => (
                <button
                  key={a}
                  role="tab"
                  type="button"
                  aria-selected={previewAspect === a}
                  onClick={() => setPreviewAspect(a)}
                  className={clsx("rounded-full px-3 py-1 text-xs font-semibold transition", previewAspect === a ? "bg-fg text-bg" : "text-muted hover:text-fg")}
                >
                  {a}
                </button>
              ))}
            </div>
          )}
          <PhonePreview
            source={preview}
            aspect={previewAspect}
            mode={settings.mode}
            look={settings.look}
            position={settings.position}
            framing={settings.mode === "crop" ? settings.smart.framing : 1}
            safeZone={settings.smart.safe_zone}
            showSafe={showSafe}
            result={resultUrl}
          />
          {!resultUrl && preview && (
            <button type="button" onClick={() => setShowSafe((v) => !v)} className="mx-auto flex items-center gap-1.5 text-xs text-muted transition hover:text-fg">
              {showSafe ? <EyeOff className="size-3.5" /> : <Eye className="size-3.5" />}
              {showSafe ? "Hide" : "Show"} app buttons overlay
            </button>
          )}
        </aside>
      </div>

      {job?.state === "done" && !editing && job.editable && (
        <div className="mt-6">
          <ShotEditor key={`${job.id}-${job.version}`} job={job} busy={submitting} onApply={applyEdits} />
        </div>
      )}
    </div>
  );
}

function numKeys(o: Record<string, Override>): Record<number, Override> {
  return Object.fromEntries(Object.entries(o ?? {}).map(([k, v]) => [Number(k), v]));
}

/* ------------------------------------------------------------------ source */

function SourcePicker({ config, onFile, onLink }: { config: Config | null; onFile: (f: File) => void; onLink: (l: LinkHandoff) => void }) {
  const [tab, setTab] = useState<"upload" | "link">("upload");
  const [over, setOver] = useState(false);
  const input = useRef<HTMLInputElement>(null);
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
          <span className="text-lg font-semibold">Drop your landscape video here</span>
          <span className="text-sm text-muted">
            or <span className="font-medium text-accent underline underline-offset-2">choose a file</span> · MP4, MOV, WebM, MKV · up to {config?.max_upload_mb ?? 1024} MB
          </span>
          <input
            ref={input}
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

function LinkInput({ onLink }: { onLink: (l: LinkHandoff) => void }) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [choices, setChoices] = useState<Resolved | null>(null);

  const pick = (r: Resolved, index: number) => {
    const it = r.items[index];
    onLink({ token: r.token, index, title: it.title || r.title, thumbnail: it.thumbnail, duration: it.duration, width: it.width, height: it.height });
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
          placeholder="Paste a YouTube, TikTok, Instagram, Facebook or X link"
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

function SourceCard({ source, job, onClear, lockedTrim }: { source: SourceState; job: Job | null; onClear: () => void; lockedTrim: boolean }) {
  const title =
    source?.kind === "file" ? source.file.name : source?.kind === "link" ? source.link.title : source?.kind === "captions" ? source.handoff.title : (job?.title ?? "Video");
  const info = source?.kind === "file" ? source.info : (job?.info ?? null);
  const duration = info?.duration ?? (source?.kind === "link" ? source.link.duration : null);
  const uploading = source?.kind === "file" && !source.uploadId && !source.error;
  const portrait = info && info.height >= info.width;
  return (
    <div className="space-y-2">
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
            {[
              info && `${info.width}×${info.height}`,
              duration && formatDuration(duration),
              source?.kind === "file" && formatBytes(source.file.size),
              info?.hdr && "HDR",
              lockedTrim && job && (job.trim[0] || job.trim[1]) ? `part ${formatClock(job.trim[0])}–${job.trim[1] ? formatClock(job.trim[1]) : "end"}` : null,
            ]
              .filter(Boolean)
              .join(" · ") || (source?.kind === "link" ? "From link" : "")}
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
      {portrait && (
        <p className="rounded-xl bg-accent-soft/60 px-3 py-2 text-xs text-fg">
          This video is already vertical. You can still make 4:5 or 1:1 versions, or reframe it to 9:16.
        </p>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ status */

const STEPS: { state: Job["state"][]; label: string }[] = [
  { state: ["queued"], label: "In line" },
  { state: ["importing"], label: "Fetching" },
  { state: ["analysing"], label: "AI analysis" },
  { state: ["rendering"], label: "Rendering" },
];

function ProgressCard({ job, onCancel }: { job: Job; onCancel: () => void }) {
  const pct = Math.round(job.progress * 100);
  const steps = STEPS.filter((s) => (s.state[0] === "importing" ? job.source.type === "link" : s.state[0] === "analysing" ? job.mode === "smart" : true));
  const current = steps.findIndex((s) => s.state.includes(job.state));
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
        <span>{formatEta(job.eta) || "You can keep this tab open and do other things."}</span>
        <button type="button" onClick={onCancel} className="rounded-full px-3 py-1 font-medium transition hover:bg-line hover:text-fg">
          Cancel
        </button>
      </div>
    </div>
  );
}

function Results({
  job,
  previewAspect,
  setPreviewAspect,
  onEdit,
  onNew,
  onCaptions,
}: {
  job: Job;
  previewAspect: Aspect;
  setPreviewAspect: (a: Aspect) => void;
  onEdit: () => void;
  onNew: () => void;
  onCaptions: () => void;
}) {
  return (
    <div className="space-y-4">
      <p className="flex items-center gap-2 rounded-xl bg-ok/10 px-3 py-2.5 text-sm">
        <Check className="size-4 shrink-0 text-ok" />
        {job.outputs.length > 1 ? "Your vertical videos are ready. Play them in the preview, then download." : "Your vertical video is ready. Play it in the preview, then download."}
      </p>
      <ul className="space-y-2">
        {job.outputs.map((o) => (
          <li key={o.aspect} className={clsx("flex items-center gap-3 rounded-2xl border p-3", previewAspect === o.aspect ? "border-accent/60" : "border-line")}>
            <button type="button" onClick={() => setPreviewAspect(o.aspect)} className="min-w-0 flex-1 text-left">
              <span className="block font-semibold">{o.aspect}</span>
              <span className="block truncate text-xs text-muted">
                {o.name} · {formatBytes(o.size)}
              </span>
            </button>
            <a
              href={o.url}
              download={o.name}
              className="inline-flex items-center gap-1.5 rounded-full bg-accent px-4 py-2 text-sm font-semibold text-accent-fg transition hover:brightness-105"
            >
              <Download className="size-4" /> Download
            </a>
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap gap-2">
        <button type="button" onClick={onEdit} className="inline-flex items-center gap-1.5 rounded-full border border-line-strong px-4 py-2 text-sm font-medium transition hover:border-fg">
          <Settings2 className="size-4" /> Change settings
        </button>
        <button type="button" onClick={onNew} className="inline-flex items-center gap-1.5 rounded-full border border-line-strong px-4 py-2 text-sm font-medium transition hover:border-fg">
          <RefreshCw className="size-4" /> Convert another video
        </button>
      </div>
      <button
        type="button"
        onClick={onCaptions}
        className="flex w-full items-center gap-3 rounded-2xl border border-accent/40 bg-accent-soft/40 p-3 text-left text-sm transition hover:border-accent"
      >
        <Subtitles className="size-5 shrink-0 text-accent" />
        <span className="min-w-0 flex-1">
          <span className="block font-medium">{job.source.captions ? "Bring your captions back" : "Add captions"}</span>
          <span className="block text-muted">
            {job.source.captions
              ? `Your edited captions go onto the ${previewAspect} video, no need to redo them.`
              : "AI captions with word highlights and emojis on your vertical video. Urdu, Hindi, Arabic & more."}
          </span>
        </span>
        <ArrowRight className="size-4 shrink-0 text-accent" />
      </button>
    </div>
  );
}
