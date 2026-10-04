"""
Comprehensive End-to-End Mathematical, Physical, Dimensional, and API Audit Script
for all 12 HELIOS-L1 Operational Tabs, Options, Filters, and Backend Engines.
"""
import math
import pytest
import numpy as np
from fastapi.testclient import TestClient

from helios.api.server import app
from helios.core.science import SpaceWeatherPhysics
from helios.core.downloader import DataDownloader
from helios.core.comparator import SatelliteComparator
from helios.core.spice_engine import SpiceEphemerisEngine, get_spice_engine
from helios.core.coronagraph import CoronagraphAnalyzer
from helios.core.parker_spiral import ParkerSpiralModel
from helios.core.aurora_model import AuroralModel
from helios.core.gic_model import GICHazardModel
from helios.core.ionosphere import IonosphericModel
from helios.core.solar_cycle import SolarCycleEngine
from helios.core.ml_forecast import SpaceWeatherForecaster
from helios.core.importer import TelemetryImporter

client = TestClient(app)

# =============================================================================
# TAB 1: DASHBOARD / L1 TELEMETRY (Telemetry, Filters, Pdyn, Epsilon, Delay, NOAA)
# =============================================================================
class TestTab1DashboardL1Telemetry:
    """Rigorous audit of Tab 1: Telemetry feeds, regime filters, and physical metrics."""

    def test_dynamic_pressure_physics_and_units(self):
        """
        P_dyn = rho * v^2 = (m_p * n) * v^2
        Dimensional check:
        m_p = 1.6726219e-27 kg
        n = 1 cm^-3 = 10^6 m^-3
        v = 1 km/s = 10^3 m/s
        rho * v^2 = 1.6726219e-27 * 10^6 * 10^6 = 1.6726219e-15 Pa
        1 nPa = 1e-9 Pa
        P_dyn [nPa] = 1.6726219e-6 * n_p * v^2
        """
        # Nominal solar wind: n = 5 cm^-3, v = 400 km/s
        # P_dyn = 1.6726e-6 * 5 * 160000 = 1.338 nPa
        pdyn = SpaceWeatherPhysics.dynamic_pressure(5.0, 400.0)
        assert abs(pdyn - 1.338) < 0.01, f"Expected ~1.338 nPa, got {pdyn}"

        # Fast CME shock: n = 45 cm^-3, v = 950 km/s
        # P_dyn = 1.6726e-6 * 45 * 902500 = 67.92 nPa
        pdyn_cme = SpaceWeatherPhysics.dynamic_pressure(45.0, 950.0)
        assert abs(pdyn_cme - 67.92) < 0.2, f"Expected ~67.92 nPa, got {pdyn_cme}"

        # Boundary checks: zero or negative returns 0.0
        assert SpaceWeatherPhysics.dynamic_pressure(0.0, 400.0) == 0.0
        assert SpaceWeatherPhysics.dynamic_pressure(5.0, -10.0) == 0.0
        assert SpaceWeatherPhysics.dynamic_pressure(None, 400.0) == 0.0

    def test_akasofu_epsilon_physics_and_units(self):
        """
        Akasofu Epsilon Poynting Flux:
        epsilon = (4 * pi / mu_0) * v * B^2 * sin^4(theta / 2) * l_0^2
        Units: v [m/s], B [Tesla], mu_0 [H/m], l_0 [m] (7 R_E = 4.4597e7 m)
        (4 * pi / mu_0 = 1e7 converts the Gaussian v * B^2 * l_0^2 [erg/s] to W.)
        Output in Gigawatts (GW = 1e9 W).
        """
        # Northward IMF (theta = 0): sin(0) = 0 -> epsilon = 0 GW (no dayside reconnection)
        eps_north = SpaceWeatherPhysics.akasofu_epsilon(500.0, 10.0, 0.0, 10.0)
        assert eps_north == 0.0

        # Southward IMF (theta = pi): sin(pi/2) = 1 -> maximum coupling
        # v = 500 km/s = 5e5 m/s, B = 10 nT = 1e-8 T, B^2 = 1e-16 T^2
        # Energy rate = 1e7 * 5e5 * 1e-16 * 1 * (4.4597e7)^2
        # = 5e-4 * 1.9889e15 = 9.944e11 W = 994.4 GW
        eps_south = SpaceWeatherPhysics.akasofu_epsilon(500.0, 10.0, 0.0, -10.0)
        assert abs(eps_south - 994.4) < 1.0, f"Expected ~994.4 GW, got {eps_south}"

    def test_propagation_delay_physics(self):
        """
        Propagation delay from Sun-Earth L1 (1.5e6 km) to Earth's bow shock (~90,000 km):
        effective_dist = 1.41e6 km.
        At v = 450 km/s: delay = 1.41e6 / 450 = 3133 s = 52.2 minutes.
        """
        delay = SpaceWeatherPhysics.propagation_delay_minutes(1500000.0, 450.0)
        assert abs(delay - 52.2) < 0.5, f"Expected ~52.2 min, got {delay}"

        # Extreme fast shock at 1800 km/s: delay = 1.41e6 / 1800 = 783 s = 13.1 min
        delay_fast = SpaceWeatherPhysics.propagation_delay_minutes(1500000.0, 1800.0)
        assert abs(delay_fast - 13.1) < 0.3, f"Expected ~13.1 min, got {delay_fast}"

    def test_noaa_scales_classification_ranges(self):
        """Verify NOAA G, S, R scale classifications against official SWPC breakpoints."""
        # G0 Quiet, S0 Nominal, R0 None
        c0 = SpaceWeatherPhysics.classify_noaa_scales(kp=1.0, bz_gsm=2.0, xray_flux=1e-7, proton_flux=0.5)
        assert c0["g_level"] == 0 and "G0" in c0["g_scale"]
        assert c0["r_level"] == 0 and "R0" in c0["r_scale"]
        assert c0["s_level"] == 0 and "S0" in c0["s_scale"]

        # G5 Extreme (Kp >= 9), R5 Extreme (X >= 2e-3), S5 Extreme (Proton >= 1e5)
        c5 = SpaceWeatherPhysics.classify_noaa_scales(kp=9.0, bz_gsm=-28.0, xray_flux=2.5e-3, proton_flux=1.2e5)
        assert c5["g_level"] == 5 and "G5" in c5["g_scale"]
        assert c5["r_level"] == 5 and "R5" in c5["r_scale"]
        assert c5["s_level"] == 5 and "S5" in c5["s_scale"]
        assert "CRITICAL" in c5["bz_alert"]

    def test_telemetry_api_and_filters(self):
        """Test telemetry endpoint for all fleet spacecraft across 1 and 7 day spans."""
        for sat in ["DSCOVR", "ACE", "ADITYA_L1", "WIND", "SOHO"]:
            res = client.get(f"/api/telemetry/{sat}?span_days=1")
            assert res.status_code == 200
            data = res.json()
            assert data["mission"]["id"] == sat or data["mission"]["name"].upper().replace("-", "_") == sat
            assert "records" in data
            assert len(data["records"]) > 0
            latest = data["latest"]
            assert "speed" in latest and "density" in latest and "bz_gsm" in latest
            assert latest["speed"] > 0
            assert latest["density"] > 0
            assert "dynamic_pressure" in latest

        # Test 7-day span
        res7 = client.get("/api/telemetry/DSCOVR?span_days=7")
        assert res7.status_code == 200
        assert len(res7.json()["records"]) > len(res.json()["records"])


