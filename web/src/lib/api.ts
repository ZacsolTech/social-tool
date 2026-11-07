export type Option = {
  id: string;
  label: string;
  kind: "video" | "audio" | "image";
  ext: string;
  quality: number;
  size: number | null;
  note: string | null;
  has_audio: boolean;
  best: boolean;
  /** false = MP3 conversion: the first bytes take a few seconds */
  instant: boolean;
};

export type Item = {
  index: number;
  title: string;
  duration: number | null;
  width: number | null;
  height: number | null;
  thumbnail: string | null;
  error: string | null;
  options: Option[];
  download_base: string;
  /** seconds until the platform allows the download (YouTube's short availability wait) */
  ready_in: number;
};

export type Resolved = {
  token: string;
  platform: { id: string; name: string };
  title: string;
  uploader: string | null;
  webpage_url: string;
  items: Item[];
};

export class ApiError extends Error {}

async function asJson<T>(res: Response): Promise<T> {
  const body = await res.json().catch(() => null);
  if (!res.ok) {
    const detail = body?.detail;
    throw new ApiError(
      typeof detail === "string"
        ? detail
        : res.status === 429
          ? "Too many requests. Please wait a minute."
          : "Something went wrong. Please try again.",
    );
  }
  return body as T;
}

export async function resolveUrl(url: string, signal?: AbortSignal): Promise<Resolved> {
  const res = await fetch("/api/resolve", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ url }),
    signal,
  }).catch(() => {
    throw new ApiError("Can't reach the server. Check your connection and try again.");
  });
  return asJson<Resolved>(res);
}

/**
 * Hand a download to the browser's own download manager (and IDM etc.).
 * It runs in a hidden iframe: a file response becomes a normal download, while an
 * error page posts a message back to us (see the backend's _error_page) instead of
 * the browser saving a broken file.
 */
export function startNativeDownload(href: string, rid: string) {
  const sep = href.includes("?") ? "&" : "?";
  const frame = document.createElement("iframe");
  frame.hidden = true;
  frame.setAttribute("aria-hidden", "true");
  frame.src = `${href}${sep}rid=${encodeURIComponent(rid)}`;
  document.body.appendChild(frame);
  // The download keeps going after the frame is gone; this only tidies the DOM.
  setTimeout(() => frame.remove(), 10 * 60 * 1000);
}

export type DownloadErrorMessage = { type: "cf-download-error"; rid: string; message: string };

export function formatBytes(n: number | null | undefined): string {
  if (!n) return "";
  const u = ["B", "KB", "MB", "GB"];
  let i = 0;
  let v = n;
  while (v >= 1024 && i < u.length - 1) {
    v /= 1024;
    i++;
  }
  return `${v >= 10 || i === 0 ? Math.round(v) : v.toFixed(1)} ${u[i]}`;
}

export function formatDuration(sec: number | null | undefined): string {
  if (!sec) return "";
  const s = Math.round(sec);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const r = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${r}` : `${m}:${r}`;
}
