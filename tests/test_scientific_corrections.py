"""
Regression tests for scientific corrections. Each test pins a value or behaviour
that was wrong in an earlier version, with the reference derivation in the docstring.
"""
import math

import numpy as np
import pytest

from helios.core.science import SpaceWeatherPhysics

# The server only answers requests addressed to a loopback host (helios.api.guard).
LOCAL = "http://127.0.0.1:8765"


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


def test_psd_of_constant_series_reports_no_slope():
    """A flat series has no power to fit: no slope, not a default Kolmogorov -5/3 with R^2 0.85."""
    res = SpaceWeatherPhysics.power_spectral_density([4.0] * 256)
    assert res["spectral_slope_alpha"] is None and res["r_squared"] is None
    assert "No power-law fit" in res["cascade_regime"]


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


def test_spectrum_api_uses_record_cadence(omni_l1):
    """5-minute data (OMNI test data); the API used to assume 60 s, putting every frequency 5x too high."""
    from fastapi.testclient import TestClient
    from helios.api.server import app
    res = TestClient(app, base_url=LOCAL).get("/api/spectrum?mission_id=DSCOVR&parameter=bz_gsm").json()
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
def test_gse_matches_sunpy(body):
    """GSE (X to the Sun, Z to the ecliptic pole of date) against SunPy's GeocentricSolarEcliptic.
    The pole of J2000 put Mars 17 000 km off in z in 2026."""
    pytest.importorskip("sunpy")
    import astropy.units as u
    from astropy.coordinates import CartesianRepresentation, HeliocentricMeanEcliptic, SkyCoord
    from astropy.time import Time
    from sunpy.coordinates import GeocentricSolarEcliptic
    from helios.core.spice_engine import get_spice_engine
    t = "2026-06-01T00:00:00"
    st = get_spice_engine().get_spacecraft_state(body, epoch_utc=t)
    p, g = st["position"], st["gse_coordinates"]
    sc = SkyCoord(CartesianRepresentation(p["x_km"] * u.km, p["y_km"] * u.km, p["z_km"] * u.km),
                  frame=HeliocentricMeanEcliptic(obstime=Time(t), equinox=Time("J2000")))
    ref = sc.transform_to(GeocentricSolarEcliptic(obstime=Time(t))).cartesian.xyz.to(u.km).value
    mine = np.array([g["x_km"], g["y_km"], g["z_km"]])
    assert np.degrees(np.arccos(ref @ mine / np.linalg.norm(ref) / np.linalg.norm(mine))) < 0.002


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
    pts = get_spice_engine().get_orbit_trajectory("PARKER_SOLAR_PROBE", num_points=64, epoch_utc="2026-01-01T00:00:00")
    radii = [p["r_au"] for p in pts]
    assert len({(p["x_au"], p["y_au"]) for p in pts}) >= 63  # the last point closes the orbit
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
    md = R.generate_markdown_executive_summary("DSCOVR", recs, cls, [], {}, provenance=prov)
    assert "SYNTHETIC - offline model" in md and "ISRO Aditya-L1 / ESA SOHO" not in md
    assert "SOUTHWARD IMF (Bz < 0): dayside reconnection" in md
    html = R.generate_html_bulletin("DSCOVR", recs, cls, [], {}, provenance=prov)
    assert "SYNTHETIC - offline model" in html


