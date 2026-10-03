"""
Regression tests for scientific corrections. Each test pins a value or behaviour
that was wrong in an earlier version, with the reference derivation in the docstring.
"""
import math

import numpy as np
import pytest

from helios.core.science import SpaceWeatherPhysics


def test_akasofu_epsilon_includes_4pi_over_mu0():
    """
    Perreault & Akasofu (1978): epsilon = v B^2 sin^4(theta/2) l0^2 in Gaussian units.
    In SI this is (4 pi / mu_0) v B^2 sin^4(theta/2) l0^2 with 4 pi / mu_0 = 1e7.
    v = 400 km/s, B = 10 nT purely southward, l0 = 7 R_E:
    1e7 * 4e5 * 1e-16 * (7 * 6.371e6)^2 = 7.955e11 W = 795.5 GW.
    """
    eps = SpaceWeatherPhysics.akasofu_epsilon(400.0, 10.0, 0.0, -10.0)
    expected = 1e7 * 4e5 * 1e-16 * (7.0 * 6.371e6) ** 2 / 1e9
    assert eps == pytest.approx(expected, rel=1e-6)
    assert 700.0 < eps < 900.0


def test_shue_1998_flaring_uses_ln_pdyn():
    """Shue et al. (1998): alpha = (0.58 - 0.007 Bz)(1 + 0.024 ln Dp); Dp = 4 nPa, Bz = 0 -> 0.5993."""
    res = SpaceWeatherPhysics.calculate_magnetospheric_boundaries(4.0, 0.0, model="shue")
    expected = 0.58 * (1.0 + 0.024 * math.log(4.0))
    assert res["magnetopause"]["flaring_alpha"] == pytest.approx(expected, abs=1e-9)


@pytest.mark.parametrize("flux, label", [
    (5.3e-4, "X5.3"), (1.7e-3, "X17.0"), (1.0e-4, "X1.0"), (9.99e-5, "M9.9"),
    (2.1e-5, "M2.1"), (3.4e-6, "C3.4"), (7.0e-7, "B7.0"), (4.0e-8, "A4.0"),
])
def test_goes_flare_class_labels(flux, label):
    assert SpaceWeatherPhysics.goes_flare_class(flux) == label


def test_noaa_scales_report_actual_flare_class_and_no_invented_proton_flux():
    cls = SpaceWeatherPhysics.classify_noaa_scales(kp=3.0, bz_gsm=-2.0, xray_flux=5.3e-4)
    # An X5.3 flare used to be labelled "X1".
    assert cls["flare_class"].startswith("X5.3")
    assert cls["r_level"] == 3
    # Without a proton measurement no flux value may be reported.
    assert cls["proton_flux_pfu"] is None
    assert "No proton data" in cls["s_scale"]
    # An A-class background used to be labelled "B".
    quiet = SpaceWeatherPhysics.classify_noaa_scales(kp=1.0, bz_gsm=1.0, xray_flux=4e-8, proton_flux=0.3)
    assert quiet["flare_class"].startswith("A4.0")
    assert quiet["proton_flux_pfu"] == 0.3


def test_forecaster_newell_uses_transverse_field_and_tolerates_gaps():
    """Newell et al. (2007) use B_T = sqrt(By^2 + Bz^2); a large Bx must not add coupling."""
    from helios.core.ml_forecast import SpaceWeatherForecaster as F
    # |B| = 10 nT but By = 0, Bz = -2 nT: B_T = 2 nT.
    expected = 400.0 ** (4.0 / 3.0) * 2.0 ** (2.0 / 3.0)
    assert F.calculate_newell_coupling(400.0, 10.0, -2.0, 0.0) == pytest.approx(expected, rel=1e-3)
    assert F.calculate_newell_coupling(400.0, 10.0, -2.0, 0.0) == pytest.approx(
        SpaceWeatherPhysics.newell_coupling(400.0, 0.0, -2.0), rel=1e-3)
    # The newest record being a gap used to raise TypeError (float(None)).
    recs = [{"time_tag": "a", "speed": 500.0, "bz_gsm": -8.0, "by_gsm": 1.0, "bt": 9.0, "dynamic_pressure": 3.0},
            {"time_tag": "b", "speed": None, "bz_gsm": None, "by_gsm": None, "bt": None, "dynamic_pressure": None}]
    out = F.forecast_geomagnetic_storm(recs)
    assert len(out["predictions_timeline"]) == 12
    assert out["current_coupling"]["newell_coupling_rate"] > 10000


