"""Accuracy layer for AI captions: listen twice, let an AI judge settle the differences, flag what's still unsure.

1. Second listen: the same audio goes through a *different* speech model (Groq turbo <-> large-v3, or
   Cloudflare). Two models rarely make the same mistake, so where they agree the words are almost surely right.
2. AI judge: only the lines where the two listens differ, or where the first model itself wasn't confident,
   go to a text AI with both versions, the neighbouring lines, the title and the visitor's hints. It writes
   what was most likely spoken, may add a dropped word or remove an invented one, and says if it was sure.
   Speech that only the second listen caught (a sentence the first one skipped) is offered to the judge too.
3. Guards: an answer that wanders too far from both listens (a paraphrase, a translation) is thrown away.
   Kept words keep their exact timing; new words get their timing from the second listen or their neighbours.
4. Lines the judge wasn't sure about, or where the listens disagree and no AI was available, get
   `check=True`: the editor shows them so a person can play and fix just those.
"""

from __future__ import annotations

import bisect
import difflib
import logging
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..config import get_settings
from . import languages, llm, stt
from .transcript import Line, Transcript, Word, joiner, split_text

log = logging.getLogger("uvicorn.error")
PAD = 0.35            # a second-listen word belongs to a line when it's this close to it (seconds)
CONTEXT_WORDS = 8     # words of the neighbouring lines sent along as context


