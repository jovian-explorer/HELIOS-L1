"""
Event analysis on real archive data. The gzipped HAPI responses in tests/data/hapi/events
were recorded from https://cdaweb.gsfc.nasa.gov/hapi (include=header) around shocks listed
in the Harvard-Smithsonian CfA Interplanetary Shock Database (Wind), and the results are
checked against the values published there:

* 2015-03-17 (event 00677, https://www.cfa.harvard.edu/shocks/wi_data/00677/wi_00677.html):
  arrival 14401.5 +- 80 s of day, type FF, MX3 normal (-0.849, -0.271, 0.453), theta_Bn
  60.1 +- 3.1 deg, shock speed 536.1 +- 3.0 km/s, density compression 2.45 +- 0.46.
* 2015-06-22 (event 00693): arrival 65296.5 +- 110 s, FF, selected method RH08 normal
  (-0.983, -0.147, -0.106), theta_Bn 63.8 +- 5.0 deg, 788.2 km/s; MX3 (-0.994, -0.103, 0.037),
  793.8 km/s; median speed of all methods 790.7 km/s, compression 3.35 +- 0.22.
* 2014-02-27 (event 00658): arrival 57013.5 +- 20 s, FF, MX3 normal (-0.820, -0.543, -0.178),
  theta_Bn 79.9 +- 3.8 deg, 436.2 km/s, compression 2.47 +- 0.14. Most downstream SWE spectra
  carry fit_flag 1; the CfA downstream values (V_x -413.4 km/s, N 42.3 cm^-3) are theirs.
"""
import asyncio
import gzip
import math
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd
import pytest

from helios.core.archive import parse_hapi_csv
from helios.core.event_analysis import (EVENT_SOURCES, EventDataClient, analyze_shock, classify_shock,
                                        minimum_variance, shock_normals, shock_speed)

# The server only answers requests addressed to a loopback host (helios.api.guard).
LOCAL = "http://127.0.0.1:8765"

EVENTS = Path(__file__).parent / "data" / "hapi" / "events"


def _text(name):
    with gzip.open(EVENTS / f"{name}.csv.gz", "rt", encoding="utf-8") as f:
        return f.read()


def _wind(day):
    src = EVENT_SOURCES["WIND"]
    field = src["field"]["reduce"](parse_hapi_csv(_text(f"wi_h0_mfi3s_{day}")))
    plasma = src["plasma"]["reduce"](parse_hapi_csv(_text(f"wi_h1_swe_{day}")))
    return field, plasma


def _angle(a, b):
    a, b = np.asarray(a) / np.linalg.norm(a), np.asarray(b) / np.linalg.norm(b)
    return math.degrees(math.acos(min(1.0, abs(float(np.dot(a, b))))))


def test_shock_20150317_matches_cfa_database():
    field, plasma = _wind("20150317")
    res = analyze_shock(field, plasma, "2015-03-17 04:00", upstream_minutes=28, downstream_minutes=24)
    t = pd.Timestamp(res["shock_time"], tz="UTC")
    cfa_arrival = pd.Timestamp("2015-03-17", tz="UTC") + pd.Timedelta(seconds=14401.5)
    assert abs((t - cfa_arrival).total_seconds()) <= 80
    assert res["shock_type"] == "FF"
    mx3 = res["methods"]["MX3"]
    assert _angle(mx3["normal_gse"], [-0.849, -0.271, 0.453]) < 3.0
    assert mx3["normal_gse"][0] < 0  # points into the upstream wind, as in the CfA convention
    assert abs(mx3["theta_bn_deg"] - 60.1) < 3.1
    assert abs(mx3["shock_speed_kms"] - 536.1) / 536.1 < 0.03
    assert abs(res["density_ratio"] - 2.45) < 0.46
    # The other methods scatter as in the CfA table (MC 58.8 deg / 476.7 km/s, VC 71.3 deg / 543.7 km/s).
    assert abs(res["methods"]["MC"]["theta_bn_deg"] - 58.8) < 5 and abs(res["methods"]["VC"]["theta_bn_deg"] - 71.3) < 5
    assert abs(res["methods"]["VC"]["shock_speed_kms"] - 543.7) / 543.7 < 0.03
    # Supercritical fast shock: Alfven Mach number well above 1, and the uncertainty is reported.
    assert mx3["alfven_mach"] > 2.5 and mx3["fast_mach"] > 1.5
    assert 0 < mx3["shock_speed_sigma_kms"] < 50
    # With the flag-1 spectra kept, 30 spectra are averaged (the CfA used 17 + 15).
    assert res["upstream"]["plasma_samples"] + res["downstream"]["plasma_samples"] == 30
    assert all("fit_flag 1" in w for w in res["warnings"])


