"""System tests of the caption tool through its HTTP API: upload -> AI captions -> edit -> AI actions ->
burn-in render -> downloads, plus links, Reframe hand-offs, SRT import, logo, limits and cleanup.

Speech-to-text and the AI text model are replaced by deterministic fakes (the real ones are covered by
tests/test_captions_live.py when keys / models are available). FFmpeg rendering is real.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import cv2
import numpy as np
import pytest
from fastapi.testclient import TestClient

from app import jobs as dl_jobs
from app.captions import api as capi
from app.captions import jobs as cjobs
from app.captions import llm, stt
from app.captions.transcript import Word
from app.config import get_settings
from app.main import app
from app.reframe import api as rapi
from app.reframe import jobs as rjobs
from app.reframe.media import ffmpeg_bin, probe
from tests.conftest import wait_for
from tests.test_api import upload

SPEECH = {
    "en": "Hello everyone um welcome to the channel. Today I will show you how to save money fast.",
    "hi": "क्या हाल है दोस्तों आज हम पैसे की बात करेंगे",
    "ur": "آج ہم پیسے کی بات کریں گے",
}


def fake_words(text: str, start: float = 0.3, step: float = 0.32) -> list[Word]:
    out, t = [], start
    for x in text.split():
        out.append(Word(x, t, t + step - 0.04))
        t += step
    return out


@pytest.fixture
def calls():
    return []


@pytest.fixture
def client(isolated, monkeypatch, calls):
    monkeypatch.setattr(cjobs, "JOBS_DIR", isolated / "captions")
    cjobs._jobs.clear()
    capi._minute.clear()
    capi._window.clear()
    rapi._minute.clear()
    rapi._daily.clear()

    def transcribe(audio, language, prompt=None, cancelled=lambda: False, progress=lambda p: None, stage=lambda s: None):
        calls.append(("stt", language, prompt))
        assert Path(audio).exists() and Path(audio).stat().st_size > 1000
        lang = language or "en"
        progress(0.5)
        return stt.SttResult(lang, fake_words(SPEECH.get(lang, SPEECH["en"])), "fake")

    def translate_en(audio, prompt=None, cancelled=lambda: False):
        calls.append(("stt-translate",))
        return [(0.3, 2.0, "How are you friends"), (2.0, 4.0, "today we talk about money")]

    monkeypatch.setattr(stt, "transcribe", transcribe)
    monkeypatch.setattr(stt, "translate_to_english", translate_en)
    monkeypatch.setattr(llm, "available", lambda: False)
    with TestClient(app) as c:
        yield c
    for j in list(cjobs._jobs.values()):
        j.cancel.set()


def settle(c: TestClient, jid: str, timeout: float = 240) -> dict:
    out: dict = {}

    def done() -> bool:
        nonlocal out
        out = c.get(f"/api/captions/jobs/{jid}").json()
        return out["state"] not in cjobs.ACTIVE
    wait_for(done, timeout)
    return out


def create(c: TestClient, media_path: Path, **body) -> dict:
    uid = upload(c, media_path)
    r = c.post("/api/captions/jobs", json={"source": {"type": "upload", "id": uid}, **body})
    assert r.status_code == 200, r.text
    return settle(c, r.json()["id"])


def frame(path: Path, t: float) -> np.ndarray:
    raw = subprocess.run([ffmpeg_bin(), "-v", "error", "-ss", f"{t}", "-i", str(path), "-frames:v", "1",
                          "-f", "image2pipe", "-vcodec", "png", "-"], capture_output=True, check=True).stdout
    return cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)


# ---------------------------------------------------------------- config


def test_config_lists_languages_presets_fonts(client):
    cfg = client.get("/api/captions/config").json()
    codes = [x["code"] for x in cfg["languages"]]
    assert codes[:3] == ["en", "ur", "ur-Latn"] and "hi-Latn" in codes and "ar" in codes
    assert len(cfg["presets"]) >= 12 and cfg["presets"][0]["style"]["font"]
    assert any(f["key"] == "nastaliq" for f in cfg["fonts"])
    assert cfg["features"] == {"ai": False, "stt": stt.provider_name(), "translate_any": False}
    font = next(f for f in cfg["fonts"] if f["key"] == "montserrat")
    r = client.get(font["url"])
    assert r.status_code == 200 and r.content[:4] in (b"\x00\x01\x00\x00", b"OTTO", b"true")
    assert "immutable" in r.headers["cache-control"]
    assert client.get("/api/captions/fonts/../../app/config.py").status_code == 404


# ---------------------------------------------------------------- the main flow


def test_upload_transcribe_edit_render_and_download(client, media, calls):
    job = create(client, media["plain"], language="auto", prompt="Klyprima")
    assert job["state"] == "ready", job["error"]
    assert calls[0] == ("stt", None, "Klyprima")
    t = job["transcript"]
    assert t["language"] == "en" and t["rev"] == 1 and len(t["lines"]) >= 2
    assert t["lines"][0]["text"].startswith("Hello everyone")
    assert job["files"]["srt"].endswith("/file/srt")

    # Polling with the current rev leaves the (large) transcript out.
    slim = client.get(f"/api/captions/jobs/{job['id']}?since_rev=1").json()
    assert "transcript" not in slim and slim["transcript_rev"] == 1

    # Edit: fix a word and retype a line.
    lines = t["lines"]
    lines[0]["words"][0]["text"] = "Hi"
    r = client.put(f"/api/captions/jobs/{job['id']}/transcript", json={"rev": 1, "lines": lines})
    assert r.status_code == 200, r.text
    assert r.json()["transcript"]["rev"] == 2 and r.json()["transcript"]["lines"][0]["text"].startswith("Hi everyone")
    stale = client.put(f"/api/captions/jobs/{job['id']}/transcript", json={"rev": 1, "lines": lines})
    assert stale.status_code == 409

    # Exports.
    srt = client.get(job["files"]["srt"])
    assert srt.status_code == 200 and "attachment" in srt.headers["content-disposition"]
    assert "00:00:00,300 --> " in srt.text and "Hi everyone" in srt.text
    assert client.get(job["files"]["vtt"]).text.startswith("WEBVTT")
    assert "Hi everyone" in client.get(job["files"]["txt"]).text

    # Render with a hook, progress bar and watermark.
    r = client.post(f"/api/captions/jobs/{job['id']}/render", json={
        "style": {"preset": "bold-pop", "font": "montserrat", "size": 64, "animation": "pop", "y": 0.5},
        "hook": "Save money fast", "progress_bar": "bottom", "watermark": True, "quality": "720p"})
    assert r.status_code == 200, r.text
    assert client.post(f"/api/captions/jobs/{job['id']}/render", json={}).status_code == 409    # busy
    done = settle(client, job["id"])
    assert done["state"] == "ready" and done["output"], done["error"]
    out = done["output"]
    vid = client.get(out["url"])
    assert vid.status_code == 200 and vid.headers["content-type"] == "video/mp4"
    assert int(vid.headers["content-length"]) == out["size"] and "klyprima-captions" in vid.headers["content-disposition"]
    path = cjobs.get(job["id"]).output.path
    info = probe(path)
    assert (info.width, info.height) == (1280, 720) and abs(info.duration - 5.0) < 0.3 and info.has_audio
    part = client.get(out["url"], headers={"Range": "bytes=0-99"})
    assert part.status_code == 206 and len(part.content) == 100

    # The captions really are burned in: the middle band changes, a caption-free corner doesn't.
    plain = cv2.resize(frame(media["plain"], 1.0), (1280, 720))
    capt = frame(path, 1.0)
    band = np.abs(capt[300:420, 300:980].astype(int) - plain[300:420, 300:980].astype(int)).mean()
    corner = np.abs(capt[600:700, 1100:1270].astype(int) - plain[600:700, 1100:1270].astype(int)).mean()
    assert band > 12 and corner < 6, (band, corner)

    # Re-render replaces the old file.
    r = client.post(f"/api/captions/jobs/{job['id']}/render", json={"style": {"animation": "karaoke"}, "quality": "720p"})
    done = settle(client, job["id"])
    assert done["output"]["version"] == 2 and not path.exists()


def test_filler_and_silence_removal_shortens_video(client, media):
    job = create(client, media["plain"], language="en")
    words = [w["text"] for ln in job["transcript"]["lines"] for w in ln["words"]]
    assert "um" in words
    r = client.post(f"/api/captions/jobs/{job['id']}/render", json={
        "quality": "720p", "remove_fillers": True, "remove_silences": True, "style": {"animation": "highlight"}})
    assert r.status_code == 200, r.text
    done = settle(client, job["id"])
    assert done["state"] == "ready" and done["output"], done["error"]
    info = probe(cjobs.get(job["id"]).output.path)
    assert info.duration < 5.0 - 0.3 and abs(info.duration - done["output"]["duration"]) < 0.25
    ass_text = (cjobs.get(job["id"]).dir / "captions.ass").read_text(encoding="utf-8")
    assert "um" not in [x.strip("{}") for x in ass_text.split()]


def test_roman_urdu_without_ai_uses_hindi_speech_and_offline_romanisation(client, media, calls):
    job = create(client, media["face"], language="ur-Latn")
    assert job["state"] == "ready", job["error"]
    assert calls[0][1] == "hi"
    t = job["transcript"]
    assert t["language"] == "ur-Latn" and job["rtl"] is False
    assert t["lines"][0]["text"].startswith("kya haal hai doston")


def test_urdu_script_translate_romanize_enhance(client, media, calls):
    job = create(client, media["face"], language="ur")
    assert job["transcript"]["language"] == "ur" and job["rtl"] is True
    jid = job["id"]

    # Without AI only English translation exists (Whisper's own translation, aligned to our lines).
    assert client.post(f"/api/captions/jobs/{jid}/translate", json={"target": "fr"}).status_code == 422
    assert client.post(f"/api/captions/jobs/{jid}/translate", json={"target": "xx"}).status_code == 422
    r = client.post(f"/api/captions/jobs/{jid}/translate", json={"target": "en"})
    assert r.status_code == 200, r.text
    job = settle(client, jid)
    assert job["transcript"]["translation_lang"] == "en"
    assert any(ln.get("translation") for ln in job["transcript"]["lines"])
    srt = client.get(job["files"]["srt"] + "?mode=dual").text
    assert "money" in srt

    # Highlights + hooks (offline heuristics).
    r = client.post(f"/api/captions/jobs/{jid}/enhance", json={"keywords": True, "emojis": True, "hooks": True})
    job = settle(client, jid)
    words = [w for ln in job["transcript"]["lines"] for w in ln["words"]]
    assert any(w.get("emoji") == "💰" for w in words)
    assert job["hooks"]

    # Dual-language render.
    r = client.post(f"/api/captions/jobs/{jid}/render", json={"mode": "dual", "quality": "720p",
                                                                "style": {"preset": "desi-bold", "box": True}})
    assert r.status_code == 200, r.text
    job = settle(client, jid)
    assert job["output"], job["error"]

    # Roman letters: without AI, Urdu script is listened to again as Hindi.
    r = client.post(f"/api/captions/jobs/{jid}/romanize")
    assert r.status_code == 200, r.text
    job = settle(client, jid)
    assert job["transcript"]["language"] == "ur-Latn" and calls[-1][1] == "hi"
    assert client.post(f"/api/captions/jobs/{jid}/romanize").status_code == 422     # already Roman


def test_ai_paths_are_used_when_configured(client, media, monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)
    seen = {}

    def translate(lines, source, target):
        seen["translate"] = (len(lines), source, target)
        return {i: f"[{target}] {t}" for i, t in lines}

    def romanize(lines, style):
        seen["romanize"] = style
        return {i: [f"r{k}" for k in range(len(w))] for i, w in lines}

    def enhance(lines, language):
        return {i: (0, "🔥") for i, _ in lines}, ["Hook one", "Hook two"]

    monkeypatch.setattr(llm, "translate", translate)
    monkeypatch.setattr(llm, "romanize", romanize)
    monkeypatch.setattr(llm, "enhance", enhance)
    assert client.get("/api/captions/config").json()["features"]["ai"] is True

    job = create(client, media["face"], language="ur-Latn")
    assert seen["romanize"] == "urdu" and job["transcript"]["lines"][0]["words"][0]["text"] == "r0"
    jid = job["id"]
    client.post(f"/api/captions/jobs/{jid}/translate", json={"target": "fr"})
    job = settle(client, jid)
    assert seen["translate"][2] == "French" and job["transcript"]["lines"][0]["translation"].startswith("[French]")
    client.post(f"/api/captions/jobs/{jid}/enhance", json={})
    job = settle(client, jid)
    assert job["hooks"] == ["Hook one", "Hook two"]
    first = job["transcript"]["lines"][0]["words"][0]
    assert first.get("keyword") and first.get("emoji") == "🔥"
    r = client.post(f"/api/captions/jobs/{jid}/render", json={"mode": "translation", "quality": "720p"})
    assert r.status_code == 200
    assert settle(client, jid)["output"]


def test_ai_failure_falls_back_to_offline(client, media, monkeypatch):
    monkeypatch.setattr(llm, "available", lambda: True)

    def boom(*a, **k):
        raise llm.LlmError("down")
    monkeypatch.setattr(llm, "romanize", boom)
    monkeypatch.setattr(llm, "enhance", boom)
    job = create(client, media["face"], language="ur-Latn")
    assert job["transcript"]["lines"][0]["text"].startswith("kya haal hai")
    client.post(f"/api/captions/jobs/{job['id']}/enhance", json={})
    job = settle(client, job["id"])
    assert job["state"] == "ready" and job["error"] is None


def test_srt_import_skips_ai_and_quota(client, media, calls, monkeypatch):
    monkeypatch.setattr(get_settings(), "captions_daily_per_ip", 0)
    srt = "1\n00:00:00,500 --> 00:00:02,000\nImported line one\n\n2\n00:00:02,500 --> 00:00:04,000\nLine two\n"
    job = create(client, media["plain"], language="en", subtitles=srt)
    assert job["state"] == "ready" and not calls
    assert [ln["text"] for ln in job["transcript"]["lines"]] == ["Imported line one", "Line two"]
    bad = client.post("/api/captions/jobs", json={"source": {"type": "upload", "id": upload(client, media["plain"])},
                                                   "subtitles": "nonsense"})
    assert settle(client, bad.json()["id"])["state"] == "error"
    over = client.post("/api/captions/jobs", json={"source": {"type": "upload", "id": upload(client, media["plain"])}})
    assert over.status_code == 429 and "limit" in over.json()["detail"]


def test_validation_ownership_cancel_and_cleanup(client, media):
    uid = upload(client, media["plain"])
    assert client.post("/api/captions/jobs", json={"source": {"type": "upload", "id": uid}, "language": "xx"}).status_code == 422
    assert client.post("/api/captions/jobs", json={"source": {"type": "upload", "id": "nope0000000000000"}}).status_code == 404
    other = {"x-forwarded-for": "203.0.113.7"}
    assert client.post("/api/captions/jobs", json={"source": {"type": "upload", "id": uid}}, headers=other).status_code == 403
    job = client.post("/api/captions/jobs", json={"source": {"type": "upload", "id": uid}}).json()
    job = settle(client, job["id"])
    jid = job["id"]
    for method, url, kw in [("put", f"/api/captions/jobs/{jid}/transcript", {"json": {"lines": []}}),
                            ("post", f"/api/captions/jobs/{jid}/render", {"json": {}}),
                            ("post", f"/api/captions/jobs/{jid}/enhance", {"json": {}}),
                            ("delete", f"/api/captions/jobs/{jid}", {})]:
        assert getattr(client, method)(url, headers=other, **kw).status_code == 403, url
    bad_style = client.post(f"/api/captions/jobs/{jid}/render", json={"style": {"color": "red"}})
    assert bad_style.status_code == 422
    assert client.post(f"/api/captions/jobs/{jid}/render", json={"style": {"font": "comic-sans"}}).status_code == 422
    assert client.post(f"/api/captions/jobs/{jid}/render", json={"mode": "dual"}).status_code == 422
    # Cancel a render: the captions stay editable.
    client.post(f"/api/captions/jobs/{jid}/render", json={"quality": "1080p"})
    client.delete(f"/api/captions/jobs/{jid}")
    after = settle(client, jid)
    assert after["state"] == "ready" and after["transcript_rev"] == 1
    assert not list(cjobs.get(jid).dir.glob("*.part.mp4"))
    # Cleanup after the TTL frees the job and the upload.
    j = cjobs.get(jid)
    d = j.dir
    j.created -= 10 * 86400
    cjobs.prune(3600)
    assert not d.exists() and client.get(f"/api/captions/jobs/{jid}").status_code == 404
    from app.reframe import uploads
    assert uploads.get(uid).used_by == 0


def test_logo_upload_and_render(client, media, tmp_path):
    job = create(client, media["plain"], language="en")
    jid = job["id"]
    assert client.put(f"/api/captions/jobs/{jid}/logo", content=b"not an image").status_code == 422
    logo = np.zeros((80, 200, 4), np.uint8)
    logo[..., 2] = 255
    logo[..., 3] = 255
    ok, png = cv2.imencode(".png", logo)
    r = client.put(f"/api/captions/jobs/{jid}/logo", content=png.tobytes())
    assert r.status_code == 200 and r.json()["has_logo"]
    client.post(f"/api/captions/jobs/{jid}/render", json={"quality": "720p", "logo": {"corner": "br", "scale": 0.2}})
    job = settle(client, jid)
    assert job["output"], job["error"]
    img = frame(cjobs.get(jid).output.path, 0.5)
    corner = img[640:700, 1150:1240]
    assert corner[..., 2].mean() > 180 and corner[..., 0].mean() < 80      # red logo bottom-right
    assert client.delete(f"/api/captions/jobs/{jid}/logo").json()["has_logo"] is False


def test_link_source_and_long_video_limit(client, media, monkeypatch, tmp_path):
    copy = tmp_path / "fetched.mp4"
    shutil.copyfile(media["face"], copy)
    opt = SimpleNamespace(id="v720", kind="video", best=True, has_audio=True, ext="mp4")
    item = SimpleNamespace(index=0, title="Linked clip", duration=6.0, error=None, options=[opt])
    resolved = SimpleNamespace(title="Post", item=lambda i: item)
    monkeypatch.setattr(rjobs, "link_lookup", lambda token: resolved if token == "tok1" else (_ for _ in ()).throw(KeyError()))
    monkeypatch.setattr(dl_jobs, "start", lambda r, it, o, s: SimpleNamespace(state="done", progress=1.0, path=copy, error=None))
    assert client.post("/api/captions/jobs", json={"source": {"type": "link", "token": "zzz"}}).status_code == 410
    r = client.post("/api/captions/jobs", json={"source": {"type": "link", "token": "tok1"}, "language": "en"})
    assert r.status_code == 200, r.text
    job = settle(client, r.json()["id"])
    assert job["state"] == "ready" and job["title"] == "Linked clip"
    assert client.get(job["source"]["url"], headers={"Range": "bytes=0-9"}).status_code == 206
    monkeypatch.setattr(get_settings(), "captions_max_duration_sec", 2)
    long = client.post("/api/captions/jobs", json={"source": {"type": "upload", "id": upload(client, media["plain"])}})
    assert long.status_code == 422 and "longer" in long.json()["detail"]


def test_make_it_vertical_and_back_keeps_the_captions(client, media, calls):
    """Captions -> Make it vertical (Reframe) -> Add captions: the transcript is carried over, no new AI run."""
    cap = create(client, media["face"], language="en")
    client.put(f"/api/captions/jobs/{cap['id']}/transcript",
               json={"rev": 1, "lines": [{**cap["transcript"]["lines"][0], "words": [
                   {**cap["transcript"]["lines"][0]["words"][0], "text": "Edited"}] + cap["transcript"]["lines"][0]["words"][1:]}]
                     + cap["transcript"]["lines"][1:]})
    r = client.post("/api/reframe/jobs", json={"source": {"type": "captions", "id": cap["id"]}, "mode": "blur",
                                               "quality": "720p"})
    assert r.status_code == 200, r.text
    rj = r.json()
    wait_for(lambda: client.get(f"/api/reframe/jobs/{rj['id']}").json()["state"] in ("done", "error"), 240)
    rj = client.get(f"/api/reframe/jobs/{rj['id']}").json()
    assert rj["state"] == "done", rj["error"]
    n_stt = len([c for c in calls if c[0] == "stt"])
    r = client.post("/api/captions/jobs", json={"source": {"type": "reframe", "id": rj["id"], "aspect": "9:16"},
                                                "reuse": cap["id"], "language": "en"})
    assert r.status_code == 200, r.text
    vert = settle(client, r.json()["id"])
    assert vert["state"] == "ready" and vert["info"]["height"] > vert["info"]["width"]
    assert vert["transcript"]["lines"][0]["words"][0]["text"] == "Edited"
    assert vert["transcript"]["source"] == "reused"
    assert len([c for c in calls if c[0] == "stt"]) == n_stt
    other = {"x-forwarded-for": "198.51.100.4"}
    assert client.post("/api/reframe/jobs", json={"source": {"type": "captions", "id": cap["id"]}}, headers=other).status_code == 403
    client.post(f"/api/captions/jobs/{vert['id']}/render", json={"quality": "720p"})
    done = settle(client, vert["id"])
    out = probe(cjobs.get(vert["id"]).output.path)
    assert out.height > out.width


def test_video_without_sound_is_explained(client, media):
    uid = upload(client, media["portrait"])
    r = client.post("/api/captions/jobs", json={"source": {"type": "upload", "id": uid}})
    job = settle(client, r.json()["id"])
    assert job["state"] == "error" and "no sound" in job["error"]


def test_health_counts_caption_jobs(client):
    h = client.get("/api/health").json()
    assert "captions_jobs" in h and "captions_waiting" in h
