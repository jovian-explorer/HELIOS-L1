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
        # Host header set directly: the test client cannot parse an IPv6 base URL.
        assert client.get("/api/status", headers={"Host": host, "Origin": f"http://{host}"}).status_code == 200


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


@pytest.mark.parametrize("url", ["/api/orbits?epoch=nan", "/api/ephemeris/spice?epoch=1e309",
                                 "/api/parker_spiral?speed_kms=inf", "/api/gic/hazard?db_dt=-Infinity",
                                 "/api/ionosphere/absorption?xray_flux=NaN"])
def test_non_finite_query_numbers_are_422_not_500(url):
    # Reproduction: FastAPI parses 'nan'/'inf' as floats; the NaN results failed JSON encoding (500).
    r = TestClient(server.app, base_url=LOCAL, raise_server_exceptions=False).get(url)
    assert r.status_code == 422 and "finite" in r.json()["detail"]


@pytest.mark.parametrize("body", ['{"dt_minutes": NaN}', '{"r2_rsun": Infinity}', '{"dt_minutes": 0}',
                                  '{"r1_rsun": 6, "r2_rsun": 3}', '{"launch_time_iso": "yesterday"}'])
def test_invalid_cme_inputs_are_422(body):
    # NaN/Infinity bodies made FastAPI's own 422 handler fail (500); dt = 0 or r2 < r1 answered
    # 200 with an "error" field; an unreadable launch time silently became "now".
    c = TestClient(server.app, base_url=LOCAL, raise_server_exceptions=False)
    r = c.post("/api/coronagraph/kinematics", content=body, headers={"Content-Type": "application/json"})
    assert r.status_code == 422


def test_empty_epoch_means_now(client):
    assert client.get("/api/orbits?epoch=").status_code == 200
    assert client.get("/api/ephemeris/spice/trajectory?epoch=").status_code == 200


def test_settings_save_failure_is_reported(client, restore_settings, monkeypatch):
    # Reproduction: make the settings file unwritable; the answer said "saved": true because
    # an older settings file existed, and the interface closed the dialog as if saved.
    client.post("/api/settings", json={"theme": "mission-slate"})
    assert config.SETTINGS_FILE.exists()

    def locked(*a, **k):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(config.os, "replace", locked)
    r = client.post("/api/settings", json={"theme": "deep-space"})
    assert r.status_code == 200
    body = r.json()
    assert body["saved"] is False and "Permission denied" in body["save_error"]
    assert body["theme"] == "deep-space"  # still applied for this session


class _Stop(Exception):
    """Ends the launcher's headless wait loop in a test."""


def _launcher(monkeypatch):
    import threading
    import time as _time
    from helios.gui import app as launcher
    real_sleep = _time.sleep

    def sleep(seconds):
        if threading.current_thread() is threading.main_thread():
            raise _Stop()
        real_sleep(seconds)

    monkeypatch.setattr(launcher.time, "sleep", sleep)
    monkeypatch.setattr(launcher, "check_existing_helios", lambda host, port: False)
    return launcher


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.1.20", "::"])
def test_launcher_refuses_non_loopback_bind_address(monkeypatch, capsys, host):
    # Reproduction: `helios --headless --host 0.0.0.0` served the API to the whole network.
    launcher = _launcher(monkeypatch)
    started = []
    monkeypatch.setattr(launcher, "find_available_port", lambda h, p: started.append(h) or p)
    with pytest.raises(SystemExit) as exc:
        launcher.launch_desktop(host=host, port=8799, headless=True)
    assert exc.value.code == 2 and not started
    assert "only listens on the local machine" in capsys.readouterr().out


def test_launcher_reports_a_port_taken_by_another_program(monkeypatch, capsys):
    # Reproduction: another program listens on the port HELIOS chose (taken between the
    # free-port check and the start). The server thread died, the launcher saw *something*
    # answering on the port, printed "Engine online" and opened the window on the other program.
    import socket
    launcher = _launcher(monkeypatch)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as other:
        other.bind(("127.0.0.1", 0))
        other.listen(1)
        port = other.getsockname()[1]
        monkeypatch.setattr(launcher, "find_available_port", lambda h, p: port)
        with pytest.raises(SystemExit) as exc:
            launcher.launch_desktop(host="127.0.0.1", port=port, headless=True)
    out = capsys.readouterr().out
    assert exc.value.code == 1
    assert f"could not listen on 127.0.0.1:{port}" in out and "--port" in out
    assert "Engine online" not in out


def test_ctrl_c_in_the_desktop_window_does_not_open_a_browser(monkeypatch):
    # The window fallback caught BaseException, so Ctrl+C (KeyboardInterrupt) or a SystemExit
    # raised while the desktop window was open started the system browser instead of quitting.
    import sys
    import types
    launcher = _launcher(monkeypatch)
    monkeypatch.setattr(launcher, "find_available_port", lambda h, p: p)

    class FakeServer:
        started = True

    monkeypatch.setattr(launcher, "start_server", lambda h, p: (FakeServer(), None))
    monkeypatch.setattr(launcher, "wait_for_server", lambda server, thread: True)
    opened = []
    monkeypatch.setattr(launcher.webbrowser, "open", lambda url: opened.append(url))

    def start(**kwargs):
        raise KeyboardInterrupt

    fake = types.SimpleNamespace(create_window=lambda **kw: None, start=start)
    monkeypatch.setitem(sys.modules, "webview", fake)
    with pytest.raises(KeyboardInterrupt):
        launcher.launch_desktop(host="127.0.0.1", port=8798, headless=False)
    assert opened == []

    # An ordinary failure of the window toolkit still falls back to the browser.
    def broken(**kwargs):
        raise RuntimeError("no GUI toolkit")

    fake.start = broken
    with pytest.raises(_Stop):
        launcher.launch_desktop(host="127.0.0.1", port=8798, headless=False)
    assert opened == ["http://127.0.0.1:8798"]


def test_launcher_check_on_a_free_port_is_immediate():
    """A port that can be bound has no HELIOS-L1 behind it: no HTTP probe (a refused local
    connection took about a second on Windows, once or twice per start)."""
    import socket
    import time
    from helios.gui import app as launcher
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    t = time.monotonic()
    assert launcher.check_existing_helios("127.0.0.1", port) is False
    assert time.monotonic() - t < 0.5
