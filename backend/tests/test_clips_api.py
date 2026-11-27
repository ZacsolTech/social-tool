"""System tests of AI Clips through its HTTP API: upload -> listen -> find moments -> render clips -> download,
edit and re-render one clip, search again, ZIP, links, the caption-editor hand-off, limits and cleanup.

Speech-to-text and the AI text model are deterministic fakes (the real ones are covered by the caption tool's
live tests). Video work is real: FFmpeg cuts, Smart Reframe analysis and rendering, libass captions.
"""

from __future__ import annotations

import io
import shutil
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import jobs as dl_jobs
from app.captions import api as capi
from app.captions import jobs as cjobs
from app.captions import llm, stt
from app.captions.transcript import Word
from app.clips import api as kapi
from app.clips import jobs as kjobs
from app.config import get_settings
from app.main import app
from app.reframe import jobs as rjobs
from app.reframe.media import ffmpeg_bin, probe
from tests.conftest import wait_for
from tests.test_api import upload
from tests.test_clips_unit import SENTENCES

OTHER = {"x-forwarded-for": "203.0.113.9"}


def speech_words(offset: float = 0.0, step: float = 0.33, pause: float = 0.55) -> list[Word]:
    out, t = [], 0.4
    for s in SENTENCES:
        for w in s.split():
            if t >= offset:
                out.append(Word(w, t - offset, t - offset + step - 0.03))
            t += step
        t += pause
    return out


