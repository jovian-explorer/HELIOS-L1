"""
Sampling uncertainty of statistics computed from geophysical time series.

Consecutive solar wind and geomagnetic samples are strongly correlated (hourly Dst has a
lag-1 autocorrelation near 0.99), so treating N samples as independent gives confidence
intervals that are far too narrow. Every interval here uses an effective sample size from
the lag-1 autocorrelation (AR(1) approximation):

- a mean: n_eff = n (1 - rho) / (1 + rho)  (Wilks 2011, Statistical Methods in the
  Atmospheric Sciences, 3rd ed., eq. 5.12);
- a correlation of two series: n_eff = n (1 - rho_x rho_y) / (1 + rho_x rho_y)
  (Bretherton et al. 1999, J. Climate 12, 1990, eq. 31; as in xskillscore's
  effective_sample_size), with the Fisher z interval tanh(atanh r +- 1.96 / sqrt(n_eff - 3)).
Means use Student's t with n_eff - 1 degrees of freedom.

The AR(1) estimate of n_eff is itself uncertain in short, persistent series. Simulated AR(1)
errors (n = 300, 1500-2000 trials each) give coverages of the 95 % intervals of 95/94/94 %
(r), 96/94/92 % (bias) and 96/93/90 % (RMSE) for lag-1 autocorrelations 0, 0.5 and 0.9,
but only about 60-85 % when n_eff falls below about 10, which is flagged.
"""

import math
from typing import Any, Dict, Optional, Sequence, Tuple

import numpy as np

Z95 = 1.959963984540054  # two-sided 95 % point of the standard normal distribution
FEW_INDEPENDENT = 10.0  # below this n_eff the intervals are likely too narrow


def lag1_autocorrelation(x: Sequence[float]) -> float:
    """Sample lag-1 autocorrelation of a series (0 for fewer than 3 values or a constant series)."""
    a = np.asarray(x, dtype=float)
    if len(a) < 3:
        return 0.0
    d = a - a.mean()
    den = float(np.dot(d, d))
    return float(np.dot(d[:-1], d[1:]) / den) if den > 0 else 0.0


def effective_sample_size(x: Sequence[float], y: Optional[Sequence[float]] = None) -> float:
    """
    Effective number of independent samples of one series (for its mean) or of a pair (for
    their correlation). Negative autocorrelations are taken as zero, so n_eff never exceeds n.
    """
    n = len(x)
    rx = max(0.0, lag1_autocorrelation(x))
    rr = rx * max(0.0, lag1_autocorrelation(y)) if y is not None else rx
    if rr >= 1.0:
        return 1.0
    return float(min(n, n * (1.0 - rr) / (1.0 + rr)))


def fisher_interval(r: float, n_eff: float, z: float = Z95) -> Optional[Tuple[float, float]]:
    """Confidence interval of a Pearson r from the Fisher z transform; None if n_eff <= 3."""
    if r is None or not np.isfinite(r) or n_eff <= 3:
        return None
    zr = math.atanh(max(-0.999999, min(0.999999, r)))
    half = z / math.sqrt(n_eff - 3.0)
    return math.tanh(zr - half), math.tanh(zr + half)


def student_t95(dof: float) -> float:
    """
    Two-sided 95 % point of Student's t (Cornish-Fisher expansion, Abramowitz & Stegun 26.7.5;
    within 0.1 % of the exact value for dof >= 3 and 0.8 % at dof = 2).
    """
    z = Z95
    g1 = (z ** 3 + z) / 4.0
    g2 = (5 * z ** 5 + 16 * z ** 3 + 3 * z) / 96.0
    g3 = (3 * z ** 7 + 19 * z ** 5 + 17 * z ** 3 - 15 * z) / 384.0
    g4 = (79 * z ** 9 + 776 * z ** 7 + 1482 * z ** 5 - 1920 * z ** 3 - 945 * z) / 92160.0
    return z + g1 / dof + g2 / dof ** 2 + g3 / dof ** 3 + g4 / dof ** 4


def mean_interval(values: Sequence[float]) -> Dict[str, Any]:
    """
    Mean with its interval mean +- t s / sqrt(n_eff), t the 95 % point of Student's t with
    n_eff - 1 degrees of freedom; no interval if n_eff < 3.
    """
    a = np.asarray(values, dtype=float)
    a = a[np.isfinite(a)]
    if len(a) == 0:
        return {"n": 0, "n_eff": 0.0, "mean": None, "ci95": None}
    n_eff = effective_sample_size(a)
    m = float(a.mean())
    if len(a) < 3 or n_eff < 3:
        return {"n": len(a), "n_eff": n_eff, "mean": m, "ci95": None}
    half = student_t95(n_eff - 1.0) * float(a.std(ddof=1)) / math.sqrt(n_eff)
    return {"n": len(a), "n_eff": n_eff, "mean": m, "ci95": (m - half, m + half)}


def correlation(x: Sequence[float], y: Sequence[float]) -> Dict[str, Any]:
    """Pearson r of paired, time-ordered samples with its 95 % interval (Fisher z, Bretherton n_eff)."""
    a, b = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    ok = np.isfinite(a) & np.isfinite(b)
    a, b = a[ok], b[ok]
    n = len(a)
    if n < 3 or a.std() == 0 or b.std() == 0:
        return {"n": n, "r": None, "n_eff": None, "ci95": None}
    r = float(np.corrcoef(a, b)[0, 1])
    n_eff = effective_sample_size(a, b)
    return {"n": n, "r": r, "n_eff": n_eff, "ci95": fisher_interval(r, n_eff)}


def skill_scores(predicted: Sequence[float], observed: Sequence[float]) -> Dict[str, Any]:
    """
    Model-vs-observation scores of time-ordered pairs with 95 % intervals: Pearson r (Fisher z,
    Bretherton n_eff), mean bias (predicted - observed; interval from the n_eff of the error
    series) and RMSE (the square root of the interval of the mean squared error, from the n_eff
    of the squared errors, on a log scale because squared errors are skewed).
    """
    p, o = np.asarray(predicted, dtype=float), np.asarray(observed, dtype=float)
    ok = np.isfinite(p) & np.isfinite(o)
    p, o = p[ok], o[ok]
    err = p - o
    corr = correlation(p, o)
    bias = mean_interval(err)
    mse = mean_interval(err ** 2)
    rmse_ci = None
    if mse["ci95"] is not None and mse["mean"] > 0:
        rel = (mse["ci95"][1] - mse["mean"]) / mse["mean"]  # t s / (sqrt(n_eff) mean)
        rmse_ci = (math.sqrt(mse["mean"] * math.exp(-rel)), math.sqrt(mse["mean"] * math.exp(rel)))
    n_effs = [v for v in (corr["n_eff"], bias["n_eff"], mse["n_eff"]) if v is not None]
    return {
        "n": len(p),
        "r": corr["r"], "r_ci95": corr["ci95"], "n_eff_r": corr["n_eff"],
        "bias": bias["mean"], "bias_ci95": bias["ci95"], "n_eff_bias": bias["n_eff"],
        "rmse": math.sqrt(mse["mean"]) if mse["mean"] is not None else None, "rmse_ci95": rmse_ci,
        "few_independent_samples": bool(n_effs) and min(n_effs) < FEW_INDEPENDENT,
    }
