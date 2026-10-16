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


def test_shock_20170906_matches_cfa_database():
    """
    The shock of 6 Sep 2017 at WIND (CfA event 00735, https://www.cfa.harvard.edu/shocks/wi_data/00735/wi_00735.html;
    not in the IPShocks database at WIND): MX3 theta_Bn 45.5 +- 20.5 deg, V_sh 621.1 +- 5.6 km/s, compression
    5.20 +- 1.50, fast Mach 3.98 +- 0.51, arrival 82966.5 +- 30 s of day. With the default windows: 50.5 deg,
    619 km/s, 4.75; the normal 14 deg from theirs (their MX3 normal is uncertain by +-12 deg in latitude). The fast
    Mach number is 3.2: the sound speed here is OMNI's (0.12 sqrt(T + 1.28e5 K) = 48 km/s against their 29 km/s).
    """
    field, plasma = _wind("20170906")
    res = analyze_shock(field, plasma, "2017-09-06 23:02:46")
    t = pd.Timestamp(res["shock_time"], tz="UTC")
    assert abs((t - (pd.Timestamp("2017-09-06", tz="UTC") + pd.Timedelta(seconds=82966.5))).total_seconds()) <= 30
    mx3 = res["methods"]["MX3"]
    assert res["shock_type"] == "FF" and _angle(mx3["normal_gse"], [-1.000, 0.009, -0.025]) < 15.0
    assert abs(mx3["theta_bn_deg"] - 45.5) < 20.5 and abs(mx3["shock_speed_kms"] - 621.1) < 5.6
    assert abs(res["density_ratio"] - 5.20) < 1.50
    assert 3.0 < mx3["fast_mach"] < 3.98 - 0.51


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
    assert client.get("/api/analysis/shock?mission=ACE&time=2015-03-17T04:00").status_code == 503  # nothing served: CDAWeb not reached


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
    listed = by["ACE"]["ipshocks"]  # IPShocks: ACE fast forward shock at 16:08:41
    assert listed["time"] == "2014-02-27 16:08:41" and abs(listed["minus_observed_s"]) <= 16  # 16-s ACE field
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

    gfz = Path(__file__).parent / "data" / "gfz"  # GFZ web service answers for the storm days

    async def fake(url, timeout=120.0):
        q = parse_qs(urlparse(url).query)
        if url.startswith("https://kp.gfz.de/"):
            name = {("Kp", "2015"): "kp_20150316", ("Hp30", "2015"): "hp30_20150316",
                    ("Kp", "2024"): "kp_20240509", ("Hp30", "2024"): "hp30_20240509"}.get((q["index"][0], q["start"][0][:4]))
            return (gfz / f"{name}.json").read_text() if name else None
        day = q["time.min"][0][:10]
        return _text(days[day]) if q["id"][0] == "OMNI_HRO_1MIN" and day in days else no_data

    dl = DataDownloader()
    dl.fetch_text = fake
    dl.archive = ArchiveClient(lambda url: dl.fetch_text(url), tmp_path)
    monkeypatch.setattr(server, "downloader", dl)
    monkeypatch.setattr(server.helios_config, "CACHE_DIR", tmp_path)
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
    assert client.get(base + "&parameters=xyz").status_code == 422
    # GFZ Kp and Hp30 held over their intervals: Kp 8- (7.667) from 12 UT on 17 March 2015 and 9o from
    # 00 UT on 11 May 2024 (the first Kp 9 since 2003); Hp30, not capped at 9, 9- at 13:30 and 11- at 22:30.
    gz = client.get(base + "&cadence_minutes=1&parameters=kp,hp30").json()
    ev15, ev24 = gz["result"]["events"]
    assert (ev15["kp"]["max"], ev15["kp"]["max_epoch_hours"]) == (7.667, pytest.approx(7.25))
    assert (ev15["hp30"]["max"], ev15["hp30"]["max_epoch_hours"]) == (8.667, pytest.approx(8.75))
    assert (ev24["kp"]["max"], ev24["kp"]["max_epoch_hours"]) == (9.0, pytest.approx(6 + 55 / 60))
    assert (ev24["hp30"]["max"], ev24["hp30"]["max_epoch_hours"]) == (11.333, pytest.approx(5 + 25 / 60))
    hp = gz["result"]["statistics"]["hp30"]["per_event"][1]
    i = gz["result"]["epoch_hours"].index(5.5)  # 22:35, inside the 22:30-23:00 interval
    assert hp[i] == 11.333 and hp[i - 6] != 11.333  # 22:29 belongs to the interval before
    prov = gz["provenance"]["geomagnetic_indices"]
    assert prov["licence"] == "CC BY 4.0" and prov["years_unread"] == []
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