@pytest.fixture(scope="module")
def talk(tmp_path_factory) -> Path:
    """A 50 s 'talking' video: a moving test pattern with sound (the words come from the fake speech-to-text)."""
    d = tmp_path_factory.mktemp("talk")
    out = d / "long talk.mp4"
    subprocess.run([ffmpeg_bin(), "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=960x540:r=25:d=50",
                    "-f", "lavfi", "-i", "sine=frequency=300:sample_rate=48000:d=50",
                    "-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(out)],
                   check=True)
    return out


@pytest.fixture
def calls():
    return []


@pytest.fixture
def client(isolated, monkeypatch, calls):
    monkeypatch.setattr(kjobs, "JOBS_DIR", isolated / "clips")
    monkeypatch.setattr(cjobs, "JOBS_DIR", isolated / "captions")
    kjobs._jobs.clear()
    cjobs._jobs.clear()
    for m in (kapi, capi):
        m._minute.clear()
        m._window.clear()

    def transcribe(audio, language, prompt=None, cancelled=lambda: False, progress=lambda p: None, stage=lambda s: None):
        calls.append(("stt", language, Path(audio).name))
        assert Path(audio).exists() and Path(audio).stat().st_size > 1000
        dur = probe(Path(audio)).duration if Path(audio).suffix == ".mp4" else None
        progress(0.5)
        offset = getattr(transcribe, "offset", 0.0)
        words = [w for w in speech_words(offset) if dur is None or w.end <= dur + 0.5]
        return stt.SttResult(language or "en", words, "fake", segments=[])

    monkeypatch.setattr(stt, "transcribe", transcribe)
    monkeypatch.setattr(llm, "available", lambda: False)
    with TestClient(app) as c:
        c.transcribe = transcribe
        yield c
    for j in list(kjobs._jobs.values()):
        j.cancel.set()


def settle(c: TestClient, jid: str, timeout: float = 400) -> dict:
    out: dict = {}

    def done() -> bool:
        nonlocal out
        out = c.get(f"/api/clips/jobs/{jid}").json()
        return out["state"] not in kjobs.ACTIVE
    wait_for(done, timeout, 0.4)
    return out


def create(c: TestClient, uid: str, **kw) -> dict:
    body = {"source": {"type": "upload", "id": uid}, "language": "en", "length": "short",
            "look": {"layout": "blur", "quality": "720p"}, **kw}
    r = c.post("/api/clips/jobs", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def check_video(c: TestClient, url: str, size: tuple[int, int], duration: float, tmp: Path) -> None:
    r = c.get(url)
    assert r.status_code == 200 and r.headers["content-type"] == "video/mp4"
    p = tmp / "check.mp4"
    p.write_bytes(r.content)
    info = probe(p)
    assert (info.width, info.height) == size
    assert abs(info.duration - duration) < 0.6, (info.duration, duration)
    assert info.has_audio


# ---------------------------------------------------------------- the main flow


def test_config(client):
    cfg = client.get("/api/clips/config").json()
    assert {"auto", "short", "medium", "long", "xl"} <= set(cfg["lengths"])
    assert cfg["features"]["ai"] is False and cfg["max_clips"] >= 10
    assert any(lang["code"] == "ur-Latn" for lang in cfg["languages"])
    assert any(p["id"] == "bold-pop" for p in cfg["presets"])


def test_upload_find_render_download(client, talk, calls, tmp_path):
    uid = upload(client, talk)
    job = create(client, uid, count=2)
    assert job["state"] in kjobs.ACTIVE and job["title"] == "long talk.mp4"
    job = settle(client, job["id"])
    assert job["state"] == "ready", job
    assert job["method"] == "auto" and job["detected_language"] == "en"
    assert [x[0] for x in calls] == ["stt"]
    clips = job["clips"]
    assert len(clips) == 2 and [c["rank"] for c in clips] == [1, 2]
    assert clips[0]["score"] >= clips[1]["score"]
    for c in clips:
        assert c["status"] == "done" and c["video"] and c["thumb"] and c["srt"]
        assert 11 <= c["end"] - c["start"] <= 31.5
        assert c["title"] and c["hook"] and c["hashtags"] and c["text"]
        assert set(c["scores"]) == {"hook", "flow", "value", "trend"}
        check_video(client, c["video"], (720, 1280), c["end"] - c["start"], tmp_path)
        assert client.get(c["thumb"]).headers["content-type"] == "image/jpeg"
        srt = client.get(c["srt"]).text
        assert "-->" in srt and srt.lstrip("﻿").startswith("1\n00:00:0")
    for a in clips:
        for b in clips:
            if a is not b:
                assert min(a["end"], b["end"]) - max(a["start"], b["start"]) <= 3.0
    # Range requests work (players seek, downloads resume).
    r = client.get(clips[0]["video"], headers={"Range": "bytes=0-99"})
    assert r.status_code == 206 and len(r.content) == 100
    # Transcript for the clip editor.
    tr = client.get(job["transcript"]).json()
    assert tr["lines"][0]["text"].startswith("Hello") and not tr["rtl"]
    # ZIP: every clip, its SRT and the post texts.
    z = zipfile.ZipFile(io.BytesIO(client.get(job["zip"]).content))
    names = z.namelist()
    assert sum(n.endswith(".mp4") for n in names) == 2 and sum(n.endswith(".srt") for n in names) == 2
    notes = z.read("clips.txt").decode()
    assert clips[0]["title"] in notes and "score" in notes
    # Health counts clip jobs.
    assert client.get("/api/health").json()["clips_jobs"] == 1


def test_smart_reframe_and_original_shape(client, talk, tmp_path):
    uid = upload(client, talk)
    job = settle(client, create(client, uid, count=1, look={"layout": "smart", "quality": "720p", "aspect": "9:16"})["id"])
    assert job["state"] == "ready", job
    c = job["clips"][0]
    check_video(client, c["video"], (720, 1280), c["end"] - c["start"], tmp_path)
    # Original shape: no reframe, the clip keeps 16:9.
    r = client.patch(f"/api/clips/jobs/{job['id']}/clips/{c['id']}", json={"look": {"aspect": "original"}})
    assert r.status_code == 200, r.text
    job = settle(client, job["id"])
    c = job["clips"][0]
    assert c["look"]["aspect"] == "original" and c["version"] == 2
    check_video(client, c["video"], (960, 540), c["end"] - c["start"], tmp_path)   # never upscaled


def test_edit_trim_hook_style_and_metadata(client, talk, tmp_path):
    uid = upload(client, talk)
    job = settle(client, create(client, uid, count=1)["id"])
    jid, c = job["id"], job["clips"][0]
    url = f"/api/clips/jobs/{jid}/clips/{c['id']}"
    kc = kjobs.clip(kjobs.get(jid), c["id"])
    base_before = kc.base

    # Metadata only: no new render.
    r = client.patch(url, json={"title": "My new title", "description": "Post this", "hashtags": ["#a", "b c"]})
    assert r.status_code == 200
    c2 = next(x for x in r.json()["clips"] if x["id"] == c["id"])
    assert c2["title"] == "My new title" and c2["hashtags"] == ["#a", "#bc"] and c2["version"] == 1
    assert r.json()["state"] == "ready"

    # New hook + caption style: re-render that reuses the framed clip (fast path).
    style = {**c["look"]["style"], "color": "#FFEE00", "animation": "karaoke"}
    r = client.patch(url, json={"hook": "Watch till the end", "look": {"style": style}})
    assert r.status_code == 200 and r.json()["state"] in kjobs.ACTIVE
    job = settle(client, jid)
    c3 = job["clips"][0]
    assert c3["version"] == 2 and c3["hook"] == "Watch till the end"
    assert c3["look"]["style"]["animation"] == "karaoke"
    assert kc.base == base_before and base_before.exists()

    # Trim: snapped to word edges, the frame is made again, the video has the new length.
    words = kjobs.get(jid).transcript.words()
    mid = next(w for w in words if w.start > c3["start"] + 2)
    r = client.patch(url, json={"start": (mid.start + mid.end) / 2, "end": c3["start"] + 14})
    assert r.status_code == 200
    job = settle(client, jid)
    c4 = job["clips"][0]
    assert c4["start"] <= mid.start and c4["version"] == 3
    assert kc.base != base_before and not base_before.exists()
    check_video(client, c4["video"], (720, 1280), c4["end"] - c4["start"], tmp_path)

    # Captions off and the hook off: the plain framed clip.
    r = client.patch(url, json={"look": {"captions": False, "hook": False}})
    job = settle(client, jid)
    assert job["clips"][0]["look"]["captions"] is False and job["clips"][0]["version"] == 4

    # Bad edits.
    assert client.patch(url, json={"start": 10, "end": 11}).status_code == 422          # too short
    assert client.patch(url, json={"look": {"aspect": "3:2"}}).status_code == 422
    assert client.patch(url, json={"look": {"style": {"color": "red"}}}).status_code == 422
    assert client.patch(f"/api/clips/jobs/{jid}/clips/nope", json={"title": "x"}).status_code == 404
    assert client.patch(url, json={"title": "x"}, headers=OTHER).status_code == 403


def test_find_again_reuses_the_transcript(client, talk, calls):
    uid = upload(client, talk)
    job = settle(client, create(client, uid, count=2)["id"])
    jid = job["id"]
    old_ids = {c["id"] for c in job["clips"]}
    old_dirs = [kjobs.get(jid).dir / f"clip-{i}" for i in old_ids]
    r = client.post(f"/api/clips/jobs/{jid}/find", json={"length": "medium", "count": 1, "topic": "business",
                                                         "look": {"layout": "fit", "quality": "720p"}})
    assert r.status_code == 200, r.text
    job = settle(client, jid)
    assert job["state"] == "ready" and len(job["clips"]) == 1
    assert not ({c["id"] for c in job["clips"]} & old_ids)
    assert not any(d.exists() for d in old_dirs)
    assert job["settings"]["length"] == "medium" and job["settings"]["topic"] == "business"
    assert "business" in job["clips"][0]["text"].lower()
    assert [x[0] for x in calls] == ["stt"]                      # no second speech-to-text
    assert client.post(f"/api/clips/jobs/{jid}/find", json={}, headers=OTHER).status_code == 403


def test_ai_finder_and_proofread_are_used(client, talk, monkeypatch):
    asked = []

    def ask(system, payload, schema):
        asked.append(system[:40])
        if "accuracy check" in system:
            return {"lines": [{"id": ln["id"], "text": ln["heard"].replace("rich", "wealthy"), "sure": True}
                              for ln in payload["lines"]]}
        return {"clips": [{"start_line": 2, "end_line": 6, "title": "Why you never save", "hook": "Nobody tells you this",
                           "description": "The one money rule.", "hashtags": ["money", "saving"], "hook_score": 91,
                           "flow_score": 85, "value_score": 80, "trend_score": 70, "reason": "Strong question hook."}]}

    monkeypatch.setattr(llm, "available", lambda: True)
    monkeypatch.setattr(llm, "provider", lambda: "claude")
    monkeypatch.setattr(llm, "_ask", ask)
    uid = upload(client, talk)
    job = settle(client, create(client, uid, count=1)["id"])
    assert job["state"] == "ready", job
    c = job["clips"][0]
    assert job["method"] == "ai" and c["method"] == "ai"
    assert c["title"] == "Why you never save" and c["hook"] == "Nobody tells you this"
    assert c["hashtags"] == ["#money", "#saving"] and c["score"] == 84     # 0.35*91 + 0.25*85 + 0.25*80 + 0.15*70
    assert "wealthy" in c["text"] and "rich" not in c["text"]
    assert any("accuracy check" in a for a in asked)


def test_range_language_and_roman_urdu(client, talk, calls):
    uid = upload(client, talk)
    client.transcribe.offset = 20.0
    try:
        job = settle(client, create(client, uid, count=1, range_start=20, range_end=48, language="ur-Latn")["id"])
    finally:
        client.transcribe.offset = 0.0
    assert job["state"] == "ready", job
    assert calls[-1][1] == "hi"                  # Roman Urdu listens as Hindi, then romanises
    c = job["clips"][0]
    assert c["start"] >= 19.5 and c["end"] <= 48.5
    assert job["detected_language"] == "ur-Latn"


def test_progressive_results_and_cancel(client, talk):
    uid = upload(client, talk)
    job = create(client, uid, count=2, look={"layout": "smart", "quality": "1080p"})
    jid = job["id"]
    wait_for(lambda: client.get(f"/api/clips/jobs/{jid}").json()["state"] == "rendering", 120, 0.2)
    j = client.get(f"/api/clips/jobs/{jid}").json()
    assert len(j["clips"]) == 2 and "clip" in j["stage"].lower()
    assert client.delete(f"/api/clips/jobs/{jid}", headers=OTHER).status_code == 403
    client.delete(f"/api/clips/jobs/{jid}")
    j = settle(client, jid)
    assert j["state"] == "ready"           # the transcript and found moments stay: render them later
    assert all(c["status"] in ("done", "pending") for c in j["clips"])
    assert not list(kjobs.get(jid).dir.rglob("*.part.mp4"))
    pending = next((c for c in j["clips"] if c["status"] == "pending"), None)
    if pending:
        r = client.patch(f"/api/clips/jobs/{jid}/clips/{pending['id']}", json={"render": True, "look": {"quality": "720p", "layout": "blur"}})
        assert r.status_code == 200
        j = settle(client, jid)
        assert next(c for c in j["clips"] if c["id"] == pending["id"])["status"] == "done"


# ---------------------------------------------------------------- sources, hand-offs


def test_link_source(client, talk, monkeypatch, tmp_path):
    copy = tmp_path / "fetched.mp4"
    shutil.copyfile(talk, copy)
    opt = SimpleNamespace(id="v720", kind="video", best=True, has_audio=True, ext="mp4")
    item = SimpleNamespace(index=0, title="Linked podcast", duration=50.0, error=None, options=[opt])
    resolved = SimpleNamespace(title="Post", item=lambda i: item)
    monkeypatch.setattr(rjobs, "link_lookup", lambda token: resolved if token == "tok1" else (_ for _ in ()).throw(KeyError()))
    monkeypatch.setattr(dl_jobs, "start", lambda r, it, o, s: SimpleNamespace(state="done", progress=1.0, path=copy, error=None))
    body = {"source": {"type": "link", "token": "zzz"}, "look": {"layout": "blur", "quality": "720p"}}
    assert client.post("/api/clips/jobs", json=body).status_code == 410
    body["source"]["token"] = "tok1"
    body["count"] = 1
    r = client.post("/api/clips/jobs", json=body)
    assert r.status_code == 200, r.text
    job = settle(client, r.json()["id"])
    assert job["state"] == "ready" and job["title"] == "Linked podcast"
    assert client.get(job["source"]["url"], headers={"Range": "bytes=0-9"}).status_code == 206
    monkeypatch.setattr(get_settings(), "clips_max_duration_sec", 30)
    r = client.post("/api/clips/jobs", json=body)
    assert r.status_code == 422 and "minutes" in r.json()["detail"]


def test_open_a_clip_in_the_caption_editor(client, talk, calls):
    uid = upload(client, talk)
    job = settle(client, create(client, uid, count=1)["id"])
    c = job["clips"][0]
    src = {"type": "clip", "id": job["id"], "clip": c["id"]}
    assert client.post("/api/captions/jobs", json={"source": src}, headers=OTHER).status_code == 403
    assert client.post("/api/captions/jobs", json={"source": {**src, "clip": "nope"}}).status_code == 404
    r = client.post("/api/captions/jobs", json={"source": src})
    assert r.status_code == 200, r.text
    cid = r.json()["id"]
    wait_for(lambda: client.get(f"/api/captions/jobs/{cid}").json()["state"] not in cjobs.ACTIVE, 60, 0.2)
    cj = client.get(f"/api/captions/jobs/{cid}").json()
    assert cj["state"] == "ready" and cj["title"] == c["title"]
    assert [x[0] for x in calls] == ["stt"]                        # words carried over, not transcribed again
    words = [w["text"] for ln in cj["transcript"]["lines"] for w in ln["words"]]
    assert " ".join(words).split()[:3] == c["text"].split()[:3]
    assert cj["info"]["width"] == 720 and cj["info"]["height"] == 1280   # the clean vertical clip, no burned captions


# ---------------------------------------------------------------- validation, limits, cleanup


def test_validation_limits_and_cleanup(client, talk, media, monkeypatch):
    uid = upload(client, talk)
    bad = [
        {"source": {"type": "upload", "id": uid}, "language": "xx"},
        {"source": {"type": "upload", "id": uid}, "length": "forever"},
        {"source": {"type": "upload", "id": uid}, "count": 0},
        {"source": {"type": "upload", "id": uid}, "count": 99},
        {"source": {"type": "upload", "id": uid}, "range_start": 10, "range_end": 12},
        {"source": {"type": "upload", "id": uid}, "range_start": 49.5},
        {"source": {"type": "upload", "id": uid}, "look": {"layout": "zoom"}},
        {"source": {"type": "file", "id": uid}},
    ]
    for b in bad:
        assert client.post("/api/clips/jobs", json=b).status_code == 422, b
    assert client.post("/api/clips/jobs", json={"source": {"type": "upload", "id": "nope0000000000000"}}).status_code == 404
    assert client.post("/api/clips/jobs", json={"source": {"type": "upload", "id": uid}}, headers=OTHER).status_code == 403
    silent = upload(client, media["portrait"])                          # no audio track
    r = client.post("/api/clips/jobs", json={"source": {"type": "upload", "id": silent}})
    assert r.status_code == 422 and "sound" in r.json()["detail"]
    monkeypatch.setattr(get_settings(), "clips_max_duration_sec", 20)
    r = client.post("/api/clips/jobs", json={"source": {"type": "upload", "id": uid}})
    assert r.status_code == 422 and "minutes" in r.json()["detail"]
    monkeypatch.setattr(get_settings(), "clips_max_duration_sec", 3600)

    # One video at a time per visitor, and a daily limit.
    kapi._minute.clear()
    first = create(client, uid, count=1)
    r = client.post("/api/clips/jobs", json={"source": {"type": "upload", "id": uid}})
    assert r.status_code == 429 and "already" in r.json()["detail"]
    job = settle(client, first["id"])
    monkeypatch.setattr(get_settings(), "clips_daily_per_ip", 0)
    r = client.post("/api/clips/jobs", json={"source": {"type": "upload", "id": uid}})
    assert r.status_code == 429 and "today" in r.json()["detail"]
    assert client.get("/api/clips/jobs/zzzzzzzzzzzzzzzz").status_code == 404
    assert client.get(f"/api/clips/jobs/{job['id']}/clips/nope/file").status_code == 404

    # Cleanup after the time limit frees the job and the upload.
    from app.reframe import uploads
    assert uploads.get(uid).used_by == 1
    j = kjobs.get(job["id"])
    d = j.dir
    j.created -= 10 * 86400
    kjobs.prune(3600)
    assert not d.exists() and client.get(f"/api/clips/jobs/{job['id']}").status_code == 404
    assert uploads.get(uid).used_by == 0


def test_remove_deletes_everything(client, talk):
    uid = upload(client, talk)
    job = settle(client, create(client, uid, count=1)["id"])
    d = kjobs.get(job["id"]).dir
    assert client.delete(f"/api/clips/jobs/{job['id']}?remove=true").json() == {"ok": True}
    assert not d.exists() and client.get(f"/api/clips/jobs/{job['id']}").status_code == 404