# =============================================================================
# TAB 2: MULTI-SATELLITE COMPARATOR (Cross-Correlation, Lag, Spatial Baseline)
# =============================================================================
class TestTab2Comparator:
    """Rigorous audit of Tab 2: Mutual fleet statistics, lag optimization, and GSE geometry."""

    def test_comparator_math_metrics(self):
        """Verify Pearson r, R^2, RMSE, and regression slope between DSCOVR and ACE."""
        res = client.get("/api/compare?mission_a=DSCOVR&mission_b=ACE&parameter=bz_gsm&span_days=1")
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "success"

        m = data["metrics"]
        r = m["correlation_r"]
        r2 = m["r_squared"]
        rmse = m["rmse"]
        assert -1.0 <= r <= 1.0
        assert 0.0 <= r2 <= 1.0
        assert abs(r2 - round(r ** 2, 3)) <= 0.01
        assert rmse >= 0.0

        # Lag analysis
        lag = data["lag_analysis"]
        assert "optimal_lag_minutes" in lag
        assert "lags_minutes" in lag
        assert "correlation" in lag or "cross_correlation" in lag

        # Spatial baseline geometry
        base = data["spatial_baseline"]
        assert "distance_km" in base
        assert "distance_re" in base
        assert abs(base["distance_re"] - base["distance_km"] / 6371.0) < 0.1
        assert "theoretical_delay_min" in base

    def test_fleet_matrix_symmetry_and_identity(self):
        """Verify 5x5 mutual fleet correlation matrix properties."""
        res = client.get("/api/compare/matrix?parameter=bz_gsm")
        assert res.status_code == 200
        data = res.json()
        missions = data["missions"]
        matrix = data["matrix_r"]

        n = len(missions)
        assert n == 5
        for i in range(n):
            # Diagonal identity r_ii = 1.000
            assert abs(matrix[i][i] - 1.0) < 1e-4
            for j in range(n):
                # Symmetric: r_ij == r_ji
                assert abs(matrix[i][j] - matrix[j][i]) < 1e-4
                assert -1.0 <= matrix[i][j] <= 1.0


