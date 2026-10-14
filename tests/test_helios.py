"""
Expanded Test Suite for HELIOS-L1 Scientific and Telemetry Engines.
"""
import math
import pytest
import numpy as np
from fastapi.testclient import TestClient

from helios.core.science import SpaceWeatherPhysics
from helios.core.downloader import DataDownloader
from helios.core.comparator import SatelliteComparator
from helios.core.orbital_mechanics import OrbitalMechanics
from helios.core.exporter import DataExporter
from helios.core.aurora_model import AuroralModel
from helios.core.coronagraph import CoronagraphAnalyzer
from helios.core.parker_spiral import ParkerSpiralModel
from helios.core.report_generator import ScientificReportGenerator
from helios.api.server import app

# The server only answers requests addressed to a loopback host (helios.api.guard).
LOCAL = "http://127.0.0.1:8765"

client = TestClient(app, base_url=LOCAL)

def test_space_weather_physics_equations():
    # 1. Dynamic pressure
    pdyn = SpaceWeatherPhysics.dynamic_pressure(5.0, 400.0)
    assert pdyn == pytest.approx(1.6)  # OMNI flow pressure: 2.0e-6 N V^2

    # 2. Magnetopause standoff
    rmp = SpaceWeatherPhysics.magnetopause_standoff(2.0, 0.0)
    assert 9.0 < rmp < 11.5

    # 3. Akasofu Epsilon
    eps = SpaceWeatherPhysics.akasofu_epsilon(500.0, 11.18, 5.0, -10.0)
    assert eps > 50.0

    # 4. Propagation delay
    delay = SpaceWeatherPhysics.propagation_delay_minutes(1500000.0, 500.0)
    assert 40.0 < delay < 55.0

    # 5. NOAA Scale classification
    cls_quiet = SpaceWeatherPhysics.classify_noaa_scales(kp=1.0, bz_gsm=2.0, xray_flux=1e-7)
    assert "Quiet" in cls_quiet["g_scale"]
    assert "Northward" in cls_quiet["bz_alert"]
    assert cls_quiet["r_scale"] == "R0 (None)"
    # No X-ray measurement: no R level, as for missing proton data.
    assert SpaceWeatherPhysics.classify_noaa_scales(kp=1.0, bz_gsm=2.0, xray_flux=None)["r_scale"].startswith("R--")

    cls_storm = SpaceWeatherPhysics.classify_noaa_scales(kp=9.0, bz_gsm=-25.0, xray_flux=1.5e-4)
    assert "G5" in cls_storm["g_scale"]
    assert "CRITICAL" in cls_storm["bz_alert"]
    assert "R3" in cls_storm["r_scale"]

def test_interplanetary_shock_detection():
    records = []
    for i in range(10):
        records.append({
            "time_tag": f"2026-09-20 12:{i*5:02d}:00",
            "speed": 350.0 if i < 5 else 620.0,
            "density": 4.0 if i < 5 else 18.0,
            "bt": 5.0 if i < 5 else 16.0
        })
    shocks = SpaceWeatherPhysics.detect_interplanetary_shocks(records)
    assert len(shocks) > 0
    assert shocks[0]["delta_speed_kms"] >= 200.0

def test_power_spectral_density():
    t = np.linspace(0, 100, 128)
    signal = np.sin(2 * np.pi * 0.05 * t) + np.random.normal(0, 0.1, 128)
    psd = SpaceWeatherPhysics.power_spectral_density(signal.tolist(), v_sw_kms=450.0)
    assert len(psd["frequencies_hz"]) > 0
    assert len(psd["power_density"]) > 0
    assert "spectral_slope_alpha" in psd
    assert "cascade_regime" in psd
    assert "taylor_scale_km_1mhz" in psd
    assert psd["taylor_scale_km_1mhz"] == 450000.0
    assert len(psd["kolmogorov_psd"]) == len(psd["frequencies_hz"])

def test_synthetic_telemetry_generation():
    dl = DataDownloader()
    telemetry = dl.generate_synthetic_telemetry("DSCOVR", hours=6, condition="active")
    assert len(telemetry) == (6 * 60) // 5
    first = telemetry[0]
    assert "speed" in first
    assert "bz_gsm" in first
    assert "dynamic_pressure" in first
    assert "l1_travel_time_min" in first

def test_satellite_comparator():
    dl = DataDownloader()
    data_a = dl.generate_synthetic_telemetry("DSCOVR", hours=12, condition="active")
    data_b = dl.generate_synthetic_telemetry("ADITYA_L1", hours=12, condition="active")

    comp = SatelliteComparator.compare_satellites(
        data_a, data_b, "DSCOVR", "Aditya-L1", parameter="bz_gsm"
    )
    assert comp["status"] == "success"
    assert "correlation_r" in comp["metrics"]
    assert "r_squared" in comp["metrics"]
    assert "optimal_lag_minutes" in comp["lag_analysis"]
    assert len(comp["scatter_points"]) > 0

def test_orbital_mechanics():
    lagrange = OrbitalMechanics.get_lagrange_points()
    assert "L1" in lagrange
    assert "L2" in lagrange
    assert lagrange["L1"]["x_mkm"] == -1.496

    orbits = OrbitalMechanics.get_satellite_orbits()
    assert "DSCOVR" in orbits
    assert "ADITYA_L1" in orbits
    assert "ACE" in orbits
    assert len(orbits["DSCOVR"]["path"]) > 0

