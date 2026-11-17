"""Unit tests for the Auto Director: camera moves, active speaker, layout choice, crop bounds."""

from __future__ import annotations

import numpy as np
import pytest

from app.reframe.analyze import Analysis, Det, Shot
from app.reframe.director import (
    ASPECTS, Options, Override, camera_path, crop_w, plan, plan_shot, speaker_timeline, main_faces, zoom_curve,
)

SF = 10.0


def make_analysis(n: int, faces_fn, speech: float | np.ndarray = 0.0, loud: np.ndarray | None = None,
                  shots: list[Shot] | None = None, objects_fn=None) -> Analysis:
    an = Analysis(duration=n / SF, width=1920, height=1080, an_size=(640, 360), sample_fps=SF)
    an.faces = [faces_fn(i) for i in range(n)]
    an.objects = [objects_fn(i) if objects_fn else [] for i in range(n)]
    an.speech = np.full(n, speech, np.float32) if np.isscalar(speech) else np.asarray(speech, np.float32)
    an.loud = loud if loud is not None else np.full(n, -30.0, np.float32)
    an.shots = shots or [Shot(0, 0.0, n / SF, 0, n)]
    return an


def face(track: int, cx: float, cy: float = 0.4, size: float = 0.12, mouth: float = 0.0, yaw: float = 0.0) -> Det:
    return Det(track, cx - size * 0.28, cy - size / 2, size * 0.56, size, 0.9, -1, mouth, yaw)


def check_bounds(an: Analysis, p) -> None:
    for sp in p.shots:
        for pane in sp.panes:
            cw = crop_w(an, pane.ch, pane.aspect)
            assert np.all(pane.cx - cw / 2 >= -1e-6) and np.all(pane.cx + cw / 2 <= 1 + 1e-6)
            assert np.all(pane.cy - pane.ch / 2 >= -1e-6) and np.all(pane.cy + pane.ch / 2 <= 1 + 1e-6)
            assert np.all(pane.ch > 0)


# ---------------------------------------------------------------- camera path


def test_camera_ignores_jitter_in_steady_mode():
    rng = np.random.default_rng(0)
    raw = 0.5 + rng.normal(0, 0.01, 100)
    out = camera_path(raw, SF, "steady", span=0.32)
    assert out is not None
    assert out.std() < 0.004


def test_camera_follows_a_real_move_with_speed_limit():
    raw = np.r_[np.full(30, 0.3), np.full(70, 0.7)]
    out = camera_path(raw, SF, "steady", span=0.32)
    assert abs(out[-1] - 0.7) < 0.03
    assert np.abs(np.diff(out)).max() <= 0.75 * 0.32 / SF + 1e-6   # never faster than the limit


def test_camera_fills_gaps_and_handles_all_unknown():
    raw = np.r_[np.full(10, np.nan), np.full(20, 0.6), np.full(10, np.nan)]
    out = camera_path(raw, SF, "follow", span=0.3)
    assert np.allclose(out, 0.6, atol=1e-3)
    assert camera_path(np.full(5, np.nan), SF, "steady", 0.3) is None


# ---------------------------------------------------------------- active speaker


def _two_speakers(n: int, talker) -> Analysis:
    def faces(i):
        a, b = talker(i)
        return [face(1, 0.2, mouth=0.6 if a else 0.02), face(2, 0.8, mouth=0.6 if b else 0.02)]
    return make_analysis(n, faces, speech=1.0)


def test_speaker_switches_when_the_other_person_talks():
    an = _two_speakers(120, lambda i: (i < 40 or i >= 80, 40 <= i < 80))
    shot = an.shots[0]
    sel, cuts, share = speaker_timeline(an, shot, main_faces(an, shot))
    assert sel[20] == 1 and sel[60] == 2 and sel[110] == 1
    switch_at = list(np.flatnonzero(cuts))
    assert len(switch_at) == 2
    assert abs(switch_at[0] - 40) <= 4 and abs(switch_at[1] - 80) <= 4   # cut placed where they started talking
    assert share[1] > 0.5 and share[2] > 0.25


def test_short_interjection_does_not_cause_a_cut():
    an = _two_speakers(100, lambda i: (not 50 <= i < 55, 50 <= i < 55))   # B says "yeah" for 0.5 s
    shot = an.shots[0]
    sel, cuts, _ = speaker_timeline(an, shot, main_faces(an, shot))
    assert not cuts.any()
    assert set(sel.tolist()) == {1}


def test_no_switch_during_silence():
    def talker(i):
        return (i < 30, 30 <= i)
    an = _two_speakers(100, talker)
    an.speech[:] = 0.0          # mouths move but nobody is speaking (chewing, smiling)
    shot = an.shots[0]
    _, cuts, _ = speaker_timeline(an, shot, main_faces(an, shot))
    assert not cuts.any()


# ---------------------------------------------------------------- layouts


def test_single_face_is_followed_and_framed_left_of_the_buttons():
    an = make_analysis(60, lambda i: [face(1, 0.3)])
    p = plan(an, Options())
    sp = p.shots[0]
    assert sp.layout == "follow"
    pane = sp.panes[0]
    cw = crop_w(an, pane.ch[30], pane.aspect)
    rel = (0.3 - (pane.cx[30] - cw / 2)) / cw
    assert 0.35 < rel < 0.5            # face slightly left of centre (TikTok buttons on the right)
    check_bounds(an, p)


