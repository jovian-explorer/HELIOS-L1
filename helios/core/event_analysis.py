"""
Event analysis on archive data at the instruments' own cadence: interplanetary shock
normals and speeds, and minimum variance analysis of the magnetic field.

Data come from NASA CDAWeb through HAPI (helios.core.archive.parse_hapi_csv), not from
the 1-minute means used for display: WIND MFI 3-s field with SWE non-linear proton fits
(92 s, GSE velocity vector), ACE MAG 16-s with SWEPAM 64-s Level 2, and the DSCOVR 1-s
magnetometer with the Faraday cup (2016-2019). All vectors are GSE.

Shock normals (Schwartz 1998, "Shock and discontinuity normals, Mach numbers, and
related parameters", ISSI Scientific Report SR-001, ch. 10):
  MC   magnetic coplanarity      n ~ (B2 x B1) x dB
  VC   velocity coplanarity      n ~ dV
  MX1  mixed mode 1              n ~ (B1 x dV) x dB      (Abraham-Shrauner 1972)
  MX2  mixed mode 2              n ~ (B2 x dV) x dB
  MX3  mixed mode 3              n ~ (dB x dV) x dB
with dB = B2 - B1 and dV = V2 - V1 (1 = upstream, 2 = downstream). The normal points
into the upstream plasma (n . dV > 0), the convention of the Harvard-Smithsonian CfA
Interplanetary Shock Database, so a forward shock at L1 has n_x < 0. Shock speed in the
spacecraft frame from mass flux conservation: V_sh = n . (N2 V2 - N1 V1) / (N2 - N1).
theta_Bn is the angle between the upstream field and the normal (0-90 deg).

Minimum variance analysis (Sonnerup & Scheible 1998, ISSI SR-001, ch. 8): eigenvalues
and eigenvectors of the magnetic variance matrix M_ij = <B_i B_j> - <B_i><B_j>, with the
statistical angular errors of eq. 8.23,
  dphi_ij = sqrt( lambda3 / (K - 1) * (lambda_i + lambda_j - lambda3) / (lambda_i - lambda_j)^2 ) rad.
"""
import hashlib
import math
import os
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from helios.core.archive import HapiError, hapi_data_url, parse_hapi_csv

PROTON_MASS_KG = 1.67262192369e-27
BOLTZMANN_J_K = 1.380649e-23
MU0 = 4.0e-7 * math.pi
EARTH_RADIUS_KM = 6371.2

MAX_EVENT_HOURS = 72
RECENT_TTL_SECONDS = 6 * 3600

SHOCK_METHODS = ("MC", "VC", "MX1", "MX2", "MX3")
PREFERRED_METHOD = "MX3"  # the mixed-mode normal used by the CfA and Helsinki shock lists for single-spacecraft data


def _w_to_kelvin(w_kms):
    """Most probable thermal speed W = sqrt(2kT/m_p) (km/s) to proton temperature (K)."""
    return PROTON_MASS_KG * (np.asarray(w_kms, dtype=float) * 1e3) ** 2 / (2.0 * BOLTZMANN_J_K)


# ----------------------------------------------------------------------------
# Instrument datasets at native cadence (GSE). Each reducer returns standard columns:
# field: bx, by, bz [nT]; plasma: vx, vy, vz [km/s], n [cm^-3], t [K];
# position: x, y, z [km].
# ----------------------------------------------------------------------------
def _field(name: str, flag: Optional[str] = None) -> Callable:
    def reduce(df: pd.DataFrame) -> pd.DataFrame:
        if flag:
            df = df[df[flag] == 0]
        return pd.DataFrame({"bx": df[f"{name}_0"], "by": df[f"{name}_1"], "bz": df[f"{name}_2"]}, index=df.index)
    return reduce


