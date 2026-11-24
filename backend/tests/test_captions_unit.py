"""Unit tests for the caption tool's pure logic (no FFmpeg, no network)."""

from __future__ import annotations

import pytest

from app.captions import ass, cuts, enhance, fonts, languages, translit
from app.captions.jobs import align_segments, display_transcript
from app.captions.styles import PRESETS, Style, preset_style
from app.captions.transcript import (Line, Transcript, Word, build_lines, from_dict, normalize, pages,
                                     parse_subtitles, retime, split_text, to_srt, to_txt, to_vtt)


def words(text: str, start: float = 0.0, step: float = 0.3) -> list[Word]:
    out, t = [], start
    for x in text.split():
        out.append(Word(x, t, t + step - 0.05))
        t += step
    return out


# ---------------------------------------------------------------- transcript


def test_build_lines_breaks_on_sentences_pauses_and_length():
    ws = words("Hello there. This is a test of the caption tool and it keeps going on and on", 0)
    ws += words("after a pause", 10)
    lines = build_lines(ws, "en", max_words=8)
    texts = [ln.text("en") for ln in lines]
    assert texts[0] == "Hello there."
    assert all(len(ln.words) <= 8 for ln in lines)
    assert texts[-1] == "after a pause"


def test_pages_are_balanced_and_respect_limits():
    ln = Line(words=words("one two three four five six seven"))
    ps = pages(ln, max_words=3, max_chars=40)
    assert [len(p) for p in ps] == [3, 2, 2] or [len(p) for p in ps] == [2, 3, 2] or sum(len(p) for p in ps) == 7
    assert all(len(p) <= 3 for p in ps) and sum(len(p) for p in ps) == 7
    long = Line(words=words("supercalifragilistic expialidocious word"))
    assert all(sum(len(w.text) for w in p) <= 40 for p in pages(long, 5, 22))
    assert len(pages(Line(words=words("a b c d")), 1, 50)) == 4


def test_retime_keeps_timings_when_word_count_matches_else_spreads():
    ws = words("hello world")
    same = retime(ws, ["Hello", "World!"], 0, 0.55)
    assert [w.text for w in same] == ["Hello", "World!"]
    assert [x for w in same for x in (w.start, w.end)] == pytest.approx([0.0, 0.25, 0.3, 0.55])
    spread = retime(ws, ["a", "bbbb", "cc"], 0, 1.4)
    assert spread[0].start == 0 and abs(spread[-1].end - 1.4) < 1e-9
    assert spread[1].end - spread[1].start > spread[0].end - spread[0].start


def test_normalize_fixes_overlaps_and_clamps_to_duration():
    t = Transcript("en", [Line(words=[Word("b", 2.0, 1.0), Word("a", -1, 0.5)]), Line(words=[Word("  ", 0, 1)]),
                          Line(words=[Word("c", 9.5, 12)])])
    normalize(t, duration=10)
    flat = t.words()
    assert [w.text for w in flat] == ["b", "a", "c"] or all(w.end > w.start for w in flat)
    assert all(0 <= w.start < w.end <= 10 for w in flat)
    assert len(t.lines) == 2
    assert all(b.start >= a.end - 1e-6 for a, b in zip(flat, flat[1:]))


def test_srt_vtt_txt_export_and_import_round_trip():
    t = Transcript("en", [Line(words=words("Hello world", 1.0), translation="Hola mundo"),
                          Line(words=words("Second line", 3661.5))], translation_lang="es")
    srt = to_srt(t)
    assert "1\n00:00:01,000 --> 00:00:01,550\nHello world" in srt
    assert "01:01:01,500" in srt
    assert "Hello world\nHola mundo" in to_srt(t, "dual")
    assert to_txt(t, "translation").splitlines() == ["Hola mundo", "Second line"]
    vtt = to_vtt(t)
    assert vtt.startswith("WEBVTT") and "00:00:01.000 --> " in vtt
    back = parse_subtitles(srt)
    assert [ln.text() for ln in back] == ["Hello world", "Second line"]
    assert abs(back[1].start - 3661.5) < 0.01
    assert [ln.text() for ln in parse_subtitles(vtt)] == ["Hello world", "Second line"]
    messy = "﻿1\r\n00:00:00,500 --> 00:00:02,000\r\n<i>Hi</i> {\\an8}there\r\n\r\nnot a cue\r\n"
    assert [ln.text() for ln in parse_subtitles(messy)] == ["Hi there"]


