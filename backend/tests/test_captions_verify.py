"""Unit tests of the caption accuracy layer (app/captions/verify.py): comparing two listens, the guards on
the AI judge's answers, keeping word timings when a line is rewritten, and flagging lines to check."""

from __future__ import annotations

import pytest

from app.captions import llm, stt, verify
from app.captions.transcript import Line, Transcript, Word
from app.config import get_settings


def words(text: str, start: float = 0.0, step: float = 0.4, prob: float = 0.95) -> list[Word]:
    out, t = [], start
    for x in text.split():
        out.append(Word(x, t, t + step - 0.05, prob=prob))
        t += step
    return out


def transcript(*sentences: tuple[str, float], prob: float = 0.95) -> Transcript:
    return Transcript(language="en", lines=[Line(words=words(s, at, prob=prob), id=f"l{i}")
                                            for i, (s, at) in enumerate(sentences)])


@pytest.fixture
def judge(monkeypatch):
    """A fake AI judge: answers[id] = (text, sure); records what it was asked."""
    seen: dict = {"items": None}
    answers: dict[str, tuple[str, bool]] = {}

    def fake(items, language, hints, title, progress=None, cancelled=None):
        seen["items"], seen["language"], seen["hints"], seen["title"] = items, language, hints, title
        return {i["id"]: answers[i["id"]] for i in items if i["id"] in answers}
    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "verify", fake)
    seen["answers"] = answers
    return seen


@pytest.fixture
def second(monkeypatch, tmp_path):
    """The second listen returns these words (relative to the audio)."""
    box: dict = {"words": None, "calls": 0}

    def fake(audio, language, prompt, first, cancelled=lambda: False, progress=lambda p: None):
        box["calls"] += 1
        box["language"] = language
        if box["words"] is None:
            return None
        return stt.SttResult(language, [Word(w.text, w.start, w.end, prob=w.prob) for w in box["words"]], "groq",
                             [], "whisper-large-v3")
    monkeypatch.setattr(stt, "second_listen", fake)
    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"ID3" + b"\0" * 2000)
    box["audio"] = audio
    return box


FIRST = stt.SttResult("en", [], "groq", [], "whisper-large-v3-turbo")


# ---------------------------------------------------------------- comparing


def test_key_and_units_ignore_case_punctuation_and_symbols():
    assert verify.key("Hello,") == verify.key("hello") == "hello"
    assert verify.units("Save MONEY, fast!", "en") == ["save", "money", "fast"]
    assert verify.units("你好，世界", "zh") == ["你", "好", "世", "界"]
    # Combining marks stay: Devanagari words are compared whole.
    assert verify.units("क्या हाल", "hi") == ["क्या", "हाल"]


def test_plausible_rejects_paraphrase_translation_and_rambling():
    heard = verify.units("today I will show you how to safe money", "en")
    alt = verify.units("today I will show you how to save money fast", "en")
    assert verify.plausible("Today I will show you how to save money fast.", heard, alt, "en")
    assert not verify.plausible("In this video, saving cash quickly is explained.", heard, alt, "en")
    assert not verify.plausible("Aaj main aapko dikhaunga paise kaise bachayein", heard, alt, "en")
    assert not verify.plausible("today I will show you how to save money fast and also many other things "
                                "about money that you never knew before", heard, alt, "en")
    # Whole line removed: only short, and only when the second listen heard nothing there.
    thanks = verify.units("Thanks for watching", "en")
    assert verify.plausible("", thanks, [], "en")
    assert not verify.plausible("", thanks, None, "en")
    assert not verify.plausible("", heard, [], "en")


def test_assign_gives_words_to_lines_and_finds_skipped_speech():
    lines = [Line(words=words("one two three", 0.0), id="a"), Line(words=words("four five", 3.0), id="b")]
    alt = words("one two three", 0.02) + words("four five", 3.01) + words("this was skipped entirely", 8.0)
    by_line, missing = verify.assign(lines, alt)
    assert [w.text for w in by_line["a"]] == ["one", "two", "three"]
    assert [w.text for w in by_line["b"]] == ["four", "five"]
    assert len(missing) == 1 and [w.text for w in missing[0]] == ["this", "was", "skipped", "entirely"]
    # A lone low-confidence word in silence is not "skipped speech".
    _, missing = verify.assign(lines, words("hmm", 8.0, prob=0.2))
    assert missing == []


def test_merge_ranges_pads_and_joins():
    assert verify.merge_ranges([(10, 20), (20.5, 30), (50, 60)]) == [(9, 31), (49, 61)]


# ---------------------------------------------------------------- rewriting


