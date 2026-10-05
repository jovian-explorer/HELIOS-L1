"""
Security of the local server: requests a web page open in the user's browser can make to
127.0.0.1 (cross-site request forgery, DNS rebinding), path handling, request limits,
error answers and the bind address.
"""
import pytest
from fastapi.testclient import TestClient

from helios import config
from helios.api import server

LOCAL = "http://127.0.0.1:8765"
EVIL = "http://evil.example"


@pytest.fixture
def client():
    return TestClient(server.app, base_url=LOCAL)


@pytest.fixture
def restore_settings():
    before = config.get_system_settings()
    yield
    config.update_system_settings(theme=before["theme"], font_size=before["font_size"],
                                  timezone=before["timezone"], processors=before["active_processors"])


def test_cross_origin_json_post_cannot_change_settings(client, restore_settings):
    # Reproduction: a page on another site sends fetch('http://127.0.0.1:8765/api/settings',
    # {method: 'POST', headers: {'Content-Type': 'application/json'}, body: ...}). The old
    # CORS policy (allow_origins=["*"] with credentials) approved the preflight and the
    # POST changed and saved the settings.
    client.post("/api/settings", json={"theme": "mission-slate"})
    pre = client.options("/api/settings", headers={
        "Origin": EVIL, "Access-Control-Request-Method": "POST", "Access-Control-Request-Headers": "content-type"})
    assert pre.headers.get("access-control-allow-origin") is None
    r = client.post("/api/settings", json={"theme": "solar-amber"},
                    headers={"Origin": EVIL, "Sec-Fetch-Site": "cross-site"})
    assert r.status_code == 403
    assert config.get_system_settings()["theme"] == "mission-slate"


def test_cross_origin_page_cannot_read_answers(client):
    r = client.get("/api/settings", headers={"Origin": EVIL})
    assert r.status_code == 403
    assert r.headers.get("access-control-allow-origin") is None


@pytest.mark.parametrize("site", ["cross-site", "same-site"])
def test_cross_site_side_effect_get_is_rejected(client, site):
    # <img src="http://127.0.0.1:8765/api/archive/WIND?start=...&end=..."> on another site
    # (or another local port, which browsers count as "same-site") would start a month of
    # archive downloads. Browsers mark such requests with Sec-Fetch-Site.
    r = client.get("/api/archive/WIND?start=2024-05-01&end=2024-05-31", headers={"Sec-Fetch-Site": site})
    assert r.status_code == 403


@pytest.mark.parametrize("ctype,body", [
    ("text/plain", '{"theme": "solar-amber"}'),
    ("application/x-www-form-urlencoded", "theme=solar-amber"),
    ("multipart/form-data; boundary=x", "--x--"),
])
def test_simple_post_bodies_are_rejected(client, ctype, body):
    # Simple requests (no preflight) without Origin or Sec-Fetch-Site, as older browsers send.
    r = client.post("/api/settings", content=body, headers={"Content-Type": ctype})
    assert r.status_code == 415


def test_null_origin_is_rejected(client):
    # Sandboxed iframes and file:// pages send Origin: null.
    r = client.post("/api/custom/import", json={"content": "x"}, headers={"Origin": "null"})
    assert r.status_code == 403


@pytest.mark.parametrize("host", ["evil.example:8765", "127.0.0.1.nip.io:8765", "192.168.1.5:8765"])
def test_dns_rebinding_host_is_rejected(host):
    # A site whose name resolves to 127.0.0.1 is same-origin with the server in the browser.
    c = TestClient(server.app, base_url=f"http://{host}")
    assert c.get("/api/settings").status_code == 403
    assert c.get("/").status_code == 403


def test_interface_requests_still_work(client, restore_settings):
    same = {"Origin": LOCAL, "Sec-Fetch-Site": "same-origin"}
    r = client.post("/api/settings", json={"theme": "deep-space"}, headers=same)
    assert r.status_code == 200 and r.json()["theme"] == "deep-space"
    assert client.get("/api/status", headers={"Sec-Fetch-Site": "same-origin"}).status_code == 200
    # Typed into the address bar / opened by the launcher.
    assert client.get("/api/status", headers={"Sec-Fetch-Site": "none"}).status_code == 200
    assert client.get("/", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 200
    for host in ("localhost:8765", "[::1]:8765"):
        c = TestClient(server.app, base_url=f"http://{host}")
        assert c.get("/api/status", headers={"Origin": f"http://{host}"}).status_code == 200
