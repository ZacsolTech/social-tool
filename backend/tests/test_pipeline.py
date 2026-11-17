"""Integration tests for the media -> analysis -> plan -> render pipeline on real encoded videos."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from app.reframe import models
from app.reframe.analyze import analyze, track_point
from app.reframe.director import Options, crop_w, describe, plan
from app.reframe.media import MediaError, probe
from app.reframe.render import Look, render_smart, render_static


def test_models_are_present_and_verified():
    for key in models.MODELS:
        p = models.path(key)
        assert p.exists() and p.stat().st_size > 100_000


def test_probe(media):
    info = probe(media["plain"])
    assert (info.width, info.height) == (1920, 1080) and info.has_audio and info.fps == 30
    assert 4.9 < info.duration < 5.2
    rot = probe(media["rotated"])
    assert (rot.width, rot.height) == (1080, 1920) and abs(rot.rotation) == 90
    assert probe(media["portrait"]).has_audio is False
    with pytest.raises(MediaError):
        probe(media["not_video"])


def _analyse(path: Path, tmp_path: Path):
    info = probe(path)
    return info, analyze(path, info, 0.0, info.duration, tmp_path / "thumbs")


def test_shot_cuts_are_found_on_the_right_frame(media, tmp_path):
    _, an = _analyse(media["cuts"], tmp_path)
    assert len(an.shots) == 3
    assert abs(an.shots[1].start - 2.0) < 0.05 and abs(an.shots[2].start - 4.0) < 0.05
    assert all(s.thumb and (tmp_path / "thumbs" / s.thumb).exists() for s in an.shots)
    p = plan(an, Options())
    assert [s.layout for s in p.shots] == ["follow", "fit", "follow"]
    left, right = p.shots[0].panes[0].cx.mean(), p.shots[2].panes[0].cx.mean()
    assert left < 0.3 and right > 0.55


def test_moving_face_is_tracked(media, tmp_path):
    info, an = _analyse(media["face"], tmp_path)
    found = sum(1 for f in an.faces if f) / an.n
    assert found > 0.9
    tracks = {d.track for f in an.faces for d in f}
    assert len(tracks) <= 3            # one person, not a new id every frame
    p = plan(an, Options(style="follow"))
    pane = p.shots[0].panes[0]
    # The crop must contain the face in (almost) every sample.
    inside = 0
    for j, dets in enumerate(an.faces):
        if not dets:
            continue
        d = dets[0]
        cw = crop_w(an, pane.ch[j], pane.aspect)
        inside += pane.cx[j] - cw / 2 <= d.cx <= pane.cx[j] + cw / 2
    assert inside / sum(1 for f in an.faces if f) > 0.95


def test_facecam_is_detected(media, tmp_path):
    _, an = _analyse(media["facecam"], tmp_path)
    assert len(an.shots) == 1
    cam = an.shots[0].facecam
    assert cam is not None
    x, y, w, h = cam
    assert x > 0.75 and y > 0.6 and w < 0.25 and h < 0.4
    assert plan(an, Options()).shots[0].layout == "facecam"


def test_slides_keep_the_whole_frame(media, tmp_path):
    _, an = _analyse(media["slides"], tmp_path)
    assert an.shots[0].text_cover > 0.03
    sp = plan(an, Options()).shots[0]
    assert sp.layout == "fit" and "text" in sp.reason
    assert plan(an, Options(text_aware=False)).shots[0].layout == "follow"


def test_two_people_split_and_editor_description(media, tmp_path):
    _, an = _analyse(media["two"], tmp_path)
    p = plan(an, Options(two_person="split"))
    assert p.shots[0].layout == "split"
    desc = describe(an, p)
    assert len(desc) == 1 and len(desc[0]["crops"]) == 2 and len(desc[0]["faces"]) == 2
    assert [f["label"] for f in desc[0]["faces"]] == ["A", "B"]


def test_click_to_follow_tracks_what_was_clicked(media, tmp_path):
    info, an = _analyse(media["face"], tmp_path)
    shot = an.shots[0]
    i0 = an.sample_at(shot.thumb_t)
    d = an.faces[i0][0]
    boxes = track_point(media["face"], info, an, 0.0, shot, d.cx, d.cy)
    assert all(b is not None for b in boxes)
    errs = [abs((b[0] + b[2] / 2) - f[0].cx) for b, f in zip(boxes[i0:], an.faces[i0:]) if f]
    assert np.mean(errs) < 0.03          # the box stays on the moving face


def test_click_on_empty_background_still_works(media, tmp_path):
    info, an = _analyse(media["plain"], tmp_path)
    boxes = track_point(media["plain"], info, an, 0.0, an.shots[0], 0.9, 0.1)
    assert len(boxes) == an.shots[0].s1 - an.shots[0].s0
    assert boxes[0] is not None


@pytest.mark.parametrize("mode", ["blur", "crop", "fit"])
@pytest.mark.parametrize("aspect,size", [("9:16", (1080, 1920)), ("1:1", (1080, 1080)), ("4:5", (1080, 1350))])
def test_static_modes(media, tmp_path, mode, aspect, size):
    info = probe(media["plain"])
    out = tmp_path / f"{mode}.mp4"
    render_static(media["plain"], info, mode, aspect, "1080p", Look(background="color" if mode == "fit" else "blur", color="#ff0000"),
                  out, 1.0, 3.0, 0.3, 1.0, lambda p: None, lambda: False)
    got = probe(out)
    assert (got.width, got.height) == size and got.has_audio
    assert abs(got.duration - 3.0) < 0.2


def test_smart_render_720p_and_rotated_source(media, tmp_path):
    info, an = _analyse(media["rotated"], tmp_path)
    assert an.width == 1080 and an.height == 1920
    p = plan(an, Options(aspect="1:1"))
    out = tmp_path / "smart.mp4"
    render_smart(media["rotated"], info, an, p, out, 0.0, "720p", Look(), lambda x: None, lambda: False)
    got = probe(out)
    assert (got.width, got.height) == (720, 720) and got.has_audio
    assert abs(got.duration - info.duration) < 0.2


def test_fit_frame_and_compose_shapes(media, tmp_path):
    from app.reframe.render import fit_frame
    frame = np.zeros((1080, 1920, 3), np.uint8)
    frame[:, :960] = 255
    out = fit_frame(frame, 1080, 1920, Look())
    assert out.shape == (1920, 1080, 3)
    mid = out[960, :, 0]
    assert mid[10] == 255 and mid[-10] == 0       # left half white, right half black: not mirrored or squashed
    col = fit_frame(frame, 1080, 1920, Look(background="color", color="#00ff00"))
    assert tuple(col[20, 540]) == (0, 255, 0)


def test_smart_render_keeps_colours_exact(media, tmp_path, face_crop):
    """Frames go YUV -> BGR -> YUV through OpenCV and are tagged with the source's colour standard,
    so a cropped region must look the same as in the source (no green/red shift)."""
    import cv2
    from tests.conftest import write_video
    W, H = 1920, 1080
    head = cv2.resize(face_crop, (450, 475))

    def frames():
        for _ in range(45):
            f = np.zeros((H, W, 3), np.uint8)
            f[:, :] = (40, 160, 230)          # warm orange (BGR)
            f[:300, :] = (200, 60, 30)        # strong blue band at the top
            f[300:475, 735:1185] = head[:175]
            f[475:775, 735:1185] = head[175:]
            yield f
    src = write_video(tmp_path / "colours.mp4", frames(), (W, H), extra=["-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709"])
    info, an = _analyse(src, tmp_path)
    p = plan(an, Options())
    assert p.shots[0].layout == "follow"
    out = tmp_path / "out.mp4"
    render_smart(src, info, an, p, out, 0.0, "1080p", Look(), lambda x: None, lambda: False)

    def rgb_at(path, x, y, w, h):
        import subprocess
        from app.reframe.media import ffmpeg_bin
        raw = subprocess.run([ffmpeg_bin(), "-v", "error", "-i", str(path), "-vf", f"select=eq(n\,20),crop={w}:{h}:{x}:{y}",
                              "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True).stdout
        return np.frombuffer(raw, np.uint8).reshape(-1, 3).mean(0)
    src_top = rgb_at(src, 900, 100, 40, 40)
    out_top = rgb_at(out, 520, 60, 40, 40)       # same blue band, top of the vertical frame
    src_mid = rgb_at(src, 900, 950, 40, 40)
    out_mid = rgb_at(out, 520, 1800, 40, 40)     # orange area near the bottom
    assert np.abs(src_top - out_top).max() < 8, (src_top, out_top)
    assert np.abs(src_mid - out_mid).max() < 8, (src_mid, out_mid)


def test_blur_fill_ignores_a_leftover_colour_choice(media):
    """Bug report: picking Fit + Colour, then going back to Blur Fill, still gave colour bars."""
    from app.reframe.render import static_filter
    info = probe(media["plain"])
    leftover = Look(background="color", color="#ffcc00")
    assert "gblur" in static_filter(info, "blur", "9:16", "1080p", leftover)
    assert "pad=" in static_filter(info, "fit", "9:16", "1080p", leftover)
