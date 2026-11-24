"""Remove filler words ("um", "uh") and long pauses: which parts of the video to keep, and new caption times."""

from __future__ import annotations

import re

from .transcript import Line, Transcript, Word

FILLERS = {
    "um", "umm", "ummm", "uh", "uhh", "uhm", "uhmm", "erm", "er", "err", "ah", "ahh", "hmm", "hmmm", "hm", "mm", "mmm",
    "mhm", "eh", "ehh", "aa", "aaa", "aah", "uff",
    "ہمم", "ہم م", "امم", "اں", "آں", "ام", "اوں",
    "हम्म", "उम्म", "अं", "आं", "ऊं", "हम्म्म",
}
_STRIP = re.compile(r"^[\W_]+|[\W_]+$", re.UNICODE)


def is_filler(text: str) -> bool:
    k = _STRIP.sub("", text).lower()
    return bool(k) and (k in FILLERS or bool(re.fullmatch(r"(u+h+m*|u+m+|h+m+|e+r+m*|a+h+|m{2,})", k)))


def plan(t: Transcript, duration: float, fps: float, fillers: bool = True, silences: bool = True,
         max_gap: float = 0.6, pad: float = 0.15) -> list[tuple[float, float]]:
    """Parts of [0, duration] to keep, snapped to the frame grid so audio and video stay in sync."""
    remove: list[tuple[float, float]] = []
    words = t.words()
    if fillers:
        for w in words:
            if is_filler(w.text):
                remove.append((w.start - 0.02, w.end + 0.03))
    if silences and words:
        speech = [w for w in words if not (fillers and is_filler(w.text))]
        if speech:
            if speech[0].start > max_gap:
                remove.append((0.0, speech[0].start - pad))
            for a, b in zip(speech, speech[1:]):
                if b.start - a.end > max_gap:
                    remove.append((a.end + pad, b.start - pad))
            if duration - speech[-1].end > max_gap:
                remove.append((speech[-1].end + pad, duration))
    if not remove:
        return [(0.0, duration)]
    remove.sort()
    merged: list[list[float]] = []
    for a, b in remove:
        a, b = max(0.0, a), min(duration, b)
        if b <= a:
            continue
        if merged and a <= merged[-1][1] + 0.05:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    keep: list[tuple[float, float]] = []
    t0 = 0.0
    for a, b in merged:
        if a - t0 > 0.08:
            keep.append((t0, a))
        t0 = b
    if duration - t0 > 0.08:
        keep.append((t0, duration))
    fps = fps or 30.0
    snapped = []
    for a, b in keep:
        a2, b2 = round(a * fps) / fps, round(b * fps) / fps
        if b2 - a2 >= 2 / fps:
            snapped.append((a2, b2))
    return snapped or [(0.0, duration)]


def kept_duration(keep: list[tuple[float, float]]) -> float:
    return sum(b - a for a, b in keep)


def mapper(keep: list[tuple[float, float]]):
    offsets = []
    acc = 0.0
    for a, b in keep:
        offsets.append(acc)
        acc += b - a

    def f(t: float) -> float:
        for (a, b), off in zip(keep, offsets):
            if t < a:
                return off           # inside a removed part: jump to where the next kept part starts
            if t <= b:
                return off + (t - a)
        return acc
    return f


def remap(t: Transcript, keep: list[tuple[float, float]], drop_fillers: bool) -> Transcript:
    """Caption times on the shortened video. Filler words are dropped from the captions too."""
    f = mapper(keep)
    out = t.copy()
    lines: list[Line] = []
    for ln in out.lines:
        words: list[Word] = []
        for w in ln.words:
            if drop_fillers and is_filler(w.text):
                continue
            s, e = f(w.start), f(w.end)
            if e - s < 0.04:
                e = s + 0.04
            words.append(Word(text=w.text, start=s, end=e, keyword=w.keyword, emoji=w.emoji))
        if words:
            ln.words = words
            lines.append(ln)
    out.lines = lines
    return out


def select_expr(keep: list[tuple[float, float]]) -> str:
    """Expression for FFmpeg's select/aselect (used inside single quotes in the filter graph)."""
    return "+".join(f"between(t,{a:.4f},{b - 1e-4:.4f})" for a, b in keep)
