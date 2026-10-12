

def test_bulletins_give_the_reading_time_and_the_oval_driver():
    from helios.core.aurora_model import AuroralModel
    from helios.core.report_generator import ScientificReportGenerator as R
    rows = [{"time_tag": "2026-10-12 08:15:00", "speed": 450.0, "bz_gsm": -3.0}]
    aur = AuroralModel.calculate_auroral_boundaries(3.0, -3.0)
    for text in (R.generate_html_bulletin("DSCOVR", rows, {}, [], aur), R.generate_markdown_executive_summary("DSCOVR", rows, {}, [], aur)):
        assert "2026-10-12 08:15:00 UTC" in text and aur["al_source"] in text
        assert "Sighting" not in text and "License" not in text
    assert "unavailable (no Kp)" in R.generate_html_bulletin("DSCOVR", rows, {}, [], {})
