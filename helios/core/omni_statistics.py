"""
Statistics of the hourly OMNI data set (OMNI2_H0_MRG1HR, 1963 to the present) with
regime and quality filters.

* Data: NASA OMNIWeb hourly merged solar wind (field and plasma time-shifted to the bow
  shock nose), WDC Kyoto Dst, AE, AL, AU, Kp, sunspot number and F10.7, one HAPI request
  per year, cached; years more than two years old are re-checked twice a year, because
  OMNI revises older years now and then.
* Derived per hour: Newell dPhi/dt, V Bs, IMF clock angle, Alfven speed, proton specific
  entropy, the expected-temperature ratio and the solar wind type of Xu & Borovsky (2015).
* Filters (each recorded, with the number of hours it kept, in every answer): value
  ranges of any quantity, southward or northward IMF lasting at least N hours, solar wind
  type, minimum numbers of fine-scale field and plasma points in the hour (data quality
  and coverage), and Dst thresholds (storm or quiet time).
* Analyses: distributions, joint histograms, conditional averages (y binned in x),
  correlations, and yearly or monthly statistics against the sunspot number. Intervals
  allow for autocorrelation (helios.core.statistics), using only consecutive hours that
  both passed the filters to estimate the lag-1 autocorrelation.

The 95 % intervals and every filter are part of the answer and of its CSV export.
"""
import hashlib
import math
import os
import re
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

from helios.core.archive import HapiError, hapi_data_url, parse_hapi_csv
from helios.core.statistics import fisher_interval, student_t95
from helios.core.cache import cached_text

OMNI_HOURLY_ID = "OMNI2_H0_MRG1HR"
FIRST_YEAR = 1963
MAX_YEARS = 64
RECENT_TTL_SECONDS = 86400
OLD_TTL_SECONDS = 180 * 86400
EV_PER_K = 1.0 / 11604.518

# HAPI parameters in dataset order (HAPI answers in dataset order), HELIOS names, units.
OMNI_HOURLY_PARAMETERS: List[Tuple[str, str, str, str]] = [
    ("IMF_PTS1800", "imf_points", "Fine-scale field points in the hour", ""),
    ("PLS_PTS1800", "plasma_points", "Fine-scale plasma points in the hour", ""),
    ("ABS_B1800", "b", "Field magnitude |B| (hourly mean of |B|)", "nT"),
    ("BY_GSM1800", "by_gsm", "IMF By GSM", "nT"),
    ("BZ_GSM1800", "bz_gsm", "IMF Bz GSM", "nT"),
    ("T1800", "temperature", "Proton temperature", "K"),
    ("N1800", "density", "Proton density", "cm^-3"),
    ("V1800", "speed", "Flow speed", "km/s"),
    ("Pressure1800", "pressure", "Flow pressure", "nPa"),
    ("E1800", "e_field", "Electric field -V Bz", "mV/m"),
    ("Beta1800", "beta", "Plasma beta", ""),
    ("Mach_num1800", "alfven_mach", "Alfven Mach number", ""),
    ("Mgs_mach_num1800", "ms_mach", "Magnetosonic Mach number", ""),
    ("R1800", "sunspot_number", "Sunspot number (version 2)", ""),
    ("F10_INDEX1800", "f107", "F10.7 index", "sfu"),
    ("KP1800", "kp", "Kp (OMNI coding /10, e.g. 3+ = 3.3)", ""),
    ("DST1800", "dst", "Dst (WDC Kyoto)", "nT"),
    ("AE1800", "ae", "AE (WDC Kyoto)", "nT"),
    ("AL_INDEX1800", "al", "AL (WDC Kyoto)", "nT"),
    ("AU_INDEX1800", "au", "AU (WDC Kyoto)", "nT"),
]

DERIVED_QUANTITIES: Dict[str, Tuple[str, str]] = {
    "newell": ("Newell dPhi/dt = V^4/3 B_T^2/3 sin^8/3(theta/2)", "(km/s)^4/3 nT^2/3"),
    "vbs": ("V Bs, Bs = max(0, -Bz GSM)", "mV/m"),
    "clock_angle": ("IMF clock angle atan2(By, Bz) GSM, 0-180", "deg"),
    "alfven_speed": ("Alfven speed 21.81 B / sqrt(n)", "km/s"),
    "specific_entropy": ("Proton specific entropy T / n^2/3", "eV cm^2"),
    "texp_ratio": ("Texp / T, Texp = (V / 258)^3.113 eV", ""),
    "sw_type": ("Xu & Borovsky (2015) type: 1 ejecta, 2 coronal hole, 3 sector reversal, 4 streamer belt", ""),
}

QUANTITIES: Dict[str, Dict[str, str]] = {
    name: {"label": label, "units": units} for _, name, label, units in OMNI_HOURLY_PARAMETERS
}
QUANTITIES.update({k: {"label": v[0], "units": v[1]} for k, v in DERIVED_QUANTITIES.items()})

