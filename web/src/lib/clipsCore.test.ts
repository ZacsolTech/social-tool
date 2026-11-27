/** Unit tests for the AI Clips helpers: `npm test` (Node's built-in test runner). */

import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  type TLine,
  clampRange,
  clock,
  lineAt,
  needsRender,
  overallProgress,
  parseClock,
  parseHashtags,
  postText,
  scoreTier,
  stepEdge,
  totalScore,
} from "./clipsCore.ts";

const LINES: TLine[] = [
  { i: 0, start: 0.5, end: 3.0, text: "Hello and welcome." },
  { i: 1, start: 3.6, end: 6.2, text: "Why do people never save?" },
  { i: 2, start: 7.0, end: 9.5, text: "The answer is simple." },
  { i: 3, start: 10.1, end: 14.0, text: "Save first, spend the rest." },
];

describe("scores", () => {
  it("weights match the server", () => {
    assert.equal(totalScore({ hook: 91, flow: 85, value: 80, trend: 70 }), 84);
    assert.equal(totalScore({ hook: 100, flow: 100, value: 100, trend: 100 }), 100);
    assert.equal(totalScore({ hook: 500 }), 35);
    assert.equal(totalScore({}), 0);
  });
  it("tiers", () => {
    assert.equal(scoreTier(90), "viral");
    assert.equal(scoreTier(72), "strong");
    assert.equal(scoreTier(60), "good");
    assert.equal(scoreTier(10), "fair");
  });
});

describe("time", () => {
  it("formats clocks", () => {
    assert.equal(clock(0), "0:00");
    assert.equal(clock(65.4), "1:05");
    assert.equal(clock(3725), "1:02:05");
    assert.equal(clock(12.34, true), "0:12.3");
    assert.equal(clock(-3), "-0:03");
  });
  it("parses clocks", () => {
    assert.equal(parseClock("1:05"), 65);
    assert.equal(parseClock("1:02:05"), 3725);
    assert.equal(parseClock("42.5"), 42.5);
    assert.equal(parseClock(""), null);
    assert.equal(parseClock("a:10"), null);
    assert.equal(parseClock("1::2"), null);
    assert.equal(parseClock("1:2:3:4"), null);
  });
  it("clamps ranges", () => {
    assert.deepEqual(clampRange({ start: 5, end: 6 }, 60), { start: 5, end: 8 });
    assert.deepEqual(clampRange({ start: 59, end: 60 }, 60), { start: 57, end: 60 });
    assert.deepEqual(clampRange({ start: 20, end: 10 }, 60), { start: 10, end: 20 });
    assert.deepEqual(clampRange({ start: -4, end: 999 }, 60, 3, 30), { start: 0, end: 30 });
  });
});

describe("transcript stepping", () => {
  it("finds the line at a time", () => {
    assert.equal(lineAt(LINES, 0), 0);
    assert.equal(lineAt(LINES, 4), 1);
    assert.equal(lineAt(LINES, 6.5), 2);
    assert.equal(lineAt(LINES, 99), 3);
    assert.equal(lineAt([], 3), -1);
  });
  it("moves a start or end by one sentence", () => {
    assert.equal(stepEdge(LINES, "start", 3.45, -1), 0.35);
    assert.equal(stepEdge(LINES, "start", 3.45, 1), 6.85);
    assert.equal(stepEdge(LINES, "start", 0.35, -1), 0.35);
    assert.equal(stepEdge(LINES, "end", 9.75, 1), 14.25);
    assert.equal(stepEdge(LINES, "end", 9.75, -1), 6.45);
    assert.equal(stepEdge([], "end", 4, 1), 4);
  });
});

describe("post text", () => {
  it("joins title, description and hashtags", () => {
    assert.equal(postText({ title: "Save money", description: " One rule. ", hashtags: ["#money", "#tips"] }), "Save money\n\nOne rule.\n\n#money #tips");
    assert.equal(postText({ title: "Only", description: "", hashtags: [] }), "Only");
  });
  it("parses hashtags", () => {
    assert.deepEqual(parseHashtags("money, #Save it  ,  x"), ["#money", "#Saveit", "#x"]);
    assert.deepEqual(parseHashtags("#a#b #a"), ["#a", "#b"]);
    assert.deepEqual(parseHashtags(""), []);
    assert.equal(parseHashtags("a,b,c,d,e,f,g,h,i,j").length, 8);
  });
});

describe("misc", () => {
  it("knows which edits re-render", () => {
    assert.equal(needsRender({ title: "x" }), false);
    assert.equal(needsRender({ hook: "x" }), true);
    assert.equal(needsRender({ start: 0 }), true);
    assert.equal(needsRender({ look: { captions: false } }), true);
  });
  it("progress", () => {
    assert.equal(overallProgress("ready", 0.3), 1);
    assert.equal(overallProgress("rendering", 1.4), 1);
    assert.equal(overallProgress("transcribing", 0.4), 0.4);
  });
});