def test_psd_is_one_sided_and_integrates_to_variance():
    """White noise of variance s^2 sampled every dt has a one-sided PSD of 2 s^2 dt."""
    rng = np.random.default_rng(1)
    dt, sigma = 60.0, 3.0
    x = rng.normal(0.0, sigma, 4096)
    res = SpaceWeatherPhysics.power_spectral_density(x.tolist(), dt_seconds=dt)
    level = float(np.mean(res["power_density"]))
    assert level == pytest.approx(2.0 * sigma ** 2 * dt, rel=0.25)
    assert res["dt_seconds"] == dt


def test_psd_gaps_are_interpolated_not_spliced():
    """Removing gap samples would shift the spectral peak; interpolation keeps it in place."""
    dt = 60.0
    n = 512
    f0 = 1.0 / (32 * dt)
    t = np.arange(n) * dt
    x = np.sin(2 * np.pi * f0 * t).tolist()
    for i in range(100, 180):  # a 15 % gap
        x[i] = None
    res = SpaceWeatherPhysics.power_spectral_density(x, dt_seconds=dt)
    peak_f = res["frequencies_hz"][int(np.argmax(res["power_density"]))]
    assert peak_f == pytest.approx(f0, rel=0.05)
    assert res["gap_fraction"] == pytest.approx(80 / 512, abs=1e-3)


def test_spectrum_api_uses_record_cadence():
    """The offline model is 5-minute data; the API used to assume 60 s, putting every frequency 5x too high."""
    from fastapi.testclient import TestClient
    from helios.api.server import app
    res = TestClient(app).get("/api/spectrum?mission_id=DSCOVR&parameter=bz_gsm").json()
    assert res["dt_seconds"] == 300.0
    n = 24 * 12  # 24 h of 5-minute samples
    assert res["frequencies_hz"][0] == pytest.approx(1.0 / (n * 300.0), rel=1e-3)


def _storm_records(step_min, hours=6):
    from datetime import datetime, timedelta
    t0 = datetime(2026, 10, 2, 0, 0, 0)
    return [{"time_tag": (t0 + timedelta(minutes=i * step_min)).strftime("%Y-%m-%d %H:%M:%S"),
             "speed": 600.0, "bz_gsm": -15.0, "dynamic_pressure": 5.0}
            for i in range(int(hours * 60 / step_min) + 1)]


def test_dst_simulation_independent_of_cadence():
    """
    Burton model with Ey = 9 mV/m: Q = -4.4 (9 - 0.5) = -37.4 nT/h, tau = 7.7 h.
    After 6 h: Dst* = -5 e^(-6/7.7) + Q tau (1 - e^(-6/7.7)) ~ -158.8 nT, regardless
    of whether the inputs are 1-minute or 5-minute samples (1-minute data used to be
    integrated as if each step lasted 5 minutes).
    """
    from helios.core.aurora_model import AuroralModel
    tau, q = 7.7, -4.4 * (9.0 - 0.5)
    decay = math.exp(-6.0 / tau)
    expected_star = -5.0 * decay + q * tau * (1.0 - decay)
    p_term = 7.26 * math.sqrt(5.0) - 11.0
    one_min = AuroralModel.simulate_dst_evolution(_storm_records(1))[-1]["dst_predicted_nt"]
    five_min = AuroralModel.simulate_dst_evolution(_storm_records(5))[-1]["dst_predicted_nt"]
    # The first record carries one default (5-min) step before the time stamps take over.
    assert five_min == pytest.approx(expected_star + p_term, abs=3.0)
    assert one_min == pytest.approx(five_min, abs=3.0)


def test_dst_simulation_handles_gaps():
    from helios.core.aurora_model import AuroralModel
    recs = _storm_records(5, hours=1)
    recs[3]["speed"] = None
    out = AuroralModel.simulate_dst_evolution(recs)
    assert out[3]["ey_electric_field_mvm"] is None
    assert len(out) == len(recs)
