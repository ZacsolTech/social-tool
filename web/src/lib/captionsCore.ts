/**
 * Caption logic shared by the editor and the live preview. No imports, so it runs anywhere (and is unit
 * tested with `npm test`). Mirrors backend/app/captions/transcript.py so the preview matches the export.
 */

export type CWord = { text: string; start: number; end: number; keyword?: boolean; emoji?: string | null };
export type CLine = { id: string; start: number; end: number; text: string; words: CWord[]; translation?: string | null };
export type CTranscript = {
  language: string;
  source: string;
  translation_lang: string | null;
  rev: number;
  lines: CLine[];
};

export type Animation = "none" | "fade" | "pop" | "bounce" | "slide" | "karaoke" | "highlight" | "word" | "reveal";

export type CStyle = {
  preset: string;
  font: string;
  size: number;
  uppercase: boolean;
  color: string;
  highlight: string;
  highlight_mode: "color" | "box" | "scale";
  keyword_color: string;
  outline_color: string;
  outline: number;
  shadow: number;
  box: boolean;
  box_color: string;
  box_opacity: number;
  y: number;
  max_words: number;
  max_chars: number;
  animation: Animation;
  spacing: number;
  emoji: boolean;
  keywords: boolean;
  translation_color: string;
  translation_scale: number;
};