def test_shock_20150622_matches_cfa_database():
    field, plasma = _wind("20150622")
    # Two minutes are left out on each side: the overshoot behind this strong (M_A ~ 7) shock
    # biases the downstream mean in the first minute.
    res = analyze_shock(field, plasma, "2015-06-22 18:08", upstream_minutes=10, downstream_minutes=8,
                        exclude_minutes=2)
    t = pd.Timestamp(res["shock_time"], tz="UTC")
    assert abs((t - (pd.Timestamp("2015-06-22", tz="UTC") + pd.Timedelta(seconds=65296.5))).total_seconds()) <= 110
    assert res["shock_type"] == "FF"
    mx3 = res["methods"]["MX3"]
    # Closest to the CfA's selected Rankine-Hugoniot normal (2.5 deg), 9 deg from their MX3
    # (whose stated uncertainty in N_y is 0.26).
    assert _angle(mx3["normal_gse"], [-0.983, -0.147, -0.106]) < 4.0
    assert _angle(mx3["normal_gse"], [-0.994, -0.103, 0.037]) < 11.0
    assert abs(mx3["theta_bn_deg"] - 63.8) < 5.0
    assert abs(mx3["shock_speed_kms"] - 790.7) / 790.7 < 0.04
    assert abs(res["density_ratio"] - 3.35) < 0.4


def test_shock_20140227_uses_flagged_downstream_spectra_like_cfa():
    field, plasma = _wind("20140227")
    res = analyze_shock(field, plasma, "2014-02-27 15:50", upstream_minutes=13, downstream_minutes=5)
    t = pd.Timestamp(res["shock_time"], tz="UTC")
    assert abs((t - (pd.Timestamp("2014-02-27", tz="UTC") + pd.Timedelta(seconds=57013.5))).total_seconds()) <= 20
    mx3 = res["methods"]["MX3"]
    assert _angle(mx3["normal_gse"], [-0.820, -0.543, -0.178]) < 2.0
    assert abs(mx3["theta_bn_deg"] - 79.9) < 3.8
    assert abs(mx3["shock_speed_kms"] - 436.2) / 436.2 < 0.02
    assert abs(res["density_ratio"] - 2.47) < 0.14
    assert res["downstream"]["V_gse_kms"][0] == pytest.approx(-413.4, abs=6)
    assert any("fit_flag 1" in w for w in res["warnings"])
    # The magnetic coplanarity normal degenerates for this quasi-perpendicular shock (the CfA
    # MC normal is 70 deg from MX3 too); the velocity-based methods agree, so no warning.
    assert not any("poorly constrained" in w for w in res["warnings"])


def test_shock_normal_conventions_and_reverse_shock():
    # Synthetic fast forward shock with an exactly known normal: n = -x, theta_Bn = 45 deg.
    n_true = np.array([-1.0, 0.0, 0.0])
    b1 = np.array([-3.0, 3.0, 0.0])
    v1, n1 = np.array([-400.0, 0.0, 0.0]), 5.0
    r = 3.0
    vsh_true = -600.0 * -1  # shock moves anti-sunward at 600 km/s: along n
    # Mass flux: N1 (V1.n - Vsh) = N2 (V2.n - Vsh); tangential B jumps, normal B continuous.
    u1 = np.dot(v1, n_true) - vsh_true
    v2 = v1 + n_true * (u1 / r - u1) + np.array([0.0, 20.0, 0.0])
    b2 = np.array([-3.0, 9.0, 0.0])
    normals = shock_normals(b1, b2, v1, v2)
    assert _angle(normals["MC"], n_true) < 1e-6
    assert np.dot(normals["MX3"], v2 - v1) > 0
    assert abs(shock_speed(normals["MC"], n1, n1 * r, v1, v2) - vsh_true) < 1e-6
    assert classify_shock(5, 15, 4, 9) == "FF"
    assert classify_shock(15, 5, 9, 4) == "FR"
    assert classify_shock(5, 15, 9, 4) == "SF"
    assert classify_shock(15, 5, 4, 9) == "SR"

    # A fast reverse shock: the same jump seen in reversed time order. Upstream is then the
    # side after the shock, and the normal still points into the upstream plasma.
    field, plasma = _wind("20150317")
    t0 = pd.Timestamp("2015-03-17 04:00:04", tz="UTC")

    def mirror(df):
        out = df.copy()
        out.index = t0 - (df.index - t0)
        return out.sort_index()

    fwd = analyze_shock(field, plasma, t0, 28, 24, refine=False)
    rev = analyze_shock(mirror(field), mirror(plasma), t0, 24, 28, refine=False)
    assert rev["shock_type"] == "FR"
    assert _angle(rev["methods"]["MX3"]["normal_gse"], fwd["methods"]["MX3"]["normal_gse"]) < 1e-6
    assert rev["upstream"]["density_cm3"] == pytest.approx(fwd["upstream"]["density_cm3"])


def test_weak_jump_and_short_windows_are_flagged():
    field, plasma = _wind("20150317")
    # Both windows upstream of the shock: no real jump.
    res = analyze_shock(field, plasma, "2015-03-17 03:45", 10, 10, refine=False)
    assert any("Density jump" in w or "poorly constrained" in w for w in res["warnings"])
    with pytest.raises(ValueError):
        analyze_shock(field, plasma, "2015-03-17 03:45", 0.5, 0.5, refine=False)


