"""End-to-end API tests: chunked upload -> job -> progress -> download, the shot editor, links, limits."""

from __future__ import annotations

import shutil
import time
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import jobs as dl_jobs
from app.config import get_settings
from app.main import app
from app.reframe import api as rapi
from app.reframe import jobs as rjobs
from app.reframe.media import probe
from tests.conftest import wait_for


@pytest.fixture
def client(isolated):
    rapi._minute.clear()
    rapi._daily.clear()
    with TestClient(app) as c:
        yield c


def upload(c: TestClient, path: Path, chunk: int | None = None, headers: dict | None = None) -> str:
    data = path.read_bytes()
    r = c.post("/api/uploads", json={"filename": path.name, "size": len(data)}, headers=headers)
    assert r.status_code == 200, r.text
    up = r.json()
    size = chunk or up["chunk_size"]
    off = 0
    while off < len(data):
        r = c.put(f"/api/uploads/{up['id']}?offset={off}", content=data[off:off + size], headers=headers)
        assert r.status_code == 200, r.text
        off = r.json()["received"]
    r = c.post(f"/api/uploads/{up['id']}/complete", headers=headers)
    assert r.status_code == 200, r.text
    return up["id"]


def finished(c: TestClient, jid: str, timeout: float = 240) -> dict:
    out: dict = {}

    def done() -> bool:
        nonlocal out
        out = c.get(f"/api/reframe/jobs/{jid}").json()
        return out["state"] in ("done", "error", "cancelled")
    wait_for(done, timeout)
    return out


# ---------------------------------------------------------------- uploads


def test_chunked_upload_resumes_and_validates(client, media):
    data = media["plain"].read_bytes()
    up = client.post("/api/uploads", json={"filename": "../../evil name?.mp4", "size": len(data)}).json()
    assert up["filename"] == "evil name.mp4" and up["received"] == 0
    uid = up["id"]
    # A piece sent at the wrong offset is refused with the size we really have.
    r = client.put(f"/api/uploads/{uid}?offset=500", content=data[500:1000])
    assert r.status_code == 409 and r.json()["received"] == 0
    r = client.put(f"/api/uploads/{uid}?offset=0", content=data[:100_000])
    assert r.json()["received"] == 100_000
    # Resending the same piece (e.g. after a network blip) is also a 409 that tells the browser where to go on.
    r = client.put(f"/api/uploads/{uid}?offset=0", content=data[:100_000])
    assert r.status_code == 409 and r.json()["received"] == 100_000
    assert client.post(f"/api/uploads/{uid}/complete").status_code == 409     # not finished yet
    client.put(f"/api/uploads/{uid}?offset=100000", content=data[100_000:])
    r = client.post(f"/api/uploads/{uid}/complete")
    assert r.status_code == 200
    info = r.json()["info"]
    assert info["width"] == 1920 and info["height"] == 1080 and info["has_audio"]


def test_upload_limits(client, media, monkeypatch):
    big = get_settings().upload_max_mb * 1024 * 1024 + 1
    r = client.post("/api/uploads", json={"filename": "x.mp4", "size": big})
    assert r.status_code == 413
    data = media["not_video"].read_bytes()
    uid = client.post("/api/uploads", json={"filename": "x.mp4", "size": len(data)}).json()["id"]
    client.put(f"/api/uploads/{uid}?offset=0", content=data)
    r = client.post(f"/api/uploads/{uid}/complete")
    assert r.status_code == 422 and "isn't a video" in r.json()["detail"]
    r = client.put(f"/api/uploads/{uid}?offset=0", content=b"x" * 10, headers={"x-forwarded-for": "9.9.9.9"})
    assert r.status_code in (403, 409)
    assert client.get("/api/uploads/doesnotexist0000000").status_code == 404


# ---------------------------------------------------------------- jobs


def test_blur_fill_job_in_three_formats_and_download(client, media):
    uid = upload(client, media["plain"])
    r = client.post("/api/reframe/jobs", json={
        "source": {"type": "upload", "id": uid}, "mode": "blur", "aspects": ["9:16", "1:1", "4:5", "9:16"],
        "quality": "720p", "trim_start": 1.0, "trim_end": 3.5,
    })
    assert r.status_code == 200, r.text
    job = r.json()
    assert job["aspects"] == ["9:16", "1:1", "4:5"]
    job = finished(client, job["id"])
    assert job["state"] == "done", job["error"]
    assert job["progress"] == 1 and len(job["outputs"]) == 3
    sizes = {"9:16": (720, 1280), "1:1": (720, 720), "4:5": (720, 900)}
    for out in job["outputs"]:
        r = client.get(out["url"])
        assert r.status_code == 200 and r.headers["content-type"] == "video/mp4"
        assert "attachment" in r.headers["content-disposition"] and "klyprima" in r.headers["content-disposition"]
        assert int(r.headers["content-length"]) == len(r.content) == out["size"]
        p = Path(rjobs.get(job["id"]).outputs[out["aspect"]].path)
        info = probe(p)
        assert (info.width, info.height) == sizes[out["aspect"]] and abs(info.duration - 2.5) < 0.2
    url = job["outputs"][0]["url"]
    whole = client.get(url).content
    part = client.get(url, headers={"Range": "bytes=100-199"})
    assert part.status_code == 206 and part.content == whole[100:200]
    assert part.headers["content-range"] == f"bytes 100-199/{len(whole)}"
    assert "inline" in client.head(url + "&inline=1").headers["content-disposition"]
    assert client.get(url, headers={"Range": "bytes=999999999-"}).status_code == 416