def test_close_up_is_never_cropped_through_the_face():
    an = make_analysis(40, lambda i: [face(1, 0.5, size=0.5)])
    p = plan(an, Options(framing=1.6))
    assert p.shots[0].panes[0].ch.min() >= 0.5 * 2.0


def test_two_people_far_apart_switch_or_split():
    an = _two_speakers(120, lambda i: (i < 60, i >= 60))
    switch = plan(an, Options(two_person="switch")).shots[0]
    assert switch.layout == "follow" and switch.cuts is not None and switch.cuts.any()
    split = plan(an, Options(two_person="split")).shots[0]
    assert split.layout == "split" and len(split.panes) == 2
    top, bottom = split.panes
    assert top.cx.mean() < bottom.cx.mean()          # left person on top
    check_bounds(an, plan(an, Options(two_person="split")))


def test_two_people_close_together_stay_in_one_shot():
    an = make_analysis(60, lambda i: [face(1, 0.45, size=0.1), face(2, 0.55, size=0.1)], speech=1.0)
    sp = plan(an, Options()).shots[0]
    assert sp.layout == "follow" and "everyone" in sp.reason
    assert abs(sp.panes[0].cx.mean() - 0.5) < 0.05


def test_facecam_layout_uses_the_webcam_box():
    shot = Shot(0, 0.0, 6.0, 0, 60, facecam=(0.8, 0.65, 0.18, 0.3))
    an = make_analysis(60, lambda i: [face(1, 0.89, cy=0.78, size=0.12)], shots=[shot])
    sp = plan(an, Options()).shots[0]
    assert sp.layout == "facecam" and len(sp.panes) == 2
    cam = sp.panes[0]
    assert 0.8 <= cam.cx[0] <= 0.98 and cam.dst[1] == 0
    assert sp.panes[1].dst[1] == cam.dst[3]          # gameplay directly under the cam
    assert plan(an, Options(facecam=False)).shots[0].layout == "follow"


def test_text_heavy_shot_is_kept_whole():
    shot = Shot(0, 0.0, 6.0, 0, 60, text_cover=0.08, text_span=(0.05, 0.95))
    an = make_analysis(60, lambda i: [face(1, 0.1)], shots=[shot])
    assert plan(an, Options()).shots[0].layout == "fit"
    assert plan(an, Options(text_aware=False)).shots[0].layout == "follow"


def test_nobody_found_keeps_the_whole_frame_or_follows_a_person():
    an = make_analysis(40, lambda i: [])
    assert plan(an, Options()).shots[0].layout == "fit"
    person = Det(9, 0.6, 0.2, 0.1, 0.6, 0.8, 0)
    an2 = make_analysis(40, lambda i: [], objects_fn=lambda i: [person] if i % 5 == 0 else [])
    sp = plan(an2, Options()).shots[0]
    assert sp.layout == "follow" and abs(sp.panes[0].cx.mean() - 0.65) < 0.08


@pytest.mark.parametrize("aspect", list(ASPECTS))
def test_every_aspect_stays_inside_the_frame(aspect):
    rng = np.random.default_rng(3)
    an = make_analysis(80, lambda i: [face(1, float(np.clip(0.5 + 0.45 * np.sin(i / 7) + rng.normal(0, 0.02), 0.05, 0.95)))])
    p = plan(an, Options(aspect=aspect, framing=1.3, dynamic_zoom=True))
    check_bounds(an, p)


def test_editor_overrides():
    an = make_analysis(60, lambda i: [face(1, 0.3), face(2, 0.8)], speech=0.0)
    shot = an.shots[0]
    size = ASPECTS["9:16"]
    sp = plan_shot(an, Options(), shot, Override(layout="fit"), size, {})
    assert sp.layout == "fit"
    sp = plan_shot(an, Options(), shot, Override(center=0.9), size, {})
    assert sp.layout == "follow" and np.allclose(sp.panes[0].cx, sp.panes[0].cx[0])
    sp = plan_shot(an, Options(), shot, Override(track=2), size, {})
    assert sp.subjects == [2] and sp.panes[0].cx.mean() > 0.6
    boxes = [(0.1, 0.4, 0.05, 0.05)] * 60
    sp = plan_shot(an, Options(), shot, Override(point=(0.12, 0.42)), size, {}, boxes)
    assert "clicked" in sp.reason and sp.panes[0].cx.mean() < 0.35


def test_dynamic_zoom_punches_in_on_loud_moments():
    loud = np.full(200, -35.0, np.float32)
    loud[50] = loud[140] = -10.0
    an = make_analysis(200, lambda i: [face(1, 0.5)], speech=1.0, loud=loud)
    z = zoom_curve(an, Options(dynamic_zoom=True), 0, 200, np.zeros(200, bool), {})
    assert z.max() == pytest.approx(1.12)
    assert z[48] == 1.0 and z[55] > 1.1 and z[140 + 5] > 1.1
    assert np.all(zoom_curve(an, Options(dynamic_zoom=False), 0, 200, np.zeros(200, bool), {}) == 1.0)
