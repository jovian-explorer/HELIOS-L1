"""
NASA CDAWeb HAPI archive retrieval. The payloads in tests/data/hapi are small real
responses recorded from https://cdaweb.gsfc.nasa.gov/hapi (include=header), so the
parsing, fill-value handling, quality flags, dataset fallback, caching and provenance
are tested offline against the exact server format.
"""
import asyncio
import os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import pytest

from helios.core.archive import ArchiveClient, HapiError, parse_hapi_csv, ARCHIVE_SOURCES
from helios.core.ncei import NCEI_BUCKET, f1m_frame, read_netcdf3
from helios.core.coordinates import gse_to_gsm
from helios.core.downloader import DataDownloader

# The server only answers requests addressed to a loopback host (helios.api.guard).
LOCAL = "http://127.0.0.1:8765"

DATA = Path(__file__).parent / "data" / "hapi"

# dataset id -> (UTC day served, recorded file)
RECORDED = {
    "OMNI_HRO_1MIN": ("2024-05-10", "omni_hro_1min_20240510.csv"),
    "WI_H0_MFI@0": ("2024-05-10", "wi_h0_mfi_20240510.csv"),
    "WI_H1_SWE": ("2024-05-20", "wi_h1_swe_20240520.csv"),
    "WI_K0_SWE": ("2024-05-20", "wi_k0_swe_20240520.csv"),
    "DSCOVR_H0_MAG": ("2018-05-10", "dscovr_h0_mag_20180510.csv"),
}
NO_DATA = (DATA / "wi_h1_swe_nodata.csv").read_text()
# NOAA NCEI DSCOVR f1m file of 19 Jan 2026 and its S3 listing, recorded from archive.data.noaa.gov.
NCEI_F1M = DATA.parent / "ncei" / "oe_f1m_dscovr_s20260119000000_e20260119235959_p20260120020420_pub.nc.gz"
NCEI_LISTING = (DATA.parent / "ncei" / "listing_20260119.xml").read_text()


def _utc(s):
    return datetime.fromisoformat(s).replace(tzinfo=timezone.utc)


def _downloader(tmp_path, served=RECORDED, log=None):
    """DataDownloader whose HAPI requests are answered from the recorded files (no-data otherwise)."""
    dl = DataDownloader()

    async def fake_text(url, timeout=120.0):
        if url.startswith(NCEI_BUCKET):  # NCEI S3 listing: the recorded day, nothing otherwise
            day = parse_qs(urlparse(url).query)["prefix"][0][-8:]
            if log is not None:
                log.append(("NCEI_DSCOVR_F1M", day))
            return NCEI_LISTING if day == "20260119" else "<ListBucketResult></ListBucketResult>"
        q = parse_qs(urlparse(url).query)
        ds, day = q["id"][0], q["time.min"][0][:10]
        if log is not None:
            log.append((ds, day))
        if ds in served and served[ds][0] == day:
            return (DATA / served[ds][1]).read_text()
        return NO_DATA

    async def fake_bytes(url, timeout=120.0):
        return NCEI_F1M.read_bytes() if url.endswith(NCEI_F1M.name) else None

    dl.fetch_text = fake_text
    dl.archive = ArchiveClient(lambda url: dl.fetch_text(url), tmp_path, fake_bytes)
    return dl


def test_parse_hapi_csv_applies_declared_fill_values():
    df = parse_hapi_csv((DATA / "omni_hro_1min_20240510.csv").read_text())
    assert len(df) == 6 and str(df.index.tz) == "UTC"
    # 17:00 has OMNI plasma fills 99999.9 km/s, 999.99 cm^-3, 9999999. K.
    first = df.iloc[0]
    assert np.isnan(first["flow_speed"]) and np.isnan(first["proton_density"]) and np.isnan(first["T"])
    assert first["BZ_GSM"] == pytest.approx(3.70)
    assert df.iloc[-1]["flow_speed"] == pytest.approx(713.7)


def test_parse_hapi_csv_vectors_no_data_and_errors():
    df = parse_hapi_csv((DATA / "wi_h0_mfi_20240510.csv").read_text())
    assert {"BGSM_0", "BGSM_1", "BGSM_2", "BGSE_2"} <= set(df.columns)
    assert df.iloc[0]["BGSM_2"] == pytest.approx(-11.75159)
    assert parse_hapi_csv(NO_DATA).empty
    with pytest.raises(HapiError):
        parse_hapi_csv('{\n"HAPI": "2.0",\n"status": {"code": 1406, "message": "Bad request - unknown dataset id"}}')


