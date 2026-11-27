/** Pure helpers for AI Clips (no React, no fetch): unit-tested in clipsCore.test.ts. */

export type ScoreKey = "hook" | "flow" | "value" | "trend";
export type Scores = Record<ScoreKey, number>;

export const SCORE_LABELS: Record<ScoreKey, { label: string; hint: string }> = {
  hook: { label: "Hook", hint: "How likely the first 3 seconds stop the scroll" },
  flow: { label: "Flow", hint: "A complete thought that makes sense on its own" },
  value: { label: "Value", hint: "Insight, emotion, humour or usefulness" },
  trend: { label: "Shareable", hint: "Relatable, the kind of clip people send to friends" },
};

export const WEIGHTS: Record<ScoreKey, number> = { hook: 0.35, flow: 0.25, value: 0.25, trend: 0.15 };

export function totalScore(s: Partial<Scores>): number {
  return Math.round((Object.keys(WEIGHTS) as ScoreKey[]).reduce((acc, k) => acc + WEIGHTS[k] * Math.max(0, Math.min(100, s[k] ?? 0)), 0));
}

export type Tier = "viral" | "strong" | "good" | "fair";

export function scoreTier(score: number): Tier {
  if (score >= 85) return "viral";
  if (score >= 72) return "strong";
  if (score >= 58) return "good";
  return "fair";
}

export const TIER_LABEL: Record<Tier, string> = { viral: "Viral potential", strong: "Strong", good: "Good", fair: "Fair" };

export type LengthId = "auto" | "short" | "medium" | "long" | "xl";

export const LENGTH_OPTIONS: { id: LengthId; label: string; hint: string }[] = [
  { id: "auto", label: "Auto", hint: "20–75 s, whatever fits each moment" },
  { id: "short", label: "< 30 s", hint: "12–30 s, punchy" },
  { id: "medium", label: "30–60 s", hint: "Reels & Shorts sweet spot" },
  { id: "long", label: "60–90 s", hint: "Room for a story" },
  { id: "xl", label: "90 s–3 min", hint: "TikTok long-form, YouTube" },
];

export function clock(sec: number, withTenths = false): string {
  const neg = sec < 0;
  const s = Math.abs(sec);
  const whole = Math.floor(s + (withTenths ? 0 : 0.5));
  const h = Math.floor(whole / 3600);
  const m = Math.floor((whole % 3600) / 60);
  const r = String(whole % 60).padStart(2, "0");
  const tenths = withTenths ? `.${Math.floor((s - Math.floor(s)) * 10 + 1e-6)}` : "";
  return `${neg ? "-" : ""}${h ? `${h}:${String(m).padStart(2, "0")}` : m}:${r}${tenths}`;
}

/** "0:42" "1:05:10" "12:3" -> seconds; null when it isn't a time. */
export function parseClock(v: string): number | null {
  const t = v.trim();
  if (!t) return null;
  const parts = t.split(":");
  if (parts.length > 3 || parts.some((p) => p === "" || Number.isNaN(Number(p)) || Number(p) < 0)) return null;
  return parts.reduce((acc, p) => acc * 60 + Number(p), 0);
}

export type TLine = { i: number; start: number; end: number; text: string };

/** Index of the transcript line a time falls in (or the nearest one after it). */
export function lineAt(lines: TLine[], t: number): number {
  if (!lines.length) return -1;
  let lo = 0;
  let hi = lines.length - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (lines[mid].end < t) lo = mid + 1;
    else hi = mid;
  }
  return lo;
}

/** Move a clip edge by whole sentences: -1 = one sentence earlier, +1 = one later. */
export function stepEdge(lines: TLine[], edge: "start" | "end", value: number, dir: -1 | 1): number {
  if (!lines.length) return value;
  const at = (k: number) => (edge === "start" ? lines[k].start : lines[k].end);
  let cur = 0;
  for (let k = 1; k < lines.length; k++) if (Math.abs(at(k) - value) < Math.abs(at(cur) - value)) cur = k;
  const k = Math.max(0, Math.min(lines.length - 1, cur + dir));
  return edge === "start" ? Math.max(0, lines[k].start - 0.15) : lines[k].end + 0.25;
}

export type Range = { start: number; end: number };

export function clampRange(r: Range, duration: number, min = 3, max = 300): Range {
  let start = Math.max(0, Math.min(r.start, duration));
  let end = Math.max(0, Math.min(r.end, duration));
  if (end < start) [start, end] = [end, start];
  if (end - start < min) end = Math.min(duration, start + min);
  if (end - start < min) start = Math.max(0, end - min);
  if (end - start > max) end = start + max;
  return { start: round3(start), end: round3(end) };
}

const round3 = (v: number) => Math.round(v * 1000) / 1000;

/** The text people paste under the post: title, description and hashtags. */
export function postText(c: { title: string; description: string; hashtags: string[] }): string {
  return [c.title, c.description, c.hashtags.join(" ")].map((x) => x.trim()).filter(Boolean).join("\n\n");
}

/** "money, #Save it  ,  x" -> ["#money", "#Saveit", "#x"] (max 8, no duplicates). */
export function parseHashtags(v: string): string[] {
  const out: string[] = [];
  for (const raw of v.split(/[,\n]|(?=#)/)) {
    const t = raw.replace(/[#\s]+/g, "");
    if (t && !out.includes(`#${t}`)) out.push(`#${t}`);
  }
  return out.slice(0, 8);
}

/** Which clip edits need a new video (vs. only text that lives next to the video). */
export function needsRender(patch: Record<string, unknown>): boolean {
  return ["start", "end", "hook", "look", "render"].some((k) => patch[k] !== undefined && patch[k] !== null);
}

export function overallProgress(state: string, progress: number): number {
  return state === "ready" ? 1 : Math.max(0, Math.min(1, progress));
}
