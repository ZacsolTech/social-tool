"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { type DownloadErrorMessage, type Item, type Option, startNativeDownload } from "@/lib/api";

export type DownloadStatus = { state: "starting" | "started" | "error"; error?: string };

export const dlKey = (item: number, option: string) => `${item}:${option}`;

/**
 * Every click goes straight to the browser's download manager (or IDM): no waiting on the page.
 * Each button only shows a light status: starting -> started, or the error the server reported.
 */
export function useDownloads(token: string) {
  const [status, setStatus] = useState<Record<string, DownloadStatus>>({});
  const ridToKey = useRef(new Map<string, string>());
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  useEffect(() => {
    setStatus({});
    ridToKey.current.clear();
    return () => timers.current.forEach(clearTimeout);
  }, [token]);

  // Error pages inside the hidden iframe report back here.
  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (e.origin !== window.location.origin) return;
      const msg = e.data as DownloadErrorMessage;
      if (msg?.type !== "cf-download-error") return;
      const key = ridToKey.current.get(msg.rid);
      if (key) setStatus((s) => ({ ...s, [key]: { state: "error", error: msg.message } }));
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, []);

  const start = useCallback((item: Item, opt: Option) => {
    const key = dlKey(item.index, opt.id);
    const rid = `${key}:${Date.now()}`;
    ridToKey.current.set(rid, key);
    setStatus((s) => ({ ...s, [key]: { state: "starting" } }));
    startNativeDownload(`${item.download_base}/${opt.id}`, rid);
    // MP3 conversion needs a few seconds before the first bytes; everything else starts at once.
    const t = setTimeout(
      () => setStatus((s) => (s[key]?.state === "starting" ? { ...s, [key]: { state: "started" } } : s)),
      opt.instant ? 1500 : 4000,
    );
    timers.current.push(t);
  }, []);

  return { status, start };
}