def test_magnetic_cloud_search_reports_field_and_plasma_coverage(monkeypatch):
    # The search gave the coverage of the merged 1-min table as "field", so plasma gaps were
    # hidden wherever the field was present: for this WIND interval "field 100.0 %" and no
    # word of the plasma, which covers 77.7 % with a 4.7-h gap from 21:48 on 6 November.
    from fastapi.testclient import TestClient
    from helios.api import server
    frame = _wind_1min_19971106()
    frame.index = frame.index.tz_localize("UTC") if frame.index.tz is None else frame.index

    async def fetch_mission(mission, start, end):
        return {"frame": frame, "datasets": [{"id": "WI_H0_MFI@0"}, {"id": "WI_H1_SWE"}], "offline": False,
                "failed_days": 0}

    monkeypatch.setattr(server.downloader.archive, "fetch_mission", fetch_mission)
    body = TestClient(server.app, base_url=LOCAL).get(
        "/api/analysis/mcdetect?mission=WIND&start=1997-11-06T12:00&end=1997-11-09T12:00").json()
    cov = body["provenance"]["coverage"]
    assert set(cov) == {"field", "plasma"}
    assert cov["field"]["covered_fraction"] == 1.0 and cov["field"]["gaps"] == 0
    assert cov["plasma"]["covered_fraction"] == pytest.approx(0.777, abs=0.001) and cov["plasma"]["gaps"] == 13
    assert cov["plasma"]["longest_gap"] == {"start": "1997-11-06 21:48:00", "end": "1997-11-07 02:31:00", "minutes": 283.0}


def test_superposed_epoch_bootstrap_confidence_bands():
    from helios.core.event_analysis import superposed_epoch
    rng = np.random.default_rng(7)
    events = []
    for k in range(40):
        onset = pd.Timestamp("2020-01-01", tz="UTC") + pd.Timedelta(days=5 * k)
        recs = [{"time_tag": (onset + pd.Timedelta(minutes=m)).strftime("%Y-%m-%d %H:%M:%S"),
                 "sym_h": -50.0 + rng.normal(0, 10)} for m in range(-60, 120, 10)]
        events.append((onset, recs))
    res = superposed_epoch(events, ["sym_h"], 1, 2, cadence_minutes=10)
    st = res["statistics"]["sym_h"]
    # One value per event and bin, sigma = 10 nT, 40 events: the 95 % interval of the mean is
    # about +-1.96 * 10 / sqrt(40) = +-3.1 nT around the sample mean.
    widths = np.array(st["mean_ci95_high"]) - np.array(st["mean_ci95_low"])
    assert np.median(widths) == pytest.approx(2 * 1.96 * 10 / math.sqrt(40), rel=0.15)
    lo, hi, mean = np.array(st["mean_ci95_low"]), np.array(st["mean_ci95_high"]), np.array(st["mean"])
    assert np.all(lo < mean) and np.all(mean < hi)
    assert np.mean((lo < -50) & (-50 < hi)) > 0.8  # the true mean is inside in most bins
    assert st["median_ci95_low"][0] < st["median"][0] < st["median_ci95_high"][0]
    # Fewer than 3 events: no bands.
    assert "mean_ci95_low" not in superposed_epoch(events[:2], ["sym_h"], 1, 2)["statistics"]["sym_h"]