def test_wind_swe_quality_flags_and_thermal_speed():
    h1 = parse_hapi_csv((DATA / "wi_h1_swe_20240520.csv").read_text())
    reduced = ARCHIVE_SOURCES["WIND"]["groups"][1][0]["reduce"](h1)
    # fit_flag = 1 (proton fit not OK) at 17:04:16 is dropped.
    assert len(h1) == 4 and len(reduced) == 3

    text = (DATA / "wi_k0_swe_20240520.csv").read_text().replace("4098,4098", "35,35")
    k0 = ARCHIVE_SOURCES["WIND"]["groups"][1][1]["reduce"](parse_hapi_csv(text))
    # QF 14338 = 0x3802: low byte 2 ("caution") is usable; 35 is not valid.
    assert k0["speed"].notna().tolist() == [True, True, False]
    assert k0["speed"].iloc[0] == pytest.approx(np.sqrt(352.3 ** 2 + 8.9 ** 2 + 21.2 ** 2))
    # W = sqrt(2kT/m_p): 28.7 km/s -> 4.99e4 K.
    assert k0["temperature"].iloc[0] == pytest.approx(49_890, rel=1e-3)


def test_omni_bundle_records_provenance_and_cache(tmp_path):
    dl = _downloader(tmp_path)
    b = asyncio.run(dl.get_archive_bundle("OMNI", _utc("2024-05-10 17:00"), _utc("2024-05-10 17:06")))
    recs, prov = b["records"], b["provenance"]
    assert [r["time_tag"][11:16] for r in recs] == ["17:00", "17:01", "17:02", "17:03", "17:04", "17:05"]
    assert recs[0]["speed"] is None and recs[0]["dynamic_pressure"] is None and recs[0]["bz_gsm"] == 3.70
    assert recs[5]["speed"] == 713.7 and recs[5]["bx_gsm"] == -2.54 and recs[5]["bz_gse"] == -13.47
    # OMNI is already propagated to the bow shock: no L1 travel time.
    assert recs[5]["l1_travel_time_min"] is None and recs[5]["dynamic_pressure"] is not None
    assert all(r["data_source"] == "observed" for r in recs)
    assert prov["kind"] == "observed" and prov["datasets"][0]["id"] == "OMNI_HRO_1MIN"
    assert "bow shock" in prov["description"]

    # The day ended long ago and has data: served from the cache with the network gone.
    async def offline(url, timeout=120.0):
        return None
    dl.fetch_text = offline
    again = asyncio.run(dl.get_archive_bundle("OMNI", _utc("2024-05-10 17:00"), _utc("2024-05-10 17:06")))
    assert again["records"] == recs


def test_dscovr_one_second_mag_is_averaged_and_rotated_to_gsm(tmp_path):
    dl = _downloader(tmp_path)
    b = asyncio.run(dl.get_archive_bundle("DSCOVR", _utc("2018-05-10 16:00"), _utc("2018-05-10 18:00")))
    (rec,) = b["records"]
    raw = parse_hapi_csv((DATA / "dscovr_h0_mag_20180510.csv").read_text())
    by, bz = raw["B1GSE_1"].mean(), raw["B1GSE_2"].mean()
    _, gy, gz = gse_to_gsm([raw.index[0]], raw["B1GSE_0"].mean(), by, bz)
    assert rec["time_tag"] == "2018-05-10 16:57:00"
    assert rec["bz_gse"] == pytest.approx(bz, abs=0.006)
    assert rec["by_gsm"] == pytest.approx(gy[0], abs=0.02) and rec["bz_gsm"] == pytest.approx(gz[0], abs=0.02)
    assert rec["speed"] is None  # the Faraday cup archive has no data here
    assert "rotated from GSE" in b["provenance"]["description"]