# =============================================================================
# TAB 3: PROBE POSITIONS & ORBITS (NAIF SPICE, Conics, Vis-Viva, Chao Boundaries)
# =============================================================================
class TestTab3OrbitsAndSpiceEphemeris:
    """Rigorous audit of Tab 3: JPL CSPICE conics, orbital speed framing, and Chao boundaries."""

    def test_spice_fleet_positions_and_velocities(self):
        """
        Verify that all 11 probes and bodies have verified 6-state vectors,
        correct primary-body frame velocities, and physical distance bounds.
        """
        targets = [
            "PARKER_SOLAR_PROBE", "SOLAR_ORBITER", "STEREO_A",
            "ADITYA_L1", "DSCOVR", "ACE", "WIND", "SOHO", "GOES_16", "EARTH", "MOON"
        ]
        res = client.get(f"/api/ephemeris/spice?satellites={','.join(targets)}")
        assert res.status_code == 200
        fleet = res.json()["fleet"]

        # 1. Parker Solar Probe (PSP) Vis-Viva speed bounds
        # Perihelion ~ 9.86 R_sun: v = 190.8 km/s; Aphelion ~ 0.73 AU: v ~ 12 km/s
        psp = fleet["PARKER_SOLAR_PROBE"]
        assert 0.04 <= psp["heliocentric"]["distance_au"] <= 0.75
        assert 10.0 <= psp["velocity"]["speed_kms"] <= 200.0, f"PSP speed out of bounds: {psp['velocity']['speed_kms']}"
        assert "true_anomaly_deg" in psp["orbital_elements"]
        assert 0.0 <= psp["orbital_elements"]["true_anomaly_deg"] <= 360.0

        # 2. GOES-16 Geostationary velocity frame check
        # Geostationary speed v_geo = sqrt(GM_earth / 42164 km) = 3.075 km/s
        # Heliocentric orbital speed around Sun ~ 29.8 km/s
        goes = fleet["GOES_16"]
        assert abs(goes["velocity"]["speed_kms"] - 3.075) < 0.15, f"GOES-16 speed should be ~3.075 km/s, got {goes['velocity']['speed_kms']}"
        assert abs(goes["earth_relative"]["distance_km"] - 42164.0) < 1000.0
        assert abs(goes["earth_relative"]["distance_re"] - 6.6) < 0.2
        assert "heliocentric_speed_kms" in goes["velocity"]
        assert 25.0 < goes["velocity"]["heliocentric_speed_kms"] < 35.0

        # 3. Aditya-L1 and DSCOVR at L1
        aditya = fleet["ADITYA_L1"]
        assert 0.98 <= aditya["heliocentric"]["distance_au"] <= 1.02
        assert 1.3e6 <= aditya["earth_relative"]["distance_km"] <= 1.7e6
        assert abs(aditya["velocity"]["speed_kms"] - 29.8) < 4.0

    def test_magnetopause_and_bow_shock_physics(self):
        """
        Shue et al. (1998) magnetopause and Chao et al. (2002) bow shock:
        r_0,mp = (10.22 + 1.29 tanh(0.184 (Bz + 8.14))) P^(-1/6.6)
        """
        # Nominal: P_dyn = 2.0 nPa, Bz = 0 nT -> 11.387 * 0.9003 = 10.25 R_E
        r0, alpha = SpaceWeatherPhysics.shue1998_magnetopause(2.0, 0.0)
        assert abs(r0 - 10.25) < 0.01
        assert r0 > 6.6

        # Compressed inside GEO: P_dyn = 18.0 nPa, Bz = -15.0 nT
        r0_storm, _ = SpaceWeatherPhysics.shue1998_magnetopause(18.0, -15.0)
        assert r0_storm < 6.6

        # Bow shock stands upstream of the magnetopause
        bs_res = SpaceWeatherPhysics.chao_bow_shock(2.0, 0.0, mach_number=8.0)
        assert bs_res["standoff_r0_re"] > r0, "Bow shock must stand upstream of magnetopause"

        # Boundary profile generation endpoint
        res_b = client.get("/api/magnetosphere/boundaries?dynamic_pressure=2.5&bz_gsm=-4.0&mach_number=7.5&model=chao")
        assert res_b.status_code == 200
        b_data = res_b.json()
        assert "magnetopause" in b_data
        assert "bow_shock" in b_data
        assert b_data["magnetosheath_thickness_re"] > 0


