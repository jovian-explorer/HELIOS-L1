"""Sampling uncertainty of statistics (helios.core.statistics) and where it is reported."""
import math

import numpy as np
import pytest

from helios.core import statistics as st


def _ar1(rng, n, phi):
    e = rng.normal(size=n)
    x = np.empty(n)
    x[0] = e[0] / math.sqrt(1 - phi * phi)
    for i in range(1, n):
        x[i] = phi * x[i - 1] + e[i]
    return x


def test_fisher_interval_matches_reference_values():
    # scipy.stats.pearsonr(...).confidence_interval(0.95) for the same r and n (scipy 1.18).
    assert st.fisher_interval(0.491337, 50) == pytest.approx((0.246733, 0.677085), abs=2e-6)
    assert st.fisher_interval(0.603249, 400) == pytest.approx((0.536959, 0.662136), abs=2e-6)
    assert st.fisher_interval(0.5, 50) == pytest.approx((0.2575, 0.6833), abs=1e-4)
    assert st.fisher_interval(0.5, 3) is None


def test_student_t_quantile_against_tables():
    # Two-sided 95 % points of Student's t (standard tables).
    for dof, t in ((1, 12.7062), (3, 3.1824), (4, 2.7764), (10, 2.2281), (30, 2.0423), (100, 1.9840)):
        assert st.student_t95(dof) == pytest.approx(t, rel=1.5e-3)


def test_effective_sample_size_formulas():
    rng = np.random.default_rng(3)
    x, y = _ar1(rng, 20000, 0.8), _ar1(rng, 20000, 0.5)
    rx, ry = st.lag1_autocorrelation(x), st.lag1_autocorrelation(y)
    assert rx == pytest.approx(0.8, abs=0.02) and ry == pytest.approx(0.5, abs=0.02)
    assert st.effective_sample_size(x) == pytest.approx(20000 * (1 - rx) / (1 + rx))
    assert st.effective_sample_size(x, y) == pytest.approx(20000 * (1 - rx * ry) / (1 + rx * ry))
    # White noise: n_eff never exceeds n, even with a slightly negative sample autocorrelation.
    assert st.effective_sample_size(rng.normal(size=500)) <= 500


def test_interval_coverage_for_autocorrelated_errors():
    """Monte Carlo: AR(1) model and observation series with known r, bias and RMSE."""
    rng = np.random.default_rng(7)
    phi, rho, n, trials = 0.5, 0.5, 300, 300
    true_rmse = math.sqrt(2 * (1 - rho) / (1 - phi * phi) + 0.09)
    hits = {"r": 0, "bias": 0, "rmse": 0, "naive_bias": 0}
    for _ in range(trials):
        o, c = _ar1(rng, n, phi), _ar1(rng, n, phi)
        p = rho * o + math.sqrt(1 - rho * rho) * c + 0.3
        s = st.skill_scores(p, o)
        hits["r"] += s["r_ci95"][0] <= rho <= s["r_ci95"][1]
        hits["bias"] += s["bias_ci95"][0] <= 0.3 <= s["bias_ci95"][1]
        hits["rmse"] += s["rmse_ci95"][0] <= true_rmse <= s["rmse_ci95"][1]
        d = p - o
        hits["naive_bias"] += abs(d.mean() - 0.3) <= 1.96 * d.std(ddof=1) / math.sqrt(n)
    for k in ("r", "bias", "rmse"):
        assert 0.89 <= hits[k] / trials <= 0.99, (k, hits[k] / trials)
    assert hits["naive_bias"] / trials < 0.85  # treating samples as independent undercovers


def test_dst_skill_reports_intervals():
    from helios.core.aurora_model import AuroralModel
    rng = np.random.default_rng(1)
    obs = -50 + 30 * _ar1(rng, 400, 0.3)
    pred = obs + 5 + 10 * rng.normal(size=400)
    sk = AuroralModel.dst_skill(list(zip(pred, obs)))
    assert sk["r_ci95"][0] < sk["r"] < sk["r_ci95"][1]
    assert sk["bias_ci95_nt"][0] < 5 < sk["bias_ci95_nt"][1]
    assert sk["rmse_ci95_nt"][0] < sk["rmse_nt"] < sk["rmse_ci95_nt"][1]
    assert not sk["few_independent_samples"]
    # A smooth single storm is about one independent sample: flagged, no r interval.
    t = np.arange(864)
    storm = -400 * np.exp(-((t - 300) / 120.0) ** 2)
    sk = AuroralModel.dst_skill(list(zip(0.6 * storm, storm)))
    assert sk["few_independent_samples"] and sk["r_ci95"] is None