def test_wind_falls_back_to_key_parameters_and_labels_them(tmp_path):
    log = []
    served = {"WI_K0_SWE": RECORDED["WI_K0_SWE"]}  # no definitive SWE and no MFI for this interval
    dl = _downloader(tmp_path, served, log)
    b = asyncio.run(dl.get_archive_bundle("WIND", _utc("2024-05-20 17:00"), _utc("2024-05-20 17:06")))
    ids = [d["id"] for d in b["provenance"]["datasets"]]
    assert ids == ["WI_K0_SWE"]
    assert "preliminary" in b["provenance"]["description"]
    assert ("WI_H1_SWE", "2024-05-20") in log  # the definitive dataset was tried first
    assert [r["speed"] is not None for r in b["records"]] == [True, True, True]


def test_archive_unreachable_and_empty_are_reported(tmp_path):
    dl = _downloader(tmp_path, served={})
    empty = asyncio.run(dl.get_archive_bundle("ACE", _utc("2024-05-20 00:00"), _utc("2024-05-20 06:00")))
    assert empty["records"] == [] and empty["provenance"]["kind"] == "unavailable"
    assert "no ACE data" in empty["provenance"]["description"]

    dl2 = DataDownloader()  # conftest: no network
    dl2.archive = ArchiveClient(lambda url: dl2.fetch_text(url), tmp_path / "other")
    off = asyncio.run(dl2.get_archive_bundle("ACE", _utc("2024-05-20 00:00"), _utc("2024-05-20 06:00")))
    assert off["provenance"]["kind"] == "unavailable" and "could not be reached" in off["provenance"]["description"]


def test_wind_view_without_archive_data_is_empty(tmp_path):
    """It was the operational stream with invented offsets (+1.1 km/s) and noise, labelled simulated."""
    dl = DataDownloader()
    dl.archive = ArchiveClient(lambda url: dl.fetch_text(url), tmp_path)
    b = asyncio.run(dl.get_telemetry_bundle("WIND", 1))
    assert b["provenance"]["kind"] == "unavailable" and b["records"] == []
    assert "could not be reached" in b["provenance"]["description"]


def test_historical_event_uses_real_omni_data(tmp_path):
    dl = _downloader(tmp_path)
    ev = asyncio.run(dl.get_historical_event("may_2024_g5"))
    assert ev["provenance"]["kind"] == "observed" and ev["satellite"] == "OMNI"
    assert [r["time_tag"] for r in ev["telemetry"]] == ["2024-05-10 17:00:00", "2024-05-10 17:05:00"]
    assert ev["metadata"]["observed_5min"]["peak_speed"] == 713.7

    offline = DataDownloader()
    offline.archive = ArchiveClient(lambda url: offline.fetch_text(url), tmp_path / "off")
    ev2 = asyncio.run(offline.get_historical_event("may_2024_g5"))
    assert ev2["provenance"]["kind"] == "observed" and "bundled" in ev2["provenance"]["description"]


def test_offline_events_are_the_bundled_omni_data(tmp_path):
    """Offline, the events are the OMNI 5-min data bundled with the app (they were hand-made
    profiles that overshot their own peaks, 1469 km/s and 153 nPa for May 2024, with no shock):
    May 2024 OMNI extremes -44.3 nT / 1023 km/s and the shock in the 10 May 17:00 UT bin; the Halloween
    window reaches the Dst minimum of 30 Oct (SYM-H below -383 nT) and states its plasma gap;
    Carrington has no time series."""
    dl = DataDownloader()  # conftest: no network
    dl.archive = ArchiveClient(lambda url: dl.fetch_text(url), tmp_path)
    may = asyncio.run(dl.get_historical_event("may_2024_g5"))
    obs = may["metadata"]["observed_5min"]
    assert obs["min_bz"] == -44.3 and round(obs["peak_speed"]) == 1023
    assert may["shocks"][0]["time"] == "2024-05-10 17:00:00"
    hal = asyncio.run(dl.get_historical_event("halloween_2003"))
    assert hal["metadata"]["observed_5min"]["min_sym_h"] < -383
    assert "Solar wind plasma: 35.0 % covered" in hal["provenance"]["description"]
    car = asyncio.run(dl.get_historical_event("carrington_1859"))
    assert car["telemetry"] == [] and car["provenance"]["kind"] == "none"


