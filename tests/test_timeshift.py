"""Time shift to the bow shock nose (helios/core/timeshift.py, /api/analysis/timeshift)."""
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from helios.core import timeshift as ts

EVENTS = Path(__file__).parent / "data" / "hapi" / "events"
LOCAL = "http://127.0.0.1:8765"
T0 = pd.Timestamp("2020-01-01", tz="UTC")


def _unit(v):
    v = np.asarray(v, dtype=float)
    return v / np.linalg.norm(v)


def _frames(b, n_cm3=5.0, v=(-400.0, 0.0, 0.0), t_k=1e5, x_km=1.5e6):
    """15-s field `b` with constant plasma (64 s) and position (60 s)."""
    times = T0 + pd.to_timedelta(np.arange(len(b)) * 15, unit="s")
    field = pd.DataFrame(b, columns=["bx", "by", "bz"], index=times)
    pt = pd.date_range(times[0] - pd.Timedelta(hours=1), times[-1] + pd.Timedelta(hours=1), freq="64s")
    plasma = pd.DataFrame({"vx": v[0], "vy": v[1], "vz": v[2], "n": n_cm3, "t": t_k}, index=pt)
    pos = pd.DataFrame({"x": x_km, "y": 0.0, "z": 0.0}, index=pd.date_range(pt[0], pt[-1], freq="60s"))
    return field, plasma, pos


def test_cross_product_normal_and_delay_of_a_tangential_discontinuity():
    # A rotation by 60 deg across a plane with normal n0, convected past the spacecraft: the
    # cross product of the field before and after it is n0, and the delay is n0.dR / n0.V.
    n0 = _unit([1.0, 0.5, 0.2])
    u = _unit(np.cross(n0, [0.0, 0.0, 1.0]))
    w = np.cross(n0, u)
    b1, b2 = 5 * u, 5 * (np.cos(np.radians(60)) * u + np.sin(np.radians(60)) * w)
    b = np.array([b1 if i < 200 else b2 for i in range(400)])
    field, plasma, pos = _frames(b)
    tsec = ts._seconds(field.index)
    v = np.tile([-400.0, ts.ORBITAL_VY_KMS, 0.0], (len(b), 1))
    out = ts.phase_front_normals(b, tsec, v)
    near = np.arange(195, 206)
    assert (out["source"][near] == 1).all()
    nn = out["normal"][near]
    # angle by atan2(|a x b|, a.b): arccos near 1 turns one rounding step into 1e-6 deg (macOS CI)
    assert np.degrees(np.arctan2(np.linalg.norm(np.cross(nn, n0), axis=1), nn @ n0)).max() < 1e-6
    # Away from it the field is constant: no cross product and no MVAB-0 (no variance; before
    # the floor on the eigenvalues, round-off passed as normals in such windows).
    assert set(out["source"][:150]) <= {0} and set(out["source"][250:]) <= {0}

    res = ts.shift_to_bow_shock(field, plasma, pos, T0, T0 + pd.Timedelta(hours=3))
    m = res["minutes"].dropna(subset=["delay_s"])
    va = np.array([-400.0, ts.ORBITAL_VY_KMS, 0.0])
    bsn = m[["bsn_x", "bsn_y", "bsn_z"]].to_numpy() * ts.EARTH_RADIUS_KM
    expected = (bsn - np.array([1.5e6, 0, 0])) @ n0 / (n0 @ va)
    assert len(m) >= 2 and np.allclose(m["delay_s"], expected, atol=1e-3)
    # The bow shock nose lies along the aberrated flow, sunward of the Shue et al. magnetopause.
    assert np.allclose(m["bsn_y"] / m["bsn_x"], va[1] / va[0]) and (m["bsn_x"] > 11).all()
    src = res["normal_sources"]
    assert src["cross_product"] >= len(near) and src["mvab0"] == 0 and src["interpolated"] == 0


def test_mvab0_normal_of_planar_fluctuations():
    # Fluctuations in the plane of the mean field and u (variance 1 nT^2) and weak ones along
    # n0 (0.01 nT^2): MVAB-0 finds n0; the before/after averages differ too little for a
    # cross product.
    rng = np.random.default_rng(3)
    n0 = _unit([1.0, -0.4, 0.3])
    e = _unit(np.cross(n0, [0.0, 0.0, 1.0]))
    u = np.cross(n0, e)
    k = 600
    b = 5 * e + rng.normal(0, 1.0, (k, 1)) * u + rng.normal(0, 0.1, (k, 1)) * n0
    tsec = ts._seconds(T0 + pd.to_timedelta(np.arange(k) * 15, unit="s"))
    out = ts.phase_front_normals(b, tsec, np.tile([-450.0, ts.ORBITAL_VY_KMS, 0.0], (k, 1)))
    inner = slice(40, k - 40)
    assert (out["source"][inner] == 2).mean() > 0.95
    ang = np.degrees(np.arccos(np.clip(np.abs(out["normal"][inner] @ n0), -1, 1)))
    assert np.nanmedian(ang) < 2.0
    assert (out["normal"][inner][:, 0] >= 0).all()  # OMNI's sign convention, n_x > 0


