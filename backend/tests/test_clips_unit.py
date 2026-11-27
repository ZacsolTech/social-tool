"""Unit tests for AI Clips: the moment finder (AI + offline), refinement, ranking, clip transcripts and snapping.

No video, network or AI service: the AI is a deterministic fake.
"""

from __future__ import annotations

import pytest

from app.captions import llm
from app.captions.transcript import Line, Transcript, Word
from app.clips import finder, jobs
from app.clips import render as crender
from app.reframe.media import MediaInfo

SENTENCES = [
    "Hello and welcome back to the show.",                                   # 0
    "So today we talk about saving.",                                       # 1
    "Why do most people never save money?",                                 # 2  strong hook
    "The answer is simple and it surprised me.",                            # 3
    "You spend first and save whatever is left.",                           # 4
    "Flip it and save twenty percent the day you get paid.",                # 5
    "That one change made me rich in five years.",                          # 6  payoff
    "and then we went to the shop and it was fine",                         # 7  dangling, no punctuation
    "and the weather was okay too I guess",                                 # 8
    "Here's the biggest mistake I made with my first business.",            # 9  strong hook
    "I hired friends instead of experts.",                                  # 10
    "It cost me ten thousand dollars and two years.",                       # 11
    "Never hire someone you can't fire.",                                   # 12 payoff
    "Anyway that is all for today, thanks for watching.",                   # 13
]


def make_transcript(sentences=SENTENCES, word=0.35, pause=0.5, lang="en") -> Transcript:
    lines, t = [], 0.5
    for s in sentences:
        words = []
        for w in s.split():
            words.append(Word(w, t, t + word - 0.03))
            t += word
        lines.append(Line(words=words, id=f"l{len(lines)}"))
        t += pause
    return Transcript(language=lang, lines=lines)


@pytest.fixture
def t() -> Transcript:
    return make_transcript()


def cand(s: int, e: int, lines: list[Line], score: int = 60) -> finder.Candidate:
    return finder.Candidate(s, e, lines[s].start, lines[e].end, scores={k: score for k in finder.SCORE_KEYS})


# ---------------------------------------------------------------- basics


def test_total_score_is_the_weighted_mix():
    assert finder.total_score({"hook": 100, "flow": 100, "value": 100, "trend": 100}) == 100
    assert finder.total_score({"hook": 100, "flow": 0, "value": 0, "trend": 0}) == 35
    assert finder.total_score({"hook": 500, "flow": -5}) == 35          # clamped
    assert abs(sum(finder.WEIGHTS.values()) - 1) < 1e-9


def test_lengths_and_auto_count():
    assert finder.lengths("short") == finder.LENGTHS["short"]
    assert finder.lengths("nonsense") == finder.LENGTHS["auto"]
    assert finder.auto_count(20, 20) == 1                  # shorter than 1.6 clips: one clip
    assert finder.auto_count(60, 20) == 2
    assert finder.auto_count(30 * 60, 20) == 10            # half an hour: capped at 10... one per 2.5 min = 12
    assert finder.auto_count(10 * 60, 20) == 4
    assert 1 <= finder.auto_count(3 * 3600, 90) <= 10


def test_sentence_edges(t):
    lines = t.lines
    assert finder.starts_sentence(lines, 0)
    assert finder.starts_sentence(lines, 3)                # previous ends with "?"
    assert not finder.starts_sentence(lines, 8)            # previous line "...it was fine" has no full stop
    assert finder.ends_sentence(lines, 2) and finder.ends_sentence(lines, len(lines) - 1)
    lines[8].words[0].start += 1.0                         # a long pause also counts as a sentence edge
    assert finder.starts_sentence(lines, 8)


def test_scores_reward_hooks_and_punish_dangling_openings():
    strong = finder.hook_score("Why do most people never save money?")
    weak = finder.hook_score("and then we went to the shop")
    assert strong >= 75 and weak <= 30 and strong > weak
    assert finder.hook_score("") >= 0
    assert finder.hook_score("You need 3 things to win!") > finder.hook_score("The weather was okay")


# ---------------------------------------------------------------- refinement


def test_refine_shortens_long_clips_at_a_sentence_end(t):
    lines = t.lines
    c = finder.refine(cand(2, 13, lines), lines, lo=8, hi=16, duration=60)
    assert c is not None
    assert c.end - c.start <= 16 + 1.2
    assert finder.ends_sentence(lines, c.end_line)
    assert c.start_line == 2


def test_refine_extends_short_clips_and_pads_without_touching_neighbours(t):
    lines = t.lines
    c = finder.refine(cand(2, 2, lines), lines, lo=10, hi=20, duration=60)
    assert c is not None and c.end - c.start >= 10 - 0.6
    assert c.start <= lines[c.start_line].start and c.start >= lines[c.start_line - 1].end
    assert c.end >= lines[c.end_line].end
    if c.end_line + 1 < len(lines):
        assert c.end <= lines[c.end_line + 1].start