SW_TYPES = {1: "ejecta", 2: "coronal_hole", 3: "sector_reversal", 4: "streamer_belt"}


# ----------------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------------
class OmniHourlyClient:
    """Hourly OMNI by calendar year from CDAWeb HAPI; `fetch_text(url)` returns the body or None."""

    def __init__(self, fetch_text: Callable, cache_dir: str):
        self.fetch_text = fetch_text
        self.cache_dir = os.path.join(str(cache_dir), "omni_hourly")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.parameters = [p for p, _, _, _ in OMNI_HOURLY_PARAMETERS]
        self._key = hashlib.sha1(",".join(self.parameters).encode()).hexdigest()[:10]

    def url(self, year: int) -> str:
        return hapi_data_url(OMNI_HOURLY_ID, self.parameters, datetime(year, 1, 1, tzinfo=timezone.utc),
                             datetime(year + 1, 1, 1, tzinfo=timezone.utc))

    async def year(self, year: int) -> Tuple[Optional[pd.DataFrame], bool]:
        """(frame of one year or None, served from cache without reaching the server)."""
        path = os.path.join(self.cache_dir, f"{year}_{self._key}.csv.gz")
        now = datetime.now(timezone.utc)
        ttl = OLD_TTL_SECONDS if year < now.year - 1 else RECENT_TTL_SECONDS
        text, offline = await cached_text(path, self.url(year), self.fetch_text, ttl, gz=True)
        if text is None:
            return None, offline
        try:
            df = parse_hapi_csv(text)
        except (HapiError, ValueError):
            return None, offline
        return (decode(df) if not df.empty else None), offline


def decode(df: pd.DataFrame) -> pd.DataFrame:
    """HAPI columns to HELIOS names, time stamps moved to the start of each hourly average."""
    out = pd.DataFrame({name: df[p] for p, name, _, _ in OMNI_HOURLY_PARAMETERS if p in df}, index=df.index)
    # HAPI stamps OMNI hourly values at the middle of the hour (hh:30).
    out.index = out.index.floor("h")
    out = out[~out.index.duplicated()]
    if "kp" in out:
        out["kp"] = out["kp"] / 10.0
    return add_derived(out)


def xb15_type(speed, density, temperature_k, b_nt) -> np.ndarray:
    """
    Solar wind type of Xu & Borovsky (2015, J. Geophys. Res. 120, 70), from their three
    separating planes in (log10 Sp, log10 vA, log10 Texp/T):
      ejecta           log vA > 0.277 log Sp + 0.055 log(Texp/T) + 1.83
      coronal hole     log Sp > -0.525 log(Texp/T) - 0.676 log vA + 1.74
      sector reversal  log Sp < -0.125 log(Texp/T) - 0.658 log vA + 1.04
      streamer belt    otherwise,
    checked in this order, with Sp = T/n^2/3 [eV cm^2], vA [km/s] and Texp = (V/258)^3.113
    [eV]. The planes are those of the FDL 2025 Heliolab code (point-normal form) and match
    the coefficients quoted in the literature. 0 where an input is missing.
    """
    v, n, t, b = (np.asarray(x, dtype=float) for x in (speed, density, temperature_k, b_nt))
    with np.errstate(divide="ignore", invalid="ignore"):
        t_ev = t * EV_PER_K
        x = np.log10(t_ev / n ** (2.0 / 3.0))
        y = np.log10(21.81 * b / np.sqrt(n))
        z = np.log10((v / 258.0) ** 3.113 / t_ev)
        ok = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
        g3 = -3.88 * (x + 1.5) + 14.0 * (y - 1.52) - 0.77 * (z - 2.0)   # > 0: ejecta
        g1 = 5.92 * (x - 1.1) + 4.0 * (y - 2.5) + 3.108 * (z + 2.0)     # > 0: coronal hole
        g2 = 6.08 * (x + 0.3) + 4.0 * (y - 2.41) + 0.76 * (z + 2.0)     # < 0: sector reversal
    out = np.where(g3 > 0, 1, np.where(g1 > 0, 2, np.where(g2 < 0, 3, 4)))
    return np.where(ok, out, 0).astype(int)