def test_polar_cap_potential_is_the_hill_model_and_saturates():
    """Siscoe et al. (2002), baseline of their Fig. 2 (p = 1 nPa, F = 1, xi Sigma = 21.7 S): 198 kV at
    E = 50 mV/m, saturation 212 kV. Boyle et al. (1997) had no saturation and was clipped at an
    invented 280 kV (210 min of 16-18 March 2015 at the clip); on those OMNI data it now peaks at 264 kV."""
    v = 1000.0  # E = 50 mV/m with Bz = -50 nT; n for p = 1 nPa
    res = SpaceWeatherPhysics.polar_cap_potential(v, 0.0, -50.0, 1.0 / (2.0e-6 * v * v))
    assert res["polar_cap_potential_kv"] == pytest.approx(197.8, abs=0.1)
    assert res["saturation_kv"] == pytest.approx(212.4, abs=0.1)
    from helios.core.downloader import omni_snapshot
    s = omni_snapshot("st_patricks_2015")
    ix = {k: s["columns"].index(k) for k in ("speed", "density", "by_gsm", "bz_gsm")}
    phis = [SpaceWeatherPhysics.polar_cap_potential(r[ix["speed"]], r[ix["by_gsm"]], r[ix["bz_gsm"]], r[ix["density"]])
            ["polar_cap_potential_kv"] for r in s["rows"] if None not in (r[i] for i in ix.values())]
    assert round(max(phis)) == 264

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
    client = TestClient(app, base_url=LOCAL)
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
    body = TestClient(server.app, base_url=LOCAL).get("/api/aurora?kp=3&dst_model=burton").json()
    assert body["dst_model"] == "Burton et al. (1975)"
    # Shifted by 60 min the drivers start at 01:00, where Kyoto Dst is -10 nT
    assert body["dst_evolution"][0]["time_tag"] == "2026-10-02 01:00:00"
    assert body["dst_initial_observed_nt"] == -10.0 and body["dst_evolution"][0]["dst_predicted_nt"] == -10.0
    assert [o["dst"] for o in body["dst_observed"]] == [-10.0, -20.0, -30.0, -40.0]
    assert body["dst_skill"]["n"] == 3  # 01, 02, 03 h are complete; 04:00 has one sample
    assert TestClient(server.app, base_url=LOCAL).get("/api/aurora?dst_model=xyz").status_code == 400


def test_reference_dois_point_to_the_cited_papers():
    """DOIs were checked against Crossref; several pointed to unrelated papers."""
    from helios.config import SCIENTIFIC_REFERENCES, MISSIONS
    refs = {r["id"]: r for r in SCIENTIFIC_REFERENCES}
    assert refs["burton_dst_1975"]["doi"] == "10.1029/JA080i031p04204"
    assert refs["siscoe_hill_2002"]["doi"] == "10.1029/2001JA000109"
    assert refs["sauer_drap_2008"]["doi"] == "10.1029/2008SW000399"
    assert refs["starkov_aurora_1994"]["doi"] is None
    assert MISSIONS["SOHO"]["doi"] == "10.1007/BF00733425"
    assert MISSIONS["SOLAR_ORBITER"]["doi"] == "10.1051/0004-6361/202038467"


def test_custom_latest_is_not_an_error_before_any_import(monkeypatch):
    """The import tab asks for the latest dataset on every visit; nothing imported is not a 404."""
    from fastapi.testclient import TestClient
    from helios.api import server
    monkeypatch.setattr(server, "latest_custom_dataset", None)
    res = TestClient(server.app, base_url=LOCAL).get("/api/custom/latest")
    assert res.status_code == 200 and res.json()["status"] == "empty" and res.json()["total_records"] == 0


def test_coronagraph_feeds_are_labelled_by_the_instrument_that_made_them():
    """The '/SDO AIA' feeds were GOES SUVI images (at dead URLs) and 'Aditya VELC' showed LASCO C2."""
    from helios.core.coronagraph import CoronagraphAnalyzer
    feeds = CoronagraphAnalyzer.get_coronagraph_feeds()
    assert "SDO_AIA_193" not in feeds
    assert feeds["GOES_SUVI_195"]["url"].endswith("/suvi/primary/195/latest.png")
    assert feeds["GOES_SUVI_304"]["url"].endswith("/suvi/primary/304/latest.png")
    assert feeds["ADITYA_VELC"]["url"] is None and "PRADAN" in feeds["ADITYA_VELC"]["status"]


def test_aditya_l1_states_why_it_is_simulated():
    """ISSDC PRADAN needs a registered login: Aditya-L1 stays simulated and says why."""
    from helios.config import MISSIONS
    m = MISSIONS["ADITYA_L1"]
    assert m["data_portal_url"] == "https://pradan.issdc.gov.in/al1/"
    assert "login" in m["data_access"]


