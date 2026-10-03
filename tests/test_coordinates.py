"""
GSE <-> GSM transform (Hapgood 1992 with the IGRF-14 dipole axis), checked against
GSM components published by NASA in the OMNI 1-minute data set (OMNI_HRO_1MIN, values
retrieved from CDAWeb). OMNI derives its GSM By/Bz from the GSE components, rounded to
0.01 nT, so the transform must reproduce them to that rounding.
"""
import numpy as np
import pytest

from helios.core.coordinates import (dipole_coefficients, dipole_tilt_deg, gse_gsm_angle,
                                     gse_to_gsm, gsm_to_gse)

# time, BX_GSE, BY_GSE, BZ_GSE, BY_GSM, BZ_GSM (nT), from OMNI_HRO_1MIN.
OMNI_PAIRS = [
    ("1995-06-21T06:00:00Z", -1.45, 4.94, -0.69, 4.89, -0.96),
    ("2000-07-15T15:01:00Z", 25.09, 19.74, 21.46, 24.73, 15.44),
    ("2000-07-15T15:02:00Z", 23.63, 26.42, 14.63, 29.35, 7.11),
    ("2010-03-20T00:00:00Z", -2.62, 3.34, -1.05, 3.37, 0.94),
    ("2015-12-21T18:00:00Z", 5.27, -12.35, 1.96, -12.43, 1.34),
    ("2020-09-22T03:00:00Z", 1.68, -6.95, 1.29, -6.13, 3.52),
    ("2024-05-10T17:04:00Z", 9.01, 0.24, -16.35, 4.78, -15.64),
    ("2026-03-01T09:01:00Z", -0.14, 0.78, 3.33, -0.06, 3.42),
]


def test_gse_to_gsm_reproduces_omni_published_values():
    t = [p[0] for p in OMNI_PAIRS]
    v = np.array([p[1:] for p in OMNI_PAIRS])
    x, y, z = gse_to_gsm(t, v[:, 0], v[:, 1], v[:, 2])
    np.testing.assert_allclose(x, v[:, 0])
    np.testing.assert_allclose(y, v[:, 3], atol=0.011)
    np.testing.assert_allclose(z, v[:, 4], atol=0.011)


def test_round_trip_and_magnitude_preserved():
    t = ["2003-10-29 06:00:00", "2017-09-08 00:00:00"]
    x, y, z = gse_to_gsm(t, [1.0, -3.0], [-20.0, 5.0], [35.0, -12.0])
    np.testing.assert_allclose(np.hypot(y, z), np.hypot([-20.0, 5.0], [35.0, -12.0]))
    bx, by, bz = gsm_to_gse(t, x, y, z)
    np.testing.assert_allclose(by, [-20.0, 5.0])
    np.testing.assert_allclose(bz, [35.0, -12.0])


def test_nan_components_stay_nan():
    _, y, z = gse_to_gsm(["2024-01-01T00:00:00"], [np.nan], [1.0], [np.nan])
    assert np.isnan(y[0]) and np.isnan(z[0])


def test_igrf_dipole_coefficients_and_tilt_range():
    # IGRF-14: 2020 DGRF values, and 2025 + 2 years of secular variation.
    g10, g11, h11 = dipole_coefficients(np.array([2020.0, 2027.0]))
    np.testing.assert_allclose(g10, [-29403.41, -29350.0 + 2 * 12.6])
    np.testing.assert_allclose(h11, [4653.35, 4545.5 - 2 * 21.5])
    # Largest tilts near the solstices: ~ 23.4 deg (ecliptic) + ~10 deg (dipole offset),
    # towards the Sun around 17 UT in June and away around 05 UT in December.
    june, december = dipole_tilt_deg(["2000-06-21T17:00:00", "2000-12-21T05:00:00"])
    assert 33.0 < june < 35.0 and -35.0 < december < -33.0
    assert abs(np.degrees(gse_gsm_angle("2000-06-21T17:00:00")[0])) < 5.0


def test_importer_converts_gse_only_files_to_gsm():
    from helios.core.importer import TelemetryImporter
    text = ("time,flow_speed,proton_density,BX_GSE,BY_GSE,BZ_GSE\n"
            "2024-05-10T17:04:00Z,740,20,9.01,0.24,-16.35\n"
            "2015-12-21T18:00:00Z,450,5,5.27,-12.35,9999.99\n")
    res = TelemetryImporter.parse_csv_or_text(text, "GSE file")
    late = res["records"][-1]
    assert late["time_tag"] == "2024-05-10 17:04:00"
    assert late["bx_gsm"] == 9.01 and late["bz_gse"] == -16.35
    assert late["by_gsm"] == pytest.approx(4.78, abs=0.011)
    assert late["bz_gsm"] == pytest.approx(-15.64, abs=0.011)
    assert late["akasofu_gw"] is not None and late["magnetopause_re"] is not None
    # A fill value in one GSE component leaves both rotated components missing.
    early = res["records"][0]
    assert early["bz_gse"] is None and early["by_gsm"] is None and early["bz_gsm"] is None
    assert any("GSE to GSM" in w for w in res["warnings"])


def test_importer_prefers_gsm_columns_when_both_are_present():
    from helios.core.importer import TelemetryImporter
    text = ("time,BX_GSE,BY_GSE,BZ_GSE,BY_GSM,BZ_GSM\n"
            "2024-05-10T17:04:00Z,9.01,0.24,-16.35,4.78,-15.64\n")
    res = TelemetryImporter.parse_csv_or_text(text, "OMNI")
    r = res["records"][0]
    assert (r["bx_gsm"], r["by_gsm"], r["bz_gsm"]) == (9.01, 4.78, -15.64)
    assert not any("GSE to GSM" in w for w in res["warnings"])