const NO_SPACE = new Set(["zh", "ja", "th", "lo", "my", "km", "yue"]);
const SENTENCE_END = /[.!?…۔؟।॥。！？]+["'”’)\]]*$/;
const CLAUSE_END = /[,;:،؛、，]+$/;

export const baseLang = (lang: string | null | undefined) => (lang ?? "").split("-")[0];
export const isRoman = (lang: string | null | undefined) => (lang ?? "").endsWith("-Latn");
export const joiner = (lang: string | null | undefined) => (isRoman(lang) ? " " : NO_SPACE.has(baseLang(lang)) ? "" : " ");

export function newId(): string {
  return Math.random().toString(16).slice(2, 10);
}

export function cleanWord(t: string): string {
  return t.replace(/\s+/g, " ").trim();
}

export function splitText(text: string, lang: string | null | undefined): string[] {
  const t = cleanWord(text);
  if (!t) return [];
  if (joiner(lang) === "") {
    const chars = [...t].filter((c) => !/\s/.test(c));
    const out: string[] = [];
    for (let i = 0; i < chars.length; i += 2) out.push(chars.slice(i, i + 2).join(""));
    return out;
  }
  return t.split(" ");
}

export function lineText(words: CWord[], lang: string | null | undefined): string {
  return words.map((w) => w.text).join(joiner(lang));
}

/** A line's words after its text was retyped: same word count keeps each timing, else spread by length. */
export function retime(words: CWord[], texts: string[], start: number, end: number): CWord[] {
  const ts = texts.map(cleanWord).filter(Boolean);
  if (!ts.length) return [];
  if (ts.length === words.length) return ts.map((text, i) => ({ ...words[i], text }));
  const total = ts.reduce((a, x) => a + Math.max(1, [...x].length), 0);
  const span = Math.max(0.05 * ts.length, end - start);
  let t0 = start;
  return ts.map((text) => {
    const d = (span * Math.max(1, [...text].length)) / total;
    const w = { text, start: round3(t0), end: round3(t0 + d) };
    t0 += d;
    return w;
  });
}

const round3 = (n: number) => Math.round(n * 1000) / 1000;

export function withText(line: CLine, text: string, lang: string): CLine {
  const words = retime(line.words, splitText(text, lang), line.start, line.end);
  return refresh({ ...line, words }, lang);
}

export function refresh(line: CLine, lang: string): CLine {
  const words = line.words;
  return {
    ...line,
    words,
    text: lineText(words, lang),
    start: words.length ? words[0].start : line.start,
    end: words.length ? words[words.length - 1].end : line.end,
  };
}

/* ------------------------------------------------------------- line editing */

export function splitLine(t: CTranscript, li: number, wordIndex: number): CTranscript {
  const ln = t.lines[li];
  if (!ln || wordIndex <= 0 || wordIndex >= ln.words.length) return t;
  const a = refresh({ ...ln, words: ln.words.slice(0, wordIndex), translation: ln.translation }, t.language);
  const b = refresh({ ...ln, id: newId(), words: ln.words.slice(wordIndex), translation: null }, t.language);
  const lines = [...t.lines.slice(0, li), a, b, ...t.lines.slice(li + 1)];
  return { ...t, lines };
}

export function mergeWithNext(t: CTranscript, li: number): CTranscript {
  const a = t.lines[li];
  const b = t.lines[li + 1];
  if (!a || !b) return t;
  const tr = [a.translation, b.translation].filter(Boolean).join(" ") || null;
  const merged = refresh({ ...a, words: [...a.words, ...b.words], translation: tr }, t.language);
  return { ...t, lines: [...t.lines.slice(0, li), merged, ...t.lines.slice(li + 2)] };
}

export function deleteLine(t: CTranscript, li: number): CTranscript {
  return { ...t, lines: t.lines.filter((_, i) => i !== li) };
}

export function shiftLine(t: CTranscript, li: number, delta: number, duration?: number | null): CTranscript {
  const ln = t.lines[li];
  if (!ln) return t;
  const max = duration ?? Number.POSITIVE_INFINITY;
  const d = Math.max(-ln.start, Math.min(delta, max - ln.end));
  const words = ln.words.map((w) => ({ ...w, start: round3(w.start + d), end: round3(w.end + d) }));
  const lines = [...t.lines];
  lines[li] = refresh({ ...ln, words }, t.language);
  return { ...t, lines };
}

export function setWord(t: CTranscript, li: number, wi: number, patch: Partial<CWord>): CTranscript {
  const ln = t.lines[li];
  if (!ln || !ln.words[wi]) return t;
  const words = ln.words.map((w, i) => (i === wi ? { ...w, ...patch } : w));
  const lines = [...t.lines];
  lines[li] = refresh({ ...ln, words }, t.language);
  return { ...t, lines };
}

export function setLineEmoji(t: CTranscript, li: number, emoji: string | null): CTranscript {
  const ln = t.lines[li];
  if (!ln || !ln.words.length) return t;
  const target = Math.max(0, ln.words.findIndex((w) => w.keyword));
  const words = ln.words.map((w, i) => ({ ...w, emoji: i === target ? emoji : null }));
  const lines = [...t.lines];
  lines[li] = refresh({ ...ln, words }, t.language);
  return { ...t, lines };
}

export function findReplace(t: CTranscript, find: string, replace: string, matchCase: boolean): { t: CTranscript; count: number } {
  if (!find) return { t, count: 0 };
  const esc = find.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const re = new RegExp(esc, matchCase ? "g" : "gi");
  let count = 0;
  const lines = t.lines.map((ln) => {
    const text = ln.text;
    const n = (text.match(re) ?? []).length;
    if (!n) return ln;
    count += n;
    return withText(ln, text.replace(re, replace), t.language);
  });
  return { t: { ...t, lines }, count };
}

/* -------------------------------------------------------------------- pages */

export function pages(words: CWord[], maxWords: number, maxChars: number, lang: string): CWord[][] {
  const n = words.length;
  if (!n) return [];
  const sep = joiner(lang).length;
  const totalChars = words.reduce((a, w) => a + [...w.text].length, 0) + sep * (n - 1);
  let k = Math.max(Math.ceil(n / Math.max(1, maxWords)), Math.ceil(totalChars / Math.max(1, maxChars)));
  k = Math.max(1, Math.min(k, n));
  const out: CWord[][] = [];
  let i = 0;
  for (let p = 0; p < k; p++) {
    const left = k - p;
    const take = Math.max(1, roundHalfEven((n - i) / left));
    let chunk = words.slice(i, i + take);
    if (p < k - 1 && chunk.length > 2) {
      for (let j = chunk.length - 1; j > Math.max(0, chunk.length - 3); j--) {
        const prev = chunk[j - 1].text;
        if (SENTENCE_END.test(prev) || CLAUSE_END.test(prev)) {
          chunk = chunk.slice(0, j);
          break;
        }
      }
    }
    out.push(chunk);
    i += chunk.length;
    if (i >= n) break;
  }
  if (i < n) out[out.length - 1] = [...out[out.length - 1], ...words.slice(i)];
  return out.filter((p) => p.length);
}

/** Python's round() rounds halves to even; match it so pages split the same way as the export. */
function roundHalfEven(x: number): number {
  const f = Math.floor(x);
  const diff = x - f;
  if (Math.abs(diff - 0.5) < 1e-9) return f % 2 === 0 ? f : f + 1;
  return Math.round(x);
}

export type Page = { line: CLine; words: CWord[]; start: number; end: number };

export function buildPages(t: CTranscript, style: Pick<CStyle, "max_words" | "max_chars" | "animation">, duration?: number | null): Page[] {
  const maxWords = style.animation === "word" ? 1 : style.max_words;
  const all: { line: CLine; words: CWord[] }[] = [];
  for (const line of t.lines) for (const words of pages(line.words, maxWords, style.max_chars, t.language)) all.push({ line, words });
  return all.map(({ line, words }, k) => {
    const start = words[0].start;
    const last = words[words.length - 1];
    const nxt = k + 1 < all.length ? all[k + 1].words[0].start : null;
    let end = last.end + 0.35;
    if (nxt !== null) end = nxt - last.end < 0.7 ? nxt : Math.min(end, nxt);
    end = Math.max(end, last.end + 0.05, start + 0.25);
    if (duration) end = Math.min(end, duration);
    return { line, words, start, end };
  });
}

export function pageAt(pagesList: Page[], t: number): Page | null {
  let lo = 0;
  let hi = pagesList.length - 1;
  while (lo <= hi) {
    const mid = (lo + hi) >> 1;
    const p = pagesList[mid];
    if (t < p.start) hi = mid - 1;
    else if (t >= p.end) lo = mid + 1;
    else return p;
  }
  return null;
}

/** Index of the word being spoken at time t inside a page (the highlight). */
export function activeWord(page: Page, t: number): number {
  let idx = 0;
  page.words.forEach((w, i) => {
    if (t >= (i === 0 ? page.start : w.start)) idx = i;
  });
  return idx;
}

export function lineIndexAt(t: CTranscript, time: number): number {
  for (let i = 0; i < t.lines.length; i++) {
    const ln = t.lines[i];
    const next = t.lines[i + 1];
    if (time >= ln.start && time < (next ? Math.max(ln.end, Math.min(next.start, ln.end + 0.7)) : ln.end + 0.7)) return i;
  }
  return -1;
}

/** Captions in the translated language (mode "translation"): spread over each line's time. */
export function displayTranscript(t: CTranscript, mode: "original" | "translation" | "dual"): CTranscript {
  if (mode !== "translation" || !t.translation_lang) return t;
  const lang = t.translation_lang;
  return {
    ...t,
    language: lang,
    lines: t.lines.map((ln) => {
      if (!ln.translation) return { ...ln, translation: null };
      const words = retime(ln.words, splitText(ln.translation, lang), ln.start, ln.end);
      return refresh({ ...ln, words, translation: null }, lang);
    }),
  };
}

/* -------------------------------------------------------------------- misc */

export function formatTimecode(sec: number): string {
  const s = Math.max(0, sec);
  const m = Math.floor(s / 60);
  const r = s - m * 60;
  return `${m}:${r.toFixed(1).padStart(4, "0")}`;
}

export function hexToRgba(hex: string, alpha: number): string {
  const h = hex.replace("#", "");
  const n = parseInt(h.length === 3 ? h.split("").map((c) => c + c).join("") : h, 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}

export function wordCount(t: CTranscript): number {
  return t.lines.reduce((a, l) => a + l.words.length, 0);
}

export const FILLER = /^(u+h+m*|u+m+|h+m+|e+r+m*|a+h+|m{2,}|mhm|eh+|aa+h?)$/i;
export function isFiller(text: string): boolean {
  const k = text.replace(/^[\p{P}\p{S}\s]+|[\p{P}\p{S}\s]+$/gu, "").toLowerCase();
  return !!k && (FILLER.test(k) || ["ہمم", "امم", "اں", "आं", "उम्म", "हम्म"].includes(k));
}