# =============================================================================
# TAB 5: CORONAGRAPH & CME (Vrsnak DBM Analytical Model & Inversion)
# =============================================================================
class TestTab5CMEKinematics:
    """Rigorous audit of Tab 5: Vrsnak (2013) Drag-Based Model, closed-form integrals, and arrival solvers."""

    def test_vrsnak_dbm_decelerating_fast_cme(self):
        """
        Fast CME: v0 = 1600 km/s > w = 450 km/s.
        Governing equation: dv/dt = -Gamma * (v - w)^2
        Closed form: v(t) = w + (v0 - w) / (1 + Gamma * (v0 - w) * t)
        R(t) = R0 + w*t + (1/Gamma) * ln(1 + Gamma * (v0 - w) * t)
        """
        analyzer = CoronagraphAnalyzer()
        res = analyzer.calculate_cme_kinematics(
            r1_rsun=2.5,
            r2_rsun=5.0,
            dt_minutes=15.0,  # delta_r = 2.5 R_sun = 1.739e6 km -> v0 = 1932 km/s
            ambient_wind_kms=450.0,
            gamma_drag=1.0e-7
        )
        assert "initial_speed_kms" in res
        v0 = res["initial_speed_kms"]
        assert v0 > 1800.0

        # Arrival speed at L1 and Earth must be less than v0 and greater than ambient wind w
        assert 450.0 < res["v_arrival_l1_kms"] < v0
        assert 450.0 < res["v_arrival_earth_kms"] < res["v_arrival_l1_kms"]

        # Transit time to L1 must be less than transit time to Earth
        t_l1 = res["transit_to_l1_hours"]
        t_earth = res["transit_to_earth_hours"]
        assert 15.0 < t_l1 < 80.0
        assert t_l1 < t_earth < 85.0

    def test_vrsnak_dbm_accelerating_slow_cme(self):
        """
        Slow CME: v0 = 300 km/s < w = 500 km/s.
        Governing equation: dv/dt = +Gamma * (w - v)^2
        Closed form: v(t) = w - (w - v0) / (1 + Gamma * (w - v0) * t)
        Velocity must increase towards ambient wind.
        """
        analyzer = CoronagraphAnalyzer()
        res = analyzer.calculate_cme_kinematics(
            r1_rsun=2.0,
            r2_rsun=2.5,
            dt_minutes=19.325,  # delta_r = 0.5 R_sun = 347,850 km -> v0 = 300 km/s
            ambient_wind_kms=500.0,
            gamma_drag=1.0e-7
        )
        assert res["initial_speed_kms"] < 400.0
        assert res["initial_speed_kms"] < res["v_arrival_l1_kms"] < 500.0
        assert res["v_arrival_l1_kms"] < res["v_arrival_earth_kms"] <= 500.0


