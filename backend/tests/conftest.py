"""Shared fixtures: synthetic test videos made with OpenCV + ffmpeg (no network needed except one
public sample photo from the OpenCV repository, cached under .tmp/test-assets)."""

from __future__ import annotations

import os

os.environ.setdefault("CF_CAPTIONS_WARM_MODEL", "false")   # tests don't download the 480 MB speech model

import math  # noqa: E402
import subprocess
import sys
from collections.abc import Callable, Iterator
from pathlib import Path

import cv2
import httpx
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import DATA_DIR  # noqa: E402
from app.reframe import jobs as rjobs  # noqa: E402
from app.reframe import uploads  # noqa: E402
from app.reframe.media import ffmpeg_bin  # noqa: E402

ASSETS = DATA_DIR / "test-assets"
PHOTO_URL = "https://raw.githubusercontent.com/opencv/opencv/4.x/samples/data/messi5.jpg"


def _photo() -> np.ndarray:
    p = ASSETS / "messi5.jpg"
    if not p.exists():
        ASSETS.mkdir(parents=True, exist_ok=True)
        try:
            r = httpx.get(PHOTO_URL, timeout=30, follow_redirects=True)
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            pytest.skip(f"sample photo unavailable (offline?): {e}")
        p.write_bytes(r.content)
    img = cv2.imread(str(p))
    assert img is not None
    return img


@pytest.fixture(scope="session")
def face_crop() -> np.ndarray:
    """A head-and-shoulders crop around the face in the sample photo (face at ~226,93 31x40)."""
    img = _photo()
    return img[40:230, 150:330].copy()