def test_coupling_functions_with_propagated_errors():
    """WIND 17 Mar 2015 12-18 UT (sheath of the St Patrick's Day storm) with SWE 1-sigma uncertainties."""
    from helios.core.coordinates import gse_to_gsm
    from helios.core.event_analysis import coupling_with_errors, field_at_plasma_times
    field = EVENT_SOURCES["WIND"]["field_coarse"]["reduce"](parse_hapi_csv(_text("wi_h0_mfi1m_20150317_cpl")))
    plasma = EVENT_SOURCES["WIND"]["plasma"]["reduce"](parse_hapi_csv(_text("wi_h1_swe_20150317_cpl")))
    assert {"sigma_v", "sigma_n"} <= set(plasma.columns)
    res = coupling_with_errors(field, plasma)
    assert res["uncertainties_available"]
    # Independent recomputation of the values from the definitions.
    p = plasma.dropna(subset=["vx", "vy", "vz"])
    b = field_at_plasma_times(field, p)
    ok = np.all(np.isfinite(b), axis=1)
    p, b = p[ok], b[ok]
    _, by, bz = gse_to_gsm(p.index, b[:, 0], b[:, 1], b[:, 2])
    v = np.sqrt(p.vx ** 2 + p.vy ** 2 + p.vz ** 2).to_numpy()
    theta = np.arctan2(np.abs(by), bz)
    newell = v ** (4 / 3) * np.hypot(by, bz) ** (2 / 3) * np.sin(theta / 2) ** (8 / 3)
    eps = 1e7 * v * 1e3 * (np.linalg.norm(b, axis=1) * 1e-9) ** 2 * np.sin(theta / 2) ** 4 * (7 * 6371e3) ** 2 / 1e9
    f = res["functions"]
    assert f["newell_dphi_dt"]["mean"] == pytest.approx(newell.mean(), rel=1e-9)
    assert f["akasofu_epsilon_gw"]["mean"] == pytest.approx(eps.mean(), rel=1e-6)
    assert f["dynamic_pressure_npa"]["mean"] == pytest.approx((1.6726e-6 * p.n * v ** 2).mean(), rel=1e-3)
    # First-order propagation against Monte Carlo draws from the archive's 1-sigma errors.
    rng = np.random.default_rng(0)
    sv, sn, n = p.sigma_v.to_numpy(), p.sigma_n.to_numpy(), p.n.to_numpy()
    draws_pd, draws_nw = [], []
    for _ in range(4000):
        vv = v + sv * rng.normal(size=len(v))
        nn = n + sn * rng.normal(size=len(v))
        draws_pd.append((1.6726e-6 * nn * vv ** 2).mean())
        draws_nw.append((vv ** (4 / 3) * np.hypot(by, bz) ** (2 / 3) * np.sin(theta / 2) ** (8 / 3)).mean())
    assert f["dynamic_pressure_npa"]["measurement_sigma_of_mean"] == pytest.approx(np.std(draws_pd), rel=0.05)
    assert f["newell_dphi_dt"]["measurement_sigma_of_mean"] == pytest.approx(np.std(draws_nw), rel=0.05)
    # The sampling interval of a mean is much wider than its measurement error.
    lo, hi = f["dynamic_pressure_npa"]["sampling_ci95_of_mean"]
    assert hi - lo > 10 * f["dynamic_pressure_npa"]["measurement_sigma_of_mean"]

    # Proton beta and Alfven Mach number, recomputed from SI constants, and their errors
    # (thermal speed error as sigma_T / T = 2 sigma_W / W) against Monte Carlo draws.
    assert {"sigma_t"} <= set(p.columns)
    mu0, kb, mp = 4e-7 * math.pi, 1.380649e-23, 1.67262192e-27
    bt = np.linalg.norm(b, axis=1) * 1e-9
    t_k, st = p.t.to_numpy(), p.sigma_t.to_numpy()
    beta = 2 * mu0 * n * 1e6 * kb * t_k / bt ** 2
    ma = v * 1e3 * np.sqrt(mu0 * mp * n * 1e6) / bt
    has_t = np.isfinite(t_k)  # spectra without a thermal speed have no beta
    assert 0 < (~has_t).sum() < 5 and f["proton_beta"]["mean"] == pytest.approx(beta[has_t].mean(), rel=1e-6)
    assert f["alfven_mach"]["mean"] == pytest.approx(ma.mean(), rel=1e-6)
    draws_b, draws_m = [], []
    for _ in range(4000):
        vv = v + sv * rng.normal(size=len(v))
        nn = n + sn * rng.normal(size=len(v))
        tt = t_k + st * rng.normal(size=len(v))
        draws_b.append((2 * mu0 * nn * 1e6 * kb * tt / bt ** 2)[has_t].mean())
        draws_m.append((vv * 1e3 * np.sqrt(mu0 * mp * nn * 1e6) / bt).mean())
    assert f["proton_beta"]["measurement_sigma_of_mean"] == pytest.approx(np.std(draws_b), rel=0.05)
    assert f["alfven_mach"]["measurement_sigma_of_mean"] == pytest.approx(np.std(draws_m), rel=0.05)