def test_refine_clamps_bad_indices_and_handles_the_video_edges(t):
    lines = t.lines
    c = finder.refine(cand(0, 0, lines), lines, lo=1, hi=5, duration=60)
    assert c.start >= 0
    c = finder.refine(finder.Candidate(50, 99, 0, 0, scores={}), lines, lo=1, hi=8, duration=lines[-1].end + 0.2)
    assert c is not None and c.end_line == len(lines) - 1 and c.end <= lines[-1].end + 0.2 + 1e-6
    assert finder.refine(cand(0, 0, lines), [], 1, 5, 60) is None


def test_select_keeps_the_best_non_overlapping(t):
    lines = t.lines
    a, b, c = cand(2, 6, lines, 80), cand(3, 6, lines, 70), cand(9, 12, lines, 60)
    picked = finder.select([b, c, a], 5)
    assert picked == [a, c]
    assert finder.select([a, b, c], 1) == [a]


# ---------------------------------------------------------------- offline finder


def test_heuristic_prefers_hooks_and_complete_thoughts(t):
    lo, hi, ideal = 6.0, 20.0, 12.0
    cands = finder.heuristic(t.lines, "en", lo, hi, ideal, 60)
    assert cands and all(lo - 0.6 <= c.end - c.start <= hi + 0.6 for c in cands)
    best = finder.select(cands, 2)
    starts = {c.start_line for c in best}
    assert starts & {2, 9}, [(c.start_line, c.score, c.title) for c in best]
    assert all(c.title and c.hook and c.hashtags and c.reason for c in best)
    assert all(h.startswith("#") for c in best for h in c.hashtags)
    assert not any(c.start_line in (8,) for c in cands)         # never starts mid-sentence


def test_heuristic_topic_filter(t):
    cands = finder.heuristic(t.lines, "en", 6, 20, 12, 60, topic="business experts")
    assert cands and all(any(w in " ".join(w2.text for ln in t.lines[c.start_line:c.end_line + 1] for w2 in ln.words).lower()
                             for w in ("business", "experts")) for c in cands)


def test_find_offline_end_to_end(t, monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: False)
    clips, method = finder.find(t, 60, "short", count=2)
    assert method == "auto" and 1 <= len(clips) <= 2
    assert clips == sorted(clips, key=lambda c: -c.score)
    for a in clips:
        for b in clips:
            if a is not b:
                assert finder.overlap(a, b) <= 3.0


def test_find_short_video_gives_one_whole_clip(monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: False)
    t = make_transcript(SENTENCES[2:5])
    clips, _ = finder.find(t, t.lines[-1].end + 0.5, "medium")
    assert len(clips) == 1
    assert clips[0].start_line == 0 and clips[0].end_line == 2


def test_find_empty_transcript():
    assert finder.find(Transcript(language="en", lines=[]), 10) == ([], "none")


# ---------------------------------------------------------------- AI finder


def ai_answer(rows):
    return {"clips": [{"start_line": a, "end_line": b, "title": f"Title {a}", "hook": f"Hook {a}",
                       "description": "desc", "hashtags": ["money", "#Save Money", ""], "hook_score": hs,
                       "flow_score": 80, "value_score": 70, "trend_score": 60, "reason": "why"}
                      for a, b, hs in rows]}


def test_parse_ai_validates_everything(t):
    lines = t.lines
    data = {"clips": [
        {"start_line": 6, "end_line": 2, "hook_score": "90", "flow_score": None, "hashtags": "nope"},  # reversed
        {"start_line": -5, "end_line": 400, "title": "  x  " * 50, "hook_score": 900},                  # out of range
        {"start_line": "a", "end_line": 3},                                                             # unusable
        "junk",
    ]}
    out = finder.parse_ai(data, lines, 0, len(lines))
    assert len(out) == 2
    assert (out[0].start_line, out[0].end_line) == (2, 6)
    assert out[0].scores["hook"] == 90 and out[0].scores["flow"] == 0 and out[0].hashtags == []
    assert (out[1].start_line, out[1].end_line) == (0, len(lines) - 1) and out[1].scores["hook"] == 100
    assert len(out[1].title) <= 90
    assert finder.parse_ai([], lines, 0, 3) == []
    assert finder._tags(["#a b", "a b", "c", "", "#"]) == ["#ab", "#c"]