def _wind_swe(df: pd.DataFrame) -> pd.DataFrame:
    # fit_flag: 10 = parameters OK, 2-9 = alpha-particle contingencies with valid protons,
    # 1 = "poor peak identification", 0 = no fit. Behind strong shocks most spectra carry
    # flag 1, and the CfA shock database (built by the SWE team) uses them: its downstream
    # values for e.g. 27 Feb 2014 are those of the flag-1 spectra. Event analysis keeps them
    # and marks them, so the number used is reported; flag 0 is dropped.
    df = df[df["fit_flag"] >= 1]
    return pd.DataFrame({"vx": df["Proton_VX_nonlin"], "vy": df["Proton_VY_nonlin"], "vz": df["Proton_VZ_nonlin"],
                         "n": df["Proton_Np_nonlin"], "t": _w_to_kelvin(df["Proton_W_nonlin"]),
                         "poor_fit": (df["fit_flag"] == 1).astype(float)}, index=df.index)


def _wind_pos(df: pd.DataFrame) -> pd.DataFrame:
    return pd.DataFrame({"x": df["xgse"] * EARTH_RADIUS_KM, "y": df["ygse"] * EARTH_RADIUS_KM,
                         "z": df["zgse"] * EARTH_RADIUS_KM}, index=df.index)


def _vec_plasma(n: str, t: str, flag: Optional[str] = None) -> Callable:
    def reduce(df: pd.DataFrame) -> pd.DataFrame:
        if flag:
            df = df[df[flag] == 0]
        return pd.DataFrame({"vx": df["V_GSE_0"], "vy": df["V_GSE_1"], "vz": df["V_GSE_2"],
                             "n": df[n], "t": df[t]}, index=df.index)
    return reduce