def test_minimum_variance_recovers_known_frame_and_errors():
    rng = np.random.default_rng(3)
    # Variance 25, 4 and 0.04 nT^2 along a rotated orthonormal frame.
    rot = np.linalg.qr(rng.normal(size=(3, 3)))[0]
    k = 2000
    comps = np.column_stack([rng.normal(0, 5, k), rng.normal(0, 2, k), rng.normal(0, 0.2, k)])
    b = comps @ rot.T + np.array([1.0, 2.0, 3.0])
    res = minimum_variance(b)
    l1, l2, l3 = res["eigenvalues_nT2"]
    assert l1 == pytest.approx(25, rel=0.1) and l2 == pytest.approx(4, rel=0.1) and l3 == pytest.approx(0.04, rel=0.1)
    assert _angle(res["eigenvectors"]["min"], rot[:, 2]) < 1.0
    assert _angle(res["eigenvectors"]["max"], rot[:, 0]) < 2.0
    assert res["ratio_intermediate_to_min"] == pytest.approx(l2 / l3)
    # Sonnerup & Scheible (1998) eq. 8.23 for the rotation of the normal toward the intermediate axis.
    expect = math.degrees(math.sqrt(l3 / (k - 1) * (l2 + l3 - l3) / (l2 - l3) ** 2))
    assert res["angular_error_deg"]["normal_toward_intermediate"] == pytest.approx(expect)
    assert res["mean_normal_field_nT"] >= 0
    x1, x2, x3 = (np.array(res["eigenvectors"][k_]) for k_ in ("max", "intermediate", "min"))
    assert np.dot(np.cross(x1, x2), x3) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        minimum_variance(b[:3])


# Sonnerup & Scheible (1998, ISSI SR-001, ch. 8), Table 8.4: the 16 AMPTE/IRM vectors
# (nT, GSE) of the magnetopause crossing on 19 October 1984, 05:18:20-05:19:26 UT.
AMPTE_IRM_B = np.array([
    [-13.6, -24.7, 54.6], [-14.8, -24.9, 58.7], [-13.4, -17.2, 62.4], [-14.0, -25.0, 43.8],
    [-7.1, -4.5, 33.5], [-0.9, -5.0, 44.4], [-10.0, -0.4, 44.6], [-6.1, -4.8, 21.1],
    [1.2, 1.6, 21.0], [-3.4, -3.9, 4.1], [-0.9, 1.2, 5.0], [-1.0, -1.5, 12.3],
    [11.0, 13.2, 29.7], [19.1, 34.4, 20.1], [24.9, 50.1, 1.9], [29.2, 47.1, -10.6]])


def test_minimum_variance_matches_the_ampte_irm_benchmark():
    res = minimum_variance(AMPTE_IRM_B)
    # Fig. 8.2: eigenvalues 1012.86, 138.01, 7.08 nT^2; x3 = (0.8671, -0.4978, 0.0187) with
    # <B>.x3 = -0.58 nT (the opposite sense: here n is oriented so that <B>.n >= 0).
    # (The table's one-decimal values give 137.91 for lambda2, 0.08 % below the published 138.01.)
    assert res["eigenvalues_nT2"] == pytest.approx([1012.86, 138.01, 7.08], rel=1e-3)
    assert np.allclose(np.abs(res["eigenvectors"]["min"]), [0.8671, 0.4978, 0.0187], atol=1e-4)
    assert np.allclose(np.abs(res["eigenvectors"]["max"]), [0.4061, 0.6845, 0.6055], atol=1e-4)
    assert abs(res["mean_normal_field_nT"]) == pytest.approx(0.58, abs=0.005)
    # Section 8.3.1: dphi32 = 0.062 rad, dphi31 = 0.022 rad, dphi21 = 0.027 rad, d(<B>.x3) = 1.63 nT.
    err = res["angular_error_deg"]
    assert math.radians(err["normal_toward_intermediate"]) == pytest.approx(0.062, abs=0.0005)
    assert math.radians(err["normal_toward_max"]) == pytest.approx(0.022, abs=0.0005)
    assert math.radians(err["max_toward_intermediate"]) == pytest.approx(0.027, abs=0.0005)
    assert res["mean_normal_field_error_nT"] == pytest.approx(1.63, abs=0.005)
    # Section 8.3.2, Fig. 8.6 (1000 bootstrap sets): std of <B>.x3 1.17 nT, of the rotation of
    # x3 toward x1 0.023 rad and toward x2 0.059 rad; mean normal (0.8669, -0.4982, 0.0182),
    # 0.04 deg from x3. A 1000-sample bootstrap of 16 vectors scatters by several per cent
    # between runs (here 1.06 nT, 0.024 and 0.058 rad).
    bs = res["bootstrap"]
    assert bs["mean_normal_field_std_nT"] == pytest.approx(1.17, rel=0.15)
    assert math.radians(bs["normal_toward_max_std_deg"]) == pytest.approx(0.023, rel=0.1)
    assert math.radians(bs["normal_toward_intermediate_std_deg"]) == pytest.approx(0.059, rel=0.1)
    assert np.allclose(np.abs(bs["mean_normal"]), [0.8669, 0.4982, 0.0182], atol=0.003)
    assert bs["mean_normal_angle_to_x3_deg"] < 0.3


# Table 8.4: plasma velocity (km/s, GSE) and density (cm^-3) for the same 16 AMPTE/IRM samples.
AMPTE_IRM_V = np.array([
    [-111.0, -211.0, 57.0], [-102.0, -213.0, 41.0], [-111.0, -196.0, 34.0], [-135.0, -229.0, 54.0],
    [-128.0, -252.0, 54.0], [-82.0, -237.0, 51.0], [-139.0, -228.0, 77.0], [-143.0, -241.0, 57.0],
    [-132.0, -226.0, 80.0], [-117.0, -217.0, 79.0], [-112.0, -210.0, 93.0], [-98.0, -212.0, 92.0],
    [-90.0, -186.0, 104.0], [-83.0, -168.0, 121.0], [-82.0, -129.0, 88.0], [-93.0, -123.0, 53.0]])
