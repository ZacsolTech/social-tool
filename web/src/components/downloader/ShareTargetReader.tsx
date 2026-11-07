"use client";

import { useSearchParams } from "next/navigation";
import { useEffect, useRef } from "react";
import { extractUrl } from "@/lib/platforms";

/**
 * Reads ?url= / ?text= (sent by the PWA share sheet or by links like /?url=…)
 * and hands the link to the downloader once. Lives inside <Suspense> so the
 * rest of the page can still be prerendered.
 */
export function ShareTargetReader({ onUrl }: { onUrl: (url: string) => void }) {
  const params = useSearchParams();
  const done = useRef(false);

  useEffect(() => {
    if (done.current) return;
    const raw = [params.get("url"), params.get("text"), params.get("title")].filter(Boolean).join(" ");
    const url = raw ? extractUrl(raw) : null;
    if (url) {
      done.current = true;
      onUrl(url);
      window.history.replaceState(null, "", window.location.pathname);
    }
  }, [params, onUrl]);

  return null;
}