def test_starkov_1994_table_and_kp_conversion():
    """Coefficients as printed in Sigernes et al. (2011) Tables 1-2 (signs included)."""
    from helios.core.aurora_model import AuroralModel, STARKOV_COEFFS, STARKOV_KP_TO_AL
    assert STARKOV_KP_TO_AL == (18.0, -12.3, 27.2, -2.0)
    assert STARKOV_COEFFS["poleward"][0] == (-0.07, -10.06, -4.44, -3.77, -6.61, 6.37, -4.48)
    assert STARKOV_COEFFS["equatorward"][2] == (-10.97, -7.20, -7.96, -6.73, -0.58, -26.96, -24.20)
    assert STARKOV_COEFFS["diffuse"][3] == (3.35, 0.87, 0.72, 0.31, -0.28, -2.14, 0.76)
    assert AuroralModel.kp_to_al(0) == 18.0
    assert AuroralModel.kp_to_al(3) == pytest.approx(171.9)
    assert AuroralModel.kp_to_al(9) == pytest.approx(652.5)


def test_starkov_boundaries_match_published_ovals():
    """
    Boundaries read off the Feldstein-Starkov oval plots in Fig. 2.10 of the UNIS master's
    thesis that implements Starkov (1994) with the Sigernes et al. (2011) table
    (aurora.unis.no/doc/Master_thesis_Mikkel.pdf), to the ~1.5 deg the figure can be read.
    A sign error in the table moves boundaries by several degrees.
    """
    from helios.core.aurora_model import AuroralModel
    kp_al = AuroralModel.kp_to_al
    lat = AuroralModel.starkov_latitude
    # (Kp, MLT, boundary, latitude read from the figure)
    for kp, mlt, name, expected in [(0, 12, "poleward", 77.0), (0, 12, "equatorward", 75.0), (0, 12, "diffuse", 69.0),
                                    (0, 0, "poleward", 71.0), (0, 0, "diffuse", 66.0),
                                    (3, 0, "equatorward", 63.0), (3, 12, "equatorward", 73.5), (3, 0, "diffuse", 60.5),
                                    (9, 0, "poleward", 73.0), (9, 0, "diffuse", 53.5), (9, 12, "equatorward", 70.0)]:
        assert float(lat(kp_al(kp), mlt, name)) == pytest.approx(expected, abs=1.5), (kp, mlt, name)
    # Ordering at every MLT: poleward > equatorward > diffuse edge, for quiet to storm levels
    import numpy as np
    t = np.arange(0, 24, 0.5)
    for al in (18, 100, 400, 652.5, 750):
        assert np.all(lat(al, t, "poleward") > lat(al, t, "equatorward"))
        assert np.all(lat(al, t, "equatorward") > lat(al, t, "diffuse"))


def test_dipole_pole_and_magnetic_local_time():
    """IGRF-14 geomagnetic north pole for 2025.0 is at 80.8 N, 72.8 W; Tromso magnetic midnight ~21:30 UT."""
    import numpy as np
    from helios.core import coordinates as c
    p = c.dipole_axis_geo("2025-01-01")[0]
    assert np.degrees(np.arcsin(p[2])) == pytest.approx(80.8, abs=0.05)
    assert np.degrees(np.arctan2(p[1], p[0])) == pytest.approx(-72.8, abs=0.1)
    mlt, mlat = c.geo_to_mlt_mlat("2025-12-21 21:30", 69.66, 18.94)
    assert min(mlt, 24 - mlt) < 0.5 and mlat == pytest.approx(67.5, abs=0.3)
    lat, lon = c.mlt_mlat_to_geo("2025-12-21 21:30", [3.0], [65.0])
    back_mlt, back_mlat = c.geo_to_mlt_mlat("2025-12-21 21:30", lat, lon)
    assert float(back_mlt[0]) == pytest.approx(3.0, abs=1e-6) and float(back_mlat[0]) == pytest.approx(65.0, abs=1e-6)