def test_auroral_model():
    res = AuroralModel.calculate_auroral_boundaries(kp=7.0, bz_gsm=-12.0)
    # Starkov (1994): Kp 7 -> |AL| = 578.7 nT, equatorward midnight boundary 59.9 deg CGM
    assert res["equatorward_midnight_lat"] == pytest.approx(59.9, abs=0.1)
    assert res["hemispheric_power_gw"] > 50.0
    assert len(res["visible_regions"]) > 0

    dl = DataDownloader()
    sample = dl.generate_synthetic_telemetry("DSCOVR", hours=4, condition="storm")
    dst_sim = AuroralModel.simulate_dst_evolution(sample)
    assert len(dst_sim) == len(sample)
    assert "dst_predicted_nt" in dst_sim[-1]

def test_coronagraph_kinematics():
    feeds = CoronagraphAnalyzer.get_coronagraph_feeds()
    assert "SOHO_LASCO_C2" in feeds
    assert "SOHO_LASCO_C3" in feeds

    # Test CME moving from 2.5 to 6.0 R_sun in 30 minutes
    kin = CoronagraphAnalyzer.calculate_cme_kinematics(r1_rsun=2.5, r2_rsun=6.0, dt_minutes=30.0)
    assert kin["initial_speed_kms"] > 1000.0
    assert kin["transit_to_earth_hours"] > 10.0
    assert kin["l1_to_earth_lead_time_minutes"] > 10.0

def test_parker_spiral():
    pitch = ParkerSpiralModel.spiral_pitch_angle(400.0)
    assert 40.0 < pitch < 52.0

    footpoint = ParkerSpiralModel.magnetic_footpoint_longitude(400.0)
    assert 45.0 < footpoint < 65.0

    streamlines = ParkerSpiralModel.generate_parker_spiral_lines(400.0, num_streamlines=6)
    assert len(streamlines) == 6
    assert len(streamlines[0]["points"]) > 10

def test_report_generator():
    dl = DataDownloader()
    data = dl.generate_synthetic_telemetry("DSCOVR", hours=2)
    cls = SpaceWeatherPhysics.classify_noaa_scales(3.0, -2.0, 1e-6, proton_flux=15.0)
    shocks = SpaceWeatherPhysics.detect_interplanetary_shocks(data)
    auroral = AuroralModel.calculate_auroral_boundaries(3.0, -2.0)

    html = ScientificReportGenerator.generate_html_bulletin("DSCOVR", data, cls, shocks, auroral)
    assert "HELIOS-L1" in html
    assert "Solar Wind Velocity" in html
    assert "S1 (Minor)" in html

    md = ScientificReportGenerator.generate_markdown_executive_summary("DSCOVR", data, cls, shocks, auroral)
    assert "HELIOS-L1 SPACE WEATHER EXECUTIVE SUMMARY" in md
    assert "OPERATIONAL ALERT POSTURE" in md
    assert "24-HOUR SYNOPTIC TELEMETRY EXTREMA" in md
    assert "SHOCK CANDIDATES" in md

def test_api_endpoints():
    # 1. Status
    res = client.get("/api/status")
    assert res.status_code == 200
    assert res.json()["app_name"] == "HELIOS-L1"

    # 2. Missions
    res = client.get("/api/missions")
    assert res.status_code == 200

    # 3. Telemetry
    res = client.get("/api/telemetry/DSCOVR?span_days=1")
    assert res.status_code == 200

    # 4. Compare
    res = client.get("/api/compare?mission_a=DSCOVR&mission_b=ADITYA_L1&parameter=bz_gsm")
    assert res.status_code == 200

    # 5. Aurora
    res = client.get("/api/aurora?kp=4.0&bz_gsm=-5.0")
    assert res.status_code == 200
    assert "boundaries" in res.json()

    # 6. Coronagraph
    res = client.get("/api/coronagraph/feeds")
    assert res.status_code == 200
    kin_res = client.post("/api/coronagraph/kinematics", json={"r1_rsun": 2.0, "r2_rsun": 5.0, "dt_minutes": 25.0})
    assert kin_res.status_code == 200
    assert kin_res.json()["initial_speed_kms"] > 0

    # 7. Parker Spiral
    res = client.get("/api/parker_spiral?speed_kms=450")
    assert res.status_code == 200
    assert "streamlines" in res.json()

    # 8. HTML Report
    res = client.get("/api/report/html?mission_id=DSCOVR")
    assert res.status_code == 200
    assert "text/html" in res.headers["content-type"]

    # 9. Custom Import & Presets Suite
    presets_res = client.get("/api/custom/presets")
    assert presets_res.status_code == 200
    assert len(presets_res.json()["presets"]) >= 4

    preset_item_res = client.get("/api/custom/presets/may2024_g5")
    assert preset_item_res.status_code == 200
    assert "csv_content" in preset_item_res.json()["preset"]

    # Ingest custom dataset matching current DSCOVR timestamps for cross-comparison
    dscovr_data = client.get("/api/telemetry/DSCOVR?span_days=1").json()["records"]
    csv_rows = ["time,speed,density,bz_gsm"]
    for r in dscovr_data[:10]:
        csv_rows.append(f"{r['time_tag']},{r['speed']},{r['density']},{r['bz_gsm']}")
    csv_sample = "\n".join(csv_rows)

    import_res = client.post("/api/custom/import", json={"content": csv_sample, "mission_name": "TestSat"})
    assert import_res.status_code == 200
    assert import_res.json()["status"] == "success"
    assert import_res.json()["total_records"] == 10
    assert "summary" in import_res.json()

    latest_res = client.get("/api/custom/latest")
    assert latest_res.status_code == 200
    assert latest_res.json()["mission_name"] == "TestSat"

    csv_export_res = client.get("/api/custom/export/csv")
    assert csv_export_res.status_code == 200
    assert "text/csv" in csv_export_res.headers["content-type"]

    json_export_res = client.get("/api/custom/export/json")
    assert json_export_res.status_code == 200
    assert "application/json" in json_export_res.headers["content-type"]

    comp_custom_res = client.get("/api/compare?mission_a=DSCOVR&mission_b=CUSTOM&parameter=bz_gsm")
    assert comp_custom_res.status_code == 200
    assert comp_custom_res.json()["status"] == "success"

    # 10. Fleet Matrix
    res = client.get("/api/compare/matrix?parameter=bz_gsm")
    assert res.status_code == 200
    assert "matrix_r" in res.json()
    assert len(res.json()["missions"]) == 5

    # 11. ML Forecast
    res = client.get("/api/forecast/ml?mission_id=DSCOVR")
    assert res.status_code == 200
    assert "predictions_timeline" in res.json()
    assert "hazard_assessment" in res.json()

    # 12. Reports (HTML & Markdown Executive Summary)
    res_html = client.get("/api/report/html?mission_id=DSCOVR")
    assert res_html.status_code == 200
    assert "text/html" in res_html.headers["content-type"]
    assert "HELIOS-L1 Space Weather Scientific Bulletin" in res_html.text

    res_md = client.get("/api/report/markdown?mission_id=DSCOVR")
    assert res_md.status_code == 200
    assert "text/markdown" in res_md.headers["content-type"]
    assert "HELIOS-L1 SPACE WEATHER EXECUTIVE SUMMARY" in res_md.text

