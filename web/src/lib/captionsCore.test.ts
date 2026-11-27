/** Unit tests for the caption editor/preview logic: `npm test` (Node's built-in test runner). */

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  type CTranscript,
  type CWord,
  activeWord,
  buildPages,
  confirmLine,
  deleteLine,
  displayTranscript,
  findReplace,
  isFiller,
  lineIndexAt,
  mergeWithNext,
  nextToCheck,
  pageAt,
  pages,
  refresh,
  retime,
  setLineEmoji,
  shiftLine,
  splitLine,
  splitText,
  toCheckCount,
  withText,
} from "./captionsCore.ts";

function words(text: string, start = 0, step = 0.3): CWord[] {
  return text.split(" ").map((t, i) => ({ text: t, start: start + i * step, end: start + i * step + step - 0.05 }));
}

function transcript(...lines: [string, number][]): CTranscript {
  return {
    language: "en",
    source: "ai",
    translation_lang: null,
    rev: 1,
    lines: lines.map(([text, start], i) => refresh({ id: `l${i}`, start: 0, end: 0, text: "", words: words(text, start) }, "en")),
  };
}

describe("retime", () => {
  it("keeps timings and flags when the word count is unchanged", () => {
    const ws = words("hello world");
    ws[1].keyword = true;
    const out = retime(ws, ["Hello", "World!"], 0, 0.55);
    assert.deepEqual(out.map((w) => [w.text, w.start, w.keyword]), [["Hello", 0, undefined], ["World!", 0.3, true]]);
  });
  it("spreads the line's time by word length otherwise", () => {
    const out = retime(words("a b"), ["one", "three", "x"], 1, 2);
    assert.equal(out[0].start, 1);
    assert.equal(out.at(-1)!.end, 2);
    assert.ok(out[1].end - out[1].start > out[2].end - out[2].start);
  });
});

describe("pages", () => {
  it("matches the backend's balanced split", () => {
    const ws = words("one two three four five six seven");
    const ps = pages(ws, 3, 40, "en");
    assert.equal(ps.flat().length, 7);
    assert.ok(ps.every((p) => p.length <= 3));
    assert.deepEqual(ps.map((p) => p.length), [2, 2, 3]);   // same as backend/app/captions/transcript.py
  });
  it("one word per page for the word-by-word animation", () => {
    const t = transcript(["a b c", 0]);
    assert.equal(buildPages(t, { max_words: 4, max_chars: 30, animation: "word" }).length, 3);
  });
  it("finds the page and spoken word at a time", () => {
    const t = transcript(["one two three four five six", 0.5]);
    const ps = buildPages(t, { max_words: 3, max_chars: 40, animation: "highlight" }, 10);
    assert.equal(ps.length, 2);
    const p = pageAt(ps, 0.95)!;
    assert.equal(p.words[0].text, "one");
    assert.equal(activeWord(p, 0.95), 1);
    assert.equal(pageAt(ps, 0.1), null);
    assert.equal(pageAt(ps, 9.9), null);
  });
});

describe("line editing", () => {
  const t = transcript(["Hello there my friend", 0], ["Second line", 3]);
  it("splits and merges lines", () => {
    const s = splitLine(t, 0, 2);
    assert.deepEqual(s.lines.map((l) => l.text), ["Hello there", "my friend", "Second line"]);
    assert.notEqual(s.lines[0].id, s.lines[1].id);
    const m = mergeWithNext(s, 0);
    assert.equal(m.lines[0].text, "Hello there my friend");
    assert.equal(m.lines[0].start, 0);
  });
  it("retypes, deletes and shifts lines", () => {
    const e = { ...t, lines: [withText(t.lines[0], "Hi there my good friend", "en"), t.lines[1]] };
    assert.equal(e.lines[0].words.length, 5);
    assert.equal(e.lines[0].end, t.lines[0].end);
    assert.equal(deleteLine(t, 0).lines.length, 1);
    const sh = shiftLine(t, 1, 0.5, 10);
    assert.equal(sh.lines[1].start, 3.5);
    const capped = shiftLine(t, 1, 0.5, 4.0);       // can't run past the end of the video
    assert.ok(Math.abs(capped.lines[1].end - 4.0) < 1e-9);
    assert.equal(shiftLine(t, 0, -5).lines[0].start, 0);
  });
  it("find and replace, emoji", () => {
    const r = findReplace(t, "hello", "Hey", false);
    assert.equal(r.count, 1);
    assert.equal(r.t.lines[0].words[0].text, "Hey");
    const e = setLineEmoji(t, 0, "🔥");
    assert.equal(e.lines[0].words.filter((w) => w.emoji).length, 1);
  });
  it("finds the line at a time", () => {
    assert.equal(lineIndexAt(t, 0.1), 0);
    assert.equal(lineIndexAt(t, 3.2), 1);
    assert.equal(lineIndexAt(t, 9), -1);
  });
});

describe("languages", () => {
  it("languages without spaces get two-character words", () => {
    assert.deepEqual(splitText("你好世界今天", "zh"), ["你好", "世界", "今天"]);
    assert.deepEqual(splitText("kya haal hai", "ur-Latn"), ["kya", "haal", "hai"]);
  });
  it("shows the translation as the captions", () => {
    const t = { ...transcript(["kya haal hai", 0]), translation_lang: "en" };
    t.lines[0] = { ...t.lines[0], translation: "How are you doing" };
    const d = displayTranscript(t, "translation");
    assert.equal(d.language, "en");
    assert.equal(d.lines[0].text, "How are you doing");
    assert.equal(d.lines[0].start, t.lines[0].start);
    assert.equal(displayTranscript(t, "dual"), t);
  });
  it("detects filler words", () => {
    for (const f of ["um", "Uhh,", "hmm...", "ہمم"]) assert.ok(isFiller(f), f);
    for (const w of ["umbrella", "hum", "the"]) assert.ok(!isFiller(w), w);
  });
});

describe("accuracy-check flags", () => {
  const flagged = (): CTranscript => {
    const t = transcript(["one two", 0], ["three four", 2], ["five six", 4], ["seven eight", 6]);
    t.lines[1].check = true;
    t.lines[3].check = true;
    return t;
  };

  it("counts and walks the flagged lines, wrapping around", () => {
    const t = flagged();
    assert.equal(toCheckCount(t), 2);
    assert.equal(nextToCheck(t, -1), 1);
    assert.equal(nextToCheck(t, 1), 3);
    assert.equal(nextToCheck(t, 3), 1);
    assert.equal(nextToCheck(transcript(["a b", 0]), 0), -1);
  });

  it("is cleared when the line is retyped or confirmed, kept otherwise", () => {
    const t = flagged();
    assert.equal(withText(t.lines[1], "three for", "en").check, false);
    const c = confirmLine(t, 3);
    assert.equal(c.lines[3].check, false);
    assert.equal(c.lines[1].check, true);
    assert.equal(t.lines[3].check, true); // not mutated
    assert.equal(shiftLine(t, 1, 0.1).lines[1].check, true);
  });
});