def test_aurora_endpoint_uses_al_and_draws_starkov_oval(monkeypatch):
    from fastapi.testclient import TestClient
    from helios.api import server
    client = TestClient(server.app, base_url=LOCAL)
    body = client.get("/api/aurora?al=-450&kp=5&time=2024-05-10T22:00").json()
    b = body["boundaries"]
    assert b["model"] == "Starkov (1994)" and b["al_used_nt"] == 450.0 and b["al_source"] == "user input"
    assert b["equatorward_midnight_lat"] == pytest.approx(float(server.AuroralModel.starkov_latitude(450, 0.0)), abs=0.05)
    oval = body["oval_polygon"]
    assert oval["time_utc"] == "2024-05-10 22:00:00"
    north = oval["north"]["equatorward"]
    assert north[0]["lon"] == -180.0 and north[-1]["lon"] == 180.0
    assert all(a["lon"] <= b2["lon"] for a, b2 in zip(north, north[1:]))
    assert all(p["lat"] < 0 for p in oval["south"]["poleward"])
    # Past time with no OMNI AL and no Kp/AL given: explained 404 instead of today's Kp
    r = client.get("/api/aurora?time=2024-05-10T22:00")
    assert r.status_code == 404 and "OMNI AL" in r.json()["detail"]

    # With OMNI AL in the archive the hourly mean drives the oval
    async def omni(mission, start, end, cadence_minutes=1):
        assert mission == "OMNI"
        return {"records": [{"time_tag": "x", "al": -400.0 - i} for i in range(60)], "provenance": {"kind": "observed"}}
    monkeypatch.setattr(server.downloader, "get_archive_bundle", omni)
    b = client.get("/api/aurora?time=2024-05-10T22:00").json()["boundaries"]
    assert b["al_used_nt"] == pytest.approx(429.5) and b["al_source"].startswith("OMNI 1-min AL")
    assert b["hemispheric_power_gw"] is None
    # Nothing live next to a past oval: no Bz, no Dst model or Kyoto Dst of today.
    past = client.get("/api/aurora?time=2024-05-10T22:00").json()
    assert past["bz_gsm"] is None and past["dst_evolution"] is None and past["dst_observed"] is None
    assert "past oval time" in past["dst_note"]


def test_gopalswamy_2001_empirical_arrival():
    """
    a = 2.193 - 0.0054 u m/s^2 until 0.76 AU (Gopalswamy et al. 2001, JGR 106, 29207; abstract
    and Ravishankar & Michalek 2019, arXiv:1910.02797). The abstract notes a flat arrival time
    of ~4.3 days for slow CMEs.
    """
    from helios.core.coronagraph import CoronagraphAnalyzer as C
    for u in (150, 200, 300):
        assert C.gopalswamy_2001_arrival(u)["transit_hours"] / 24.0 == pytest.approx(4.3, abs=0.05)
    fast = C.gopalswamy_2001_arrival(2000.0)
    assert fast["acceleration_ms2"] == pytest.approx(2.193 - 10.8, abs=1e-3)
    assert fast["transit_hours"] < 30.0 and fast["arrival_speed_kms"] < 2000.0
    kin = C.calculate_cme_kinematics(2.0, 7.5, 38.1, ambient_wind_kms=500.0, gamma_drag=0.5e-7)
    assert kin["initial_speed_kms"] == pytest.approx(1675, abs=2)  # Bastille Day preset
    assert kin["ambient_wind_kms"] == 500.0 and kin["drag_parameter_gamma"] == 0.5e-7
    assert kin["gopalswamy_2001_transit_hours"] == C.gopalswamy_2001_arrival(kin["initial_speed_kms"], 7.5 * C.R_SUN_KM)["transit_hours"]


def test_importer_reads_its_own_exports_json_and_headers_with_units():
    """HELIOS CSV exports ('#' metadata lines) and JSON could not be imported; 'Bz GSM (nT)' was silently ignored."""
    import json
    from helios.core.importer import TelemetryImporter as T
    from helios.core.exporter import DataExporter as E
    first = T.parse_csv_or_text(T.get_preset("quiet_wind")["csv_content"], "x")
    csv_text = E.to_csv(first["records"], metadata={"title": "t", "data_kind": "imported"})
    again = T.parse_csv_or_text(csv_text, "x")
    assert again["total_records"] == 144 and again["summary"]["speed_mean"] == first["summary"]["speed_mean"]
    assert again["warnings"] == []
    assert T.parse_csv_or_text(json.dumps(first), "x")["total_records"] == 144
    assert T.parse_csv_or_text(json.dumps(first["records"]), "x")["total_records"] == 144
    swpc = [["time_tag", "bz_gsm", "speed"], ["2024-01-01 00:00:00", "-3", "400"]]
    assert T.parse_csv_or_text(json.dumps(swpc), "x")["records"][0]["bz_gsm"] == -3.0
    units = T.parse_csv_or_text("Time (UTC),Bz GSM (nT),Speed [km/s],Foo\n2024-05-10T00:00:00Z,-3,400,1\n", "x")
    assert units["records"][0]["bz_gsm"] == -3.0 and units["records"][0]["speed"] == 400.0
    assert any("Foo" in w for w in units["warnings"])
    # ACE SWEPAM (Vp, Np, Tpr) and NOAA RTSW (proton_speed, proton_temperature) names: the speed
    # column of such files was listed as "not used".
    ace = T.parse_csv_or_text("Epoch (UTC),Vp [km/s],Np [cm^-3],Tpr [K]\n2015-03-17T00:00:00Z,421.8,12.79,51000\n", "x")
    assert ace["records"][0]["speed"] == 421.8 and ace["records"][0]["temperature"] == 51000.0
    assert not any("not used" in w for w in ace["warnings"])
    rtsw = [{"time_tag": "2024-01-01T00:00:00", "proton_speed": 410, "proton_density": 3, "proton_temperature": 60000}]
    r0 = T.parse_csv_or_text(json.dumps(rtsw), "x")["records"][0]
    assert r0["speed"] == 410.0 and r0["density"] == 3.0 and r0["temperature"] == 60000.0
    err = T.parse_csv_or_text("time,foo,bar\n2024-01-01,1,2\n", "x")["error"]
    assert "No recognised solar wind column" in err and "bar, _t" not in err