def test_telemetry_importer_direct():
    from helios.core.importer import TelemetryImporter
    csv_data = "Epoch,V_bulk,N_p,B_z\n2026-09-20 01:00:00,400.5,4.2,2.5\n2026-09-20 01:05:00,550.0,12.0,-9.2"
    parsed = TelemetryImporter.parse_csv_or_text(csv_data, "Custom-OMNI")
    assert parsed["status"] == "success"
    assert parsed["total_records"] == 2
    assert parsed["records"][0]["speed"] == 400.5
    assert parsed["records"][1]["bz_gsm"] == -9.2
    assert "summary" in parsed
    assert parsed["summary"]["speed_min"] == 400.5
    assert parsed["summary"]["speed_max"] == 550.0
    assert parsed["summary"]["bz_min"] == -9.2
    assert parsed["summary"]["bz_max"] == 2.5

    # Test Presets
    presets = TelemetryImporter.get_presets_list()
    assert len(presets) >= 4
    preset_ids = [p["id"] for p in presets]
    assert "may2024_g5" in preset_ids
    assert "bastille_2000" in preset_ids
    assert "carrington_1859" in preset_ids

    detail = TelemetryImporter.get_preset("may2024_g5")
    assert detail is not None
    assert "csv_content" in detail
    parsed_preset = TelemetryImporter.parse_csv_or_text(detail["csv_content"], detail["name"])
    # The cards show the number of rows ("pts"); it was missing from the list.
    listed = next(p for p in presets if p["id"] == "may2024_g5")
    assert listed["records_count"] == parsed_preset["total_records"] > 0
    assert parsed_preset["status"] == "success"
    assert parsed_preset["summary"]["speed_max"] >= 800.0
    assert parsed_preset["summary"]["bz_min"] <= -40.0
    assert len(parsed_preset["detected_shocks"]) >= 1

def test_space_weather_ml_forecaster():
    from helios.core.ml_forecast import SpaceWeatherForecaster
    dl = DataDownloader()
    data = dl.generate_synthetic_telemetry("DSCOVR", hours=6)
    forecast = SpaceWeatherForecaster.forecast_geomagnetic_storm(data)

    assert "model_version" in forecast
    assert "predictions_timeline" in forecast
    assert len(forecast["predictions_timeline"]) == 12
    assert "power_grid_gic" in forecast["hazard_assessment"]
    assert "aviation_hf" in forecast["hazard_assessment"]
    assert "satellite_ops" in forecast["hazard_assessment"]

