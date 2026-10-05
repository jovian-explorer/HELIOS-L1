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


CSV = "time_tag,speed,density\n2024-05-10 00:00,400,5\n2024-05-10 00:01,410,6\n"


@pytest.mark.parametrize("name", ["..\..\AppData\Roaming\evil.bat", "../../etc/x", 'a"; filename=x.exe',
                                  "probe\r\nX-Injected: 1", "日本の探査機"])
def test_download_names_from_request_values_are_sanitised(client, name):
    # Reproduction: import a file with this mission name, then export it. The name went
    # into the Content-Disposition header unchanged: path separators and quotes reached the
    # browser, CR/LF injected a header and non-Latin-1 names made the export a 500.
    assert client.post("/api/custom/import", json={"content": CSV, "mission_name": name}).status_code == 200
    for fmt in ("csv", "json"):
        r = client.get(f"/api/custom/export/{fmt}")
        assert r.status_code == 200
        disp = r.headers["content-disposition"]
        assert "x-injected" not in {k.lower() for k in r.headers}
        filename = disp.split("filename=", 1)[1].strip('"')
        assert all(c.isascii() and (c.isalnum() or c in "._-") for c in filename), disp
        assert filename.endswith(f"_telemetry.{fmt}") and ".." not in filename


def test_static_files_do_not_leave_the_static_folder(client):
    for path in ("/static/../config.py", "/static/%2e%2e/%2e%2e/config.py", "/static/..%5c..%5cconfig.py",
                 "/static/%2e%2e%2fapi%2fserver.py"):
        r = client.get(path)
        assert r.status_code == 404 or "DEFAULT_PORT" not in r.text


def test_import_body_size_is_limited(client):
    # Reproduction: POST a 70 MB import; it was read, decoded and parsed whole.
    big = '{"content": "' + "x" * (70 * 1024 * 1024) + '"}'
    r = client.post("/api/custom/import", content=big, headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    # Without Content-Length (chunked), the streamed size is counted.
    def chunks():
        yield b'{"content": "'
        for _ in range(70):
            yield b"x" * (1 << 20)
        yield b'"}'
    r = client.post("/api/custom/import", content=chunks(), headers={"Content-Type": "application/json"})
    assert r.status_code == 413
    # Normal imports still pass, and so do small forms.
    assert client.post("/api/custom/import", json={"content": CSV, "mission_name": "probe"}).status_code == 200


def test_form_endpoints_have_a_small_body_limit(client):
    r = client.post("/api/coronagraph/kinematics", json={"dt_minutes": 30, "pad": "x" * 100_000})
    assert r.status_code == 413
    r = client.post("/api/custom/import", json={"content": CSV, "mission_name": "m" * 500})
    assert r.status_code == 422


def test_superposed_epoch_total_download_is_limited(client):
    # 60 onsets x 240 h asked for 600 days of OMNI files in one request.
    onsets = ",".join(f"2020-{m:02d}-{d:02d}T00:00" for m in range(1, 4) for d in range(1, 21))
    r = client.get("/api/analysis/superposed", params={"onsets": onsets, "before_hours": 120, "after_hours": 120})
    assert r.status_code == 422 and "at most 180 days" in r.json()["detail"]


def test_ephemeris_id_list_is_deduplicated_and_limited(client):
    r = client.get("/api/ephemeris/spice", params={"satellites": ",".join(f"SC{i}" for i in range(41))})
    assert r.status_code == 422
    r = client.get("/api/ephemeris/spice", params={"satellites": "EARTH," * 500})
    assert r.status_code == 200 and list(r.json()["fleet"]) == ["EARTH"]
