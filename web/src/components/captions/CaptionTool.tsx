"use client";

import clsx from "clsx";
import {
  ArrowRight,
  Captions,
  Check,
  CircleAlert,
  CloudUpload,
  Copy,
  Crop,
  Download,
  FileText,
  FileVideo,
  Link2,
  LoaderCircle,
  Palette,
  RefreshCw,
  Rocket,
  Share2,
  Sparkles,
  X,
} from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { ApiError, formatBytes, formatDuration, resolveUrl, type Resolved } from "@/lib/api";
import {
  ACTIVE,
  CAPTIONS_HANDOFF_KEY,
  CAPTIONS_JOB_KEY,
  CAPTIONS_STYLE_KEY,
  type CConfig,
  type CJob,
  type CSource,
  type CaptionsHandoff,
  DEFAULT_EXTRAS,
  type Extras,
  cancelCaptionJob,
  createCaptionJob,
  deleteLogo,
  enhanceJob,
  ensureFonts,
  getCaptionConfig,
  getCaptionJob,
  readLocal,
  renderJob,
  romanizeJob,
  saveTranscript,
  translateJob,
  uploadLogo,
  writeLocal,
} from "@/lib/captions";
import { type CStyle, type CTranscript, lineIndexAt, wordCount } from "@/lib/captionsCore";
import type { CaptionPreset } from "@/lib/captionTools";
import { extractUrl } from "@/lib/platforms";
import {
  CAPTIONS_REFRAME_KEY,
  type CaptionsReframeHandoff,
  type MediaInfo,
  formatEta,
  readSession,
  uploadFile,
  writeSession,
} from "@/lib/reframe";
import { REFRAME_SLUG } from "@/lib/tools";
import { BoostPanel } from "./BoostPanel";
import { CaptionPreview, type PreviewHandle } from "./CaptionPreview";
import { StylePanel } from "./StylePanel";
import { TranscriptEditor } from "./TranscriptEditor";
import { Segmented } from "./ui";

type FileSrc = { kind: "file"; file: File; url: string; progress: number; uploadId: string | null; info: MediaInfo | null; error: string | null };
type LinkSrc = { kind: "link"; token: string; index: number; title: string; thumbnail: string | null; duration: number | null };
/** A Reframe result, or (with `clip`) one clip of an AI Clips project: both arrive with their words. */
type ReframeSrc = { kind: "reframe"; job: string; aspect: string; title: string; reuse: string | null; clip?: string };
type Src = FileSrc | LinkSrc | ReframeSrc | null;
type Tab = "captions" | "style" | "boost";

const FALLBACK_STYLE: CStyle = {
  preset: "bold-pop", font: "montserrat", size: 62, uppercase: true, color: "#FFFFFF", highlight: "#FFE14D", highlight_mode: "scale",
  keyword_color: "#3DDC84", outline_color: "#000000", outline: 6, shadow: 3, box: false, box_color: "#000000", box_opacity: 0.75,
  y: 0.7, max_words: 3, max_chars: 18, animation: "pop", spacing: 0, emoji: true, keywords: true, translation_color: "#FFE14D",
  translation_scale: 0.72,
};