def test_scientific_references_and_data_provenance():
    # 1. Scientific references catalog
    ref_res = client.get("/api/references")
    assert ref_res.status_code == 200
    refs = ref_res.json()["references"]
    assert len(refs) >= 10
    assert any("Newell" in r["authors"] for r in refs)
    assert any("Akasofu" in r["authors"] for r in refs)
    assert any("Parker" in r["authors"] for r in refs)
    assert any("Boyle" in r["authors"] for r in refs)
    for r in refs:
        assert "doi" in r
        assert "doi_url" in r
        # Starkov (1994, Geomagn. Aeron.) has no DOI: such entries carry None
        assert r["doi_url"] is None or r["doi_url"].startswith("https://doi.org/")

    # 2. Data Providers catalog
    prov_res = client.get("/api/providers")
    assert prov_res.status_code == 200
    provs = prov_res.json()["providers"]
    assert len(provs) >= 6
    prov_ids = [p["id"] for p in provs]
    assert "NOAA_SWPC" in prov_ids
    assert "NASA_CDAWEB" in prov_ids
    assert "ISRO_ISSDC" in prov_ids
    assert "ESA_SOAR" in prov_ids
    assert "GFZ_POTSDAM" in prov_ids
    assert "WDC_KYOTO" in prov_ids
    for p in provs:
        assert "data_license" in p
        assert "terms_of_use" in p
        assert "url" in p

    # 3. Parameter definitions handbook
    param_res = client.get("/api/parameters")
    assert param_res.status_code == 200
    params = param_res.json()["parameters"]
    assert "speed" in params
    assert "bz_gsm" in params
    assert "bt" in params
    assert "density" in params
    assert "pdyn" in params
    assert "epsilon" in params
    assert "standoff" in params
    assert "polar_cap_potential" in params
    assert "ae_index" in params

    # 4. Individual parameter detail and aliases
    speed_res = client.get("/api/parameters/speed")
    assert speed_res.status_code == 200
    assert speed_res.json()["unit"] == "km/s"

    bz_res = client.get("/api/parameters/bz_gsm")
    assert bz_res.status_code == 200
    assert bz_res.json()["unit"] == "nT"

    alias_res = client.get("/api/parameters/rmp")
    assert alias_res.status_code == 200
    assert "Subsolar Magnetopause" in alias_res.json()["name"]

    not_found = client.get("/api/parameters/unknown_param_xyz")
    assert not_found.status_code == 404

def test_solar_cycle_progression():
    from helios.core.solar_cycle import SolarCycleEngine
    prog = SolarCycleEngine.calculate_cycle_25_progression(2024.75)
    assert prog["solar_cycle"] == 25
    assert prog["smoothed_sunspot_number"] > 140.0
    assert prog["f107_radio_flux_sfu"] > 150.0
    assert len(prog["timeline"]) > 30

    res = client.get("/api/solar_cycle?year=2024.5")
    assert res.status_code == 200
    assert "smoothed_sunspot_number" in res.json()

def test_drap_ionospheric_absorption():
    from helios.core.ionosphere import IonosphericModel
    # M5 flare (5e-5 W/m^2)
    abs_m5 = IonosphericModel.calculate_drap_absorption(5.0e-5, zenith_angle_deg=0.0)
    assert abs_m5["highest_affected_frequency_mhz"] > 10.0
    assert abs_m5["attenuation_at_10mhz_db"] > 3.0
    assert "R2" in abs_m5["r_scale"]

    # X10 flare (1e-3 W/m^2)
    abs_x10 = IonosphericModel.calculate_drap_absorption(1.0e-3, zenith_angle_deg=20.0)
    assert abs_x10["highest_affected_frequency_mhz"] > 25.0
    assert "R4" in abs_x10["r_scale"]

    res = client.get("/api/ionosphere/absorption?xray_flux=1e-4&zenith_angle=30")
    assert res.status_code == 200
    assert "highest_affected_frequency_mhz" in res.json()
    assert len(res.json()["absorption_spectrum"]) > 5

def test_gic_geoelectric_hazard():
    from helios.core.gic_model import GICHazardModel
    # Hydro-Quebec benchmark ~ 400 nT/min on resistive shield
    gic = GICHazardModel.calculate_geoelectric_field(
        db_dt_nt_per_min=400.0,
        geology_type="precambrian_shield",
        transmission_line_length_km=300.0
    )
    assert gic["geoelectric_field_v_km"] > 2.0
    assert gic["transformer_neutral_current_amps"] > 300.0
    assert "CRITICAL" in gic["hazard_classification"] or "SEVERE" in gic["hazard_classification"]

    # Sedimentary basin attenuation
    gic_sed = GICHazardModel.calculate_geoelectric_field(
        db_dt_nt_per_min=400.0,
        geology_type="sedimentary_basin",
        transmission_line_length_km=300.0
    )
    assert gic_sed["geoelectric_field_v_km"] < gic["geoelectric_field_v_km"]

    res = client.get("/api/gic/hazard?db_dt=250&geology=precambrian_shield")
    assert res.status_code == 200
    assert "geoelectric_field_v_km" in res.json()

