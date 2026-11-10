"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type DownloadErrorMessage, type Item, type Option, prepareDownload, startNativeDownload } from "@/lib/api";

export type DownloadStatus = {
  state: "preparing" | "starting" | "started" | "error";
  error?: string;
  /** preparing: conversion progress 0..1 (null = unknown) */
  progress?: number | null;
};

export const dlKey = (item: number, option: string) => `${item}:${option}`;

const POLL_MS = 800;

/**
 * Every click ends in the browser's download manager (or IDM).
 * Options that need converting (Facebook H.264, MP3) are first prepared on the server while the
 * button shows the progress, so the download then starts with its exact size and can resume.
 */
export function useDownloads(token: string) {
  const [status, setStatus] = useState<Record<string, DownloadStatus>>({});
  const ridToKey = useRef(new Map<string, string>());
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);
  const gen = useRef(0); // bumps when the link changes: running conversions stop updating the buttons

  useEffect(() => {
    gen.current += 1;
    setStatus({});
    ridToKey.current.clear();
    return () => {
      gen.current += 1;
      timers.current.forEach(clearTimeout);
    };
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

  const set = useCallback((key: string, st: DownloadStatus) => setStatus((s) => ({ ...s, [key]: st })), []);

  const handOff = useCallback(
    (key: string, href: string, delay: number) => {
      const rid = `${key}:${Date.now()}`;
      ridToKey.current.set(rid, key);
      set(key, { state: "starting" });
      startNativeDownload(href, rid);
      const t = setTimeout(
        () => setStatus((s) => (s[key]?.state === "starting" ? { ...s, [key]: { state: "started" } } : s)),
        delay,
      );
      timers.current.push(t);
    },
    [set],
  );

  const start = useCallback(
    async (item: Item, opt: Option) => {
      const key = dlKey(item.index, opt.id);
      const href = `${item.download_base}/${opt.id}`;
      if (!opt.prepare) {
        handOff(key, href, opt.instant ? 1500 : 4000);
        return;
      }
      const mine = gen.current;
      const alive = () => gen.current === mine;
      set(key, { state: "preparing", progress: 0 });
      try {
        let st = await prepareDownload(href, "POST");
        while (st.state === "running") {
          if (!alive()) return;
          set(key, { state: "preparing", progress: st.progress });
          await new Promise((r) => setTimeout(r, POLL_MS));
          st = await prepareDownload(href, "GET");
        }
        if (!alive()) return;
        if (st.state === "error") throw new ApiError(st.error || "Couldn't prepare this file.");
        handOff(key, href, 1500);
      } catch (e) {
        if (alive()) set(key, { state: "error", error: e instanceof ApiError ? e.message : "Something went wrong. Please try again." });
      }
    },
    [handOff, set],
  );

  return { status, start };
}
