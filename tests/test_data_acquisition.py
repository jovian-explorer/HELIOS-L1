"""
Data acquisition tests: NOAA RTSW parsing, fill values, provenance labels,
cache fallback and index parsing. All payloads are small hand-made samples in
the exact format served by NOAA SWPC; no network access is needed.
"""
import asyncio
import json
import os

import httpx
import pytest

from helios.core.downloader import DataDownloader, block_average, infer_cadence_seconds


def _mag(t, source, active, bz, by=-3.0, bx=2.0, bt=5.0, quality=0):
    return {"time_tag": t, "active": active, "source": source, "bt": bt,
            "bx_gse": bx, "by_gse": None if by is None else by + 0.5, "bz_gse": None if bz is None else bz + 0.5,
            "bx_gsm": bx, "by_gsm": by, "bz_gsm": bz, "overall_quality": quality}


def _wind(t, source, active, speed, density=4.0, temp=50000, quality=0):
    return {"time_tag": t, "active": active, "source": source, "proton_speed": speed,
            "proton_density": density, "proton_temperature": temp, "overall_quality": quality}


# Newest first, as served by NOAA.
MAG = [
    _mag("2026-10-02T18:02:00", "SOLAR1", True, -2.5),
    _mag("2026-10-02T18:02:00", "ACE", False, -2.0),
    _mag("2026-10-02T18:01:00", "SOLAR1", True, None, bt=None, by=None, bx=None),
    _mag("2026-10-02T18:01:00", "ACE", False, -1.9),
    _mag("2026-10-02T18:00:00", "SOLAR1", True, -2.2, quality=1),
    _mag("2026-10-02T18:00:00", "ACE", False, -1.8),
]
WIND = [
    _wind("2026-10-02T18:02:00", "SOLAR1", True, 300.0),
    _wind("2026-10-02T18:02:00", "ACE", False, 290.0, density=1.1),
    _wind("2026-10-02T18:01:00", "SOLAR1", True, 301.0),
    _wind("2026-10-02T18:00:00", "ACE", False, 289.0, density=1.0),
]


def test_parse_rtsw_operational_stream_keeps_gaps_and_order():
    recs, sources = DataDownloader.parse_rtsw(MAG, WIND, source=None)
    assert sources == ["SOLAR1"]
    # 18:00 magnetometer row has a bad quality flag and there is no 18:00 SOLAR1 plasma.
    assert [r["time_tag"] for r in recs] == ["2026-10-02 18:01:00", "2026-10-02 18:02:00"]
    gap = recs[0]
    # Missing field values must stay missing: no zeros, no defaults.
    assert gap["bz_gsm"] is None and gap["bt"] is None
    assert gap["magnetopause_re"] is None and gap["akasofu_gw"] is None
    assert gap["speed"] == 301.0 and gap["dynamic_pressure"] is not None
    last = recs[-1]
    assert last["bz_gsm"] == -2.5 and last["bz_gse"] == -2.0
    assert last["data_source"] == "observed" and last["source_spacecraft"] == "SOLAR1"


def test_parse_rtsw_selects_one_spacecraft():
    recs, sources = DataDownloader.parse_rtsw(MAG, WIND, source="ACE", mission_label="ACE")
    assert sources == ["ACE"]
    assert len(recs) == 3
    assert recs[0]["density"] == 1.0 and recs[0]["bz_gsm"] == -1.8
    assert recs[1]["speed"] is None  # no ACE plasma at 18:01


def test_bundle_reports_provenance(monkeypatch):
    async def fake_fetch(self, url, cache_key):
        return MAG if "mag" in url else WIND

    monkeypatch.setattr(DataDownloader, "fetch_json", fake_fetch)
    dl = DataDownloader()
    ace = asyncio.run(dl.get_telemetry_bundle("ACE"))
    assert ace["provenance"]["kind"] == "observed"
    assert all(r["data_source"] == "observed" for r in ace["records"])

    dscovr = asyncio.run(dl.get_telemetry_bundle("DSCOVR"))
    assert dscovr["provenance"]["kind"] == "observed"
    assert "SOLAR1" in dscovr["provenance"]["description"]

    wind = asyncio.run(dl.get_telemetry_bundle("WIND"))
    assert wind["provenance"]["kind"] == "simulated"
    assert all(r["data_source"] == "simulated" for r in wind["records"])