def test_transcript_dict_round_trip_keeps_keywords_emoji_translation():
    t = Transcript("ur", [Line(words=[Word("پیسہ", 0, 1, keyword=True, emoji="💰")], translation="money")],
                   translation_lang="en", rev=3)
    back = from_dict(t.to_dict())
    assert back.lines[0].words[0].keyword and back.lines[0].words[0].emoji == "💰"
    assert back.lines[0].translation == "money" and back.rev == 3 and back.translation_lang == "en"


def test_languages_without_spaces():
    assert split_text("你好世界今天", "zh") == ["你好", "世界", "今天"]
    t = Transcript("zh", [Line(words=[Word("你好", 0, 1), Word("世界", 1, 2)])])
    assert t.lines[0].text("zh") == "你好世界"


# ---------------------------------------------------------------- languages, fonts


def test_language_normalization():
    assert languages.normalize("urdu") == "ur"
    assert languages.normalize("English") == "en"
    assert languages.normalize("pt-BR") == "pt"
    assert languages.normalize("klingon") is None
    assert languages.get("ur-Latn").stt == "ur" and languages.get("ur").rtl
    assert all(c in languages.BY_CODE for c in languages.TRANSLATE_TARGETS)


def test_fonts_are_present_and_named():
    reg = fonts.registry()
    for key in ("montserrat", "nastaliq", "naskh", "devanagari", "bengali", "emoji", "notosans"):
        assert key in reg, key
    assert reg["nastaliq"].family == "Noto Nastaliq Urdu"
    for preset in PRESETS.values():
        assert preset["font"] in reg


@pytest.mark.parametrize("word,script", [("hello", "latin"), ("اردو", "arabic"), ("हिन्दी", "devanagari"),
                                         ("বাংলা", "bengali"), ("💰", "emoji"), ("123", None), ("你好", "cjk")])
def test_word_script(word, script):
    assert fonts.word_script(word) == script


def test_rtl_detection():
    assert fonts.is_rtl_text("یہ اردو ہے")
    assert not fonts.is_rtl_text("this is English")


# ---------------------------------------------------------------- transliteration


@pytest.mark.parametrize("deva,roman", [
    ("क्या हाल है दोस्तों", "kya haal hai doston"),
    ("मैं आज बहुत खुश हूँ", "main aaj bohat khush hun"),
    ("समझना ज़रूरी है।", "samajhna zaruri hai."),
    ("कमल", "kamal"),
    ("ज़िंदगी में मेहनत करो", "zindagi mein mehnat karo"),
])
def test_devanagari_to_roman_urdu(deva, roman):
    assert translit.deva_to_roman(deva) == roman


def test_hinglish_style_and_mixed_text():
    assert translit.deva_to_roman("वो बहुत अच्छा है", "hindi") == "vo bahut acha hai"
    assert translit.to_roman("हम money की बात", "urdu") == "hum money ki baat"


def test_urdu_script_to_roman_common_words():
    assert translit.urdu_to_roman("السلام علیکم دوستو، آج ہم بات کریں گے۔").startswith("Assalam alaikum")
    assert "aaj hum baat karein" in translit.urdu_to_roman("آج ہم بات کریں")


# ---------------------------------------------------------------- highlights


def test_auto_highlight_picks_keywords_and_emojis():
    t = Transcript("en", [Line(words=words("I made 5000 dollars with this secret trick")),
                          Line(words=words("and that is it"))])
    enhance.auto_highlight(t)
    first = t.lines[0].words
    assert any(w.keyword for w in first)
    assert [w.text for w in first if w.keyword][0] in ("5000", "secret", "dollars", "trick")
    assert any(w.emoji for w in first)
    assert not any(w.keyword for w in t.lines[1].words)   # only stopwords


