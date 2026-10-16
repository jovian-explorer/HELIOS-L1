"""
The IPShocks database snapshot (helios.core.shock_catalog; Zenodo doi:10.5281/zenodo.19730292,
CC BY 4.0) and its use in the shock analysis.
"""
import gzip
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from helios.core import shock_catalog as sc

LOCAL = "http://127.0.0.1:8765"
EVENTS = Path(__file__).parent / "data" / "hapi" / "events"


def _text(name):
    with gzip.open(EVENTS / f"{name}.csv.gz", "rt", encoding="utf-8") as f:
        return f.read()


def test_snapshot_holds_the_l1_shocks_of_the_zenodo_version():
    cat = sc.load()
    assert cat["licence"] == "CC BY 4.0" and cat["doi"] == "10.5281/zenodo.19730292" and cat["version"] == "2026-04-24"
    ev = cat["events"]
    assert len(ev) == 1064 and {e["spacecraft"] for e in ev} == {"WIND", "ACE", "DSCOVR"}
    assert sum(e["type"] == "FF" for e in ev) == 851
    e = sc.nearest(ev, "WIND", datetime(2015, 3, 17, 4, 1, tzinfo=timezone.utc))
    assert e["time"] == "2015-03-17 04:00:03" and e["type"] == "FF"
    assert (e["shock_speed_kms"], e["shock_speed_error_kms"], e["theta_bn_deg"], e["alfven_mach"]) == (561.7, 39.1, 63.1, 3.53)
    assert sc.nearest(ev, "ACE", datetime(2015, 3, 17, 4, 1, tzinfo=timezone.utc)) is None  # not listed at ACE
    arrival = sc.planar_arrival(e)  # |n.r| / V_sh = 44.6 min after 04:00:03
    assert arrival.strftime("%H:%M:%S") == "04:44:37"
    assert sc.driver_of(ev, arrival + timedelta(minutes=14)) is e and sc.driver_of(ev, arrival + timedelta(minutes=16)) is None
    assert sc.angle_deg([1, 0, 0], [-1, 0, 0]) == 0.0 and sc.angle_deg([1, 0, 0], [0, 1, 0]) == pytest.approx(90.0)


def test_shock_list_api(monkeypatch):
    from fastapi.testclient import TestClient
    from helios.api import server
    client = TestClient(server.app, base_url=LOCAL)
    body = client.get("/api/catalogs/shocks?start=2015-06-22&end=2015-06-23").json()
    assert [(e["time"], e["spacecraft"]) for e in body["events"]] == [
        ("2015-06-22 04:51:06", "ACE"), ("2015-06-22 05:04:45", "WIND"), ("2015-06-22 17:59:39", "ACE"),
        ("2015-06-22 18:08:17", "WIND")]
    assert body["catalog"]["licence"] == "CC BY 4.0" and "Kilpua" in body["catalog"]["citation"]
    wind = client.get("/api/catalogs/shocks?start=2015-06-22&end=2015-06-23&spacecraft=wind").json()
    assert wind["count"] == 2
    text = client.get("/api/catalogs/shocks?start=2015-06-22&end=2015-06-23&spacecraft=ACE&format=csv").text
    lines = text.splitlines()
    assert "# licence: CC BY 4.0" in lines and lines[-1].startswith("2015-06-22 17:59:39,ACE,FF,249.54 -1.44 25.35,")
    assert client.get("/api/catalogs/shocks?spacecraft=SOHO").status_code == 422
    assert client.get("/api/catalogs/shocks?start=2015-06-23&end=2015-06-22").status_code == 422


