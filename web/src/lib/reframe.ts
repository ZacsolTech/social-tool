/** Client for the Reframe API (backend/app/reframe/api.py). */

import { ApiError } from "./api";

export type Aspect = "9:16" | "4:5" | "1:1";
export type Mode = "smart" | "blur" | "crop" | "fit";
export type Quality = "1080p" | "720p";
export type Layout = "follow" | "split" | "facecam" | "fit";

export const ASPECTS: { id: Aspect; label: string; hint: string; ratio: number }[] = [
  { id: "9:16", label: "9:16", hint: "TikTok, Reels, Shorts", ratio: 9 / 16 },
  { id: "4:5", label: "4:5", hint: "Instagram & Facebook feed", ratio: 4 / 5 },
  { id: "1:1", label: "1:1", hint: "Square feed, LinkedIn, X", ratio: 1 },
];

export type SmartOptions = {
  style: "steady" | "follow";
  framing: number;
  dynamic_zoom: boolean;
  zoom_amount: number;
  split: boolean;
  facecam: boolean;
  text_aware: boolean;
  two_person: "auto" | "split" | "switch";
  safe_zone: "tiktok" | "reels" | "shorts" | "none";
  follow: string | null;
};

export type Look = {
  background: "blur" | "color";
  color: string;
  blur: 1 | 2 | 3;
  dim: number;
  fg_zoom: number;
};

export const DEFAULT_SMART: SmartOptions = {
  style: "steady",
  framing: 1,
  dynamic_zoom: false,
  zoom_amount: 1.12,
  split: true,
  facecam: true,
  text_aware: true,
  two_person: "auto",
  safe_zone: "tiktok",
  follow: null,
};

export const DEFAULT_LOOK: Look = { background: "blur", color: "#000000", blur: 2, dim: 0.15, fg_zoom: 1 };

export type Settings = {
  mode: Mode;
  aspects: Aspect[];
  quality: Quality;
  smart: SmartOptions;
  look: Look;
  position: number;
  trimStart: number;
  trimEnd: number | null;
};

export type MediaInfo = {
  duration: number;
  width: number;
  height: number;
  fps: number;
  has_audio: boolean;
  vcodec: string;
  rotation: number;
  hdr: boolean;
  size: number;
};

export type Config = {
  max_upload_mb: number;
  chunk_mb: number;
  max_duration_sec: number;
  allow_links: boolean;
  objects: string[];
  synonyms: Record<string, string>;
  ttl_hours: number;
};

type Box = [number, number, number, number];

export type ShotDesc = {
  index: number;
  start: number;
  end: number;
  thumb_t: number;
  thumb: string;
  layout: Layout;
  reason: string;
  crops: { box: Box; dst: Box }[];
  faces: { track: number; label: string; box: Box }[];
  objects: { track: number; label: string; box: Box }[];
  subjects: number[];
  facecam: Box | null;
  has_text: boolean;
};

export type Override = {
  layout?: "auto" | Layout;
  center?: number;
  track?: number;
  point?: [number, number];
};

export type JobState = "queued" | "importing" | "analysing" | "rendering" | "done" | "error" | "cancelled";

export type Job = {
  id: string;
  state: JobState;
  stage: string;
  progress: number;
  eta: number | null;
  queue_position: number | null;
  error: string | null;
  mode: Mode;
  aspects: Aspect[];
  quality: Quality;
  smart: SmartOptions;
  look: Look;
  position: number;
  trim: [number, number | null];
  title: string;
  source: { type: "upload" | "link"; url: string };
  info: MediaInfo | null;
  version: number;
  outputs: { aspect: Aspect; size: number; name: string; url: string }[];
  shots: Partial<Record<Aspect, ShotDesc[]>>;
  overrides: Record<string, Override>;
  editable: boolean;
};

export type Source =
  | { type: "upload"; id: string }
  | { type: "link"; token: string; index: number };

export const ACTIVE: JobState[] = ["queued", "importing", "analysing", "rendering"];

async function json<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const d = body?.detail;
    throw new ApiError(
      typeof d === "string" ? d : res.status === 429 ? "Too many requests. Please wait a minute." : "Something went wrong. Please try again.",
    );
  }
  return body as T;
}

async function call<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, { cache: "no-store", ...init }).catch(() => {
    throw new ApiError("Can't reach the server. Check your connection and try again.");
  });
  return json<T>(res);
}

const jsonInit = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "content-type": "application/json" },
  body: JSON.stringify(body),
});

let configPromise: Promise<Config> | null = null;
export function getConfig(): Promise<Config> {
  configPromise ??= call<Config>("/api/reframe/config").catch((e) => {
    configPromise = null;
    throw e;
  });
  return configPromise;
}

/* ------------------------------------------------------------------ uploads */

export type UploadResult = { id: string; info: MediaInfo };

