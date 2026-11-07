"use client";

import clsx from "clsx";
import { ArrowRight, CircleAlert, ClipboardPaste, History, Link2, LoaderCircle, X } from "lucide-react";
import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import { ApiError, type Resolved, resolveUrl } from "@/lib/api";
import { byId, detectPlatform, extractUrl, type PlatformId } from "@/lib/platforms";
import { PlatformBadge } from "../PlatformBadge";
import { ResultCard } from "./ResultCard";
import { ShareTargetReader } from "./ShareTargetReader";
import { useHistory } from "./useHistory";

type Phase = "idle" | "resolving" | "ready" | "error";

export function Downloader({ platformHint }: { platformHint?: PlatformId }) {
  const [value, setValue] = useState("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [data, setData] = useState<Resolved | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [canPaste, setCanPaste] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const history = useHistory();
  const addHistory = history.add;

  const hint = platformHint ? byId(platformHint) : null;
  const detected = value ? detectPlatform(extractUrl(value) ?? value) : null;

  useEffect(() => {
    setCanPaste(typeof navigator !== "undefined" && !!navigator.clipboard?.readText);
  }, []);

  const submit = useCallback(
    async (raw: string) => {
      const url = extractUrl(raw) ?? raw.trim();
      if (!url) {
        inputRef.current?.focus();
        return;
      }
      setValue(url);
      if (!detectPlatform(url)) {
        setPhase("error");
        setData(null);
        setError(
          "That doesn't look like a supported link. Copy the link of a YouTube, TikTok, Instagram, Facebook, X, Reddit or Pinterest post.",
        );
        return;
      }
      abortRef.current?.abort();
      const ctrl = new AbortController();
      abortRef.current = ctrl;
      setPhase("resolving");
      setError(null);
      setData(null);
      try {
        const res = await resolveUrl(url, ctrl.signal);
        if (ctrl.signal.aborted) return;
        setData(res);
        setPhase("ready");
        addHistory({ url, title: res.title, platform: res.platform.id });
      } catch (e) {
        if (ctrl.signal.aborted) return;
        setPhase("error");
        setError(e instanceof ApiError ? e.message : "Something went wrong. Please try again.");
      }
    },
    [addHistory],
  );

  // Ctrl/Cmd+V anywhere on the page pastes the link and starts right away.
  useEffect(() => {
    const onPaste = (e: ClipboardEvent) => {
      const t = e.target as HTMLElement | null;
      if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
      const url = extractUrl(e.clipboardData?.getData("text") ?? "");
      if (url) {
        e.preventDefault();
        submit(url);
        window.scrollTo({ top: 0, behavior: "smooth" });
      }
    };
    document.addEventListener("paste", onPaste);
    return () => document.removeEventListener("paste", onPaste);
  }, [submit]);

  async function pasteFromClipboard() {
    try {
      const text = await navigator.clipboard.readText();
      const url = extractUrl(text);
      if (url) submit(url);
      else {
        setValue(text);
        inputRef.current?.focus();
      }
    } catch {
      inputRef.current?.focus();
    }
  }

  function reset() {
    abortRef.current?.abort();
    setValue("");
    setData(null);
    setError(null);
    setPhase("idle");
    inputRef.current?.focus();
    window.scrollTo({ top: 0, behavior: "smooth" });
  }

  const busy = phase === "resolving";
  const badge = detected ?? hint;

  return (
    <div className="w-full">
      <Suspense fallback={null}>
        <ShareTargetReader onUrl={submit} />
      </Suspense>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(value);
        }}
        className={clsx(
          "group relative flex items-center gap-2 rounded-2xl border bg-elev p-2 shadow-card transition sm:rounded-[20px]",
          phase === "error" ? "border-danger/60" : "border-line-strong focus-within:border-fg",
        )}
      >
        <span className="grid size-10 shrink-0 place-items-center">
          {badge ? <PlatformBadge platform={badge} size={30} /> : <Link2 className="size-5 text-subtle" />}
        </span>
        <label htmlFor="cf-url" className="sr-only">
          Video link
        </label>
        <input
          ref={inputRef}
          id="cf-url"
          type="url"
          inputMode="url"
          autoComplete="off"
          spellCheck={false}
          enterKeyHint="go"
          placeholder={hint ? `Paste ${hint.short} link…` : "Paste a YouTube, TikTok, Instagram or X link…"}
          value={value}
          onChange={(e) => {
            setValue(e.target.value);
            if (phase === "error") setPhase("idle");
          }}
          onPaste={(e) => {
            const url = extractUrl(e.clipboardData.getData("text"));
            if (url) {
              e.preventDefault();
              submit(url);
            }
          }}
          className="min-w-0 flex-1 bg-transparent py-3 text-base outline-none placeholder:text-subtle"
        />
        {value ? (
          <button
            type="button"
            onClick={reset}
            aria-label="Clear"
            className="grid size-9 shrink-0 place-items-center rounded-full text-subtle transition hover:bg-line hover:text-fg"
          >
            <X className="size-4" />
          </button>
        ) : (
          canPaste && (
            <button
              type="button"
              onClick={pasteFromClipboard}
              className="hidden shrink-0 items-center gap-1.5 rounded-xl px-3 py-2 text-sm font-medium text-muted transition hover:bg-line hover:text-fg sm:inline-flex"
            >
              <ClipboardPaste className="size-4" /> Paste
            </button>
          )
        )}
        <button
          type={!value && canPaste ? "button" : "submit"}
          onClick={!value && canPaste ? pasteFromClipboard : undefined}
          disabled={busy}
          className="inline-flex h-12 shrink-0 items-center gap-2 rounded-xl bg-accent px-4 font-semibold text-accent-fg transition hover:brightness-105 active:scale-[0.98] disabled:opacity-80 sm:px-6"
        >
          {busy ? (
            <LoaderCircle className="size-5 animate-spin" />
          ) : !value && canPaste ? (
            <ClipboardPaste className="size-5 sm:hidden" />
          ) : (
            <ArrowRight className="size-5 sm:hidden" />
          )}
          <span className="hidden sm:inline">{busy ? "Fetching…" : !value && canPaste ? "Paste & go" : "Download"}</span>
          <span className="sr-only sm:hidden">{!value && canPaste ? "Paste and download" : "Download"}</span>
        </button>
      </form>

      <div aria-live="polite" className="mt-4">
        {phase === "resolving" && <Skeleton />}

        {phase === "error" && error && (
          <div className="flex items-start gap-3 rounded-2xl border border-danger/30 bg-danger/5 p-4 text-sm">
            <CircleAlert className="mt-0.5 size-4 shrink-0 text-danger" />
            <div className="flex-1">
              <p className="text-fg">{error}</p>
              {detectPlatform(value) && (
                <button type="button" onClick={() => submit(value)} className="mt-2 font-medium text-accent hover:underline">
                  Try again
                </button>
              )}
            </div>
          </div>
        )}

        {phase === "ready" && data && <ResultCard data={data} onReset={reset} />}

        {phase === "idle" && history.items.length > 0 && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="inline-flex items-center gap-1 text-subtle">
              <History className="size-3.5" /> Recent
            </span>
            {history.items.slice(0, 4).map((h) => {
              const p = byId(h.platform);
              return (
                <button
                  key={h.url}
                  type="button"
                  onClick={() => submit(h.url)}
                  className="inline-flex max-w-[220px] items-center gap-1.5 rounded-full border border-line bg-elev py-1 pl-1 pr-3 transition hover:border-line-strong"
                >
                  {p && <PlatformBadge platform={p} size={20} />}
                  <span className="truncate">{h.title}</span>
                </button>
              );
            })}
            <button type="button" onClick={history.clear} className="text-subtle underline-offset-2 hover:text-fg hover:underline">
              Clear
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function Skeleton() {
  // Some platforms (TikTok on some networks) need a few retries; tell people we're still on it.
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    const t = setTimeout(() => setSlow(true), 6000);
    return () => clearTimeout(t);
  }, []);
  return (
    <div className="rounded-3xl border border-line bg-elev p-4 shadow-card">
      <div className="grid gap-5 sm:grid-cols-[200px_1fr]">
        <div className="shimmer mx-auto aspect-[9/16] w-full max-w-[200px] rounded-2xl sm:aspect-[3/4]" />
        <div className="space-y-3 py-1">
          <div className="shimmer h-4 w-32 rounded" />
          <div className="shimmer h-6 w-4/5 rounded" />
          <div className="shimmer h-6 w-3/5 rounded" />
          <div className="grid grid-cols-2 gap-2 pt-4 sm:grid-cols-3">
            {Array.from({ length: 3 }).map((_, i) => (
              <div key={i} className="shimmer h-14 rounded-xl" />
            ))}
          </div>
          <p className="pt-1 text-sm text-muted">
            {slow ? "Still trying… the platform is slow to respond, retrying automatically." : "Reading the link…"}
          </p>
        </div>
      </div>
    </div>
  );
}
