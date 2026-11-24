/** Client for the Captions API (backend/app/captions/api.py). */

import { ApiError } from "./api";
import type { CStyle, CTranscript } from "./captionsCore";
import type { MediaInfo } from "./reframe";

export type CLang = { code: string; name: string; native: string; script: string; rtl: boolean; popular: boolean };
export type CFont = { key: string; label: string; family: string; kind: "display" | "script"; scripts: string[]; url: string };
export type Preset = { id: string; label: string; style: CStyle };

export type CConfig = {
  languages: CLang[];
  translate_targets: CLang[];
  presets: Preset[];
  fonts: CFont[];
  script_fonts: Record<string, string>;
  features: { ai: boolean; stt: "groq" | "local"; translate_any: boolean };
  max_duration_sec: number;
  max_upload_mb: number;
  allow_links: boolean;
  ttl_hours: number;
  watermark: string;
  daily_limit: number;
};

export type CJobState = "queued" | "importing" | "transcribing" | "processing" | "rendering" | "ready" | "error" | "cancelled";
export const ACTIVE: CJobState[] = ["queued", "importing", "transcribing", "processing", "rendering"];

export type CJob = {
  id: string;
  state: CJobState;
  task: string | null;
  stage: string;
  progress: number;
  eta: number | null;
  queue_position: number | null;
  error: string | null;
  title: string;
  language: string;
  detected_language: string | null;
  rtl: boolean;
  source: { type: "upload" | "link" | "reframe"; url: string };
  info: MediaInfo | null;
  provider: string | null;
  hooks: string[];
  transcript_rev: number | null;
  has_logo: boolean;
  output: { url: string; size: number; name: string; duration: number; version: number } | null;
  files: { srt: string; vtt: string; txt: string } | null;
  transcript?: CTranscript;
};

export type Mode = "original" | "translation" | "dual";

export type Extras = {
  hook: string;
  hook_seconds: number;
  hook_y: number;
  hook_color: string;
  hook_bg: string;
  progress_bar: "none" | "top" | "bottom";
  progress_color: string;
  watermark: boolean;
  mode: Mode;
  quality: "1080p" | "720p";
  remove_fillers: boolean;
  remove_silences: boolean;
  logo: { corner: "tl" | "tr" | "bl" | "br"; scale: number; opacity: number } | null;
};

export const DEFAULT_EXTRAS: Extras = {
  hook: "",
  hook_seconds: 4,
  hook_y: 0.12,
  hook_color: "#FFFFFF",
  hook_bg: "#FF4F1F",
  progress_bar: "none",
  progress_color: "#FF4F1F",
  watermark: true,
  mode: "original",
  quality: "1080p",
  remove_fillers: false,
  remove_silences: false,
  logo: null,
};

export type CSource =
  | { type: "upload"; id: string }
  | { type: "link"; token: string; index: number }
  | { type: "reframe"; id: string; aspect: string };

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { cache: "no-store", ...init }).catch(() => {
    throw new ApiError("Can't reach the server. Check your connection and try again.");
  });
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const d = body?.detail;
    throw new ApiError(
      typeof d === "string" ? d : res.status === 429 ? "Too many requests. Please wait a minute." : "Something went wrong. Please try again.",
    );
  }
  return body as T;
}

const json = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});

let configPromise: Promise<CConfig> | null = null;
export function getCaptionConfig(): Promise<CConfig> {
  configPromise ??= call<CConfig>("/api/captions/config").catch((e) => {
    configPromise = null;
    throw e;
  });
  return configPromise;
}

export function createCaptionJob(body: {
  source: CSource;
  language: string;
  prompt?: string;
  subtitles?: string;
  reuse?: string;
  title?: string;
}): Promise<CJob> {
  return call<CJob>("/api/captions/jobs", json("POST", body));
}

export const getCaptionJob = (id: string, sinceRev?: number | null) =>
  call<CJob>(`/api/captions/jobs/${id}${sinceRev != null ? `?since_rev=${sinceRev}` : ""}`);

const transcriptBody = (t: CTranscript) => ({
  rev: t.rev,
  translation_lang: t.translation_lang,
  lines: t.lines.map((l) => ({ id: l.id, translation: l.translation ?? null, words: l.words })),
});

export const saveTranscript = (id: string, t: CTranscript) => call<CJob>(`/api/captions/jobs/${id}/transcript`, json("PUT", transcriptBody(t)));
export const translateJob = (id: string, target: string) => call<CJob>(`/api/captions/jobs/${id}/translate`, json("POST", { target }));
export const romanizeJob = (id: string) => call<CJob>(`/api/captions/jobs/${id}/romanize`, { method: "POST" });
export const enhanceJob = (id: string, opts: { keywords: boolean; emojis: boolean; hooks: boolean; ai: boolean }) =>
  call<CJob>(`/api/captions/jobs/${id}/enhance`, json("POST", opts));