def _pos(name: str) -> Callable:
    def reduce(df: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame({"x": df[f"{name}_0"], "y": df[f"{name}_1"], "z": df[f"{name}_2"]}, index=df.index)
    return reduce


def _ds(ds_id: str, params: List[str], reduce: Callable, label: str) -> Dict[str, Any]:
    return {"id": ds_id, "parameters": params, "reduce": reduce, "label": label}


EVENT_SOURCES: Dict[str, Dict[str, Dict[str, Any]]] = {
    "WIND": {
        "field": _ds("WI_H0_MFI@1", ["B3GSE"], _field("B3GSE"), "WIND MFI 3-s"),
        "plasma": _ds("WI_H1_SWE", ["fit_flag", "Proton_VX_nonlin", "Proton_VY_nonlin", "Proton_VZ_nonlin",
                                    "Proton_W_nonlin", "Proton_Np_nonlin", "xgse", "ygse", "zgse"],
                      _wind_swe, "WIND SWE non-linear proton fits (92 s)"),
        "position": "plasma", "position_reduce": _wind_pos,
    },
    "ACE": {
        "field": _ds("AC_H0_MFI", ["BGSEc", "SC_pos_GSE"], _field("BGSEc"), "ACE MAG 16-s Level 2"),
        "plasma": _ds("AC_H0_SWE", ["Np", "Tpr", "V_GSE"], _vec_plasma("Np", "Tpr"),
                      "ACE SWEPAM 64-s Level 2 (to 2024-07)"),
        "position": "field", "position_reduce": _pos("SC_pos_GSE"),
    },
    "DSCOVR": {
        "field": _ds("DSCOVR_H0_MAG", ["B1GSE", "FLAG1"], _field("B1GSE", "FLAG1"), "DSCOVR MAG 1-s"),
        "plasma": _ds("DSCOVR_H1_FC", ["DQF", "V_GSE", "Np", "THERMAL_TEMP"],
                      _vec_plasma("Np", "THERMAL_TEMP", "DQF"), "DSCOVR Faraday cup 1-min (2016-2019)"),
        "position": _ds("DSCOVR_ORBIT_PRE", ["GSE_POS"], _pos("GSE_POS"), "DSCOVR predicted orbit"),
    },
}


class EventDataClient:
    """
    Native-cadence HAPI data for an event interval (up to MAX_EVENT_HOURS). One request per
    dataset and interval; responses are cached by URL, for good once the interval ended
    more than two days ago. `fetch_text(url)` returns the body or None.
    """

    def __init__(self, fetch_text: Callable, cache_dir: str):
        self.fetch_text = fetch_text
        self.cache_dir = os.path.join(str(cache_dir), "hapi_events")
        os.makedirs(self.cache_dir, exist_ok=True)

    async def _get(self, url: str, end: datetime) -> Optional[str]:
        path = os.path.join(self.cache_dir, hashlib.sha1(url.encode("utf-8")).hexdigest()[:20] + ".csv")
        old = (datetime.now(timezone.utc) - end).total_seconds() > 2 * 86400
        if os.path.exists(path) and (old or time.time() - os.path.getmtime(path) < RECENT_TTL_SECONDS):
            with open(path, "r", encoding="utf-8") as f:
                return f.read()
        text = await self.fetch_text(url)
        if text is None:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    return f.read()
            return None
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp, path)
        return text

    async def fetch(self, mission: str, start: datetime, end: datetime) -> Dict[str, Any]:
        """{"field", "plasma", "position": DataFrame or None, "datasets": [...], "offline": bool}"""
        src = EVENT_SOURCES[mission]
        out: Dict[str, Any] = {"field": None, "plasma": None, "position": None, "datasets": [], "offline": True}
        raw: Dict[str, pd.DataFrame] = {}
        specs = [(k, src[k]) for k in ("field", "plasma")]
        if isinstance(src["position"], dict):
            specs.append(("position", src["position"]))
        for kind, spec in specs:
            url = hapi_data_url(spec["id"], spec["parameters"], start, end)
            text = await self._get(url, end)
            if text is None:
                continue
            out["offline"] = False
            try:
                df = parse_hapi_csv(text)
                if df.empty:
                    continue
                raw[kind] = df
                frame = spec["reduce"](df).dropna(how="all").sort_index()
            except (HapiError, KeyError, ValueError):
                continue
            if frame.empty:
                continue
            out[kind] = frame
            out["datasets"].append({
                "role": kind, "id": spec["id"], "label": spec["label"], "hapi_url": url,
                "n_samples": int(len(frame)),
                "coverage_start": frame.index[0].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                "coverage_end": frame.index[-1].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]})
        if isinstance(src["position"], str) and src["position"] in raw:
            try:
                out["position"] = src["position_reduce"](raw[src["position"]]).dropna().sort_index()
            except KeyError:
                pass
        return out


# ----------------------------------------------------------------------------
# Minimum variance analysis
# ----------------------------------------------------------------------------
def minimum_variance(b: np.ndarray) -> Dict[str, Any]:
    """
    MVA of K field vectors (K x 3). Eigenvalues are returned as lambda1 >= lambda2 >= lambda3
    (maximum, intermediate, minimum variance) with their unit eigenvectors; the minimum
    variance direction is oriented so that <B> . n >= 0 and the triad is right-handed.
    The angular errors (deg) follow Sonnerup & Scheible (1998) eq. 8.23. A ratio
    lambda2/lambda3 below about 10 means the normal is poorly determined.
    """
    b = np.asarray(b, dtype=float)
    b = b[np.all(np.isfinite(b), axis=1)]
    k = len(b)
    if k < 5:
        raise ValueError("Minimum variance analysis needs at least 5 field vectors.")
    mean = b.mean(axis=0)
    m = (b.T @ b) / k - np.outer(mean, mean)
    lam, vec = np.linalg.eigh(m)  # ascending
    lam, vec = lam[::-1], vec[:, ::-1]
    lam = np.clip(lam, 0.0, None)
    x1, x2, x3 = vec[:, 0], vec[:, 1], vec[:, 2]
    if np.dot(mean, x3) < 0:
        x3 = -x3
    if np.dot(np.cross(x1, x2), x3) < 0:
        x2 = -x2
    l1, l2, l3 = (float(v) for v in lam)

    def dphi(li, lj):
        if li - lj <= 0:
            return None
        return math.degrees(math.sqrt(l3 / (k - 1) * (li + lj - l3) / (li - lj) ** 2))

    return {
        "n_vectors": k,
        "eigenvalues_nT2": [l1, l2, l3],
        "eigenvectors": {"max": x1.tolist(), "intermediate": x2.tolist(), "min": x3.tolist()},
        "ratio_intermediate_to_min": (l2 / l3) if l3 > 0 else None,
        "ratio_max_to_intermediate": (l1 / l2) if l2 > 0 else None,
        "mean_field_nT": mean.tolist(),
        "mean_normal_field_nT": float(np.dot(mean, x3)),
        "angular_error_deg": {"normal_about_intermediate": dphi(l2, l3), "normal_about_max": dphi(l1, l3),
                              "max_about_intermediate": dphi(l1, l2)},
        "method": "Minimum variance analysis, Sonnerup & Scheible (1998), errors from eq. 8.23",
    }


