"""Find the moments worth posting.

The transcript is cut into sentence-sized *lines* (with word timings). A text AI reads them with times and
returns line ranges, each with a title, an on-screen hook, a post description, hashtags and four scores.
Without an AI key (or when it fails) an offline scorer does the same job with text and pacing signals, so
the tool always works. Either way every clip is then *refined* the same way: snapped to sentence edges,
fitted to the chosen length, padded so no word is cut, and kept from overlapping a better clip.
"""

from __future__ import annotations

import logging
import math
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field

from ..captions import enhance, languages, llm
from ..captions.transcript import CLAUSE_END, SENTENCE_END, Line, Transcript

log = logging.getLogger("uvicorn.error")

# Clip length choices: (shortest, longest, ideal) in seconds.
LENGTHS: dict[str, tuple[float, float, float]] = {
    "auto": (20.0, 75.0, 45.0),
    "short": (12.0, 30.0, 22.0),
    "medium": (30.0, 60.0, 45.0),
    "long": (60.0, 90.0, 75.0),
    "xl": (90.0, 180.0, 120.0),
}
MAX_CLIPS = 12
WEIGHTS = {"hook": 0.35, "flow": 0.25, "value": 0.25, "trend": 0.15}
SCORE_KEYS = tuple(WEIGHTS)

_STRIP = re.compile(r"^[\W_]+|[\W_]+$", re.UNICODE)
# A clip that opens with one of these needs the sentence before it to make sense.
DANGLING = set("""and but so because also then plus or which who whom whose that's thats it's its they them he she him
her this these those there also anyway besides however therefore otherwise aur lekin magar to toh phir kyunki isliye
jo jis wo woh ye yeh""".split())
HOOK_PHRASES = (
    "how to", "how do", "how i", "why ", "what if", "the secret", "nobody", "no one", "everyone", "stop ", "never ",
    "the truth", "the biggest", "the best", "the worst", "mistake", "here's", "here is", "the reason", "did you know",
    "you need", "you won't", "you will", "you have to", "imagine", "the problem", "i was", "i lost", "i made",
    "i quit", "i never", "the one thing", "number one", "most people", "the real", "warning", "listen",
    "kya aap", "kabhi", "sab se", "sabse", "asal mein", "sach", "galti", "raaz",
)
EMOTION = set("""love hate angry cry crying laugh laughing funny hilarious scared afraid fear shocked shocking crazy insane
amazing incredible unbelievable beautiful terrible awful worst best dream died death kill killed broke broken rich poor
famous fired quit married divorce baby mom dad mother father family secret lie lied truth fight war win won lose lost
pyar dukh khushi dar ghussa maza""".split())
LAUGHTER = re.compile(r"\b(?:ha(?:ha)+|lol|lmao|\[laugh\w*\]|\(laugh\w*\))", re.I)


@dataclass
class Candidate:
    start_line: int
    end_line: int
    start: float
    end: float
    title: str = ""
    hook: str = ""
    description: str = ""
    hashtags: list[str] = field(default_factory=list)
    scores: dict[str, int] = field(default_factory=dict)
    reason: str = ""
    source: str = "auto"          # ai | auto

    @property
    def duration(self) -> float:
        return self.end - self.start

    @property
    def score(self) -> int:
        return total_score(self.scores)


def total_score(scores: dict[str, int]) -> int:
    return int(round(sum(WEIGHTS[k] * max(0, min(100, int(scores.get(k, 0)))) for k in WEIGHTS)))


def _key(text: str) -> str:
    return _STRIP.sub("", text).lower()


def lengths(name: str) -> tuple[float, float, float]:
    return LENGTHS.get(name, LENGTHS["auto"])