def test_archive_api_endpoint(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from helios.api import server

    dl = _downloader(tmp_path)
    monkeypatch.setattr(server, "downloader", dl)
    client = TestClient(server.app, base_url=LOCAL)
    r = client.get("/api/archive/omni?start=2024-05-10T17:00Z&end=2024-05-10T17:06")
    assert r.status_code == 200
    body = r.json()
    assert body["data_points"] == 6 and body["provenance"]["kind"] == "observed"
    assert body["latest"]["time_tag"] == "2024-05-10 17:05:00"
    cov = body["provenance"]["coverage"]["groups"]
    assert cov["magnetic field"]["samples"] == 6 and cov["magnetic field"]["covered_fraction"] == 1.0
    assert set(cov) == {"magnetic field", "plasma", "SYM-H"}
    csv_text = client.get("/api/archive/OMNI?start=2024-05-10T17:00&end=2024-05-10T17:06&format=csv").text
    assert "# datasets: OMNI_HRO_1MIN" in csv_text and "713.7" in csv_text
    assert "# coverage_magnetic_field: 100.0 % covered" in csv_text
    assert client.get("/api/archive/GOES_19?start=2024-05-10&end=2024-05-11").status_code == 404
    assert client.get("/api/archive/OMNI?start=2024-05-10&end=2024-05-09").status_code == 422
    assert client.get("/api/archive/OMNI?start=2024-01-01&end=2024-03-01").status_code == 422
    assert client.get("/api/archive/OMNI?start=yesterday&end=2024-03-01").status_code == 422
    assert "WIND" in client.get("/api/archive").json()["missions"]


def test_processors_setting_sizes_the_worker_pool():
    import threading
    from helios import config

    before = config.ACTIVE_PROCESSOR_CORES
    try:
        config.update_system_settings(processors=2)
        assert config.get_worker_pool()._max_workers == 2
        name = asyncio.run(config.run_in_workers(lambda: threading.current_thread().name))
        assert name.startswith("helios-worker")
        config.update_system_settings(processors=3)
        assert config.get_worker_pool()._max_workers == 3
    finally:
        config.update_system_settings(processors=before)


def test_omni_geomagnetic_indices_and_storm_endpoint(monkeypatch, tmp_path):
    """OMNI_HRO_1MIN SYM-H, ASY-H, AE, AL, AU reach the records and /api/storm/indices."""
    from fastapi.testclient import TestClient
    from helios.api import server
    from helios.core.archive import ArchiveClient

    dl = _downloader(tmp_path)
    b = asyncio.run(dl.get_archive_bundle("OMNI", _utc("2024-05-10 17:00"), _utc("2024-05-10 17:06")))
    first, last = b["records"][0], b["records"][5]
    assert (first["ae"], first["al"], first["au"], first["sym_h"], first["asy_h"]) == (124.0, -65.0, 59.0, 15.0, 15.0)
    assert (last["sym_h"], last["asy_h"]) == (10.0, 12.0)
    # Adding parameters to a dataset changes its cache key, so day files cached without
    # them are not served for good.
    spec = ARCHIVE_SOURCES["OMNI"]["groups"][0][0]
    client_a = ArchiveClient(lambda u: None, tmp_path)
    p_full = client_a._cache_path(spec, _utc("2024-05-10"))
    p_less = client_a._cache_path(dict(spec, parameters=spec["parameters"][:9]), _utc("2024-05-10"))
    assert p_full != p_less

    monkeypatch.setattr(server, "downloader", dl)
    body = TestClient(server.app, base_url=LOCAL).get("/api/storm/indices?start=2024-05-10T17:00&end=2024-05-10T17:06&cadence_minutes=1").json()
    assert body["indices"]["sym_h"] == [15.0, 13.0, 11.0, 12.0, 11.0, 10.0]
    cmp = body["dst_comparison"]
    assert cmp["observed_index"] == "SYM-H" and cmp["models"]["obrien"]["series"][0] == 15.0
    assert cmp["models"]["burton"]["skill"]["n"] == 6


def test_hapi_sample_before_the_day_does_not_duplicate_a_minute(tmp_path):
    # Real case: the WIND SWE response for 17 March 1997 starts with a spectrum at 16 March
    # 23:58, so that minute appeared in two day files, and merging the field and plasma
    # groups for any interval containing both days failed (pandas InvalidIndexError, a 500).
    header = "".join(l for l in (DATA / "wi_h1_swe_20240520.csv").read_text().splitlines(True) if l.startswith("#"))
    stray = header + "2024-05-20T17:02:10.000Z,2,3.60e+02,3.00e+01,9.99e+00\n"
    served = {"WI_H1_SWE": ("2024-05-20", "wi_h1_swe_20240520.csv")}
    dl = _downloader(tmp_path, served)
    base = dl.fetch_text

    async def text(url, timeout=120.0):
        if "time.min=2024-05-21" in url:
            return stray
        return await base(url, timeout)

    dl.fetch_text = text
    spec = ARCHIVE_SOURCES["WIND"]["groups"][1][0]
    df, failed = asyncio.run(dl.archive.fetch_dataset(spec, _utc("2024-05-20T00:00"), _utc("2024-05-22T00:00")))
    assert failed == 0 and df.index.is_unique
    assert df.loc[df.index == "2024-05-20 17:02:00+00:00", "density"].tolist() == [pytest.approx(4.03)]  # day 1 value


def test_day_file_is_kept_for_good_only_if_written_after_the_day_was_complete(tmp_path):
    path = tmp_path / "day.json"
    path.write_text("{}")
    day = _utc("2024-05-10")
    early = _utc("2024-05-11T06:00").timestamp()  # fetched while the day was still being filled
    os.utime(path, (early, early))
    assert not ArchiveClient._cache_is_fresh(str(path), day, True)
    late = _utc("2024-05-20").timestamp()
    os.utime(path, (late, late))
    assert ArchiveClient._cache_is_fresh(str(path), day, True)


def test_day_cache_key_changes_with_the_processing_version(tmp_path, monkeypatch):
    from helios.core import archive
    client = ArchiveClient(None, tmp_path)
    spec, day = ARCHIVE_SOURCES["WIND"]["groups"][0][0], _utc("2024-05-10")
    before = client._cache_path(spec, day)
    monkeypatch.setattr(archive, "DAY_CACHE_VERSION", archive.DAY_CACHE_VERSION + 1)
    assert client._cache_path(spec, day) != before


def test_unknown_event_id_is_404_not_another_event():
    from fastapi.testclient import TestClient
    from helios.api import server
    r = TestClient(server.app, base_url=LOCAL).get("/api/events/may_2042_g9")
    assert r.status_code == 404 and "Unknown event" in r.json()["detail"]


def test_soho_and_stereo_a_archive_sources():
    """CDAWeb SOHO_CELIAS-PM_5MIN (speed, density) and STA_L2_MAGPLASMA_1M (|B| and plasma; the
    field vector is RTN, so no GSE/GSM components), checked against CDAWeb on 16 Oct 2026."""
    import pandas as pd
    from helios.core.archive import ARCHIVE_SOURCES
    soho = ARCHIVE_SOURCES["SOHO"]["groups"][0][0]
    sta = ARCHIVE_SOURCES["STEREO_A"]["groups"][0][0]
    assert soho["id"] == "SOHO_CELIAS-PM_5MIN" and sta["id"] == "STA_L2_MAGPLASMA_1M"
    idx = pd.to_datetime(["2023-04-23 01:00"], utc=True)
    out = sta["reduce"](pd.DataFrame({"BTOTAL": [12.4], "Np": [9.1], "Vp": [450.0], "Tp": [7.4e4]}, index=idx))
    assert list(out.columns) == ["bt", "speed", "density", "temperature"]
    out = soho["reduce"](pd.DataFrame({"V_p": [455.0], "N_p": [7.0]}, index=idx))
    assert list(out.columns) == ["speed", "density"]


def test_ncei_dscovr_f1m_netcdf_and_noaa_quality_flags():
    """NOAA's f1m file (netCDF-3, read without a netCDF library): 1440 minutes, 293 kept. NOAA's
    reduced-quality flag and isolated good minutes drop the sheath of 19 Jan 2026, where the unflagged
    speeds read about 400-500 km/s against WIND's 1000-1150 km/s."""
    import gzip
    raw = read_netcdf3(gzip.decompress(NCEI_F1M.read_bytes()))
    assert raw["proton_speed"][0].shape == (1440,) and raw["time"][1]["units"].startswith("milliseconds since 1970")
    f = f1m_frame(NCEI_F1M.read_bytes())
    assert len(f) == 1440 and f["speed"].notna().sum() == 293
    shock = f.loc["2026-01-19 18:57":"2026-01-19 18:58"]
    assert shock["speed"].tolist() == pytest.approx([500.3, 539.5], abs=0.05)
    assert shock["density"].tolist() == pytest.approx([9.43, 21.06], abs=0.005)
    # 19:02 has overall_quality 2, 19:05 (389 km/s) the reduced-quality flag; WIND: 1020 km/s at 19:06.
    assert f.loc["2026-01-19 19:00":"2026-01-19 20:00", "speed"].isna().all()
    assert raw["overall_quality"][0][19 * 60 + 2] == 2 and raw["reduced_proton_quality_flag"][0][19 * 60 + 5] == 1
    assert f1m_frame(b"").empty
    with pytest.raises(ValueError):
        read_netcdf3(b"HDF5....")


def test_dscovr_plasma_after_2019_comes_from_ncei(tmp_path):
    """CDAWeb's DSCOVR_H1_FC has no data in 2026: the NCEI f1m dataset fills the plasma group."""
    log = []
    dl = _downloader(tmp_path, log=log)
    res = asyncio.run(dl.archive.fetch_mission("DSCOVR", _utc("2026-01-19 18:50"), _utc("2026-01-19 19:10")))
    ids = [d["id"] for d in res["datasets"]]
    assert ids == ["NCEI_DSCOVR_F1M"] and "NCEI" in res["datasets"][0]["label"]
    assert ("DSCOVR_H1_FC", "2026-01-19") in log and ("NCEI_DSCOVR_F1M", "20260119") in log
    assert res["frame"].loc["2026-01-19 18:58", "speed"] == pytest.approx(539.5)
    b = asyncio.run(dl.get_archive_bundle("DSCOVR", _utc("2026-01-19 18:50"), _utc("2026-01-19 19:10")))
    assert "NOAA NCEI" in b["provenance"]["description"]
    # Another day: NCEI lists no file -> empty, not unreachable.
    res = asyncio.run(dl.archive.fetch_mission("DSCOVR", _utc("2026-08-01"), _utc("2026-08-02")))
    assert res["frame"].empty and not res["offline"]


def test_psp_span_i_moments_without_counts_or_flagged_are_missing():
    """PSP SPAN-I L3 partial moments (CDAWeb, recorded 19 Oct 2026). With no counts in the partial field of
    view the file gives DENS = 0.0 (not a fill value) with velocity and temperature NaN: 75 of 386 samples on
    1 Dec 2020 and 485 of 551 on 19 Jan 2026. Those, the samples whose QUALITY_FLAG marks a bad measurement
    (counter overflow, spoiler test, over-deflection, bad energy table, MCP test) and non-positive temperatures
    (1-count moments) must be missing, not 0, in the archive and in Event Analysis."""
    import gzip
    import pandas as pd
    from helios.core.event_analysis import EVENT_SOURCES
    raw = parse_hapi_csv(gzip.decompress((DATA / "events" / "psp_spi_20201201_20260119.csv.gz").read_bytes()).decode())
    no_counts = raw["CNTS"] == 0
    assert no_counts.sum() == 399 and (raw.loc[no_counts, "DENS"] == 0).all()
    spec = ARCHIVE_SOURCES["PSP"]["groups"][1][0]
    out = spec["reduce"](raw)
    assert out.loc[no_counts].isna().all().all()
    assert (out["density"].dropna() > 0).all() and (out["temperature"].dropna() > 0).all()
    good = out.loc["2020-12-01 02:31:39"].iloc[0]
    assert good["density"] == pytest.approx(1.3658e-2) and good["speed"] == pytest.approx(467.64, abs=0.01)
    # A sample flagged with a bad-measurement bit (bit 8, over-deflection) is dropped as a whole.
    flagged = raw.iloc[[0]].copy()
    flagged["QUALITY_FLAG"] = 12352 | 256
    assert spec["reduce"](flagged).isna().all().all()
    ev = EVENT_SOURCES["PSP"]["plasma"]["reduce"](raw)
    assert ev.loc[no_counts].isna().all().all() and (ev["n"].dropna() > 0).all() and (ev["t"].dropna() > 0).all()
    assert ev.loc["2020-12-01 02:31:39", "n"].iloc[0] == pytest.approx(1.3658e-2)