def test_rewrite_keeps_timings_of_unchanged_words_and_highlights():
    ln = Line(words=words("how to safe money", 1.0))
    ln.words[3].keyword = True
    before = [(w.start, w.end) for w in ln.words]
    n = verify.rewrite(ln, "How to save money.", [], "en")
    assert [w.text for w in ln.words] == ["How", "to", "save", "money."]
    assert [(w.start, w.end) for w in ln.words] == before
    assert ln.words[3].keyword and n == 1


def test_rewrite_adds_a_dropped_word_with_the_second_listen_timing():
    ln = Line(words=words("save money", 1.0))                    # 1.0-1.35, 1.4-1.75
    alt = [Word("save", 1.0, 1.35), Word("money", 1.4, 1.75), Word("fast", 1.8, 2.1)]
    n = verify.rewrite(ln, "save money fast", alt, "en")
    assert [w.text for w in ln.words] == ["save", "money", "fast"] and n == 1
    assert (ln.words[2].start, ln.words[2].end) == (1.8, 2.1)


def test_rewrite_insert_without_timing_uses_the_pause_or_shares_a_word():
    ln = Line(words=[Word("I", 0.0, 0.2), Word("it", 1.0, 1.2)])   # a 0.8 s pause in the middle
    verify.rewrite(ln, "I love it", [], "en")
    love = ln.words[1]
    assert love.text == "love" and 0.2 <= love.start < love.end <= 1.0
    ln = Line(words=[Word("I", 0.0, 0.5), Word("it", 0.5, 0.9)])   # no pause: shares the previous word
    verify.rewrite(ln, "I love it", [], "en")
    assert [w.text for w in ln.words] == ["I", "love", "it"]
    assert ln.words[0].end <= ln.words[1].start + 1e-9 and ln.words[1].end <= 0.5 + 1e-9


def test_rewrite_removes_an_invented_word():
    ln = Line(words=words("we we talk about money", 0.0))
    keep = [(w.start, w.end) for w in ln.words[1:]]
    n = verify.rewrite(ln, "we talk about money", [], "en")
    assert [w.text for w in ln.words] == ["we", "talk", "about", "money"] and n == 1
    assert [(w.start, w.end) for w in ln.words][1:] == keep[1:]


# ---------------------------------------------------------------- the whole check


def test_agreeing_lines_are_skipped_only_disagreements_go_to_the_judge(judge, second):
    t = transcript(("Hello everyone welcome to the channel.", 0.0), ("Today I will show you how to safe money.", 4.0))
    second["words"] = words("Hello everyone welcome to the channel.", 0.0) + \
        words("Today I will show you how to save money fast.", 4.0)
    judge["answers"]["l1"] = ("Today I will show you how to save money fast.", True)
    today = (t.lines[1].words[0].start, t.lines[1].words[0].end)
    rep = verify.run(t, second["audio"], FIRST, stt_lang="en", prompt="Klyprima", title="Money tips", duration=12)
    assert [i["id"] for i in judge["items"]] == ["l1"]
    item = judge["items"][0]
    assert item["heard"] == "Today I will show you how to safe money." and item["alt"].endswith("save money fast.")
    assert item["before"].endswith("to the channel.") and item["after"] == ""
    assert judge["language"] == "English" and judge["hints"] == "Klyprima" and judge["title"] == "Money tips"
    assert t.lines[1].text("en") == "Today I will show you how to save money fast."
    assert (t.lines[1].words[0].start, t.lines[1].words[0].end) == today
    assert rep.listens == 2 and rep.second == "whisper-large-v3" and rep.ai
    assert rep.agreed == 1 and rep.checked == 1 and rep.fixed_lines == 1 and rep.fixed_words == 2
    assert rep.flagged == 0 and not any(ln.check for ln in t.lines)


def test_unsure_first_listen_is_checked_even_when_both_agree(judge, second):
    t = transcript(("Karachi is a big city", 0.0), prob=0.3)
    second["words"] = words("Karachi is a big city", 0.0)
    judge["answers"]["l0"] = ("Karachi is a big city", True)
    rep = verify.run(t, second["audio"], FIRST, stt_lang="en", duration=5)
    assert judge["items"][0]["unsure"] is True and rep.checked == 1 and rep.fixed_words == 0


def test_judge_not_sure_flags_the_line(judge, second):
    t = transcript(("the price is fifteen dollars", 0.0))
    second["words"] = words("the price is fifty dollars", 0.0)
    judge["answers"]["l0"] = ("the price is fifteen dollars", False)
    rep = verify.run(t, second["audio"], FIRST, stt_lang="en", duration=5)
    assert t.lines[0].check and rep.flagged == 1
    assert t.to_dict()["lines"][0]["check"] is True