def write_video(path: Path, frames: Iterator[np.ndarray], size: tuple[int, int], fps: int = 30,
                audio: str | None = "sine", extra: list[str] | None = None) -> Path:
    w, h = size
    cmd = [ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y",
           "-f", "rawvideo", "-pix_fmt", "bgr24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "pipe:0"]
    if audio == "sine":
        cmd += ["-f", "lavfi", "-i", "sine=frequency=220:sample_rate=48000"]
    cmd += ["-map", "0:v"] + (["-map", "1:a", "-c:a", "aac", "-shortest"] if audio else [])
    cmd += ["-c:v", "libx264", "-preset", "ultrafast", "-pix_fmt", "yuv420p", *(extra or []), str(path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in frames:
        proc.stdin.write(np.ascontiguousarray(f).tobytes())
    proc.stdin.close()
    assert proc.wait() == 0
    return path


def _place(canvas: np.ndarray, img: np.ndarray, x: int, y: int) -> None:
    h, w = img.shape[:2]
    H, W = canvas.shape[:2]
    x0, y0, x1, y1 = max(0, x), max(0, y), min(W, x + w), min(H, y + h)
    if x1 > x0 and y1 > y0:
        canvas[y0:y1, x0:x1] = img[y0 - y:y1 - y, x0 - x:x1 - x]


@pytest.fixture(scope="session")
def media(tmp_path_factory, face_crop) -> dict[str, Path]:
    d = tmp_path_factory.mktemp("media")
    W, H, fps = 1920, 1080, 30
    head = cv2.resize(face_crop, (450, 475))
    small_head = cv2.resize(face_crop, (260, 275))
    out: dict[str, Path] = {}

    def plain(n: int = 150) -> Iterator[np.ndarray]:
        for i in range(n):
            f = np.zeros((H, W, 3), np.uint8)
            f[:] = (40 + i % 60, 80, 120)
            cv2.circle(f, (200 + 10 * i, 540), 120, (0, 200, 255), -1)
            yield f
    out["plain"] = write_video(d / "plain.mp4", plain(), (W, H), fps)

    def moving_face(n: int = 180) -> Iterator[np.ndarray]:
        for i in range(n):
            f = np.full((H, W, 3), 60, np.uint8)
            x = int(735 + 520 * math.sin(i / n * 2 * math.pi))
            _place(f, head, x, 300)
            yield f
    out["face"] = write_video(d / "face.mp4", moving_face(), (W, H), fps)

    def two_faces(n: int = 150) -> Iterator[np.ndarray]:
        for _ in range(n):
            f = np.full((H, W, 3), 70, np.uint8)
            _place(f, head, 120, 300)
            _place(f, cv2.flip(head, 1), 1350, 300)
            yield f
    out["two"] = write_video(d / "two.mp4", two_faces(), (W, H), fps)

    def facecam(n: int = 150) -> Iterator[np.ndarray]:
        rng = np.random.default_rng(1)
        for i in range(n):
            f = np.zeros((H, W, 3), np.uint8)
            f[:] = (20, int(120 + 40 * math.sin(i / 20)), 40)
            for k in range(25):     # "gameplay": lots of movement everywhere
                cx = int((k * 211 + i * (7 + k)) % W)
                cy = int((k * 97 + i * (5 + k % 4)) % H)
                cv2.rectangle(f, (cx, cy), (cx + 60, cy + 40), tuple(int(v) for v in rng.integers(0, 255, 3)), -1)
            cam = small_head.copy()
            x, y = W - 300, H - 330
            cv2.rectangle(f, (x - 10, y - 10), (x + cam.shape[1] + 10, y + cam.shape[0] + 10), (255, 255, 255), -1)
            _place(f, cam, x, y)
            yield f
    out["facecam"] = write_video(d / "facecam.mp4", facecam(), (W, H), fps)

    def slides(n: int = 120) -> Iterator[np.ndarray]:
        for _ in range(n):
            f = np.full((H, W, 3), 30, np.uint8)
            _place(f, small_head, 60, 60)
            cv2.putText(f, "QUARTERLY RESULTS 2026", (120, 560), cv2.FONT_HERSHEY_SIMPLEX, 3.2, (255, 255, 255), 8)
            cv2.putText(f, "Revenue grew 48 percent year on year", (120, 720), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (230, 230, 230), 5)
            cv2.putText(f, "Three new markets opened this quarter", (120, 860), cv2.FONT_HERSHEY_SIMPLEX, 2.0, (230, 230, 230), 5)
            yield f
    out["slides"] = write_video(d / "slides.mp4", slides(), (W, H), fps)

    photo = cv2.resize(_photo(), None, fx=5, fy=5, interpolation=cv2.INTER_CUBIC)   # face centre ~ (1206, 565)

    def cuts(n: int = 180) -> Iterator[np.ndarray]:   # three full-frame shots: face left, empty, face right
        for i in range(n):
            if i < 60:
                f = photo[0:H, 820:820 + W].copy()       # face at x ~ 386 (left)
            elif i < 120:
                f = np.full((H, W, 3), (180, 60, 20), np.uint8)
            else:
                f = photo[0:H, 0:W].copy()               # face at x ~ 1206 (right of centre)
            yield f
    out["cuts"] = write_video(d / "cuts.mp4", cuts(), (W, H), fps)

    def portrait(n: int = 60) -> Iterator[np.ndarray]:
        for i in range(n):
            f = np.full((1280, 720, 3), (i * 4) % 255, np.uint8)
            yield f
    out["portrait"] = write_video(d / "portrait.mp4", portrait(), (720, 1280), fps, audio=None)

    rotated = d / "rotated.mp4"
    subprocess.run([ffmpeg_bin(), "-hide_banner", "-loglevel", "error", "-y", "-display_rotation:v:0", "90",
                    "-i", str(out["plain"]), "-c", "copy", str(rotated)], check=True)
    out["rotated"] = rotated
    out["not_video"] = d / "notes.mp4"
    out["not_video"].write_bytes(b"this is not a video file at all" * 100)
    return out


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    """Uploads and jobs go to a temp folder for the test."""
    monkeypatch.setattr(uploads, "UPLOADS_DIR", tmp_path / "uploads")
    monkeypatch.setattr(rjobs, "JOBS_DIR", tmp_path / "reframe")
    uploads._uploads.clear()
    rjobs._jobs.clear()
    yield tmp_path
    for j in list(rjobs._jobs.values()):
        j.cancel.set()


def wait_for(fn: Callable[[], bool], timeout: float = 180, step: float = 0.25) -> None:
    import time
    end = time.time() + timeout
    while time.time() < end:
        if fn():
            return
        time.sleep(step)
    raise AssertionError("timed out")