AMPTE_IRM_N = np.array([12.18, 9.22, 9.92, 18.08, 20.39, 15.00, 20.19, 23.53, 24.31, 25.91, 26.17,
                        24.49, 22.20, 22.86, 17.56, 17.86])


def test_dehoffmann_teller_matches_the_ampte_irm_benchmark():
    from helios.core.event_analysis import dehoffmann_teller
    x3 = [0.8671, -0.4978, 0.0187]  # MVAB normal, Fig. 8.2
    res = dehoffmann_teller(AMPTE_IRM_B, AMPTE_IRM_V, AMPTE_IRM_N, normal=x3, n_bootstrap=5000)
    # Khrabrov & Sonnerup (1998), Sect. 9.3 and Table 9.1: V_HT = (-122.8, -223.0, 76.0) km/s from
    # D, c = 0.994, D(V_HT)/D(0) = 0.012; (-120.9, -224.1, 72.9) km/s from Q; error ellipsoid
    # semiaxes 7.62, 4.59, 3.94 km/s (D) and 8.19, 4.85, 4.21 km/s (Q); u_n = 5.9 +- 3.9 km/s
    # (D) and 8.1 +- 4.2 km/s (Q). The one-decimal values of Table 8.4 reproduce the field
    # results of chapter 8 exactly but V_HT only to 0.7 km/s (-122.6, -223.6, 75.7), so the
    # chapter 9 numbers were evidently computed from unrounded velocities.
    d, q = res["D"], res["Q"]
    assert d["v_ht_kms"] == pytest.approx([-122.8, -223.0, 76.0], abs=0.8)
    assert q["v_ht_kms"] == pytest.approx([-120.9, -224.1, 72.9], abs=0.8)
    assert res["correlation_ec_eht"] == pytest.approx(0.994, abs=0.0005)
    assert d["residual_ratio"] == pytest.approx(0.012, abs=0.0005)
    assert [a["sigma_kms"] for a in d["error_axes"]] == pytest.approx([7.62, 4.59, 3.94], rel=0.015)
    assert [a["sigma_kms"] for a in q["error_axes"]] == pytest.approx([8.19, 4.85, 4.21], rel=0.015)
    assert abs(np.dot(d["error_axes"][0]["axis"], [-0.2457, -0.3726, 0.8949])) == pytest.approx(1.0, abs=1e-3)
    assert d["normal_velocity_kms"] == pytest.approx(5.9, abs=0.6)
    assert d["normal_velocity_error_kms"] == pytest.approx(3.9, abs=0.05)
    assert q["normal_velocity_kms"] == pytest.approx(8.1, abs=0.6)
    assert q["normal_velocity_error_kms"] == pytest.approx(4.2, abs=0.05)
    # Table 9.2 (5000 bootstrap resamples, D): V_HT (-122.7, -223.2, 74.5) km/s, semiaxes 7.88,
    # 5.29, 4.62 km/s, u_n = 6.1 +- 4.7 km/s; another set of resamples scatters by a few per cent.
    bs = res["bootstrap"]
    assert bs["v_ht_kms"] == pytest.approx([-122.7, -223.2, 74.5], abs=1.0)
    assert [a["sigma_kms"] for a in bs["error_axes"]] == pytest.approx([7.88, 5.29, 4.62], rel=0.1)
    assert bs["normal_velocity_kms"] == pytest.approx(6.1, abs=0.8)
    assert bs["normal_velocity_error_kms"] == pytest.approx(4.7, rel=0.1)
    # Fig. 9.4a: the Walen test fails for this tangential discontinuity (points cluster near v' = 0).
    assert abs(res["walen"]["slope"]) < 0.2


def test_event_data_client_fetches_native_cadence_and_caches(tmp_path):
    served = {"WI_H0_MFI@1": "wi_h0_mfi3s_20150317", "WI_H1_SWE": "wi_h1_swe_20150317",
              "WI_H0_MFI@0": "wi_h0_pgse_20150317"}
    calls = []

    async def fake(url):
        q = parse_qs(urlparse(url).query)
        calls.append(q["id"][0])
        return _text(served[q["id"][0]])

    client = EventDataClient(fake, tmp_path)
    t0 = datetime(2015, 3, 17, 3, 25, tzinfo=timezone.utc)
    t1 = datetime(2015, 3, 17, 4, 35, tzinfo=timezone.utc)
    out = asyncio.run(client.fetch("WIND", t0, t1))
    assert len(out["field"]) > 1300  # 3-s samples (fill values dropped), not 1-minute means
    assert {"vx", "vy", "vz", "n", "t"} <= set(out["plasma"].columns)
    # Position from the MFI file's definitive orbit; the CfA lists 252.852, 54.339, 12.569 R_E at the shock.
    from helios.core.event_analysis import position_at
    pos = position_at(out["position"], pd.Timestamp("2015-03-17 04:00:01", tz="UTC")) / 6371.2
    assert np.allclose(pos, [252.852, 54.339, 12.569], atol=0.02)
    assert [d["id"] for d in out["datasets"]] == ["WI_H0_MFI@1", "WI_H1_SWE", "WI_H0_MFI@0"]
    assert out["datasets"][0]["hapi_url"].startswith("https://cdaweb.gsfc.nasa.gov/hapi/data?id=WI_H0_MFI%401")

    async def offline(url):
        return None

    # Old intervals are served from the cache without a request; nothing cached -> offline.
    again = asyncio.run(EventDataClient(offline, tmp_path).fetch("WIND", t0, t1))
    assert len(again["field"]) == len(out["field"]) and not again["offline"]
    empty = asyncio.run(EventDataClient(offline, tmp_path / "other").fetch("WIND", t0, t1))
    assert empty["offline"] and empty["field"] is None


