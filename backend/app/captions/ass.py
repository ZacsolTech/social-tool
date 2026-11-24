"""Build an ASS subtitle script (rendered by libass inside FFmpeg) from a transcript and a style.

Everything visual lives here: pages of words, the spoken-word highlight, animations, keyword colours,
emojis, dual-language lines, the hook title, the progress bar and the watermark. Fonts are chosen per
word by writing system, so an Urdu caption with an English word in it uses Nastaliq for the Urdu and the
chosen display font for the English.
"""

from __future__ import annotations

from dataclasses import dataclass

from . import fonts, languages
from .styles import Style
from .transcript import Line, Transcript, Word, joiner, pages

REF = 1080.0       # style sizes are px on a video whose short side is 1080
SCRIPT_BOOST = {"urdu": 1.15}    # same factor as the preview (CaptionPreview.tsx)


def fs(em_px: float, font_key: str) -> float:
    """libass font size that draws an em of em_px with this font (see fonts.em_ratio)."""
    return em_px / fonts.get(font_key).em


@dataclass
class Extras:
    hook: str | None = None
    hook_seconds: float = 4.0        # 0 = whole video
    hook_y: float = 0.12
    hook_color: str = "#FFFFFF"
    hook_bg: str = "#FF4F1F"
    progress_bar: str = "none"       # none | top | bottom
    progress_color: str = "#FF4F1F"
    watermark: str | None = None     # text, e.g. "klyprima.com"
    mode: str = "original"           # original | translation | dual


def color(hex_: str, alpha: float = 0.0) -> str:
    """#RRGGBB + transparency (0 opaque .. 1 invisible) -> ASS &HAABBGGRR."""
    h = hex_.lstrip("#")
    a = max(0, min(255, int(round(alpha * 255))))
    return f"&H{a:02X}{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def bgr(hex_: str) -> str:
    h = hex_.lstrip("#")
    return f"&H{h[4:6]}{h[2:4]}{h[0:2]}&".upper()


