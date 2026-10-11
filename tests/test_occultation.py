"""
Radio occultation (helios.core.occultation): integrals along a straight ray with analytic
answers, the field model, the 180-degree correction and the Horizons-to-SPK writer. The
network test (HELIOS_NETWORK_TESTS=1) checks the elongation of Mars Express from DSS-63
during the solar conjunction of November 2023 against JPL Horizons.
"""
import math
import os
from datetime import datetime

import numpy as np
import pytest

from helios.core import occultation as oc

R = oc.R_SUN_KM


def _ray(p_rsun, half_length_rsun=2000.0):
    """A ray from (-L, p) to (+L, p) in the Sun's frame: closest approach p at the middle."""
    length = 2 * half_length_rsun * R
    u = np.array([1.0, 0.0, 0.0])
    sun = np.array([half_length_rsun * R, -p_rsun * R, 0.0])  # Sun as seen from the station
    return {"u": u, "sun": sun, "rot": np.eye(3), "length_km": length, "d_km": float(sun @ u),
            "impact_km": p_rsun * R, "impact_rsun": p_rsun}


def test_tec_of_an_inverse_square_corona():
    # Integrals of r^-k over a line at impact p: 2 atan(L/p)/p for k = 2 (finite line of half
    # length L), pi/(2 p^3) and 3 pi/(8 p^5) for k = 4 and 6.
    g = _ray(50.0)
    tec = oc.ray_integrals(g, "leblanc", n=8001)["tec_el_m2"]
    p = 50.0
    expected = (3.3e5 * 2 * math.atan(2000.0 / p) / p + 4.1e6 * math.pi / (2 * p ** 3) + 8.0e7 * 3 * math.pi / (8 * p ** 5)) * 1e6 * R * 1e3
    assert tec == pytest.approx(expected, rel=2e-3)
    assert oc.density_cm3(215.0) == pytest.approx(7.2, abs=0.2)  # about 7 cm^-3 at 1 AU
    assert oc.density_cm3(1.0, "allen") == pytest.approx(4.54e8, rel=1e-3)


def test_faraday_rotation_of_a_radial_and_a_spiral_field():
    g = _ray(5.0)
    radial = oc.parker_field(3.5, 1, 1e9)  # no spiral: B . dl is antisymmetric about the closest point
    spiral = oc.parker_field(3.5, 1, 400.0)
    rm_radial = oc.ray_integrals(g, "leblanc", radial)["rm_rad_m2"]
    rm_spiral = oc.ray_integrals(g, "leblanc", spiral)["rm_rad_m2"]
    rm_inward = oc.ray_integrals(g, "leblanc", oc.parker_field(3.5, -1, 400.0))["rm_rad_m2"]
    assert abs(rm_radial) < 1e-3 * abs(rm_spiral)
    assert rm_inward == pytest.approx(-rm_spiral)


def test_unwrap_180():
    r = oc.unwrap_180([170, 178, 4, 12, 20])
    assert r["corrected_deg"] == [170, 178, 184, 192, 200] and r["jumps_removed"] == 1
    m = oc.unwrap_180([170, 178, 4, 12, 20], [350, 358, 364, 372, 380])
    assert m["corrected_deg"][0] == 350 and m["shift_multiples_of_180"] == 1
    with pytest.raises(ValueError):
        oc.unwrap_180([1, 2], [1])