def test_cme_presets_match_cdaw_catalogue_speeds():
    """
    The CME presets give the SOHO/LASCO linear speeds of the CDAW CME catalogue
    (cdaw.gsfc.nasa.gov/CME_list): 2024-05-09 09:24 halo 1280 km/s, 2003-10-28 11:30
    halo 2459 km/s, 2000-07-14 10:54 halo 1674 km/s. The May 2024 and Halloween buttons
    said ~1800 and ~2150 km/s. Each button's heights and dt must give its label.
    """
    import re
    from pathlib import Path
    from helios.core.coronagraph import CoronagraphAnalyzer
    from conftest import package_dir
    html = (package_dir() / "gui" / "static" / "index.html").read_text(encoding="utf-8")
    presets = re.findall(r"setCMEPreset\(([\d.]+), ([\d.]+), ([\d.]+), '[^']*'\)[^>]*>\s*([^<]+?)\s*</button>", html)
    labels = {}
    for r1, r2, dt, label in presets:
        v = CoronagraphAnalyzer.calculate_cme_kinematics(float(r1), float(r2), float(dt))["initial_speed_kms"]
        labels[label.split(" (")[0]] = v
        stated = float(re.search(r"\(~?(\d+) km/s", label).group(1))
        assert v == pytest.approx(stated, abs=1.0 if "~" not in label else 30.0), label
    assert labels["May 2024"] == pytest.approx(1280.0, abs=1.0)
    assert labels["Halloween 2003"] == pytest.approx(2459.0, abs=1.0)
    assert labels["Bastille Day"] == pytest.approx(1674.0, abs=1.0)


def test_forecaster_kp_is_newell_2008_fit():
    """
    Newell et al. (2008, JGR 113, A04218): Kp = 0.05 + 2.244e-4 dPhi/dt + 2.844e-6 n^(1/2) v^2.
    v = 400 km/s, n = 5 cm^-3, Bz = -5 nT, By = 0: dPhi/dt = 400^(4/3) 5^(2/3) = 8617.6,
    Kp = 0.05 + 1.9338 + 1.0175 = 3.001. The old Kp blended 1.8 + dPhi/7000 with Dst/22
    and came with an invented +-(0.3 + 0.12 h) "95% CI".
    """
    from helios.core.ml_forecast import SpaceWeatherForecaster as F
    dphi = 400.0 ** (4.0 / 3.0) * 5.0 ** (2.0 / 3.0)
    expected = 0.05 + 2.244e-4 * dphi + 2.844e-6 * math.sqrt(5.0) * 400.0 ** 2
    assert F.newell_2008_kp(400.0, 5.0, 0.0, -5.0) == pytest.approx(expected, rel=1e-4)
    assert expected == pytest.approx(3.001, abs=0.002)
    # Northward IMF: only the viscous term, 0.05 + 1.0175
    assert F.newell_2008_kp(400.0, 5.0, 0.0, 5.0) == pytest.approx(1.0675, abs=1e-3)
    assert F.newell_2008_kp(400.0, None, 0.0, -5.0) is None
    # Steady drivers equal to the quiet values: the trajectory stays at the same Kp, the band
    # (range of the last 3 h) is zero wide and the probabilities come only from NOAA.
    recs = [{"time_tag": f"2026-01-01 00:{m:02d}:00", "speed": 400.0, "density": 5.0,
             "by_gsm": 0.0, "bz_gsm": -1.0, "bt": 1.0} for m in range(30)]
    noaa = {"issued": "2026 Jan 01 0030 UTC", "day": "01 Jan",
            "probabilities": {"active": 10, "minor_storm": 5, "moderate_storm": 1, "strong_extreme_storm": 1}}
    out = F.forecast_geomagnetic_storm(recs, observed_dst=-10.0, noaa_forecast=noaa)
    kp_quiet = round(F.newell_2008_kp(400.0, 5.0, 0.0, -1.0), 1)
    for step in out["predictions_timeline"]:
        assert step["predicted_kp"] == kp_quiet
        assert step["kp_confidence_interval"] == [kp_quiet, kp_quiet]
    assert out["storm_probabilities"]["minor_storm_g1_percent"] == 5
    assert out["storm_probabilities"]["day"] == "01 Jan"
    # Auroral boundary from Starkov (1994) for the trajectory Kp
    from helios.core.aurora_model import AuroralModel
    lat = AuroralModel.calculate_auroral_boundaries(kp_quiet)["equatorward_midnight_lat"]
    assert out["predictions_timeline"][0]["auroral_midnight_boundary_lat"] == pytest.approx(lat, abs=0.15)