function putChunk(url: string, blob: Blob, onBytes: (n: number) => void, signal: AbortSignal): Promise<{ status: number; body: any }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", url);
    xhr.responseType = "json";
    xhr.upload.onprogress = (e) => onBytes(e.loaded);
    xhr.onload = () => resolve({ status: xhr.status, body: xhr.response });
    xhr.onerror = () => reject(new TypeError("network"));
    xhr.ontimeout = () => reject(new TypeError("timeout"));
    xhr.timeout = 120_000;
    const abort = () => xhr.abort();
    signal.addEventListener("abort", abort, { once: true });
    xhr.onabort = () => reject(new DOMException("Aborted", "AbortError"));
    xhr.send(blob);
  });
}

/** Chunked upload that survives flaky connections: each piece is retried, and the server tells us
 * how much it really has (409) so we always continue from the right place. */
export async function uploadFile(file: File, onProgress: (fraction: number) => void, signal: AbortSignal): Promise<UploadResult> {
  const init = await call<{ id: string; chunk_size: number }>("/api/uploads", { ...jsonInit("POST", { filename: file.name, size: file.size }), signal });
  const chunk = init.chunk_size;
  let offset = 0;
  let failures = 0;
  onProgress(0);
  while (offset < file.size) {
    if (signal.aborted) throw new DOMException("Aborted", "AbortError");
    const blob = file.slice(offset, Math.min(file.size, offset + chunk));
    try {
      const res = await putChunk(`/api/uploads/${init.id}?offset=${offset}`, blob, (n) => onProgress((offset + n) / file.size), signal);
      if (res.status === 200 || res.status === 409) {
        if (typeof res.body?.received !== "number") throw new ApiError("Upload failed. Please try again.");
        offset = res.body.received;
        failures = 0;
        onProgress(offset / file.size);
        continue;
      }
      if (res.status >= 500 || res.status === 400) throw new TypeError("retry");
      throw new ApiError(res.body?.detail ?? "Upload failed. Please try again.");
    } catch (e) {
      if (e instanceof ApiError || (e as Error)?.name === "AbortError") throw e;
      failures += 1;
      if (failures > 8) throw new ApiError("Your connection keeps dropping. Please try again on a stronger connection.");
      await new Promise((r) => setTimeout(r, Math.min(15_000, 800 * 2 ** failures)));
      const status = await call<{ received: number }>(`/api/uploads/${init.id}`).catch(() => null);
      if (status) offset = status.received;
    }
  }
  const done = await call<{ id: string; info: MediaInfo }>(`/api/uploads/${init.id}/complete`, { method: "POST", signal });
  onProgress(1);
  return { id: done.id, info: done.info };
}

export function deleteUpload(id: string) {
  return fetch(`/api/uploads/${id}`, { method: "DELETE" }).catch(() => undefined);
}

/* --------------------------------------------------------------------- jobs */

export function createJob(source: Source, s: Settings, title?: string): Promise<Job> {
  return call<Job>(
    "/api/reframe/jobs",
    jsonInit("POST", {
      source,
      mode: s.mode,
      aspects: s.aspects,
      quality: s.quality,
      smart: s.smart,
      look: s.look,
      position: s.position,
      trim_start: s.trimStart,
      trim_end: s.trimEnd,
      title,
    }),
  );
}

export const getJob = (id: string) => call<Job>(`/api/reframe/jobs/${id}`);

export function rerender(id: string, body: { overrides?: Record<number, Override>; settings?: Settings }): Promise<Job> {
  const s = body.settings;
  return call<Job>(
    `/api/reframe/jobs/${id}/render`,
    jsonInit("POST", {
      overrides: body.overrides ?? {},
      ...(s ? { mode: s.mode, aspects: s.aspects, quality: s.quality, smart: s.smart, look: s.look, position: s.position } : {}),
    }),
  );
}

export const cancelJob = (id: string, remove = false) => call<Job | { ok: true }>(`/api/reframe/jobs/${id}${remove ? "?remove=true" : ""}`, { method: "DELETE" });

/* ------------------------------------------------------------------ helpers */

export function parseTime(v: string): number | null {
  const t = v.trim();
  if (!t) return null;
  const parts = t.split(":").map((p) => Number(p));
  if (parts.some((p) => Number.isNaN(p) || p < 0)) return null;
  return parts.reduce((acc, p) => acc * 60 + p, 0);
}

export function formatClock(sec: number): string {
  const s = Math.max(0, Math.round(sec));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${r}` : `${m}:${r}`;
}

export function formatEta(sec: number | null): string {
  if (!sec) return "";
  if (sec < 60) return `about ${Math.max(5, Math.round(sec / 5) * 5)} s left`;
  return `about ${Math.round(sec / 60)} min left`;
}

/** The downloader's "Make it vertical" button hands its link over through sessionStorage. */
export type LinkHandoff = { token: string; index: number; title: string; thumbnail: string | null; duration: number | null; width: number | null; height: number | null };
export const HANDOFF_KEY = "klyprima:reframe-link";
export const JOB_KEY = "klyprima:reframe-job";

export function readSession<T>(key: string): T | null {
  try {
    const v = sessionStorage.getItem(key);
    return v ? (JSON.parse(v) as T) : null;
  } catch {
    return null;
  }
}

export function writeSession(key: string, value: unknown) {
  try {
    if (value === null) sessionStorage.removeItem(key);
    else sessionStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* private mode: ignore */
  }
}