def test_paraphrased_answer_is_ignored(judge, second):
    t = transcript(("today we talk about money", 0.0))
    second["words"] = words("today we talk about the money", 0.0)
    judge["answers"]["l0"] = ("This episode covers personal finance topics in depth", True)
    verify.run(t, second["audio"], FIRST, stt_lang="en", duration=5)
    assert t.lines[0].text("en") == "today we talk about money"


def test_skipped_speech_is_put_back_and_flagged_invented_line_removed(judge, second):
    t = transcript(("we start the show now", 0.0), ("Thanks for watching", 20.0))
    second["words"] = words("we start the show now", 0.0) + words("and this part was skipped", 5.0)
    judge["answers"]["m0"] = ("and this part was skipped", True)
    judge["answers"]["l1"] = ("", True)
    rep = verify.run(t, second["audio"], FIRST, stt_lang="en", duration=25)
    texts = [ln.text("en") for ln in t.lines]
    assert texts == ["we start the show now", "and this part was skipped"]
    assert t.lines[1].check and abs(t.lines[1].start - 5.0) < 1e-6
    assert rep.added_lines == 1 and rep.removed_lines == 1


def test_without_ai_strong_disagreements_are_flagged(monkeypatch, second):
    monkeypatch.setattr(llm, "available", lambda: False)
    t = transcript(("we talk about money", 0.0), ("this line is fine", 3.0), ("a b c d", 6.0))
    second["words"] = words("we talk about money", 0.0) + words("this line is fine.", 3.0) + words("w x y z", 6.0)
    rep = verify.run(t, second["audio"], FIRST, stt_lang="en", duration=9)
    assert [ln.check for ln in t.lines] == [False, False, True]
    assert not rep.ai and rep.flagged == 1


def test_ai_failure_never_breaks_the_captions(monkeypatch, second):
    monkeypatch.setattr(llm, "available", lambda: True)

    def boom(*a, **kw):
        raise llm.LlmError("busy")
    monkeypatch.setattr(llm, "verify", boom)
    t = transcript(("we talk about money", 0.0))
    second["words"] = words("we talk about honey", 0.0)
    rep = verify.run(t, second["audio"], FIRST, stt_lang="en", duration=3)
    assert t.lines[0].text("en") == "we talk about money" and not rep.ai


def test_no_second_listen_sends_every_line_to_the_judge(judge, second):
    t = transcript(("one two three", 0.0), ("four five six", 3.0))
    judge["answers"]["l0"] = ("one too three", True)
    rep = verify.run(t, second["audio"], FIRST, stt_lang="en", duration=6)
    assert [i["id"] for i in judge["items"]] == ["l0", "l1"] and "alt" not in judge["items"][0]
    assert rep.listens == 1 and t.lines[0].text("en") == "one too three"


def test_long_videos_skip_the_second_listen(judge, second, monkeypatch):
    monkeypatch.setattr(get_settings(), "captions_verify_listen_max_sec", 60)
    t = transcript(("one two three", 0.0))
    verify.run(t, second["audio"], FIRST, stt_lang="en", duration=61)
    assert second["calls"] == 0


def test_only_some_lines_and_ranges_with_an_audio_offset(judge, second, monkeypatch):
    cuts = []
    monkeypatch.setattr(stt, "extract_audio", lambda src, dest, start=0.0, duration=None: cuts.append((start, duration)) or src)
    t = transcript(("first line here", 100.0), ("clip line here", 130.0), ("last line here", 160.0))
    # The audio starts at 100 s of the video; the second listen hears the clip piece (starts at 29 s).
    second["words"] = words("clip line hear", 1.0)
    judge["answers"]["l1"] = ("clip line here", True)
    rep = verify.run(t, second["audio"], FIRST, stt_lang="en", only=[t.lines[1]], ranges=[(129.0, 132.5)],
                     audio_offset=100.0)
    assert [i["id"] for i in judge["items"]] == ["l1"] and judge["items"][0]["alt"] == "clip line hear"
    assert rep.lines == 1 and rep.listens == 2 and cuts == [(29.0, 3.5)]


def test_a_word_that_looks_like_a_hint_is_checked_even_when_both_agree(judge, second):
    t = transcript(("welcome back to Clyprama", 0.0), ("we talk about money", 3.0))
    second["words"] = words("welcome back to Clyprama", 0.0) + words("we talk about money", 3.0)
    judge["answers"]["l0"] = ("welcome back to Klyprima", True)
    rep = verify.run(t, second["audio"], FIRST, stt_lang="en", prompt="Klyprima, Karachi", duration=6)
    assert [i["id"] for i in judge["items"]] == ["l0"] and rep.agreed == 1
    assert t.lines[0].text("en") == "welcome back to Klyprima"
    assert verify.hint_terms("Klyprima, Dr. Shehzad", "Klyprima") == ["klyprima", "shehzad"]
