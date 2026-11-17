"""Reframe: landscape -> portrait (9:16, 4:5, 1:1) with an AI "Auto Director".

Pipeline (see landscape-to-portrait-proposal.md):
    media.py     probe files, decode frames / audio with ffmpeg
    models.py    the four small ONNX models (verified, auto-restored)
    detect.py    faces, people/objects, text, speech
    analyze.py   Stage A: shots, detections, tracks, mouth movement, facecam boxes
    director.py  Stage B+C: layout per shot, active speaker, framing, smoothing, zoom
    render.py    Stage D: compose frames and encode the MP4
    uploads.py   chunked, resumable uploads
    jobs.py      queue, workers, progress, cleanup
    api.py       HTTP routes (/api/uploads, /api/reframe/...)
"""