@dataclass
class Report:
    listens: int = 1
    second: str | None = None        # model of the second listen
    ai: bool = False                 # the AI judge ran
    lines: int = 0                   # lines looked at
    agreed: int = 0                  # lines both listens heard the same way
    checked: int = 0                 # lines the AI judge looked at
    fixed_lines: int = 0
    fixed_words: int = 0
    added_lines: int = 0             # speech the first listen skipped, put back
    removed_lines: int = 0           # invented lines taken out
    flagged: int = 0                 # lines left for a person to check

    def public(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


# ---------------------------------------------------------------- comparing text


def key(text: str) -> str:
    """A word as compared: same letters, ignoring case, punctuation and symbols."""
    t = unicodedata.normalize("NFKC", text).casefold()
    return "".join(ch for ch in t if unicodedata.category(ch)[0] not in "PSZ")


def units(text: str, lang: str | None) -> list[str]:
    """Comparable pieces of a text: words, or characters in languages written without spaces."""
    if joiner(lang) == "":
        return list(key(text))
    return [k for k in (key(x) for x in text.split()) if k]


def ratio(a: list[str], b: list[str]) -> float:
    if not a and not b:
        return 1.0
    return difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()


def plausible(text: str, heard: list[str], alt: list[str] | None, lang: str | None) -> bool:
    """Is the judge's answer still a transcription of this audio (and not a paraphrase or translation)?"""
    new = units(text, lang)
    if not new:
        # Removing a whole line: only a short one, and only when the second listen heard nothing there.
        return alt is not None and not alt and len(heard) <= 6
    longest = max(len(heard), len(alt or []))
    if len(new) > longest + max(3, longest // 3):
        return False
    near_heard = max(ratio(new, heard), ratio(list("".join(new)), list("".join(heard))))
    if alt is None:
        return near_heard >= 0.6
    return near_heard >= 0.5 or ratio(new, alt) >= 0.7


# ---------------------------------------------------------------- second listen -> lines


def assign(lines: list[Line], alt: list[Word]) -> tuple[dict[str, list[Word]], list[list[Word]]]:
    """Give every second-listen word to the line it was spoken in. Words far from every line are speech the
    first listen skipped: returned as groups (one group per stretch of talk)."""
    starts = [ln.start for ln in lines]
    by_line: dict[str, list[Word]] = {ln.id: [] for ln in lines}
    orphans: list[tuple[int, Word]] = []
    for w in alt:
        mid = (w.start + w.end) / 2
        i = bisect.bisect_right(starts, mid) - 1
        best, dist = None, float("inf")
        for k in (i, i + 1):
            if 0 <= k < len(lines):
                ln = lines[k]
                d = 0.0 if ln.start <= mid <= ln.end else min(abs(mid - ln.start), abs(mid - ln.end))
                if d < dist:
                    best, dist = ln, d
        if best is not None and dist <= PAD:
            by_line[best.id].append(w)
        else:
            orphans.append((i, w))
    groups: list[list[Word]] = []
    last_i = None
    for i, w in orphans:
        if groups and last_i == i and w.start - groups[-1][-1].end < 1.0:
            groups[-1].append(w)
        else:
            groups.append([w])
        last_i = i
    keep = [g for g in groups
            if len(g) >= 2 and g[-1].end - g[0].start >= 0.6 and sum(w.prob for w in g) / len(g) >= 0.5]
    return by_line, keep


def hint_terms(*texts: str | None) -> list[str]:
    """Names and special words the visitor gave (comma or space separated), as compared."""
    out: list[str] = []
    for text in texts:
        for part in re.split(r"[,;\s]+", text or ""):
            k = key(part)
            if len(k) >= 3 and k not in out:
                out.append(k)
    return out[:60]


def near_hint(words: list[Word], terms: list[str]) -> bool:
    """A word that looks like a hint but isn't spelled like it: both listens can share that mistake."""
    for w in words:
        k = key(w.text)
        if len(k) < 3:
            continue
        for term in terms:
            if k != term and difflib.SequenceMatcher(None, k, term, autojunk=False).ratio() >= 0.6:
                return True
    return False


def _text(words: list[Word], lang: str | None) -> str:
    return joiner(lang).join(w.text for w in words)


# ---------------------------------------------------------------- rewriting a line, keeping timings


def _spread(texts: list[str], lo: float, hi: float) -> list[Word]:
    total = sum(max(1, len(x)) for x in texts)
    span = max(0.04 * len(texts), hi - lo)
    out, t0 = [], lo
    for x in texts:
        d = span * max(1, len(x)) / total
        out.append(Word(text=x, start=t0, end=t0 + d))
        t0 += d
    return out


def _from_alt(texts: list[str], alt: list[Word], lo: float, hi: float) -> list[Word] | None:
    """Timings for inserted words, taken from where the second listen heard them."""
    want = [key(x) for x in texts]
    keys = [key(w.text) for w in alt]
    for i in range(len(keys) - len(want) + 1):
        if keys[i:i + len(want)] == want:
            got = alt[i:i + len(want)]
            if got[0].start >= lo - 0.05 and got[-1].end <= hi + 0.05:
                out = []
                for x, w in zip(texts, got):
                    st = max(lo, w.start)
                    out.append(Word(text=x, start=st, end=max(st + 0.04, min(hi, w.end) if hi > lo else w.end)))
                return out
    return None


def rewrite(line: Line, text: str, alt: list[Word], lang: str | None) -> int:
    """Put the judge's text into the line. Unchanged words keep their timing (and highlight/emoji); changed
    words share the time of the words they replace; added words get the second listen's timing, or the
    pause next to them. Returns how many words changed."""
    new = split_text(text, lang)
    old = line.words
    if joiner(lang) == "":
        if [key(x) for x in new] == [key(w.text) for w in old]:
            return 0
        from .transcript import retime
        line.words = retime(old, new, line.start, line.end)
        return max(len(old), len(new))
    sm = difflib.SequenceMatcher(None, [key(w.text) for w in old], [key(x) for x in new], autojunk=False)
    out: list[Word] = []
    changed = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            for w, x in zip(old[i1:i2], new[j1:j2]):
                out.append(Word(text=x, start=w.start, end=w.end, keyword=w.keyword, emoji=w.emoji, prob=w.prob))
        elif tag == "delete":
            changed += i2 - i1
        elif tag == "replace":
            words = _spread(new[j1:j2], old[i1].start, old[i2 - 1].end)
            if i2 - i1 == j2 - j1:          # word for word: each keeps its own slot
                words = [Word(text=x, start=w.start, end=w.end) for w, x in zip(old[i1:i2], new[j1:j2])]
            first = old[i1]
            words[0].keyword, words[0].emoji = first.keyword, first.emoji
            out += words
            changed += max(i2 - i1, j2 - j1)
        else:                                # insert
            texts = new[j1:j2]
            lo = out[-1].end if out else max(0.0, old[0].start - 0.3 * len(texts)) if old else line.start
            at_end = i1 >= len(old)
            hi = lo + 0.3 * len(texts) if at_end else old[i1].start
            words = _from_alt(texts, alt, lo, lo + 2.0 if at_end else hi)
            if words is None:
                if hi - lo >= 0.12 * len(texts):
                    words = _spread(texts, lo, hi)
                elif out:                    # no pause to use: share the previous word's time
                    prev = out[-1]
                    both = _spread([prev.text, *texts], prev.start, max(prev.end, hi))
                    prev.end = both[0].end
                    words = both[1:]
                else:
                    words = _spread(texts, max(0.0, hi - 0.25 * len(texts)), hi)
            out += words
            changed += j2 - j1
    line.words = out
    return changed


# ---------------------------------------------------------------- the whole check


def _second_listen(audio: Path, stt_lang: str | None, prompt: str | None, first: stt.SttResult,
                   ranges: list[tuple[float, float]] | None, audio_offset: float, duration: float | None,
                   cancelled: Callable[[], bool], progress: Callable[[float], None],
                   ) -> tuple[list[Word], list[tuple[float, float]], str | None]:
    """Second-listen words (absolute times) and the stretches of time it covered."""
    s = get_settings()
    if not s.captions_verify_listen:
        return [], [], None
    if ranges is None:
        if duration is not None and duration > s.captions_verify_listen_max_sec:
            return [], [], None
        res = stt.second_listen(audio, stt_lang, prompt, first, cancelled, progress)
        if res is None:
            return [], [], None
        for w in res.words:
            w.start += audio_offset
            w.end += audio_offset
        return res.words, [(float("-inf"), float("inf"))], res.model
    words: list[Word] = []
    covered: list[tuple[float, float]] = []
    model = None
    parts = audio.parent / "verify"
    parts.mkdir(exist_ok=True)
    total = sum(b - a for a, b in ranges) or 1.0
    done = 0.0
    for k, (a, b) in enumerate(ranges):
        if sum(y - x for x, y in covered) + (b - a) > s.captions_verify_listen_max_sec:
            break
        start = max(0.0, a - audio_offset)
        try:
            piece = stt.extract_audio(audio, parts / f"part{k}.mp3", start, b - a)
        except stt.SttError:
            continue
        res = stt.second_listen(piece, stt_lang, prompt, first, cancelled,
                                lambda p, d=done, n=b - a: progress((d + p * n) / total))
        done += b - a
        if res is None:
            continue
        for w in res.words:
            w.start += start + audio_offset
            w.end += start + audio_offset
        words += res.words
        covered.append((a + 0.5, b - 0.5))
        model = res.model
    return words, covered, model


def merge_ranges(spans: list[tuple[float, float]], pad: float = 1.0) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for a, b in sorted((max(0.0, a - pad), b + pad) for a, b in spans):
        if out and a <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], b))
        else:
            out.append((a, b))
    return out


