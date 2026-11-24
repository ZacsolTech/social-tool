"""Download the caption fonts (all SIL Open Font Licence, from Google Fonts) into backend/fonts.

    uv run python scripts/fetch_fonts.py          # skips files that are already there

The files are committed to the repo, so builds don't need the network. Re-run only to add fonts.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fonts"
sys.path.insert(0, str(ROOT))

from app.captions.fonts import read_family  # noqa: E402

# key, Google family, weight, label, kind, scripts
FONTS = [
    ("montserrat", "Montserrat", 800, "Montserrat", "display", ["latin"]),
    ("poppins", "Poppins", 700, "Poppins", "display", ["latin"]),
    ("anton", "Anton", 400, "Anton", "display", ["latin"]),
    ("bebas", "Bebas Neue", 400, "Bebas Neue", "display", ["latin"]),
    ("bangers", "Bangers", 400, "Bangers", "display", ["latin"]),
    ("oswald", "Oswald", 700, "Oswald", "display", ["latin"]),
    ("marker", "Permanent Marker", 400, "Marker", "display", ["latin"]),
    ("lilita", "Lilita One", 400, "Lilita One", "display", ["latin"]),
    ("archivo", "Archivo Black", 400, "Archivo Black", "display", ["latin"]),
    ("notosans", "Noto Sans", 700, "Noto Sans", "display", ["latin"]),
    ("nastaliq", "Noto Nastaliq Urdu", 700, "Nastaliq (Urdu)", "script", ["urdu"]),
    ("naskh", "Noto Naskh Arabic", 700, "Naskh (Arabic)", "script", ["arabic"]),
    ("devanagari", "Noto Sans Devanagari", 700, "Devanagari", "script", ["devanagari"]),
    ("bengali", "Noto Sans Bengali", 700, "Bengali", "script", ["bengali"]),
    ("gurmukhi", "Noto Sans Gurmukhi", 700, "Gurmukhi", "script", ["gurmukhi"]),
    ("gujarati", "Noto Sans Gujarati", 700, "Gujarati", "script", ["gujarati"]),
    ("tamil", "Noto Sans Tamil", 700, "Tamil", "script", ["tamil"]),
    ("telugu", "Noto Sans Telugu", 700, "Telugu", "script", ["telugu"]),
    ("kannada", "Noto Sans Kannada", 700, "Kannada", "script", ["kannada"]),
    ("malayalam", "Noto Sans Malayalam", 700, "Malayalam", "script", ["malayalam"]),
    ("sinhala", "Noto Sans Sinhala", 700, "Sinhala", "script", ["sinhala"]),
    ("thai", "Noto Sans Thai", 700, "Thai", "script", ["thai"]),
    ("hebrew", "Noto Sans Hebrew", 700, "Hebrew", "script", ["hebrew"]),
    ("korean", "Noto Sans KR", 700, "Korean", "script", ["korean"]),
    ("japanese", "Noto Sans JP", 700, "Japanese", "script", ["japanese"]),
    ("chinese", "Noto Sans SC", 700, "Chinese", "script", ["cjk"]),
    ("emoji", "Noto Emoji", 700, "Emoji", "script", ["emoji"]),
]


def main() -> None:
    OUT.mkdir(exist_ok=True)
    manifest = []
    with httpx.Client(timeout=60, follow_redirects=True) as client:
        for key, family, weight, label, kind, scripts in FONTS:
            path = OUT / f"{key}.ttf"
            if not path.exists():
                css = client.get("https://fonts.googleapis.com/css2", params={"family": f"{family}:wght@{weight}"})
                css.raise_for_status()
                urls = re.findall(r"url\((https://[^)]+\.ttf)\)", css.text)
                if len(urls) != 1:
                    raise SystemExit(f"{family}: expected one TTF, got {len(urls)}")
                data = client.get(urls[0]).content
                path.write_bytes(data)
                print(f"{key:12s} {len(data) / 1024:8.0f} KB  {family}")
            manifest.append({"key": key, "file": path.name, "label": label, "kind": kind, "scripts": scripts,
                             "family": read_family(path), "source": f"Google Fonts: {family} {weight}"})
    (OUT / "manifest.json").write_text(json.dumps({"licence": "SIL Open Font License 1.1", "fonts": manifest}, indent=1),
                                       encoding="utf-8")
    total = sum(p.stat().st_size for p in OUT.glob("*.ttf"))
    print(f"total {total / 1024 / 1024:.1f} MB")


if __name__ == "__main__":
    main()