def test_magnetospheric_boundaries_chao_and_shue():
    from helios.core.science import SpaceWeatherPhysics

    # 1. Nominal quiet solar wind conditions: P = 2.0 nPa, Bz = 0 nT
    r0_mp, alpha_mp = SpaceWeatherPhysics.shue1998_magnetopause(2.0, 0.0)
    assert 9.5 <= r0_mp <= 12.0
    assert 0.45 <= alpha_mp <= 0.70

    nom_bs = SpaceWeatherPhysics.chao_bow_shock(2.0, 0.0, mach_number=8.0)
    assert nom_bs["standoff_r0_re"] > r0_mp
    assert 12.0 <= nom_bs["standoff_r0_re"] <= 16.0
    assert abs(nom_bs["standoff_km"] - nom_bs["standoff_r0_re"] * 6371.0) < 40.0
    assert 0.50 <= nom_bs["flaring_alpha"] <= 0.95

    # 2. Extreme coronal mass ejection shock compression: P = 32.0 nPa, Bz = -25.0 nT
    shock = SpaceWeatherPhysics.calculate_magnetospheric_boundaries(32.0, -25.0, mach_number=4.0)
    assert shock["magnetopause"]["standoff_re"] < 6.6
    assert shock["magnetopause"]["inside_geo"] is True

    # 3. Mach number scaling: lower Mach expands Bow Shock standoff
    bs_low_mach = SpaceWeatherPhysics.chao_bow_shock(2.0, 0.0, mach_number=2.0)
    bs_high_mach = SpaceWeatherPhysics.chao_bow_shock(2.0, 0.0, mach_number=12.0)
    assert bs_low_mach["standoff_r0_re"] > bs_high_mach["standoff_r0_re"]

    # 4. Discrete 2D GSE boundary coordinates generation
    chao_bounds = SpaceWeatherPhysics.calculate_magnetospheric_boundaries(2.5, -4.0, mach_number=7.5, model="chao")
    assert chao_bounds["status"] == "success"
    assert "Chao" in chao_bounds["model"]
    assert len(chao_bounds["magnetopause"]["profile"]) == 60
    assert len(chao_bounds["bow_shock"]["profile"]) == 60
    assert chao_bounds["magnetosheath_thickness_re"] > 0
    assert chao_bounds["magnetosheath_thickness_km"] == round(chao_bounds["magnetosheath_thickness_re"] * 6371.0, 1)

    # 5. Farris & Russell (1994) bow shock on the Shue et al. (1998) magnetopause
    shue_bounds = SpaceWeatherPhysics.calculate_magnetospheric_boundaries(2.5, -4.0, mach_number=7.5, model="shue")
    assert shue_bounds["status"] == "success"
    assert "Farris & Russell" in shue_bounds["model"]
    assert len(shue_bounds["magnetopause"]["profile"]) == 60

    # 6. REST API Endpoint: GET /api/magnetosphere/boundaries
    res_api_chao = client.get("/api/magnetosphere/boundaries?dynamic_pressure=2.0&bz_gsm=0.0&mach_number=8.0&model=chao")
    assert res_api_chao.status_code == 200
    data = res_api_chao.json()
    assert data["status"] == "success"
    assert "magnetopause" in data
    assert "bow_shock" in data
    assert "magnetosheath_thickness_re" in data

    # Extreme shock API call verifying inside_geo flag
    res_api_shock = client.get("/api/magnetosphere/boundaries?dynamic_pressure=35.0&bz_gsm=-30.0&mach_number=4.0&model=chao")
    assert res_api_shock.status_code == 200
    assert res_api_shock.json()["magnetopause"]["inside_geo"] is True

def test_geospace_coupling_and_wave_dynamics():
    """
    Test wave speeds (Alfvén, Sound, Fast Magnetosonic), Mach numbers,
    Boyle et al. (1997) Polar Cap Potential, Newell Universal Coupling / AE proxy,
    convective electric field, and REST API GET /api/geospace/coupling.
    """
    # 1. Alfvén Speed: V_A = 21.812 * (B_t / sqrt(n))
    va = SpaceWeatherPhysics.alfven_speed(b_total_nt=10.0, density_cm3=4.0)
    assert 108.0 <= va <= 110.0

    # 2. Sound Speed: C_s = 0.1174 * sqrt(T)
    cs = SpaceWeatherPhysics.sound_speed(temp_k=100000.0)
    assert 36.0 <= cs <= 38.5

    # 3. Fast Magnetosonic Speed: V_ms = sqrt(V_A^2 + C_s^2)
    vms = SpaceWeatherPhysics.magnetosonic_speed(b_total_nt=10.0, density_cm3=4.0, temp_k=100000.0)
    assert vms > va
    assert vms > cs

    # 4. Mach numbers
    mach = SpaceWeatherPhysics.mach_numbers(speed_kms=450.0, b_total_nt=5.0, density_cm3=5.0, temp_k=100000.0)
    assert mach["alfven_mach"] > 1.0
    assert mach["magnetosonic_mach"] > 1.0

    # 5. Boyle et al. (1997) Polar Cap Potential
    phi_quiet = SpaceWeatherPhysics.polar_cap_potential(speed_kms=350.0, by_gsm_nt=1.0, bz_gsm_nt=5.0)
    assert phi_quiet["polar_cap_potential_kv"] < 50.0
    assert "NOMINAL" in phi_quiet["convection_state"]

    phi_storm = SpaceWeatherPhysics.polar_cap_potential(speed_kms=850.0, by_gsm_nt=10.0, bz_gsm_nt=-25.0)
    assert phi_storm["polar_cap_potential_kv"] >= 140.0
    assert "CRITICAL" in phi_storm["convection_state"]

    # 6. Auroral Electrojet proxy via Newell
    ae_quiet = SpaceWeatherPhysics.auroral_electrojet_ae(speed_kms=350.0, by_gsm_nt=1.0, bz_gsm_nt=5.0)
    assert ae_quiet["ae_index_nt"] < 150.0
    assert "QUIET" in ae_quiet["substorm_status"]

    ae_storm = SpaceWeatherPhysics.auroral_electrojet_ae(speed_kms=900.0, by_gsm_nt=15.0, bz_gsm_nt=-25.0)
    assert ae_storm["ae_index_nt"] >= 500.0
    assert "SUBSTORM" in ae_storm["substorm_status"] or "EXTREME" in ae_storm["substorm_status"]

    # 7. Convective electric field
    ey_north = SpaceWeatherPhysics.convective_electric_field(speed_kms=400.0, bz_gsm_nt=5.0)
    assert ey_north < 0  # Northward Bz suppresses convection
    ey_south = SpaceWeatherPhysics.convective_electric_field(speed_kms=500.0, bz_gsm_nt=-10.0)
    assert ey_south == 5.0  # -500 * -10 * 1e-3 = 5.0 mV/m

    # 8. REST API Endpoint: GET /api/geospace/coupling
    res = client.get("/api/geospace/coupling?speed_kms=550&density_cm3=8&b_total_nt=12&by_gsm_nt=-4&bz_gsm_nt=-8&temp_k=150000")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "success"
    assert "dynamic_pressure_npa" in data
    assert "wave_speeds" in data
    assert "mach_numbers" in data
    assert "polar_cap_potential" in data
    assert "auroral_electrojet" in data
    assert "akasofu_epsilon_gw" in data
    assert "convective_efield_mvm" in data
    assert data["convective_efield_mvm"] > 0