def auto_count(duration: float, lo: float) -> int:
    """How many clips to aim for when the visitor leaves it on Auto: about one per 2.5 minutes."""
    if duration < lo * 1.6:
        return 1
    return int(max(2, min(10, round(duration / 150), duration // max(lo, 1))))


# ---------------------------------------------------------------- refinement (shared by both finders)


def starts_sentence(lines: list[Line], i: int) -> bool:
    if i <= 0:
        return True
    prev = lines[i - 1]
    if lines[i].start - prev.end >= 0.6:
        return True
    return bool(prev.words and SENTENCE_END.search(prev.words[-1].text))


def ends_sentence(lines: list[Line], i: int) -> bool:
    if i >= len(lines) - 1:
        return True
    ln = lines[i]
    if lines[i + 1].start - ln.end >= 0.7:
        return True
    return bool(ln.words and SENTENCE_END.search(ln.words[-1].text))


def _span(lines: list[Line], s: int, e: int) -> float:
    return lines[e].end - lines[s].start


def refine(c: Candidate, lines: list[Line], lo: float, hi: float, duration: float) -> Candidate | None:
    """Fit a clip to [lo, hi] seconds on sentence edges, then pad its ends without cutting a word."""
    n = len(lines)
    if n == 0:
        return None
    s = max(0, min(n - 1, c.start_line))
    e = max(s, min(n - 1, c.end_line))
    # Too long: end earlier, preferably where a sentence ends.
    if _span(lines, s, e) > hi + 0.5:
        fits = [k for k in range(s, e + 1) if _span(lines, s, k) <= hi + 0.5]
        if not fits:
            fits = [s]
        clean = [k for k in fits if ends_sentence(lines, k) and _span(lines, s, k) >= lo * 0.8]
        e = clean[-1] if clean else fits[-1]
    # Too short: carry on to the next sentence end(s), else start earlier.
    if _span(lines, s, e) < lo - 0.5:
        k = e
        while k + 1 < n and _span(lines, s, k + 1) <= hi + 0.5 and (_span(lines, s, k) < lo or not ends_sentence(lines, k)):
            k += 1
        e = k
        while _span(lines, s, e) < lo - 0.5 and s > 0 and _span(lines, s - 1, e) <= hi + 0.5:
            s -= 1
            while s > 0 and not starts_sentence(lines, s) and _span(lines, s - 1, e) <= hi + 0.5:
                s -= 1
    start = lines[s].start
    end = lines[e].end
    # Padding: a breath before the first word and after the last, never into a neighbouring word.
    prev_end = lines[s - 1].end if s > 0 else 0.0
    next_start = lines[e + 1].start if e + 1 < n else duration
    start = max(0.0, prev_end + 0.02, start - 0.3) if s > 0 else max(0.0, start - 0.3)
    end = min(duration, next_start - 0.02, end + 0.45) if e + 1 < n else min(duration, end + 0.6)
    start = min(start, lines[s].start)
    end = max(end, min(duration, lines[e].end))
    if end - start < min(lo * 0.5, 5.0) and end - start < duration * 0.8:
        return None
    c.start_line, c.end_line, c.start, c.end = s, e, round(start, 3), round(end, 3)
    return c


def overlap(a: Candidate, b: Candidate) -> float:
    return max(0.0, min(a.end, b.end) - max(a.start, b.start))


def select(cands: list[Candidate], count: int) -> list[Candidate]:
    """Best first, no clip sharing more than a few seconds (or a quarter of itself) with a better one."""
    out: list[Candidate] = []
    for c in sorted(cands, key=lambda x: (-x.score, x.start)):
        if any(overlap(c, o) > min(3.0, 0.25 * min(c.duration, o.duration)) for o in out):
            continue
        out.append(c)
        if len(out) >= count:
            break
    return out


# ---------------------------------------------------------------- offline scorer


def _words(lines: list[Line], s: int, e: int) -> list[str]:
    return [w.text for ln in lines[s:e + 1] for w in ln.words]


def _first_text(lines: list[Line], s: int, seconds: float = 3.5) -> str:
    t0 = lines[s].start
    out = []
    for ln in lines[s:]:
        for w in ln.words:
            if w.start - t0 > seconds and out:
                return " ".join(out)
            out.append(w.text)
    return " ".join(out)


def hook_score(text: str) -> int:
    low = " " + text.lower().strip() + " "
    first = _key(text.split()[0]) if text.split() else ""
    s = 42
    if "?" in text or "؟" in text:
        s += 16
    if re.search(r"\d", text):
        s += 10
    if re.search(r"\b(you|your|aap|tum|tumhe|aapko)\b", low):
        s += 8
    if any(p in low for p in HOOK_PHRASES):
        s += 14
    keys = {_key(w) for w in text.split()}
    if keys & enhance.POWER:
        s += 8
    if keys & EMOTION:
        s += 6
    if "!" in text:
        s += 4
    if first in DANGLING:
        s -= 22
    return max(0, min(100, s))


def flow_score(lines: list[Line], s: int, e: int, ideal: float) -> int:
    sc = 50
    if starts_sentence(lines, s):
        sc += 12
    if ends_sentence(lines, e):
        sc += 18
    elif lines[e].words and CLAUSE_END.search(lines[e].words[-1].text):
        sc += 6
    long_pauses = sum(1 for k in range(s + 1, e + 1) if lines[k].start - lines[k - 1].end > 2.0)
    sc -= 8 * long_pauses
    d = _span(lines, s, e)
    sc += int(round(15 * math.exp(-abs(d - ideal) / max(ideal, 1.0))))
    first = _key(lines[s].words[0].text) if lines[s].words else ""
    if first in DANGLING:
        sc -= 10
    return max(0, min(100, sc))


def value_score(lines: list[Line], s: int, e: int) -> int:
    words = _words(lines, s, e)
    if not words:
        return 0
    d = max(1.0, _span(lines, s, e))
    wps = len(words) / d
    keys = [_key(w) for w in words]
    content = [k for k in keys if k and k not in enhance.STOPWORDS]
    sc = 30
    sc += int(max(0.0, 20 - 12 * abs(wps - 2.9)))                     # lively but clear pace
    sc += min(18, 3 * sum(1 for k in keys if k in enhance.POWER))
    sc += min(12, 3 * sum(1 for w in words if re.search(r"\d", w)))
    sc += min(10, int(40 * len(set(content)) / max(1, len(words))))  # says something, not filler
    sc += min(8, 2 * sum(1 for w in words if w.endswith(("!", "?", "؟"))))
    return max(0, min(100, sc))


def trend_score(lines: list[Line], s: int, e: int) -> int:
    words = _words(lines, s, e)
    text = " ".join(words)
    keys = {_key(w) for w in words}
    sc = 40
    sc += min(24, 6 * len(keys & EMOTION))
    sc += min(14, 7 * len(LAUGHTER.findall(text)))
    sc += min(12, 4 * len(keys & {"everyone", "nobody", "people", "world", "internet", "viral", "trend", "money",
                                  "sab", "log", "duniya"}))
    if re.search(r"\b(you|your|aap)\b", text.lower()):
        sc += 6
    return max(0, min(100, sc))


def _sub(lines: list[Line], s: int, e: int, lang: str) -> Transcript:
    return Transcript(language=lang, lines=lines[s:e + 1])


def title_from(text: str, max_words: int = 9) -> str:
    words = text.split()
    t = " ".join(words[:max_words]).strip(" ,.;:،۔-")
    if len(words) > max_words:
        t += "…"
    return t[:1].upper() + t[1:] if t else ""


def hashtags_from(lines: list[Line], s: int, e: int, n: int = 4) -> list[str]:
    counts: Counter[str] = Counter()
    for w in _words(lines, s, e):
        k = _key(w)
        if len(k) >= 4 and k not in enhance.STOPWORDS and not k.isdigit():
            counts[k] += 2 if k in enhance.POWER or k in EMOTION else 1
    tags = ["#" + re.sub(r"\W+", "", k) for k, _ in counts.most_common(n)]
    return [t for t in dict.fromkeys(tags) if len(t) > 2] + ["#shorts"]


def heuristic(lines: list[Line], lang: str, lo: float, hi: float, ideal: float, duration: float,
              topic: str | None = None) -> list[Candidate]:
    """Every sentence start is a possible clip start; each is grown to the best sentence end in range."""
    n = len(lines)
    topic_keys = {_key(w) for w in (topic or "").split() if len(_key(w)) >= 3} - enhance.STOPWORDS
    out: list[Candidate] = []
    for s in range(n):
        if not starts_sentence(lines, s):
            continue
        best: tuple[float, int] | None = None
        for e in range(s, n):
            d = _span(lines, s, e)
            if d > hi + 0.5:
                break
            if d < lo - 0.5:
                continue
            fit = -abs(d - ideal) / ideal + (0.35 if ends_sentence(lines, e) else 0.0)
            if best is None or fit > best[0]:
                best = (fit, e)
        if best is None:
            if s == 0 and _span(lines, 0, n - 1) < lo:     # the whole video is shorter than a clip
                best = (0.0, n - 1)
            else:
                continue
        e = best[1]
        opening = _first_text(lines, s)
        scores = {"hook": hook_score(opening), "flow": flow_score(lines, s, e, ideal), "value": value_score(lines, s, e),
                  "trend": trend_score(lines, s, e)}
        if topic_keys:
            hits = len(topic_keys & {_key(w) for w in _words(lines, s, e)})
            if not hits:
                continue
            scores["value"] = min(100, scores["value"] + 10 * hits)
        sub = _sub(lines, s, e, lang)
        hooks = enhance.suggest_hooks(sub, 1)
        first_sentence = lines[s].text(lang)
        c = Candidate(start_line=s, end_line=e, start=lines[s].start, end=lines[e].end,
                      title=title_from(first_sentence), hook=title_from(hooks[0] if hooks else first_sentence, 8),
                      description=title_from(" ".join(ln.text(lang) for ln in lines[s:min(e + 1, s + 3)]), 30),
                      hashtags=hashtags_from(lines, s, e), scores=scores, source="auto",
                      reason=_reason(scores))
        out.append(c)
    return out


def _reason(scores: dict[str, int]) -> str:
    best = max(SCORE_KEYS, key=lambda k: scores.get(k, 0))
    return {
        "hook": "Opens strong: the first seconds give viewers a reason to stay.",
        "flow": "A complete thought that makes sense on its own.",
        "value": "Packed with useful or surprising points.",
        "trend": "Emotional and relatable, the kind of moment people share.",
    }[best]


# ---------------------------------------------------------------- AI finder

_SYSTEM = (
    "You are a senior short-form video editor who has grown many TikTok, Reels and YouTube Shorts accounts. You get "
    "the transcript of a long video as numbered lines with their start and end times. Choose the moments that "
    "would perform best as stand-alone short clips.\n"
    "Rules for every clip:\n"
    "- It is one continuous range of lines, start_line to end_line (inclusive).\n"
    "- Its length (end time of end_line minus start time of start_line) is between min_seconds and max_seconds; aim "
    "for ideal_seconds when the content allows.\n"
    "- It makes complete sense to someone who has not seen the video: it must not open on a dangling reference "
    "('and', 'so', 'that', 'he said') and must not stop mid-thought. It ends on a payoff: the answer, the "
    "punchline, the conclusion or a strong statement.\n"
    "- The first sentence is a hook: a question, a bold claim, a surprising fact, a strong emotion, a conflict or a "
    "promise. Prefer starting one sentence later over a weak opening.\n"
    "- Clips must not overlap. Prefer variety: different topics or moments.\n"
    "- If a topic is given, only choose clips about that topic.\n"
    "Scores are integers 0-100 and must be honest (most clips land between 50 and 85; keep 90+ for exceptional "
    "moments): hook_score = how likely the first 3 seconds stop the scroll; flow_score = complete, coherent, makes "
    "sense alone; value_score = insight, emotion, humour or usefulness; trend_score = shareable, relatable, "
    "comment-worthy.\n"
    "Text fields use the transcript's own language and script (Roman Urdu stays in Latin letters): title = a "
    "catchy title of at most 60 characters; hook = on-screen text for the first seconds, at most 8 words, creating "
    "curiosity without lying; description = a 1-2 sentence post caption; hashtags = 3 to 6 relevant hashtags "
    "starting with #; reason = one short sentence on why this clip works."
)

_SCHEMA = {
    "type": "object",
    "properties": {"clips": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "start_line": {"type": "integer"}, "end_line": {"type": "integer"},
            "title": {"type": "string"}, "hook": {"type": "string"}, "description": {"type": "string"},
            "hashtags": {"type": "array", "items": {"type": "string"}},
            "hook_score": {"type": "integer"}, "flow_score": {"type": "integer"},
            "value_score": {"type": "integer"}, "trend_score": {"type": "integer"},
            "reason": {"type": "string"},
        },
        "required": ["start_line", "end_line", "title", "hook", "description", "hashtags", "hook_score",
                     "flow_score", "value_score", "trend_score", "reason"],
        "additionalProperties": False}}},
    "required": ["clips"], "additionalProperties": False,
}