def test_horizons_vectors_become_a_readable_spk(tmp_path):
    from helios.core.spice_engine import get_spice_engine
    import spiceypy as sp
    get_spice_engine()
    # A body moving at 30 km/s along x, states every 10 min (Horizons CSV layout).
    rows = []
    jd0 = 2460267.5
    for k in range(200):
        t = k * 600.0
        rows.append(f"{jd0 + t / 86400:.9f}, A.D. x, {1.5e8 + 30 * t:.6f}, 1.0e6, 0.0, 30.0, 0.0, 0.0,")
    text = "header\n$$SOE\n" + "\n".join(rows) + "\n$$EOE\n"

    def fetch(url):
        assert "COMMAND=%27-999%27" in url and "VECTORS" in url
        return text.encode()
    path = oc.horizons_spk("-999", datetime(2023, 11, 17, 1), datetime(2023, 11, 17, 3), str(tmp_path), fetch)
    sp.furnsh(path)
    try:
        et = (jd0 + 3000 / 86400 - 2451545.0) * 86400.0
        pos, _ = sp.spkpos("-999", et, "J2000", "NONE", "0")
        assert pos[0] == pytest.approx(1.5e8 + 30 * 3000, abs=1e-3)
    finally:
        sp.unload(path)
    with pytest.raises(ValueError):
        oc.user_spk("https://example.com/x.bsp", str(tmp_path))


def test_unwrap_endpoint_and_option_list():
    from fastapi.testclient import TestClient
    from helios.api import server
    c = TestClient(server.app, base_url="http://127.0.0.1:8765")
    assert "DSS-63" in c.get("/api/occultation/options").json()["stations"]
    assert c.post("/api/occultation/unwrap", json={"measured_deg": [170, 4]}).json()["corrected_deg"] == [170, 184]
    assert c.post("/api/occultation", json={"start": "2023-11-14", "end": "2023-11-15", "field_model": "dipole"}).status_code == 422


@pytest.mark.skipif(os.environ.get("HELIOS_NETWORK_TESTS") != "1", reason="network test (HELIOS_NETWORK_TESTS=1)")
def test_mars_express_conjunction_elongation(tmp_path):
    k = oc.generic_kernels(str(tmp_path))
    s = oc.horizons_spk("-41", datetime(2023, 11, 16), datetime(2023, 11, 20), str(tmp_path))
    oc.furnish(k + [s])
    rows = oc.occultation("-41", "DSS-63", datetime(2023, 11, 16, 12), datetime(2023, 11, 19, 12), 720, 8420.0)
    # JPL Horizons S-O-T angle from the geocentre, every 12 h from 16 November 12 UT
    assert [r["elongation_deg"] for r in rows] == pytest.approx([0.5366, 0.3897, 0.2470, 0.1353, 0.1410, 0.2595, 0.4024], abs=0.003)
    assert all(r["blocked_by_sun"] == (r["impact_rsun"] < 1.0) for r in rows)


def test_interval_checks_come_before_any_download():
    from fastapi.testclient import TestClient
    from helios.api import server
    c = TestClient(server.app, base_url="http://127.0.0.1:8765")
    for body, text in (({"start": "2023-11-16", "end": "2023-11-14"}, "after the start"),
                       ({"start": "2023-11-01", "end": "2023-11-14", "step_minutes": 1}, "step of at least"),
                       ({"start": "x", "end": "2023-11-14"}, "ISO 8601"),
                       ({"start": "2023-11-14", "end": "2023-11-15", "field_model": "pfss", "pfss_source": "hmi"}, "JSOC")):
        r = c.post("/api/occultation", json=body)
        assert r.status_code == 422 and text in r.json()["detail"], r.json()


def test_interrupted_spk_write_does_not_block_the_next(tmp_path):
    from datetime import datetime
    rows = "\n".join(f"{2460267.5 + k / 144:.9f}, A.D. x, {1.5e8 + k}, 1.0, 0.0, 30.0, 0.0, 0.0," for k in range(100))
    text = ("$$SOE\n" + rows + "\n$$EOE\n").encode()
    path_args = ("-998", datetime(2023, 11, 17, 1), datetime(2023, 11, 17, 2), str(tmp_path))
    first = oc.horizons_spk(*path_args, lambda url: text)
    os.remove(first)
    open(first + ".tmp", "wb").write(b"partial")  # left by an interrupted write
    assert oc.horizons_spk(*path_args, lambda url: text) == first and os.path.exists(first)