# ----------------------------------------------------------------------------
# Shock analysis
# ----------------------------------------------------------------------------
def _window(df: Optional[pd.DataFrame], t0: pd.Timestamp, a_min: float, b_min: float) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    lo, hi = t0 + pd.Timedelta(minutes=a_min), t0 + pd.Timedelta(minutes=b_min)
    return df[(df.index >= lo) & (df.index < hi)]


def refine_shock_time(field: pd.DataFrame, guess: pd.Timestamp, search_minutes: float = 10.0,
                      half_window_seconds: float = 60.0) -> Optional[pd.Timestamp]:
    """
    Time of the largest jump in |B| near `guess`: the sample that maximises the difference
    between the mean |B| over the following and the preceding `half_window_seconds`.
    """
    if field is None or field.empty:
        return None
    sub = _window(field, guess, -search_minutes - 2, search_minutes + 2)
    if len(sub) < 10:
        return None
    mag = np.sqrt(sub["bx"] ** 2 + sub["by"] ** 2 + sub["bz"] ** 2).dropna()
    t = mag.index
    vals = mag.to_numpy()
    secs = (t - t[0]).total_seconds().to_numpy()
    csum = np.concatenate([[0.0], np.cumsum(vals)])
    lo_t, hi_t = (guess - pd.Timedelta(minutes=search_minutes)), (guess + pd.Timedelta(minutes=search_minutes))
    best, best_i = -np.inf, None
    for i in range(len(t)):
        if t[i] < lo_t or t[i] > hi_t:
            continue
        a = np.searchsorted(secs, secs[i] - half_window_seconds, side="left")
        c = np.searchsorted(secs, secs[i] + half_window_seconds, side="left")
        if i - a < 3 or c - i < 3:
            continue
        jump = abs((csum[c] - csum[i]) / (c - i) - (csum[i] - csum[a]) / (i - a))
        if jump > best:
            best, best_i = jump, i
    if best_i is None:
        return None
    # The largest window difference can sit on the overshoot behind the ramp; the arrival is
    # where |B| first crosses half-way between the levels before and after.
    i = best_i
    a = np.searchsorted(secs, secs[i] - half_window_seconds, side="left")
    c = np.searchsorted(secs, secs[i] + half_window_seconds, side="left")
    pre, post = vals[a:i].mean(), vals[i:c].mean()
    mid = 0.5 * (pre + post)
    for j in range(a, c):
        if (vals[j] >= mid) if post > pre else (vals[j] <= mid):
            return t[j]
    return t[i]


def _means(df: pd.DataFrame, cols: List[str], required: int = 3) -> Tuple[np.ndarray, np.ndarray, int]:
    """
    Column means, standard errors of the mean, and the sample count of the first `required`
    columns (a missing temperature must not discard a valid velocity and density).
    """
    if df.empty:
        return np.full(len(cols), np.nan), np.zeros(len(cols)), 0
    sub = df[cols]
    counts = sub.notna().sum().to_numpy()
    mean = sub.mean().to_numpy(dtype=float)
    std = sub.std(ddof=1).to_numpy(dtype=float)
    sem = np.where(counts > 1, std / np.sqrt(np.maximum(counts, 1)), 0.0)
    return mean, np.nan_to_num(sem), int(counts[:required].min())


