"""The ONNX model files: verified by SHA-256 and re-downloaded if missing or damaged."""

from __future__ import annotations

import hashlib
import logging
import threading
from dataclasses import dataclass
from pathlib import Path

import httpx

from ..config import get_settings

log = logging.getLogger("uvicorn.error")


@dataclass(frozen=True)
class ModelFile:
    name: str
    sha256: str
    url: str


MODELS = {
    "face": ModelFile(
        "face_detection_yunet_2023mar.onnx",
        "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4",
        "https://huggingface.co/opencv/face_detection_yunet/resolve/main/face_detection_yunet_2023mar.onnx",
    ),
    "objects": ModelFile(
        "yolox_nano.onnx",
        "c789161ed43c8269fcd4e67c67eeeb4e80c622da2eb296a20bc6007bd18a0b7d",
        "https://github.com/Megvii-BaseDetection/YOLOX/releases/download/0.1.1rc0/yolox_nano.onnx",
    ),
    "text": ModelFile(
        "text_detection_en_ppocrv3_2023may.onnx",
        "03f550c6b406fda8bf54bd8327815f6c7e2edd98cea02348c93d879254366587",
        "https://huggingface.co/opencv/text_detection_ppocr/resolve/main/text_detection_en_ppocrv3_2023may.onnx",
    ),
    "vad": ModelFile(
        "silero_vad.onnx",
        "1a153a22f4509e292a94e67d6f9b85e8deb25b4988682b7e174c65279d8788e3",
        "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx",
    ),
}

_lock = threading.Lock()
_verified: set[str] = set()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def path(key: str, models_dir: Path | None = None) -> Path:
    """Local path of a verified model file (downloads it once if needed)."""
    m = MODELS[key]
    folder = models_dir or get_settings().models_dir
    p = folder / m.name
    with _lock:
        if str(p) in _verified:
            return p
        if p.exists() and _sha256(p) == m.sha256:
            _verified.add(str(p))
            return p
        log.warning("model %s missing or damaged, downloading from %s", m.name, m.url)
        folder.mkdir(parents=True, exist_ok=True)
        tmp = p.with_suffix(".part")
        with httpx.stream("GET", m.url, follow_redirects=True, timeout=60) as r:
            r.raise_for_status()
            with tmp.open("wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    f.write(chunk)
        if _sha256(tmp) != m.sha256:
            tmp.unlink(missing_ok=True)
            raise RuntimeError(f"Downloaded model {m.name} failed its checksum")
        tmp.replace(p)
        _verified.add(str(p))
        return p