def test_noaa_geomag_forecast_parsers():
    """Day-1 probabilities and issue time from the SWPC 3-day forecast text; predicted Kp rows only."""
    from helios.core.downloader import DataDownloader as D
    text = """:Product: Geomagnetic Forecast
:Issued: 2026 Oct 03 2205 UTC
NOAA Geomagnetic Activity Probabilities 04 Oct-06 Oct
Active                25/35/35
Minor storm           35/20/20
Moderate storm        20/05/05
Strong-Extreme storm  05/01/01

NOAA Kp index forecast 04 Oct - 06 Oct
"""
    out = D.parse_geomag_forecast(text)
    assert out == {"issued": "2026 Oct 03 2205 UTC", "day": "04 Oct",
                   "probabilities": {"active": 25, "minor_storm": 35, "moderate_storm": 20, "strong_extreme_storm": 5}}
    assert D.parse_geomag_forecast("no block here") is None
    rows = [{"time_tag": "2026-10-03T21:00:00", "kp": 3.0, "observed": "observed"},
            {"time_tag": "2026-10-04T00:00:00", "kp": 2.33, "observed": "estimated"},
            {"time_tag": "2026-10-04T03:00:00", "kp": 4.67, "observed": "predicted"}]
    # NOAA labels the whole current UTC day "estimated", its future bins too (product of
    # 2026-10-07 07 UTC: 09-21 UTC "estimated"), so those are kept with their label.
    assert D.parse_kp_forecast(rows) == [{"time_tag": "2026-10-04 00:00:00", "kp": 2.33, "kind": "estimated"},
                                         {"time_tag": "2026-10-04 03:00:00", "kp": 4.67, "kind": "predicted"}]


@pytest.mark.parametrize("kp, level", [
    (4.33, 0), (4.67, 1), (5.0, 1), (5.33, 1), (5.67, 2), (6.33, 2), (6.67, 3), (7.33, 3),
    (7.67, 4), (8.0, 4), (8.67, 4), (9.0, 5), (None, 0),
])
def test_noaa_g_scale_counts_minus_kp_with_its_integer(kp, level):
    """
    NOAA G scale: G1 = Kp 5 (5-, 5o, 5+) ... G4 = Kp 8 including 9-, G5 = Kp 9 (9o, 9+).
    SWPC's planetary K-index forecast product tags Kp 4.67 as "G1" (checked 2026-10-04).
    The classifier started G1 at Kp 5.0, so 5- was G0, 6- G1 and so on.
    """
    assert SpaceWeatherPhysics.noaa_g_level(kp) == level
    assert SpaceWeatherPhysics.classify_noaa_scales(kp, 0.0, None)["g_level"] == level