def shock_normals(b1, b2, v1, v2) -> Dict[str, np.ndarray]:
    """Unit normals of the five coplanarity / mixed-mode methods, oriented so that n . dV > 0."""
    b1, b2, v1, v2 = (np.asarray(x, dtype=float) for x in (b1, b2, v1, v2))
    db, dv = b2 - b1, v2 - v1
    raw = {
        "MC": np.cross(np.cross(b2, b1), db),
        "VC": dv,
        "MX1": np.cross(np.cross(b1, dv), db),
        "MX2": np.cross(np.cross(b2, dv), db),
        "MX3": np.cross(np.cross(db, dv), db),
    }
    out = {}
    for k, n in raw.items():
        norm = np.linalg.norm(n)
        if not np.isfinite(norm) or norm == 0:
            continue
        n = n / norm
        if np.dot(n, dv) < 0:
            n = -n
        out[k] = n
    return out


def shock_speed(n, n1, n2, v1, v2) -> float:
    """Shock speed along n in the spacecraft frame from mass flux conservation (km/s)."""
    return float(np.dot(n, n2 * np.asarray(v2) - n1 * np.asarray(v1)) / (n2 - n1))


def theta_bn(n, b1) -> float:
    """Angle between upstream field and shock normal, folded into 0-90 deg."""
    b1 = np.asarray(b1, dtype=float)
    c = abs(float(np.dot(n, b1))) / float(np.linalg.norm(b1))
    return math.degrees(math.acos(min(1.0, c)))


def _upstream_waves(n_cm3: float, t_k: Optional[float], b_nt: np.ndarray, tbn_deg: float) -> Dict[str, Optional[float]]:
    """
    Alfven speed (protons), sound speed with the OMNI definition C_s = 0.12 sqrt(T + 1.28e5 K)
    km/s (electron temperature not measured), and the fast magnetosonic speed along n.
    """
    bmag = float(np.linalg.norm(b_nt))
    va = 21.8 * bmag / math.sqrt(n_cm3)
    if t_k is None or not np.isfinite(t_k):
        return {"alfven_kms": va, "sound_kms": None, "fast_kms": None}
    cs = 0.12 * math.sqrt(t_k + 1.28e5)
    s = va ** 2 + cs ** 2
    c2 = math.cos(math.radians(tbn_deg)) ** 2
    vf = math.sqrt(0.5 * (s + math.sqrt(max(0.0, s * s - 4.0 * va ** 2 * cs ** 2 * c2))))
    return {"alfven_kms": va, "sound_kms": cs, "fast_kms": vf}


def classify_shock(n_before: float, n_after: float, b_before: float, b_after: float) -> str:
    """FF / FR / SF / SR from the time order of density and |B| (fast: B and N jump together)."""
    forward = n_after > n_before
    fast = (b_after > b_before) == forward
    return ("F" if fast else "S") + ("F" if forward else "R")


