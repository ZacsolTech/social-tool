"""The four detectors. All run on the CPU in a few milliseconds per frame.

    FaceDetector    YuNet (OpenCV)            face box + eyes, nose, mouth corners
    ObjectDetector  YOLOX-nano (onnxruntime)  people and 79 other everyday objects (COCO)
    TextDetector    PP-OCRv3 DB (OpenCV)      on-screen text, slides, lower-thirds
    SpeechDetector  Silero VAD (onnxruntime)  probability that someone is speaking, every 32 ms
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from functools import lru_cache

import cv2
import numpy as np
import onnxruntime as ort

from ..config import get_settings
from . import models

try:   # OpenCV 5 prints a harmless "Targets are not supported" warning for every model it loads
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)
except AttributeError:
    pass

COCO = [
    "person", "bicycle", "car", "motorcycle", "airplane", "bus", "train", "truck", "boat", "traffic light",
    "fire hydrant", "stop sign", "parking meter", "bench", "bird", "cat", "dog", "horse", "sheep", "cow",
    "elephant", "bear", "zebra", "giraffe", "backpack", "umbrella", "handbag", "tie", "suitcase", "frisbee",
    "skis", "snowboard", "sports ball", "kite", "baseball bat", "baseball glove", "skateboard", "surfboard",
    "tennis racket", "bottle", "wine glass", "cup", "fork", "knife", "spoon", "bowl", "banana", "apple",
    "sandwich", "orange", "broccoli", "carrot", "hot dog", "pizza", "donut", "cake", "chair", "couch",
    "potted plant", "bed", "dining table", "toilet", "tv", "laptop", "mouse", "remote", "keyboard", "cell phone",
    "microwave", "oven", "toaster", "sink", "refrigerator", "book", "clock", "vase", "scissors", "teddy bear",
    "hair drier", "toothbrush",
]
PERSON = 0

# Words people type in "Follow this…" mapped to the detector's object names.
SYNONYMS = {
    "ball": "sports ball", "football": "sports ball", "soccer": "sports ball", "basketball": "sports ball",
    "cricket ball": "sports ball", "tennis ball": "sports ball", "phone": "cell phone", "mobile": "cell phone",
    "smartphone": "cell phone", "iphone": "cell phone", "puppy": "dog", "kitten": "cat", "bike": "bicycle",
    "motorbike": "motorcycle", "plane": "airplane", "tv screen": "tv", "television": "tv", "monitor": "tv",
    "computer": "laptop", "mug": "cup", "glass": "wine glass", "sofa": "couch", "plant": "potted plant",
    "racket": "tennis racket", "bat": "baseball bat", "teddy": "teddy bear", "man": "person", "woman": "person",
    "people": "person", "player": "person", "speaker": "person", "kid": "person", "child": "person",
    "board": "skateboard", "skater": "person", "horse rider": "horse",
}


def class_id(label: str) -> int | None:
    label = label.strip().lower()
    label = SYNONYMS.get(label, label)
    return COCO.index(label) if label in COCO else None


def _session(key: str) -> ort.InferenceSession:
    so = ort.SessionOptions()
    so.intra_op_num_threads = max(1, get_settings().reframe_threads)
    so.inter_op_num_threads = 1
    so.log_severity_level = 3
    return ort.InferenceSession(str(models.path(key)), so, providers=["CPUExecutionProvider"])


@lru_cache
def _shared_session(key: str) -> ort.InferenceSession:   # sessions are thread-safe for run()
    return _session(key)


# ---------------------------------------------------------------- faces


@dataclass
class Face:
    x: float
    y: float
    w: float
    h: float
    score: float
    lm: np.ndarray   # 5x2: right eye, left eye, nose tip, right mouth corner, left mouth corner (pixels)


class FaceDetector:
    """One per analysis (OpenCV's detector object isn't thread-safe)."""

    def __init__(self, size: tuple[int, int], threshold: float = 0.62):
        self.det = cv2.FaceDetectorYN.create(str(models.path("face")), "", size, threshold, 0.3, 50)
        self.min_side = max(8.0, min(size) * 0.025)

    def __call__(self, frame: np.ndarray) -> list[Face]:
        _, rows = self.det.detect(frame)
        if rows is None:
            return []
        out = []
        for r in rows:
            if min(r[2], r[3]) < self.min_side:
                continue
            out.append(Face(float(r[0]), float(r[1]), float(r[2]), float(r[3]), float(r[14]), r[4:14].reshape(5, 2).copy()))
        return out


# ---------------------------------------------------------------- objects


@dataclass
class Obj:
    x: float
    y: float
    w: float
    h: float
    score: float
    cls: int


class ObjectDetector:
    SIZE = 416

    def __init__(self) -> None:
        self.sess = _shared_session("objects")
        grids, strides = [], []
        for s in (8, 16, 32):
            n = self.SIZE // s
            yv, xv = np.meshgrid(np.arange(n), np.arange(n), indexing="ij")
            grids.append(np.stack((xv, yv), 2).reshape(-1, 2))
            strides.append(np.full((n * n, 1), s))
        self.grids = np.concatenate(grids).astype(np.float32)
        self.strides = np.concatenate(strides).astype(np.float32)

    def __call__(self, frame: np.ndarray, classes: set[int] | None = None, conf: float = 0.35) -> list[Obj]:
        h, w = frame.shape[:2]
        r = min(self.SIZE / h, self.SIZE / w)
        rw, rh = int(w * r), int(h * r)
        canvas = np.full((self.SIZE, self.SIZE, 3), 114, np.uint8)
        canvas[:rh, :rw] = cv2.resize(frame, (rw, rh), interpolation=cv2.INTER_LINEAR)
        blob = canvas.transpose(2, 0, 1)[None].astype(np.float32)
        out = self.sess.run(None, {"images": blob})[0][0]
        xy = (out[:, :2] + self.grids) * self.strides
        wh = np.exp(np.clip(out[:, 2:4], -10, 10)) * self.strides
        cls_scores = out[:, 4:5] * out[:, 5:]
        cls = cls_scores.argmax(1)
        score = cls_scores[np.arange(len(cls)), cls]
        keep = score > conf
        if classes is not None:
            keep &= np.isin(cls, list(classes))
        if not keep.any():
            return []
        xy, wh, score, cls = xy[keep], wh[keep], score[keep], cls[keep]
        boxes = np.concatenate([xy - wh / 2, wh], 1) / r
        idx = cv2.dnn.NMSBoxesBatched(boxes.tolist(), score.tolist(), cls.tolist(), conf, 0.45)
        result = []
        for i in np.array(idx).reshape(-1):
            x, y, bw, bh = boxes[i]
            x0, y0 = max(0.0, x), max(0.0, y)
            x1, y1 = min(float(w), x + bw), min(float(h), y + bh)
            if x1 - x0 > 2 and y1 - y0 > 2:
                result.append(Obj(float(x0), float(y0), float(x1 - x0), float(y1 - y0), float(score[i]), int(cls[i])))
        return result


# ---------------------------------------------------------------- text


class TextDetector:
    def __init__(self, size: tuple[int, int]):
        w, h = size
        self.size = (max(32, w // 32 * 32), max(32, h // 32 * 32))
        m = cv2.dnn.TextDetectionModel_DB(str(models.path("text")))
        m.setBinaryThreshold(0.3).setPolygonThreshold(0.5).setMaxCandidates(200).setUnclipRatio(2.0)
        m.setInputParams(1.0 / 255.0, self.size, (122.67891434, 116.66876762, 104.00698793), False)
        self.m = m

    def __call__(self, frame: np.ndarray) -> list[tuple[float, float, float, float]]:
        polys, _ = self.m.detect(frame)
        out = []
        for p in polys:
            x, y, w, h = cv2.boundingRect(np.asarray(p, np.int32))
            if w >= 6 and h >= 4:
                out.append((float(x), float(y), float(w), float(h)))
        return out


# ---------------------------------------------------------------- speech


class SpeechDetector:
    SR = 16000
    CHUNK = 512        # 32 ms
    CONTEXT = 64

    _lock = threading.Lock()

    def __init__(self) -> None:
        self.sess = _shared_session("vad")

    def __call__(self, audio: np.ndarray) -> np.ndarray:
        """Speech probability (0..1) for every 32 ms of `audio` (16 kHz mono float32)."""
        n = len(audio) // self.CHUNK
        probs = np.zeros(n, np.float32)
        state = np.zeros((2, 1, 128), np.float32)
        context = np.zeros(self.CONTEXT, np.float32)
        sr = np.array(self.SR, dtype=np.int64)
        for i in range(n):
            chunk = audio[i * self.CHUNK:(i + 1) * self.CHUNK]
            x = np.concatenate([context, chunk])[None]
            out, state = self.sess.run(None, {"input": x, "state": state, "sr": sr})
            probs[i] = out[0, 0]
            context = chunk[-self.CONTEXT:]
        return probs
