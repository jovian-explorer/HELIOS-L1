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

# The server only answers requests addressed to a loopback host (helios.api.guard).
LOCAL = "http://127.0.0.1:8765"


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
    assert out[0]["dynamic_pressure"] == pytest.approx(2.0e-6 * 5.0 * 420.0 ** 2, rel=1e-3)
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
    data = TestClient(app, base_url=LOCAL).get("/api/telemetry/DSCOVR").json()
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
    client = TestClient(app, base_url=LOCAL)
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


def test_importer_reads_year_month_day_columns():
    """With a month column, DAY is the day of the month (it was read as day of year: 10 January)."""
    from helios.core.importer import TelemetryImporter
    text = "year,month,day,hour,minute,bz_gsm\n2024,5,10,17,5,-30.5\n2024,5,10,17,10,-32.0\n"
    res = TelemetryImporter.parse_csv_or_text(text, "custom")
    assert [r["time_tag"] for r in res["records"]] == ["2024-05-10 17:05:00", "2024-05-10 17:10:00"]


def test_csv_export_handles_mixed_keys_and_carries_metadata():
    import io
    import pandas as pd
    from fastapi.testclient import TestClient
    from helios.api.server import app
    from helios.core.exporter import DataExporter

    # Records with different key sets used to raise ValueError in csv.DictWriter.
    out = DataExporter.to_csv([{"time_tag": "a", "speed": 400.0}, {"time_tag": "b", "speed": None, "hp_mag": 90.0}])
    assert out.splitlines()[0] == "time_tag,speed,hp_mag"

    text = TestClient(app, base_url=LOCAL).get("/api/export/csv?mission_id=DSCOVR").text
    assert text.startswith("# title:")
    assert "# data_kind: synthetic" in text  # offline test run
    assert "speed=km/s" in text
    df = pd.read_csv(io.StringIO(text), comment="#")
    assert "data_source" in df.columns and len(df) > 0
    plain = TestClient(app, base_url=LOCAL).get("/api/export/csv?mission_id=DSCOVR&metadata=false").text
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
    client = TestClient(app, base_url=LOCAL)
    comp = client.get("/api/compare?mission_a=ACE&mission_b=WIND&parameter=bz_gsm").json()
    assert comp["provenance_a"]["kind"] == "observed"
    assert comp["provenance_b"]["kind"] == "simulated"
    matrix = client.get("/api/compare/matrix?parameter=bz_gsm").json()
    assert matrix["provenance"] == {"DSCOVR": "observed", "ACE": "observed", "ADITYA_L1": "simulated",
                                    "WIND": "simulated", "SOHO": "simulated"}


# Rows from the NOAA RTSW hourly ephemeris feed (json/rtsw/rtsw_ephemerides_1h.json), GSE km.
EPHEMERIS = [
    {"time_tag": "2026-10-03T09:00:00", "active": True, "source": "SOLAR1", "x_gse": 1582227, "y_gse": -23859, "z_gse": 128782},
    {"time_tag": "2026-10-03T08:00:00", "active": True, "source": "SOLAR1", "x_gse": 1582205, "y_gse": -23406, "z_gse": 128943},
    {"time_tag": "2026-10-03T09:00:00", "active": False, "source": "ACE", "x_gse": 1409538, "y_gse": -31890, "z_gse": 6378},
]


def test_rtsw_ephemeris_latest_position():
    pos = DataDownloader.parse_rtsw_ephemeris(EPHEMERIS, "solar1")
    assert (pos["x_km"], pos["z_km"], pos["time_tag"]) == (1582227, 128782, "2026-10-03 09:00:00")
    assert DataDownloader.parse_rtsw_ephemeris(EPHEMERIS, "IMAP") is None


