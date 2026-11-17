"""Browser end-to-end test of the Reframe page (real Next.js site + real API).

Not part of the normal run. Start both servers, then:
    KLY_E2E_URL=http://localhost:3000 pytest tests/e2e -s
Screenshots are written to .tmp/e2e/.
"""

from __future__ import annotations

import os
import re

import pytest

from app.config import DATA_DIR

BASE = os.environ.get("KLY_E2E_URL")
pytestmark = pytest.mark.skipif(not BASE, reason="set KLY_E2E_URL to run browser tests")
SHOTS = DATA_DIR / "e2e"


@pytest.fixture(scope="module")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception:  # noqa: BLE001  Playwright's own browser not downloaded: use the installed Edge / Chrome
            try:
                b = p.chromium.launch(channel="msedge")
            except Exception:  # noqa: BLE001
                b = p.chromium.launch(channel="chrome")
        yield b
        b.close()


def _snap(page, name: str) -> None:
    SHOTS.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(SHOTS / f"{name}.png"), full_page=False)


def test_upload_convert_edit_download(browser, media):
    page = browser.new_page(viewport={"width": 1366, "height": 900})
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(f"{BASE}/landscape-to-portrait-video-converter")
    page.get_by_text("Drop your landscape video here").wait_for()
    _snap(page, "1-empty")

    page.set_input_files("input[type=file]", str(media["cuts"]))
    convert = page.get_by_role("button", name=re.compile(r"^Convert to 9:16"))
    convert.wait_for(timeout=60_000)
    page.get_by_role("button", name=re.compile("Blur Fill")).click()
    page.wait_for_timeout(600)
    _snap(page, "2-blur-preview")
    page.get_by_role("button", name=re.compile("Smart Reframe")).click()
    page.get_by_role("button", name=re.compile(r"^1:1")).click()
    page.get_by_role("button", name=re.compile(r"^Convert to 9:16 \+ 1:1")).click()

    page.get_by_text(re.compile("AI analysis|Rendering|Waiting in line")).first.wait_for(timeout=30_000)
    _snap(page, "3-progress")
    page.get_by_text(re.compile("Your vertical videos are ready")).wait_for(timeout=240_000)
    _snap(page, "4-done")

    links = page.locator("a[download]")
    assert links.count() == 2
    href = links.first.get_attribute("href")
    resp = page.request.get(f"{BASE}{href}")
    assert resp.status == 200 and resp.headers["content-type"] == "video/mp4" and len(resp.body()) > 10_000
    assert page.locator("aside video").first.get_attribute("src")

    # Shot editor: force the first shot to "Keep whole" and apply.
    editor = page.get_by_role("heading", name="Shot editor")
    editor.scroll_into_view_if_needed()
    _snap(page, "5-editor")
    page.get_by_label("Layout for shot 1").select_option("fit")
    page.get_by_role("button", name=re.compile(r"Apply \(1 shot\)")).click()
    page.wait_for_function(
        "() => { const a = [...document.querySelectorAll('a[download]')]; return a.length === 2 && a.every(x => x.href.includes('v=1')); }",
        timeout=240_000,
    )
    page.get_by_role("heading", name="Shot editor").scroll_into_view_if_needed()
    _snap(page, "6-after-edit")
    reasons = page.locator("article p").all_inner_texts()
    assert any("Chosen in the editor" in r for r in reasons), reasons
    assert not errors, errors


def test_mobile_layout_and_seo(browser):
    page = browser.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True)
    page.goto(f"{BASE}/podcast-to-shorts")
    page.get_by_text("Drop your landscape video here").wait_for()
    _snap(page, "7-mobile")
    width = page.evaluate("() => document.documentElement.scrollWidth")
    assert width <= 390, "page scrolls sideways on phones"
    html = page.content()
    assert '"@type":"FAQPage"' in html.replace(" ", "") and "canonical" in html
    sitemap = page.request.get(f"{BASE}/sitemap.xml").text()
    assert "landscape-to-portrait-video-converter" in sitemap and "gameplay-to-tiktok" in sitemap


@pytest.mark.skipif(not os.environ.get("KLY_E2E_LINK"), reason="set KLY_E2E_LINK to a public video URL (needs internet)")
def test_make_it_vertical_from_the_downloader(browser):
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(BASE)
    page.get_by_role("textbox").first.fill(os.environ["KLY_E2E_LINK"])
    page.keyboard.press("Enter")
    page.get_by_role("button", name="Make it vertical").click(timeout=90_000)
    page.wait_for_url(re.compile(r"landscape-to-portrait-video-converter\?from=link"))
    page.get_by_role("button", name=re.compile(r"^Blur Fill")).click()
    page.get_by_role("button", name=re.compile(r"^Convert to 9:16")).click()
    page.get_by_text(re.compile("Your vertical video is ready")).wait_for(timeout=300_000)
    _snap(page, "8-from-link")
    assert page.locator("a[download]").count() == 1
