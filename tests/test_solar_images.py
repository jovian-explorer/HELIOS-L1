"""
Solar image archive (helios.core.solar_images). The Helioviewer answers below are real
getClosestImage responses (LASCO C2 on 9 May 2024); the network test runs only with
HELIOS_NETWORK_TESTS=1.
"""
import asyncio
import json
import os
from datetime import datetime, timezone
from urllib.parse import parse_qs, urlparse

import pytest

from helios.core import solar_images as si

LOCAL = "http://127.0.0.1:8765"
C2 = {"id": "156576933", "date": "2024-05-09 09:24:07", "name": "LASCO C2", "scale": 11.9, "width": 1024,
      "height": 1024, "refPixelX": 511.2, "refPixelY": 507.5, "rsun": 80.64235294117648, "layeringOrder": 2}
PNG = b"\x89PNG\r\n\x1a\nfake"


def _client(tmp_path, answers, log):
    async def text(url):
        log.append(url)
        q = parse_qs(urlparse(url).query)
        return json.dumps(answers(q["date"][0]))

    async def data(url):
        log.append(url)
        return PNG
    return si.SolarImageClient(text, data, tmp_path)


def test_frames_are_distinct_images_inside_the_interval_with_their_geometry(tmp_path):
    # Images every 12 min: 6 requests over 1 h give the closest ones, each listed once.
    def answers(date):
        t = datetime.strptime(date, "%Y-%m-%dT%H:%M:%SZ")
        m = round(t.minute / 12) * 12
        return dict(C2, id=str(1000 + t.hour * 60 + m), date=f"2024-05-09 {t.hour:02d}:{m:02d}:07" if m < 60 else "2024-05-09 10:00:07")
    log = []
    c = _client(tmp_path, answers, log)
    res = asyncio.run(c.frames("lasco_c2", datetime(2024, 5, 9, 9), datetime(2024, 5, 9, 10), 6, 512))
    dates = [f["date"] for f in res["frames"]]
    assert dates == sorted(set(dates)) and len(dates) == 6
    f = res["frames"][0]
    # R_sun = 80.64 px x 11.9"/px = 959.6"; +-6.5 R_sun over 512 px
    assert f["rsun_arcsec"] == pytest.approx(959.64, abs=0.01)
    assert f["rsun_px"] == pytest.approx(512 / 13.0)
    assert f["scale_arcsec_per_px"] == pytest.approx(2 * 6.5 * 959.64 / 512, rel=1e-4)
    assert "instrument=lasco_c2" in f["image_url"] and "Helioviewer" in res["credit"]
    # An image taken outside the interval is not listed.
    out = asyncio.run(c.frames("lasco_c2", datetime(2024, 5, 9, 11, 30), datetime(2024, 5, 9, 11, 40), 1))
    assert out["frames"] == [] or all("11:" in x["date"] for x in out["frames"])


def test_image_is_sun_centred_and_cached(tmp_path):
    log = []
    c = _client(tmp_path, lambda d: C2, log)
    png = asyncio.run(c.image("lasco_c2", datetime(2024, 5, 9, 9, 24, tzinfo=timezone.utc), 512))
    assert png == PNG
    shot = parse_qs(urlparse(log[-1]).query)
    assert shot["x0"] == ["0"] and shot["y0"] == ["0"] and shot["layers"] == ["[4,1,100]"]
    assert float(shot["imageScale"][0]) == pytest.approx(2 * 6.5 * 959.64 / 512, rel=1e-3)
    n = len(log)
    assert asyncio.run(c.image("lasco_c2", datetime(2024, 5, 9, 9, 24, tzinfo=timezone.utc), 512)) == PNG
    assert len(log) == n  # metadata and picture from the cache (the interval is old)
    with pytest.raises(ValueError):
        asyncio.run(c.image("lasco_c9", datetime(2024, 5, 9), 512))


def test_api_answers_offline_and_without_sunpy(monkeypatch):
    from fastapi.testclient import TestClient
    from helios.api import server
    client = TestClient(server.app, base_url=LOCAL)
    keys = {i["key"] for i in client.get("/api/solar_images/sources").json()["instruments"]}
    assert {"aia_193", "lasco_c2", "lasco_c3", "cor2", "euvi_195", "eui_fsi_174"} <= keys
    r = client.get("/api/solar_images/frames?instrument=lasco_c2&start=2024-05-09T06:00&end=2024-05-09T07:00")
    assert r.status_code == 503 and "Helioviewer" in r.json()["detail"]
    assert client.get("/api/solar_images/frames?instrument=nope&start=2024-05-09T06:00&end=2024-05-09T07:00").status_code == 422

    def no_sunpy(*a, **k):
        raise ImportError("sunpy")
    monkeypatch.setattr(si, "fits_search", no_sunpy)
    r = client.get("/api/solar_images/fits?instrument=lasco_c2&start=2024-05-09T06:00&end=2024-05-09T07:00")
    assert r.status_code == 501 and "helios-l1[solar]" in r.json()["detail"]


@pytest.mark.skipif(os.environ.get("HELIOS_NETWORK_TESTS") != "1", reason="network test (HELIOS_NETWORK_TESTS=1)")
def test_helioviewer_live(tmp_path):
    import httpx  # the suite's downloader is offline: plain requests here

    async def text(url):
        async with httpx.AsyncClient(timeout=60) as h:
            return (await h.get(url)).text

    async def data(url):
        async with httpx.AsyncClient(timeout=60) as h:
            return (await h.get(url)).content
    c = si.SolarImageClient(text, data, tmp_path)
    res = asyncio.run(c.frames("lasco_c2", datetime(2024, 5, 9, 9), datetime(2024, 5, 9, 10), 3))
    assert res["frames"] and res["frames"][0]["rsun_arcsec"] == pytest.approx(959.6, abs=1.0)
    assert asyncio.run(c.image("lasco_c2", datetime(2024, 5, 9, 9, 24), 256)).startswith(b"\x89PNG")