def test_compare_baseline_uses_supplying_spacecraft_position(monkeypatch):
    """The operational stream comes from SOLAR1: the baseline must use SOLAR1's position, not DSCOVR's model orbit."""
    from fastapi.testclient import TestClient
    from helios.api.server import app

    # Enough overlapping 1-minute rows for a comparison.
    mag = [_mag(f"2026-10-02T17:{m:02d}:00", s, s == "SOLAR1", -2.0 - 0.1 * m + 0.05 * (m % 3))
           for m in range(30) for s in ("SOLAR1", "ACE")]
    wind = [_wind(f"2026-10-02T17:{m:02d}:00", s, s == "SOLAR1", 400.0) for m in range(30) for s in ("SOLAR1", "ACE")]

    async def fake_fetch(self, url, cache_key):
        if "ephemerides" in url:
            return EPHEMERIS
        return mag if "rtsw_mag" in url else wind

    monkeypatch.setattr(DataDownloader, "fetch_json", fake_fetch)
    comp = TestClient(app, base_url=LOCAL).get("/api/compare?mission_a=DSCOVR&mission_b=ACE&parameter=bz_gsm").json()
    base = comp["spatial_baseline"]
    assert "SOLAR1" in base["position_source_a"] and "ACE" in base["position_source_b"]
    # SOLAR1 is 172,689 km further sunward than ACE: dx < 0 and the plasma reaches it first.
    assert base["dx_km"] == pytest.approx(-(1582227 - 1409538), abs=1)
    assert base["theoretical_delay_min"] == pytest.approx((1582227 - 1409538) / 400.0 / 60.0, abs=0.2)


def test_downloads_share_one_tls_context_and_cache_raw_bytes(tmp_path):
    """Per-request TLS contexts (~0.35 s each) and re-encoding big JSON blocked the event loop."""
    from helios.core import downloader as dl
    assert dl._ssl_context() is dl._ssl_context()
    body = b'[["time_tag","bz"],["2026-10-01 00:00:00.000","-3.1"]]'
    path = str(tmp_path / "x.json")
    assert dl._decode_and_store(body, path) == [["time_tag", "bz"], ["2026-10-01 00:00:00.000", "-3.1"]]
    assert open(path, "rb").read() == body


def test_solar_regions_use_latest_noaa_summary(monkeypatch):
    """The active region scanner showed a fixed 2024 catalogue with invented flare probabilities."""
    from fastapi.testclient import TestClient
    from helios.api import server
    rows = [
        {"observed_date": "2026-10-02", "region": 4547, "latitude": 15, "longitude": -10, "location": "N15W10",
         "area": 20, "spot_class": "Cro", "mag_class": "B", "number_spots": 3, "c_xray_events": 1,
         "m_xray_events": 0, "x_xray_events": 0, "c_flare_probability": 10, "m_flare_probability": 1,
         "x_flare_probability": 1, "proton_probability": 1, "carrington_longitude": 100, "first_date": "2026-09-28T00:00:00"},
        {"observed_date": "2026-10-03", "region": 4548, "latitude": -11, "longitude": 64, "location": "S11E64",
         "area": 30, "spot_class": "Hsx", "mag_class": "A", "number_spots": 1, "c_xray_events": 0,
         "m_xray_events": 0, "x_xray_events": 0, "c_flare_probability": 5, "m_flare_probability": 1,
         "x_flare_probability": 1, "proton_probability": 1, "carrington_longitude": 60, "first_date": "2026-10-02T00:00:00"},
    ]

    async def fake(self, url, cache_key):
        return rows if cache_key == "solar_regions" else None
    from helios.core.downloader import DataDownloader
    monkeypatch.setattr(DataDownloader, "fetch_json", fake)
    body = TestClient(server.app, base_url=LOCAL).get("/api/solar/regions").json()
    assert body["observed_date"] == "2026-10-03" and body["kind"] == "observed"
    assert [r["region"] for r in body["regions"]] == [4548]
    r = body["regions"][0]
    assert r["longitude_east"] == 64.0 and r["flare_probability_pct"] == {"C": 5, "M": 1, "X": 1}


def test_solar_regions_offline_is_unavailable():
    from fastapi.testclient import TestClient
    from helios.api import server
    body = TestClient(server.app, base_url=LOCAL).get("/api/solar/regions").json()
    assert body["kind"] == "unavailable" and body["regions"] == []


def test_import_presets_are_labelled_illustrative():
    """The preset tables are hand-written, but were labelled 'DSCOVR / NASA OMNI-HRO', 'ACE SWEPAM / MAG'..."""
    from helios.core.importer import TelemetryImporter
    for p in TelemetryImporter.get_presets_list():
        assert p["data_kind"] == "synthetic" and p["satellite"].startswith("Illustrative profile")
        assert "not measured" in p["note"] or "no in-situ" in p["note"]


