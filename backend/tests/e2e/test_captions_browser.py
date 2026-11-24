"""Browser end-to-end test of the caption tool (real Next.js site + real API + real speech-to-text).

Not part of the normal run. Start both servers (backend with e.g. CF_LOCAL_WHISPER_MODEL=tiny), then:
    KLY_E2E_URL=http://localhost:3000 pytest tests/e2e/test_captions_browser.py -s
Screenshots are written to .tmp/e2e/.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from app.config import DATA_DIR
from app.reframe.media import ffmpeg_bin
from tests.test_captions_live import _speech

BASE = os.environ.get("KLY_E2E_URL")
pytestmark = pytest.mark.skipif(not BASE, reason="set KLY_E2E_URL to run browser tests")
SHOTS = DATA_DIR / "e2e"


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception:  # noqa: BLE001
            try:
                b = p.chromium.launch(channel="msedge")
            except Exception:  # noqa: BLE001
                b = p.chromium.launch(channel="chrome")
        yield b
        b.close()


@pytest.fixture(scope="module")
def talking_video(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("talk")
    speech = _speech(d)
    if speech is None:
        pytest.skip("no text-to-speech engine")
    out = d / "my talk.mp4"
    subprocess.run([ffmpeg_bin(), "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=25", "-i", str(speech),
                    "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)], check=True)
    return out


def _snap(page, name: str) -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f"captions-{name}.png"), full_page=False)


def test_caption_flow_edit_style_boost_export_and_vertical_round_trip(browser, talking_video):
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    try:
        _flow(page, talking_video, errors)
    except Exception:
        _snap(page, "failure")
        print("page errors:", errors)
        raise


def _flow(page, talking_video, errors):
    page.goto(f"{BASE}/auto-caption-generator")
    page.get_by_text("Drop your video here").wait_for()
    _snap(page, "1-empty")

    page.set_input_files("input[type=file]", str(talking_video))
    page.get_by_role("button", name="Detect automatically").wait_for()
    page.get_by_role("button", name=re.compile(r"^English")).click()
    page.wait_for_function("() => [...document.querySelectorAll('button[aria-pressed=true]')].some(b => b.textContent === 'English')")
    gen = page.get_by_role("button", name=re.compile("Generate captions"))
    gen.wait_for(timeout=60_000)
    page.wait_for_function("() => [...document.querySelectorAll('button')].some(b => b.textContent.includes('Generate captions') && !b.disabled)", timeout=60_000)
    _snap(page, "2-setup")
    gen.click()
    first = page.get_by_label("Caption line 1")
    first.wait_for(timeout=300_000)
    _snap(page, "3-editor")
    text = first.input_value().lower()
    assert "hello" in text or "welcome" in text, text

    # Edit the first line, then let autosave run.
    first.click()
    first.fill("Hello everybody and welcome back")
    page.get_by_role("tab", name="Style").click()
    page.get_by_text("Saved").wait_for(timeout=15_000)

    # Style: pick a preset and change the size.
    page.get_by_role("button", name=re.compile("Comic")).first.click()
    page.get_by_label("Size").fill("70")
    # Seek a bit so the live preview shows a caption.
    page.evaluate("() => { const v = document.querySelector('aside video'); v.currentTime = 1.2; }")
    page.wait_for_timeout(800)
    _snap(page, "4-style")

    # Boost: highlights + hook + progress bar.
    page.get_by_role("tab", name="Boost").click()
    page.get_by_role("button", name=re.compile("Auto-highlight")).click()
    page.wait_for_function("() => !document.body.innerText.includes('AI is picking highlights')", timeout=60_000)
    page.get_by_label("Hook title").fill("Save money the smart way")
    page.get_by_role("radio", name="Bottom").first.click()
    page.wait_for_timeout(500)
    _snap(page, "5-boost")

    # Export.
    page.get_by_role("button", name=re.compile("Export video")).click()
    page.get_by_text(re.compile("Your captioned video is ready")).wait_for(timeout=300_000)
    _snap(page, "6-exported")
    href = page.locator("a", has_text="Download MP4").get_attribute("href")
    resp = page.request.get(f"{BASE}{href}")
    assert resp.status == 200 and resp.headers["content-type"] == "video/mp4" and len(resp.body()) > 20_000
    srt = page.request.get(BASE + page.locator("a", has_text=re.compile("^srt$", re.I)).first.get_attribute("href"))
    assert srt.status == 200 and "Hello everybody and welcome back" in srt.text()

    # Preview vs export at the same moment (screenshots for a visual check).
    for mode in ("Live preview", "Exported video"):
        page.get_by_role("radio", name=mode).click()
        page.wait_for_timeout(700)
        page.evaluate("() => { const v = document.querySelector('aside video'); v.pause(); v.currentTime = 1.3; }")
        page.wait_for_timeout(1500)
        page.locator("aside video").first.locator("..").screenshot(path=str(SHOTS / f"captions-parity-{mode.split()[0].lower()}.png"))

    # Make it vertical -> Reframe -> bring the captions back.
    page.get_by_role("button", name=re.compile("Make it vertical")).click()
    page.wait_for_url(re.compile(r"landscape-to-portrait-video-converter\?from=captions"))
    page.get_by_role("button", name=re.compile(r"^Blur Fill")).click()
    page.get_by_role("button", name=re.compile(r"^Convert to 9:16")).click()
    page.get_by_text(re.compile("Your vertical video is ready")).wait_for(timeout=300_000)
    _snap(page, "7-reframed")
    page.get_by_role("button", name=re.compile("Bring your captions back")).click()
    page.wait_for_url(re.compile(r"auto-caption-generator\?from=reframe"))
    line = page.get_by_label("Caption line 1")
    line.wait_for(timeout=60_000)
    assert line.input_value() == "Hello everybody and welcome back"
    page.get_by_role("button", name=re.compile("Export video")).click()
    page.get_by_text(re.compile("Your captioned video is ready")).wait_for(timeout=300_000)
    _snap(page, "8-vertical-captions")
    assert not errors, errors


def test_caption_pages_mobile_and_seo(browser):
    page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    page.goto(f"{BASE}/roman-urdu-caption-generator")
    page.get_by_text("Drop your video here").wait_for()
    _snap(page, "9-mobile")
    assert page.evaluate("() => document.documentElement.scrollWidth") <= 390, "page scrolls sideways on phones"
    html = page.content()
    assert '"@type":"FAQPage"' in html.replace(" ", "") and "canonical" in html
    sitemap = page.request.get(f"{BASE}/sitemap.xml").text()
    for slug in ("auto-caption-generator", "add-urdu-subtitles-to-video", "roman-urdu-caption-generator", "srt-subtitle-generator"):
        assert slug in sitemap
    font = page.request.get(f"{BASE}/api/captions/fonts/nastaliq.ttf")
    assert font.status == 200 and len(font.body()) > 100_000
