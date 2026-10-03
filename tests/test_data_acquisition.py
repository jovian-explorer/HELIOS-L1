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


def test_telemetry_api_uses_observed_indices_and_reports_provenance(monkeypatch):
    from fastapi.testclient import TestClient
    from helios.api.server import app

    kp_rows = [{"time_tag": "2026-10-02T15:00:00", "Kp": 7.33}]
    xr_rows = [{"time_tag": "2026-10-02T18:04:00Z", "flux": 5.3e-4, "energy": "0.1-0.8nm"}]
    pr_rows = [{"time_tag": "2026-10-02T18:40:00Z", "flux": 150.0, "energy": ">=10 MeV"}]

    async def fake_fetch(self, url, cache_key):
        if "rtsw_mag" in url:
            return MAG
        if "rtsw_wind" in url:
            return WIND
        if "k-index" in url:
            return kp_rows
        if "xrays" in url:
            return xr_rows
        if "protons" in url:
            return pr_rows
        return None

    monkeypatch.setattr(DataDownloader, "fetch_json", fake_fetch)
    data = TestClient(app).get("/api/telemetry/DSCOVR").json()
    assert data["provenance"]["kind"] == "observed"
    cls = data["classification"]
    # Previously: Kp guessed from Bz (3.0 here), X-ray fixed at 1.5e-6, protons fixed at 1.2 pfu.
    assert cls["kp"] == 7.33 and cls["g_level"] == 3 and "Observed" in cls["kp_source"]
    assert cls["flare_class"].startswith("X5.3") and cls["r_level"] == 3
    assert cls["proton_flux_pfu"] == 150.0 and cls["s_level"] == 2
    # "latest" skips trailing partial rows; here the newest row is complete.
    assert data["latest"]["time_tag"] == "2026-10-02 18:02:00"


def test_latest_valid_record_skips_partial_rows():
    from helios.api.server import latest_valid_record
    recs = [{"time_tag": "a", "speed": 400.0, "bz_gsm": -1.0}, {"time_tag": "b", "speed": None, "bz_gsm": -2.0}]
    assert latest_valid_record(recs)["time_tag"] == "a"


def test_export_rejects_unknown_mission():
    from fastapi.testclient import TestClient
    from helios.api.server import app
    client = TestClient(app)
    assert client.get("/api/export/csv?mission_id=NOT_A_MISSION").status_code == 404
    assert client.get("/api/export/csv?mission_id=DSCOVR&span_days=99").status_code == 422


def test_importer_treats_fill_values_and_missing_columns_as_gaps():
    from helios.core.importer import TelemetryImporter
    csv_text = ("time,speed,density,bz_gsm,by_gsm,bt,temperature\n"
                "2024-05-10 12:00:00,412.3,4.8,-1.2,3.4,4.4,9999999.\n"
                "2024-05-10 12:01:00,99999.9,999.99,9999.99,3.0,5.0,85000\n"
                "2024-05-10 12:02:00,420.0,,-2.0,2.0,4.0,90000\n")
    res = TelemetryImporter.parse_csv_or_text(csv_text, "OMNI")
    r0, r1, r2 = res["records"]
    assert r0["temperature"] is None and r1["temperature"] == 85000
    # OMNI fill values used to enter as 99999.9 km/s, 999.99 cm^-3 and 9999.99 nT.
    assert r1["speed"] is None and r1["density"] is None and r1["bz_gsm"] is None
    assert r1["dynamic_pressure"] is None and r1["akasofu_gw"] is None
    # A missing density used to be replaced with 5 cm^-3.
    assert r2["density"] is None and r2["dynamic_pressure"] is None
    assert res["summary"]["speed_max"] == 420.0
    assert any("fill" in w for w in res["warnings"])


def test_importer_without_speed_column_invents_nothing():
    from helios.core.importer import TelemetryImporter
    res = TelemetryImporter.parse_csv_or_text("time,bz\n2024-05-10 12:00:00,-5\n2024-05-10 12:05:00,-6", "MAG only")
    assert all(r["speed"] is None and r["akasofu_gw"] is None for r in res["records"])
    assert res["summary"]["speed_max"] is None