def test_smart_job_then_shot_editor_rerenders(client, media):
    uid = upload(client, media["cuts"])
    job = client.post("/api/reframe/jobs", json={
        "source": {"type": "upload", "id": uid}, "mode": "smart", "aspects": ["9:16"],
        "smart": {"dynamic_zoom": True, "safe_zone": "reels"},
    }).json()
    job = finished(client, job["id"])
    assert job["state"] == "done", job["error"]
    assert job["editable"] is True
    shots = job["shots"]["9:16"]
    assert [s["layout"] for s in shots] == ["follow", "fit", "follow"]
    assert client.get(shots[0]["thumb"]).headers["content-type"] == "image/jpeg"
    assert shots[0]["faces"] and shots[0]["crops"]
    first_size = job["outputs"][0]["size"]

    # Editor: force shot 0 to Fit, pin shot 2's crop to the far right, and also add 1:1.
    r = client.post(f"/api/reframe/jobs/{job['id']}/render", json={
        "overrides": {"0": {"layout": "fit"}, "2": {"center": 0.95}}, "aspects": ["9:16", "1:1"],
    })
    assert r.status_code == 200, r.text
    assert client.post(f"/api/reframe/jobs/{job['id']}/render", json={}).status_code == 409   # busy
    job = finished(client, job["id"])
    assert job["state"] == "done" and job["version"] == 1
    assert [s["layout"] for s in job["shots"]["9:16"]] == ["fit", "fit", "follow"]
    assert job["shots"]["9:16"][2]["reason"] == "Position set in the editor"
    assert len(job["outputs"]) == 2 and job["outputs"][0]["url"].endswith("v=1")
    assert job["overrides"] == {"0": {"layout": "fit"}, "2": {"center": 0.95}}
    assert job["outputs"][0]["size"] != first_size

    # Click-to-follow on shot 0 and a mode switch to plain crop.
    r = client.post(f"/api/reframe/jobs/{job['id']}/render", json={"overrides": {"0": {"point": [0.2, 0.5]}}})
    job = finished(client, job["id"])
    assert job["shots"]["9:16"][0]["reason"] == "Following what you clicked"
    r = client.post(f"/api/reframe/jobs/{job['id']}/render", json={"mode": "crop", "position": 0.1, "aspects": ["4:5"]})
    job = finished(client, job["id"])
    assert job["state"] == "done" and [o["aspect"] for o in job["outputs"]] == ["4:5"]
    # Old files of earlier versions are removed.
    files = sorted(p.name for p in rjobs.get(job["id"]).dir.glob("*.mp4"))
    assert len(files) == 1


def test_follow_object_and_validation(client, media):
    uid = upload(client, media["face"])
    bad = client.post("/api/reframe/jobs", json={"source": {"type": "upload", "id": uid}, "smart": {"follow": "unicorn"}})
    assert bad.status_code == 422 and "unicorn" in bad.json()["detail"]
    too_late = client.post("/api/reframe/jobs", json={"source": {"type": "upload", "id": uid}, "trim_start": 60})
    assert too_late.status_code == 422
    wrong = client.post("/api/reframe/jobs", json={"source": {"type": "upload", "id": uid}, "aspects": ["16:9"]})
    assert wrong.status_code == 422
    job = client.post("/api/reframe/jobs", json={
        "source": {"type": "upload", "id": uid}, "smart": {"follow": "person", "style": "follow", "framing": 1.3},
    }).json()
    job = finished(client, job["id"])
    assert job["state"] == "done", job["error"]


def test_cancel_and_ownership(client, media):
    uid = upload(client, media["two"])
    job = client.post("/api/reframe/jobs", json={"source": {"type": "upload", "id": uid}, "aspects": ["9:16", "1:1", "4:5"]}).json()
    other = {"x-forwarded-for": "203.0.113.9"}
    assert client.delete(f"/api/reframe/jobs/{job['id']}", headers=other).status_code == 403
    assert client.post(f"/api/reframe/jobs/{job['id']}/render", json={}, headers=other).status_code == 403
    client.delete(f"/api/reframe/jobs/{job['id']}")
    job = finished(client, job["id"])
    assert job["state"] == "cancelled"
    assert not list(rjobs.get(job["id"]).dir.glob("*.part.mp4"))
    assert client.delete(f"/api/reframe/jobs/{job['id']}?remove=true").status_code == 200
    assert client.get(f"/api/reframe/jobs/{job['id']}").status_code == 404