export function CaptionTool({ preset }: { preset?: CaptionPreset }) {
  const router = useRouter();
  const [config, setConfig] = useState<CConfig | null>(null);
  const [source, setSource] = useState<Src>(null);
  const [language, setLanguage] = useState(preset?.language ?? "auto");
  const [prompt, setPrompt] = useState("");
  const [subtitles, setSubtitles] = useState<{ name: string; text: string } | null>(null);
  const [job, setJob] = useState<CJob | null>(null);
  const [transcript, setTranscript] = useState<CTranscript | null>(null);
  const [past, setPast] = useState<CTranscript[]>([]);
  const [future, setFuture] = useState<CTranscript[]>([]);
  const [dirty, setDirty] = useState(false);
  const [style, setStyleState] = useState<CStyle>(FALLBACK_STYLE);
  const [extras, setExtras] = useState<Extras>(DEFAULT_EXTRAS);
  const [tab, setTab] = useState<Tab>("captions");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [time, setTime] = useState(0);
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [showResult, setShowResult] = useState(false);
  const preview = useRef<PreviewHandle | null>(null);
  const uploadAbort = useRef<AbortController | null>(null);
  const editSeq = useRef(0);
  const saving = useRef<Promise<void> | null>(null);
  const root = useRef<HTMLDivElement>(null);

  const setStyle = useCallback((s: CStyle) => {
    setStyleState(s);
    writeLocal(CAPTIONS_STYLE_KEY, s);
  }, []);

  // Config, fonts and the starting style (last used, else the page's preset).
  useEffect(() => {
    getCaptionConfig()
      .then((cfg) => {
        setConfig(cfg);
        ensureFonts(cfg);
        const saved = readLocal<CStyle>(CAPTIONS_STYLE_KEY);
        const fromPreset = cfg.presets.find((p) => p.id === (preset?.style ?? "bold-pop"))?.style;
        if (preset?.style && fromPreset) setStyleState(fromPreset);
        else if (saved && cfg.fonts.some((f) => f.key === saved.font))
          setStyleState({ ...FALLBACK_STYLE, ...saved, size: Math.min(120, Math.max(14, saved.size ?? FALLBACK_STYLE.size)) });
        else if (fromPreset) setStyleState(fromPreset);
      })
      .catch(() => setError("Can't reach the server. Please reload the page."));
  }, [preset?.style]);

  const applyJob = useCallback((j: CJob, opts?: { force?: boolean }) => {
    setJob(j);
    if (j.transcript) {
      const incoming = j.transcript;
      setTranscript((cur) => {
        if (!cur || opts?.force) return incoming;
        if (incoming.rev === cur.rev) return cur;
        // The server changed the captions (an AI action): keep the old version for Undo.
        setPast((p) => [...p.slice(-49), cur]);
        setFuture([]);
        return incoming;
      });
      if (opts?.force) setDirty(false);
    }
  }, []);

  // Hand-offs from the downloader / Reframe, or resume a project after a reload.
  useEffect(() => {
    const from = new URLSearchParams(window.location.search).get("from");
    const handoff = readSession<CaptionsHandoff>(CAPTIONS_HANDOFF_KEY);
    if (handoff && (from === "link" || from === "reframe" || from === "clip")) {
      writeSession(CAPTIONS_HANDOFF_KEY, null);
      // Next keeps visited pages alive: drop the previous project before starting this one.
      setJob(null);
      setTranscript(null);
      setPast([]);
      setFuture([]);
      setDirty(false);
      setSubtitles(null);
      setShowResult(false);
      setTab("captions");
      writeSession(CAPTIONS_JOB_KEY, null);
      if (handoff.kind === "link") {
        setSource({ kind: "link", token: handoff.token, index: handoff.index, title: handoff.title, thumbnail: handoff.thumbnail, duration: handoff.duration });
      } else if (handoff.kind === "clip") {
        const src: ReframeSrc = { kind: "reframe", job: handoff.job, aspect: handoff.aspect, title: handoff.title, reuse: null, clip: handoff.clip };
        setSource(src);
        void start(src, "auto");
      } else {
        const src: ReframeSrc = { kind: "reframe", job: handoff.job, aspect: handoff.aspect, title: handoff.title, reuse: handoff.reuse };
        setSource(src);
        if (handoff.reuse) void start(src, "auto");
      }
      return;
    }
    const saved = readSession<string>(CAPTIONS_JOB_KEY);
    if (saved) {
      getCaptionJob(saved)
        .then((j) => applyJob(j, { force: true }))
        .catch(() => writeSession(CAPTIONS_JOB_KEY, null));
    }
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Poll while the server works.
  const active = job ? ACTIVE.includes(job.state) : false;
  useEffect(() => {
    if (!job || !active) return;
    let stop = false;
    const id = setInterval(async () => {
      try {
        const j = await getCaptionJob(job.id, transcript?.rev ?? null);
        if (!stop) applyJob(j);
      } catch (e) {
        if (!stop && e instanceof ApiError && /expired/i.test(e.message)) {
          setJob(null);
          setError(e.message);
          writeSession(CAPTIONS_JOB_KEY, null);
        }
      }
    }, 900);
    return () => {
      stop = true;
      clearInterval(id);
    };
  }, [job?.id, active, transcript?.rev, applyJob]); // eslint-disable-line react-hooks/exhaustive-deps

  /* ---------------------------------------------------------------- editing */

  const edit = useCallback((next: CTranscript) => {
    setTranscript((cur) => {
      if (cur) setPast((p) => [...p.slice(-49), cur]);
      return next;
    });
    setFuture([]);
    setDirty(true);
    editSeq.current += 1;
  }, []);

  const undo = useCallback(() => {
    setPast((p) => {
      if (!p.length || !transcript) return p;
      const prev = p[p.length - 1];
      setFuture((f) => [transcript, ...f].slice(0, 50));
      setTranscript({ ...prev, rev: transcript.rev });
      setDirty(true);
      editSeq.current += 1;
      return p.slice(0, -1);
    });
  }, [transcript]);

  const redo = useCallback(() => {
    setFuture((f) => {
      if (!f.length || !transcript) return f;
      const [next, ...rest] = f;
      setPast((p) => [...p, transcript]);
      setTranscript({ ...next, rev: transcript.rev });
      setDirty(true);
      editSeq.current += 1;
      return rest;
    });
  }, [transcript]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = document.activeElement;
      if (el && (el.tagName === "TEXTAREA" || el.tagName === "INPUT")) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && !e.shiftKey) {
        e.preventDefault();
        undo();
      } else if ((e.ctrlKey || e.metaKey) && (e.key.toLowerCase() === "y" || (e.key.toLowerCase() === "z" && e.shiftKey))) {
        e.preventDefault();
        redo();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [undo, redo]);

  const flush = useCallback(async () => {
    if (saving.current) await saving.current;
    if (!job || !transcript || !dirty) return;
    const seq = editSeq.current;
    const p = saveTranscript(job.id, transcript)
      .then((j) => {
        setJob(j);
        if (j.transcript) {
          if (editSeq.current === seq) {
            setTranscript(j.transcript);
            setDirty(false);
          } else {
            const rev = j.transcript.rev;
            setTranscript((cur) => (cur ? { ...cur, rev } : cur));
          }
        }
      })
      .catch((e) => {
        setError(e instanceof ApiError ? e.message : "Couldn't save your changes.");
        throw e;
      })
      .finally(() => {
        saving.current = null;
      });
    saving.current = p;
    await p;
  }, [job, transcript, dirty]);

  // Autosave edits a moment after typing stops.
  useEffect(() => {
    if (!dirty || !job || job.state !== "ready") return;
    const id = setTimeout(() => void flush().catch(() => undefined), 1200);
    return () => clearTimeout(id);
  }, [dirty, transcript, job, flush]);

  /* ------------------------------------------------------------------ source */

  const startUpload = useCallback(
    (file: File) => {
      uploadAbort.current?.abort();
      setError(null);
      const max = (config?.max_upload_mb ?? 1024) * 1024 * 1024;
      if (file.size > max) return setError(`This file is ${formatBytes(file.size)}. The limit is ${config?.max_upload_mb ?? 1024} MB.`);
      if (file.type && !file.type.startsWith("video/") && !file.type.startsWith("audio/") && !/\.(mkv|mov|mp4|webm|m4v|avi|3gp|mp3|m4a|wav)$/i.test(file.name)) {
        return setError("Please choose a video file (MP4, MOV, WebM, MKV).");
      }
      const url = URL.createObjectURL(file);
      const ctrl = new AbortController();
      uploadAbort.current = ctrl;
      setSource({ kind: "file", file, url, progress: 0, uploadId: null, info: null, error: null });
      uploadFile(file, (p) => setSource((c) => (c?.kind === "file" && c.file === file ? { ...c, progress: p } : c)), ctrl.signal)
        .then((res) => setSource((c) => (c?.kind === "file" && c.file === file ? { ...c, uploadId: res.id, info: res.info, progress: 1 } : c)))
        .catch((e) => {
          if ((e as Error)?.name === "AbortError") return;
          setSource((c) => (c?.kind === "file" && c.file === file ? { ...c, error: e instanceof ApiError ? e.message : "Upload failed. Please try again." } : c));
        });
    },
    [config],
  );

  async function start(src: Src = source, lang: string = language) {
    if (!src) return;
    let s: CSource;
    let title: string | undefined;
    if (src.kind === "file") {
      if (!src.uploadId) return;
      s = { type: "upload", id: src.uploadId };
      title = src.file.name;
    } else if (src.kind === "link") {
      s = { type: "link", token: src.token, index: src.index };
      title = src.title;
    } else {
      s = src.clip ? { type: "clip", id: src.job, clip: src.clip } : { type: "reframe", id: src.job, aspect: src.aspect };
      title = src.title;
    }
    setSubmitting(true);
    setError(null);
    try {
      const j = await createCaptionJob({
        source: s,
        language: lang,
        prompt: prompt.trim() || undefined,
        subtitles: src.kind === "reframe" ? undefined : subtitles?.text,
        reuse: src.kind === "reframe" ? (src.reuse ?? undefined) : undefined,
        title,
      });
      setTranscript(null);
      setPast([]);
      setFuture([]);
      setDirty(false);
      setShowResult(false);
      setTab("captions");
      applyJob(j, { force: true });
      writeSession(CAPTIONS_JOB_KEY, j.id);
      root.current?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  function reset() {
    uploadAbort.current?.abort();
    if (source?.kind === "file") URL.revokeObjectURL(source.url);
    if (logoUrl) URL.revokeObjectURL(logoUrl);
    setSource(null);
    setJob(null);
    setTranscript(null);
    setPast([]);
    setFuture([]);
    setDirty(false);
    setError(null);
    setSubtitles(null);
    setLogoUrl(null);
    setExtras(DEFAULT_EXTRAS);
    setShowResult(false);
    writeSession(CAPTIONS_JOB_KEY, null);
  }

  /* ----------------------------------------------------------------- actions */

  async function act(fn: () => Promise<CJob>) {
    if (!job) return;
    setError(null);
    try {
      await flush();
      applyJob(await fn());
    } catch (e) {
      setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
    }
  }

  async function exportVideo() {
    if (!job) return;
    setShowResult(false);
    await act(() => renderJob(job.id, style, { ...extras, logo: job.has_logo ? extras.logo : null }, null));
  }

  async function cancel() {
    if (!job) return;
    try {
      const j = await cancelCaptionJob(job.id);
      if ("id" in j) applyJob(j);
    } catch {
      /* the next poll shows the real state */
    }
  }

  useEffect(() => {
    if (job?.output && job.state === "ready" && job.task === null) setShowResult(true);
  }, [job?.output?.version]); // eslint-disable-line react-hooks/exhaustive-deps

  /* ------------------------------------------------------------------ render */

  const info: MediaInfo | null = job?.info ?? (source?.kind === "file" ? source.info : null);
  const videoUrl = source?.kind === "file" ? source.url : (job?.source.url ?? null);
  const duration = info?.duration ?? null;
  const currentLine = useMemo(() => (transcript ? lineIndexAt(transcript, time) : -1), [transcript, time]);
  const ready = !!transcript && !!job;
  const working = job ? ACTIVE.includes(job.state) : false;
  const busy = working ? job!.task : null;
  const onTime = useCallback((t: number) => setTime(t), []);

  return (
    <div ref={root} className="scroll-mt-24">
      {error && (
        <p role="alert" className="mb-4 flex items-start gap-2 rounded-xl bg-danger/10 p-3 text-sm text-danger">
          <CircleAlert className="mt-0.5 size-4 shrink-0" /> <span className="flex-1">{error}</span>
          <button type="button" aria-label="Dismiss" onClick={() => setError(null)}>
            <X className="size-4" />
          </button>
        </p>
      )}

      {!ready && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px] lg:items-start">
          <div className="min-w-0 space-y-5 rounded-3xl border border-line bg-elev p-4 shadow-card sm:p-6">
            {!job && !source && <SourcePicker config={config} onFile={startUpload} onLink={(l) => setSource(l)} />}
            {(source || job) && <SourceCard source={source} job={job} onClear={reset} />}
            {!job && source && (
              <Setup
                config={config}
                language={language}
                setLanguage={setLanguage}
                prompt={prompt}
                setPrompt={setPrompt}
                subtitles={subtitles}
                setSubtitles={setSubtitles}
                srtFirst={!!preset?.srt}
              />
            )}
            {!job && source && (
              <>
                <button
                  type="button"
                  onClick={() => start()}
                  disabled={submitting || (source.kind === "file" && !source.uploadId)}
                  className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-accent px-6 py-3.5 text-base font-semibold text-accent-fg shadow-[0_10px_30px_-10px_var(--accent)] transition hover:-translate-y-px hover:brightness-105 disabled:translate-y-0 disabled:opacity-60"
                >
                  {submitting || (source.kind === "file" && !source.uploadId && !source.error) ? (
                    <LoaderCircle className="size-5 animate-spin" />
                  ) : (
                    <Sparkles className="size-5" />
                  )}
                  {source.kind === "file" && !source.uploadId
                    ? source.error
                      ? "Upload failed"
                      : `Uploading… ${Math.round(source.progress * 100)}%`
                    : subtitles
                      ? "Use my subtitles"
                      : "Generate captions"}
                </button>
                <p className="text-center text-xs text-subtle">
                  Only caption videos you own or have permission to use. Files are deleted automatically within {config?.ttl_hours ?? 24} hours.
                </p>
              </>
            )}
            {job && working && <Progress job={job} onCancel={cancel} />}
            {job && !working && !transcript && (
              <div className="space-y-3">
                <p className="flex items-start gap-2 rounded-xl bg-danger/10 p-3 text-sm text-danger">
                  <CircleAlert className="mt-0.5 size-4 shrink-0" /> {job.state === "cancelled" ? "Cancelled." : job.error}
                </p>
                <div className="flex flex-wrap gap-2">
                  {source && (
                    <button type="button" onClick={() => (setJob(null), writeSession(CAPTIONS_JOB_KEY, null))} className="inline-flex items-center gap-1.5 rounded-full bg-fg px-4 py-2 text-sm font-medium text-bg">
                      <RefreshCw className="size-4" /> Try again
                    </button>
                  )}
                  <button type="button" onClick={reset} className="rounded-full border border-line-strong px-4 py-2 text-sm font-medium">
                    Use another video
                  </button>
                </div>
              </div>
            )}
          </div>
          <aside className={clsx("lg:sticky lg:top-24", !videoUrl && "hidden lg:block")}>
            {source?.kind === "link" && !videoUrl && source.thumbnail ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={source.thumbnail} alt="" className="mx-auto max-h-[60vh] rounded-2xl object-contain shadow-card" />
            ) : (
              <CaptionPreview
                src={videoUrl}
                width={info?.width ?? 9}
                height={info?.height ?? 16}
                duration={duration}
                transcript={null}
                style={style}
                extras={extras}
                config={config}
                rtl={false}
                logoUrl={null}
              />
            )}
          </aside>
        </div>
      )}

      {ready && transcript && job && (
        <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(300px,400px)] lg:items-start">
          <div className="order-2 min-w-0 rounded-3xl border border-line bg-elev p-4 shadow-card sm:p-5 lg:order-1">
            <div className="mb-4 flex flex-wrap items-center gap-3">
              <div className="min-w-0 flex-1">
                <p className="truncate font-semibold">{job.title}</p>
                <p className="text-xs text-muted">
                  {[
                    config?.languages.find((l) => l.code === transcript.language)?.name ?? transcript.language,
                    `${wordCount(transcript)} words`,
                    duration ? formatDuration(duration) : null,
                    dirty ? "Saving…" : "Saved",
                  ]
                    .filter(Boolean)
                    .join(" · ")}
                </p>
              </div>
              <button type="button" onClick={reset} className="text-sm text-muted transition hover:text-fg">
                New video
              </button>
            </div>
            <div role="tablist" className="mb-5 flex gap-1 rounded-xl bg-line/60 p-1">
              {(
                [
                  ["captions", "Captions", Captions],
                  ["style", "Style", Palette],
                  ["boost", "Boost", Rocket],
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
            {job.error && job.state === "ready" && (
              <p className="mb-4 flex items-start gap-2 rounded-xl bg-danger/10 p-3 text-sm text-danger">
                <CircleAlert className="mt-0.5 size-4 shrink-0" /> {job.error}
              </p>
            )}
            {working && job.task !== "render" && (
              <div className="mb-4">
                <Progress job={job} onCancel={cancel} compact />
              </div>
            )}
            {tab === "captions" && (
              <TranscriptEditor
                transcript={transcript}
                onChange={edit}
                current={currentLine}
                onSeek={(t) => {
                  setShowResult(false);
                  setTimeout(() => {
                    preview.current?.seek(t);
                    preview.current?.play();
                  }, 0);
                }}
                rtl={job.rtl && !transcript.language.endsWith("-Latn")}
                duration={duration}
                canUndo={past.length > 0}
                canRedo={future.length > 0}
                onUndo={undo}
                onRedo={redo}
                disabled={working}
              />
            )}
            {tab === "style" && <StylePanel style={style} setStyle={setStyle} config={config} />}
            {tab === "boost" && (
              <BoostPanel
                job={job}
                config={config}
                transcript={transcript}
                extras={extras}
                setExtras={setExtras}
                busy={busy}
                onEnhance={() => act(() => enhanceJob(job.id, { keywords: true, emojis: true, hooks: true, ai: true }))}
                onTranslate={(target) =>
                  act(async () => {
                    const j = await translateJob(job.id, target);
                    setExtras((x) => ({ ...x, mode: x.mode === "original" ? "dual" : x.mode }));
                    return j;
                  })
                }
                onRomanize={() => act(() => romanizeJob(job.id))}
                onLogo={(f) =>
                  act(async () => {
                    const j = await uploadLogo(job.id, f);
                    if (logoUrl) URL.revokeObjectURL(logoUrl);
                    setLogoUrl(URL.createObjectURL(f));
                    setExtras((x) => ({ ...x, logo: x.logo ?? { corner: "tr", scale: 0.16, opacity: 0.9 } }));
                    return j;
                  })
                }
                onLogoRemove={() =>
                  act(async () => {
                    const j = await deleteLogo(job.id);
                    setExtras((x) => ({ ...x, logo: null }));
                    return j;
                  })
                }
              />
            )}
          </div>

          <aside className="order-1 space-y-4 lg:sticky lg:top-24 lg:order-2">
            {job.output && (
              <Segmented
                label="Preview"
                value={showResult ? "result" : "live"}
                onChange={(v) => setShowResult(v === "result")}
                options={[
                  { id: "live", label: "Live preview" },
                  { id: "result", label: "Exported video" },
                ]}
              />
            )}
            <CaptionPreview
              src={videoUrl}
              width={info?.width ?? 9}
              height={info?.height ?? 16}
              duration={duration}
              transcript={transcript}
              style={style}
              extras={extras}
              config={config}
              rtl={job.rtl}
              logoUrl={job.has_logo ? logoUrl : null}
              handle={preview}
              onTime={onTime}
              result={showResult && job.output ? `${job.output.url}&inline=1` : null}
            />
            <ExportPanel
              job={job}
              extras={extras}
              setExtras={setExtras}
              translated={!!transcript.translation_lang}
              onExport={exportVideo}
              onCancel={cancel}
              onVertical={() => {
                const h: CaptionsReframeHandoff = { captions: job.id, title: job.title, duration, width: info?.width ?? null, height: info?.height ?? null };
                writeSession(CAPTIONS_REFRAME_KEY, h);
                router.push(`/${REFRAME_SLUG}?from=captions`);
              }}
              text={transcript.lines.map((l) => l.text).join("\n")}
            />
          </aside>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ source */

function SourcePicker({ config, onFile, onLink }: { config: CConfig | null; onFile: (f: File) => void; onLink: (l: LinkSrc) => void }) {
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
            <Captions className="size-7" />
          </span>
          <span className="text-lg font-semibold">Drop your video here</span>
          <span className="text-sm text-muted">
            or <span className="font-medium text-accent underline underline-offset-2">choose a file</span> · MP4, MOV, WebM, MKV · up to {config?.max_upload_mb ?? 1024} MB ·{" "}
            {Math.round((config?.max_duration_sec ?? 3600) / 60)} min
          </span>
          <input
            type="file"
            accept="video/*,audio/*,.mkv,.mov,.m4v"
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

function LinkInput({ onLink }: { onLink: (l: LinkSrc) => void }) {
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [choices, setChoices] = useState<Resolved | null>(null);
  const pick = (r: Resolved, index: number) => {
    const it = r.items[index];
    onLink({ kind: "link", token: r.token, index, title: it.title || r.title, thumbnail: it.thumbnail, duration: it.duration });
  };
  async function go(e: React.FormEvent) {
    e.preventDefault();
    const url = extractUrl(value) ?? value.trim();
    if (!url) return;
    setBusy(true);
    setErr(null);
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
        <input value={value} onChange={(e) => setValue(e.target.value)} placeholder="Paste a TikTok, Instagram, Facebook, X or YouTube link" inputMode="url" aria-label="Video link" className="min-w-0 flex-1 bg-transparent px-3 py-2.5 text-sm outline-none" />
        <button type="submit" disabled={busy || !value.trim()} className="inline-flex items-center gap-1.5 rounded-xl bg-fg px-4 text-sm font-medium text-bg disabled:opacity-50">
          {busy ? <LoaderCircle className="size-4 animate-spin" /> : <ArrowRight className="size-4" />} Use
        </button>
      </form>
      {err && <p className="text-sm text-danger">{err}</p>}
      {choices && (
        <div className="flex gap-2 overflow-x-auto pb-1">
          {choices.items
            .filter((it) => !it.error)
            .map((it) => (
              <button key={it.index} type="button" onClick={() => pick(choices, it.index)} className="relative h-24 w-16 shrink-0 overflow-hidden rounded-lg border-2 border-transparent bg-line hover:border-accent">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                {it.thumbnail && <img src={it.thumbnail} alt="" className="size-full object-cover" />}
              </button>
            ))}
        </div>
      )}
      <p className="text-xs text-subtle">Only use videos you own or have permission to repost.</p>
    </div>
  );
}

function SourceCard({ source, job, onClear }: { source: Src; job: CJob | null; onClear: () => void }) {
  const title = source?.kind === "file" ? source.file.name : source ? source.title : (job?.title ?? "Video");
  const info = source?.kind === "file" ? source.info : (job?.info ?? null);
  const uploading = source?.kind === "file" && !source.uploadId && !source.error;
  return (
    <div className="flex items-center gap-3 rounded-2xl border border-line bg-bg p-3">
      <span className="grid size-11 shrink-0 place-items-center overflow-hidden rounded-xl bg-accent-soft text-accent">
        {source?.kind === "link" && source.thumbnail ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={source.thumbnail} alt="" className="size-full object-cover" />
        ) : source?.kind === "link" ? (
          <Link2 className="size-5" />
        ) : source?.kind === "reframe" ? (
          <Crop className="size-5" />
        ) : (
          <FileVideo className="size-5" />
        )}
      </span>
      <div className="min-w-0 flex-1">
        <p className="truncate font-medium">{title}</p>
        <p className="truncate text-xs text-muted">
          {[info && `${info.width}×${info.height}`, info?.duration && formatDuration(info.duration), source?.kind === "file" && formatBytes(source.file.size), source?.kind === "reframe" && (source.clip ? "AI clip" : `Vertical ${source.aspect}`)]
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
  );
}

function Setup({
  config,
  language,
  setLanguage,
  prompt,
  setPrompt,
  subtitles,
  setSubtitles,
  srtFirst,
}: {
  config: CConfig | null;
  language: string;
  setLanguage: (l: string) => void;
  prompt: string;
  setPrompt: (p: string) => void;
  subtitles: { name: string; text: string } | null;
  setSubtitles: (s: { name: string; text: string } | null) => void;
  srtFirst: boolean;
}) {
  const popular = config?.languages.filter((l) => l.popular) ?? [];
  const others = config?.languages.filter((l) => !l.popular) ?? [];
  const [more, setMore] = useState(false);
  const srtInput = useRef<HTMLInputElement>(null);
  const chip = (code: string, label: string, sub?: string) => (
    <button
      key={code}
      type="button"
      onClick={() => setLanguage(code)}
      aria-pressed={language === code}
      className={clsx(
        "rounded-full border px-3 py-1.5 text-sm transition",
        language === code ? "border-accent bg-accent text-accent-fg" : "border-line-strong hover:border-fg",
      )}
    >
      {label}
      {sub && sub !== label && <span className={clsx("ml-1 text-xs", language === code ? "text-accent-fg/80" : "text-muted")}>{sub}</span>}
    </button>
  );
  return (
    <div className="space-y-5">
      <div className="space-y-2">
        <p className="text-sm font-semibold">Language spoken in the video</p>
        <div className="flex flex-wrap gap-2">
          {chip("auto", "Detect automatically")}
          {popular.map((l) => chip(l.code, l.name, l.native))}
          {!more && others.length > 0 && (
            <button type="button" onClick={() => setMore(true)} className="rounded-full border border-dashed border-line-strong px-3 py-1.5 text-sm text-muted hover:text-fg">
              +{others.length} more
            </button>
          )}
        </div>
        {more && (
          <select value={others.some((l) => l.code === language) ? language : ""} onChange={(e) => setLanguage(e.target.value)} aria-label="More languages" className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm">
            <option value="">More languages…</option>
            {others.map((l) => (
              <option key={l.code} value={l.code}>
                {l.name} · {l.native}
              </option>
            ))}
          </select>
        )}
        {(language === "ur-Latn" || language === "hi-Latn") && (
          <p className="rounded-xl bg-accent-soft/60 px-3 py-2 text-xs">
            Captions will be written in English letters, the way people type on social media (“kya haal hai”).
          </p>
        )}
      </div>
      <details className="group rounded-2xl border border-line px-4 py-3" open={srtFirst || undefined}>
        <summary className="cursor-pointer text-sm font-medium">More options</summary>
        <div className="mt-3 space-y-4">
          <label className="block space-y-1.5">
            <span className="text-sm">Names or special words in the video (optional)</span>
            <input value={prompt} onChange={(e) => setPrompt(e.target.value.slice(0, 400))} placeholder="e.g. Klyprima, Karachi, iPhone 17" className="w-full rounded-xl border border-line bg-bg px-3 py-2 text-sm outline-none focus:border-accent" />
            <span className="block text-xs text-subtle">Helps the AI spell them right.</span>
          </label>
          <div className="space-y-1.5">
            <span className="text-sm">Already have subtitles?</span>
            <div className="flex flex-wrap items-center gap-2">
              <input
                ref={srtInput}
                type="file"
                accept=".srt,.vtt,text/vtt,application/x-subrip"
                className="sr-only"
                onChange={async (e) => {
                  const f = e.target.files?.[0];
                  if (f) setSubtitles({ name: f.name, text: await f.text() });
                  e.target.value = "";
                }}
              />
              <button type="button" onClick={() => srtInput.current?.click()} className="inline-flex items-center gap-1.5 rounded-full border border-line-strong px-3.5 py-1.5 text-sm transition hover:border-fg">
                <FileText className="size-4" /> {subtitles ? subtitles.name : "Import SRT or VTT"}
              </button>
              {subtitles && (
                <button type="button" onClick={() => setSubtitles(null)} className="text-sm text-muted hover:text-fg">
                  Remove
                </button>
              )}
            </div>
            <span className="block text-xs text-subtle">Style them and burn them into the video, no AI needed.</span>
          </div>
        </div>
      </details>
    </div>
  );
}

/* --------------------------------------------------------------- progress */

const STAGES: { states: CJob["state"][]; label: string }[] = [
  { states: ["queued"], label: "In line" },
  { states: ["importing"], label: "Fetching" },
  { states: ["transcribing"], label: "Listening" },
  { states: ["processing", "rendering"], label: "Working" },
];

function Progress({ job, onCancel, compact }: { job: CJob; onCancel: () => void; compact?: boolean }) {
  const pct = Math.round(job.progress * 100);
  const steps = STAGES.filter((s) => (s.states[0] === "importing" ? job.source.type === "link" : s.states[0] === "transcribing" ? job.task === "transcribe" : s.states[0] === "processing" ? job.task !== "transcribe" : true));
  const current = steps.findIndex((s) => s.states.includes(job.state));
  return (
    <div className={clsx("space-y-3 rounded-2xl border border-line bg-bg", compact ? "p-3" : "p-4")} aria-live="polite">
      <div className="flex items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-sm font-semibold">
          <LoaderCircle className="size-4 animate-spin text-accent" />
          {job.state === "queued" && job.queue_position ? `Waiting in line (#${job.queue_position})` : job.stage}
        </p>
        <span className="font-mono text-xs text-muted">{pct}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-line">
        <div className="h-full rounded-full bg-accent transition-[width] duration-700 ease-out" style={{ width: `${Math.max(3, pct)}%` }} />
      </div>
      {!compact && (
        <ol className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
          {steps.map((s, i) => (
            <li key={s.label} className={clsx("flex items-center gap-1", i < current ? "text-ok" : i === current ? "font-medium text-fg" : "text-subtle")}>
              {i < current ? <Check className="size-3.5" /> : <span className="size-1.5 rounded-full bg-current" />} {s.label}
            </li>
          ))}
        </ol>
      )}
      <div className="flex items-center justify-between text-xs text-muted">
        <span>{formatEta(job.eta) || "You can keep this tab open and do other things."}</span>
        <button type="button" onClick={onCancel} className="rounded-full px-3 py-1 font-medium transition hover:bg-line hover:text-fg">
          Cancel
        </button>
      </div>
    </div>
  );
}

/* ----------------------------------------------------------------- export */

function ExportPanel({
  job,
  extras,
  setExtras,
  translated,
  onExport,
  onCancel,
  onVertical,
  text,
}: {
  job: CJob;
  extras: Extras;
  setExtras: (x: Extras) => void;
  translated: boolean;
  onExport: () => void;
  onCancel: () => void;
  onVertical: () => void;
  text: string;
}) {
  const rendering = job.state === "rendering" || (job.task === "render" && ACTIVE.includes(job.state));
  const working = ACTIVE.includes(job.state);
  const [canShare, setCanShare] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [copied, setCopied] = useState(false);
  const landscape = !!job.info && job.info.width > job.info.height;
  useEffect(() => {
    try {
      setCanShare(typeof navigator !== "undefined" && !!navigator.canShare?.({ files: [new File([""], "a.mp4", { type: "video/mp4" })] }));
    } catch {
      setCanShare(false);
    }
  }, []);
  const mode = translated ? extras.mode : "original";
  const q = mode !== "original" ? `?mode=${mode}` : "";

  async function share() {
    if (!job.output) return;
    setSharing(true);
    try {
      const blob = await fetch(job.output.url).then((r) => r.blob());
      await navigator.share({ files: [new File([blob], job.output.name, { type: "video/mp4" })], title: job.title });
    } catch {
      /* cancelled */
    } finally {
      setSharing(false);
    }
  }

  return (
    <div className="space-y-3 rounded-3xl border border-line bg-elev p-4 shadow-card">
      <Segmented
        label="Quality"
        value={extras.quality}
        onChange={(v) => setExtras({ ...extras, quality: v })}
        options={[
          { id: "1080p", label: "1080p HD" },
          { id: "720p", label: "720p · faster" },
        ]}
      />
      {rendering ? (
        <Progress job={job} onCancel={onCancel} compact />
      ) : (
        <button
          type="button"
          onClick={onExport}
          disabled={working}
          className="inline-flex w-full items-center justify-center gap-2 rounded-full bg-accent px-5 py-3 text-base font-semibold text-accent-fg shadow-[0_10px_30px_-10px_var(--accent)] transition hover:-translate-y-px hover:brightness-105 disabled:opacity-60"
        >
          <Sparkles className="size-5" /> {job.output ? "Export again" : "Export video"}
        </button>
      )}
      {job.output && !rendering && (
        <div className="space-y-2">
          <p className="flex items-center gap-2 rounded-xl bg-ok/10 px-3 py-2 text-sm">
            <Check className="size-4 shrink-0 text-ok" /> Your captioned video is ready ({formatBytes(job.output.size)}).
          </p>
          <div className="flex gap-2">
            <a href={job.output.url} download={job.output.name} className="inline-flex flex-1 items-center justify-center gap-1.5 rounded-full bg-fg px-4 py-2.5 text-sm font-semibold text-bg transition hover:opacity-90">
              <Download className="size-4" /> Download MP4
            </a>
            {canShare && (
              <button type="button" onClick={share} disabled={sharing} className="inline-flex items-center gap-1.5 rounded-full border border-line-strong px-4 py-2.5 text-sm font-medium">
                {sharing ? <LoaderCircle className="size-4 animate-spin" /> : <Share2 className="size-4" />} Share
              </button>
            )}
          </div>
        </div>
      )}
      {job.files && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-xs text-muted">Subtitle files:</span>
          {(["srt", "vtt", "txt"] as const).map((k) => (
            <a key={k} href={`${job.files![k]}${q}`} download className="rounded-full border border-line-strong px-3 py-1 text-xs font-semibold uppercase transition hover:border-fg">
              {k}
            </a>
          ))}
          <button
            type="button"
            onClick={() => navigator.clipboard?.writeText(text).then(() => (setCopied(true), setTimeout(() => setCopied(false), 1500)))}
            className="inline-flex items-center gap-1 rounded-full border border-line-strong px-3 py-1 text-xs font-semibold transition hover:border-fg"
          >
            {copied ? <Check className="size-3.5" /> : <Copy className="size-3.5" />} {copied ? "Copied" : "Copy text"}
          </button>
        </div>
      )}
      {landscape && (
        <button type="button" onClick={onVertical} className="flex w-full items-center gap-3 rounded-2xl border border-dashed border-accent/50 p-3 text-left text-sm transition hover:border-accent">
          <Crop className="size-5 shrink-0 text-accent" />
          <span>
            <span className="block font-medium">Make it vertical for TikTok & Reels</span>
            <span className="block text-xs text-muted">AI reframes to 9:16, then your captions come back with it.</span>
          </span>
        </button>
      )}
      <p className="text-center text-[11px] text-subtle">
        {extras.remove_fillers || extras.remove_silences ? "Filler words and pauses are cut when you export. " : ""}
        The preview is drawn by your browser; the export uses the same fonts and timing.
      </p>
    </div>
  );
}