def test_vrsnak_dbm_cme_kinematics():
    # Test Vršnak et al. (2013) Drag-Based Model for fast CME
    fast_cme = CoronagraphAnalyzer.calculate_cme_kinematics(
        r1_rsun=2.0,
        r2_rsun=5.5,
        dt_minutes=25.0,
        ambient_wind_kms=420.0,
        gamma_drag=1.0e-7
    )
    assert fast_cme["model"] == "Vršnak et al. (2013) Drag-Based Model (DBM)"
    assert fast_cme["initial_speed_kms"] > 1200.0  # Fast liftoff
    assert fast_cme["v_arrival_earth_kms"] < fast_cme["initial_speed_kms"]  # Decelerated by aerodynamic drag
    assert fast_cme["v_arrival_earth_kms"] > 420.0  # Asymptotes to ambient wind
    assert 30.0 < fast_cme["transit_to_earth_hours"] < 90.0  # Realistic DBM transit time
    assert 20.0 < fast_cme["l1_to_earth_lead_time_minutes"] < 70.0  # Realistic warning window
    assert fast_cme["shock_compression_ratio"] >= 1.0

    # Test slow CME entrained and accelerated by fast solar wind stream
    slow_cme = CoronagraphAnalyzer.calculate_cme_kinematics(
        r1_rsun=2.0,
        r2_rsun=2.8,
        dt_minutes=40.0,
        ambient_wind_kms=600.0,
        gamma_drag=1.0e-7
    )
    assert slow_cme["initial_speed_kms"] < 350.0
    assert slow_cme["v_arrival_earth_kms"] > slow_cme["initial_speed_kms"]  # Accelerated by fast stream

def test_settings_and_system_concurrency_api():
    # 1. GET /api/settings
    res = client.get("/api/settings")
    assert res.status_code == 200
    data = res.json()
    assert "total_cpu_cores" in data
    assert "active_processors" in data
    assert "theme" in data
    assert "font_size" in data
    assert "timezone" in data
    assert data["total_cpu_cores"] >= 1

    # 2. POST /api/settings (pick a core count valid on any machine; CI runners have 2)
    target_cores = min(6, data["total_cpu_cores"])
    update_res = client.post("/api/settings", json={
        "processors": target_cores,
        "theme": "deep-space",
        "font_size": "compact",
        "timezone": "Asia/Kolkata"
    })
    assert update_res.status_code == 200
    updated = update_res.json()
    assert updated["active_processors"] == target_cores
    assert updated["theme"] == "deep-space"
    assert updated["font_size"] == "compact"
    assert updated["timezone"] == "Asia/Kolkata"

    # Reset back to nominal
    client.post("/api/settings", json={
        "processors": 4,
        "theme": "mission-slate",
        "font_size": "normal",
        "timezone": "UTC"
    })

def test_parker_solar_probe_ephemeris_physics():
    # NASA Parker Solar Probe (PSP) Physical Constants:
    # a = 0.3879 AU, e = 0.8819, Perihelion = 9.86 R_sun (~0.0458 AU, 6.85M km), Aphelion = 0.730 AU
    au_km = 149597870.7
    r_sun_km = 696340.0
    mu_sun = 1.3271244e11  # km^3/s^2 (G * M_sun)
    a_au = 0.3879
    a_km = a_au * au_km

    # 1. Vis-Viva speed at perihelion (r = 9.86 R_sun = 0.0458 AU = 6,851,582 km)
    r_peri_km = 0.0458 * au_km
    v_peri_kms = math.sqrt(mu_sun * (2.0 / r_peri_km - 1.0 / a_km))
    # Must be ~190.8 km/s (or ~687,000 km/h)
    assert 185.0 < v_peri_kms < 195.0, f"Expected perihelion velocity ~191 km/s, got {v_peri_kms}"

    # 2. Vis-Viva speed at aphelion (r = 0.730 AU = 109,206,445 km)
    r_aph_km = 0.730 * au_km
    v_aph_kms = math.sqrt(mu_sun * (2.0 / r_aph_km - 1.0 / a_km))
    # Must be ~12.0 km/s (or ~43,000 km/h)
    assert 10.0 < v_aph_kms < 14.0, f"Expected aphelion velocity ~12 km/s, got {v_aph_kms}"

    # 3. Keplerian period check: T^2 = a^3  ==>  T = a^1.5 years = 88.2 days
    t_years = a_au ** 1.5
    t_days = t_years * 365.25
    assert 86.0 < t_days < 90.0, f"Expected orbital period ~88.2 days, got {t_days}"