def run(t: Transcript, audio: Path | None, first: stt.SttResult | None, *, stt_lang: str | None,
        prompt: str | None = None, hints: str | None = None, title: str | None = None, only: list[Line] | None = None,
        ranges: list[tuple[float, float]] | None = None, audio_offset: float = 0.0, duration: float | None = None,
        cancelled: Callable[[], bool] = lambda: False, progress: Callable[[float], None] = lambda p: None,
        stage: Callable[[str], None] = lambda s: None) -> Report:
    """Check (and fix in place) the lines of `t` (or only `only`). `first`: the speech-to-text result the
    lines were built from. `ranges`: listen again only to these stretches (absolute seconds) instead of
    the whole audio. `audio_offset`: the time in the video where `audio` starts. `prompt`: names and words for
    the speech model; `hints`: extra context for the AI judge only (defaults to the prompt)."""
    s = get_settings()
    lines = list(only if only is not None else t.lines)
    rep = Report(lines=len(lines))
    if not lines:
        return rep
    lang = t.language
    judge = s.captions_ai_proofread and llm.available()

    alt_words: list[Word] = []
    covered: list[tuple[float, float]] = []
    if audio is not None and first is not None:
        stage("AI is listening again to double-check")
        alt_words, covered, rep.second = _second_listen(audio, stt_lang, prompt, first, ranges, audio_offset,
                                                         duration, cancelled, lambda p: progress(0.5 * p))
        if covered:
            rep.listens = 2
    if cancelled():
        raise stt.Cancelled()

    def has_alt(ln: Line) -> bool:
        return any(a <= ln.start and ln.end <= b for a, b in covered)

    by_line, missing = assign(lines, alt_words) if alt_words else ({ln.id: [] for ln in lines}, [])
    missing = [g for g in missing if any(a <= g[0].start and g[-1].end <= b for a, b in covered)]
    doubt = s.captions_verify_doubt
    terms = hint_terms(prompt, hints)
    items: list[dict[str, Any]] = []
    info: dict[str, tuple[Line, list[str], list[str] | None]] = {}
    for i, ln in enumerate(lines):
        heard = units(ln.text(lang), lang)
        alt = units(_text(by_line[ln.id], lang), lang) if has_alt(ln) else None
        probs = [w.prob for w in ln.words]
        unsure = bool(probs) and (sum(probs) / len(probs) < doubt or min(probs) < doubt * 0.6)
        if alt is not None and alt == heard and not unsure and not (terms and near_hint(ln.words, terms)):
            rep.agreed += 1
            continue
        info[ln.id] = (ln, heard, alt)
        item: dict[str, Any] = {"id": ln.id, "heard": ln.text(lang), "unsure": unsure}
        if alt is not None:
            item["alt"] = _text(by_line[ln.id], lang)
        item["before"] = " ".join(lines[i - 1].text(lang).split()[-CONTEXT_WORDS:]) if i else ""
        item["after"] = " ".join(lines[i + 1].text(lang).split()[:CONTEXT_WORDS]) if i + 1 < len(lines) else ""
        items.append(item)
    extra: dict[str, list[Word]] = {}
    starts = [ln.start for ln in lines]
    for k, g in enumerate(missing):
        mid = bisect.bisect_right(starts, g[0].start)
        mid_id = f"m{k}"
        extra[mid_id] = g
        items.append({"id": mid_id, "heard": "", "alt": _text(g, lang), "unsure": True,
                      "before": " ".join(lines[mid - 1].text(lang).split()[-CONTEXT_WORDS:]) if mid else "",
                      "after": " ".join(lines[mid].text(lang).split()[:CONTEXT_WORDS]) if mid < len(lines) else ""})

    answers: dict[str, tuple[str, bool]] = {}
    if judge and items:
        stage("AI is comparing and fixing words")
        try:
            answers = llm.verify(items, languages.info(stt_lang or lang).name, hints or prompt, title,
                                 progress=lambda p: progress(0.5 + 0.5 * p), cancelled=cancelled)
            rep.ai = True
            rep.checked = len(items)
        except llm.LlmError as e:
            log.info("caption check: AI judge skipped: %s", e)
    if cancelled():
        raise stt.Cancelled()

    removed: set[str] = set()
    for lid, (ln, heard, alt) in info.items():
        got = answers.get(lid)
        if got is None:
            # No verdict: flag lines where the two listens clearly disagree.
            if alt is not None and ratio(heard, alt) < 0.7:
                ln.check = True
            continue
        text, sure = got
        if not plausible(text, heard, alt, lang):
            log.info("caption check: answer for %s dropped (too far from what was heard)", lid)
            ln.check = ln.check or (alt is not None and ratio(heard, alt) < 0.7)
            continue
        if not units(text, lang):
            removed.add(lid)
            continue
        n = rewrite(ln, text, by_line[lid], lang)
        if n:
            rep.fixed_lines += 1
            rep.fixed_words += n
        if not sure:
            ln.check = True
    added: list[Line] = []
    for mid_id, g in extra.items():
        got = answers.get(mid_id)
        if not got or not got[0].strip():
            continue
        alt = units(_text(g, lang), lang)
        if ratio(units(got[0], lang), alt) < 0.7:
            continue
        ln = Line(words=[Word(text=w.text, start=w.start, end=w.end, prob=w.prob) for w in g], check=True)
        rewrite(ln, got[0], g, lang)
        if ln.words:
            added.append(ln)
    if removed or added:
        t.lines = sorted([ln for ln in t.lines if ln.id not in removed] + added, key=lambda ln: ln.start)
    rep.removed_lines = len(removed)
    rep.added_lines = len(added)
    rep.flagged = sum(1 for ln in t.lines if ln.check)
    progress(1.0)
    log.info("caption check: %s", rep.public())
    return rep
