"""
Expanded Test Suite for HELIOS-L1 Scientific and Telemetry Engines.
"""
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

client = TestClient(app)

def test_space_weather_physics_equations():
    # 1. Dynamic pressure
    pdyn = SpaceWeatherPhysics.dynamic_pressure(5.0, 400.0)
    assert 1.3 < pdyn < 1.4

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
    assert res["equatorward_midnight_lat"] < 52.0
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
    assert "Rankine-Hugoniot" in md

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
    for r in refs:
        assert "doi" in r
        assert "doi_url" in r
        assert r["doi_url"].startswith("https://doi.org/")

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
    nom_mp = SpaceWeatherPhysics.chao_magnetopause(2.0, 0.0)
    assert 9.5 <= nom_mp["standoff_r0_re"] <= 12.0
    assert nom_mp["inside_geo"] is False
    assert nom_mp["standoff_km"] == round(nom_mp["standoff_r0_re"] * 6371.0, 1)
    assert 0.45 <= nom_mp["flaring_alpha"] <= 0.70

    nom_bs = SpaceWeatherPhysics.chao_bow_shock(2.0, 0.0, mach_number=8.0)
    assert nom_bs["standoff_r0_re"] > nom_mp["standoff_r0_re"]
    assert 12.0 <= nom_bs["standoff_r0_re"] <= 16.0
    assert 0.50 <= nom_bs["flaring_alpha"] <= 0.75

    # 2. Extreme coronal mass ejection shock compression: P = 32.0 nPa, Bz = -25.0 nT
    shock_mp = SpaceWeatherPhysics.chao_magnetopause(32.0, -25.0)
    assert shock_mp["standoff_r0_re"] < 6.6
    assert shock_mp["inside_geo"] is True

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

    # 5. Shue et al. (1997) model comparison
    shue_bounds = SpaceWeatherPhysics.calculate_magnetospheric_boundaries(2.5, -4.0, mach_number=7.5, model="shue")
    assert shue_bounds["status"] == "success"
    assert "Shue" in shue_bounds["model"]
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




