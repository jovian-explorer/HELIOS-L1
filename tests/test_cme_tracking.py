"""
Coronagraph tools (helios.core.cme_tracking): J-map, front track, height-time fit,
projection correction and the hand-over to the CME arrival solver, on synthetic frames with a
front of known speed. Checked on real data (LASCO C3, 10 September 2017, PA 262): see the
CHANGELOG entry.
"""
import io
import math
from datetime import datetime, timedelta

import numpy as np
import pytest
from PIL import Image

from helios.core import cme_tracking as ct

SIZE, RSUN_PX = 512, 256 / 30.0  # a C3-like picture: +-30 R_sun
V_KMS = 1200.0


def _frame(t_s, pa_deg=270.0, r0=5.0):
    """Sun-centred picture with a bright front at r0 + V t (R_sun) along pa_deg and noise elsewhere."""
    rng = np.random.default_rng(int(t_s))
    img = rng.normal(60, 3, (SIZE, SIZE))
    front = r0 + V_KMS * t_s / ct.R_SUN_KM
    y, x = np.mgrid[:SIZE, :SIZE]
    rr = np.hypot(x - SIZE / 2, y - SIZE / 2) / RSUN_PX
    pa = np.degrees(np.arctan2(-(x - SIZE / 2), -(y - SIZE / 2))) % 360  # from north through east (left)
    lobe = (np.abs(((pa - pa_deg + 180) % 360) - 180) < 20) & (rr < front) & (rr > front - 3)
    img[lobe] += 120
    buf = io.BytesIO()
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert("RGBA").save(buf, format="PNG")
    return buf.getvalue()


def _frames(n=10, step_s=720, pa=270.0):
    t0 = datetime(2024, 5, 9, 9, 0)
    return [{"date": (t0 + timedelta(seconds=k * step_s)).strftime("%Y-%m-%d %H:%M:%S"), "png": _frame(k * step_s, pa),
             "center_px": [SIZE / 2, SIZE / 2], "rsun_px": RSUN_PX} for k in range(n)]


def test_jmap_track_and_fit_recover_the_front_speed():
    jm = ct.jmap(_frames(), pa_deg=270.0, r_min=4.0, r_max=29.0)
    assert len(jm["times"]) == 9 and jm["png_data_url"].startswith("data:image/png;base64,")
    pts = ct.auto_track(jm["values"], jm["r_rsun"], jm["times"])
    assert len(pts) >= 6
    fit = ct.fit_height_time(pts, 1)
    assert fit["speed_kms"] == pytest.approx(V_KMS, rel=0.08)
    # Nothing at the opposite position angle.
    jm_e = ct.jmap(_frames(), pa_deg=90.0, r_min=4.0, r_max=29.0)
    assert len(ct.auto_track(jm_e["values"], jm_e["r_rsun"], jm_e["times"], k=5.0)) <= 1


def test_quadratic_fit_and_errors():
    t0 = datetime(2024, 5, 9)
    a = 50.0 / 1000.0  # km/s^2
    pts = [{"time": (t0 + timedelta(minutes=10 * k)).isoformat(),
            "r_rsun": (3.0 * ct.R_SUN_KM + 800 * 600 * k + 0.5 * a * (600 * k) ** 2) / ct.R_SUN_KM} for k in range(8)]
    f = ct.fit_height_time(pts, 2)
    assert f["acceleration_ms2"] == pytest.approx(50.0, abs=0.01)
    assert f["speed_kms"] == pytest.approx(800 + a * 4200, abs=0.1)  # at the last point
    with pytest.raises(ValueError):
        ct.fit_height_time(pts[:3], 2)


def test_projection_correction():
    # Limb event seen from Earth: no correction; 60 deg from the line of sight: 1/sin(60).
    assert ct.projection(1000.0, 90.0, 0.0)["radial_speed_kms"] == pytest.approx(1000.0)
    p = ct.projection(1000.0, 30.0, 0.0)
    assert p["psi_deg"] == pytest.approx(30.0) and p["radial_speed_kms"] == pytest.approx(2000.0, rel=1e-3)
    # The same source seen from 70 deg west of Earth (STEREO-A-like): psi = 40 deg.
    assert ct.projection(1000.0, 30.0, 0.0, 70.0)["psi_deg"] == pytest.approx(40.0)
    halo = ct.projection(1000.0, 5.0, 5.0)
    assert halo["radial_speed_kms"] is None and "halo" in halo["note"]


def test_observer_longitude_and_solver_inputs():
    when = datetime(2026, 10, 10)
    assert ct.observer_longitude("lasco_c3", when)["longitude_deg"] == 0.0
    sta = ct.observer_longitude("cor2", when)
    assert sta["spacecraft"] == "STEREO_A" and sta["longitude_deg"] == pytest.approx(70.7, abs=1.0)
    s = ct.solver_inputs({"height_end_rsun": 20.0, "time_end": "2024-05-09 10:00:00"}, 1500.0)
    from helios.core.coronagraph import CoronagraphAnalyzer
    k = CoronagraphAnalyzer.calculate_cme_kinematics(s["r1_rsun"], s["r2_rsun"], s["dt_minutes"], s["launch_time"])
    assert k["initial_speed_kms"] == pytest.approx(1500.0, abs=0.5) and k["start_height_rsun"] == 20.0
    assert k["predicted_earth_arrival"] > "2024-05-09 10:00"


def test_fit_endpoint():
    from fastapi.testclient import TestClient
    from helios.api import server
    c = TestClient(server.app, base_url="http://127.0.0.1:8765")
    pts = [{"time": f"2017-09-10 16:{m:02d}:05", "r_rsun": r} for m, r in ((18, 9.10), (30, 12.31), (42, 15.77), (54, 18.95))]
    body = c.post("/api/coronagraph/fit", json={"points": pts, "instrument": "lasco_c3",
                                                "source_lon_deg": 88, "source_lat_deg": -9}).json()
    # CDAW leading-edge heights of the 10 September 2017 CME at PA 262 (C3).
    assert body["fit"]["speed_kms"] == pytest.approx(3200, rel=0.05)
    assert body["projection"]["psi_deg"] == pytest.approx(math.degrees(math.acos(math.cos(math.radians(9)) * math.cos(math.radians(88)))), abs=0.1)
    assert body["solver_inputs"]["r2_rsun"] == body["fit"]["height_end_rsun"]
    assert c.post("/api/coronagraph/fit", json={"points": pts[:2]}).status_code == 422