def test_missions_catalog_contains_psp_and_solo():
    from helios.config import MISSIONS
    assert "PARKER_SOLAR_PROBE" in MISSIONS
    assert "SOLAR_ORBITER" in MISSIONS
    psp = MISSIONS["PARKER_SOLAR_PROBE"]
    assert psp["name"] == "Parker Solar Probe"
    assert "FIELDS" in [inst["id"] for inst in psp["instruments"]]

    solo = MISSIONS["SOLAR_ORBITER"]
    assert solo["name"] == "Solar Orbiter"
    assert "MAG" in [inst["id"] for inst in solo["instruments"]]

    res = client.get("/api/missions")
    assert res.status_code == 200
    data = res.json()
    names = [m["name"] for m in data]
    assert "Parker Solar Probe" in names
    assert "Solar Orbiter" in names

def test_spice_engine_initialization_and_kernels():
    from helios.core.spice_engine import get_spice_engine
    engine = get_spice_engine()
    assert engine is not None
    assert engine.is_spice_available is True
    assert "CSPICE" in engine.toolkit_version
    assert len(engine.loaded_kernels) >= 3

    # Planetary Gravitational Parameters (GM in km^3/s^2)
    mu_sun = engine.get_body_gm("10")
    mu_earth = engine.get_body_gm("399")
    assert 1.327e11 < mu_sun < 1.328e11
    assert 3.985e5 < mu_earth < 3.987e5

    # Epoch ET conversion
    et = engine.epoch_to_et("2026-09-22T08:00:00")
    assert et > 800000000.0
    iso = engine.et_to_utc(et)
    assert "2026-09-22" in iso

def test_spice_engine_spacecraft_fleet():
    from helios.core.spice_engine import get_spice_engine
    engine = get_spice_engine()

    # 1. Parker Solar Probe (PSP)
    psp = engine.get_spacecraft_state("PARKER_SOLAR_PROBE")
    assert psp["name"] == "Parker Solar Probe (PSP)"
    assert 0.04 < psp["heliocentric"]["distance_au"] < 0.75
    assert 10.0 <= psp["velocity"]["speed_kms"] <= 200.0
    assert 86.0 < psp["orbital_elements"]["orbital_period_days"] < 90.0
    assert 0.88 < psp["orbital_elements"]["eccentricity"] < 0.89

    # 2. Aditya-L1 (ISRO Sun-Earth L1 Halo)
    aditya = engine.get_spacecraft_state("ADITYA_L1")
    assert aditya["name"] == "Aditya-L1"
    assert 1400000.0 < aditya["earth_relative"]["distance_km"] < 1650000.0
    assert 220.0 < aditya["earth_relative"]["distance_re"] < 260.0
    assert 25.0 < aditya["velocity"]["speed_kms"] < 35.0

    # 3. GOES-16 (Geostationary)
    goes = engine.get_spacecraft_state("GOES_16")
    assert goes["name"] == "GOES-16"
    assert 40000.0 < goes["earth_relative"]["distance_km"] < 44000.0
    assert 3.0 < goes["velocity"]["speed_kms"] < 3.15

    # 4. Solar Orbiter (SolO)
    solo = engine.get_spacecraft_state("SOLAR_ORBITER")
    assert solo["name"] == "Solar Orbiter (SolO)"
    assert 0.25 < solo["heliocentric"]["distance_au"] < 0.95
    assert 20.0 < solo["velocity"]["speed_kms"] < 75.0
    assert 0.50 < solo["orbital_elements"]["eccentricity"] < 0.52

def test_spice_rest_api_endpoints():
    # 1. SPICE status endpoint
    res_status = client.get("/api/ephemeris/spice/status")
    assert res_status.status_code == 200
    st_data = res_status.json()
    assert st_data["spice_available"] is True
    assert "CSPICE" in st_data["toolkit_version"]
    assert st_data["kernel_count"] >= 3
    assert "naif0012.tls" in st_data["loaded_kernels"]

    # 2. SPICE fleet ephemeris endpoint
    res_eph = client.get("/api/ephemeris/spice?satellites=PARKER_SOLAR_PROBE,ADITYA_L1,SOLAR_ORBITER,DSCOVR")
    assert res_eph.status_code == 200
    eph_data = res_eph.json()
    assert eph_data["spacecraft_count"] == 4
    fleet = eph_data["fleet"]
    assert "PARKER_SOLAR_PROBE" in fleet
    assert "ADITYA_L1" in fleet
    assert fleet["ADITYA_L1"]["is_spice_verified"] is True
    assert fleet["PARKER_SOLAR_PROBE"]["velocity"]["speed_kms"] > 0

    # 3. Trajectory endpoint
    res_traj = client.get("/api/ephemeris/spice/trajectory?satellite=PARKER_SOLAR_PROBE&points=15")
    assert res_traj.status_code == 200
    traj_data = res_traj.json()
    assert traj_data["points_count"] == 15
    assert len(traj_data["trajectory"]) == 15
    assert "x_au" in traj_data["trajectory"][0]

    # 4. Upgraded orbits endpoint with SPICE telemetry
    res_orbits = client.get("/api/orbits")
    assert res_orbits.status_code == 200
    orbits_data = res_orbits.json()
    assert "orbits" in orbits_data
    orbits = orbits_data["orbits"]
    assert "ADITYA_L1" in orbits
    assert "PARKER_SOLAR_PROBE" in orbits
    assert orbits["ADITYA_L1"].get("spice_telemetry") is not None