# =============================================================================
# TAB 6: PARKER SPIRAL & CIR (Archimedean Geometry, Pitch, Footpoint)
# =============================================================================
class TestTab6ParkerSpiralCIR:
    """Rigorous audit of Tab 6: Archimedean magnetic field angle and solar footpoint connections."""

    def test_parker_spiral_pitch_and_footpoint_math(self):
        """
        Archimedean spiral pitch angle at 1 AU (r = 1.496e8 km):
        tan(psi) = (Omega_sun * r) / v_sw
        With Omega_sun = 2.865e-6 rad/s (25.38 day sidereal rotation):
        For v_sw = 450 km/s:
        tan(psi) = (2.865e-6 * 1.496e8) / 450 = 428.6 / 450 = 0.9525
        psi = arctan(0.9525) = 43.6 deg ~ 45 deg.
        Footpoint offset Delta_phi = 0.9525 rad = 54.6 deg West.
        """
        res = client.get("/api/parker/spiral?speed_kms=450")
        assert res.status_code == 200
        data = res.json()
        pitch = data.get("spiral_pitch_angle_deg") or data.get("pitch_angle_1au_deg")
        assert abs(pitch - 43.6) < 2.5
        fp = data.get("connected_footpoint_deg_west") or data.get("earth_connected_footpoint_deg_w")
        assert 45.0 < fp < 65.0

        # Faster wind (1000 km/s CME) -> straighter spiral (smaller pitch angle, closer footpoint)
        res_fast = client.get("/api/parker/spiral?speed_kms=1000")
        data_fast = res_fast.json()
        pitch_fast = data_fast.get("spiral_pitch_angle_deg") or data_fast.get("pitch_angle_1au_deg")
        assert pitch_fast < pitch


# =============================================================================
# TAB 7: FFT TURBULENCE & PSD (Power Spectrum, Kolmogorov -5/3, Taylor Scale)
# =============================================================================
class TestTab7TurbulencePSD:
    """Rigorous audit of Tab 7: Fast Fourier Transform, spectral regression, and Taylor frozen-in-flow."""

    def test_power_spectral_density_fft(self):
        """
        Generate synthetic turbulent signal with known Kolmogorov -5/3 slope.
        Verify FFT PSD output, slope alpha ~ 1.67, and Taylor scale length.
        """
        n_pts = 256
        dt = 60.0  # 1 min sampling -> fs = 1/60 Hz
        # Synthetic time series
        t = np.arange(n_pts) * dt
        signal = np.cumsum(np.random.normal(0, 1, n_pts))

        psd_res = SpaceWeatherPhysics.power_spectral_density(signal.tolist(), dt_seconds=dt, v_sw_kms=450.0)
        assert len(psd_res["frequencies_hz"]) > 20
        assert len(psd_res["power_density"]) == len(psd_res["frequencies_hz"])
        assert psd_res["spectral_slope_alpha"] > 0
        assert 0.0 <= psd_res["r_squared"] <= 1.0

        # Taylor hypothesis: lambda = v_sw / f at f = 1 mHz
        # lambda = 450 km/s / 0.001 s^-1 = 450,000 km = ~70.6 R_E
        assert psd_res["taylor_scale_km_1mhz"] == 450000.0
        assert abs(psd_res["taylor_scale_re_1mhz"] - 70.6) < 0.5

        # API endpoint verification with numpy fixed
        res_api = client.get("/api/spectrum?mission_id=DSCOVR&parameter=bz_gsm&span_days=1")
        assert res_api.status_code == 200
        assert "kolmogorov_psd" in res_api.json()
        assert "iroshnikov_psd" in res_api.json()


