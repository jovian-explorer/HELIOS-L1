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

client = TestClient(app)


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