def test_windows_cover_everything_with_overlap(t):
    w = finder.windows(t.lines, budget_words=20, overlap_lines=2)
    assert w[0][0] == 0 and w[-1][1] == len(t.lines)
    for (s0, e0), (s1, e1) in zip(w, w[1:]):
        assert s1 < e0 and s1 > s0
    assert finder.windows(t.lines, 10_000) == [(0, len(t.lines))]


def test_ai_find_used_when_available(t, monkeypatch):
    seen = []

    def ask(system, payload, schema):
        seen.append(payload)
        assert "L2 [" in payload["transcript"] and payload["min_seconds"] >= 1
        return ai_answer([(2, 6, 92), (9, 12, 70)])

    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "provider", lambda: "claude")
    monkeypatch.setattr(llm, "_ask", ask)
    clips, method = finder.find(t, 60, "short", count=2, topic="money", title="My podcast")
    assert method == "ai" and len(seen) == 1
    assert seen[0]["topic"] == "money" and seen[0]["video_title"] == "My podcast"
    assert [c.title for c in clips] == ["Title 2", "Title 9"]
    assert clips[0].hashtags == ["#money", "#SaveMoney"]
    assert clips[0].source == "ai"


def test_ai_failure_falls_back_to_offline(t, monkeypatch):
    def ask(*a, **k):
        raise llm.LlmError("down")
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "provider", lambda: "groq")
    monkeypatch.setattr(llm, "_ask", ask)
    clips, method = finder.find(t, 60, "short", count=2)
    assert method == "auto" and clips


def test_too_few_ai_clips_are_topped_up_below_the_ai_ones(t, monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "provider", lambda: "claude")
    monkeypatch.setattr(llm, "_ask", lambda *a, **k: ai_answer([(9, 12, 40)]))
    clips, method = finder.find(t, 60, "short", count=3)
    assert method == "ai" and len(clips) >= 2
    assert any(c.source == "ai" for c in clips) and any(c.source == "auto" for c in clips)


def test_groq_splits_long_transcripts_and_survives_a_failed_window(monkeypatch):
    long = make_transcript(SENTENCES * 70)
    calls = []

    def ask(system, payload, schema):
        calls.append(payload)
        if len(calls) == 2:
            raise llm.LlmError("rate limit")
        first = int(payload["transcript"].split("]", 1)[0][1:].split(" ")[0])
        return ai_answer([(first + 2, first + 6, 85)])

    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "provider", lambda: "groq")
    monkeypatch.setattr(llm, "_ask", ask)
    clips, method = finder.find(long, long.lines[-1].end, "short", count=4)
    assert len(calls) >= 3 and method == "ai" and len(clips) == 4


# ---------------------------------------------------------------- clip transcript, snapping, look


def test_clip_transcript_is_relative_and_trimmed(t):
    start, end = t.lines[2].start - 0.2, t.lines[3].end + 0.1
    sub = crender.clip_transcript(t, start, end)
    words = sub.words()
    assert words[0].text == "Why" and abs(words[0].start - 0.2) < 1e-6
    assert words[-1].text == "me."
    assert all(0 <= w.start < w.end <= end - start + 1e-6 for w in words)
    assert crender.clip_transcript(t, 1000, 1010).lines == []


def test_snap_never_cuts_a_word(t):
    w = t.lines[2].words[1]
    mid = (w.start + w.end) / 2
    s, e = jobs.snap(t, mid, mid + 5, 60)
    assert s <= w.start and s >= t.lines[2].words[0].end
    assert not any(x.start < e < x.end for x in t.words())
    assert jobs.snap(None, -5, 999, 60) == (0.0, 60.0)


def test_effective_aspect_keeps_vertical_sources():
    tall = MediaInfo(10, 1080, 1920, 30, "30", True, "h264", 0, False, 1)
    wide = MediaInfo(10, 1920, 1080, 30, "30", True, "h264", 0, False, 1)
    assert crender.effective_aspect(tall, "9:16") == "original"
    assert crender.effective_aspect(tall, "1:1") == "1:1"
    assert crender.effective_aspect(wide, "9:16") == "9:16"
    assert crender.effective_aspect(wide, "original") == "original"


def test_needs_burn_and_frame_key():
    lk = crender.ClipLook(captions=False, hook=False)
    assert not crender.needs_burn(lk, "hook", True)
    assert crender.needs_burn(crender.ClipLook(captions=True), None, True)
    assert not crender.needs_burn(crender.ClipLook(captions=True, hook=False), None, False)
    assert crender.needs_burn(crender.ClipLook(captions=False, hook=True), "Watch this", False)
    a = crender.ClipLook().frame_key(1, 2)
    assert a == crender.ClipLook(captions=False, hook=False).frame_key(1, 2)     # words don't change the frame
    assert a != crender.ClipLook(layout="blur").frame_key(1, 2)