def test_daily_limit(client, media, monkeypatch):
    monkeypatch.setattr(get_settings(), "reframe_daily_per_ip", 1)
    uid = upload(client, media["plain"])
    ok = client.post("/api/reframe/jobs", json={"source": {"type": "upload", "id": uid}, "mode": "fit"})
    assert ok.status_code == 200
    again = client.post("/api/reframe/jobs", json={"source": {"type": "upload", "id": uid}, "mode": "fit"})
    assert again.status_code == 429 and "limit" in again.json()["detail"]
    finished(client, ok.json()["id"])


def test_make_it_vertical_from_a_downloader_link(client, media, monkeypatch, tmp_path):
    """The downloader's result card hands its link token to the Reframe tool."""
    copy = tmp_path / "fetched.mp4"
    shutil.copyfile(media["face"], copy)
    opt = SimpleNamespace(id="v1080", kind="video", best=True, has_audio=True, ext="mp4")
    item = SimpleNamespace(index=0, title="My clip", duration=6.0, error=None, options=[opt])
    resolved = SimpleNamespace(title="Post", item=lambda i: item)
    monkeypatch.setattr(rjobs, "link_lookup", lambda token: resolved if token == "tok123" else (_ for _ in ()).throw(KeyError()))
    calls = []

    def fake_start(r, it, o, settings):
        calls.append(o.id)
        return SimpleNamespace(state="done", progress=1.0, path=copy, error=None)
    monkeypatch.setattr(dl_jobs, "start", fake_start)

    expired = client.post("/api/reframe/jobs", json={"source": {"type": "link", "token": "nope"}})
    assert expired.status_code == 410
    job = client.post("/api/reframe/jobs", json={"source": {"type": "link", "token": "tok123"}, "mode": "blur"}).json()
    assert job["title"] == "My clip"
    job = finished(client, job["id"])
    assert job["state"] == "done", job["error"]
    assert calls == ["v1080"]
    assert job["outputs"][0]["name"] == "My-clip-klyprima-9x16.mp4"
    src = client.get(job["source"]["url"], headers={"Range": "bytes=0-99"})
    assert src.status_code == 206 and len(src.content) == 100


def test_config_and_health(client):
    cfg = client.get("/api/reframe/config").json()
    assert cfg["aspects"]["9:16"] == [1080, 1920] and "sports ball" in cfg["objects"]
    assert client.get("/api/health").json()["ok"] is True


def test_old_jobs_and_uploads_are_cleaned_up(client, media):
    uid = upload(client, media["plain"])
    job = client.post("/api/reframe/jobs", json={"source": {"type": "upload", "id": uid}, "mode": "fit"}).json()
    finished(client, job["id"])
    j = rjobs.get(job["id"])
    d = j.dir
    j.created -= 10 * 86400
    rjobs.prune(3600)
    assert not d.exists()
    from app.reframe import uploads
    up = uploads.get(uid)
    assert up.used_by == 0
    up.created -= 10 * 86400
    uploads.prune(3600)
    assert not up.path.exists()
    time.sleep(0.1)


def test_editor_memory_is_freed_after_the_edit_window(client, media):
    uid = upload(client, media["face"])
    job = finished(client, client.post("/api/reframe/jobs", json={"source": {"type": "upload", "id": uid}}).json()["id"])
    assert job["editable"]
    j = rjobs.get(job["id"])
    j.finished -= rjobs.EDIT_WINDOW_SEC + 1
    rjobs.prune(10 * 86400)
    after = client.get(f"/api/reframe/jobs/{job['id']}").json()
    assert after["editable"] is False and after["outputs"]          # still downloadable
    assert client.get(after["outputs"][0]["url"]).status_code == 200


def test_daily_limit_does_not_pin_the_upload(client, media, monkeypatch):
    monkeypatch.setattr(get_settings(), "reframe_daily_per_ip", 0)
    uid = upload(client, media["plain"])
    r = client.post("/api/reframe/jobs", json={"source": {"type": "upload", "id": uid}, "mode": "fit"})
    assert r.status_code == 429
    from app.reframe import uploads
    assert uploads.get(uid).used_by == 0


@pytest.mark.parametrize("url", [
    "https://www.youtube.com/playlist?list=PLBCF2DAC6FFB574DE",
    "https://www.youtube.com/@SomeChannel",
    "https://youtube.com/channel/UC123456",
])
def test_youtube_playlists_get_a_clear_message(client, url):
    r = client.post("/api/resolve", json={"url": url})
    assert r.status_code == 422 and "playlists" in r.json()["detail"]
