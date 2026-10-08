"""Data coverage and gap reporting (helios/core/coverage.py)."""
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

from helios.core import coverage as cv

T0 = datetime(2019, 6, 27, tzinfo=timezone.utc)


def test_gap_report_lists_leading_inner_and_trailing_gaps():
    minutes = list(range(5, 30)) + list(range(50, 100))  # data 00:05-00:29 and 00:50-01:39
    times = [T0 + timedelta(minutes=m) for m in minutes]
    r = cv.gap_report(times, T0, T0 + timedelta(hours=2), threshold_s=600, nominal_s=60)
    assert r["samples"] == 75 and r["expected_samples"] == 120 and r["sample_fraction"] == 0.625
    assert [(g["start"][11:16], g["end"][11:16], g["minutes"]) for g in r["gap_list"]] == [
        ("00:30", "00:50", 20.0), ("01:40", "02:00", 20.0)]  # the 5 min at the start are below 10 min
    assert r["longest_gap"]["minutes"] == 20.0 and r["covered_fraction"] == round(1 - 40 / 120, 4)
    assert r["first_sample"] == "2019-06-27 00:05:00" and r["last_sample"] == "2019-06-27 01:39:00"
    empty = cv.gap_report([], T0, T0 + timedelta(hours=1), 600, 60)
    assert empty["covered_fraction"] == 0.0 and empty["gaps"] == 1 and empty["first_sample"] is None


def test_records_coverage_per_group():
    recs = []
    for m in range(60):
        t = (T0 + timedelta(minutes=m)).strftime("%Y-%m-%d %H:%M:%S")
        recs.append({"time_tag": t, "bt": 5.0, "bz_gsm": -1.0,
                     "speed": None if 20 <= m < 45 else 400.0, "density": None if 20 <= m < 45 else 5.0})
    c = cv.records_coverage(recs, T0, T0 + timedelta(hours=1), 1)
    assert set(c["groups"]) == {"magnetic field", "plasma"}  # no SYM-H outside OMNI
    assert c["groups"]["magnetic field"]["covered_fraction"] == 1.0
    p = c["groups"]["plasma"]
    assert p["gaps"] == 1 and p["longest_gap"]["minutes"] == 25.0 and p["samples"] == 35
    assert cv.describe(p).startswith("58.3 % covered, 1 gap(s), longest 25 min from 2019-06-27 00:20:00")


def test_frame_coverage_uses_the_native_cadence():
    """WIND MFI 3-s on 17 March 2015: fill values from 03:55:10.5 to 03:56:37.5 in the
    HAPI stream (WI_H0_MFI@1) are a 1.5-minute gap; the report finds it at that cadence."""
    t = pd.date_range("2015-03-17 03:50:01.5", "2015-03-17 04:00:00", freq="3s", tz="UTC")
    b = np.ones((len(t), 3))
    bad = (t >= pd.Timestamp("2015-03-17 03:55:10.5", tz="UTC")) & (t <= pd.Timestamp("2015-03-17 03:56:37.5", tz="UTC"))
    b[bad] = np.nan
    frame = pd.DataFrame(b, index=t, columns=["bx", "by", "bz"])
    r = cv.frame_coverage(frame, datetime(2015, 3, 17, 3, 50, tzinfo=timezone.utc), datetime(2015, 3, 17, 4, 0, tzinfo=timezone.utc))
    assert r["nominal_cadence_s"] == 3.0 and r["gaps"] == 1
    assert r["longest_gap"]["start"] == "2015-03-17 03:55:10" and r["longest_gap"]["end"] == "2015-03-17 03:56:40"
    assert r["longest_gap"]["minutes"] == 1.5


def test_a_short_gap_is_not_rounded_away():
    # A 10-min gap in 29 days of 1-min data (WIND MFI, November 1997) is 99.98 % coverage,
    # which was shown as "100.0 % covered, 1 gap(s)".
    t1 = T0 + timedelta(days=29)
    times = [T0 + timedelta(minutes=m) for m in range(29 * 1440) if not 100 <= m < 110]
    r = cv.gap_report(times, T0, t1, threshold_s=300, nominal_s=60)
    assert r["gaps"] == 1 and r["covered_fraction"] == 0.9998
    assert cv.describe(r).startswith("> 99.9 % covered, 1 gap(s), longest 10 min")
    full = cv.gap_report([T0 + timedelta(minutes=m) for m in range(60)], T0, T0 + timedelta(hours=1), 300, 60)
    assert cv.describe(full) == "100.0 % covered"