def test_custom_csv_export_has_metadata_and_plot_states_provenance(monkeypatch):
    from fastapi.testclient import TestClient
    from helios.api import server
    from helios.core.exporter import DataExporter
    client = TestClient(server.app, base_url=LOCAL)
    csv_text = "time,speed,bz\n2024-05-10 00:00:00,400,-3\n2024-05-10 00:01:00,410,-4\n"
    assert client.post("/api/custom/import", json={"content": csv_text, "mission_name": "Test"}).status_code == 200
    out = client.get("/api/custom/export/csv").text
    assert out.startswith("# title: HELIOS-L1 imported telemetry: Test") and "# data_kind: imported" in out
    seen = {}

    def chart(records, name, provenance=None):
        seen["provenance"] = provenance
        return b"png"
    monkeypatch.setattr(DataExporter, "generate_overview_chart", staticmethod(chart))
    assert client.get("/api/export/plot?mission_id=ADITYA_L1").status_code == 200
    assert seen["provenance"]["kind"] in ("simulated", "synthetic")


def test_unexpected_errors_answer_json(monkeypatch):
    from fastapi.testclient import TestClient
    from helios.api import server

    def boom(*a, **k):
        raise RuntimeError("solver diverged")
    monkeypatch.setattr(server.SolarCycleEngine, "calculate_cycle_25_progression", boom)
    r = TestClient(server.app, base_url=LOCAL, raise_server_exceptions=False).get("/api/solar_cycle")
    assert r.status_code == 500
    assert r.json()["detail"] == "Internal error in /api/solar_cycle: RuntimeError: solver diverged"


def test_solar_cycle_uses_noaa_observed_indices(monkeypatch):
    """The tab showed a sin^2/exp curve labelled as Hathaway's model and as the current sunspot number."""
    from fastapi.testclient import TestClient
    from helios.api import server
    from helios.core.downloader import DataDownloader
    obs = [{"time-tag": "2008-12", "ssn": 1.7, "smoothed_ssn": 2.2, "f10.7": 69.0, "smoothed_f10.7": 69.5},
           {"time-tag": "2019-12", "ssn": 1.5, "smoothed_ssn": 1.8, "f10.7": 70.9, "smoothed_f10.7": 71.0},
           {"time-tag": "2021-12", "ssn": 67.6, "smoothed_ssn": 59.0, "f10.7": 102.0, "smoothed_f10.7": 95.0},
           {"time-tag": "2024-10", "ssn": 166.3, "smoothed_ssn": 160.9, "f10.7": 210.0, "smoothed_f10.7": 200.0},
           {"time-tag": "2025-12", "ssn": 110.0, "smoothed_ssn": 120.0, "f10.7": 150.0, "smoothed_f10.7": 145.0},
           {"time-tag": "2026-09", "ssn": 60.3, "smoothed_ssn": -1.0, "f10.7": 105.4, "smoothed_f10.7": -1.0}]
    pred = [{"time-tag": "2026-10", "predicted_ssn": 80.0, "low_ssn": 70.0, "high_ssn": 90.0}]

    async def fake(self, url, cache_key):
        return {"solar_cycle_observed": obs, "solar_cycle_predicted": pred}.get(cache_key)
    monkeypatch.setattr(DataDownloader, "fetch_json", fake)
    sc = TestClient(server.app, base_url=LOCAL).get("/api/solar_cycle?year=2026.8").json()
    assert sc["data_kind"] == "observed"
    assert sc["monthly_sunspot_number"] == 60.3 and sc["month"] == "2026-09"
    assert sc["smoothed_sunspot_number"] == 120.0 and sc["smoothed_month"] == "2025-12"  # -1 = not yet smoothed
    assert sc["peak_sunspot_number"] == 160.9 and sc["peak_month"] == "2024-10"
    t = {r["year_month"]: r for r in sc["timeline"]}
    assert t["2019-12"]["cycle_24_comparison_ssn"] == 2.2 and t["2026-10"]["ssn_predicted"] == 80.0
    assert sc["current_phase"] == "Declining phase"
    early = TestClient(server.app, base_url=LOCAL).get("/api/solar_cycle?year=2022.5").json()
    assert early["peak_month"] == "2021-12" and early["current_phase"] == "Ascending phase"  # not the 2024 peak


def test_solar_cycle_offline_is_labelled_model():
    from fastapi.testclient import TestClient
    from helios.api import server
    sc = TestClient(server.app, base_url=LOCAL).get("/api/solar_cycle").json()
    assert sc["data_kind"] == "model" and "approximation" in sc["source"]
    assert all(t["cycle_24_comparison_ssn"] is None for t in sc["timeline"])