def test_shock_and_mva_api_with_provenance(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from helios.api import server
    from helios.core.downloader import DataDownloader

    served = {"WI_H0_MFI@1": "wi_h0_mfi3s_20150317", "WI_H1_SWE": "wi_h1_swe_20150317"}

    async def fake(url, timeout=120.0):
        ds = parse_qs(urlparse(url).query)["id"][0]
        return _text(served[ds]) if ds in served else None

    dl = DataDownloader()
    dl.fetch_text = fake
    dl.events = EventDataClient(lambda url: dl.fetch_text(url), tmp_path)
    monkeypatch.setattr(server, "downloader", dl)
    client = TestClient(server.app, base_url=LOCAL)

    r = client.get("/api/analysis/shock?mission=wind&time=2015-03-17T04:00&upstream_minutes=28&downstream_minutes=24")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"]["shock_type"] == "FF"
    assert abs(body["result"]["methods"]["MX3"]["shock_speed_kms"] - 536.1) < 16
    prov = body["provenance"]
    assert [d["id"] for d in prov["datasets"]] == ["WI_H0_MFI@1", "WI_H1_SWE"]
    assert prov["parameters"]["upstream_minutes"] == 28 and prov["software"].startswith("HELIOS-L1")
    assert len(body["series"]["field_gse"]["bt"]) > 1000 and body["series"]["plasma_gse"]["n"]

    dl_file = client.get("/api/analysis/shock?mission=WIND&time=2015-03-17T04:00&upstream_minutes=28"
                         "&downstream_minutes=24&download=true")
    assert 'attachment; filename="HELIOS_shock_WIND_20150317T0400.json"' in dl_file.headers["content-disposition"]
    assert '"hapi_url"' in dl_file.text

    mva = client.get("/api/analysis/mva?mission=WIND&start=2015-03-17T04:01&end=2015-03-17T04:25").json()
    assert mva["result"]["n_vectors"] > 400 and len(mva["result"]["eigenvalues_nT2"]) == 3
    assert client.get("/api/analysis/mva?mission=WIND&start=2015-03-17T04:01&end=2015-03-17T04:25"
                      "&average_seconds=60").json()["result"]["n_vectors"] == 24

    ht = client.get("/api/analysis/ht?mission=WIND&start=2015-03-17T04:02&end=2015-03-17T04:25").json()["result"]
    assert ht["n_vectors"] > 10 and len(ht["D"]["v_ht_kms"]) == 3 and ht["bootstrap"]["n_samples"] == 1000
    assert 0.9 < ht["correlation_ec_eht"] <= 1.0 and np.linalg.norm(ht["normal_used"]["vector_gse"]) == pytest.approx(1.0)
    assert client.get("/api/analysis/ht?mission=WIND&start=2015-03-17T04:02&end=2015-03-17T04:04").status_code == 422
    assert client.get("/api/analysis/shock?mission=SOHO&time=2015-03-17T04:00").status_code == 404
    assert client.get("/api/analysis/mva?mission=WIND&start=2015-03-17&end=2015-03-21").status_code == 422
    assert client.get("/api/analysis/shock?mission=ACE&time=2015-03-17T04:00").status_code == 404  # nothing served


def test_timing_wind_to_ace_20140227_against_cfa_arrivals():
    """
    27 Feb 2014: WIND (CfA event 00658, at 219.166, 99.616, -0.544 R_E) and ACE (CfA ACE event
    00262, https://www.cfa.harvard.edu/shocks/ac_master_data/00262/ac_master_00262.html, arrival
    58060 +- 80 s of day at 228.977, -39.744, -15.955 R_E). ACE is 10 R_E further upstream but
    sees the shock 17 min after WIND: the normal is tilted towards -Y and the spacecraft are
    140 R_E apart in Y.
    """
    from helios.core.event_analysis import position_at, predict_arrival, timing_comparison
    re_km = 6371.2
    field, plasma = _wind("20140227")
    res = analyze_shock(field, plasma, "2014-02-27 15:50", upstream_minutes=13, downstream_minutes=5)
    t_ref = pd.Timestamp(res["shock_time"], tz="UTC")
    wind_pos = position_at(EVENT_SOURCES["WIND"]["position"]["reduce"](parse_hapi_csv(_text("wi_h0_pgse_20140227"))), t_ref)
    ace_raw = parse_hapi_csv(_text("ac_h0_mfi_20140227"))
    ace_pos = position_at(EVENT_SOURCES["ACE"]["position_reduce"](ace_raw), t_ref)
    # The MFI file puts WIND at X = 220.91 R_E here, 1.7 R_E further out than the CfA page (which
    # agrees with the MFI file to 0.01 R_E for 17 March 2015); along the normal that is ~20 s.
    assert np.allclose(wind_pos / re_km, [220.91, 99.05, -0.66], atol=0.02)
    assert np.allclose(ace_pos / re_km, [228.977, -39.744, -15.955], atol=0.05)

    # The delay predicted from the CfA's own MX3 normal, speed and positions.
    cfa = predict_arrival([-0.820, -0.543, -0.178], 436.2, t_ref, np.array([219.166, 99.616, -0.544]) * re_km,
                          np.array([228.977, -39.744, -15.955]) * re_km)
    mx3 = res["methods"]["MX3"]
    out = timing_comparison(mx3["normal_gse"], mx3["shock_speed_kms"], t_ref, wind_pos,
                            EVENT_SOURCES["ACE"]["field"]["reduce"](ace_raw), ace_pos)
    assert abs(out["predicted_delay_s"] - cfa["delay_s"]) / cfa["delay_s"] < 0.05
    cfa_ace = pd.Timestamp("2014-02-27", tz="UTC") + pd.Timedelta(seconds=58060)
    assert abs((pd.Timestamp(out["observed_time"], tz="UTC") - cfa_ace).total_seconds()) <= 80 + 16  # 16-s ACE data
    assert abs(out["residual_s"]) < 150
    assert 350 < out["implied_speed_kms"] < 480
    assert out["baseline_along_normal_km"] > 4e5


def test_timing_api(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from helios.api import server
    from helios.core.downloader import DataDownloader

    served = {"WI_H0_MFI@1": "wi_h0_mfi3s_20140227", "WI_H1_SWE": "wi_h1_swe_20140227",
              "WI_H0_MFI@0": "wi_h0_pgse_20140227", "AC_H0_MFI": "ac_h0_mfi_20140227"}

    async def fake(url, timeout=120.0):
        ds = parse_qs(urlparse(url).query)["id"][0]
        return _text(served[ds]) if ds in served else None

    dl = DataDownloader()
    dl.fetch_text = fake
    dl.events = EventDataClient(lambda url: dl.fetch_text(url), tmp_path)
    monkeypatch.setattr(server, "downloader", dl)
    client = TestClient(server.app, base_url=LOCAL)
    r = client.get("/api/analysis/timing?reference=WIND&time=2014-02-27T15:50&upstream_minutes=13&downstream_minutes=5")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["reference"]["method"] == "MX3" and body["reference"]["shock_type"] == "FF"
    by = {t["spacecraft"]: t for t in body["targets"]}
    assert set(by) == {"ACE", "DSCOVR"}
    assert by["ACE"]["status"] == "ok" and by["ACE"]["observed_time"].startswith("2014-02-27 16:08")
    assert by["DSCOVR"]["status"].startswith("no data for this interval")  # DSCOVR science data start in 2015
    assert any(d["id"] == "AC_H0_MFI" and d["spacecraft"] == "ACE" for d in body["provenance"]["datasets"])
    assert client.get("/api/analysis/timing?reference=WIND&time=2014-02-27T15:50&method=XYZ").status_code == 422


# WIND MFI magnetic cloud table (Lepping et al. fits, https://wind.nasa.gov/mfi/mag_cloud_S1.html),
# quality 1 clouds: (file day, start, end, axis longitude, latitude, B0 nT, H, CA %, 2R0 AU, flux 1e20 Mx, chi_R)
LEPPING_CLOUDS = [
    ("19951018", "1995-10-18 19:48", "1995-10-20 01:18", 287, -8, 25.9, "R", 12, 0.257, 13.1, 0.143),
    ("19970110", "1997-01-10 05:18", "1997-01-11 02:18", 247, 1, 17.7, "R", -11, 0.190, None, 0.103),
    ("19980304", "1998-03-04 14:18", "1998-03-06 06:18", 121, 21, 12.4, "L", -6, 0.327, None, 0.152),
]


@pytest.mark.parametrize("cloud", LEPPING_CLOUDS, ids=[c[0] for c in LEPPING_CLOUDS])
def test_lundquist_fit_matches_wind_mfi_cloud_table(cloud):
    from helios.core.event_analysis import _field, fit_flux_rope, _axis
    day, start, end, lon, lat, b0, hand, ca, diam, flux, chi = cloud
    field = _field("BGSE")(parse_hapi_csv(_text(f"wi_h0_mfi1m_{day}")))
    plasma = EVENT_SOURCES["WIND"]["plasma"]["reduce"](parse_hapi_csv(_text(f"wi_h1_swe_{day}")))
    res = fit_flux_rope(field, plasma, start, end, average_minutes=30)
    # Our boundaries are the table's (to 0.1 h), the averages and speed our own: axis within
    # 20 deg (9, 13 and 18 deg for the three clouds), B0 within 10 %, same handedness.
    assert _angle(res["axis_gse"], _axis(lon, lat)) < 20
    assert np.dot(res["axis_gse"], _axis(lon, lat)) > 0  # axis along the axial field, as in the table
    assert abs(res["b0_nT"] - b0) / b0 < 0.10
    assert res["handedness"] == hand
    assert np.sign(res["closest_approach_percent"]) == np.sign(ca) and abs(res["closest_approach_percent"] - ca) < 20
    assert abs(res["diameter_au"] - diam) / diam < 0.30
    assert abs(res["chi_r"] - chi) < 0.03
    if flux is not None:
        assert abs(res["axial_flux_1e20_Mx"] - flux) / flux < 0.10
    assert len(res["model"]["model_gse_nT"]) == res["n_averages"]


def test_lundquist_model_geometry():
    from helios.core.event_analysis import _bessel_j, lundquist_field
    # J0, J1 series against tabulated values (Abramowitz & Stegun table 9.1).
    assert _bessel_j(0, np.array([1.0]))[0] == pytest.approx(0.7651976866, abs=1e-9)
    assert _bessel_j(1, np.array([1.0]))[0] == pytest.approx(0.4400505857, abs=1e-9)
    assert abs(_bessel_j(0, np.array([2.404825557695773]))[0]) < 1e-12
    # Axis along +Z, crossing through the centre: field is purely axial at closest approach,
    # azimuthal (|B| = B0 J1(2.405) = 0.519 B0) at the boundaries, and rotates in sense H.
    t = np.linspace(0, 20, 201)
    b = lundquist_field(t, 0.0, 90.0, 0.0, 10.0, 1, 20.0, 400.0, b0=10.0)
    assert b[100] == pytest.approx([0, 0, 10.0], abs=1e-9)
    assert np.linalg.norm(b[0]) == pytest.approx(10 * 0.5191474973, rel=1e-6) and abs(b[0][2]) < 1e-9
    assert np.sign(b[0][1]) == -np.sign(lundquist_field(t, 0.0, 90.0, 0.0, 10.0, -1, 20.0, 400.0, b0=10.0)[0][1])


def test_flux_rope_api(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from helios.api import server
    from helios.core.downloader import DataDownloader

    served = {"WI_H0_MFI@0": "wi_h0_mfi1m_19951018", "WI_H1_SWE": "wi_h1_swe_19951018"}

    async def fake(url, timeout=120.0):
        ds = parse_qs(urlparse(url).query)["id"][0]
        return _text(served[ds]) if ds in served else None

    dl = DataDownloader()
    dl.fetch_text = fake
    dl.events = EventDataClient(lambda url: dl.fetch_text(url), tmp_path)
    monkeypatch.setattr(server, "downloader", dl)
    client = TestClient(server.app, base_url=LOCAL)
    r = client.get("/api/analysis/fluxrope?mission=WIND&start=1995-10-18T19:48&end=1995-10-20T01:18")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"]["handedness"] == "R"
    assert body["provenance"]["datasets"][0]["id"] == "WI_H0_MFI@0"  # 1-min file for day-long fits
    assert client.get("/api/analysis/fluxrope?mission=WIND&start=1995-10-18T19:48&end=1995-10-18T20:48").status_code == 422


def test_superposed_epoch_of_two_storms_from_omni(monkeypatch, tmp_path):
    """
    Epoch zero at the sudden commencements of 17 March 2015 (04:45 UT) and 10 May 2024
    (17:05 UT, Tulasi Ram et al. 2024, Space Weather, doi:10.1029/2024SW004126). Published
    SYM-H minima: about -234 nT at 22:47 UT on 17 March 2015 (e.g. arXiv:1703.10583) and
    -518 nT at 02:14 UT on 11 May 2024 (Tulasi Ram et al. 2024).
    """
    from fastapi.testclient import TestClient
    from helios.api import server
    from helios.core.archive import ArchiveClient
    from helios.core.downloader import DataDownloader

    days = {"2015-03-17": "omni_hro_1min_20150317", "2024-05-10": "omni_hro_1min_20240510_storm",
            "2024-05-11": "omni_hro_1min_20240511"}
    no_data = (Path(__file__).parent / "data" / "hapi" / "wi_h1_swe_nodata.csv").read_text()

    async def fake(url, timeout=120.0):
        q = parse_qs(urlparse(url).query)
        day = q["time.min"][0][:10]
        return _text(days[day]) if q["id"][0] == "OMNI_HRO_1MIN" and day in days else no_data

    dl = DataDownloader()
    dl.fetch_text = fake
    dl.archive = ArchiveClient(lambda url: dl.fetch_text(url), tmp_path)
    monkeypatch.setattr(server, "downloader", dl)
    client = TestClient(server.app, base_url=LOCAL)
    base = "/api/analysis/superposed?onsets=2015-03-17T04:45,2024-05-10T17:05&before_hours=2&after_hours=18.5"
    r = client.get(base + "&cadence_minutes=1&parameters=sym_h,bz_gsm")
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    ev15, ev24 = res["events"]
    assert ev15["sym_h"]["min"] == -234 and ev15["sym_h"]["min_epoch_hours"] == pytest.approx(18 + 2 / 60)
    assert ev24["sym_h"]["min"] == -518 and ev24["sym_h"]["min_epoch_hours"] == pytest.approx(9 + 9 / 60)
    epoch = np.array(res["epoch_hours"])
    per = res["statistics"]["sym_h"]["per_event"]
    i0 = int(np.argmin(np.abs(epoch)))
    for row in per:  # sudden commencement: SYM-H jumps by tens of nT within minutes of epoch zero
        assert row[i0 + 5] - row[i0 - 5] > 40
    st = res["statistics"]["sym_h"]
    assert st["mean"][i0 + 60] == pytest.approx((per[0][i0 + 60] + per[1][i0 + 60]) / 2, abs=1e-3)
    assert st["n_events"][i0] == 2 and st["n_events"][-1] == 1  # the 2024 file ends at 04:00 UT

    ten = client.get(base + "&cadence_minutes=10&parameters=sym_h").json()["result"]
    assert len(ten["epoch_hours"]) == 123 and ten["epoch_hours"][12] == 0.0
    # 10-minute block means can only be shallower than the 1-minute minimum.
    assert min(v for v in ten["statistics"]["sym_h"]["per_event"][1] if v is not None) > -518
    csv_text = client.get(base + "&cadence_minutes=60&parameters=sym_h,speed&format=csv").text
    assert csv_text.startswith("# title: HELIOS-L1 superposed epoch analysis (2 events")
    assert "epoch_hours,sym_h_mean,sym_h_median,sym_h_q25,sym_h_q75,sym_h_n_events,speed_mean" in csv_text
    prov = r.json()["provenance"]
    assert prov["datasets"][0]["datasets"][0]["id"] == "OMNI_HRO_1MIN"
    assert client.get(base + "&parameters=kp").status_code == 422
    assert client.get("/api/analysis/superposed?onsets=yesterday").status_code == 422


# WIND MFI magnetic cloud table (https://wind.nasa.gov/mfi/mag_cloud_S1.html), clouds 25 and 26:
# 7 Nov 1997 15:48 - 8 Nov 04:18 and 8 Nov 04:54 - 14:54 (quality 2). WIND 1-min MFI and SWE
# from CDAWeb (WI_H0_MFI@0, WI_H1_SWE) for 6 Nov 12:00 - 9 Nov 12:00.
MC_TABLE_1997_11 = [("1997-11-07 15:48", "1997-11-08 04:18"), ("1997-11-08 04:54", "1997-11-08 14:54")]


def _wind_1min_19971106():
    return pd.read_csv(EVENTS / "wi_1min_19971106_mc.csv.gz", index_col=0, parse_dates=True)


@pytest.mark.parametrize("criteria", ["loose", "strict"])
def test_magnetic_cloud_detection_finds_the_wind_mfi_clouds(criteria):
    from helios.core.event_analysis import detect_magnetic_clouds
    res = detect_magnetic_clouds(_wind_1min_19971106(), criteria)
    found = [(pd.Timestamp(c["start"]), pd.Timestamp(c["end"])) for c in res["accepted"]]
    assert len(found) == 2
    for (s, e), (fs, fe) in zip(MC_TABLE_1997_11, found):
        assert abs((fs - pd.Timestamp(s)).total_seconds()) <= 1800   # front boundary within 30 min
        assert abs((fe - pd.Timestamp(e)).total_seconds()) <= 2400   # rear boundary within 40 min
    for c in res["accepted"]:
        assert c["mean_b_nt"] >= 7 and c["mean_beta"] <= 0.3 and c["theta_b_range_deg"] >= 35
        assert c["chi_m_over_b"] <= 0.42 and c["mean_thermal_speed_kms"] <= 30


def test_magnetic_cloud_detection_rejects_ordinary_solar_wind():
    from helios.core.event_analysis import detect_magnetic_clouds
    df = _wind_1min_19971106()
    quiet = df[df.index < "1997-11-07 14:00"]  # the 27 h before the first cloud
    assert detect_magnetic_clouds(quiet, "loose")["accepted"] == []
    with pytest.raises(ValueError):
        detect_magnetic_clouds(quiet.drop(columns=["temperature"]), "loose")
    with pytest.raises(ValueError):
        detect_magnetic_clouds(quiet, "medium")


def test_magnetic_cloud_detection_api(monkeypatch):
    from fastapi.testclient import TestClient
    from helios.api import server
    frame = _wind_1min_19971106()
    frame.index = frame.index.tz_localize("UTC") if frame.index.tz is None else frame.index

    async def fetch_mission(mission, start, end):
        return {"frame": frame, "datasets": [{"id": "WI_H0_MFI@0"}, {"id": "WI_H1_SWE"}], "offline": False,
                "failed_days": 0}

    monkeypatch.setattr(server.downloader.archive, "fetch_mission", fetch_mission)
    client = TestClient(server.app, base_url=LOCAL)
    body = client.get("/api/analysis/mcdetect?mission=WIND&start=1997-11-06T12:00&end=1997-11-09T12:00").json()
    assert [c["start"] for c in body["result"]["accepted"]] == ["1997-11-07 15:34", "1997-11-08 04:54"]
    assert body["provenance"]["datasets"][1]["id"] == "WI_H1_SWE" and body["provenance"]["parameters"]["criteria"] == "loose"
    assert client.get("/api/analysis/mcdetect?start=1997-11-06&end=1997-11-06T04:00").status_code == 422
    assert client.get("/api/analysis/mcdetect?start=1997-11-01&end=1997-12-15").status_code == 422
    assert client.get("/api/analysis/mcdetect?mission=SOHO&start=1997-11-06&end=1997-11-07").status_code == 404