def _clock(t: float) -> str:
    t = max(0, int(t))
    return f"{t // 3600}:{t % 3600 // 60:02d}:{t % 60:02d}" if t >= 3600 else f"{t // 60}:{t % 60:02d}"


def format_lines(lines: list[Line], lang: str, s: int, e: int) -> str:
    return "\n".join(f"L{i} [{_clock(lines[i].start)}-{_clock(lines[i].end)}] {lines[i].text(lang)}" for i in range(s, e))


def windows(lines: list[Line], budget_words: int, overlap_lines: int = 12) -> list[tuple[int, int]]:
    """Split the transcript into pieces of about budget_words words (overlapping, so no clip falls in a gap)."""
    out: list[tuple[int, int]] = []
    s = 0
    n = len(lines)
    while s < n:
        words, e = 0, s
        while e < n and (words < budget_words or e == s):
            words += len(lines[e].words)
            e += 1
        out.append((s, e))
        if e >= n:
            break
        s = max(s + 1, e - overlap_lines)
    return out


def _clean_text(v: object, limit: int) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip().strip('"')[:limit]


def _tags(v: object) -> list[str]:
    if not isinstance(v, list):
        return []
    out = []
    for t in v[:8]:
        t = re.sub(r"[\s#]+", "", str(t))
        if t:
            out.append("#" + t[:40])
    return list(dict.fromkeys(out))[:6]


