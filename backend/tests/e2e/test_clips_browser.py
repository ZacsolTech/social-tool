"""Browser end-to-end test of AI Clips (real Next.js site + real API + real speech-to-text and AI when keys are set).

Not part of the normal run. Start both servers (see backend README / dev.ps1), then:
    KLY_E2E_URL=http://localhost:3000 pytest tests/e2e/test_clips_browser.py -s
Screenshots are written to .tmp/e2e/.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from app.config import DATA_DIR
from app.reframe.media import ffmpeg_bin

BASE = os.environ.get("KLY_E2E_URL")
pytestmark = pytest.mark.skipif(not BASE, reason="set KLY_E2E_URL to run browser tests")
SHOTS = DATA_DIR / "e2e"

SCRIPT = (
    "Welcome back to the show. Today we talk about money and the habits that change everything. "
    "Why do most people never manage to save any money? The answer surprised me. "
    "Most of us spend first and save whatever is left at the end of the month, and usually nothing is left. "
    "Flip it. Save twenty percent the day you get paid, and live on the rest. "
    "That one change made me debt free in three years. "
    "Here is the biggest mistake I made with my first business. I hired my friends instead of experts. "
    "It cost me ten thousand dollars and two years of my life. "
    "So my advice is simple. Never hire someone you cannot fire. Thanks for watching, see you next week."
)


def _speech(tmp: Path) -> Path | None:
    wav = tmp / "speech.wav"
    if sys.platform == "win32":
        ps = (f"Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
              f"$s.Rate = 0; $s.SetOutputToWaveFile('{wav}'); $s.Speak('{SCRIPT}'); $s.Dispose()")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, timeout=180)
    else:
        subprocess.run(["espeak-ng", "-w", str(wav), SCRIPT], capture_output=True, timeout=180)
    return wav if wav.exists() and wav.stat().st_size > 100_000 else None


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
def podcast(tmp_path_factory) -> Path:
    d = tmp_path_factory.mktemp("podcast")
    speech = _speech(d)
    if speech is None:
        pytest.skip("no text-to-speech engine")
    out = d / "money podcast.mp4"
    subprocess.run([ffmpeg_bin(), "-v", "error", "-y", "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=25", "-i", str(speech),
                    "-shortest", "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", "-c:a", "aac", str(out)],
                   check=True)
    return out


def _snap(page, name: str, full: bool = False) -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f"clips-{name}.png"), full_page=full)


def test_clips_flow_find_edit_zip_and_caption_editor(browser, podcast):
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    errors: list[str] = []
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.on("pageerror", lambda e: errors.append(str(e)))

    page.goto(f"{BASE}/ai-clip-generator", wait_until="networkidle")
    assert page.get_by_role("heading", level=1).inner_text().lower().startswith("turn one long video")
    _snap(page, "1-landing")

    page.set_input_files("input[type=file]", str(podcast))
    page.get_by_role("radio", name="< 30 s").click()
    start = page.get_by_role("button", name="Find viral clips")
    start.wait_for(state="visible")
    page.wait_for_function("() => [...document.querySelectorAll('button')].some(b => b.textContent.includes('Find viral clips') && !b.disabled)",
                           timeout=120_000)
    _snap(page, "2-settings")
    start.click()

    page.get_by_text(re.compile(r"Listening|AI is listening|Waiting in line|Finding moments|Making")).first.wait_for(timeout=60_000)
    _snap(page, "3-progress")
    page.get_by_role("heading", name=re.compile(r"clips?, best first")).wait_for(timeout=600_000)
    page.get_by_role("link", name=re.compile(r"Download all")).wait_for(timeout=900_000)
    page.wait_for_function("() => !document.body.innerText.includes('Making it…') && !document.body.innerText.includes('Waiting…')",
                           timeout=900_000)
    cards = page.locator("article[aria-label^='Clip ']")
    n = cards.count()
    assert n >= 1
    first = cards.first
    assert first.locator("h3").inner_text().strip()
    assert first.locator("video").count() == 1
    _snap(page, "4-results", full=True)

    # Why this clip: score breakdown + reason.
    first.get_by_role("button", name="Why this clip").click()
    for label in ("Hook", "Flow", "Value", "Shareable"):
        assert first.get_by_text(label, exact=True).count() >= 1

    # The clip video and ZIP really download.
    video_url = first.locator("video").get_attribute("src")
    r = page.request.get(f"{BASE}{video_url}")
    assert r.ok and r.headers["content-type"] == "video/mp4" and len(r.body()) > 50_000
    zip_href = page.get_by_role("link", name=re.compile(r"Download all")).get_attribute("href")
    r = page.request.get(f"{BASE}{zip_href}")
    assert r.ok and r.body()[:2] == b"PK"

    # Edit: new hook -> the clip is made again.
    first.get_by_role("button", name="Edit", exact=True).click()
    dialog = page.get_by_role("dialog")
    dialog.wait_for()
    dialog.get_by_text("Loading the transcript…").wait_for(state="detached", timeout=30_000)
    assert dialog.get_by_role("button", name="Start here").count() >= 1
    _snap(page, "5-editor-trim")
    dialog.get_by_role("radio", name="Hook & text").click()
    hook = dialog.get_by_placeholder("e.g. Nobody tells you this about money")
    hook.fill("The money rule nobody teaches")
    _snap(page, "6-editor-text")
    dialog.get_by_role("button", name="Save & make the clip again").click()
    dialog.wait_for(state="detached")
    page.wait_for_function("() => document.body.innerText.includes('The money rule nobody teaches')", timeout=30_000)
    page.wait_for_function("() => !document.body.innerText.includes('Making it…') && !document.body.innerText.includes('Waiting…')",
                           timeout=600_000)
    _snap(page, "7-after-edit")

    # Open a clip in the full caption editor: words come along, no new speech-to-text.
    cards.first.get_by_role("button", name="Edit captions word by word").click()
    page.wait_for_url(re.compile(r"/auto-caption-generator"), timeout=30_000)
    page.get_by_text("AI clip").first.wait_for(timeout=30_000)
    page.get_by_role("tab", name=re.compile("Captions", re.I)).first.wait_for(timeout=120_000)
    _snap(page, "8-caption-editor")

    # Home page shows the tool as live, the header links to it.
    page.goto(f"{BASE}/", wait_until="networkidle")
    assert page.get_by_role("link", name=re.compile(r"AI Clips")).count() >= 1
    page.close()
    real = [e for e in errors if "favicon" not in e and "net::ERR_ABORTED" not in e]
    assert not real, real


def test_clips_page_on_a_phone(browser):
    page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    page.goto(f"{BASE}/youtube-video-to-shorts", wait_until="networkidle")
    assert page.get_by_role("heading", level=1).is_visible()
    assert page.get_by_text("Drop your long video here").is_visible()
    width = page.evaluate("() => document.documentElement.scrollWidth")
    assert width <= 392, f"page scrolls sideways on a phone ({width}px)"
    _snap(page, "9-phone")
    page.close()