def test_settings_are_validated_and_saved(monkeypatch, tmp_path):
    """Invalid values were stored (theme, time zone) or silently ignored (cores); nothing survived a restart."""
    import json as _json
    from helios import config
    monkeypatch.setattr(config, "SETTINGS_FILE", tmp_path / "settings.json")
    before = config.get_system_settings()
    try:
        assert client.post("/api/settings", json={"timezone": "Mars/Olympus"}).status_code == 422
        assert client.post("/api/settings", json={"theme": "neon"}).status_code == 422
        r = client.post("/api/settings", json={"processors": 10_000})
        assert r.status_code == 422 and "logical cores" in r.json()["detail"]
        assert config.get_system_settings()["timezone"] == before["timezone"]
        # "Station Local Time" in the settings dialog is stored as LOCAL (it was refused: 422)
        assert client.post("/api/settings", json={"timezone": "LOCAL"}).json()["timezone"] == "LOCAL"
        ok = client.post("/api/settings", json={"timezone": "Europe/Oslo", "theme": "solar-amber"}).json()
        assert ok["saved"] and _json.loads((tmp_path / "settings.json").read_text())["timezone"] == "Europe/Oslo"
        # A restart restores them; a hand-edited invalid entry is skipped
        (tmp_path / "settings.json").write_text(_json.dumps({"timezone": "Asia/Kolkata", "theme": "bogus"}))
        config._apply_settings(timezone="UTC", theme="mission-slate")
        config._load_saved_settings()
        assert config.ACTIVE_TIMEZONE == "Asia/Kolkata" and config.ACTIVE_THEME == "mission-slate"
    finally:
        config._apply_settings(processors=before["active_processors"], theme=before["theme"],
                               font_size=before["font_size"], timezone=before["timezone"])


def test_desktop_window_keeps_its_browser_storage():
    from pathlib import Path
    from conftest import package_dir
    src = (package_dir() / "gui" / "app.py").read_text(encoding="utf-8")
    assert "private_mode=False" in src and "storage_path=" in src


def test_bulletins_show_missing_values_as_dashes_not_none():
    from helios.core.report_generator import ScientificReportGenerator as R
    latest = {"time_tag": "2026-10-10 12:00:00", "speed": 450.0, "bz_gsm": -3.0, "density": None,
              "dynamic_pressure": None, "magnetopause_re": None, "akasofu_gw": None, "l1_travel_time_min": None}
    cls = {"g_scale": "G-- (No Kp data)", "kp": None, "kp_source": "unavailable"}
    md = R.generate_markdown_executive_summary("DSCOVR", [latest], cls, [], {})
    html = R.generate_html_bulletin("DSCOVR", [latest], cls, [], {})
    for text in (md, html):
        assert "None" not in text.replace("R0 (None)", "")
    assert "unavailable (no Kp)" in md and "Mach Number" not in md


def test_parker_and_gic_inputs_are_validated():
    from fastapi.testclient import TestClient
    from helios.api.server import app
    c = TestClient(app, base_url=LOCAL)
    assert c.get("/api/parker/spiral?speed_kms=0").status_code == 422  # used to answer a fixed 45 deg
    r = c.get("/api/gic/hazard?db_dt=100&geology=granit")
    assert r.status_code == 422 and "precambrian_shield" in r.json()["detail"]
    assert c.get("/api/gic/hazard?db_dt=-5").status_code == 422


def test_flow_pressure_is_omni_s():
    # OMNI HRO 1-min, 17 March 2015 06:00 UT: V 504.5 km/s, Np 41.57 cm^-3, Pressure 21.16 nPa
    assert SpaceWeatherPhysics.dynamic_pressure(41.57, 504.5) == pytest.approx(21.16, abs=0.01)


def test_every_mission_says_what_helios_uses_from_it():
    from fastapi.testclient import TestClient
    from helios.api.server import app
    ms = TestClient(app, base_url="http://127.0.0.1:8765").get("/api/missions").json()
    assert all(m["helios_use"] for m in ms if m.get("agency") != "User Custom Ingestion")
    assert "Simulated" in next(m for m in ms if "Aditya" in m["name"])["helios_use"]


def test_headless_example_runs():
    import subprocess
    import sys
    from conftest import source_root
    root = source_root()
    env = {**__import__("os").environ, "PYTHONPATH": str(root)}
    res = subprocess.run([sys.executable, str(root / "examples" / "headless_basics.py")], capture_output=True,
                         text=True, env=env, timeout=120)
    assert res.returncode == 0, res.stderr
    assert "magnetopause stand-off 6.10" in res.stdout and "G4 (Severe)" in res.stdout