def test_dst_model_does_not_count_an_unreadable_time_stamp_twice():
    from helios.core.aurora_model import AuroralModel
    rows = [{"time_tag": f"2024-05-10 12:{m:02d}:00", "speed": 700.0, "bz_gsm": -20.0, "dynamic_pressure": 5.0}
            for m in range(0, 60, 10)]
    bad = [dict(r) for r in rows]
    bad[3]["time_tag"] = "not a time"
    good = AuroralModel.simulate_dst_evolution(rows)[-1]["dst_predicted_nt"]
    assert AuroralModel.simulate_dst_evolution(bad)[-1]["dst_predicted_nt"] == good


def test_kp_fallback_is_the_newell_fit_and_says_so():
    """Without observed Kp: Newell et al. (2008) from the drivers, never a default (Bz -> Kp 3 or 7)."""
    from helios.api.server import kp_from_solar_wind
    from helios.core.ml_forecast import SpaceWeatherForecaster as F
    rec = {"speed": 650.0, "density": 12.0, "by_gsm": 3.0, "bz_gsm": -15.0}
    kp, src = kp_from_solar_wind(rec)
    assert kp == round(F.newell_2008_kp(650.0, 12.0, 3.0, -15.0), 2) and "Newell" in src
    assert "simulated" in kp_from_solar_wind(rec, "simulated")[1]
    assert kp_from_solar_wind({"bz_gsm": -15.0})[0] is None  # no speed: no estimate
    from helios.core.science import SpaceWeatherPhysics
    assert SpaceWeatherPhysics.classify_noaa_scales(kp=None, bz_gsm=None, xray_flux=None)["g_scale"].startswith("G--")


def test_kp_time_is_shown_as_its_three_hour_interval():
    from helios.api.server import kp_interval
    assert kp_interval("2026-10-10 06:00:00") == "2026-10-10 06:00-09:00 UTC"
    assert kp_interval("2026-10-10T21:00:00") == "2026-10-10 21:00-00:00 UTC"


def test_forecast_starts_from_kyoto_dst_only_when_it_is_recent():
    from datetime import datetime, timedelta, timezone
    from helios.api.server import recent_dst
    hour = lambda h: (datetime.now(timezone.utc) - timedelta(hours=h)).strftime("%Y-%m-%d %H:00:00")
    assert recent_dst([{"time_tag": hour(1), "dst": -40.0}])[0] == -40.0
    assert recent_dst([{"time_tag": hour(50), "dst": -40.0}]) == (None, None)  # an old cached copy
    assert recent_dst([]) == (None, None)


def test_forecast_starts_after_the_measured_wind_not_at_the_observed_hour():
    from datetime import datetime, timezone
    from helios.core.ml_forecast import SpaceWeatherForecaster as F
    end = datetime(2024, 5, 10, 18, tzinfo=timezone.utc)
    drivers = [{"time_tag": f"2024-05-10 {h:02d}:{m:02d}:00", "speed": 700.0, "bz_gsm": -20.0, "by_gsm": 0.0,
                "density": 10.0, "dynamic_pressure": 9.8} for h in (17, 18, 19, 20) for m in (0, 30)]
    out = F.forecast_geomagnetic_storm(drivers, observed_dst=-50.0, observed_dst_end=end, earth_drivers=drivers)
    # Two hours of strong southward field after the observed hour, then the 12 h trajectory.
    assert out["trajectory_start_utc"] == "2024-05-10 20:30"
    assert out["current_coupling"]["estimated_dst_nt"] < -80
    assert out["predictions_timeline"][0]["time_iso"].startswith("2024-05-10T21:30")


def test_dst_step_uses_the_driver_of_the_interval_that_ends():
    """Hourly rows: the southward hour starting at row 3 acts from row 3 to row 4, not before row 3."""
    from helios.core.aurora_model import AuroralModel
    rows = [{"time_tag": f"2024-05-10 {h:02d}:00:00", "speed": 500.0, "bz_gsm": 5.0 if h < 3 else -10.0,
             "dynamic_pressure": 2.0} for h in range(6)]
    d = [r["dst_predicted_nt"] for r in AuroralModel.simulate_dst_evolution(rows, initial_dst=0.0)]
    assert d[3] > -2.0 and d[4] < d[3] - 10.0


def test_boundaries_list_the_inputs_left_at_typical_values():
    from fastapi.testclient import TestClient
    from helios.api.server import app
    r = TestClient(app, base_url=LOCAL).get("/api/magnetosphere/boundaries?dynamic_pressure=3&bz_gsm=-2").json()
    assert r["inputs_assumed"] == {"mach_number": 8.0, "plasma_beta": 2.0} and r["dynamic_pressure_npa"] == 3.0


