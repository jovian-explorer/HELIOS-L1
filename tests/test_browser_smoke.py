"""
Browser smoke test: the app served offline (network blocked by conftest, bundled data only) in headless
Chromium, every main view opened once. Fails on a page error, a console error, or a view that shows no
text (an empty panel without an explanation) or prints "undefined" / "NaN" / "[object Object]".

Needs Playwright and its Chromium (`pip install playwright && python -m playwright install chromium`);
skipped without them. CI runs it in its own job (.github/workflows/ci.yml).
"""
import os
import re
import socket

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

# Text a view must not show: values the code failed to fill in.
BROKEN = re.compile(r"\bundefined\b|\bNaN\b|\[object Object\]")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def server_url():
    from helios.gui.app import start_server, wait_for_server
    port = _free_port()
    server, thread = start_server("127.0.0.1", port)
    assert wait_for_server(server, thread), "server did not start"
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(10)


def test_every_view_opens_offline_without_errors(server_url):
    problems = []
    with sync_api.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except sync_api.Error as exc:  # Playwright installed without its browser: a failure in CI's browser job
            if os.environ.get("CI"):
                raise
            pytest.skip(f"Chromium for Playwright is not installed: {exc}")
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.on("pageerror", lambda e: problems.append(f"page error: {e}"))
        # Offline the live-data routes answer 503 with an explanation the views show; Chromium logs every
        # such answer as a console error, so those are left out here and any other 4xx/5xx is a problem.
        page.on("console", lambda m: problems.append(f"console {m.type}: {m.text}")
                if m.type == "error" and not m.text.startswith("Failed to load resource") else None)
        page.on("response", lambda r: problems.append(f"HTTP {r.status}: {r.url}")
                if r.status >= 400 and r.status != 503 else None)
        page.goto(server_url, wait_until="networkidle")
        tabs = page.evaluate("Object.keys(TAB_TO_DOMAIN).filter(t => document.getElementById('tab-' + t))")
        assert len(tabs) >= 14, tabs
        for tab in tabs:
            page.evaluate(f"switchTab('{tab}')")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(300)
            text = page.inner_text(f"#tab-{tab}")
            if len(text.strip()) < 80:
                problems.append(f"{tab}: almost no text ({text.strip()[:60]!r})")
            for m in BROKEN.finditer(text):
                problems.append(f"{tab}: shows {m.group(0)!r} near {text[max(0, m.start() - 40):m.end() + 20]!r}")
        page.evaluate("openReferencesModal()")
        page.wait_for_load_state("networkidle")
        if len(page.inner_text("#modal-references").strip()) < 80:
            problems.append("references: almost no text")
        browser.close()
    assert not problems, "\n".join(problems)


def _browser(p):
    try:
        return p.chromium.launch()
    except sync_api.Error as exc:
        if os.environ.get("CI"):
            raise
        pytest.skip(f"Chromium for Playwright is not installed: {exc}")


def test_bulletin_keeps_its_styles_to_itself_and_prints_alone(server_url):
    """The bulletin is a full HTML document with its own <style> (body padding, .grid of three columns, ...).
    Shown in the window it must not restyle the app, and "Print / PDF" must print the bulletin only (not the
    dashboard behind the dialog, cut at the dialog's height), dark text on white paper."""
    with sync_api.sync_playwright() as p:
        browser = _browser(p)
        page = browser.new_page(viewport={"width": 1280, "height": 900})
        page.goto(server_url, wait_until="networkidle")
        probe = """(() => { const g = [...document.querySelectorAll('main .grid')].find(e => e.offsetParent);
                      return [getComputedStyle(document.body).padding, getComputedStyle(g).gridTemplateColumns]; })()"""
        before = page.evaluate(probe)
        page.evaluate("openBulletinModal()")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(500)
        assert page.evaluate(probe) == before
        frame = page.frame_locator("#bulletin-content iframe")
        assert "Space Weather Scientific Bulletin" in frame.locator("h1").inner_text()
        # The iframe is as tall as its document (no inner scrollbar) and prints itself, not the app.
        heights = page.evaluate("""(() => { const f = document.querySelector('#bulletin-content iframe');
                                      return [f.offsetHeight, f.contentDocument.documentElement.scrollHeight]; })()""")
        assert abs(heights[0] - heights[1]) <= 2, heights
        page.evaluate("""window.__printed = [];
            window.print = () => window.__printed.push('app');
            document.querySelector('#bulletin-content iframe').contentWindow.print = () => window.__printed.push('bulletin');
            0;""")  # not a function value: Playwright would call it
        page.get_by_role("button", name="Print / PDF").click()
        assert page.evaluate("window.__printed") == ["bulletin"]
        page.evaluate("setBulletinViewFormat('md')")
        assert "HELIOS-L1" in frame.locator("pre").inner_text()
        # The PDF of the bulletin alone: one A4 page, black body text on white with background graphics off.
        doc = browser.new_page()
        doc.goto(server_url + "/api/report/html?mission_id=DSCOVR", wait_until="networkidle")
        doc.emulate_media(media="print")
        assert doc.evaluate("[getComputedStyle(document.body).color, getComputedStyle(document.body).backgroundColor]") == \
            ["rgb(0, 0, 0)", "rgb(255, 255, 255)"]
        pdf = doc.pdf(format="A4")
        assert pdf[:5] == b"%PDF-" and len(re.findall(rb"/Type\s*/Page[^s]", pdf)) == 1
        browser.close()
