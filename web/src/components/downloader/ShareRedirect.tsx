"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useEffect } from "react";

/**
 * The home page is AI Clips now. Links shared to the installed app (and old bookmarks) still arrive as
 * /?url=…&text=…: send them on to the downloader, which reads them and starts by itself.
 */
export function ShareRedirect() {
  const params = useSearchParams();
  const router = useRouter();
  useEffect(() => {
    if (params.get("url") || params.get("text") || params.get("title")) {
      router.replace(`/video-downloader?${params.toString()}`);
    }
  }, [params, router]);
  return null;
}