def test_spectral_slope_is_fitted_on_log_bins_with_its_error():
    """A day of 1-min data with an exact f^-5/3 spectrum: slope 5/3 within its error, fitted above 0.1 mHz."""
    import numpy as np
    from helios.core.science import SpaceWeatherPhysics as S
    rng = np.random.default_rng(3)
    n = 1440
    f = np.fft.rfftfreq(n, 60.0)
    amp = np.zeros_like(f)
    amp[1:] = f[1:] ** (-5.0 / 6.0)
    x = np.fft.irfft(amp * np.exp(2j * np.pi * rng.random(len(f))), n)
    r = S.power_spectral_density(x.tolist(), 60.0)
    assert abs(r["spectral_slope_alpha"] - 5.0 / 3.0) <= 2 * r["spectral_slope_error"] + 0.05
    assert r["fit_range_hz"][0] >= 1e-4 and r["fit_range_hz"][1] <= 0.25 / 60.0 * 1.01
    assert "Dissipation" not in r["cascade_regime"] and len(r["frequencies_hz"]) == n // 2


def test_kp_trajectory_persists_three_hour_means_march_2015():
    """Issued 17 March 2015 12 UT from OMNI: one sample gave Kp 9.0 "now" and an invented 5 %/h
    relaxation took the 12-h trajectory down to 4.1 while GFZ Kp stayed 6.0-7.7. The 3-hour mean
    gives 6.9, persisted: within 0.9 of GFZ Kp at every hour of the next 12 h."""
    import json
    from helios.core.downloader import omni_snapshot
    from helios.core.ml_forecast import SpaceWeatherForecaster as F
    s = omni_snapshot("st_patricks_2015")
    recs = [dict(zip(s["columns"], r)) for r in s["rows"] if r[0] < "2015-03-17 12:00"]
    out = F.forecast_geomagnetic_storm(recs)
    from pathlib import Path
    gfz = json.loads((Path(__file__).parent / "data" / "gfz" / "kp_20150316.json").read_text())
    kp = dict(zip(gfz["datetime"], gfz["Kp"]))
    assert out["current_coupling"]["newell_kp_now"] == 6.9
    for p in out["predictions_timeline"]:
        h = 12 + p["horizon_hours"] - 1
        obs = kp[f"2015-03-{17 + h // 24}T{(h % 24) // 3 * 3:02d}:00:00Z"]
        assert abs(p["predicted_kp"] - obs) < 0.9


def test_shock_screen_finds_the_march_2015_shock():
    """The screen (DV >= 45 km/s, N2/N1 >= 1.5, B2/B1 >= 1.35, sample i against i-3) missed the
    17 March 2015 shock (IPShocks: WIND 04:00 UT, OMNI at the bow shock ~04:45). With the IPShocks
    jump criteria and windows it is found in the bundled OMNI data; on WIND 1-min data of 2023 it
    found 22 of the 32 catalogued fast forward shocks (the old screen 2) with 14 other detections."""
    from helios.core.downloader import omni_snapshot
    s = omni_snapshot("st_patricks_2015")
    shocks = SpaceWeatherPhysics.detect_interplanetary_shocks([dict(zip(s["columns"], r)) for r in s["rows"]])
    assert [x["time"] for x in shocks] == ["2015-03-17 04:45:00"]
    assert shocks[0]["density_ratio"] >= 1.2 and shocks[0]["magnetic_ratio"] >= 1.2


def test_drap_has_no_invented_usability_levels():
    """'Complete Blackout' above 10 dB and 'Severely Degraded' above 3 dB were thresholds of this app;
    'polar_aviation_impact' described the sunlit side. An X1 flare overhead: HAF 25 MHz (D-RAP)."""
    from helios.core.ionosphere import IonosphericModel
    res = IonosphericModel.calculate_drap_absorption(1e-4, zenith_angle_deg=0.0)
    assert res["highest_affected_frequency_mhz"] == pytest.approx(25.0)
    assert all("usability" not in row for row in res["absorption_spectrum"])
    assert "polar_aviation_impact" not in res and res["sunlit_hf_impact"].startswith("HF below 25 MHz")