def test_shock_analysis_with_the_database_windows_reports_its_entry(monkeypatch, tmp_path):
    """
    WIND, 17 March 2015: with the database's windows (8 min, 1 min left out before and 2 min
    after) and its time, the MX3 normal here is 2.4 deg from the listed one and theta_Bn
    and V_sh are within the listed errors (63.1 +- 16.8 deg, 561.7 +- 39.1 km/s).
    """
    from fastapi.testclient import TestClient
    from helios.api import server
    from helios.core.downloader import DataDownloader
    from helios.core.event_analysis import EventDataClient

    served = {"WI_H0_MFI@1": "wi_h0_mfi3s_20150317", "WI_H1_SWE": "wi_h1_swe_20150317"}

    async def fake(url, timeout=120.0):
        ds = parse_qs(urlparse(url).query)["id"][0]
        return _text(served[ds]) if ds in served else None

    dl = DataDownloader()
    dl.fetch_text = fake
    dl.events = EventDataClient(lambda url: dl.fetch_text(url), tmp_path)
    monkeypatch.setattr(server, "downloader", dl)
    client = TestClient(server.app, base_url=LOCAL)
    base = "/api/analysis/shock?mission=WIND&time=2015-03-17T04:00:03&upstream_minutes=8&downstream_minutes=8"
    r = client.get(base + "&exclude_minutes=1&exclude_after_minutes=2&refine=false").json()["result"]
    assert r["windows_minutes"] == {"before": [-9, -1], "after": [2, 10]}
    ip, m = r["ipshocks"], r["methods"]["MX3"]
    assert ip["time"] == "2015-03-17 04:00:03" and ip["offset_seconds"] == 0
    assert ip["normal_angle_deg"] == pytest.approx(2.4, abs=0.1)
    assert abs(m["theta_bn_deg"] - ip["theta_bn_deg"]) < ip["theta_bn_error_deg"]
    assert abs(m["shock_speed_kms"] - ip["shock_speed_kms"]) < ip["shock_speed_error_kms"]
    assert ip["catalog"]["windows_minutes"] == {"upstream": [-9, -1], "downstream": [2, 10]}
    same_gap = client.get(base + "&exclude_minutes=1&refine=false").json()["result"]
    assert same_gap["windows_minutes"] == {"before": [-9, -1], "after": [1, 9]}
    assert client.get(base + "&exclude_after_minutes=16").status_code == 422


@pytest.mark.parametrize("time, day, kind, listed", [
    # The field turns inside the downstream window: |mean B| 2.1 nT, mean |B| 9.7 nT. The
    # magnitude of the mean vector made this fast forward shock a slow one (B2/B1 0.31).
    ("2000-08-05T04:45:05", "20000805", "FF", {"density_ratio": 1.52, "field_ratio": 1.42}),
    # A reverse shock: the database lists the speed's magnitude (288 km/s); along the sunward normal it is negative.
    ("2000-04-17T09:39:26", "20000417", "FR", {"density_ratio": 1.92, "field_ratio": 1.65}),
])
def test_ace_shocks_with_the_database_windows(monkeypatch, tmp_path, time, day, kind, listed):
    from fastapi.testclient import TestClient
    from helios.api import server
    from helios.core.downloader import DataDownloader
    from helios.core.event_analysis import EventDataClient

    served = {"AC_H0_MFI": f"ac_h0_mfi_{day}_shock", "AC_H0_SWE": f"ac_h0_swe_{day}_shock"}

    async def fake(url, timeout=120.0):
        ds = parse_qs(urlparse(url).query)["id"][0]
        return _text(served[ds]) if ds in served else None

    dl = DataDownloader()
    dl.fetch_text = fake
    dl.events = EventDataClient(lambda url: dl.fetch_text(url), tmp_path)
    monkeypatch.setattr(server, "downloader", dl)
    gaps = "exclude_minutes=1&exclude_after_minutes=2" if kind == "FF" else "exclude_minutes=2&exclude_after_minutes=1"
    r = TestClient(server.app, base_url=LOCAL).get(
        f"/api/analysis/shock?mission=ACE&time={time}&upstream_minutes=8&downstream_minutes=8&{gaps}&refine=false"
    ).json()["result"]
    ip, m = r["ipshocks"], r["methods"]["MX3"]
    assert r["shock_type"] == ip["type"] == kind
    assert r["density_ratio"] == pytest.approx(listed["density_ratio"], abs=0.06)
    assert r["field_ratio"] == pytest.approx(listed["field_ratio"], abs=0.02)
    assert ip["normal_angle_deg"] < 3.0
    assert (m["shock_speed_kms"] > 0) == (kind == "FF")
    assert abs(abs(m["shock_speed_kms"]) - ip["shock_speed_kms"]) < ip["shock_speed_error_kms"]
    assert m["alfven_mach"] == pytest.approx(ip["alfven_mach"], rel=0.1)
