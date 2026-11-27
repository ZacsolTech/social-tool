"""Transcript model: words with timings grouped into lines, plus SRT/VTT/TXT import and export.

A *line* is one row in the editor (about a sentence). When rendering, each line is split again into
short *pages* (a few words) that are shown on screen one after another.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import asdict, dataclass, field
from typing import Any

NO_SPACE_LANGS = {"zh", "ja", "th", "lo", "my", "km", "yue"}
SENTENCE_END = re.compile(r"[.!?…۔؟।॥。！？]+[\"'”’)\]]*$")
CLAUSE_END = re.compile(r"[,;:،؛、，]+$")


@dataclass
class Word:
    text: str
    start: float
    end: float
    keyword: bool = False
    emoji: str | None = None
    prob: float = 1.0                        # speech-to-text confidence (0-1); internal, not saved

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"text": self.text, "start": round(self.start, 3), "end": round(self.end, 3)}
        if self.keyword:
            d["keyword"] = True
        if self.emoji:
            d["emoji"] = self.emoji
        return d


@dataclass
class Line:
    words: list[Word]
    id: str = field(default_factory=lambda: secrets.token_hex(4))
    translation: str | None = None
    check: bool = False                      # the AI check wasn't sure: worth a human look

    @property
    def start(self) -> float:
        return self.words[0].start if self.words else 0.0

    @property
    def end(self) -> float:
        return self.words[-1].end if self.words else 0.0

    def text(self, lang: str | None = None) -> str:
        return joiner(lang).join(w.text for w in self.words)

    def to_dict(self, lang: str | None = None) -> dict[str, Any]:
        d: dict[str, Any] = {"id": self.id, "start": round(self.start, 3), "end": round(self.end, 3),
                             "text": self.text(lang), "words": [w.to_dict() for w in self.words]}
        if self.translation:
            d["translation"] = self.translation
        if self.check:
            d["check"] = True
        return d


@dataclass
class Transcript:
    language: str
    lines: list[Line]
    source: str = "ai"                       # ai | srt | reused
    translation_lang: str | None = None      # language of Line.translation
    rev: int = 0

    def words(self) -> list[Word]:
        return [w for ln in self.lines for w in ln.words]

    def to_dict(self) -> dict[str, Any]:
        return {"language": self.language, "source": self.source, "translation_lang": self.translation_lang,
                "rev": self.rev, "lines": [ln.to_dict(self.language) for ln in self.lines]}

    def copy(self) -> Transcript:
        return from_dict(self.to_dict())


def joiner(lang: str | None) -> str:
    return "" if (lang or "").split("-")[0] in NO_SPACE_LANGS else " "


def from_dict(d: dict[str, Any]) -> Transcript:
    lines = []
    for ln in d.get("lines") or []:
        words = [Word(text=str(w.get("text", "")), start=float(w.get("start", 0)), end=float(w.get("end", 0)),
                      keyword=bool(w.get("keyword", False)), emoji=(w.get("emoji") or None))
                 for w in ln.get("words") or []]
        lines.append(Line(words=words, id=str(ln.get("id") or secrets.token_hex(4))[:16],
                          translation=(ln.get("translation") or None), check=bool(ln.get("check", False))))
    return Transcript(language=str(d.get("language") or "en"), lines=lines, source=str(d.get("source") or "ai"),
                      translation_lang=d.get("translation_lang") or None, rev=int(d.get("rev") or 0))


# ---------------------------------------------------------------- building lines


def clean_word(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def build_lines(words: list[Word], lang: str | None = None, max_words: int = 12, max_chars: int = 70,
                max_dur: float = 7.0, gap: float = 0.8, breaks: list[float] | None = None) -> list[Line]:
    """Group a stream of timed words into editor lines (roughly sentences). `breaks`: times where the speech
    recogniser started a new sentence (its segments); a line never runs across one."""
    lines: list[Line] = []
    cur: list[Word] = []
    chars = 0
    sep = len(joiner(lang))
    bounds = sorted(breaks or [])
    bi = 0
    for w in words:
        w.text = clean_word(w.text)
        if not w.text:
            continue
        crossed = False
        while bi < len(bounds) and bounds[bi] <= w.start + 0.05:
            crossed = crossed or (bool(cur) and bounds[bi] > cur[-1].start + 0.05)
            bi += 1
        if cur:
            pause = w.start - cur[-1].end
            too_long = (len(cur) >= max_words or chars + sep + len(w.text) > max_chars
                        or w.end - cur[0].start > max_dur)
            if pause > gap or too_long or (crossed and len(cur) >= 2):
                lines.append(Line(words=cur))
                cur, chars = [], 0
        cur.append(w)
        chars += len(w.text) + (sep if len(cur) > 1 else 0)
        if SENTENCE_END.search(w.text) and len(cur) >= 2:
            lines.append(Line(words=cur))
            cur, chars = [], 0
        elif CLAUSE_END.search(w.text) and len(cur) >= max_words * 0.6:
            lines.append(Line(words=cur))
            cur, chars = [], 0
    if cur:
        lines.append(Line(words=cur))
    return lines


def normalize(t: Transcript, duration: float | None = None) -> Transcript:
    """Make timings safe: sorted, inside the video, no overlaps, every word at least 40 ms long."""
    words_seen = 0
    for ln in t.lines:
        ln.words = [w for w in ln.words if clean_word(w.text)]
        for w in ln.words:
            w.text = clean_word(w.text)[:80]
            w.start = max(0.0, float(w.start))
            w.end = max(w.start + 0.04, float(w.end))
            if duration:
                w.start = min(w.start, max(0.0, duration - 0.04))
                w.end = min(w.end, duration)
                if w.end <= w.start:
                    w.end = w.start + 0.04
            if w.emoji:
                w.emoji = w.emoji[:8]
        words_seen += len(ln.words)
        if ln.translation is not None:
            ln.translation = clean_word(ln.translation)[:400] or None
    t.lines = sorted((ln for ln in t.lines if ln.words), key=lambda ln: ln.start)
    prev_end = 0.0
    for ln in t.lines:
        for w in ln.words:
            if w.start < prev_end - 0.001:
                shift = prev_end - w.start
                w.start = prev_end
                w.end = max(w.end, w.start + 0.04) if shift < 1 else w.start + max(0.04, w.end - w.start - shift)
            prev_end = w.end
    return t


def retime(words: list[Word], texts: list[str], start: float, end: float) -> list[Word]:
    """New word texts for a line. Same count: keep each word's timing. Otherwise spread the line's time
    over the new words by their length (the editor uses this when a line is retyped)."""
    texts = [clean_word(x) for x in texts if clean_word(x)]
    if not texts:
        return []
    if len(texts) == len(words):
        return [Word(text=t, start=w.start, end=w.end, keyword=w.keyword, emoji=w.emoji) for t, w in zip(texts, words)]
    total = sum(max(1, len(x)) for x in texts)
    span = max(0.05 * len(texts), end - start)
    out, t0 = [], start
    for x in texts:
        d = span * max(1, len(x)) / total
        out.append(Word(text=x, start=t0, end=t0 + d))
        t0 += d
    return out


def split_text(text: str, lang: str | None) -> list[str]:
    text = clean_word(text)
    if not text:
        return []
    if joiner(lang) == "":
        # Languages without spaces: one "word" per 2 characters keeps word-by-word effects sensible.
        chars = [c for c in text if not c.isspace()]
        return ["".join(chars[i:i + 2]) for i in range(0, len(chars), 2)]
    return text.split(" ")


def pages(line: Line, max_words: int, max_chars: int, lang: str | None = None) -> list[list[Word]]:
    """Split a line into on-screen pages of at most max_words words / max_chars characters, balanced
    so the last page isn't a single orphan word."""
    words = line.words
    if not words:
        return []
    sep = len(joiner(lang))
    n = len(words)
    total_chars = sum(len(w.text) for w in words) + sep * (n - 1)
    k = max(-(-n // max(1, max_words)), -(-total_chars // max(1, max_chars)))
    k = max(1, min(k, n))
    out: list[list[Word]] = []
    i = 0
    for p in range(k):
        left_pages = k - p
        take = max(1, round((n - i) / left_pages))
        chunk = words[i:i + take]
        # Prefer breaking after punctuation when it's close by.
        if p < k - 1 and len(chunk) > 2:
            for j in range(len(chunk) - 1, max(0, len(chunk) - 3), -1):
                if SENTENCE_END.search(chunk[j - 1].text) or CLAUSE_END.search(chunk[j - 1].text):
                    chunk = chunk[:j]
                    break
        out.append(chunk)
        i += len(chunk)
        if i >= n:
            break
    if i < n:
        out[-1].extend(words[i:])
    return [p for p in out if p]


# ---------------------------------------------------------------- export


def _ts(t: float, sep: str) -> str:
    ms = int(round(max(0.0, t) * 1000))
    h, ms = divmod(ms, 3600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}{sep}{ms:03d}"


def cue_texts(t: Transcript, mode: str) -> list[tuple[float, float, str]]:
    """mode: original | translation | dual."""
    out = []
    for ln in t.lines:
        orig = ln.text(t.language)
        if mode == "translation":
            txt = ln.translation or orig
        elif mode == "dual" and ln.translation:
            txt = f"{orig}\n{ln.translation}"
        else:
            txt = orig
        out.append((ln.start, max(ln.end, ln.start + 0.3), txt))
    return out


def to_srt(t: Transcript, mode: str = "original") -> str:
    parts = []
    for i, (s, e, txt) in enumerate(cue_texts(t, mode), 1):
        parts.append(f"{i}\n{_ts(s, ',')} --> {_ts(e, ',')}\n{txt}\n")
    return "\n".join(parts)


def to_vtt(t: Transcript, mode: str = "original") -> str:
    parts = ["WEBVTT\n"]
    for s, e, txt in cue_texts(t, mode):
        parts.append(f"{_ts(s, '.')} --> {_ts(e, '.')}\n{txt}\n")
    return "\n".join(parts)


def to_txt(t: Transcript, mode: str = "original") -> str:
    return "\n".join(txt for _, _, txt in cue_texts(t, mode)) + "\n"


# ---------------------------------------------------------------- import

_TIME = re.compile(r"(?:(\d+):)?(\d{1,2}):(\d{1,2})[.,](\d{1,3})")
_ARROW = re.compile(r"(\S+)\s*-->\s*(\S+)")


def _parse_time(s: str) -> float | None:
    m = _TIME.fullmatch(s.strip())
    if not m:
        return None
    h, mi, se, ms = m.groups()
    return int(h or 0) * 3600 + int(mi) * 60 + int(se) + int(ms.ljust(3, "0")) / 1000


def parse_subtitles(text: str, lang: str | None = None) -> list[Line]:
    """SRT or WebVTT -> lines (words get evenly spread timings inside each cue)."""
    text = text.replace("﻿", "").replace("\r\n", "\n").replace("\r", "\n")
    lines: list[Line] = []
    for block in re.split(r"\n\s*\n", text):
        rows = [r for r in block.split("\n") if r.strip()]
        for i, row in enumerate(rows):
            m = _ARROW.search(row)
            if not m:
                continue
            s, e = _parse_time(m.group(1)), _parse_time(m.group(2))
            if s is None or e is None or e <= s:
                break
            body = " ".join(re.sub(r"<[^>]+>|\{\\[^}]*\}", "", r).strip() for r in rows[i + 1:])
            words = retime([], split_text(body, lang), s, e)
            if words:
                lines.append(Line(words=words))
            break
    return lines