def ts(t: float) -> str:
    cs = int(round(max(0.0, t) * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def escape(text: str) -> str:
    return (text.replace("\\", "⧵").replace("{", "(").replace("}", ")")
            .replace("\n", " ").replace("\r", " "))


class Builder:
    def __init__(self, t: Transcript, style: Style, W: int, H: int, extras: Extras, duration: float):
        self.t, self.st, self.W, self.H, self.x, self.duration = t, style, W, H, extras, duration
        self.scale = min(W, H) / REF
        lang = languages.info(t.language.split("-Latn")[0] if t.language.endswith("-Latn") else t.language)
        self.lang_code = t.language
        self.rtl = lang.rtl and not t.language.endswith("-Latn")
        display = fonts.get(style.font)
        self.display_key = display.key
        # Base font: the display font for Latin-script languages, the script font otherwise.
        script = "latin" if t.language.endswith("-Latn") else lang.script
        self.base_key = fonts.font_for_script(script, display.key)
        self.base_family = fonts.get(self.base_key).family
        # style.size is the em size in px (what the browser preview uses). Nastaliq reads small, so it's bumped.
        self.em = style.size * self.scale * (SCRIPT_BOOST.get(script, 1.0))
        self.size = fs(self.em, self.base_key)
        self.events: list[str] = []

    # ---------------------------------------------------------------- styles

    def header(self) -> str:
        st = self.st
        pad = st.outline * self.scale
        if st.box:
            main = ("Main", self.base_family, self.size, color(st.color), color(st.color), color(st.box_color, 1 - st.box_opacity),
                    color(st.box_color, 1 - st.box_opacity), 3, max(pad, 6 * self.scale), 0)
        else:
            main = ("Main", self.base_family, self.size, color(st.color), color(st.color), color(st.outline_color),
                    color("#000000", 0.45), 1, pad, st.shadow * self.scale)
        if st.animation == "karaoke":   # \kf fills from Secondary (not yet sung) to Primary (sung)
            main = (main[0], main[1], main[2], color(st.highlight), color(st.color), *main[5:])
        hook_family = fonts.get(self.display_key).family
        hook = ("Hook", hook_family, fs(st.size * 0.95 * self.scale, self.display_key), color(self.x.hook_color), color(self.x.hook_color),
                color(self.x.hook_bg), color(self.x.hook_bg), 3, 16 * self.scale, 0)
        mark = ("Mark", fonts.get("notosans").family, fs(22 * self.scale, "notosans"), color("#FFFFFF", 0.35), color("#FFFFFF", 0.35),
                color("#000000", 0.6), color("#000000", 1), 1, 1.5 * self.scale, 0)
        bar = ("Bar", fonts.get("notosans").family, 20, color(self.x.progress_color), color(self.x.progress_color),
               color("#000000", 1), color("#000000", 1), 1, 0, 0)
        margin = int(self.W * 0.06)
        rows = []
        for name, font, size, pri, sec, out, back, border, outline, shadow in (main, hook, mark, bar):
            spacing = st.spacing * self.scale if name == "Main" else 0
            # Encoding -1 makes libass detect the base direction, so right-to-left captions keep their word
            # order even when highlight tags split a line into several runs.
            enc = -1 if name in ("Main", "Hook") else 1
            rows.append(f"Style: {name},{font},{size:.1f},{pri},{sec},{out},{back},0,0,0,0,100,100,{spacing:.1f},0,"
                        f"{border},{outline:.1f},{shadow:.1f},5,{margin},{margin},0,{enc}")
        return "\n".join([
            "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {self.W}", f"PlayResY: {self.H}", "WrapStyle: 0",
            "ScaledBorderAndShadow: yes", "YCbCr Matrix: TV.709", "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
            "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
            "MarginR, MarginV, Encoding",
            *rows, "",
            "[Events]",
            "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        ])

    def add(self, start: float, end: float, text: str, style: str = "Main", layer: int = 0) -> None:
        if end - start < 0.02:
            return
        self.events.append(f"Dialogue: {layer},{ts(start)},{ts(end)},{style},,0,0,0,,{text}")

    # ---------------------------------------------------------------- words

    def word_text(self, w: Word) -> str:
        txt = w.text
        if self.st.uppercase and fonts.word_script(txt) in (None, "latin"):
            txt = txt.upper()
        return escape(txt)

    def font_wrap(self, text: str, raw: str) -> str:
        """Switch font for words in another writing system (or emoji), then back."""
        script = fonts.word_script(raw)
        if script is None:
            return text
        want = fonts.font_for_script("urdu" if script == "arabic" and self.base_key == "nastaliq" else script,
                                     self.display_key)
        if want == self.base_key:
            return text
        return f"{{\\fn{fonts.get(want).family}\\fs{fs(self.em, want):.1f}}}{text}{{\\fn{self.base_family}\\fs{self.size:.1f}}}"

    def emoji_tag(self, e: str, col: str | None = None) -> str:
        c = bgr(col or self.st.highlight)
        return (f"{{\\fn{fonts.get('emoji').family}\\fs{fs(self.em, 'emoji'):.1f}\\c{c}}}{escape(e)}"
                f"{{\\fn{self.base_family}\\fs{self.size:.1f}\\c{bgr(self.st.color)}}}")

    def render_words(self, words: list[Word], active: int | None, hidden_after: int | None = None) -> str:
        st = self.st
        sep = joiner(self.lang_code if not self.lang_code.endswith("-Latn") else "en")
        parts = []
        base_c = bgr(st.color)
        for i, w in enumerate(words):
            txt = self.font_wrap(self.word_text(w), w.text)
            tags, reset = "", ""
            if hidden_after is not None and i > hidden_after:
                tags, reset = "\\alpha&HFF&", "\\alpha&H00&"
            elif i == active:
                if st.highlight_mode == "box":
                    tags = f"\\3c{bgr(st.highlight)}\\bord{max(6.0, st.size * 0.24) * self.scale:.1f}\\shad0"
                    reset = f"\\3c{bgr(st.outline_color)}\\bord{st.outline * self.scale:.1f}\\shad{st.shadow * self.scale:.1f}"
                elif st.highlight_mode == "scale":
                    tags = f"\\c{bgr(st.highlight)}\\fscx112\\fscy112"
                    reset = f"\\c{base_c}\\fscx100\\fscy100"
                else:
                    tags = f"\\c{bgr(st.highlight)}"
                    reset = f"\\c{base_c}"
            elif st.keywords and w.keyword:
                tags, reset = f"\\c{bgr(st.keyword_color)}", f"\\c{base_c}"
            parts.append(f"{{{tags}}}{txt}{{{reset}}}" if tags else txt)
        text = sep.join(parts)
        if st.emoji:
            em = next((w.emoji for w in words if w.emoji), None)
            if em and (hidden_after is None or any(w.emoji for w in words[:hidden_after + 1])):
                text += " " + self.emoji_tag(em)
        return text

    # ---------------------------------------------------------------- captions

    def position(self) -> str:
        return f"\\an5\\pos({self.W / 2:.0f},{self.st.y * self.H:.0f})"

    def entrance(self, dur: float) -> str:
        a = self.st.animation
        if a == "fade":
            return "\\fad(140,90)"
        if a == "bounce":
            return "\\fscx72\\fscy72\\t(0,110,\\fscx108\\fscy108)\\t(110,190,\\fscx100\\fscy100)"
        if a == "slide":
            y = self.st.y * self.H
            dy = 36 * self.scale
            return f"\\move({self.W / 2:.0f},{y + dy:.0f},{self.W / 2:.0f},{y:.0f},0,160)\\fad(120,60)"
        return ""

    def translation_suffix(self, line: Line) -> str:
        if self.x.mode != "dual" or not line.translation:
            return ""
        st = self.st
        tr = line.translation
        tr_script = fonts.word_script(tr) or "latin"
        tr_lang = self.t.translation_lang or ""
        if tr_script == "arabic" and tr_lang == "ur":
            tr_script = "urdu"
        key = fonts.font_for_script(tr_script, self.display_key)
        size = fs(self.em * st.translation_scale, key)
        return (f"\\N{{\\fn{fonts.get(key).family}\\fs{size:.1f}\\c{bgr(st.translation_color)}\\fscx100\\fscy100}}"
                f"{escape(tr)}")

    def line_pages(self, line: Line) -> list[list[Word]]:
        st = self.st
        max_words = 1 if st.animation == "word" else st.max_words
        return pages(line, max_words, st.max_chars, self.lang_code)

    def captions(self, lines: list[Line]) -> None:
        st = self.st
        all_pages: list[tuple[Line, list[Word]]] = [(ln, pg) for ln in lines for pg in self.line_pages(ln)]
        for k, (line, words) in enumerate(all_pages):
            start = words[0].start
            nxt = all_pages[k + 1][1][0].start if k + 1 < len(all_pages) else None
            end = words[-1].end + 0.35
            if nxt is not None:
                end = nxt if nxt - words[-1].end < 0.7 else min(end, nxt)
            end = max(end, words[-1].end + 0.05, start + 0.25)
            if self.duration:
                end = min(end, self.duration)
            pos = self.position()
            tail = self.translation_suffix(line)
            a = st.animation
            if a in ("none", "fade", "bounce", "slide"):
                self.add(start, end, f"{{{pos}{self.entrance(end - start)}}}{self.render_words(words, None)}{tail}")
            elif a == "karaoke":
                parts = []
                sep = joiner(self.lang_code if not self.lang_code.endswith("-Latn") else "en")
                for i, w in enumerate(words):
                    until = words[i + 1].start if i + 1 < len(words) else w.end
                    cs = max(1, int(round((until - (w.start if i else start)) * 100)))
                    style_tag = f"\\c{bgr(st.keyword_color)}" if st.keywords and w.keyword else ""
                    parts.append(f"{{\\kf{cs}{style_tag}}}{self.font_wrap(self.word_text(w), w.text)}")
                em = next((w.emoji for w in words if w.emoji), None) if st.emoji else None
                text = sep.join(parts) + (" " + self.emoji_tag(em) if em else "")
                self.add(start, end, f"{{{pos}}}{text}{tail}")
            else:   # highlight / pop / word / reveal: one event per spoken word
                for i, w in enumerate(words):
                    s0 = start if i == 0 else w.start
                    s1 = words[i + 1].start if i + 1 < len(words) else end
                    if s1 - s0 < 0.02:
                        continue
                    if a == "word":
                        pop = "\\fscx80\\fscy80\\t(0,90,\\fscx106\\fscy106)\\t(90,150,\\fscx100\\fscy100)"
                        self.add(s0, s1, f"{{{pos}{pop}}}{self.render_words([w], None)}{tail}")
                    elif a == "reveal":
                        self.add(s0, s1, f"{{{pos}}}{self.render_words(words, i, hidden_after=i)}{tail}")
                    else:
                        intro = "\\fscx85\\fscy85\\t(0,90,\\fscx100\\fscy100)" if (a == "pop" and i == 0) else ""
                        self.add(s0, s1, f"{{{pos}{intro}}}{self.render_words(words, i)}{tail}")

    # ---------------------------------------------------------------- extras

    def extras(self) -> None:
        x, W, H = self.x, self.W, self.H
        if x.hook:
            end = self.duration if x.hook_seconds <= 0 else min(self.duration or x.hook_seconds, x.hook_seconds)
            hook = escape(x.hook)
            if self.st.uppercase and fonts.word_script(hook) in (None, "latin"):
                hook = hook.upper()
            script = fonts.word_script(hook)
            fn = ""
            if script not in (None, "latin"):
                key = fonts.font_for_script("urdu" if script == "arabic" and self.base_key == "nastaliq" else script,
                                            self.display_key)
                fn = f"\\fn{fonts.get(key).family}\\fs{fs(self.st.size * 0.95 * self.scale, key):.1f}"
            self.add(0, end, f"{{\\an8\\pos({W / 2:.0f},{x.hook_y * H:.0f})\\fad(200,200){fn}"
                             f"\\t(0,180,\\fscx104\\fscy104)\\t(180,320,\\fscx100\\fscy100)}}{hook}", "Hook", 2)
        if x.progress_bar in ("top", "bottom") and self.duration:
            h = max(6, int(round(H * 0.006)))
            y = 0 if x.progress_bar == "top" else H - h
            ms = int(self.duration * 1000)
            self.add(0, self.duration, f"{{\\an7\\pos(0,{y})\\fscx0\\t(0,{ms},\\fscx100)\\p1}}m 0 0 l {W} 0 {W} {h} 0 {h}{{\\p0}}",
                     "Bar", 3)
        if x.watermark and self.duration:
            self.add(0, self.duration, f"{{\\an7\\pos({W * 0.04:.0f},{H * 0.03:.0f})}}{escape(x.watermark)}", "Mark", 3)

    def build(self) -> str:
        self.captions(self.t.lines)
        self.extras()
        return self.header() + "\n" + "\n".join(self.events) + "\n"


def build_ass(t: Transcript, style: Style, W: int, H: int, duration: float, extras: Extras | None = None) -> str:
    return Builder(t, style, W, H, extras or Extras(), duration).build()