def test_offline_bundle_is_labelled_synthetic():
    # conftest blocks the network, so this exercises the offline path.
    bundle = asyncio.run(DataDownloader().get_telemetry_bundle("DSCOVR"))
    assert bundle["provenance"]["kind"] == "synthetic"
    assert bundle["records"] and all(r["data_source"] == "synthetic" for r in bundle["records"])
    aditya = asyncio.run(DataDownloader().get_telemetry_bundle("ADITYA_L1"))
    assert aditya["provenance"]["kind"] == "synthetic"


def test_block_average_means_not_decimation():
    recs = []
    for minute in range(10):
        recs.append({"time_tag": f"2026-10-02 18:{minute:02d}:00", "mission": "X",
                     "speed": 400.0 + 10.0 * (minute % 5), "density": 5.0,
                     "bz_gsm": -1.0, "by_gsm": 0.0, "bt": 2.0})
    out = block_average(recs, 5)
    assert len(out) == 2
    # Mean of 400, 410, 420, 430, 440; keeping every 5th sample would give 400.
    assert out[0]["speed"] == pytest.approx(420.0)
    assert out[0]["time_tag"] == "2026-10-02 18:00:00"
    assert out[0]["dynamic_pressure"] == pytest.approx(1.6726e-6 * 5.0 * 420.0 ** 2, rel=1e-3)
    assert infer_cadence_seconds(out) == 300.0


def test_fetch_json_falls_back_to_cache_on_http_error(monkeypatch, tmp_path):
    """A 404 page (how the retired SWPC products now answer) must not discard the cached copy."""
    from helios.core import downloader as mod

    monkeypatch.undo()  # remove the conftest offline stub; the network is faked below instead

    class FakeClient:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        async def get(self, url):
            return httpx.Response(404, text="<html>Not Found</html>")

    monkeypatch.setattr(mod.httpx, "AsyncClient", FakeClient)
    dl = DataDownloader(cache_ttl_seconds=0)
    dl.cache_dir = str(tmp_path)
    with open(os.path.join(dl.cache_dir, "feed.json"), "w", encoding="utf-8") as f:
        json.dump([{"cached": True}], f)
    assert asyncio.run(dl.fetch_json("https://example.invalid/x.json", "feed")) == [{"cached": True}]
    assert asyncio.run(dl.fetch_json("https://example.invalid/x.json", "missing")) is None


def test_parse_kp_both_formats_and_goes_channels():
    new_fmt = [{"time_tag": "2026-10-02T12:00:00", "Kp": 0.67}, {"time_tag": "2026-10-02T15:00:00", "Kp": 2.33}]
    assert DataDownloader.parse_kp(new_fmt) == (2.33, "2026-10-02 15:00:00")
    legacy = [["time_tag", "Kp", "a_running"], ["2026-10-02 12:00:00.000", "4.00", "27"]]
    assert DataDownloader.parse_kp(legacy) == (4.0, "2026-10-02 12:00:00")

    xr = [
        {"time_tag": "2026-10-02T18:03:00Z", "flux": 3.1e-7, "energy": "0.1-0.8nm"},
        {"time_tag": "2026-10-02T18:04:00Z", "flux": 6.4e-9, "energy": "0.05-0.4nm"},
        {"time_tag": "2026-10-02T18:04:00Z", "flux": 2.4e-7, "energy": "0.1-0.8nm"},
    ]
    assert DataDownloader.parse_goes_latest(xr, "0.1-0.8nm") == (2.4e-7, "2026-10-02 18:04:00")
    pr = [{"time_tag": "2026-10-02T18:40:00Z", "flux": 0.24, "energy": ">=10 MeV"},
          {"time_tag": "2026-10-02T18:40:00Z", "flux": 16.5, "energy": ">=1 MeV"}]
    assert DataDownloader.parse_goes_latest(pr, ">=10 MeV")[0] == 0.24
