"use client";

import clsx from "clsx";
import { ChevronDown, ChevronUp, Combine, Redo2, Replace, Search, SmilePlus, Trash2, Undo2 } from "lucide-react";
import { memo, useEffect, useMemo, useRef, useState } from "react";
import {
  type CLine,
  type CTranscript,
  deleteLine,
  findReplace,
  formatTimecode,
  mergeWithNext,
  setLineEmoji,
  setWord,
  shiftLine,
  splitLine,
  withText,
} from "@/lib/captionsCore";

const EMOJIS = ["🔥", "💰", "😂", "❤️", "🤯", "✅", "❌", "💡", "🚀", "👉", "😱", "🙏", "🎯", "⚡", "👀", "💯"];

export function TranscriptEditor({
  transcript,
  onChange,
  current,
  onSeek,
  rtl,
  duration,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  disabled,
}: {
  transcript: CTranscript;
  onChange: (t: CTranscript) => void;
  current: number;
  onSeek: (t: number) => void;
  rtl: boolean;
  duration: number | null;
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
  disabled: boolean;
}) {
  const [focus, setFocus] = useState<number | null>(null);
  const [find, setFind] = useState("");
  const [replace, setReplace] = useState("");
  const [showFind, setShowFind] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const list = useRef<HTMLDivElement>(null);
  const hasTranslation = transcript.lines.some((l) => l.translation);

  // Keep the line being spoken in view while the video plays (unless the person is typing).
  useEffect(() => {
    if (current < 0 || focus !== null) return;
    const row = list.current?.querySelector<HTMLElement>(`[data-line="${current}"]`);
    const parent = list.current;
    if (row && parent) {
      const top = row.offsetTop - parent.offsetTop;
      if (top < parent.scrollTop || top > parent.scrollTop + parent.clientHeight - row.clientHeight) {
        parent.scrollTo({ top: top - parent.clientHeight / 3, behavior: "smooth" });
      }
    }
  }, [current, focus]);

  const matches = useMemo(() => {
    if (!find) return 0;
    const re = new RegExp(find.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"), "gi");
    return transcript.lines.reduce((a, l) => a + (l.text.match(re)?.length ?? 0), 0);
  }, [find, transcript]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-1.5">
        <IconBtn label="Undo (Ctrl+Z)" onClick={onUndo} disabled={!canUndo || disabled}>
          <Undo2 className="size-4" />
        </IconBtn>
        <IconBtn label="Redo (Ctrl+Y)" onClick={onRedo} disabled={!canRedo || disabled}>
          <Redo2 className="size-4" />
        </IconBtn>
        <IconBtn label="Find and replace" onClick={() => setShowFind((v) => !v)} active={showFind}>
          <Search className="size-4" />
        </IconBtn>
        <span className="ml-auto text-xs text-subtle">
          {transcript.lines.length} lines · Enter splits a line · Backspace at the start joins it with the one above
        </span>
      </div>
      {showFind && (
        <div className="flex flex-wrap items-center gap-2 rounded-xl border border-line bg-bg p-2">
          <input value={find} onChange={(e) => setFind(e.target.value)} placeholder="Find" aria-label="Find" className="min-w-0 flex-1 rounded-lg bg-elev px-2.5 py-1.5 text-sm outline-none ring-accent focus:ring-1" />
          <input value={replace} onChange={(e) => setReplace(e.target.value)} placeholder="Replace with" aria-label="Replace with" className="min-w-0 flex-1 rounded-lg bg-elev px-2.5 py-1.5 text-sm outline-none ring-accent focus:ring-1" />
          <button
            type="button"
            disabled={!matches || disabled}
            onClick={() => {
              const r = findReplace(transcript, find, replace, false);
              onChange(r.t);
              setNotice(`Replaced ${r.count}`);
              setTimeout(() => setNotice(null), 2000);
            }}
            className="inline-flex items-center gap-1 rounded-lg bg-fg px-3 py-1.5 text-xs font-medium text-bg disabled:opacity-40"
          >
            <Replace className="size-3.5" /> Replace all ({matches})
          </button>
          {notice && <span className="text-xs text-ok">{notice}</span>}
        </div>
      )}
      <div ref={list} className="relative max-h-[60vh] space-y-1 overflow-y-auto pr-1">
        {transcript.lines.map((line, i) => (
          <Row
            key={line.id}
            index={i}
            line={line}
            lang={transcript.language}
            active={i === current}
            focused={i === focus}
            rtl={rtl}
            showTranslation={hasTranslation}
            disabled={disabled}
            onFocus={() => setFocus(i)}
            onBlur={() => setFocus((f) => (f === i ? null : f))}
            onSeek={onSeek}
            onText={(text) => onChange(replaceLine(transcript, i, withText(line, text, transcript.language)))}
            onTranslation={(text) => onChange(replaceLine(transcript, i, { ...line, translation: text.trim() || null }))}
            onSplit={(wordIndex) => onChange(splitLine(transcript, i, wordIndex))}
            onMergeUp={() => i > 0 && onChange(mergeWithNext(transcript, i - 1))}
            onMergeDown={() => onChange(mergeWithNext(transcript, i))}
            onDelete={() => onChange(deleteLine(transcript, i))}
            onShift={(d) => onChange(shiftLine(transcript, i, d, duration))}
            onKeyword={(wi) => onChange(setWord(transcript, i, wi, { keyword: !line.words[wi].keyword }))}
            onEmoji={(e) => onChange(setLineEmoji(transcript, i, e))}
          />
        ))}
        {!transcript.lines.length && <p className="p-6 text-center text-sm text-muted">No captions. The video may have no speech.</p>}
      </div>
    </div>
  );
}

function replaceLine(t: CTranscript, i: number, line: CLine): CTranscript {
  if (!line.words.length) return deleteLine(t, i);
  const lines = [...t.lines];
  lines[i] = line;
  return { ...t, lines };
}

const Row = memo(function Row({
  index,
  line,
  lang,
  active,
  focused,
  rtl,
  showTranslation,
  disabled,
  onFocus,
  onBlur,
  onSeek,
  onText,
  onTranslation,
  onSplit,
  onMergeUp,
  onMergeDown,
  onDelete,
  onShift,
  onKeyword,
  onEmoji,
}: {
  index: number;
  line: CLine;
  lang: string;
  active: boolean;
  focused: boolean;
  rtl: boolean;
  showTranslation: boolean;
  disabled: boolean;
  onFocus: () => void;
  onBlur: () => void;
  onSeek: (t: number) => void;
  onText: (t: string) => void;
  onTranslation: (t: string) => void;
  onSplit: (wordIndex: number) => void;
  onMergeUp: () => void;
  onMergeDown: () => void;
  onDelete: () => void;
  onShift: (d: number) => void;
  onKeyword: (wi: number) => void;
  onEmoji: (e: string | null) => void;
}) {
  const [draft, setDraft] = useState(line.text);
  const [emojiOpen, setEmojiOpen] = useState(false);
  const area = useRef<HTMLTextAreaElement>(null);
  useEffect(() => setDraft(line.text), [line.text]);
  useEffect(() => {
    const el = area.current;
    if (el) {
      el.style.height = "0px";
      el.style.height = `${el.scrollHeight}px`;
    }
  }, [draft]);
  const emoji = line.words.find((w) => w.emoji)?.emoji ?? null;

  function commit() {
    if (draft.trim() !== line.text) onText(draft);
  }

  function caretWord(): number {
    const el = area.current;
    if (!el) return 0;
    const before = draft.slice(0, el.selectionStart).trim();
    if (!before) return 0;
    return lang.split("-")[0].match(/^(zh|ja|th)$/) ? Math.ceil([...before].length / 2) : before.split(/\s+/).length;
  }

  return (
    <div
      data-line={index}
      className={clsx(
        "group rounded-xl border px-2.5 py-2 transition",
        active ? "border-accent/60 bg-accent-soft/40" : focused ? "border-line-strong bg-bg" : "border-transparent hover:bg-bg",
      )}
    >
      <div className="flex items-start gap-2">
        <button
          type="button"
          onClick={() => onSeek(line.start)}
          title="Play from here"
          className="mt-1 shrink-0 rounded-md px-1.5 py-0.5 font-mono text-[11px] text-muted transition hover:bg-line hover:text-fg"
        >
          {formatTimecode(line.start)}
        </button>
        <textarea
          ref={area}
          rows={1}
          dir={rtl ? "rtl" : "auto"}
          value={draft}
          disabled={disabled}
          aria-label={`Caption line ${index + 1}`}
          onFocus={onFocus}
          onBlur={() => {
            commit();
            onBlur();
          }}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              const wi = caretWord();
              if (draft.trim() !== line.text) commit();
              else if (wi > 0 && wi < line.words.length) onSplit(wi);
            } else if (e.key === "Backspace" && area.current?.selectionStart === 0 && area.current?.selectionEnd === 0 && index > 0) {
              e.preventDefault();
              commit();
              onMergeUp();
            } else if (e.key === "Escape") {
              setDraft(line.text);
              area.current?.blur();
            }
          }}
          className={clsx("min-w-0 flex-1 resize-none bg-transparent py-0.5 text-[15px] leading-relaxed outline-none", rtl && "text-right")}
        />
        {emoji && <span className="mt-0.5 text-lg leading-none">{emoji}</span>}
      </div>
      {showTranslation && (
        <input
          defaultValue={line.translation ?? ""}
          key={line.translation ?? ""}
          dir="auto"
          aria-label={`Translation of line ${index + 1}`}
          placeholder="Translation"
          disabled={disabled}
          onBlur={(e) => e.target.value.trim() !== (line.translation ?? "") && onTranslation(e.target.value)}
          className="ml-12 mt-1 w-[calc(100%-3rem)] rounded-md bg-transparent px-1 py-0.5 text-sm text-muted outline-none focus:bg-elev"
        />
      )}
      {focused && !disabled && (
        <div className="ml-12 mt-2 space-y-2" onMouseDown={(e) => e.preventDefault()}>
          <div className="flex flex-wrap gap-1" dir={rtl ? "rtl" : "ltr"}>
            {line.words.map((w, wi) => (
              <button
                key={`${wi}-${w.start}`}
                type="button"
                onClick={() => onKeyword(wi)}
                title={w.keyword ? "Highlighted word (click to remove)" : "Click to highlight this word"}
                className={clsx(
                  "rounded-md border px-1.5 py-0.5 text-xs transition",
                  w.keyword ? "border-ok/60 bg-ok/15 font-semibold text-fg" : "border-line text-muted hover:border-line-strong",
                )}
              >
                {w.text}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap items-center gap-1">
            <IconBtn label="Earlier by 0.1 s" onClick={() => onShift(-0.1)}>
              <ChevronUp className="size-4" />
            </IconBtn>
            <IconBtn label="Later by 0.1 s" onClick={() => onShift(0.1)}>
              <ChevronDown className="size-4" />
            </IconBtn>
            <IconBtn label="Join with next line" onClick={onMergeDown}>
              <Combine className="size-4" />
            </IconBtn>
            <div className="relative">
              <IconBtn label="Emoji for this line" onClick={() => setEmojiOpen((v) => !v)} active={emojiOpen}>
                <SmilePlus className="size-4" />
              </IconBtn>
              {emojiOpen && (
                <div className="absolute left-0 top-9 z-20 grid w-56 grid-cols-8 gap-1 rounded-xl border border-line bg-elev p-2 shadow-card">
                  {EMOJIS.map((e) => (
                    <button key={e} type="button" onClick={() => (onEmoji(e), setEmojiOpen(false))} className="rounded p-1 text-lg hover:bg-line">
                      {e}
                    </button>
                  ))}
                  <button type="button" onClick={() => (onEmoji(null), setEmojiOpen(false))} className="col-span-8 rounded py-1 text-xs text-muted hover:bg-line">
                    No emoji
                  </button>
                </div>
              )}
            </div>
            <IconBtn label="Delete line" onClick={onDelete}>
              <Trash2 className="size-4" />
            </IconBtn>
            <span className="ml-1 font-mono text-[11px] text-subtle">
              {formatTimecode(line.start)} – {formatTimecode(line.end)}
            </span>
          </div>
        </div>
      )}
    </div>
  );
});

function IconBtn({ label, onClick, disabled, active, children }: { label: string; onClick: () => void; disabled?: boolean; active?: boolean; children: React.ReactNode }) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
      className={clsx(
        "grid size-8 place-items-center rounded-lg border transition disabled:opacity-35",
        active ? "border-accent bg-accent-soft text-accent" : "border-line text-muted hover:border-line-strong hover:text-fg",
      )}
    >
      {children}
    </button>
  );
}