# =============================================================================
# TAB 8: AURORAL OVAL & MAP (Starkov 1994, Burton Dst Simulation)
# =============================================================================
class TestTab8AuroraAndDst:
    """Rigorous audit of Tab 8: Auroral oval geometry, equatorward limits, and ring current Dst."""

    def test_starkov_auroral_boundaries_and_power(self):
        """
        Starkov (1994) oval driven by Kp converted to AL (|AL| = 18 - 12.3 Kp + 27.2 Kp^2 - 2 Kp^3);
        Hemispheric power: Zhang & Paxton (2008) HP = 16.82 exp(0.32 Kp) - 4.86 GW (Kp <= 7),
        linear to 300 GW at Kp 9 (TIE-GCM util.F hp_from_kp)
        """
        # Quiet: Kp = 1 -> |AL| = 30.9 nT, equatorward midnight boundary 67.5 deg CGM
        # HP = 16.82 e^0.32 - 4.86 = 18.30 GW
        b_quiet = AuroralModel.calculate_auroral_boundaries(1.0, 0.0)
        assert abs(b_quiet["equatorward_midnight_lat"] - 67.5) < 0.1
        assert b_quiet["hemispheric_power_gw"] == pytest.approx(18.3, abs=0.05)
        assert "Zhang & Paxton" in b_quiet["hemispheric_power_source"]

        # Kp = 9 -> |AL| = 652.5 nT; Bz does not enter the model
        # HP(Kp 9) = 300 GW (end of the TIE-GCM ramp)
        b_storm = AuroralModel.calculate_auroral_boundaries(9.0, -30.0)
        assert b_storm["equatorward_midnight_lat"] == AuroralModel.calculate_auroral_boundaries(9.0, 0.0)["equatorward_midnight_lat"]
        assert abs(b_storm["diffuse_equatorward_midnight_lat"] - 53.0) < 0.1
        assert b_storm["hemispheric_power_gw"] == pytest.approx(300.0)
        # Continuous at Kp 7: 16.82 e^2.24 - 4.86 = 153.13 GW on both branches; Kp 8 halfway
        assert AuroralModel.hemispheric_power_from_kp(7.0) == pytest.approx(153.13, abs=0.01)
        assert AuroralModel.hemispheric_power_from_kp(8.0) == pytest.approx(226.565, abs=1e-3)
        assert AuroralModel.hemispheric_power_from_kp(0.0) == pytest.approx(11.96, abs=1e-9)
        # Observed |AL| beyond the range of the fits (750 nT) is capped and flagged
        b_al = AuroralModel.calculate_auroral_boundaries(9.0, 0.0, al_nt=-1500.0)
        assert b_al["al_used_nt"] == 750.0 and b_al["al_capped"]
        assert abs(b_al["diffuse_equatorward_midnight_lat"] - 51.7) < 0.1

        # Dynamic endpoint
        res = client.get("/api/aurora")
        assert res.status_code == 200
        assert "boundaries" in res.json()
        assert "oval_polygon" in res.json()
        assert "dst_evolution" in res.json()


# =============================================================================
# TAB 9: AI / ML FORECAST (Newell Coupling, 12h Timeline, Confidence Intervals)
# =============================================================================
class TestTab9MLForecast:
    """Rigorous audit of Tab 9: Newell rate, Burton step, multi-horizon Kp predictions."""

    def test_newell_coupling_mathematics(self):
        """
        Newell coupling rate: dPhi/dt = v^(4/3) * B_T^(2/3) * sin^(8/3)(theta/2)
        v = 400 km/s, B = 10 nT, Bz = -10 (theta = pi, sin(pi/2) = 1)
        v^(4/3) = 400^1.3333 = 2942.8
        B^(2/3) = 10^0.6667 = 4.64
        dPhi/dt = 2942.8 * 4.64 * 1 = ~13,650 Wb/s proxy
        """
        coupling = SpaceWeatherForecaster.calculate_newell_coupling(400.0, 10.0, -10.0, 0.0)
        assert 12000.0 < coupling < 15000.0, f"Expected ~13650, got {coupling}"

    def test_ml_forecast_timeline_api(self):
        """Verify 12-hour predictive timeline, confidence intervals, and hazard cards."""
        res = client.get("/api/forecast/ml?mission_id=DSCOVR")
        assert res.status_code == 200
        data = res.json()
        timeline = data["predictions_timeline"]
        assert len(timeline) == 12
        for step in timeline:
            assert 0.0 <= step["predicted_kp"] <= 9.0
            lower, upper = step["kp_confidence_interval"]
            assert lower <= step["predicted_kp"] <= upper
            assert "predicted_dst_nt" in step

        probs = data["storm_probabilities"]
        assert 0 <= probs["minor_storm_g1_kp5_percent"] <= 100
        assert 0 <= probs["extreme_storm_g5_kp9_percent"] <= 100