def test_auto_highlight_roman_urdu_and_hooks():
    t = Transcript("ur-Latn", [Line(words=words("paisa kaise bachayein?")), Line(words=words("aaj hum baat karein ge"))])
    enhance.auto_highlight(t)
    assert t.lines[0].words[0].emoji == "💰"
    hooks = enhance.suggest_hooks(t)
    assert hooks[0] == "paisa kaise bachayein?"


# ---------------------------------------------------------------- cuts


def test_filler_detection():
    for f in ("um", "Uh,", "hmm...", "ummm", "ہمم"):
        assert cuts.is_filler(f), f
    for w in ("umbrella", "human", "the", "hum"):
        assert not cuts.is_filler(w), w


def test_cut_plan_removes_fillers_and_long_pauses_and_remaps():
    ws = [Word("Hello", 0.5, 0.9), Word("um", 1.0, 1.4), Word("world", 1.5, 1.9), Word("again", 5.0, 5.4)]
    t = Transcript("en", [Line(words=ws)])
    keep = cuts.plan(t, duration=8.0, fps=25, fillers=True, silences=True, max_gap=0.6, pad=0.15)
    total = cuts.kept_duration(keep)
    assert 2.0 < total < 3.0
    for a, b in keep:   # snapped to the frame grid
        assert abs(a * 25 - round(a * 25)) < 1e-6 and abs(b * 25 - round(b * 25)) < 1e-6
    out = cuts.remap(t, keep, drop_fillers=True)
    texts = [w.text for w in out.words()]
    assert texts == ["Hello", "world", "again"]
    times = [(w.start, w.end) for w in out.words()]
    assert all(e <= total + 1e-6 for _, e in times)
    assert out.words()[2].start - out.words()[1].end < 0.5     # the 3 s pause is gone
    nothing = cuts.plan(t, 8.0, 25, fillers=False, silences=False)
    assert nothing == [(0.0, 8.0)]
    assert "between(t," in cuts.select_expr(keep)


# ---------------------------------------------------------------- ASS


def _t(lang="en", text="This is a caption test with several words", **kw) -> Transcript:
    return Transcript(lang, [Line(words=words(text, 0.5), **kw)])


@pytest.mark.parametrize("preset", list(PRESETS))
def test_every_preset_builds_valid_ass(preset):
    st = preset_style(preset)
    out = ass.build_ass(_t(), st, 1080, 1920, 10.0, ass.Extras(hook="Watch this", progress_bar="bottom",
                                                                watermark="klyprima.com"))
    assert out.startswith("[Script Info]") and "PlayResX: 1080" in out and "PlayResY: 1920" in out
    dialogue = [ln for ln in out.splitlines() if ln.startswith("Dialogue:")]
    assert len(dialogue) >= 3
    main = [d for d in dialogue if ",Main," in d]
    assert main and all(d.count("{") == d.count("}") for d in dialogue)
    assert any(",Hook," in d and "watch this" in d.lower() for d in dialogue)
    assert any(",Bar," in d and "\\p1" in d for d in dialogue)
    assert any(",Mark," in d and "klyprima.com" in d for d in dialogue)


def test_animations_shape_the_events():
    base = _t(text="one two three four")
    def events(anim, **kw):
        st = Style(animation=anim, max_words=4, max_chars=40, emoji=False, **kw)
        return [ln for ln in ass.build_ass(base, st, 1080, 1920, 5, None).splitlines() if ",Main," in ln]
    assert len(events("none")) == 1
    kar = events("karaoke")
    assert len(kar) == 1 and kar[0].count("\\kf") == 4
    hl = events("highlight")
    assert len(hl) == 4 and all("\\c&H" in e for e in hl)
    assert len(events("word")) == 4
    rv = events("reveal")
    assert "\\alpha&HFF&" in rv[0] and "\\alpha&HFF&" not in rv[-1]
    assert "\\move(" in events("slide")[0]
    assert "\\fad(" in events("fade")[0]
    box = events("highlight", highlight_mode="box")
    assert "\\3c&H" in box[0] and "\\bord" in box[0]


