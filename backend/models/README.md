# AI models used by the Reframe tool

All models are small, run on the CPU and are licensed for commercial use. They are committed here so
builds and servers never need to download anything. `app/reframe/models.py` checks each file's SHA-256
and re-downloads it from the source below if it is missing or damaged.

| File | What it does | Source | Licence |
|---|---|---|---|
| `face_detection_yunet_2023mar.onnx` | Face boxes + 5 landmarks (eyes, nose, mouth corners) | [OpenCV Zoo: YuNet](https://huggingface.co/opencv/face_detection_yunet) | MIT |
| `yolox_nano.onnx` | People and 80 everyday objects (COCO) | [Megvii YOLOX](https://github.com/Megvii-BaseDetection/YOLOX) | Apache-2.0 |
| `text_detection_en_ppocrv3_2023may.onnx` | On-screen text and slides (DB text detector) | [OpenCV Zoo: PP-OCRv3](https://huggingface.co/opencv/text_detection_ppocr) | Apache-2.0 |
| `silero_vad.onnx` | Speech detection (who is talking, when) | [Silero VAD](https://github.com/snakers4/silero-vad) | MIT |

None of these is an LLM. Ultralytics YOLOv8/YOLO11 are deliberately **not** used: they are AGPL.