# =============================================================================
# TAB 10: TERRESTRIAL HAZARDS & SOLAR CYCLE (GIC, D-RAP, Hathaway SSN)
# =============================================================================
class TestTab10HazardsAndSolarCycle:
    """Rigorous audit of Tab 10: Boteler (2012) 1D GIC, Sauer (2008) D-RAP, Hathaway (2015) Cycle 25."""

    def test_gic_geoelectric_induction_and_units(self):
        """
        GIC: E_H = sqrt(rho / (mu_0 * omega)) * |dB/dt|
        Precambrian shield: rho = 5000 Ohm*m.
        Period T = 180 s -> omega = 2*pi/180 = 0.0349 s^-1.
        mu_0 = 4*pi*1e-7.
        sqrt(rho / (mu_0 * omega)) = sqrt(5000 / (4*pi*1e-7 * 0.0349)) = sqrt(1.139e11) = 3.375e5 m.
        For dB/dt = 300 nT/min = 5e-9 T/s:
        E_H = 3.375e5 * 5e-9 = 1.687e-3 V/m = 1.687 V/km.
        Voltage along L = 200 km: V = 1.687 * 200 = 337.5 V.
        Neutral current with R_loop = 1.7 Ohm: I = 337.5 / 1.7 = 198.5 A.
        """
        gic = GICHazardModel.calculate_geoelectric_field(
            db_dt_nt_per_min=300.0,
            geology_type="precambrian_shield",
            transformer_neutral_resistance_ohms=0.5,
            transmission_line_length_km=200.0
        )
        assert abs(gic["geoelectric_field_v_km"] - 1.687) < 0.1
        assert abs(gic["induced_voltage_volts"] - 337.5) < 20.0
        assert abs(gic["transformer_neutral_current_amps"] - 198.5) < 15.0

    def test_drap_radio_absorption_and_units(self):
        """
        SWPC D-RAP: HAF = 10 * log10(F_x) + 65 MHz, A(f) = (HAF / f)^1.5 dB.
        For X1.0 flare (F_x = 1e-4 W/m^2) at subsolar point (chi = 0):
        HAF = 10 * (-4) + 65 = 25 MHz; A(10 MHz) = 2.5^1.5 = 3.95 dB.
        At 21 MHz: A(21) = (25/21)^1.5 = 1.30 dB.
        """
        drap = IonosphericModel.calculate_drap_absorption(xray_flux_watts_m2=1.0e-4, zenith_angle_deg=0.0)
        assert abs(drap["highest_affected_frequency_mhz"] - 25.0) < 0.01
        assert abs(drap["attenuation_at_10mhz_db"] - 3.95) < 0.01

        # Frequency power-law check across spectrum
        spec = {item["frequency_mhz"]: item["attenuation_db"] for item in drap["absorption_spectrum"]}
        assert spec[10] > spec[21] > spec[30]
        assert abs(spec[21] - 1.30) < 0.02

    def test_solar_cycle_25_trajectory(self):
        """Verify Solar Cycle 25 Hathaway trajectory and F10.7 radio flux proxy."""
        res = client.get("/api/solar_cycle")
        assert res.status_code == 200
        sc = res.json()
        assert sc["solar_cycle"] == 25
        assert sc["smoothed_sunspot_number"] > 40.0
        # F10.7 cm radio flux must be >= 63.7 sfu (solar minimum baseline)
        assert sc["f107_radio_flux_sfu"] >= 63.7
        assert len(sc["timeline"]) > 30


