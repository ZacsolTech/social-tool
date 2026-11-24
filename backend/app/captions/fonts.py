"""Caption fonts: the files in backend/fonts (fetched by scripts/fetch_fonts.py, all SIL Open Font Licence).

The same files are used by libass for burned-in captions and by the browser for the live preview
(served from /api/captions/fonts/...), so what people see is what they get.
"""

from __future__ import annotations

import json
import struct
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..config import BACKEND_DIR

FONTS_DIR = BACKEND_DIR / "fonts"


@dataclass(frozen=True)
class Font:
    key: str            # our id: "montserrat", "nastaliq", ...
    file: str           # file name in FONTS_DIR
    label: str          # shown in the font picker
    family: str         # family name as libass sees it (name table, id 1)
    kind: str           # "display" (pickable for Latin text) | "script" (used for a writing system)
    scripts: tuple[str, ...]
    em: float = 1.0     # em size / libass size (see em_ratio)


def _tables(data: bytes) -> dict[bytes, int]:
    num = struct.unpack(">H", data[4:6])[0]
    out = {}
    for i in range(num):
        tag, _, off, _ = struct.unpack(">4sIII", data[12 + 16 * i: 28 + 16 * i])
        out[tag] = off
    return out


def em_ratio(path: Path) -> float:
    """libass (like VSFilter) sizes a font so usWinAscent + usWinDescent equals the requested size, while
    browsers size the em square. em / libass size = unitsPerEm / (winAscent + winDescent). Fonts with tall
    metrics (Nastaliq, Bangers) would otherwise come out much smaller in the export than in the preview."""
    data = path.read_bytes()
    t = _tables(data)
    upem = struct.unpack(">H", data[t[b"head"] + 18: t[b"head"] + 20])[0]
    if b"OS/2" not in t:
        return 1.0
    wa, wd = struct.unpack(">HH", data[t[b"OS/2"] + 74: t[b"OS/2"] + 78])
    return upem / (wa + wd) if wa + wd else 1.0


def read_family(path: Path) -> str:
    """Family name (name id 1, Windows English first) from a TrueType/OpenType file."""
    data = path.read_bytes()
    name_off = _tables(data).get(b"name")
    if name_off is None:
        raise ValueError(f"{path.name}: no name table")
    _, count, str_off = struct.unpack(">HHH", data[name_off:name_off + 6])
    found: dict[tuple[int, int], str] = {}
    for i in range(count):
        pid, eid, lid, nid, length, off = struct.unpack(">HHHHHH", data[name_off + 6 + 12 * i: name_off + 18 + 12 * i])
        if nid != 1:
            continue
        raw = data[name_off + str_off + off: name_off + str_off + off + length]
        if pid == 3:
            found[(0 if lid == 0x409 else 1, 0)] = raw.decode("utf-16-be", "replace")
        elif pid == 1:
            found[(2, 0)] = raw.decode("mac_roman", "replace")
    if not found:
        raise ValueError(f"{path.name}: no family name")
    return found[min(found)]


@lru_cache
def registry() -> dict[str, Font]:
    manifest = json.loads((FONTS_DIR / "manifest.json").read_text(encoding="utf-8"))
    out: dict[str, Font] = {}
    for f in manifest["fonts"]:
        path = FONTS_DIR / f["file"]
        if not path.exists():
            continue
        out[f["key"]] = Font(key=f["key"], file=f["file"], label=f["label"], family=read_family(path),
                             kind=f["kind"], scripts=tuple(f.get("scripts", [])), em=round(em_ratio(path), 4))
    return out


def get(key: str) -> Font:
    reg = registry()
    return reg.get(key) or reg["notosans"]


def display_fonts() -> list[Font]:
    return [f for f in registry().values() if f.kind == "display"]


# ---------------------------------------------------------------- scripts

# Unicode blocks -> writing system. Good enough to pick a font per word.
_RANGES: list[tuple[int, int, str]] = [
    (0x0590, 0x05FF, "hebrew"),
    (0x0600, 0x06FF, "arabic"), (0x0750, 0x077F, "arabic"), (0x08A0, 0x08FF, "arabic"),
    (0xFB50, 0xFDFF, "arabic"), (0xFE70, 0xFEFF, "arabic"),
    (0x0900, 0x097F, "devanagari"), (0xA8E0, 0xA8FF, "devanagari"),
    (0x0980, 0x09FF, "bengali"),
    (0x0A00, 0x0A7F, "gurmukhi"),
    (0x0A80, 0x0AFF, "gujarati"),
    (0x0B80, 0x0BFF, "tamil"),
    (0x0C00, 0x0C7F, "telugu"),
    (0x0C80, 0x0CFF, "kannada"),
    (0x0D00, 0x0D7F, "malayalam"),
    (0x0D80, 0x0DFF, "sinhala"),
    (0x0E00, 0x0E7F, "thai"),
    (0x1100, 0x11FF, "korean"), (0xAC00, 0xD7AF, "korean"), (0x3130, 0x318F, "korean"),
    (0x3040, 0x30FF, "japanese"),
    (0x3400, 0x4DBF, "cjk"), (0x4E00, 0x9FFF, "cjk"), (0xF900, 0xFAFF, "cjk"), (0x3000, 0x303F, "cjk"),
    (0xFF00, 0xFFEF, "cjk"),
]


def char_script(ch: str) -> str | None:
    cp = ord(ch)
    if is_emoji_char(ch):
        return "emoji"
    for lo, hi, name in _RANGES:
        if lo <= cp <= hi:
            return name
    if ch.isalpha():
        return "latin"      # Latin, Cyrillic, Greek, Vietnamese... (covered by the display fonts / Noto Sans)
    return None


def is_emoji_char(ch: str) -> bool:
    cp = ord(ch)
    return (0x1F300 <= cp <= 0x1FAFF or 0x2600 <= cp <= 0x27BF or 0x1F000 <= cp <= 0x1F2FF
            or cp in (0x2B50, 0x2B06, 0x2B07, 0x2B05, 0x27A1, 0x2934, 0x2935, 0x3030, 0x303D, 0x2122, 0x00A9, 0x00AE))


def word_script(word: str) -> str | None:
    """Main writing system of a word (the most frequent script among its letters)."""
    counts: dict[str, int] = {}
    for ch in word:
        s = char_script(ch)
        if s:
            counts[s] = counts.get(s, 0) + 1
    if not counts:
        return None
    return max(counts, key=counts.get)


def is_rtl_text(text: str) -> bool:
    letters = [unicodedata.bidirectional(c) for c in text if c.strip()]
    rtl = sum(1 for b in letters if b in ("R", "AL"))
    ltr = sum(1 for b in letters if b == "L")
    return rtl > ltr


# Which font draws each writing system. "urdu" is Arabic script in Nastaliq style.
SCRIPT_FONT = {
    "arabic": "naskh", "urdu": "nastaliq", "hebrew": "hebrew", "devanagari": "devanagari", "bengali": "bengali",
    "gurmukhi": "gurmukhi", "gujarati": "gujarati", "tamil": "tamil", "telugu": "telugu", "kannada": "kannada",
    "malayalam": "malayalam", "sinhala": "sinhala", "thai": "thai", "korean": "korean", "japanese": "japanese",
    "cjk": "chinese", "emoji": "emoji", "latin": "notosans",
}


def font_for_script(script: str | None, fallback: str) -> str:
    """Font key for a writing system; `fallback` (the chosen display font) for Latin text."""
    if script is None or script == "latin":
        return fallback
    key = SCRIPT_FONT.get(script, fallback)
    return key if key in registry() else fallback
