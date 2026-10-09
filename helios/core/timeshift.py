"""
Time shift of upstream solar wind data to the Earth's bow shock nose, as NASA's High
Resolution OMNI (HRO) data set does it: J. H. King and N. E. Papitashvili, "One min and
5-min solar wind data sets at the Earth's bow shock nose", OMNIWeb documentation, sections
3a-3b and appendix 4 (https://omniweb.gsfc.nasa.gov/html/HROdocum.html).

* Field vectors at 15-16 s: ACE MAG 16-s as they are, WIND MFI 3-s and DSCOVR MAG 1-s
  averaged to 15 s (the WIND 15-s averages equal the SPDF file OMNI uses to 0.002 nT).
* A phase front normal (PFN) for every vector by OMNI's "technique 4": the cross product
  of the field averaged over 17 points centred 14 points before and 14 points after it,
  accepted when the two averages differ by more than 13 deg and the mean field over that
  span has a component of less than 0.035 nT along the normal; otherwise MVAB-0, minimum
  variance with <B>.n = 0 (Sonnerup & Cahill 1968; Haaland et al. 2006, as coded by
  Weimer), over 77 points with an eigenvalue ratio of at least 5.2. Normals more than
  73 deg from the flow, and windows more than 1.25 times longer than without gaps, are
  rejected; the other vectors take a normal interpolated linearly between accepted ones
  at most 3 h apart (beyond that they are not shifted).
* The delay dt = n.(R_bsn - R_sc) / n.V, with V the measured velocity plus 29.8 km/s in
  GSE Y (Earth's orbital motion), interpolated to the field times between samples less
  than 1 h apart.
* The bow shock nose lies along the aberrated flow at the Farris & Russell (1994) distance
  from the Shue et al. (1997) magnetopause nose, with OMNI's wave speeds:
  V_A = 20.3 B / sqrt(N) (4 % alphas), C_s = 0.12 sqrt(T + 1.28e5), and the fast mode speed
  at the angle between the field and the flow.
* WIND data are cleaned as OMNI does (appendix 3): 3-s field records with |B| or a component
  above 70 nT are dropped, and the SWE key-parameter plasma (OMNI's velocity source; the
  non-linear fits gave noisier delays) is despiked: a record goes when V, N, T or a velocity
  component differs from the mean of its two predecessors and two followers (within 60 min)
  by more than 4 times their RMS deviation and by more than 10 % of the mean speed (V and
  components) or 30 % of the mean (N, T).
* Vectors are binned by arrival minute; the delay of a minute is the mean over the vectors
  arriving in it (OMNI's "Timeshift"), with their RMS. Plasma records take the delay of the
  field vector observed nearest to them, within 2 min.

The flat delay (n along X: dX / -Vx) to the same bow shock nose is given for comparison.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

import numpy as np
import pandas as pd

from helios.core.archive import thermal_speed_to_kelvin
from helios.core.coordinates import gse_to_gsm

EARTH_RADIUS_KM = 6371.2
ORBITAL_VY_KMS = 29.8          # added to Vy (appendix 4)
CADENCE_S = 15.0
CP_POINTS, CP_OFFSET, CP_MIN_ANGLE_DEG, CP_MAX_NORMAL_NT = 17, 14, 13.0, 0.035
MVA_POINTS, MVA_MIN_RATIO = 77, 5.2
MAX_FLOW_ANGLE_DEG = 73.0
GAP_FACTOR = 1.25
MAX_INTERPOLATION_S = 3 * 3600.0
MAX_VELOCITY_GAP_S = 3600.0
PLASMA_MATCH_S = 120.0
# Delays longer than this are not followed (the slowest wind from beyond L1 takes about 2 h).
MAX_DELAY_HOURS = 3.0

METHOD = ("Time shift to the bow shock nose as in NASA's High Resolution OMNI (King & Papitashvili, "
          "OMNIWeb HRO documentation, sec. 3 and appendix 4): phase front normals by cross products "
          "(17-point averages 14 points before and after, > 13 deg, |<B>.n| < 0.035 nT), else MVAB-0 "
          "(77 points, eigenvalue ratio >= 5.2), within 73 deg of the flow, interpolated over at most 3 h; "
          "dt = n.(R_bsn - R_sc) / n.V with 29.8 km/s added to Vy; bow shock nose from Farris & Russell "
          "(1994) and Shue et al. (1997) along the aberrated flow")


# OMNI's spacecraft codes in HRO (IMF/PLS words) for the spacecraft it shifts.
OMNI_IDS = {"WIND": 51, "ACE": 71}
# Arrival intervals per request: the data reach back MAX_DELAY_HOURS more (within 72 h).
MAX_SHIFT_HOURS = 48


def _wind_kp(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame({"vx": df["V_GSE_0"], "vy": df["V_GSE_1"], "vz": df["V_GSE_2"], "n": df["Np"],
                        "t": thermal_speed_to_kelvin(df["THERMAL_SPD"])}, index=df.index)
    return out[(out["vx"] < 0) & (out["vx"] > -3000)]  # Weimer's validity test


# Datasets used besides the event analysis ones (helios.core.event_analysis.EVENT_SOURCES).
WIND_KP_PLASMA = {"id": "WI_K0_SWE", "parameters": ["V_GSE", "THERMAL_SPD", "Np"], "reduce": _wind_kp,
                  "label": "WIND SWE key parameters (OMNI's velocity source for WIND)"}
OMNI_SHIFTS = {"id": "OMNI_HRO_1MIN", "parameters": ["IMF", "Timeshift"],
               "reduce": lambda df: df[["IMF", "Timeshift"]],
               "label": "OMNI HRO 1-min: source spacecraft and time shift (for comparison)"}


def _seconds(index: pd.DatetimeIndex) -> np.ndarray:
    """Seconds since 1970 (independent of the index's time unit)."""
    return index.as_unit("ns").asi8 / 1e9


def field_15s(field: pd.DataFrame) -> pd.DataFrame:
    """bx, by, bz at 15-16 s: kept when the cadence is already 14 s or more, else 15-s means."""
    f = field[["bx", "by", "bz"]].dropna()
    if len(f) < 2:
        return f
    step = float(np.median(np.diff(_seconds(f.index))))
    if step >= 14.0:
        return f
    return f.resample(f"{int(CADENCE_S)}s", label="left", closed="left").mean().dropna()


def _interpolate(df: Optional[pd.DataFrame], cols, times: pd.DatetimeIndex, max_gap_s: float) -> np.ndarray:
    """Linear interpolation of `cols` to `times`; NaN where the bracketing samples are more than max_gap_s apart."""
    out = np.full((len(times), len(cols)), np.nan)
    if df is None:
        return out
    d = df[list(cols)].dropna()
    if len(d) < 2:
        return out
    x = _seconds(d.index)
    t = _seconds(times)
    for k, c in enumerate(cols):
        out[:, k] = np.interp(t, x, d[c].to_numpy(dtype=float), left=np.nan, right=np.nan)
    j = np.clip(np.searchsorted(x, t), 1, len(x) - 1)
    out[(x[j] - x[j - 1]) > max_gap_s] = np.nan
    return out


def wind_field_limit(field: pd.DataFrame, limit_nt: float = 70.0) -> pd.DataFrame:
    """WIND MFI records with |B| and every component at most `limit_nt` (OMNI appendix 3)."""
    b = field[["bx", "by", "bz"]]
    ok = (b.abs() <= limit_nt).all(axis=1) & (np.sqrt((b ** 2).sum(axis=1)) <= limit_nt)
    return field[ok]


def despike_plasma(plasma: pd.DataFrame, window_s: float = 3600.0) -> pd.DataFrame:
    """
    OMNI appendix 3 for WIND SWE: drop a record when V, N, T, Vx, Vy or Vz differs from the
    mean of its two predecessors and two followers by more than 4 times their RMS deviation
    and by more than 10 % of the mean speed (V, components) or 30 % of the mean (N, T). The
    five records must lie within `window_s`; the first and last two of a stretch go untested.
    """
    p = plasma.dropna(subset=["vx", "vy", "vz"])
    if len(p) < 5:
        return p
    t = _seconds(p.index)
    vals = {"v": np.sqrt(p["vx"] ** 2 + p["vy"] ** 2 + p["vz"] ** 2).to_numpy(dtype=float),
            "n": p["n"].to_numpy(dtype=float), "t": p["t"].to_numpy(dtype=float),
            "vx": p["vx"].to_numpy(dtype=float), "vy": p["vy"].to_numpy(dtype=float),
            "vz": p["vz"].to_numpy(dtype=float)}
    idx = np.arange(2, len(p) - 2)
    tested = (t[idx + 2] - t[idx - 2]) <= window_s

    def neighbours(a):
        nb = np.stack([a[idx - 2], a[idx - 1], a[idx + 1], a[idx + 2]])
        return np.nanmean(nb, axis=0), np.nanstd(nb, axis=0)

    v_mean, _ = neighbours(vals["v"])
    spike = np.zeros(len(idx), dtype=bool)
    for key, frac in (("v", 0.1), ("n", 0.3), ("t", 0.3), ("vx", 0.1), ("vy", 0.1), ("vz", 0.1)):
        m, sd = neighbours(vals[key])
        dev = np.abs(vals[key][idx] - m)
        ref = v_mean if key in ("vx", "vy", "vz") else np.abs(m)
        with np.errstate(invalid="ignore"):
            spike |= (dev > 4.0 * sd) & (dev > frac * ref)
    drop = np.zeros(len(p), dtype=bool)
    drop[idx[tested & spike]] = True
    return p[~drop]


def bow_shock_nose(n_cm3, v_kms, b_nt, t_k, bz_gsm_nt) -> np.ndarray:
    """
    Bow shock nose (R_E, GSE) for each sample, OMNI appendix 4: along -V/|V| (V already
    aberrated) at R_bs = R_mp [1 + 1.1 ((2/3) M^2 + 2) / ((8/3)(M^2 - 1))] (Farris & Russell
    1994) with R_mp = (11.4 + K Bz) P^(-1/6.6), K = 0.013 (Bz > 0) or 0.140 (Shue et al.
    1997), P = 2e-6 N V^2 nPa, and M = V / V_ms the fast magnetosonic Mach number. NaN where
    an input is missing or the flow is not super-magnetosonic.
    """
    v = np.atleast_2d(np.asarray(v_kms, dtype=float))
    b = np.atleast_2d(np.asarray(b_nt, dtype=float))
    n = np.asarray(n_cm3, dtype=float)
    t = np.asarray(t_k, dtype=float)
    bz = np.asarray(bz_gsm_nt, dtype=float)
    vmag = np.linalg.norm(v, axis=1)
    bmag = np.linalg.norm(b, axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        p = 2e-6 * n * vmag ** 2
        r_mp = (11.4 + np.where(bz > 0, 0.013, 0.140) * bz) * p ** (-1.0 / 6.6)
        va = 20.3 * bmag / np.sqrt(n)
        cs = 0.12 * np.sqrt(t + 1.28e5)
        cos_th = np.abs(np.sum(b * v, axis=1)) / (bmag * vmag)
        s = va ** 2 + cs ** 2
        v_ms = np.sqrt(0.5 * (s + np.sqrt(np.maximum(s ** 2 - 4.0 * va ** 2 * cs ** 2 * cos_th ** 2, 0.0))))
        m2 = (vmag / v_ms) ** 2
        r_bs = r_mp * (1.0 + 1.1 * ((2.0 / 3.0) * m2 + 2.0) / ((8.0 / 3.0) * (m2 - 1.0)))
        r_bs = np.where((m2 > 1.0) & (n > 0) & (t > 0) & (p > 0), r_bs, np.nan)
        return -r_bs[:, None] * v / vmag[:, None]


def _window_sums(x: np.ndarray) -> np.ndarray:
    """Prefix sums along axis 0 with a leading zero, for window sums s[j+1] - s[i]."""
    return np.concatenate([np.zeros((1,) + x.shape[1:]), np.cumsum(x, axis=0)])


def phase_front_normals(b: np.ndarray, tsec: np.ndarray, v: np.ndarray) -> Dict[str, np.ndarray]:
    """
    OMNI technique 4 normals for each field vector. Returns {"normal": (N, 3) unit vectors
    with n_x >= 0 (NaN where none), "source": 1 cross product, 2 MVAB-0, 3 interpolated,
    0 none}. `v` is the (aberrated) velocity at the field times.
    """
    b = np.asarray(b, dtype=float)
    N = len(b)
    normal = np.full((N, 3), np.nan)
    source = np.zeros(N, dtype=int)
    if N < 3:
        return {"normal": normal, "source": source}
    dt = float(np.median(np.diff(tsec)))
    vmag = np.linalg.norm(v, axis=1)
    vhat = v / vmag[:, None]
    cos_limit = np.cos(np.radians(MAX_FLOW_ANGLE_DEG))
    idx = np.arange(N)
    s1 = _window_sums(b)

    def wmean(lo, hi):  # mean over [lo, hi] (inclusive) for valid index arrays
        return (s1[hi + 1] - s1[lo]) / (hi - lo + 1)[:, None]

    def gap_ok(lo, hi):
        return (tsec[hi] - tsec[lo]) <= GAP_FACTOR * (hi - lo) * dt

    # Cross product of the 17-point averages centred 14 points before and after.
    hc = CP_POINTS // 2
    lo, hi = idx - CP_OFFSET - hc, idx + CP_OFFSET + hc
    ok = (lo >= 0) & (hi < N)
    i = idx[ok]
    lo, hi = lo[ok], hi[ok]
    b1 = wmean(lo, lo + CP_POINTS - 1)
    b2 = wmean(hi - CP_POINTS + 1, hi)
    cross = np.cross(b1, b2)
    cnorm = np.linalg.norm(cross, axis=1)
    angle = np.degrees(np.arctan2(cnorm, np.sum(b1 * b2, axis=1)))
    with np.errstate(invalid="ignore", divide="ignore"):
        n_cp = cross / cnorm[:, None]
    good = (gap_ok(lo, hi) & (cnorm > 0) & (angle > CP_MIN_ANGLE_DEG)
            & (np.abs(np.sum(wmean(lo, hi) * n_cp, axis=1)) < CP_MAX_NORMAL_NT)
            & (np.abs(np.sum(n_cp * vhat[i], axis=1)) >= cos_limit))
    normal[i[good]] = n_cp[good]
    source[i[good]] = 1

    # MVAB-0 over 77 points where the cross product gave none.
    h = MVA_POINTS // 2
    lo, hi = idx - h, idx + h
    ok = (lo >= 0) & (hi < N) & (source == 0)
    i, lo, hi = idx[ok], lo[ok], hi[ok]
    if len(i):
        s2 = _window_sums(np.einsum("ni,nj->nij", b, b))
        mean = wmean(lo, hi)
        cov = (s2[hi + 1] - s2[lo]) / MVA_POINTS - np.einsum("ni,nj->nij", mean, mean)
        e = mean / np.linalg.norm(mean, axis=1)[:, None]
        proj = np.eye(3)[None] - np.einsum("ni,nj->nij", e, e)
        w, vecs = np.linalg.eigh(proj @ cov @ proj)  # ascending; w[:, 0] ~ 0 along <B>
        n_mv = vecs[:, :, 1]
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio = w[:, 2] / w[:, 1]
        # The floor keeps round-off in windows without variance (a constant field) from
        # passing as a well-determined normal.
        good = (gap_ok(lo, hi) & (w[:, 1] > 1e-10 * np.sum(mean ** 2, axis=1)) & (ratio >= MVA_MIN_RATIO)
                & (np.abs(np.sum(n_mv * vhat[i], axis=1)) >= cos_limit))
        normal[i[good]] = n_mv[good]
        source[i[good]] = 2

    normal[normal[:, 0] < 0] *= -1.0
    # Linear interpolation of the normal between accepted ones at most 3 h apart.
    have = np.where(source > 0)[0]
    if len(have) >= 2:
        miss = np.where(source == 0)[0]
        k = np.searchsorted(have, miss)
        inside = (k > 0) & (k < len(have))
        miss, k = miss[inside], k[inside]
        a, c = have[k - 1], have[k]
        span = tsec[c] - tsec[a]
        keep = span <= MAX_INTERPOLATION_S
        miss, a, c, span = miss[keep], a[keep], c[keep], span[keep]
        f = ((tsec[miss] - tsec[a]) / span)[:, None]
        nn = (1.0 - f) * normal[a] + f * normal[c]
        normal[miss] = nn / np.linalg.norm(nn, axis=1)[:, None]
        source[miss] = 3
    return {"normal": normal, "source": source}


def shift_to_bow_shock(field: pd.DataFrame, plasma: Optional[pd.DataFrame], position: Optional[pd.DataFrame],
                       start, end) -> Dict[str, Any]:
    """
    Shift the field (bx, by, bz nT GSE), plasma (vx, vy, vz km/s, n cm^-3, t K) and position
    (x, y, z km GSE) of an upstream spacecraft to the bow shock nose. `start`/`end` bound the
    arrival times; the data must begin early enough (up to MAX_DELAY_HOURS before `start`).
    Returns per-minute arrival series and a summary.
    """
    t0, t1 = pd.Timestamp(start), pd.Timestamp(end)
    if plasma is None or position is None:
        raise ValueError("The time shift needs the velocity and the spacecraft position as well as the field.")
    f = field_15s(field)
    if len(f) < MVA_POINTS:
        raise ValueError("Too few field vectors for phase front normals (at least 20 minutes are needed).")
    times = f.index
    tsec = _seconds(times)
    b = f.to_numpy(dtype=float)
    v = _interpolate(plasma, ("vx", "vy", "vz"), times, MAX_VELOCITY_GAP_S)
    v[:, 1] += ORBITAL_VY_KMS
    nt = _interpolate(plasma, ("n", "t"), times, MAX_VELOCITY_GAP_S)
    pos = _interpolate(position, ("x", "y", "z"), times, MAX_VELOCITY_GAP_S)
    _, _, bz_gsm = gse_to_gsm(times, b[:, 0], b[:, 1], b[:, 2])
    target = bow_shock_nose(nt[:, 0], v, b, nt[:, 1], bz_gsm) * EARTH_RADIUS_KM
    pfn = phase_front_normals(b, tsec, v)
    n = pfn["normal"]
    with np.errstate(invalid="ignore", divide="ignore"):
        delay = np.sum(n * (target - pos), axis=1) / np.sum(n * v, axis=1)
        flat = (target[:, 0] - pos[:, 0]) / v[:, 0]
    bad = ~np.isfinite(delay) | (delay < 0) | (delay > MAX_DELAY_HOURS * 3600)
    delay[bad] = np.nan
    flat[~np.isfinite(flat) | (flat < 0) | (flat > MAX_DELAY_HOURS * 3600)] = np.nan

    def by_minute(d: np.ndarray, values: Dict[str, np.ndarray]) -> pd.DataFrame:
        ok = np.isfinite(d)
        arrival = (times[ok] + pd.to_timedelta(d[ok], unit="s")).floor("min")
        frame = pd.DataFrame({k: v_[ok] for k, v_ in values.items()}, index=arrival)
        frame = frame[(frame.index >= t0) & (frame.index < t1)]
        return frame.groupby(level=0)

    src = pfn["source"]
    g = by_minute(delay, {"delay_s": delay, "bx": b[:, 0], "by": b[:, 1], "bz": b[:, 2],
                          "bsn_x": target[:, 0] / EARTH_RADIUS_KM, "bsn_y": target[:, 1] / EARTH_RADIUS_KM,
                          "bsn_z": target[:, 2] / EARTH_RADIUS_KM,
                          "cross_product": (src == 1).astype(float), "mvab0": (src == 2).astype(float),
                          "interpolated": (src == 3).astype(float)})
    minutes = g.mean()
    minutes["delay_rms_s"] = g["delay_s"].std(ddof=0)
    minutes["points"] = g["delay_s"].count()
    minutes["flat_delay_s"] = by_minute(flat, {"flat": flat}).mean()["flat"]
    # Plasma: the delay of the field vector observed nearest to each record (within 2 min).
    p = plasma[["vx", "vy", "vz", "n", "t"]].dropna(how="all")
    if len(p):
        ps = _seconds(p.index)
        k = np.clip(np.searchsorted(tsec, ps), 1, len(tsec) - 1)
        k = np.where(np.abs(tsec[k - 1] - ps) < np.abs(tsec[k] - ps), k - 1, k)
        pd_ = np.where(np.abs(tsec[k] - ps) <= PLASMA_MATCH_S, delay[k], np.nan)
        ok = np.isfinite(pd_)
        arrival = (p.index[ok] + pd.to_timedelta(pd_[ok], unit="s")).floor("min")
        pp = p[ok].copy()
        pp["speed"] = np.sqrt(pp["vx"] ** 2 + pp["vy"] ** 2 + pp["vz"] ** 2)
        pp.index = arrival
        pp = pp[(pp.index >= t0) & (pp.index < t1)].groupby(level=0).mean()
        minutes = minutes.join(pp[["speed", "vx", "vy", "vz", "n", "t"]].rename(
            columns={"n": "density", "t": "temperature"}), how="left")
    minutes = minutes.sort_index()
    if len(minutes):
        _, by_gsm, bz_gsm_m = gse_to_gsm(minutes.index, minutes["bx"].to_numpy(), minutes["by"].to_numpy(),
                                         minutes["bz"].to_numpy())
        minutes["by_gsm"], minutes["bz_gsm"] = by_gsm, bz_gsm_m
    # Vectors arriving in [start, end), by the source of their normal; vectors observed over the
    # same span shifted back by the median delay that could not be shifted.
    shifted = np.isfinite(delay)
    arrival_s = tsec + np.where(shifted, delay, 0.0)
    a0, a1 = t0.value / 1e9, t1.value / 1e9
    inside = shifted & (arrival_s >= a0) & (arrival_s < a1)
    counts = {name: int(np.sum(src[inside] == code)) for name, code in
              (("cross_product", 1), ("mvab0", 2), ("interpolated", 3))}
    if inside.any():
        lag = float(np.median(delay[inside]))
        counts["not_shifted"] = int(np.sum(~shifted & (tsec >= a0 - lag) & (tsec < a1 - lag)))
    else:
        counts["not_shifted"] = int(np.sum(~shifted))
    return {"minutes": minutes, "normal_sources": counts, "vectors": int(np.sum(inside)),
            "cadence_s": float(np.median(np.diff(tsec))), "method": METHOD}


def compare_with_omni(minutes: pd.DataFrame, omni: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """
    Agreement of the per-minute delays with OMNI's Timeshift (seconds) over the minutes of
    `omni` (index: minute, column 'Timeshift'), for the PFN and the flat delays.
    """
    if omni is None or omni.empty or minutes.empty:
        return None
    j = minutes[["delay_s", "flat_delay_s"]].join(omni[["Timeshift"]], how="inner").dropna(subset=["Timeshift"])
    if j.empty:
        return None
    out: Dict[str, Any] = {"minutes": int(len(j)), "omni_median_delay_min": round(float(j["Timeshift"].median()) / 60, 2)}
    for name, col in (("phase_front", "delay_s"), ("flat", "flat_delay_s")):
        d = ((j[col] - j["Timeshift"]) / 60.0).dropna()
        if d.empty:
            continue
        out[name] = {"minutes": int(len(d)), "median_difference_min": round(float(d.median()), 2),
                     "median_abs_difference_min": round(float(d.abs().median()), 2),
                     "within_1_min_percent": round(100.0 * float((d.abs() <= 1).mean()), 1),
                     "within_2_min_percent": round(100.0 * float((d.abs() <= 2).mean()), 1)}
    return out