def test_importer_normalises_time_to_utc_and_sorts():
    from helios.core.importer import TelemetryImporter
    csv_text = ("time,speed,density,bz_gsm\n"
                "2024-05-10T18:00:00+05:30,410,5,-1\n"
                "2024-05-10T12:00:00Z,400,5,-1\n"
                "not a time,500,5,-1\n")
    res = TelemetryImporter.parse_csv_or_text(csv_text, "TZ")
    assert [r["time_tag"] for r in res["records"]] == ["2024-05-10 12:00:00", "2024-05-10 12:30:00"]
    assert any("time stamp" in w for w in res["warnings"])


def test_importer_reads_omni_year_doy_columns():
    from helios.core.importer import TelemetryImporter
    text = "YEAR DOY HR MN BZ_GSM flow_speed proton_density\n2024 131 17 5 -30.5 740.5 28.4\n2024 131 17 10 -32.0 760.0 30.1\n"
    res = TelemetryImporter.parse_csv_or_text(text, "OMNI HRO")
    assert res["status"] == "success"
    # Day of year 131 of 2024 (leap year) is 10 May.
    assert res["records"][0]["time_tag"] == "2024-05-10 17:05:00"
    assert res["records"][0]["bz_gsm"] == -30.5 and res["records"][0]["speed"] == 740.5


def test_csv_export_handles_mixed_keys_and_carries_metadata():
    import io
    import pandas as pd
    from fastapi.testclient import TestClient
    from helios.api.server import app
    from helios.core.exporter import DataExporter

    # Records with different key sets used to raise ValueError in csv.DictWriter.
    out = DataExporter.to_csv([{"time_tag": "a", "speed": 400.0}, {"time_tag": "b", "speed": None, "hp_mag": 90.0}])
    assert out.splitlines()[0] == "time_tag,speed,hp_mag"

    text = TestClient(app).get("/api/export/csv?mission_id=DSCOVR").text
    assert text.startswith("# title:")
    assert "# data_kind: synthetic" in text  # offline test run
    assert "speed=km/s" in text
    df = pd.read_csv(io.StringIO(text), comment="#")
    assert "data_source" in df.columns and len(df) > 0
    plain = TestClient(app).get("/api/export/csv?mission_id=DSCOVR&metadata=false").text
    assert plain.startswith("time_tag,")


def test_netcdf_schema_units():
    from helios.core.exporter import DataExporter
    schema = DataExporter.to_netcdf_schema(
        [{"time_tag": "a", "temperature": 1e5, "magnetopause_re": 10.0, "akasofu_gw": 50.0, "bz_gsm": -2.0}], "X")
    units = {k: v["units"] for k, v in schema["variables"].items()}
    assert units == {"temperature": "K", "magnetopause_re": "R_E", "akasofu_gw": "GW", "bz_gsm": "nT"}


def test_compare_and_matrix_expose_provenance(monkeypatch):
    from fastapi.testclient import TestClient
    from helios.api.server import app

    async def fake_fetch(self, url, cache_key):
        return MAG if "rtsw_mag" in url else (WIND if "rtsw_wind" in url else None)

    monkeypatch.setattr(DataDownloader, "fetch_json", fake_fetch)
    client = TestClient(app)
    comp = client.get("/api/compare?mission_a=ACE&mission_b=WIND&parameter=bz_gsm").json()
    assert comp["provenance_a"]["kind"] == "observed"
    assert comp["provenance_b"]["kind"] == "simulated"
    matrix = client.get("/api/compare/matrix?parameter=bz_gsm").json()
    assert matrix["provenance"] == {"DSCOVR": "observed", "ACE": "observed", "ADITYA_L1": "simulated",
                                    "WIND": "simulated", "SOHO": "simulated"}