def test_coupling_api_without_archive_uncertainties(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from helios.api import server
    from helios.core.downloader import DataDownloader

    served = {"WI_H0_MFI@0": "wi_h0_mfi1m_19951018", "WI_H1_SWE": "wi_h1_swe_19951018"}  # recorded without sigmas

    async def fake(url, timeout=120.0):
        ds = parse_qs(urlparse(url).query)["id"][0]
        return _text(served[ds]) if ds in served else None

    dl = DataDownloader()
    dl.fetch_text = fake
    dl.events = EventDataClient(lambda url: dl.fetch_text(url), tmp_path)
    monkeypatch.setattr(server, "downloader", dl)
    client = TestClient(server.app, base_url=LOCAL)
    r = client.get("/api/analysis/coupling?mission=WIND&start=1995-10-18T20:00&end=1995-10-19T08:00")
    assert r.status_code == 200, r.text
    res = r.json()["result"]
    assert not res["uncertainties_available"]
    assert res["functions"]["vbs_mv_m"]["measurement_sigma_of_mean"] is None
    assert res["functions"]["dynamic_pressure_npa"]["n_eff"] > 3  # sampling intervals need no archive errors
    assert res["functions"]["dynamic_pressure_npa"]["sampling_ci95_of_mean"] is not None
    assert r.json()["provenance"]["coordinates"].startswith("GSM")
    assert client.get("/api/analysis/coupling?mission=WIND&start=1995-10-18T20:00&end=1995-10-22T20:00").status_code == 422


# Lepping et al. (2006, Ann. Geophys. 24, 215) Table 5: sigma B0 (nT), R0 (0.01 AU), asf (%),
# CA (%), theta_A, cone, |theta_A| (deg; printed truncated to integers), with the inputs of
# the WIND MFI cloud table (https://wind.nasa.gov/mfi/mag_cloud_S1.html): B0, chi_R, CA %,
# axis longitude and latitude.
LEPPING_TABLE5 = [
    ("1995-2-8", 15.2, 0.118, -49, 100, 18, (1.3, 1.1, 17.5, 30, 13, 25, 11)),
    ("1995-10-18", 25.9, 0.143, 12, 287, -8, (2.9, 1.1, 16.7, 28, 14, 25, 11)),
    ("1996-12-24", 14.6, 0.156, -47, 82, 26, (1.8, 1.3, 18.6, 40, 16, 31, 13)),
    ("1997-6-9", 15.3, 0.169, 53, 215, -21, (4.7, 1.9, 18.9, 46, 18, 34, 15)),
    ("1997-11-7", 17.6, 0.082, -16, 244, 38, (1.1, 0.7, 12.7, 16, 9, 16, 7)),
    ("1998-3-4", 12.4, 0.152, -6, 121, 21, (1.8, 1.3, 16.9, 29, 15, 25, 12)),
    ("1998-9-25", 18.5, 0.099, 57, 212, 46, (1.9, 1.1, 16.7, 26, 12, 23, 10)),
    ("2000-10-3", 19.4, 0.11, 23, 58, 33, (1.9, 1.0, 15.6, 23, 12, 21, 10)),
    ("2001-4-4", 17.8, 0.121, -86, 281, 8, (1.8, 1.3, 19.9, 38, 15, 31, 12)),
    ("2001-5-28", 11.7, 0.129, 37, 49, -12, (1.9, 1.3, 17.6, 31, 15, 26, 12)),
    ("2002-4-18", 16.2, 0.086, -53, 318, -27, (1.4, 0.9, 15.4, 21, 11, 20, 9)),
    ("2003-3-20", 16.7, 0.118, 66, 238, -81, (1.3, 1.1, 18.6, 33, 14, 27, 11)),
]


@pytest.mark.parametrize("row", LEPPING_TABLE5, ids=[r[0] for r in LEPPING_TABLE5])
def test_flux_rope_uncertainties_reproduce_lepping_2006_table5(row):
    from helios.core.lepping_errors import lepping_uncertainties
    _, b0, chi, ca, phi, theta, pub = row
    u = lepping_uncertainties(b0, chi, ca, phi, theta)
    assert u["b0_nT"] == pytest.approx(pub[0], abs=0.051)
    assert 100 * u["radius_au"] == pytest.approx(pub[1], abs=0.051)
    assert u["asymmetry_factor_percent"] == pytest.approx(pub[2], abs=0.051)
    truncated = [math.floor(u[k] + 1e-6) for k in ("closest_approach_percent", "axis_latitude_deg",
                                                   "axis_cone_deg", "axis_abs_latitude_deg")]
    assert truncated == list(pub[3:])
    assert not u["warnings"]


def test_flux_rope_fit_reports_uncertainties():
    from helios.core.event_analysis import _field, fit_flux_rope
    day, start, end = LEPPING_CLOUDS[0][:3]
    field = _field("BGSE")(parse_hapi_csv(_text(f"wi_h0_mfi1m_{day}")))
    plasma = EVENT_SOURCES["WIND"]["plasma"]["reduce"](parse_hapi_csv(_text(f"wi_h1_swe_{day}")))
    u = fit_flux_rope(field, plasma, start, end, average_minutes=30)["uncertainties"]
    # Our chi_R, CA and axis for 18-20 Oct 1995 are close to the table's, so are the errors
    # (Table 5: 2.9 nT, 28 %, cone 25 deg).
    assert u["b0_nT"] == pytest.approx(2.9, abs=0.4)
    assert u["closest_approach_percent"] == pytest.approx(28, abs=3)
    assert u["axis_cone_deg"] == pytest.approx(25, abs=2)
    from helios.core.lepping_errors import lepping_uncertainties
    assert lepping_uncertainties(15.0, 0.30, 10, 90, 0)["warnings"]  # beyond the 4 nT noise range
    # Cone angle 27 deg: below the 30 deg of the error study, extrapolated (no warning below 25 only).
    assert any("cone angles" in w for w in lepping_uncertainties(15.0, 0.1, 10, 27, 0)["warnings"])


def test_bootstrap_median_in_blocks_matches_all_at_once():
    from helios.core.event_analysis import _bootstrap_bands
    g = np.random.default_rng(3).normal(size=(40, 300))
    g[::7, ::5] = np.nan
    out = _bootstrap_bands(g, 1000, 1)  # 40 x 300 values: two blocks of resamples
    counts = np.random.default_rng(1).multinomial(40, np.full(40, 1 / 40), size=1000)
    idx = np.array([np.repeat(np.arange(40), c) for c in counts])
    direct = np.nanpercentile(np.nanmedian(g[idx], axis=1), 2.5, axis=0)
    assert out["median_ci95_low"] == [round(float(v), 3) for v in direct]


def test_superposed_epoch_onset_is_a_bin_edge():
    from helios.core.event_analysis import superposed_epoch
    onset = pd.Timestamp("2020-01-01", tz="UTC")
    recs = [{"time_tag": (onset + pd.Timedelta(minutes=m)).strftime("%Y-%m-%d %H:%M:%S"), "x": float(m >= 0)}
            for m in range(-75, 60)]
    res = superposed_epoch([(onset, recs)], ["x"], 1.25, 1, cadence_minutes=10)
    assert 0.0 in res["epoch_hours"] and res["epoch_hours"][0] == pytest.approx(-80 / 60)
    i0 = res["epoch_hours"].index(0.0)
    assert res["statistics"]["x"]["mean"][i0 - 1] == 0.0 and res["statistics"]["x"]["mean"][i0] == 1.0


def _sta_client(monkeypatch, tmp_path, day):
    """The API with STEREO-A 1-min field and plasma (one CDAWeb dataset) served from tests/data."""
    from fastapi.testclient import TestClient
    from urllib.parse import parse_qs, urlparse
    from helios.api import server
    from helios.core.downloader import DataDownloader

    async def fake(url, timeout=120.0):
        q = parse_qs(urlparse(url).query)
        if q["id"][0] != "STA_L2_MAGPLASMA_1M":
            return None
        return _text(f"sta_magplasma_{'field' if 'BFIELDRTN' in q['parameters'][0] else 'plasma'}_{day}")

    dl = DataDownloader()
    dl.fetch_text = fake
    dl.events = EventDataClient(lambda url: dl.fetch_text(url), tmp_path)
    monkeypatch.setattr(server, "downloader", dl)
    return TestClient(server.app, base_url=LOCAL)


def test_stereo_a_shock_in_rtn_as_gse_axes(monkeypatch, tmp_path):
    """
    STEREO-A, 25 Jun 2012 20:55:59 (L. K. Jian's STEREO shock list: forward, B2/B1 2.27). RTN is
    used as (-R, -T, N), so the forward shock's normal points sunward-negative as at L1, and the
    answer names the frame. Timing and the time shift need a monitor upstream of the Earth.
    """
    client = _sta_client(monkeypatch, tmp_path, "20120625")
    body = client.get("/api/analysis/shock?mission=STEREO-A&time=2012-06-25T20:55:59&upstream_minutes=8"
                      "&downstream_minutes=8&exclude_after_minutes=2&refine=false").json()
    r = body["result"]
    assert body["provenance"]["coordinates"].startswith("RTN given as (-R, -T, N)")
    assert r["shock_type"] == "FF" and r["field_ratio"] == pytest.approx(2.27, abs=0.05)
    assert r["methods"]["MX3"]["normal_gse"][0] < -0.5 and r["upstream"]["V_gse_kms"][0] < -300
    assert r["methods"]["MX3"]["shock_speed_kms"] > 0 and "ipshocks" not in r and "icme_list" not in r
    assert client.get("/api/analysis/coupling?mission=STEREO-A&start=2012-06-25T20:30&end=2012-06-25T21:20").status_code == 422
    assert client.get("/api/analysis/timing?reference=STEREO-A&time=2012-06-25T20:55:59").status_code == 422


def test_stereo_a_2012_july_23(monkeypatch, tmp_path):
    """
    23-24 Jul 2012 at STEREO-A (Liu et al. 2014, Nat. Commun. 5, 3481): peak field 109 +- 1 nT in
    the first ICME; the 1-min field peaks at 109.0 nT at 00:51:58 on 24 Jul. PLASTIC has no proton
    moments across the event (beyond the detector ranges, as the paper says), so the shock
    analysis has no plasma to work with.
    """
    from helios.core.archive import parse_hapi_csv
    field = EVENT_SOURCES["STEREO-A"]["field"]["reduce"](parse_hapi_csv(_text("sta_magplasma_field_20120723")))
    b = np.linalg.norm(field.to_numpy(float), axis=1)
    assert round(b.max(), 1) == 109.0 and field.index[b.argmax()].strftime("%H:%M") == "00:51"
    client = _sta_client(monkeypatch, tmp_path, "20120723")
    r = client.get("/api/analysis/shock?mission=STEREO-A&time=2012-07-23T20:55:25")
    assert r.status_code == 404 and "plasma" in r.json()["detail"]
