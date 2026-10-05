"""
Physics checks for code paths the rest of the suite did not reach: the analytic fallbacks
of the ephemeris engine (used when SPICE or its kernels are missing), checked against SPICE
itself, epoch validation, and the PNG overview export.
"""
import math

import numpy as np
import pytest
from fastapi.testclient import TestClient

import helios.core.spice_engine as spice_mod
from helios.api.server import app
from helios.core.spice_engine import get_spice_engine

# The server only answers requests addressed to a loopback host (helios.api.guard).
LOCAL = "http://127.0.0.1:8765"

client = TestClient(app, base_url=LOCAL)


@pytest.fixture
def no_spice(monkeypatch):
    """Make the engine take its analytic fallbacks."""
    monkeypatch.setattr(spice_mod, "SPICE_AVAILABLE", False)


@pytest.mark.parametrize("elts", [
    # rp (km), e, i, RAAN, argp, M0 (deg), dt (days): a 1-AU-class heliocentric ellipse
    (1.0e8, 0.3, 20.0, 40.0, 60.0, 10.0, 50.0),
    # Parker Solar Probe-like orbit (rp 9.86 R_sun, e 0.88), across perihelion
    (9.86 * 696340.0, 0.8819, 3.4, 77.0, 180.0, 350.0, 3.0),
    # near-circular, inclined
    (1.47e8, 0.0167, 7.0, 0.0, 102.9, 200.0, 200.0),
])
def test_kepler_fallback_matches_spice_conics(elts, monkeypatch):
    """The fallback Kepler solver reproduces spiceypy.conics to < 1 m and < 1 mm/s."""
    engine = get_spice_engine()
    assert spice_mod.SPICE_AVAILABLE
    rp, e, i, o, w, m0, days = elts
    gm = 132712440041.93938
    ref_r, ref_v = engine.compute_conics(rp, e, i, o, w, m0, 0.0, days * 86400.0, primary_gm=gm)
    monkeypatch.setattr(spice_mod, "SPICE_AVAILABLE", False)
    r, v = engine.compute_conics(rp, e, i, o, w, m0, 0.0, days * 86400.0, primary_gm=gm)
    assert np.max(np.abs(r - ref_r)) < 1e-3
    assert np.max(np.abs(v - ref_v)) < 1e-6
    # Energy check against vis-viva: v^2 = GM (2/r - 1/a)
    a = rp / (1.0 - e)
    assert float(np.dot(v, v)) == pytest.approx(gm * (2.0 / np.linalg.norm(r) - 1.0 / a), rel=1e-10)


def test_et_fallback_matches_spice_since_2017():
    """
    Without the leapseconds kernel ET = UTC + 37 s + 32.184 s, valid from 2017-01-01
    (last leap second). SPICE's str2et (with the LSK) is the reference; the fallback
    agrees to the TDB-TT periodic term (< 2 ms).
    """
    engine = get_spice_engine()
    for epoch in ("2017-06-01T00:00:00", "2024-05-10T17:05:00", "2026-10-04T12:00:00"):
        ref = engine.epoch_to_et(epoch)
        spice_mod.SPICE_AVAILABLE = False
        try:
            alt = engine.epoch_to_et(epoch)
            back = engine.et_to_utc(alt)
        finally:
            spice_mod.SPICE_AVAILABLE = True
        assert alt == pytest.approx(ref, abs=2e-3)
        assert back.startswith(epoch)


def test_gm_fallback_matches_kernel(no_spice):
    """Fallback GM values are the DE431/DE440 constants in the bundled PCK."""
    engine = get_spice_engine()
    sun_fallback, earth_fallback = engine.get_body_gm("10"), engine.get_body_gm("399")
    spice_mod.SPICE_AVAILABLE = True
    assert engine.get_body_gm("10") == pytest.approx(sun_fallback, rel=1e-9)
    assert engine.get_body_gm("399") == pytest.approx(earth_fallback, rel=1e-6)