def test_cross_correlation_lag_interval():
    """Moving-block bootstrap interval of the lag: covers the true delay of noisy AR(1) signals."""
    from helios.core.comparator import SatelliteComparator
    rng = np.random.default_rng(5)
    n, hits, trials = 288, 0, 60
    for _ in range(trials):
        s = _ar1(rng, n + 40, 0.9)
        a = s[20:20 + n] + rng.normal(size=n) * s.std()
        b = s[17:17 + n] + rng.normal(size=n) * s.std()  # B sees A's signal 3 samples (15 min) later
        res = SatelliteComparator.cross_correlation_lag(a, b, max_lags=24, dt_minutes=5.0)
        hits += res["lag_ci95_minutes"][0] <= 15.0 <= res["lag_ci95_minutes"][1]
    assert hits / trials >= 0.93
    # Clean, long signal: the peak never moves.
    s = _ar1(rng, 1200, 0.8)
    res = SatelliteComparator.cross_correlation_lag(s[20:1170], s[17:1167], max_lags=24, dt_minutes=5.0)
    assert res["optimal_lag_minutes"] == 15.0 and res["lag_ci95_minutes"] == [15.0, 15.0]


def test_comparator_correlation_interval():
    from helios.core.comparator import SatelliteComparator
    rng = np.random.default_rng(2)
    a = _ar1(rng, 500, 0.7)
    m = SatelliteComparator.compute_metrics(a + 0.5 * rng.normal(size=500), a)
    lo, hi = m["correlation_ci95"]
    assert lo < m["correlation_r"] < hi and m["n_eff"] < 500


def test_lag_keeps_gaps_on_the_time_grid():
    """Rows dropped for gaps used to be packed together, so a shift of k samples spanned the gaps."""
    import pandas as pd
    from helios.core.comparator import SatelliteComparator
    rng = np.random.default_rng(4)
    n = 600
    x = np.convolve(rng.normal(size=n + 50), np.ones(6) / 6, "same")
    t = pd.date_range("2024-05-10", periods=n, freq="5min", tz="UTC")
    keep = np.ones(n, bool)
    for g in range(20, n - 20, 15):
        keep[g:g + 5] = False  # 25-minute gaps every 75 minutes
    a = [{"time_tag": str(tt), "bz_gsm": float(v)} for tt, v, k in zip(t, x[10:10 + n], keep) if k]
    b = [{"time_tag": str(tt), "bz_gsm": float(v)} for tt, v, k in zip(t, x[7:7 + n], keep) if k]  # 15 min later
    lag = SatelliteComparator.compare_satellites(a, b, "A", "B", position_unknown="test")["lag_analysis"]
    assert lag["optimal_lag_minutes"] == 15.0 and lag["max_correlation"] > 0.99
    assert lag["lag_ci95_minutes"] == [15.0, 15.0]


def test_fleet_matrix_has_no_correlation_without_common_data():
    from helios.core.comparator import SatelliteComparator
    a = [{"time_tag": f"2024-05-10 12:{m:02d}:00", "bz_gsm": float(m % 7)} for m in range(60)]
    b = [{"time_tag": f"2024-05-11 12:{m:02d}:00", "bz_gsm": float(m % 5)} for m in range(60)]  # another day
    flat = [{"time_tag": f"2024-05-10 12:{m:02d}:00", "bz_gsm": 2.0} for m in range(60)]
    m = SatelliteComparator.compute_fleet_matrix({"A": a, "B": b, "C": flat})
    assert m["matrix_r"][0][1] is None  # was 0.000, read as "measured to disagree"
    assert m["matrix_r"][0][2] is None  # a constant series has no correlation


def test_fleet_matrix_finds_the_lag_between_spacecraft():
    """B sees the wind 15 min after A: r at that lag, not the lower zero-lag r."""
    import numpy as np
    from helios.core.comparator import SatelliteComparator
    rng = np.random.default_rng(3)
    x = np.cumsum(rng.normal(size=400))
    t0 = np.datetime64("2026-10-13T00:00")
    a = [{"time_tag": str(t0 + np.timedelta64(5 * k, "m")), "bz_gsm": float(x[k + 3])} for k in range(300)]
    b = [{"time_tag": str(t0 + np.timedelta64(5 * k, "m")), "bz_gsm": float(x[k])} for k in range(300)]
    m = SatelliteComparator.compute_fleet_matrix({"A": a, "B": b})
    assert m["matrix_lag_min"][0][1] == 15.0 and m["matrix_lag_min"][1][0] == -15.0
    assert m["matrix_r"][0][1] > 0.99
