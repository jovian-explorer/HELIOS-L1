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
    O'Brien & McPherron (2000) with VBs = 600 km/s * 15 nT = 9 mV/m:
    Q = -4.4 (9 - 0.49) nT/h, tau = 2.4 exp(9.74 / (4.69 + 9)) h. From Dst* = 0, after 6 h
    Dst* = Q tau (1 - e^(-6/tau)), the same for 1-minute and 5-minute samples (1-minute
    data used to be integrated as if each step lasted 5 minutes).
    """
    from helios.core.aurora_model import AuroralModel
    q, tau = -4.4 * (9.0 - 0.49), 2.4 * math.exp(9.74 / (4.69 + 9.0))
    expected = q * tau * (1.0 - math.exp(-6.0 / tau)) + 7.26 * math.sqrt(5.0) - 11.0
    one_min = AuroralModel.simulate_dst_evolution(_storm_records(1))[-1]["dst_predicted_nt"]
    five_min = AuroralModel.simulate_dst_evolution(_storm_records(5))[-1]["dst_predicted_nt"]
    assert five_min == pytest.approx(expected, abs=0.06)
    assert one_min == pytest.approx(expected, abs=0.06)


def test_burton_1975_dst_model_constants():
    """
    Burton et al. (1975): Q = -1.5e-3 nT/s per mV/m above 0.5 mV/m (-5.4 nT/h), decay
    3.6e-5 1/s (7.7 h), b = 0.20 nT/(eV cm^-3)^1/2 = 15.8 nT/nPa^1/2, c = 20 nT.
    """
    from helios.core.aurora_model import AuroralModel
    q, tau = -1.5e-3 * 3600.0 * (9.0 - 0.5), 1.0 / (3.6e-5 * 3600.0)
    expected = q * tau * (1.0 - math.exp(-6.0 / tau)) + 15.8 * math.sqrt(5.0) - 20.0
    out = AuroralModel.simulate_dst_evolution(_storm_records(5), model="burton")[-1]["dst_predicted_nt"]
    assert out == pytest.approx(expected, abs=0.1)
    # Starting from an observed Dst: a quiet interval relaxes towards b sqrt(P) - c
    quiet = [dict(r, bz_gsm=2.0) for r in _storm_records(5, hours=1)]
    start = AuroralModel.simulate_dst_evolution(quiet, model="burton", initial_dst=-100.0)
    assert start[0]["dst_predicted_nt"] == -100.0
    assert start[-1]["dst_predicted_nt"] > -100.0
    with pytest.raises(ValueError):
        AuroralModel.simulate_dst_evolution(quiet, model="temerin")


def test_dst_skill_and_model_comparison_against_sym_h():
    from helios.core.aurora_model import AuroralModel
    sk = AuroralModel.dst_skill([(-10, -12), (-50, -40), (-90, -100), (None, 5)])
    assert sk["n"] == 3 and sk["bias_nt"] == pytest.approx(0.67, abs=0.05)
    assert sk["rmse_nt"] == pytest.approx(math.sqrt((4 + 100 + 100) / 3), abs=0.05)
    assert sk["r"] == pytest.approx(0.979, abs=0.001) and sk["min_observed_nt"] == -100.0
    recs = [dict(r, sym_h=-20.0 - i) for i, r in enumerate(_storm_records(5, hours=2))]
    cmp = AuroralModel.compare_dst_models(recs)
    assert cmp["observed_index"] == "SYM-H" and set(cmp["models"]) == {"obrien", "burton"}
    # Both models start from the first observed SYM-H
    assert cmp["models"]["obrien"]["series"][0] == -20.0 and cmp["models"]["burton"]["series"][0] == -20.0
    assert cmp["models"]["obrien"]["skill"]["n"] == len(recs)


def test_kyoto_dst_hourly_alignment():
    """SWPC Kyoto Dst stamps mark the start of the hour; model hourly means pair with them."""
    from helios.core.aurora_model import AuroralModel
    from helios.core.downloader import DataDownloader
    rows = [{"time_tag": "2026-10-02T00:00:00", "dst": 5}, {"time_tag": "2026-10-02T01:00:00", "dst": -3},
            {"time_tag": "2026-10-02T02:00:00", "dst": 99999}]
    obs = DataDownloader.parse_kyoto_dst(rows)
    assert obs == [{"time_tag": "2026-10-02 00:00:00", "dst": 5.0}, {"time_tag": "2026-10-02 01:00:00", "dst": -3.0}]
    sim = [{"time_tag": f"2026-10-02 00:{m:02d}:00", "dst_predicted_nt": 1.0} for m in range(60)]
    sim += [{"time_tag": f"2026-10-02 01:{m:02d}:00", "dst_predicted_nt": -5.0} for m in range(10)]
    # 01:xx has only 10 of 60 minutes: skipped
    assert AuroralModel.hourly_pairs(sim, obs) == [(1.0, 5.0)]
    assert AuroralModel.observed_at(obs, "2026-10-02 01:37:00") == -3.0


def test_dst_simulation_handles_gaps():
    from helios.core.aurora_model import AuroralModel
    recs = _storm_records(5, hours=1)
    recs[3]["speed"] = None
    out = AuroralModel.simulate_dst_evolution(recs)
    assert out[3]["ey_electric_field_mvm"] is None
    assert len(out) == len(recs)


def test_cross_correlation_lag_sign_matches_theoretical_delay():
    """
    B sees the same signal 15 minutes (3 bins of 5 min) after A. The empirical lag must be
    +15 min, the same sign as compute_spatial_baseline's theoretical delay for a sunward A;
    it used to come out as -15 min, doubling the reported lag discrepancy.
    """
    from helios.core.comparator import SatelliteComparator
    rng = np.random.default_rng(3)
    f = np.convolve(rng.normal(size=400), np.ones(5) / 5, mode="same")
    a = f[10:310]
    b = f[7:307]  # b[n] = f[n + 7] = a[n - 3]
    res = SatelliteComparator.cross_correlation_lag(a, b, max_lags=24, dt_minutes=5.0)
    assert res["optimal_lag_minutes"] == 15.0
    assert res["max_correlation"] > 0.95


def test_align_time_series_mixed_timezones_and_long_gaps():
    from helios.core.comparator import SatelliteComparator
    a, b = [], []
    for i in range(48):
        hh, mm = divmod(i * 5, 60)
        a.append({"time_tag": f"2026-10-02 {hh:02d}:{mm:02d}:00", "bz_gsm": float(i)})
        if not 10 <= i < 30:  # 100-minute gap in B
            b.append({"time_tag": f"2026-10-02T{hh:02d}:{mm:02d}:00Z", "bz_gsm": float(i)})
    df = SatelliteComparator.align_time_series(a, b, "bz_gsm")
    # Naive and 'Z' stamps align; the long gap is not filled with interpolated values.
    assert len(df) == 48 - 20


def test_one_shock_is_reported_once():
    """A single step in V, N and B used to be reported as three shocks (i vs i-3 window)."""
    recs = [{"time_tag": f"2026-09-20 12:{i * 5:02d}:00",
             "speed": 350.0 if i < 5 else 620.0,
             "density": 4.0 if i < 5 else 18.0,
             "bt": 5.0 if i < 5 else 16.0} for i in range(12)]
    shocks = SpaceWeatherPhysics.detect_interplanetary_shocks(recs)
    assert len(shocks) == 1
    assert shocks[0]["delta_speed_kms"] == pytest.approx(270.0)
    # Two well separated jumps are two events.
    recs2 = recs + [{"time_tag": f"2026-09-20 13:{i * 5:02d}:00",
                     "speed": 620.0 if i < 4 else 800.0,
                     "density": 18.0 if i < 4 else 40.0,
                     "bt": 16.0 if i < 4 else 30.0} for i in range(10)]
    assert len(SpaceWeatherPhysics.detect_interplanetary_shocks(recs2)) == 2


@pytest.mark.parametrize("body", ["MARS", "VENUS", "SOLAR_ORBITER"])
def test_gse_z_points_to_ecliptic_north(body):
    """GSE Z is ecliptic north, so a body's GSE z equals its ecliptic z offset from Earth (Earth's z ~ 0)."""
    from helios.core.spice_engine import get_spice_engine
    eng = get_spice_engine()
    epoch = "2026-06-01T00:00:00"
    helio = eng.get_spacecraft_state(body, epoch_utc=epoch)
    earth = eng.get_spacecraft_state("EARTH", epoch_utc=epoch)
    gse = eng.get_spacecraft_state(body, epoch_utc=epoch, frame="GSE")
    dz = helio["position"]["z_km"] - earth["position"]["z_km"]
    assert abs(dz) > 1e5
    assert gse["position"]["z_km"] == pytest.approx(dz, rel=1e-3)


def test_l1_halo_gse_z_maps_to_ecliptic_north():
    from helios.core.spice_engine import get_spice_engine
    eng = get_spice_engine()
    epoch = "2026-06-01T00:00:00"
    st = eng.get_spacecraft_state("SOHO", epoch_utc=epoch)
    earth = eng.get_spacecraft_state("EARTH", epoch_utc=epoch)
    dz = st["position"]["z_km"] - earth["position"]["z_km"]
    assert st["gse_coordinates"]["z_km"] == pytest.approx(dz, rel=1e-3, abs=50.0)


def test_spice_trajectory_spans_the_orbit():
    """Trajectory points used to be identical: the ET float was passed as a string and parsed to a fixed epoch."""
    from helios.core.spice_engine import get_spice_engine
    pts = get_spice_engine().get_orbit_trajectory("PARKER_SOLAR_PROBE", num_points=8, epoch_utc="2026-01-01T00:00:00")
    radii = [p["r_au"] for p in pts]
    assert len({(p["x_au"], p["y_au"]) for p in pts}) == 8
    assert min(radii) < 0.2 and max(radii) > 0.6


def test_drap_haf_follows_swpc_formula():
    """SWPC D-RAP: HAF = 10 log10(Fx) + 65 (M1 -> 15 MHz), reduced by cos(chi)^0.75, A(HAF) = 1 dB."""
    from helios.core.ionosphere import IonosphericModel
    m1 = IonosphericModel.calculate_drap_absorption(1e-5, zenith_angle_deg=0.0)
    assert m1["highest_affected_frequency_mhz"] == pytest.approx(15.0, abs=0.01)
    slant = IonosphericModel.calculate_drap_absorption(1e-5, zenith_angle_deg=60.0)
    assert slant["highest_affected_frequency_mhz"] == pytest.approx(15.0 * 0.5 ** 0.75, abs=0.01)
    quiet = IonosphericModel.calculate_drap_absorption(1e-8, zenith_angle_deg=0.0)
    assert quiet["highest_affected_frequency_mhz"] == 0.0 and quiet["attenuation_at_10mhz_db"] == 0.0


def test_reports_state_real_provenance_and_survive_gaps():
    """The Markdown summary claimed NOAA/OMNI/ISRO/ESA provenance for any data and crashed on a trailing gap."""
    from helios.core.report_generator import ScientificReportGenerator as R
    recs = [{"time_tag": "a", "speed": 400.0, "bz_gsm": -3.0, "bt": 5.0, "density": 5.0},
            {"time_tag": "b", "speed": None, "bz_gsm": None, "bt": None, "density": None}]
    cls = SpaceWeatherPhysics.classify_noaa_scales(3.0, -3.0, 1e-6)
    prov = {"kind": "synthetic", "description": "offline model"}
    md = R.generate_markdown_executive_summary("DSCOVR", recs, cls, [], {"visible_regions": []}, provenance=prov)
    assert "SYNTHETIC - offline model" in md and "ISRO Aditya-L1 / ESA SOHO" not in md
    assert "ACTIVE RECONNECTION" in md
    html = R.generate_html_bulletin("DSCOVR", recs, cls, [], {"visible_regions": []}, provenance=prov)
    assert "SYNTHETIC - offline model" in html


def test_boyle_polar_cap_potential_uses_imf_magnitude():
    """Boyle et al. (1997): Phi = 1e-4 v^2 + 11.7 B sin^3(theta/2) with B = |B| (here 10 nT, Bz = -6 nT)."""
    res = SpaceWeatherPhysics.polar_cap_potential(500.0, 0.0, -6.0, b_total_nt=10.0)
    assert res["polar_cap_potential_kv"] == pytest.approx(1e-4 * 500.0 ** 2 + 11.7 * 10.0, abs=0.06)
    from fastapi.testclient import TestClient
    from helios.api.server import app
    api = TestClient(app).get("/api/geospace/coupling?speed_kms=500&b_total_nt=10&by_gsm_nt=0&bz_gsm_nt=-6").json()
    assert api["polar_cap_potential"]["polar_cap_potential_kv"] == pytest.approx(142.0, abs=0.06)


def test_chao_2002_bow_shock_reproduces_published_standoff():
    """
    Chao et al. (2002) bow shock with its published coefficients. Mo et al. (2025, JGR,
    Table 1) give r0 = 13.325 R_E for the initial Chao parameters at P_dyn = 2.42 nPa,
    Bz = -0.35 nT, beta = 3.02, M_ms = 5.77 (their inputs are rounded, hence 0.01 R_E).
    """
    bs = SpaceWeatherPhysics.chao_bow_shock(2.42, -0.35, mach_number=5.77, plasma_beta=3.02)
    assert bs["standoff_r0_re"] == pytest.approx(13.325, abs=0.01)
    assert bs["eccentricity"] == 1.029
    # alpha = a5 (1 + a6 Bz)(1 + a7 P)(1 + a10 ln(1 + beta))(1 + a14 M_ms) for Bz < 0
    alpha = 0.8182 * (1 - 0.0170 * -0.35) * (1 - 0.0122 * 2.42) * (1 - 0.0328 * math.log(4.02)) * (1 - 0.002 * 5.77)
    assert bs["flaring_alpha"] == pytest.approx(alpha, abs=5e-4)
    # The conic flares outward: at 90 deg r = r0 (1 + eps)^alpha
    side = SpaceWeatherPhysics.chao_bow_shock(2.42, -0.35, mach_number=5.77, plasma_beta=3.02, theta_rad=math.pi / 2)
    assert side["radial_distance_re"] == pytest.approx(13.33 * 2.029 ** alpha, abs=0.02)


def test_shue_1998_and_farris_russell_1994_standoffs():
    """Shue et al. (1998) magnetopause and the Farris & Russell (1994) bow shock relation used by OMNI."""
    r0, alpha = SpaceWeatherPhysics.shue1998_magnetopause(2.0, 0.0)
    assert r0 == pytest.approx((10.22 + 1.29 * math.tanh(0.184 * 8.14)) * 2.0 ** (-1 / 6.6), abs=1e-9)
    assert r0 == pytest.approx(10.252, abs=1e-3)
    assert alpha == pytest.approx(0.58 * (1 + 0.024 * math.log(2.0)), abs=1e-9)
    # OMNI: Rt = Rmp [1 + 1.1 ((2/3) M^2 + 2) / ((8/3)(M^2 - 1))]; Rmp = 10, M_ms = 8 -> 12.925
    assert SpaceWeatherPhysics.farris_russell_bow_shock(10.0, 8.0)["standoff_r0_re"] == pytest.approx(12.92, abs=0.01)
    with pytest.raises(ValueError):
        SpaceWeatherPhysics.farris_russell_bow_shock(10.0, 0.9)
    # OMNI Shue et al. (1997) standoff: (11.4 + 0.140 Bz) P^(-1/6.6) for Bz < 0
    assert SpaceWeatherPhysics.shue1997_standoff(2.0, -5.0) == pytest.approx(9.633, abs=1e-3)
    # OMNI plasma beta: [(T * 4.16e-5) + 5.34] Np / B^2
    assert SpaceWeatherPhysics.plasma_beta(5.0, 1e5, 5.0) == pytest.approx(1.9, abs=1e-9)


def test_boundary_endpoint_models_and_inputs():
    from fastapi.testclient import TestClient
    from helios.api.server import app
    client = TestClient(app)
    chao = client.get("/api/magnetosphere/boundaries?dynamic_pressure=2.42&bz_gsm=-0.35"
                      "&mach_number=5.77&plasma_beta=3.02&model=chao").json()
    assert chao["bow_shock"]["standoff_re"] == pytest.approx(13.325, abs=0.01)
    assert chao["magnetopause_model"] == "Shue et al. (1998)" and chao["bow_shock_model"] == "Chao et al. (2002)"
    fr = client.get("/api/magnetosphere/boundaries?dynamic_pressure=2.0&bz_gsm=0&mach_number=8&model=shue").json()
    assert fr["bow_shock"]["standoff_re"] == pytest.approx(10.2519 * 1.2924603, abs=0.01)
    assert client.get("/api/magnetosphere/boundaries?model=fairfield").status_code == 400


def test_aurora_endpoint_shows_observed_dst_next_to_model(monkeypatch):
    """L1 drivers are shifted to Earth, the model starts from Kyoto Dst and is scored hourly."""
    from fastapi.testclient import TestClient
    from helios.api import server
    recs = [dict(r, l1_travel_time_min=60.0) for r in _storm_records(1, hours=3)]

    async def bundle(mission, span_days=1):
        return {"records": recs, "provenance": {"kind": "observed"}}

    async def kyoto():
        return {"records": [{"time_tag": f"2026-10-02 0{h}:00:00", "dst": -10.0 * h} for h in range(5)],
                "source": "test"}

    monkeypatch.setattr(server.downloader, "get_telemetry_bundle", bundle)
    monkeypatch.setattr(server.downloader, "get_kyoto_dst", kyoto)
    body = TestClient(server.app).get("/api/aurora?kp=3&dst_model=burton").json()
    assert body["dst_model"] == "Burton et al. (1975)"
    # Shifted by 60 min the drivers start at 01:00, where Kyoto Dst is -10 nT
    assert body["dst_evolution"][0]["time_tag"] == "2026-10-02 01:00:00"
    assert body["dst_initial_observed_nt"] == -10.0 and body["dst_evolution"][0]["dst_predicted_nt"] == -10.0
    assert [o["dst"] for o in body["dst_observed"]] == [-10.0, -20.0, -30.0, -40.0]
    assert body["dst_skill"]["n"] == 3  # 01, 02, 03 h are complete; 04:00 has one sample
    assert TestClient(server.app).get("/api/aurora?dst_model=xyz").status_code == 400