def test_unreadable_epoch_is_rejected():
    """An unreadable epoch used to become a fixed ET in September 2026; now it is a 422."""
    engine = get_spice_engine()
    with pytest.raises(ValueError):
        spice_mod.SPICE_AVAILABLE = False
        try:
            engine.epoch_to_et("not a date")
        finally:
            spice_mod.SPICE_AVAILABLE = True
    for url in ("/api/orbits?epoch=garbage", "/api/ephemeris/spice?epoch=garbage",
                "/api/ephemeris/spice/trajectory?epoch=garbage"):
        res = client.get(url)
        assert res.status_code == 422, url
        assert "Unrecognised epoch" in res.json()["detail"]
    assert client.get("/api/ephemeris/spice?epoch=2024-05-10T12:00:00").status_code == 200


def test_overview_png_export_and_global_style_untouched():
    """The PNG export is a valid image and does not change matplotlib's global defaults."""
    import matplotlib
    before = matplotlib.rcParams["axes.facecolor"]
    res = client.get("/api/export/plot?mission_id=DSCOVR")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("image/png")
    assert res.content[:8] == b"\x89PNG\r\n\x1a\n"
    assert matplotlib.rcParams["axes.facecolor"] == before
    from helios.core.exporter import DataExporter
    assert DataExporter.generate_overview_chart([], "X")[:8] == b"\x89PNG\r\n\x1a\n"


def _rk4_transit(v0, w, gamma, r0, target):
    """Integrate the DBM dv/dt = -gamma (v - w)|v - w| (km, s) with RK4 until r = target."""
    r, v, t, h = r0, v0, 0.0, 60.0
    while r < target:
        def f(vv):
            return -gamma * (vv - w) * abs(vv - w)
        k1 = f(v); k2 = f(v + 0.5 * h * k1); k3 = f(v + 0.5 * h * k2); k4 = f(v + h * k3)
        dv = h * (k1 + 2 * k2 + 2 * k3 + k4) / 6.0
        dr = h * (v + (v + dv)) / 2.0
        if r + dr >= target:  # interpolate the last step
            t += h * (target - r) / dr
            v += dv * (target - r) / dr
            return t, v
        r, v, t = r + dr, v + dv, t + h
    return t, v


@pytest.mark.parametrize("v0, w, gamma", [(1500.0, 420.0, 1e-7), (2459.0, 450.0, 0.5e-7), (300.0, 500.0, 2e-7)])
def test_drag_based_model_matches_numerical_integration(v0, w, gamma):
    """
    Vrsnak et al. (2013) DBM closed form in CoronagraphAnalyzer against an RK4 integration
    of the same equation: Earth transit within 0.05 h and arrival speed within 1 km/s,
    for fast, very fast and slow (accelerating) CMEs.
    """
    from helios.core.coronagraph import CoronagraphAnalyzer as C
    r1, r2 = 5.0, 10.0
    dt_min = (r2 - r1) * C.R_SUN_KM / v0 / 60.0
    out = C.calculate_cme_kinematics(r1, r2, dt_min, ambient_wind_kms=w, gamma_drag=gamma)
    t, v = _rk4_transit(v0, w, gamma, r2 * C.R_SUN_KM, C.AU_KM)
    assert out["transit_to_earth_hours"] == pytest.approx(t / 3600.0, abs=0.05)
    assert out["v_arrival_earth_kms"] == pytest.approx(v, abs=1.0)
    t1, v1 = _rk4_transit(v0, w, gamma, r2 * C.R_SUN_KM, C.L1_DIST_KM)
    assert out["transit_to_l1_hours"] == pytest.approx(t1 / 3600.0, abs=0.05)


def test_gopalswamy_2001_arrival_matches_stepwise_integration():
    """Constant acceleration a = 2.193 - 0.0054 u m/s^2 to 0.76 AU, then coasting (numerical check)."""
    from helios.core.coronagraph import CoronagraphAnalyzer as C
    for u in (500.0, 1000.0, 2000.0):
        out = C.gopalswamy_2001_arrival(u)
        a = (2.193 - 0.0054 * u) / 1000.0
        r, v, t, h = 0.0, u, 0.0, 10.0
        while r < 0.76 * C.AU_KM:
            r += v * h + 0.5 * a * h * h
            v += a * h
            t += h
        t += (C.AU_KM - r) / v
        assert out["transit_hours"] == pytest.approx(t / 3600.0, abs=0.1)
        assert out["arrival_speed_kms"] == pytest.approx(v, abs=0.5)