def parse_ai(data: dict, lines: list[Line], s: int, e: int) -> list[Candidate]:
    out: list[Candidate] = []
    for row in data.get("clips", []) if isinstance(data, dict) else []:
        if not isinstance(row, dict):
            continue
        try:
            a, b = int(row.get("start_line")), int(row.get("end_line"))
        except (TypeError, ValueError):
            continue
        if b < a:
            a, b = b, a
        a, b = max(s, min(e - 1, a)), max(s, min(e - 1, b))
        scores = {}
        for k in SCORE_KEYS:
            try:
                scores[k] = max(0, min(100, int(row.get(f"{k}_score", 0))))
            except (TypeError, ValueError):
                scores[k] = 0
        out.append(Candidate(start_line=a, end_line=b, start=lines[a].start, end=lines[b].end,
                             title=_clean_text(row.get("title"), 90), hook=_clean_text(row.get("hook"), 80),
                             description=_clean_text(row.get("description"), 400), hashtags=_tags(row.get("hashtags")),
                             scores=scores, reason=_clean_text(row.get("reason"), 240), source="ai"))
    return out


def ai_find(lines: list[Line], lang: str, lo: float, hi: float, ideal: float, count: int, topic: str | None,
            title: str | None, cancelled: Callable[[], bool] = lambda: False,
            progress: Callable[[float], None] = lambda p: None) -> list[Candidate]:
    budget = 2200 if llm.provider() == "groq" else 30000     # Groq's free tier has a small tokens-per-minute limit
    parts = windows(lines, budget)
    total_words = sum(len(ln.words) for ln in lines) or 1
    lang_name = languages.info(lang).name
    out: list[Candidate] = []
    for k, (s, e) in enumerate(parts):
        if cancelled():
            break
        share = sum(len(ln.words) for ln in lines[s:e]) / total_words
        want = max(2, math.ceil(count * share * 1.6) + 1)
        payload = {
            "video_title": title or "", "language": lang_name, "topic": topic or "",
            "min_seconds": round(lo), "max_seconds": round(hi), "ideal_seconds": round(ideal),
            "clips_wanted": min(MAX_CLIPS, want), "transcript": format_lines(lines, lang, s, e),
        }
        try:
            data = llm._ask(_SYSTEM, payload, _SCHEMA)
        except llm.LlmError as err:
            log.info("clips AI window %d/%d failed: %s", k + 1, len(parts), err)
            if not out and k == len(parts) - 1:
                raise
            continue
        out.extend(parse_ai(data, lines, s, e))
        progress((k + 1) / len(parts))
    return out