def test_compare_imported_file_uses_archive_for_its_interval(monkeypatch):
    """An imported file from 2015 against WIND compared with WIND's last 24 h: never any overlap."""
    from datetime import datetime, timezone
    from fastapi.testclient import TestClient
    from helios.api import server

    recs = [{"time_tag": f"2015-03-17 04:{m:02d}:00", "bz_gsm": -5.0 + 0.3 * m + (m % 4) * 0.2, "speed": 450.0}
            for m in range(40)]
    monkeypatch.setattr(server, "latest_custom_dataset", {"mission_name": "my_solar_wind_2015", "records": recs})
    asked = {}

    async def fake_archive(self, mission_id, start, end, cadence_minutes=1):
        asked["args"] = (mission_id, start, end)
        shifted = [dict(r, bz_gsm=r["bz_gsm"] * 1.1) for r in recs]
        return {"records": shifted, "provenance": {"kind": "observed", "description": "CDAWeb"}}

    async def no_live(self, mission_id, span_days=1):
        raise AssertionError("live window requested for a 2015 comparison")

    monkeypatch.setattr(DataDownloader, "get_archive_bundle", fake_archive)
    monkeypatch.setattr(DataDownloader, "get_telemetry_bundle", no_live)
    client = TestClient(server.app, base_url=LOCAL)
    comp = client.get("/api/compare?mission_a=WIND&mission_b=CUSTOM&parameter=bz_gsm").json()
    assert comp["status"] == "success" and comp["provenance_a"]["kind"] == "observed"
    # The file has no position: no baseline (its name containing "wind" made it WIND's orbit, 0 km).
    base = comp["spatial_baseline"]
    assert base["distance_km"] is None and base["theoretical_delay_min"] is None and base["position_unknown"]
    assert asked["args"] == ("WIND", datetime(2015, 3, 17, 4, 0, tzinfo=timezone.utc),
                             datetime(2015, 3, 17, 4, 40, tzinfo=timezone.utc))

    async def empty_archive(self, mission_id, start, end, cadence_minutes=1):
        return {"records": [], "provenance": {"kind": "unavailable", "description": "none"}}

    monkeypatch.setattr(DataDownloader, "get_archive_bundle", empty_archive)
    comp = client.get("/api/compare?mission_a=WIND&mission_b=CUSTOM&parameter=bz_gsm").json()
    assert comp["status"] == "insufficient_data"
    assert "has no values" in comp["message"] and "2015-03-17 04:00:00 to 2015-03-17 04:39:00 UTC" in comp["message"]


def test_old_rtsw_copy_is_cut_to_the_window_and_flagged(monkeypatch):
    """A cached feed from days ago read as current conditions, and a feed longer than the window was kept whole."""
    import asyncio
    from datetime import datetime, timedelta, timezone
    newest = datetime.now(timezone.utc).replace(second=0, microsecond=0) - timedelta(days=2)
    ts = [newest - timedelta(minutes=10 * k) for k in range(300)]  # 50 h of data, newest first
    mag = [_mag(t.strftime("%Y-%m-%dT%H:%M:%S"), "DSCOVR", True, -3.0) for t in ts]
    wind = [_wind(t.strftime("%Y-%m-%dT%H:%M:%S"), "DSCOVR", True, 450.0) for t in ts]

    async def fake_rtsw(self):
        return mag, wind
    monkeypatch.setattr(DataDownloader, "_fetch_rtsw", fake_rtsw)
    out = asyncio.run(DataDownloader().get_telemetry_bundle("DSCOVR", span_days=1))
    recs, prov = out["records"], out["provenance"]
    assert recs[-1]["time_tag"] == newest.strftime("%Y-%m-%d %H:%M:%S")
    assert recs[0]["time_tag"] >= (newest - timedelta(days=1)).strftime("%Y-%m-%d %H:%M:%S")
    assert "not current conditions" in prov["description"] and prov["newest_record_age_hours"] > 47


def test_block_average_keeps_each_bins_spacecraft():
    from helios.core.downloader import block_average
    recs = [{"time_tag": f"2026-10-02 18:0{m}:00", "speed": 400.0, "source_spacecraft": "ACE" if m < 5 else "SOLAR1",
             "data_source": "observed"} for m in range(10)]
    out = block_average(recs, 5)
    assert [r["source_spacecraft"] for r in out] == ["ACE", "SOLAR1"]  # was ACE for both
