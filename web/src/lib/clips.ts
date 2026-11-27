/** Client for the AI Clips API (backend/app/clips/api.py). */

import { ApiError } from "./api";
import type { CStyle } from "./captionsCore";
import type { CLang, Preset } from "./captions";
import type { LengthId, Scores } from "./clipsCore";
import type { MediaInfo } from "./reframe";

export type ClipAspect = "9:16" | "1:1" | "4:5" | "original";
export type ClipLayout = "smart" | "blur" | "fit";

export type ClipLook = {
  aspect: ClipAspect;
  layout: ClipLayout;
  captions: boolean;
  style: CStyle;
  hook: boolean;
  remove_fillers: boolean;
  remove_silences: boolean;
  progress_bar: boolean;
  watermark: boolean;
  quality: "1080p" | "720p";
};

/** What the visitor picks before the AI starts (the style is a preset id here). */
export type LookIn = Omit<ClipLook, "style"> & { preset: string };

export const DEFAULT_LOOK: LookIn = {
  aspect: "9:16",
  layout: "smart",
  captions: true,
  preset: "bold-pop",
  hook: true,
  remove_fillers: false,
  remove_silences: false,
  progress_bar: false,
  watermark: false,
  quality: "1080p",
};

export type KConfig = {
  languages: CLang[];
  presets: Preset[];
  lengths: Record<LengthId, { min: number; max: number; ideal: number }>;
  max_clips: number;
  features: { ai: boolean; ai_provider: "claude" | "groq" | null; stt: string };
  max_duration_sec: number;
  max_upload_mb: number;
  allow_links: boolean;
  ttl_hours: number;
  daily_limit: number;
  watermark: string;
};

export type ClipStatus = "queued" | "rendering" | "done" | "error" | "pending";

export type Clip = {
  id: string;
  rank: number;
  start: number;
  end: number;
  duration: number;
  title: string;
  hook: string;
  description: string;
  hashtags: string[];
  score: number;
  scores: Scores;
  reason: string;
  method: "ai" | "auto";
  status: ClipStatus;
  progress: number;
  error: string | null;
  version: number;
  look: ClipLook;
  text: string;
  video: string | null;
  thumb: string | null;
  srt: string | null;
  size: number | null;
};

export type KJobState = "queued" | "importing" | "transcribing" | "finding" | "rendering" | "ready" | "error" | "cancelled";
export const ACTIVE: KJobState[] = ["queued", "importing", "transcribing", "finding", "rendering"];

export type KJob = {
  id: string;
  state: KJobState;
  task: string | null;
  stage: string;
  progress: number;
  eta: number | null;
  queue_position: number | null;
  error: string | null;
  title: string;
  source: { type: "upload" | "link"; url: string };
  info: MediaInfo | null;
  settings: { language: string; topic: string | null; length: LengthId; count: number | null; range: [number, number | null]; look: ClipLook };
  detected_language: string | null;
  provider: string | null;
  method: "ai" | "auto" | null;
  clips: Clip[];
  ready_count: number;
  zip: string | null;
  transcript: string | null;
};

export type KSource = { type: "upload"; id: string } | { type: "link"; token: string; index: number };

export type FindOptions = { length: LengthId; count: number | null; topic: string; look: LookIn };

export type ClipPatch = {
  start?: number;
  end?: number;
  title?: string;
  hook?: string;
  description?: string;
  hashtags?: string[];
  look?: Partial<ClipLook>;
  render?: boolean;
};

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

let configPromise: Promise<KConfig> | null = null;
export function getClipsConfig(): Promise<KConfig> {
  configPromise ??= call<KConfig>("/api/clips/config").catch((e) => {
    configPromise = null;
    throw e;
  });
  return configPromise;
}

function findBody(o: FindOptions) {
  return { length: o.length, count: o.count, topic: o.topic.trim() || null, look: o.look };
}

export function createClipsJob(body: {
  source: KSource;
  language: string;
  options: FindOptions;
  range_start: number;
  range_end: number | null;
  title?: string;
}): Promise<KJob> {
  return call<KJob>(
    "/api/clips/jobs",
    json("POST", { source: body.source, language: body.language, range_start: body.range_start, range_end: body.range_end, title: body.title, ...findBody(body.options) }),
  );
}

export const getClipsJob = (id: string) => call<KJob>(`/api/clips/jobs/${id}`);
export const findAgain = (id: string, o: FindOptions) => call<KJob>(`/api/clips/jobs/${id}/find`, json("POST", findBody(o)));
export const editClip = (id: string, clip: string, patch: ClipPatch) => call<KJob>(`/api/clips/jobs/${id}/clips/${clip}`, json("PATCH", patch));
export const cancelClipsJob = (id: string, remove = false) =>
  call<KJob | { ok: true }>(`/api/clips/jobs/${id}${remove ? "?remove=true" : ""}`, { method: "DELETE" });

export type KTranscript = { language: string; rtl: boolean; lines: { i: number; start: number; end: number; text: string }[] };
export const getClipsTranscript = (url: string) => call<KTranscript>(url);

/* --------------------------------------------------------------- handoffs */

export const CLIPS_JOB_KEY = "klyprima:clips-job";
export const CLIPS_HANDOFF_KEY = "klyprima:clips-link";
export type ClipsHandoff = { token: string; index: number; title: string; thumbnail: string | null; duration: number | null };