def test_seven_day_view_joins_archive_and_rtsw_without_overlap(monkeypatch):
    """
    7-day DSCOVR view: CDAWeb archive (5-min bins) up to its last sample, then the RTSW feed
    after it, averaged into 5-minute bins. RTSW rows at or before the last archive sample
    are dropped, the bin means are the means of the 1-minute values, and the provenance
    names both sources.
    """
    import asyncio
    from datetime import datetime, timedelta, timezone
    from helios.core.downloader import DataDownloader

    now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    t_arch_end = (now - timedelta(hours=2)).replace(minute=0)
    arch = [{"time_tag": (t_arch_end - timedelta(minutes=5 * k)).strftime("%Y-%m-%d %H:%M:%S"),
             "speed": 380.0, "density": 4.0, "temperature": 9e4, "bz_gsm": 1.0, "by_gsm": 0.5, "bx_gsm": 2.0,
             "bt": 3.0, "data_source": "observed"} for k in range(12)][::-1]

    async def fake_archive(self, mission_id, start, end, cadence_minutes=1):
        return {"records": arch, "provenance": {"description": "CDAWeb DSCOVR test archive.",
                                                "source_spacecraft": ["DSCOVR"], "datasets": ["DSCOVR_H0_MAG"]}}

    # RTSW from one hour before the archive end to now, speed = 500 + minute index
    rows_t = [t_arch_end - timedelta(minutes=60) + timedelta(minutes=m) for m in range(int((now - t_arch_end).total_seconds() // 60) + 60)]
    mag = [{"time_tag": t.strftime("%Y-%m-%dT%H:%M:%S"), "active": True, "source": "DSCOVR", "overall_quality": 0,
            "bt": 6.0, "bx_gsm": 1.0, "by_gsm": 2.0, "bz_gsm": -5.0} for t in rows_t]
    wind = [{"time_tag": t.strftime("%Y-%m-%dT%H:%M:%S"), "active": True, "source": "DSCOVR", "overall_quality": 0,
             "proton_density": 5.0, "proton_speed": 500.0 + i, "proton_temperature": 1e5} for i, t in enumerate(rows_t)]

    async def fake_rtsw(self):
        return mag, wind

    monkeypatch.setattr(DataDownloader, "get_archive_bundle", fake_archive)
    monkeypatch.setattr(DataDownloader, "_fetch_rtsw", fake_rtsw)
    out = asyncio.run(DataDownloader().get_telemetry_bundle("DSCOVR", span_days=7))
    recs = out["records"]
    times = [r["time_tag"] for r in recs]
    assert times == sorted(times) and len(times) == len(set(times))
    last_arch = arch[-1]["time_tag"]
    head = [r for r in recs if r["time_tag"] <= last_arch]
    assert [r["time_tag"] for r in head] == [a["time_tag"] for a in arch]
    assert all(r["speed"] == 380.0 for r in head), [(r["time_tag"], r["speed"]) for r in head if r["speed"] != 380.0]
    tail = [r for r in recs if r["time_tag"] > last_arch]
    assert tail, "RTSW after the archive end is kept"
    # First full RTSW bin after the archive: minutes 65..69 after the RTSW start (archive end + 5 min)
    first = tail[0]
    i0 = 60 + 5
    assert first["time_tag"] == (t_arch_end + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
    assert first["speed"] == pytest.approx(500.0 + i0 + 2.0)  # mean of 5 consecutive minutes
    assert out["provenance"]["kind"] == "observed"
    assert "CDAWeb DSCOVR test archive." in out["provenance"]["description"]
    assert f"After {last_arch} UTC" in out["provenance"]["description"]
