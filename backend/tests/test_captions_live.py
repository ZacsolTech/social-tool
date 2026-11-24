"""Live tests against the real speech-to-text and AI services (skipped unless set up).

    KLY_LIVE_STT=1 uv run pytest tests/test_captions_live.py      # local faster-whisper (downloads the tiny model)
    CF_GROQ_API_KEY=... uv run pytest tests/test_captions_live.py  # + Groq
    CF_ANTHROPIC_API_KEY=... uv run pytest tests/test_captions_live.py  # + Claude

Speech is generated with the operating system's text-to-speech (Windows SAPI or espeak-ng).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from app.captions import enhance, llm, stt
from app.captions.transcript import Line, Transcript, Word, build_lines
from app.config import get_settings
from app.reframe.media import ffmpeg_bin

SENTENCE = "Hello everyone and welcome back to the channel. Today I will show you how to save money."


def _speech(tmp: Path) -> Path | None:
    wav = tmp / "speech.wav"
    if sys.platform == "win32":
        ps = (f"Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$s.Rate = -1; $s.SetOutputToWaveFile('{wav}'); $s.Speak('{SENTENCE}'); $s.Dispose()")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=120)
    elif shutil.which("espeak-ng"):
        subprocess.run(["espeak-ng", "-w", str(wav), SENTENCE], capture_output=True, timeout=120)
    if not wav.exists() or wav.stat().st_size < 10_000:
        return None
    mp3 = tmp / "speech.mp3"
    subprocess.run([ffmpeg_bin(), "-v", "error", "-y", "-i", str(wav), "-ac", "1", "-ar", "16000", "-b:a", "32k", str(mp3)],
                   check=True)
    return mp3


@pytest.fixture
def speech(tmp_path) -> Path:
    p = _speech(tmp_path)
    if p is None:
        pytest.skip("no text-to-speech engine on this machine")
    return p


def _check_english(res: stt.SttResult) -> None:
    text = " ".join(w.text for w in res.words).lower()
    for word in ("welcome", "channel", "money"):
        assert word in text, text
    assert all(w.end > w.start for w in res.words)
    assert res.words == sorted(res.words, key=lambda w: w.start)
    lines = build_lines(res.words, "en")
    assert len(lines) >= 1


@pytest.mark.skipif(not os.environ.get("KLY_LIVE_STT"), reason="set KLY_LIVE_STT=1 to run local whisper")
def test_local_whisper_transcribes_real_speech(speech, monkeypatch):
    monkeypatch.setattr(get_settings(), "groq_api_key", None)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(get_settings(), "local_whisper_model", os.environ.get("KLY_LIVE_MODEL", "tiny"))
    res = stt.transcribe(speech, None)
    assert res.provider == "local" and res.language == "en"
    _check_english(res)
    segs = stt.translate_to_english(speech)
    assert segs and "money" in " ".join(s[2] for s in segs).lower()


@pytest.mark.skipif(not (get_settings().groq_api_key or os.environ.get("GROQ_API_KEY")), reason="no Groq key")
def test_groq_transcribes_real_speech(speech):
    res = stt.transcribe(speech, "en", prompt="Klyprima")
    assert res.provider == "groq"
    _check_english(res)


@pytest.mark.skipif(not llm.available(), reason="no Anthropic key")
def test_claude_translate_romanize_enhance():
    lines = [("a", "Hello friends, how are you?"), ("b", "Today we will talk about saving money.")]
    out = llm.translate(lines, "English", "Urdu")
    assert set(out) == {"a", "b"} and any("؀" <= c <= "ۿ" for c in out["a"])
    rom = llm.romanize([("a", ["کیا", "حال", "ہے"])], "urdu")
    assert len(rom["a"]) == 3 and rom["a"][0].lower().startswith("k")
    picks, hooks = llm.enhance([("a", ["I", "saved", "5000", "dollars", "this", "month"])], "English")
    assert "a" in picks and 0 <= picks["a"][0] < 6 and hooks


@pytest.mark.skipif(not os.environ.get("KLY_LIVE_STT"), reason="set KLY_LIVE_STT=1 to run local whisper")
def test_full_api_flow_with_real_speech(speech, tmp_path, isolated, monkeypatch):
    """No fakes: a video with spoken audio -> upload -> local Whisper -> burned-in captions."""
    from fastapi.testclient import TestClient

    from app.captions import api as capi
    from app.captions import jobs as cjobs
    from app.main import app
    from app.reframe.media import probe
    from tests.conftest import wait_for
    from tests.test_api import upload

    monkeypatch.setattr(cjobs, "JOBS_DIR", isolated / "captions")
    monkeypatch.setattr(get_settings(), "groq_api_key", None)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.setattr(get_settings(), "local_whisper_model", os.environ.get("KLY_LIVE_MODEL", "tiny"))
    capi._window.clear()
    video = tmp_path / "talk.mp4"
    subprocess.run([ffmpeg_bin(), "-v", "error", "-y", "-f", "lavfi", "-i", "color=c=0x334455:s=1280x720:r=25",
                    "-i", str(speech), "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(video)],
                   check=True)
    with TestClient(app) as c:
        uid = upload(c, video)
        jid = c.post("/api/captions/jobs", json={"source": {"type": "upload", "id": uid}}).json()["id"]
        wait_for(lambda: c.get(f"/api/captions/jobs/{jid}").json()["state"] not in cjobs.ACTIVE, 600)
        job = c.get(f"/api/captions/jobs/{jid}").json()
        assert job["state"] == "ready", job["error"]
        assert job["provider"] == "local" and job["detected_language"] == "en"
        assert "money" in " ".join(ln["text"] for ln in job["transcript"]["lines"]).lower()
        c.post(f"/api/captions/jobs/{jid}/enhance", json={})
        wait_for(lambda: c.get(f"/api/captions/jobs/{jid}").json()["state"] not in cjobs.ACTIVE, 60)
        c.post(f"/api/captions/jobs/{jid}/render", json={"quality": "720p", "remove_silences": True})
        wait_for(lambda: c.get(f"/api/captions/jobs/{jid}").json()["state"] not in cjobs.ACTIVE, 300)
        job = c.get(f"/api/captions/jobs/{jid}").json()
        assert job["output"], job["error"]
        assert probe(cjobs.get(jid).output.path).height == 720


def test_heuristics_are_always_available():
    t = Transcript("en", [Line(words=[Word("Save", 0, 0.3), Word("money", 0.3, 0.6), Word("now", 0.6, 0.9)])])
    enhance.auto_highlight(t)
    assert any(w.keyword for w in t.words())
