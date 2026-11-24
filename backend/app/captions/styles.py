"""Caption styles: the settings model and the ready-made presets shown in the style picker."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

HEX = r"^#[0-9a-fA-F]{6}$"
Animation = Literal["none", "fade", "pop", "bounce", "slide", "karaoke", "highlight", "word", "reveal"]


class Style(BaseModel):
    preset: str = Field("bold-pop", max_length=40)
    font: str = Field("montserrat", max_length=30)
    size: int = Field(56, ge=14, le=120)              # em size in px on a video whose short side is 1080
    uppercase: bool = False
    color: str = Field("#FFFFFF", pattern=HEX)
    highlight: str = Field("#FFE14D", pattern=HEX)    # the word being spoken
    highlight_mode: Literal["color", "box", "scale"] = "color"
    keyword_color: str = Field("#3DDC84", pattern=HEX)
    outline_color: str = Field("#000000", pattern=HEX)
    outline: float = Field(5, ge=0, le=16)
    shadow: float = Field(2, ge=0, le=12)
    box: bool = False
    box_color: str = Field("#000000", pattern=HEX)
    box_opacity: float = Field(0.75, ge=0, le=1)
    y: float = Field(0.72, ge=0.05, le=0.95)           # vertical centre of the captions, 0 = top
    max_words: int = Field(4, ge=1, le=14)
    max_chars: int = Field(28, ge=8, le=80)
    animation: Animation = "pop"
    spacing: float = Field(0, ge=0, le=12)
    emoji: bool = True
    keywords: bool = True
    translation_color: str = Field("#FFE14D", pattern=HEX)
    translation_scale: float = Field(0.72, ge=0.4, le=1.0)

    @field_validator("color", "highlight", "keyword_color", "outline_color", "box_color", "translation_color")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.upper()


def _p(**kw) -> dict:
    return kw


# Presets: named looks people pick in one tap, then fine-tune. Names describe the look, not a creator.
PRESETS: dict[str, dict] = {
    "bold-pop": _p(label="Bold Pop", font="montserrat", size=62, uppercase=True, color="#FFFFFF", highlight="#FFE14D",
                   highlight_mode="scale", animation="pop", outline=6, shadow=3, max_words=3, max_chars=18, y=0.70),
    "karaoke": _p(label="Karaoke", font="poppins", size=50, color="#FFFFFF", highlight="#3DDC84", animation="karaoke",
                  outline=5, shadow=2, max_words=5, max_chars=30, y=0.74),
    "word-by-word": _p(label="One Word", font="anton", size=80, uppercase=True, color="#FFFFFF", highlight="#FFFFFF",
                       animation="word", outline=7, shadow=4, max_words=1, max_chars=14, y=0.55, emoji=True),
    "highlight-box": _p(label="Highlight Box", font="montserrat", size=54, color="#FFFFFF", highlight="#7C3AED",
                        highlight_mode="box", animation="highlight", outline=4, shadow=0, max_words=4, max_chars=26,
                        y=0.72),
    "classic": _p(label="Classic", font="notosans", size=42, color="#FFFFFF", highlight="#FFFFFF", animation="fade",
                  outline=4, shadow=1, max_words=8, max_chars=42, y=0.86, emoji=False, keywords=False),
    "boxed": _p(label="Boxed", font="notosans", size=40, color="#FFFFFF", highlight="#FFFFFF", animation="fade",
                box=True, box_color="#000000", box_opacity=0.72, outline=12, shadow=0, max_words=8, max_chars=40,
                y=0.84, emoji=False, keywords=False),
    "neon": _p(label="Neon", font="archivo", size=56, uppercase=True, color="#E9FFF5", highlight="#39FF88",
               keyword_color="#39FF88", outline_color="#00A86B", outline=3, shadow=6, animation="highlight",
               max_words=3, max_chars=22, y=0.68),
    "cinema": _p(label="Cinema", font="bebas", size=76, uppercase=True, color="#FFFFFF", highlight="#FFFFFF",
                 animation="fade", outline=0, shadow=3, spacing=3, max_words=6, max_chars=32, y=0.86, emoji=False,
                 keywords=False),
    "comic": _p(label="Comic", font="bangers", size=64, uppercase=True, color="#FFF6D6", highlight="#FF4F1F",
                keyword_color="#38BDF8", outline=7, shadow=4, animation="bounce", max_words=3, max_chars=20, y=0.66),
    "marker": _p(label="Marker", font="marker", size=58, color="#FFFFFF", highlight="#FFB020", animation="reveal",
                 outline=5, shadow=3, max_words=4, max_chars=24, y=0.70),
    "story": _p(label="Story", font="lilita", size=58, color="#111111", highlight="#FF4F1F", box=True,
                box_color="#FFFFFF", box_opacity=1.0, outline=14, shadow=0, animation="slide", max_words=4,
                max_chars=24, y=0.66, keyword_color="#FF4F1F", translation_color="#FF4F1F"),
    "podcast": _p(label="Podcast", font="poppins", size=44, color="#FFFFFF", highlight="#FFE14D",
                  animation="highlight", highlight_mode="color", outline=4, shadow=2, max_words=7, max_chars=36, y=0.80,
                  emoji=False),
    "cricket": _p(label="Match Day", font="oswald", size=62, uppercase=True, color="#FFFFFF", highlight="#B7F500",
                  keyword_color="#B7F500", outline_color="#0B3D1F", outline=6, shadow=3, animation="pop",
                  highlight_mode="scale", max_words=3, max_chars=22, y=0.68),
    "desi-bold": _p(label="Desi Bold", font="montserrat", size=52, color="#FFFFFF", highlight="#FFD400",
                    box=True, box_color="#000000", box_opacity=0.8, outline=12, shadow=0, animation="highlight",
                    max_words=5, max_chars=30, y=0.74),
}


def preset_style(key: str) -> Style:
    p = dict(PRESETS.get(key) or PRESETS["bold-pop"])
    p.pop("label", None)
    return Style(preset=key if key in PRESETS else "bold-pop", **p)


def presets_public() -> list[dict]:
    out = []
    for key in PRESETS:
        st = preset_style(key)
        out.append({"id": key, "label": PRESETS[key]["label"], "style": st.model_dump()})
    return out
