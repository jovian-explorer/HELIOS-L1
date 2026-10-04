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
    assert res["warnings"] == []


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
    # Sonnerup & Scheible (1998) eq. 8.23 for the normal about the intermediate axis.
    expect = math.degrees(math.sqrt(l3 / (k - 1) * (l2 + l3 - l3) / (l2 - l3) ** 2))
    assert res["angular_error_deg"]["normal_about_intermediate"] == pytest.approx(expect)
    assert res["mean_normal_field_nT"] >= 0
    x1, x2, x3 = (np.array(res["eigenvectors"][k_]) for k_ in ("max", "intermediate", "min"))
    assert np.dot(np.cross(x1, x2), x3) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        minimum_variance(b[:3])


def test_event_data_client_fetches_native_cadence_and_caches(tmp_path):
    served = {"WI_H0_MFI@1": "wi_h0_mfi3s_20150317", "WI_H1_SWE": "wi_h1_swe_20150317"}
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
    assert out["position"]["x"].iloc[0] == pytest.approx(252.85 * 6371.2, rel=1e-3)
    assert [d["id"] for d in out["datasets"]] == ["WI_H0_MFI@1", "WI_H1_SWE"]
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
    client = TestClient(server.app)

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
    assert "attachment; filename=HELIOS_shock_WIND_20150317T0400.json" in dl_file.headers["content-disposition"]
    assert '"hapi_url"' in dl_file.text

    mva = client.get("/api/analysis/mva?mission=WIND&start=2015-03-17T04:01&end=2015-03-17T04:25").json()
    assert mva["result"]["n_vectors"] > 400 and len(mva["result"]["eigenvalues_nT2"]) == 3
    assert client.get("/api/analysis/mva?mission=WIND&start=2015-03-17T04:01&end=2015-03-17T04:25"
                      "&average_seconds=60").json()["result"]["n_vectors"] == 24

    assert client.get("/api/analysis/shock?mission=SOHO&time=2015-03-17T04:00").status_code == 404
    assert client.get("/api/analysis/mva?mission=WIND&start=2015-03-17&end=2015-03-21").status_code == 422
    assert client.get("/api/analysis/shock?mission=ACE&time=2015-03-17T04:00").status_code == 404  # nothing served
