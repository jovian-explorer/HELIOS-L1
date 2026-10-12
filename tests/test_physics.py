

def test_bulletins_give_the_reading_time_and_the_oval_driver():
    from helios.core.aurora_model import AuroralModel
    from helios.core.report_generator import ScientificReportGenerator as R
    rows = [{"time_tag": "2026-10-12 08:15:00", "speed": 450.0, "bz_gsm": -3.0}]
    aur = AuroralModel.calculate_auroral_boundaries(3.0, -3.0)
    for text in (R.generate_html_bulletin("DSCOVR", rows, {}, [], aur), R.generate_markdown_executive_summary("DSCOVR", rows, {}, [], aur)):
        assert "2026-10-12 08:15:00 UTC" in text and aur["al_source"] in text
        assert "Sighting" not in text and "License" not in text
    assert "unavailable (no Kp)" in R.generate_html_bulletin("DSCOVR", rows, {}, [], {})


def test_hazards_follow_the_noaa_g_scale():
    from helios.core.ml_forecast import SpaceWeatherForecaster as F
    g1, g4 = F.assess_hazards(450, -12, None, 5.0), F.assess_hazards(450, 5, None, 8.0)
    assert g1["power_grid_gic"]["risk_level"] == "MINOR (G1)" and "Weak power grid fluctuations" in g1["power_grid_gic"]["advisory"]
    assert g1["aviation_hf"]["risk_level"] == "MINOR (G1)"  # southward Bz alone no longer raises it
    assert g4["satellite_ops"]["risk_level"] == "SEVERE (G4)" and "tracking" in g4["satellite_ops"]["advisory"]
    assert F.assess_hazards(400, 0, None, 2.0)["power_grid_gic"]["risk_level"] == "NONE (G0)"