def test_wind_cleaning_drops_spikes_and_fields_above_70_nt():
    t = pd.date_range("2015-03-15", periods=40, freq="92s", tz="UTC")
    p = pd.DataFrame({"vx": -400.0 + np.sin(np.arange(40)), "vy": 2.0, "vz": -1.0, "n": 5.0 + 0.1 * np.cos(np.arange(40)),
                      "t": 1e5}, index=t)
    p.iloc[20, p.columns.get_loc("vy")] = 150.0  # a 148 km/s jump in one component
    kept = ts.despike_plasma(p)
    assert len(kept) == 39 and t[20] not in kept.index
    f = pd.DataFrame({"bx": [5.0, 71.0, 50.0], "by": [0.0, 0.0, 50.0], "bz": [0.0, 0.0, 10.0]},
                     index=pd.date_range("2015-03-15", periods=3, freq="3s", tz="UTC"))
    assert list(ts.wind_field_limit(f)["bx"]) == [5.0]  # 71 nT component; |B| 71.4 nT


def _fixture():
    read = lambda name: pd.read_csv(EVENTS / name, index_col=0, parse_dates=True)
    f = read("ac_mfi_pos_20031120_timeshift.csv.gz")
    return f[["bx", "by", "bz"]], read("ac_swe_20031120_timeshift.csv.gz"), f[["x", "y", "z"]], \
        read("omni_hro_1min_20031120_timeshift.csv.gz")


def test_shift_reproduces_omni_in_the_20_november_2003_storm():
    # ACE 16-s MAG, SWEPAM 64-s and position, 15:00-24:00 UT, and OMNI HRO for 18-24 UT (all
    # minutes from ACE, IMF code 71; Dst reached -422 nT at 20 UT, bow shock nose 5-11 R_E).
    field, plasma, pos, omni = _fixture()
    t0, t1 = pd.Timestamp("2003-11-20 18:00", tz="UTC"), pd.Timestamp("2003-11-21 00:00", tz="UTC")
    res = ts.shift_to_bow_shock(field, plasma, pos, t0, t1)
    c = ts.compare_with_omni(res["minutes"], omni[omni["IMF"] == 71][["Timeshift"]])
    pf, flat = c["phase_front"], c["flat"]
    assert c["minutes"] == 339 and abs(c["omni_median_delay_min"] - 46.85) < 0.01
    assert pf["within_1_min_percent"] >= 97 and pf["median_abs_difference_min"] <= 0.1
    assert flat["within_1_min_percent"] <= 20  # a flat delay is off by 4 min on median here
    bsn = (res["minutes"]["bsn_x"] - omni["BSN_x"]).dropna()
    assert abs(bsn.median()) < 0.25 and bsn.abs().quantile(0.9) < 0.35


def test_timeshift_api(monkeypatch):
    from fastapi.testclient import TestClient
    from helios.api import server
    field, plasma, pos, omni = _fixture()

    async def fetch(mission, start, end, coarse=False):
        return {"field": field, "plasma": plasma, "position": pos, "offline": False,
                "datasets": [{"role": "field", "id": "AC_H0_MFI"}, {"role": "plasma", "id": "AC_H0_SWE"}]}

    async def fetch_dataset(spec, start, end, role):
        assert spec["id"] == "OMNI_HRO_1MIN"
        return omni[["IMF", "Timeshift"]], {"role": role, "id": spec["id"]}, True, None

    monkeypatch.setattr(server.downloader.events, "fetch", fetch)
    monkeypatch.setattr(server.downloader.events, "fetch_dataset", fetch_dataset)
    client = TestClient(server.app, base_url=LOCAL)
    q = "start=2003-11-20T18:00&end=2003-11-21T00:00"
    body = client.get(f"/api/analysis/timeshift?mission=ACE&{q}").json()
    r = body["result"]
    assert r["omni_comparison"]["phase_front"]["within_1_min_percent"] >= 97 and r["omni_note"] is None
    assert r["summary"]["minutes"] == len(body["series"]["time_tags"]) and 40 < r["summary"]["delay_median_min"] < 55
    assert body["series"]["omni_delay_min"][0] is not None and "Farris & Russell" in r["method"]
    assert [d["id"] for d in body["provenance"]["datasets"]] == ["AC_H0_MFI", "AC_H0_SWE", "OMNI_HRO_1MIN"]
    csv_text = client.get(f"/api/analysis/timeshift?mission=ACE&{q}&format=csv").text
    lines = [l for l in csv_text.splitlines() if not l.startswith("#")]
    assert lines[0].startswith("time,delay_s,delay_rms_s,flat_delay_s,bsn_x") and lines[0].endswith("omni_timeshift_s")
    assert len(lines) == r["summary"]["minutes"] + 1 and "# OMNI comparison: 339 minutes from ACE" in csv_text
    # DSCOVR is not in OMNI: no comparison, and a note that says why.
    body = client.get(f"/api/analysis/timeshift?mission=DSCOVR&{q}").json()
    assert body["result"]["omni_comparison"] is None and "not among the spacecraft" in body["result"]["omni_note"]
    assert client.get("/api/analysis/timeshift?mission=ACE&start=2003-11-18&end=2003-11-21").status_code == 422
    assert client.get("/api/analysis/timeshift?mission=SOHO&start=2003-11-20&end=2003-11-21").status_code == 404