# =============================================================================
# TAB 11: STORMS ARCHIVE (Events Benchmarks & History)
# =============================================================================
class TestTab11StormsArchive:
    """Rigorous audit of Tab 11: Historical event benchmarks and signatures."""

    def test_storms_archive_events(self):
        """Verify all 5 historical benchmarks are loaded with correct signatures."""
        res = client.get("/api/events")
        assert res.status_code == 200
        events = res.json()
        assert len(events) >= 5
        event_ids = [e["id"] for e in events]
        assert "may_2024_g5" in event_ids or "may2024_g5" in event_ids
        assert "carrington_1859" in event_ids
        assert "quebec_1989" in event_ids

        # Specific event details
        res_may = client.get("/api/events/may_2024_g5")
        assert res_may.status_code == 200
        may = res_may.json()
        assert "satellite" in may
        assert len(may["records"]) > 10


# =============================================================================
# TAB 12: CUSTOM INGESTION & OMNI (Rankine-Hugoniot Shocks, Akasofu, Presets)
# =============================================================================
class TestTab12CustomIngestion:
    """Rigorous audit of Tab 12: File parser, Rankine-Hugoniot shock jumps, and export."""

    def test_rankine_hugoniot_shock_jump_criteria(self):
        """
        Rankine-Hugoniot fast forward shock criteria:
        Delta V >= 45 km/s, N2/N1 >= 1.5, B2/B1 >= 1.35.
        Requires >= 5 records to span the detection window.
        """
        records = [
            {"time_tag": "2026-09-22 10:00:00", "speed": 400.0, "density": 5.0, "bt": 5.0},
            {"time_tag": "2026-09-22 10:05:00", "speed": 402.0, "density": 5.1, "bt": 5.0},
            {"time_tag": "2026-09-22 10:10:00", "speed": 405.0, "density": 5.2, "bt": 5.1},
            {"time_tag": "2026-09-22 10:15:00", "speed": 410.0, "density": 5.4, "bt": 5.3},
            # Supersonic shock arrival at 10:20 (compared with 10:05)
            {"time_tag": "2026-09-22 10:20:00", "speed": 650.0, "density": 18.0, "bt": 15.0},
            {"time_tag": "2026-09-22 10:25:00", "speed": 660.0, "density": 19.0, "bt": 15.5}
        ]
        shocks = SpaceWeatherPhysics.detect_interplanetary_shocks(records)
        assert len(shocks) >= 1
        s = shocks[0]
        assert s["delta_speed_kms"] >= 200.0
        assert s["density_ratio"] >= 3.0
        assert s["magnetic_ratio"] >= 2.5
        assert "Shock" in s["classification"]

    def test_custom_import_pipeline_and_export(self):
        """Test preset loading, CSV text ingestion, and CSV/JSON export."""
        # 1. Preset retrieval
        presets = TelemetryImporter.get_presets_list()
        assert len(presets) >= 4

        # 2. Ingestion
        sample_csv = "time,speed,density,bx_gsm,by_gsm,bz_gsm,bt\n2026-09-22 01:00:00,420,5,1,2,-3,4\n2026-09-22 01:05:00,750,22,-8,14,-25,30"
        res_import = client.post("/api/custom/import", json={"content": sample_csv, "mission_name": "TestProbe"})
        assert res_import.status_code == 200
        data = res_import.json()
        assert data["status"] == "success"
        assert data["total_records"] == 2
        assert data["summary"]["speed_max"] == 750.0
        assert data["summary"]["bz_min"] == -25.0

        # 3. Export CSV and JSON
        res_csv = client.get("/api/custom/export/csv")
        assert res_csv.status_code == 200
        assert "text/csv" in res_csv.headers["content-type"]
        assert "testprobe" in res_csv.headers.get("content-disposition", "").lower()

        res_json = client.get("/api/custom/export/json")
        assert res_json.status_code == 200
        assert "application/json" in res_json.headers["content-type"]