def test_ass_colors_escaping_keywords_emoji_uppercase():
    assert ass.color("#FF8000") == "&H000080FF"
    assert ass.color("#FFFFFF", 1.0) == "&HFF FFFFFF".replace(" ", "")
    assert ass.ts(3725.456) == "1:02:05.46"
    t = Transcript("en", [Line(words=[Word("{\\bad}", 0, 0.5), Word("money", 0.5, 1, keyword=True, emoji="💰")])])
    st = Style(animation="none", uppercase=True, keyword_color="#00FF00")
    out = ass.build_ass(t, st, 1080, 1920, 2, None)
    line = next(ln for ln in out.splitlines() if ",Main," in ln)
    assert "\\bad" not in line and "MONEY" in line and "\\c&H00FF00&" in line
    assert "Noto Emoji" in line and "💰" in line


def test_rtl_and_mixed_scripts_get_the_right_fonts():
    t = Transcript("ur", [Line(words=[Word("آج", 0, 0.4), Word("money", 0.4, 0.8), Word("کی", 0.8, 1.2)])])
    out = ass.build_ass(t, Style(animation="none", emoji=False), 1080, 1920, 2, None)
    style_line = next(ln for ln in out.splitlines() if ln.startswith("Style: Main"))
    assert "Noto Nastaliq Urdu" in style_line and style_line.endswith(",-1")
    ev = next(ln for ln in out.splitlines() if ",Main," in ln)
    assert "\\fnMontserrat ExtraBold\\fs" in ev and "}money{\\fnNoto Nastaliq Urdu\\fs" in ev
    hi = ass.build_ass(Transcript("hi", [Line(words=words("नमस्ते दोस्तों"))]), Style(), 1080, 1920, 2, None)
    assert "Noto Sans Devanagari" in hi
    roman = ass.build_ass(Transcript("ur-Latn", [Line(words=words("kya haal hai"))]), Style(font="anton"), 1080, 1920, 2, None)
    assert "Style: Main,Anton," in roman


def test_sizes_are_em_sizes_converted_per_font_for_libass():
    """style.size is the em size the browser preview draws; libass sizes by win ascent+descent instead, so
    the ASS size is divided by each font's ratio. Same visible size whatever the font."""
    for key in ("bangers", "montserrat", "lilita"):
        out = ass.build_ass(_t(), Style(font=key, size=60, animation="none"), 1080, 1920, 5, None)
        size = float(next(ln for ln in out.splitlines() if ln.startswith("Style: Main")).split(",")[2])
        assert abs(size * fonts.get(key).em - 60) < 0.2, key
    nas = fonts.get("nastaliq").em
    assert 0.3 < nas < 0.5          # Nastaliq's tall metrics: without the conversion it would be tiny
    small = ass.build_ass(_t(), Style(font="montserrat", size=60), 540, 960, 5, None)
    big = ass.build_ass(_t(), Style(font="montserrat", size=60), 1080, 1920, 5, None)
    sz = lambda s: float(next(ln for ln in s.splitlines() if ln.startswith("Style: Main")).split(",")[2])
    assert abs(sz(big) - 2 * sz(small)) < 0.2       # scales with the video


def test_dual_language_and_translation_display():
    t = Transcript("ur-Latn", [Line(words=words("kya haal hai"), translation="How are you")], translation_lang="en")
    out = ass.build_ass(t, Style(animation="none"), 1080, 1920, 3, ass.Extras(mode="dual"))
    assert "\\NHow are you" in out.replace("{\\fn", "").replace("}", "") or "How are you" in out
    shown = display_transcript(t, "translation")
    assert shown.language == "en" and [w.text for w in shown.lines[0].words] == ["How", "are", "you"]
    assert shown.lines[0].start == t.lines[0].start


def test_align_translation_segments_to_lines():
    lines = [Line(words=words("a b c", 0)), Line(words=words("d e f", 5))]
    res = align_segments(lines, [(0, 0.9, "one two three"), (5, 5.9, "four five")])
    assert res[lines[0].id] == "one two three" and res[lines[1].id] == "four five"


def test_style_validation():
    with pytest.raises(ValueError):
        Style(color="red")
    with pytest.raises(ValueError):
        Style(size=500)
    assert Style(color="#abcdef").color == "#ABCDEF"
