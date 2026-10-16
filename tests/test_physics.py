

def test_bulletins_give_the_reading_time_and_the_oval_driver():
    from helios.core.aurora_model import AuroralModel
    from helios.core.report_generator import ScientificReportGenerator as R
    rows = [{"time_tag": "2026-10-12 08:15:00", "speed": 450.0, "bz_gsm": -3.0}]
    aur = AuroralModel.calculate_auroral_boundaries(3.0, -3.0)
    for text in (R.generate_html_bulletin("DSCOVR", rows, {}, [], aur), R.generate_markdown_executive_summary("DSCOVR", rows, {}, [], aur)):
        assert "2026-10-12 08:15:00 UTC" in text and aur["al_source"] in text
        assert "Sighting" not in text and "License" not in text
    assert "Equatorward boundary at magnetic midnight (Starkov 1994, corrected geomagnetic latitude): <strong>---°" in R.generate_html_bulletin("DSCOVR", rows, {}, [], {})


def test_hazards_follow_the_noaa_g_scale():
    from helios.core.ml_forecast import SpaceWeatherForecaster as F
    g1, g4 = F.assess_hazards(450, -12, None, 5.0), F.assess_hazards(450, 5, None, 8.0)
    assert g1["power_grid_gic"]["risk_level"] == "MINOR (G1)" and "Weak power grid fluctuations" in g1["power_grid_gic"]["advisory"]
    assert g1["aviation_hf"]["risk_level"] == "MINOR (G1)"  # southward Bz alone no longer raises it
    assert g4["satellite_ops"]["risk_level"] == "SEVERE (G4)" and "tracking" in g4["satellite_ops"]["advisory"]
    assert F.assess_hazards(400, 0, None, 2.0)["power_grid_gic"]["risk_level"] == "NONE (G0)"


def test_earth_connected_parker_line_passes_through_earth():
    from helios.core.parker_spiral import ParkerSpiralModel as P
    for v in (300.0, 450.0, 2000.0):
        line = P.generate_parker_spiral_lines(v, num_points=121)[0]
        assert line["is_earth_connected"]
        p = min(line["points"], key=lambda q: abs(q["r_au"] - 1.0))
        assert abs(p["r_au"] - 1.0) < 0.01 and abs(p["y_au"]) < 0.01 and p["x_au"] > 0.99


def test_scales_of_10_11_may_2024_from_archived_goes_and_gfz_values():
    """NOAA reported G5, S2 and R3 for 10-11 May 2024: GFZ Kp 9.0 (11 May 00-03 UT), GOES-16
    X5.8 (5.82e-4 W/m^2, 11 May 01:23 UT) and about 225 pfu above 10 MeV (10 May 17:45 UT)."""
    from helios.core.ionosphere import IonosphericModel as I
    from helios.core.science import SpaceWeatherPhysics as S
    c = S.classify_noaa_scales(9.0, None, 5.82e-4, 225.0)
    assert (c["g_level"], c["s_level"], c["r_level"]) == (5, 2, 3) and c["flare_class"].startswith("X5.8")
    assert I.calculate_drap_absorption(5.82e-4)["r_scale"].startswith("R3")
    assert [S.noaa_r_level(f) for f in (9.9e-6, 1e-5, 5e-5, 1e-4, 1e-3, 2e-3)] == [0, 1, 2, 3, 4, 5]


def test_fleet_matrix_leaves_a_spacecraft_without_the_parameter_empty():
    from helios.core.comparator import SatelliteComparator as C
    rows = [{"time_tag": f"2026-10-13 00:{m:02d}:00", "bz_gsm": float(m % 7), "speed": 400.0 + m} for m in range(60)]
    no_b = [{"time_tag": r["time_tag"], "bz_gsm": None, "speed": r["speed"]} for r in rows]
    res = C.compute_fleet_matrix({"A": rows, "B": rows, "SOHO": no_b}, parameter="bz_gsm")
    assert res["matrix_r"][0][0] == 1.0 and res["matrix_r"][2][2] is None and res["matrix_r"][0][2] is None


def test_comparison_of_far_apart_spacecraft_says_the_lag_search_cannot_reach():
    from helios.core.comparator import SatelliteComparator as C
    rows = [{"time_tag": f"2026-10-13 {h:02d}:{m:02d}:00", "speed": 400.0 + (h * 60 + m) % 37} for h in range(12) for m in range(0, 60, 5)]
    near = {"x_km": 1.5e6, "y_km": 0.0, "z_km": 0.0, "source": "test"}
    far = {"x_km": -1.0e8, "y_km": 1.36e8, "z_km": 0.0, "source": "test"}  # like STEREO-A, 70 deg ahead
    res = C.compare_satellites(rows, rows, "A", "B", "speed", position_a=near, position_b=far)
    assert "outside the lag search" in res["spatial_baseline"]["note"]