def add_derived(df: pd.DataFrame) -> pd.DataFrame:
    by, bz, v = df.get("by_gsm"), df.get("bz_gsm"), df.get("speed")
    if by is not None and bz is not None and v is not None:
        theta = np.arctan2(np.abs(by), bz)
        df["clock_angle"] = np.degrees(theta)
        df["newell"] = v ** (4.0 / 3.0) * np.hypot(by, bz) ** (2.0 / 3.0) * np.sin(theta / 2.0) ** (8.0 / 3.0)
        df["vbs"] = v * np.maximum(0.0, -bz) * 1e-3
    if {"b", "density", "temperature", "speed"} <= set(df.columns):
        with np.errstate(divide="ignore", invalid="ignore"):
            df["alfven_speed"] = 21.81 * df["b"] / np.sqrt(df["density"])
            df["specific_entropy"] = df["temperature"] * EV_PER_K / df["density"] ** (2.0 / 3.0)
            df["texp_ratio"] = (df["speed"] / 258.0) ** 3.113 / (df["temperature"] * EV_PER_K)
        t = xb15_type(df["speed"], df["density"], df["temperature"], df["b"])
        df["sw_type"] = np.where(t > 0, t, np.nan)
    return df


# ----------------------------------------------------------------------------
# Filters
# ----------------------------------------------------------------------------
_CONDITION = re.compile(r"^\s*([a-z_0-9]+)\s*(<=|>=|<|>)\s*(-?\d+(?:\.\d+)?(?:e-?\d+)?)\s*$", re.I)
_OPS = {"<": np.less, "<=": np.less_equal, ">": np.greater, ">=": np.greater_equal}


def parse_conditions(where: str) -> List[Tuple[str, str, float]]:
    """'speed>500; beta<=1' -> [('speed', '>', 500.0), ('beta', '<=', 1.0)]; ValueError if malformed."""
    out = []
    for part in [p for p in re.split(r"[;,]", where or "") if p.strip()]:
        m = _CONDITION.match(part)
        if not m:
            raise ValueError(f"Cannot read the condition '{part.strip()}' (use e.g. speed>500 or beta<=1).")
        q = m.group(1).lower()
        if q not in QUANTITIES:
            raise ValueError(f"Unknown quantity '{q}' in a condition; available: {', '.join(QUANTITIES)}.")
        out.append((q, m.group(2), float(m.group(3))))
    return out


