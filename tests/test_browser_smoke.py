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