def find(t: Transcript, duration: float, length: str = "auto", count: int | None = None, topic: str | None = None,
         title: str | None = None, use_ai: bool = True, cancelled: Callable[[], bool] = lambda: False,
         progress: Callable[[float], None] = lambda p: None) -> tuple[list[Candidate], str]:
    """The whole stage: candidates (AI or offline) -> refined -> best non-overlapping. Returns (clips, method)."""
    lines = [ln for ln in t.lines if ln.words]
    if not lines:
        return [], "none"
    lo, hi, ideal = lengths(length)
    span = lines[-1].end - lines[0].start
    if span < lo:        # short video: one clip, the whole talk
        lo, ideal = max(1.0, span * 0.6), span
    want = count or auto_count(duration, lo)
    method = "auto"
    cands: list[Candidate] = []
    if use_ai and llm.available():
        try:
            cands = ai_find(lines, t.language, lo, hi, ideal, want, topic, title, cancelled, progress)
            method = "ai"
        except llm.LlmError as e:
            log.info("clips AI finder unavailable, using the offline scorer: %s", e)
    refined = [r for c in cands if (r := refine(c, lines, lo, hi, duration))]
    picked = select(refined, want)
    if len(picked) < want:
        # Top up with the offline scorer (the AI may return too few, or none).
        extra = [r for c in heuristic(lines, t.language, lo, hi, ideal, duration, topic)
                 if (r := refine(c, lines, lo, hi, duration))]
        if method == "ai":
            for c in extra:
                c.scores = {k: max(0, v - 8) for k, v in c.scores.items()}   # rank below the AI's own picks
        picked = select(picked + extra, want) if picked else select(extra, want)
        if not cands:
            method = "auto"
    picked.sort(key=lambda c: (-c.score, c.start))
    progress(1.0)
    return picked, method