def _run_lengths(flag: np.ndarray, hourly_index: pd.DatetimeIndex) -> np.ndarray:
    """Length in hours of the run of consecutive True hours each sample belongs to (0 where False)."""
    out = np.zeros(len(flag))
    if not len(flag):
        return out
    hours = (hourly_index.as_unit("ns").asi8 // 3_600_000_000_000).astype(np.int64)
    start = 0
    for i in range(1, len(flag) + 1):
        if i == len(flag) or not flag[i] or not flag[i - 1] or hours[i] - hours[i - 1] != 1:
            if flag[start]:
                out[start:i] = i - start
            start = i
    return out


def apply_filters(df: pd.DataFrame, conditions: Sequence[Tuple[str, str, float]] = (),
                  bz_south_min_hours: int = 0, bz_north_min_hours: int = 0,
                  sw_types: Sequence[str] = (), min_imf_points: int = 0,
                  min_plasma_points: int = 0) -> Tuple[np.ndarray, List[Dict[str, Any]]]:
    """
    Boolean mask of the hours that pass every filter, and the filter log (description and
    hours remaining after each step). Hours with a missing value of a filtered quantity fail.
    """
    mask = np.ones(len(df), dtype=bool)
    log = [{"filter": "all hours in the interval", "hours_remaining": int(mask.sum())}]

    def step(desc, keep):
        nonlocal mask
        mask &= np.asarray(keep, dtype=bool)
        log.append({"filter": desc, "hours_remaining": int(mask.sum())})

    for q, op, val in conditions:
        col = df[q].to_numpy(dtype=float) if q in df else np.full(len(df), np.nan)
        with np.errstate(invalid="ignore"):
            step(f"{q} {op} {val:g}", _OPS[op](col, val) & np.isfinite(col))
    bz = df["bz_gsm"].to_numpy(dtype=float) if "bz_gsm" in df else np.full(len(df), np.nan)
    if bz_south_min_hours > 0:
        with np.errstate(invalid="ignore"):
            runs = _run_lengths(bz < 0, df.index)
        step(f"IMF Bz GSM < 0 for at least {bz_south_min_hours} consecutive hours", runs >= bz_south_min_hours)
    if bz_north_min_hours > 0:
        with np.errstate(invalid="ignore"):
            runs = _run_lengths(bz > 0, df.index)
        step(f"IMF Bz GSM > 0 for at least {bz_north_min_hours} consecutive hours", runs >= bz_north_min_hours)
    if sw_types:
        codes = [k for k, v in SW_TYPES.items() if v in sw_types]
        step(f"Xu & Borovsky (2015) solar wind type in {', '.join(sw_types)}",
             np.isin(df["sw_type"].to_numpy(dtype=float) if "sw_type" in df else np.zeros(len(df)), codes))
    if min_imf_points > 0:
        step(f"at least {min_imf_points} fine-scale field points in the hour",
             np.nan_to_num(df["imf_points"].to_numpy(dtype=float)) >= min_imf_points)
    if min_plasma_points > 0:
        step(f"at least {min_plasma_points} fine-scale plasma points in the hour",
             np.nan_to_num(df["plasma_points"].to_numpy(dtype=float)) >= min_plasma_points)
    return mask, log


# ----------------------------------------------------------------------------
# Sampling uncertainty with gaps
# ----------------------------------------------------------------------------
def _consecutive_pairs(index: pd.DatetimeIndex) -> np.ndarray:
    """True for samples i whose successor i+1 is exactly one hour later."""
    if len(index) < 2:
        return np.zeros(0, dtype=bool)
    return np.diff(index.as_unit("ns").asi8) == 3_600_000_000_000


def lag1_hourly(values: np.ndarray, index: pd.DatetimeIndex) -> Tuple[float, int]:
    """
    Lag-1 autocorrelation from the pairs of consecutive hours only (Pearson r of value and
    next value over those pairs, so that a subset of pairs from unusual periods cannot give
    rho > 1); (rho clipped to [0, 1), number of pairs).
    """
    a = np.asarray(values, dtype=float)
    pairs = _consecutive_pairs(index)
    if len(a) < 3 or pairs.sum() < 3:
        return 0.0, int(pairs.sum())
    u, v = a[:-1][pairs], a[1:][pairs]
    if u.std() == 0 or v.std() == 0:
        return 0.0, int(pairs.sum())
    return max(0.0, min(0.999999, float(np.corrcoef(u, v)[0, 1]))), int(pairs.sum())


def mean_with_interval(values: np.ndarray, index: pd.DatetimeIndex, rho_fallback: float = 0.0,
                       min_pairs: int = 20) -> Dict[str, Any]:
    """Mean, standard deviation and 95 % interval of the mean with an AR(1) effective sample size."""
    a = np.asarray(values, dtype=float)
    n = len(a)
    if n == 0:
        return {"n": 0, "mean": None, "std": None, "n_eff": 0.0, "ci95": None}
    rho, pairs = lag1_hourly(a, index)
    if pairs < min_pairs:
        rho = max(rho, rho_fallback)
    n_eff = min(n, n * (1 - rho) / (1 + rho))
    m = float(a.mean())
    sd = float(a.std(ddof=1)) if n > 1 else 0.0
    ci = None
    if n >= 3 and n_eff >= 3:
        half = student_t95(n_eff - 1.0) * sd / math.sqrt(n_eff)
        ci = [m - half, m + half]
    return {"n": n, "mean": m, "std": sd, "n_eff": n_eff, "ci95": ci}


def correlation_hourly(x: np.ndarray, y: np.ndarray, index: pd.DatetimeIndex) -> Dict[str, Any]:
    """Pearson r with its Fisher interval; Bretherton n_eff from the consecutive-hour autocorrelations."""
    n = len(x)
    if n < 3 or np.std(x) == 0 or np.std(y) == 0:
        return {"n": n, "r": None, "n_eff": None, "ci95": None}
    r = float(np.corrcoef(x, y)[0, 1])
    rx, _ = lag1_hourly(x, index)
    ry, _ = lag1_hourly(y, index)
    n_eff = min(n, n * (1 - rx * ry) / (1 + rx * ry))
    ci = fisher_interval(r, n_eff)
    return {"n": n, "r": r, "n_eff": n_eff, "ci95": list(ci) if ci else None,
            "spearman_rho": float(pd.Series(x).rank().corr(pd.Series(y).rank()))}


# ----------------------------------------------------------------------------
# Analyses
# ----------------------------------------------------------------------------
def _edges(values: np.ndarray, bins: int, log: bool, lo: Optional[float], hi: Optional[float]) -> np.ndarray:
    v = values[np.isfinite(values)]
    if log:
        v = v[v > 0]
    if not len(v):
        raise ValueError("No valid values to bin.")
    lo = float(np.percentile(v, 0.5)) if lo is None else lo
    hi = float(np.percentile(v, 99.5)) if hi is None else hi
    if hi <= lo:
        hi = lo + 1.0
    if log:
        if lo <= 0:
            raise ValueError("A logarithmic axis needs positive limits.")
        e = np.logspace(math.log10(lo), math.log10(hi), bins + 1)
        e[0], e[-1] = lo, hi  # exact limits: values equal to them must fall inside
        return e
    return np.linspace(lo, hi, bins + 1)


def distribution(s: pd.Series, bins: int = 40, log: bool = False, lo: Optional[float] = None,
                 hi: Optional[float] = None) -> Dict[str, Any]:
    v = s.to_numpy(dtype=float)
    v = v[np.isfinite(v)]
    edges = _edges(v, bins, log, lo, hi)
    counts, _ = np.histogram(v, bins=edges)
    widths = np.diff(edges)
    q = np.percentile(v, [5, 25, 50, 75, 95])
    stats = mean_with_interval(s.dropna().to_numpy(dtype=float), s.dropna().index)
    return {
        "edges": edges.tolist(), "counts": counts.tolist(),
        "density": (counts / max(1, len(v)) / widths).tolist(),
        "n": int(len(v)), "outside_range": int(len(v) - counts.sum()),
        "mean": stats["mean"], "mean_ci95": stats["ci95"], "std": stats["std"], "n_eff": stats["n_eff"],
        "percentiles": {"p05": q[0], "p25": q[1], "median": q[2], "p75": q[3], "p95": q[4]},
    }


def joint_histogram(x: pd.Series, y: pd.Series, bins: int = 30, log_x: bool = False,
                    log_y: bool = False) -> Dict[str, Any]:
    both = pd.concat([x, y], axis=1).dropna()
    xv, yv = both.iloc[:, 0].to_numpy(float), both.iloc[:, 1].to_numpy(float)
    ex, ey = _edges(xv, bins, log_x, None, None), _edges(yv, bins, log_y, None, None)
    counts, _, _ = np.histogram2d(xv, yv, bins=[ex, ey])
    return {"x_edges": ex.tolist(), "y_edges": ey.tolist(), "counts": counts.astype(int).tolist(),
            "n": int(len(xv)), "outside_range": int(len(xv) - counts.sum()),
            "correlation": correlation_hourly(xv, yv, both.index)}


def conditional_average(x: pd.Series, y: pd.Series, bins: int = 15, log_x: bool = False,
                        lo: Optional[float] = None, hi: Optional[float] = None,
                        min_count: int = 10) -> Dict[str, Any]:
    """
    Statistics of y in bins of x: mean with its 95 % interval, median and quartiles. The
    lag-1 autocorrelation of y inside a bin comes from consecutive hours in that bin; with
    fewer than 20 such pairs that of y over all hours is used (whichever is larger).
    """
    both = pd.concat([x, y], axis=1).dropna()
    xv, yv = both.iloc[:, 0].to_numpy(float), both.iloc[:, 1].to_numpy(float)
    edges = _edges(xv, bins, log_x, lo, hi)
    rho_all, _ = lag1_hourly(yv, both.index)
    which = np.digitize(xv, edges) - 1
    which[xv == edges[-1]] = len(edges) - 2  # the last bin includes its upper edge, as in np.histogram
    out = {k: [] for k in ("x_center", "n", "mean", "mean_ci95_low", "mean_ci95_high", "median", "q25", "q75", "n_eff")}
    for i in range(len(edges) - 1):
        sel = which == i
        centre = math.sqrt(edges[i] * edges[i + 1]) if log_x else 0.5 * (edges[i] + edges[i + 1])
        out["x_center"].append(centre)
        out["n"].append(int(sel.sum()))
        if sel.sum() < min_count:
            for k in ("mean", "mean_ci95_low", "mean_ci95_high", "median", "q25", "q75", "n_eff"):
                out[k].append(None)
            continue
        st = mean_with_interval(yv[sel], both.index[sel], rho_fallback=rho_all)
        q = np.percentile(yv[sel], [25, 50, 75])
        out["mean"].append(st["mean"])
        out["mean_ci95_low"].append(st["ci95"][0] if st["ci95"] else None)
        out["mean_ci95_high"].append(st["ci95"][1] if st["ci95"] else None)
        out["median"].append(float(q[1]))
        out["q25"].append(float(q[0]))
        out["q75"].append(float(q[2]))
        out["n_eff"].append(st["n_eff"])
    out["edges"] = edges.tolist()
    out["min_count"] = min_count
    out["correlation"] = correlation_hourly(xv, yv, both.index)
    return out


def cycle_statistics(df: pd.DataFrame, mask: np.ndarray, quantity: str, resolution: str = "year",
                     min_coverage: float = 0.5) -> Dict[str, Any]:
    """
    Yearly or monthly mean, median, standard deviation and 95 % interval of a quantity (hours
    passing the filters), the data coverage of each period, the mean sunspot number of the
    same period (all hours), and the correlation of the period means with the sunspot number
    over periods with at least `min_coverage` of their hours present.
    """
    freq = "YS" if resolution == "year" else "MS"
    q = df[quantity].where(mask)
    rows = []
    for start, grp in q.groupby(pd.Grouper(freq=freq)):
        hours_total = len(df.loc[grp.index])
        v = grp.dropna()
        st = mean_with_interval(v.to_numpy(dtype=float), v.index) if len(v) else {"mean": None, "std": None,
                                                                                  "n_eff": 0.0, "ci95": None}
        ssn = df["sunspot_number"].loc[grp.index].mean() if "sunspot_number" in df else float("nan")
        rows.append({
            "period": start.strftime("%Y" if resolution == "year" else "%Y-%m"),
            "hours": int(len(v)), "coverage": len(v) / hours_total if hours_total else 0.0,
            "mean": st["mean"], "median": float(v.median()) if len(v) else None, "std": st["std"],
            "mean_ci95": st["ci95"], "n_eff": st["n_eff"],
            "sunspot_number": None if not np.isfinite(ssn) else float(ssn),
        })
    good = [r for r in rows if r["mean"] is not None and r["sunspot_number"] is not None and r["coverage"] >= min_coverage]
    corr = None
    if len(good) >= 4:
        m = np.array([r["mean"] for r in good])
        s = np.array([r["sunspot_number"] for r in good])
        if m.std() > 0 and s.std() > 0:
            r = float(np.corrcoef(m, s)[0, 1])
            # Consecutive period means are autocorrelated over the solar cycle.
            def r1(a):
                d = a - a.mean()
                return max(0.0, float(np.dot(d[:-1], d[1:]) / np.dot(d, d)))
            rr = r1(m) * r1(s)
            n_eff = min(len(good), len(good) * (1 - rr) / (1 + rr))
            ci = fisher_interval(r, n_eff)
            corr = {"r_with_sunspot_number": r, "n_periods": len(good), "n_eff": n_eff,
                    "ci95": list(ci) if ci else None}
    return {"resolution": resolution, "min_coverage": min_coverage, "periods": rows, "correlation": corr}


ANALYSES = ("distribution", "joint", "conditional", "correlation", "cycle")


def run_analysis(df: pd.DataFrame, analysis: str, x: str, y: Optional[str], filters: Dict[str, Any],
                 bins: int = 30, log_x: bool = False, log_y: bool = False, resolution: str = "year",
                 min_count: int = 10) -> Dict[str, Any]:
    """Apply the filters to the hourly frame and run one analysis; the filter log is part of the answer."""
    if analysis not in ANALYSES:
        raise ValueError(f"'analysis' must be one of {', '.join(ANALYSES)}.")
    for q in [x] + ([y] if y else []):
        if q not in QUANTITIES:
            raise ValueError(f"Unknown quantity '{q}'; available: {', '.join(QUANTITIES)}.")
    if analysis in ("joint", "conditional", "correlation") and not y:
        raise ValueError(f"The {analysis} analysis needs a second quantity 'y'.")
    mask, log = apply_filters(df, **filters)
    sel = df[mask]
    if analysis != "cycle" and len(sel) < 10:
        raise ValueError(f"Only {len(sel)} hours pass the filters; at least 10 are needed.")
    out: Dict[str, Any] = {"analysis": analysis, "x": x, "y": y, "filters": log,
                           "hours_selected": int(mask.sum()), "hours_in_interval": int(len(df))}
    if analysis == "distribution":
        out["result"] = distribution(sel[x], bins, log_x)
    elif analysis == "joint":
        out["result"] = joint_histogram(sel[x], sel[y], bins, log_x, log_y)
    elif analysis == "conditional":
        out["result"] = conditional_average(sel[x], sel[y], bins, log_x, min_count=min_count)
    elif analysis == "correlation":
        both = sel[[x, y]].dropna()
        out["result"] = correlation_hourly(both[x].to_numpy(float), both[y].to_numpy(float), both.index)
    else:
        out["result"] = cycle_statistics(df, mask, x, resolution)
    out["units"] = {q: QUANTITIES[q]["units"] for q in [x] + ([y] if y else [])}
    out["labels"] = {q: QUANTITIES[q]["label"] for q in [x] + ([y] if y else [])}
    out["method"] = ("OMNI hourly values; 95 % intervals from AR(1) effective sample sizes estimated from "
                     "consecutive selected hours (Wilks 2011 eq. 5.12; Bretherton et al. 1999 eq. 31 with Fisher z)")
    return out


def to_csv_rows(answer: Dict[str, Any]) -> Tuple[List[str], List[List[Any]]]:
    """Header and rows of the analysis table for CSV export."""
    a, r = answer["analysis"], answer["result"]
    if a == "distribution":
        e = r["edges"]
        return (["bin_low", "bin_high", "count", "density"],
                [[e[i], e[i + 1], r["counts"][i], r["density"][i]] for i in range(len(r["counts"]))])
    if a == "joint":
        ex, ey = r["x_edges"], r["y_edges"]
        return (["x_low", "x_high", "y_low", "y_high", "count"],
                [[ex[i], ex[i + 1], ey[j], ey[j + 1], r["counts"][i][j]]
                 for i in range(len(ex) - 1) for j in range(len(ey) - 1)])
    if a == "conditional":
        keys = ["x_center", "n", "mean", "mean_ci95_low", "mean_ci95_high", "median", "q25", "q75", "n_eff"]
        return keys, [[r[k][i] for k in keys] for i in range(len(r["x_center"]))]
    if a == "correlation":
        return (["n", "r", "r_ci95_low", "r_ci95_high", "n_eff", "spearman_rho"],
                [[r["n"], r["r"], *(r["ci95"] or [None, None]), r["n_eff"], r.get("spearman_rho")]])
    keys = ["period", "hours", "coverage", "mean", "median", "std", "n_eff", "sunspot_number"]
    return (keys + ["mean_ci95_low", "mean_ci95_high"],
            [[p[k] for k in keys] + list(p["mean_ci95"] or [None, None]) for p in r["periods"]])


# ----------------------------------------------------------------------------
# Storm selection
# ----------------------------------------------------------------------------
DRIVER_HOURS = 6  # hours before the Dst minimum that characterise the driver of a storm


def find_storms(df: pd.DataFrame, threshold_nt: float = -100.0, separation_hours: float = 6.0,
                floor_nt: Optional[float] = None, drivers: Sequence[str] = ()) -> Dict[str, Any]:
    """
    Geomagnetic storms in hourly Dst: runs of consecutive hours with Dst <= threshold, joined
    when Dst stays above the threshold for less than `separation_hours` between them (so a
    two-step main phase is one storm). Each storm is listed with the time and value of its
    Dst minimum, the first and last hour at or below the threshold, and the solar wind in
    the DRIVER_HOURS hours before the minimum: mean Bz GSM, speed, Newell dPhi/dt and the
    most frequent Xu & Borovsky (2015) type. `floor_nt` keeps storms whose minimum is above
    it (e.g. -100 >= min > -250); `drivers` keeps storms whose driver type is in the list.

    For 1996-2006 the default (-100 nT, 6 h) gives 90 storms, as Echer et al. (2008,
    J. Geophys. Res. 113, A05221) counted; at -250 nT the ten storms have minima from -263
    to -422 nT, as in Echer et al. (2008, Geophys. Res. Lett. 35, L06S03), who list eleven:
    the eleventh, 15 May 2005 (-263 nT then), is -247 nT in the current final Dst.
    """
    d = df["dst"].dropna()
    if d.empty:
        return {"storms": [], "log": []}
    below = (d <= threshold_nt).to_numpy()
    hours = (d.index.as_unit("ns").asi8 // 3_600_000_000_000).astype(np.int64)
    runs: List[List[int]] = []
    for i in np.flatnonzero(below):
        gap = hours[i] - hours[runs[-1][1]] - 1 if runs else None  # hours above the threshold in between
        if runs and (gap == 0 or gap < separation_hours):
            runs[-1][1] = i
        else:
            runs.append([i, i])
    storms = []
    for a, b in runs:
        seg = d.iloc[a:b + 1]
        t_min = seg.idxmin()
        pre = df.loc[(df.index > t_min - pd.Timedelta(hours=DRIVER_HOURS)) & (df.index <= t_min)]
        types = pre["sw_type"].dropna() if "sw_type" in pre else pd.Series(dtype=float)
        # Most frequent type; a tie goes to the tied type nearest the minimum (pandas' mode
        # sorts the tied codes, so ties always went to the lowest code, ejecta).
        modes = set(types.mode())
        mode = SW_TYPES.get(int(next(v for v in types.to_numpy()[::-1] if v in modes))) if len(types) else None
        mean = lambda col: (None if col not in pre or pre[col].dropna().empty else float(pre[col].mean()))
        storms.append({
            "minimum_time": t_min.strftime("%Y-%m-%d %H:%M"), "minimum_dst_nt": float(seg.min()),
            "first_hour_below": d.index[a].strftime("%Y-%m-%d %H:%M"),
            "last_hour_below": d.index[b].strftime("%Y-%m-%d %H:%M"),
            "driver_bz_gsm_nt": mean("bz_gsm"), "driver_speed_kms": mean("speed"), "driver_newell": mean("newell"),
            "driver_type": mode, "driver_type_hours": int(len(types)),
        })
    log = [{"filter": f"storms: Dst <= {threshold_nt:g} nT, runs closer than {separation_hours:g} h joined",
            "storms_remaining": len(storms)}]
    if floor_nt is not None:
        storms = [s for s in storms if s["minimum_dst_nt"] > floor_nt]
        log.append({"filter": f"storm minimum above {floor_nt:g} nT", "storms_remaining": len(storms)})
    if drivers:
        storms = [s for s in storms if s["driver_type"] in drivers]
        log.append({"filter": f"most frequent Xu & Borovsky type in the {DRIVER_HOURS} h before the minimum in "
                              f"{', '.join(drivers)}", "storms_remaining": len(storms)})
    return {"storms": storms, "log": log, "time_convention": "start of the hourly Dst average (UTC)"}


# ----------------------------------------------------------------------------
# Ring current model skill over many storms
# ----------------------------------------------------------------------------
def storm_window(dst: pd.Series, minimum_time: pd.Timestamp, recovery_nt: float = -50.0,
                 max_before_h: int = 24, max_after_h: int = 72) -> Tuple[pd.Timestamp, pd.Timestamp]:
    """
    Scoring window of a storm, after Ji et al. (2012): from the highest Dst in the 24 h
    before the minimum (the pre-storm level or the sudden commencement) to the first hour
    after the minimum at which Dst has recovered above -50 nT (at most 72 h later).
    """
    before = dst.loc[minimum_time - pd.Timedelta(hours=max_before_h):minimum_time]
    start = before.idxmax() if len(before.dropna()) else minimum_time
    after = dst.loc[minimum_time:minimum_time + pd.Timedelta(hours=max_after_h)]
    rec = after[after > recovery_nt]
    end = rec.index[0] if len(rec) else after.index[-1] if len(after) else minimum_time
    return start, end


def dst_model_skill(df: pd.DataFrame, storms: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Burton et al. (1975) and O'Brien & McPherron (2000) driven by the hourly OMNI solar wind
    over the whole interval (started from the first observed Dst, never reset to the
    observations), scored storm by storm against hourly Dst: r, RMSE, bias and the error of
    the minimum (model - observed) in each storm window, and their means over the storms with
    95 % intervals (Student t; the storms are taken as independent samples).
    """
    from helios.core.aurora_model import AuroralModel

    obs = df["dst"]
    recs = [{"time_tag": t.strftime("%Y-%m-%d %H:%M:%S"),
             "speed": None if not np.isfinite(v) else float(v),
             "bz_gsm": None if not np.isfinite(bz) else float(bz),
             "dynamic_pressure": None if not np.isfinite(p) else float(p)}
            for t, v, bz, p in zip(df.index, df["speed"].to_numpy(float), df["bz_gsm"].to_numpy(float),
                                   df["pressure"].to_numpy(float))]
    first = obs.dropna()
    initial = float(first.iloc[0]) if len(first) else 0.0
    out: Dict[str, Any] = {"models": {}, "storms": []}
    windows = [storm_window(obs, pd.Timestamp(s["minimum_time"], tz="UTC")) for s in storms]
    for s, (a, b) in zip(storms, windows):
        out["storms"].append({"minimum_time": s["minimum_time"], "minimum_dst_nt": s["minimum_dst_nt"],
                              "window_start": a.strftime("%Y-%m-%d %H:%M"), "window_end": b.strftime("%Y-%m-%d %H:%M")})
    for key in ("obrien", "burton"):
        sim = AuroralModel.simulate_dst_evolution(recs, model=key, initial_dst=initial)
        state = pd.Series([r["dst_predicted_nt"] for r in sim], index=df.index, dtype=float)
        # Model state at the start of each hour; the observed Dst of an hour is its average,
        # compared here with the mean of the states at the start and the end of the hour.
        pred = 0.5 * (state + state.shift(-1, freq="h").reindex(state.index))
        per = []
        for entry, (a, b) in zip(out["storms"], windows):
            j = pd.concat([obs.loc[a:b], pred.loc[a:b]], axis=1).dropna()
            if len(j) < 3 or j.iloc[:, 0].std() == 0 or j.iloc[:, 1].std() == 0:
                entry[key] = None
                continue
            o, p = j.iloc[:, 0].to_numpy(), j.iloc[:, 1].to_numpy()
            sc = {"r": float(np.corrcoef(o, p)[0, 1]), "rmse_nt": float(np.sqrt(np.mean((p - o) ** 2))),
                  "bias_nt": float(np.mean(p - o)), "minimum_error_nt": float(p.min() - o.min()), "hours": int(len(o))}
            entry[key] = sc
            per.append(sc)

        def summary(name):
            v = np.array([sc[name] for sc in per])
            if len(v) < 2:
                return {"mean": float(v.mean()) if len(v) else None, "ci95": None}
            half = student_t95(len(v) - 1.0) * v.std(ddof=1) / math.sqrt(len(v))
            return {"mean": float(v.mean()), "ci95": [float(v.mean() - half), float(v.mean() + half)],
                    "median": float(np.median(v))}

        out["models"][key] = {"name": AuroralModel.DST_MODELS[key]["name"], "n_storms": len(per),
                              **{n: summary(n) for n in ("r", "rmse_nt", "bias_nt", "minimum_error_nt")}}
    out["method"] = ("Models driven by OMNI hourly speed, Bz GSM and flow pressure from the first hour of the "
                     "interval; storm windows from the highest Dst in the 24 h before the minimum to the recovery "
                     "above -50 nT (Ji et al. 2012); means over storms with Student-t 95 % intervals")
    return out