def analyze_shock(field: pd.DataFrame, plasma: pd.DataFrame, shock_time,
                  upstream_minutes: float = 10.0, downstream_minutes: float = 10.0,
                  exclude_minutes: float = 1.0, refine: bool = True, n_draws: int = 400,
                  seed: int = 1) -> Dict[str, Any]:
    """
    Normals, theta_Bn, shock speed, jump ratios and upstream Mach numbers of a shock at
    `shock_time` from field and plasma frames (GSE). Averaging windows are taken on each
    side, `exclude_minutes` away from the shock. Uncertainties come from `n_draws` Monte
    Carlo draws of the window means within their standard errors.
    """
    t_guess = pd.Timestamp(shock_time)
    t_guess = t_guess.tz_localize("UTC") if t_guess.tzinfo is None else t_guess.tz_convert("UTC")
    t0 = refine_shock_time(field, t_guess) if refine else None
    t0 = t0 if t0 is not None else t_guess

    before = (-exclude_minutes - upstream_minutes, -exclude_minutes)
    after = (exclude_minutes, exclude_minutes + downstream_minutes)
    fcols, pcols = ["bx", "by", "bz"], ["vx", "vy", "vz", "n", "t"]
    bb, bb_e, kbb = _means(_window(field, t0, *before), fcols)
    ba, ba_e, kba = _means(_window(field, t0, *after), fcols)
    pb, pb_e, kpb = _means(_window(plasma, t0, *before), pcols, 4)
    pa, pa_e, kpa = _means(_window(plasma, t0, *after), pcols, 4)
    poor = 0
    if "poor_fit" in plasma.columns:
        poor = int(_window(plasma, t0, *before)["poor_fit"].sum() + _window(plasma, t0, *after)["poor_fit"].sum())
    if min(kbb, kba) < 3 or min(kpb, kpa) < 2:
        raise ValueError("Not enough field or plasma samples in the upstream/downstream windows "
                         f"(field {kbb}/{kba}, plasma {kpb}/{kpa}).")

    shock_type = classify_shock(pb[3], pa[3], float(np.linalg.norm(bb)), float(np.linalg.norm(ba)))
    # Upstream is the side the shock propagates into: before the shock in time for a forward
    # shock, after it for a reverse shock.
    if shock_type.endswith("F"):
        (b1, b1e, b2, b2e, p1, p1e, p2, p2e) = (bb, bb_e, ba, ba_e, pb, pb_e, pa, pa_e)
        k_up, k_dn = (kbb, kpb), (kba, kpa)
    else:
        (b1, b1e, b2, b2e, p1, p1e, p2, p2e) = (ba, ba_e, bb, bb_e, pa, pa_e, pb, pb_e)
        k_up, k_dn = (kba, kpa), (kbb, kpb)

    def evaluate(b1_, b2_, p1_, p2_):
        v1_, v2_ = p1_[:3], p2_[:3]
        res = {}
        for m, n in shock_normals(b1_, b2_, v1_, v2_).items():
            res[m] = (n, theta_bn(n, b1_), shock_speed(n, p1_[3], p2_[3], v1_, v2_))
        return res

    best = evaluate(b1, b2, p1, p2)
    rng = np.random.default_rng(seed)
    draws: Dict[str, List[Tuple[np.ndarray, float, float]]] = {m: [] for m in best}
    for _ in range(n_draws):
        r = evaluate(b1 + rng.normal(0, 1, 3) * b1e, b2 + rng.normal(0, 1, 3) * b2e,
                     p1 + rng.normal(0, 1, 5) * p1e, p2 + rng.normal(0, 1, 5) * p2e)
        for m, val in r.items():
            if m in draws:
                draws[m].append(val)

    methods = {}
    for m, (n, tbn, vsh) in best.items():
        d = draws[m]
        nn = np.array([x[0] for x in d]) if d else np.zeros((0, 3))
        u1n = float(np.dot(n, p1[:3]) - vsh)  # upstream normal flow speed in the shock frame
        waves = _upstream_waves(p1[3], p1[4], b1, tbn)
        methods[m] = {
            "normal_gse": [float(x) for x in n],
            "normal_sigma": [float(x) for x in nn.std(axis=0)] if len(nn) else None,
            "theta_bn_deg": tbn,
            "theta_bn_sigma_deg": float(np.std([x[1] for x in d])) if d else None,
            "shock_speed_kms": vsh,
            "shock_speed_sigma_kms": float(np.std([x[2] for x in d])) if d else None,
            "upstream_normal_flow_kms": abs(u1n),
            "alfven_mach": abs(u1n) / waves["alfven_kms"],
            "fast_mach": (abs(u1n) / waves["fast_kms"]) if waves["fast_kms"] else None,
        }

    def side(b, be, p, pe, k):
        return {"B_gse_nT": b.tolist(), "B_sigma_nT": be.tolist(), "B_magnitude_nT": float(np.linalg.norm(b)),
                "V_gse_kms": p[:3].tolist(), "V_sigma_kms": pe[:3].tolist(),
                "density_cm3": float(p[3]), "temperature_K": float(p[4]) if np.isfinite(p[4]) else None,
                "field_samples": k[0], "plasma_samples": k[1]}

    waves = _upstream_waves(p1[3], p1[4], b1, best[PREFERRED_METHOD][1] if PREFERRED_METHOD in best else 90.0)
    density_ratio = float(p2[3] / p1[3])
    warnings = []
    if poor:
        warnings.append(f"{poor} of {kpb + kpa} plasma spectra carry the WIND SWE flag 'poor peak identification' "
                        "(fit_flag 1); they are used, as in the CfA shock database.")
    if density_ratio < 1.2:
        warnings.append(f"Density jump {density_ratio:.2f} is too small for a reliable mass-flux shock speed.")
    if min(k_up[1], k_dn[1]) < 3:
        warnings.append("Fewer than 3 plasma samples on one side: the averages rest on very few spectra.")
    if PREFERRED_METHOD in methods:
        # The methods that use the velocity jump (VC, MX1-3) should agree; the magnetic
        # coplanarity normal alone degenerates for quasi-perpendicular and quasi-parallel
        # shocks and is not part of this check.
        others = [m for m in ("VC", "MX1", "MX2") if m in best]
        spread = max((math.degrees(math.acos(min(1.0, abs(float(np.dot(best[m][0], best[PREFERRED_METHOD][0]))))))
                      for m in others), default=0.0)
        if spread > 20.0:
            warnings.append(f"The VC/MX normals differ from {PREFERRED_METHOD} by up to {spread:.0f} deg: "
                            "the normal is poorly constrained.")
    if PREFERRED_METHOD in methods and abs(methods[PREFERRED_METHOD]["shock_speed_kms"]) > 3000.0:
        warnings.append("Shock speed above 3000 km/s: the upstream and downstream states are not those of a shock.")
    return {
        "shock_time": t0.strftime("%Y-%m-%d %H:%M:%S"),
        "shock_time_requested": t_guess.strftime("%Y-%m-%d %H:%M:%S"),
        "shock_time_refined": bool(refine and t0 != t_guess),
        "shock_type": shock_type,
        "windows_minutes": {"before": list(before), "after": list(after)},
        "upstream": side(b1, b1e, p1, p1e, k_up),
        "downstream": side(b2, b2e, p2, p2e, k_dn),
        "density_ratio": density_ratio,
        "field_ratio": float(np.linalg.norm(b2) / np.linalg.norm(b1)),
        "upstream_waves_kms": waves,
        "methods": methods,
        "preferred_method": PREFERRED_METHOD if PREFERRED_METHOD in methods else next(iter(methods), None),
        "warnings": warnings,
        "conventions": ("GSE. Normal points into the upstream plasma (n . dV > 0); shock speed along n in the "
                        "spacecraft frame from mass flux conservation; theta_Bn from the upstream field. "
                        "Sound speed C_s = 0.12 sqrt(T + 1.28e5 K) km/s (OMNI definition, electrons not measured)."),
        "references": [
            "Schwartz, S. J. (1998), Shock and discontinuity normals, Mach numbers, and related parameters, "
            "ISSI Scientific Report SR-001, ch. 10",
            "Abraham-Shrauner, B. (1972), J. Geophys. Res. 77, 736, doi:10.1029/JA077i004p00736",
            "Harvard-Smithsonian CfA Interplanetary Shock Database, https://www.cfa.harvard.edu/shocks/",
        ],
    }