export function renderJob(id: string, style: CStyle, x: Extras, transcript: CTranscript | null): Promise<CJob> {
  return call<CJob>(
    `/api/captions/jobs/${id}/render`,
    json("POST", {
      style,
      mode: x.mode,
      quality: x.quality,
      hook: x.hook.trim() || null,
      hook_seconds: x.hook_seconds,
      hook_y: x.hook_y,
      hook_color: x.hook_color,
      hook_bg: x.hook_bg,
      progress_bar: x.progress_bar,
      progress_color: x.progress_color,
      watermark: x.watermark,
      remove_fillers: x.remove_fillers,
      remove_silences: x.remove_silences,
      logo: x.logo,
      transcript: transcript ? transcriptBody(transcript) : null,
    }),
  );
}

export async function uploadLogo(id: string, file: File): Promise<CJob> {
  return call<CJob>(`/api/captions/jobs/${id}/logo`, { method: "PUT", body: file, headers: { "content-type": file.type || "image/png" } });
}
export const deleteLogo = (id: string) => call<CJob>(`/api/captions/jobs/${id}/logo`, { method: "DELETE" });
export const cancelCaptionJob = (id: string, remove = false) =>
  call<CJob | { ok: true }>(`/api/captions/jobs/${id}${remove ? "?remove=true" : ""}`, { method: "DELETE" });

/* ------------------------------------------------------------------ fonts */

// Unicode ranges per writing system, so the browser downloads a script font only when that script is shown.
const RANGES: Record<string, string> = {
  urdu: "U+0600-06FF, U+0750-077F, U+08A0-08FF, U+FB50-FDFF, U+FE70-FEFF",
  arabic: "U+0600-06FF, U+0750-077F, U+08A0-08FF, U+FB50-FDFF, U+FE70-FEFF",
  devanagari: "U+0900-097F, U+A8E0-A8FF, U+1CD0-1CFF",
  bengali: "U+0980-09FF",
  gurmukhi: "U+0A00-0A7F",
  gujarati: "U+0A80-0AFF",
  tamil: "U+0B80-0BFF",
  telugu: "U+0C00-0C7F",
  kannada: "U+0C80-0CFF",
  malayalam: "U+0D00-0D7F",
  sinhala: "U+0D80-0DFF",
  thai: "U+0E00-0E7F",
  hebrew: "U+0590-05FF, U+FB1D-FB4F",
  korean: "U+1100-11FF, U+3130-318F, U+AC00-D7AF",
  japanese: "U+3000-30FF, U+4E00-9FFF, U+FF00-FFEF",
  cjk: "U+3000-303F, U+3400-4DBF, U+4E00-9FFF, U+F900-FAFF, U+FF00-FFEF",
  emoji: "U+00A9, U+00AE, U+2000-2BFF, U+3030, U+303D, U+1F000-1FAFF, U+FE0F",
};

export const cssFamily = (key: string) => `kly-${key}`;

let fontsInjected = false;
export function ensureFonts(cfg: CConfig) {
  if (fontsInjected || typeof document === "undefined") return;
  fontsInjected = true;
  const css = cfg.fonts
    .map((f) => {
      const range = f.kind === "script" ? RANGES[f.scripts[0]] : undefined;
      return `@font-face{font-family:"${cssFamily(f.key)}";src:url("${f.url}") format("truetype");font-display:swap;${range ? `unicode-range:${range};` : ""}}`;
    })
    .join("\n");
  const el = document.createElement("style");
  el.dataset.klyFonts = "1";
  el.textContent = css;
  document.head.appendChild(el);
}

/** CSS font stack for captions: the chosen display font first, then the script fonts (Nastaliq before
 * Naskh for Urdu), then the emoji font — the same choice the backend makes per word. */
export function fontStack(cfg: CConfig | null, displayKey: string, lang: string): string {
  if (!cfg) return "system-ui, sans-serif";
  const keys = [displayKey];
  const urdu = lang.split("-")[0] === "ur" && !lang.endsWith("-Latn");
  const scripts = cfg.fonts.filter((f) => f.kind === "script" && f.key !== "emoji").map((f) => f.key);
  if (urdu) keys.push("nastaliq");
  keys.push(...scripts.filter((k) => !(urdu && k === "nastaliq")));
  keys.push("notosans", "emoji");
  return [...new Set(keys)].map((k) => `"${cssFamily(k)}"`).join(", ") + ", sans-serif";
}

/* --------------------------------------------------------------- handoffs */

export const CAPTIONS_HANDOFF_KEY = "klyprima:captions-source";
export const CAPTIONS_JOB_KEY = "klyprima:captions-job";
export const CAPTIONS_STYLE_KEY = "klyprima:captions-style";
export const CAPTIONS_BRAND_KEY = "klyprima:captions-brand";

export type CaptionsHandoff =
  | { kind: "link"; token: string; index: number; title: string; thumbnail: string | null; duration: number | null; width: number | null; height: number | null }
  | { kind: "reframe"; job: string; aspect: string; title: string; reuse: string | null };

export function readLocal<T>(key: string): T | null {
  try {
    const v = localStorage.getItem(key);
    return v ? (JSON.parse(v) as T) : null;
  } catch {
    return null;
  }
}

export function writeLocal(key: string, value: unknown) {
  try {
    if (value === null) localStorage.removeItem(key);
    else localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* storage full or blocked: ignore */
  }
}
