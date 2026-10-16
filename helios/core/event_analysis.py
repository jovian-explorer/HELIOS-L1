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
import warnings
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

from helios.core.lepping_errors import lepping_uncertainties
from helios.core.archive import (BOLTZMANN_J_K, PROTON_MASS_KG, HapiError, hapi_data_url, parse_hapi_csv,
                                 thermal_speed_to_kelvin)
from helios.core.constants import AU_KM
from helios.core.cache import cached_text

MU0 = 4.0e-7 * math.pi
EARTH_RADIUS_KM = 6371.2

MAX_EVENT_HOURS = 72
RECENT_TTL_SECONDS = 6 * 3600

SHOCK_METHODS = ("MC", "VC", "MX1", "MX2", "MX3")
PREFERRED_METHOD = "MX3"  # the mixed-mode normal used by the CfA and Helsinki shock lists for single-spacecraft data


def _utc(t) -> pd.Timestamp:
    """Timestamp in UTC; naive values are taken as UTC."""
    t = pd.Timestamp(t)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


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
    out = pd.DataFrame({"vx": df["Proton_VX_nonlin"], "vy": df["Proton_VY_nonlin"], "vz": df["Proton_VZ_nonlin"],
                        "n": df["Proton_Np_nonlin"], "t": thermal_speed_to_kelvin(df["Proton_W_nonlin"]),
                        "poor_fit": (df["fit_flag"] == 1).astype(float)}, index=df.index)
    # 1-sigma fit uncertainties of the bulk speed and density ("1-sigma uncertainty of the
    # proton bulk speed / density" in the CDF metadata), where the request included them.
    if "Proton_sigmaV_nonlin" in df:
        out["sigma_v"] = df["Proton_sigmaV_nonlin"]
    if "Proton_sigmaNp_nonlin" in df:
        out["sigma_n"] = df["Proton_sigmaNp_nonlin"]
    if "Proton_sigmaW_nonlin" in df:  # T ~ W^2, so sigma_T / T = 2 sigma_W / W
        out["sigma_t"] = out["t"] * 2.0 * df["Proton_sigmaW_nonlin"] / df["Proton_W_nonlin"]
    return out


def _wind_pos(df: pd.DataFrame) -> pd.DataFrame:
    # PGSE of the MFI 1-min file (R_E, definitive orbit, 7 digits). The SWE file's xgse is
    # served with 3 significant digits (1 R_E), and the predicted orbit file WI_OR_PRE
    # differed by up to 2 R_E from it in 2014.
    return pd.DataFrame({"x": df["PGSE_0"] * EARTH_RADIUS_KM, "y": df["PGSE_1"] * EARTH_RADIUS_KM,
                         "z": df["PGSE_2"] * EARTH_RADIUS_KM}, index=df.index)


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
        "field_coarse": _ds("WI_H0_MFI@0", ["BGSE"], _field("BGSE"), "WIND MFI 1-min"),
        "plasma": _ds("WI_H1_SWE", ["fit_flag", "Proton_sigmaV_nonlin", "Proton_VX_nonlin", "Proton_VY_nonlin",
                                    "Proton_VZ_nonlin", "Proton_W_nonlin", "Proton_sigmaW_nonlin", "Proton_Np_nonlin",
                                    "Proton_sigmaNp_nonlin"],
                      _wind_swe, "WIND SWE non-linear proton fits (92 s)"),
        "position": _ds("WI_H0_MFI@0", ["PGSE"], _wind_pos, "WIND position (MFI 1-min file, definitive orbit)"),
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
    dataset and interval; responses are cached by URL, for good when fetched more than two days
    after the interval ended. `fetch_text(url)` returns the body or None.
    """

    def __init__(self, fetch_text: Callable, cache_dir: str):
        self.fetch_text = fetch_text
        self.cache_dir = os.path.join(str(cache_dir), "hapi_events")
        os.makedirs(self.cache_dir, exist_ok=True)

    async def _get(self, url: str, end: datetime) -> Optional[str]:
        path = os.path.join(self.cache_dir, hashlib.sha1(url.encode("utf-8")).hexdigest()[:20] + ".csv")
        # For good only if fetched more than two days after the interval ended (complete then).
        text, _ = await cached_text(path, url, self.fetch_text, RECENT_TTL_SECONDS, end + timedelta(days=2))
        return text

    async def fetch_dataset(self, spec: Dict[str, Any], start: datetime, end: datetime, role: str):
        """
        One dataset of `spec` (id, parameters, reduce, label): (frame or None, provenance record,
        whether the server answered or a cached copy existed, raw HAPI frame or None).
        """
        url = hapi_data_url(spec["id"], spec["parameters"], start, end)
        text = await self._get(url, end)
        if text is None:
            return None, None, False, None
        try:
            df = parse_hapi_csv(text)
        except (HapiError, ValueError):
            return None, None, True, None
        if df.empty:
            return None, None, True, None
        try:
            frame = spec["reduce"](df).dropna(how="all").sort_index()
        except (KeyError, ValueError):
            return None, None, True, df
        if frame.empty:
            return None, None, True, df
        record = {"role": role, "id": spec["id"], "label": spec["label"], "hapi_url": url,
                  "n_samples": int(len(frame)),
                  "coverage_start": frame.index[0].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3],
                  "coverage_end": frame.index[-1].strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]}
        return frame, record, True, df

    async def fetch(self, mission: str, start: datetime, end: datetime, coarse: bool = False) -> Dict[str, Any]:
        """
        {"field", "plasma", "position": DataFrame or None, "datasets": [...], "offline": bool}.
        `coarse` uses a lower-cadence field dataset where one exists (WIND 1-min), for fits
        to day-long structures that average the field anyway.
        """
        src = EVENT_SOURCES[mission]
        out: Dict[str, Any] = {"field": None, "plasma": None, "position": None, "datasets": [], "offline": True}
        raw: Dict[str, pd.DataFrame] = {}
        specs = [("field", src["field_coarse"] if coarse and "field_coarse" in src else src["field"]),
                 ("plasma", src["plasma"])]
        if isinstance(src["position"], dict):
            specs.append(("position", src["position"]))
        for kind, spec in specs:
            frame, record, reached, df = await self.fetch_dataset(spec, start, end, kind)
            out["offline"] = out["offline"] and not reached
            if df is not None:
                raw[kind] = df
            if frame is not None:
                out[kind] = frame
                out["datasets"].append(record)
        if isinstance(src["position"], str) and src["position"] in raw:
            try:
                out["position"] = src["position_reduce"](raw[src["position"]]).dropna().sort_index()
            except KeyError:
                pass
        return out


# ----------------------------------------------------------------------------
# Minimum variance analysis
# ----------------------------------------------------------------------------
BOOTSTRAP_MAX_VECTORS = 5_000_000


def _mva_eigen(b: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Mean field, eigenvalues (descending, >= 0) and eigenvectors (columns) of the variance matrix (eq. 8.8)."""
    mean = b.mean(axis=0)
    m = (b.T @ b) / len(b) - np.outer(mean, mean)
    lam, vec = np.linalg.eigh(m)  # ascending
    return mean, np.clip(lam[::-1], 0.0, None), vec[:, ::-1]


def minimum_variance(b: np.ndarray, n_bootstrap: int = 1000, seed: int = 1) -> Dict[str, Any]:
    """
    MVA of K field vectors (K x 3). Eigenvalues are returned as lambda1 >= lambda2 >= lambda3
    (maximum, intermediate, minimum variance) with their unit eigenvectors; the minimum
    variance direction is oriented so that <B> . n >= 0 and the triad is right-handed.
    Statistical errors follow Sonnerup & Scheible (1998): the angular uncertainties of
    eq. 8.23, |dphi_ij| = sqrt(lambda3 (lambda_i + lambda_j - lambda3) / ((K - 1)
    (lambda_i - lambda_j)^2)), where dphi_ij is the rotation of eigenvector i toward j, and
    the uncertainty of <B> . n from eq. 8.24. With `n_bootstrap` > 0 the same quantities
    are also estimated from bootstrap resamples of the vectors (Kawano & Higuchi 1995):
    standard deviations of <B> . x3 and of the rotations of the resampled x3 toward x1 and
    x2, and the bootstrap mean normal. A ratio lambda2/lambda3 below about 10 means the
    normal is poorly determined.
    """
    b = np.asarray(b, dtype=float)
    b = b[np.all(np.isfinite(b), axis=1)]
    k = len(b)
    if k < 5:
        raise ValueError("Minimum variance analysis needs at least 5 field vectors.")
    mean, lam, vec = _mva_eigen(b)
    x1, x2, x3 = vec[:, 0], vec[:, 1], vec[:, 2]
    if np.dot(mean, x3) < 0:
        x3 = -x3
    if np.dot(np.cross(x1, x2), x3) < 0:
        x2 = -x2
    l1, l2, l3 = (float(v) for v in lam)

    def dphi(li, lj):  # eq. 8.23, radians
        if li - lj <= 0:
            return None
        return math.sqrt(l3 / (k - 1) * (li + lj - l3) / (li - lj) ** 2)

    d32, d31, d21 = dphi(l2, l3), dphi(l1, l3), dphi(l1, l2)
    bn = float(np.dot(mean, x3))
    bn_err = None
    if d32 is not None and d31 is not None:  # eq. 8.24
        bn_err = math.sqrt(l3 / (k - 1) + (d32 * float(np.dot(mean, x2))) ** 2
                           + (d31 * float(np.dot(mean, x1))) ** 2)

    def deg(r):
        return None if r is None else math.degrees(r)

    out = {
        "n_vectors": k,
        "eigenvalues_nT2": [l1, l2, l3],
        "eigenvectors": {"max": x1.tolist(), "intermediate": x2.tolist(), "min": x3.tolist()},
        "ratio_intermediate_to_min": (l2 / l3) if l3 > 0 else None,
        "ratio_max_to_intermediate": (l1 / l2) if l2 > 0 else None,
        "mean_field_nT": mean.tolist(),
        "mean_field_along_eigenvectors_nT": [float(np.dot(mean, x)) for x in (x1, x2, x3)],
        "mean_normal_field_nT": bn,
        "mean_normal_field_error_nT": bn_err,
        # dphi_ij: rotation of eigenvector i toward eigenvector j (i.e. about the third one).
        "angular_error_deg": {"normal_toward_intermediate": deg(d32), "normal_toward_max": deg(d31),
                              "max_toward_intermediate": deg(d21)},
        "method": "Minimum variance analysis, Sonnerup & Scheible (1998); errors from eqs. 8.23-8.24",
    }
    # Memory grows as N x K: limit the resamples to 5 million vectors in all, and skip the
    # bootstrap (the analytical errors remain) when fewer than 100 resamples fit.
    n_boot = min(int(n_bootstrap or 0), BOOTSTRAP_MAX_VECTORS // k)
    if n_bootstrap and n_boot < 100:
        out["bootstrap"] = None
        out["bootstrap_note"] = (f"No bootstrap for {k} vectors (more than {BOOTSTRAP_MAX_VECTORS // 100}); "
                                 "average the data (average_seconds) to obtain one.")
    elif n_boot > 0:
        n_bootstrap = n_boot
        rng = np.random.default_rng(seed)
        samples = b[rng.integers(0, k, size=(int(n_bootstrap), k))]   # [N, K, 3]
        means = samples.mean(axis=1)
        mats = np.einsum("nki,nkj->nij", samples, samples) / k - np.einsum("ni,nj->nij", means, means)
        n3 = np.linalg.eigh(mats)[1][:, :, 0]                          # minimum variance eigenvectors
        n3 = n3 * np.where(n3 @ x3 < 0, -1.0, 1.0)[:, None]            # same sense as x3
        bns = np.einsum("ni,ni->n", means, n3)
        a31 = np.arcsin(np.clip(n3 @ x1, -1.0, 1.0))
        a32 = np.arcsin(np.clip(n3 @ x2, -1.0, 1.0))
        avg = n3.mean(axis=0)
        avg /= np.linalg.norm(avg)
        out["bootstrap"] = {
            "n_samples": int(n_bootstrap),
            "mean_normal": avg.tolist(),
            "mean_normal_angle_to_x3_deg": math.degrees(math.acos(min(1.0, float(np.dot(avg, x3))))),
            "mean_normal_field_nT": float(bns.mean()),
            "mean_normal_field_std_nT": float(bns.std(ddof=1)),
            "normal_toward_max_std_deg": math.degrees(float(a31.std(ddof=1))),
            "normal_toward_intermediate_std_deg": math.degrees(float(a32.std(ddof=1))),
            "method": "Bootstrap resampling of the field vectors with replacement (Kawano & Higuchi 1995)",
        }
    return out


# ----------------------------------------------------------------------------
# deHoffmann-Teller frame (Khrabrov & Sonnerup 1998)
# ----------------------------------------------------------------------------
def _ht_solve(b: np.ndarray, v: np.ndarray, weight_by_b2: bool) -> Tuple[np.ndarray, np.ndarray]:
    """V minimising D (eq. 9.8; K^(m) = B^2 P^(m)) or Q (eq. 9.14; P^(m)), and the matrix K0 or P0."""
    b2 = np.einsum("mi,mi->m", b, b)
    proj = np.eye(3)[None, :, :] - np.einsum("mi,mj->mij", b, b) / b2[:, None, None]  # P^(m)
    km = proj * (b2[:, None, None] if weight_by_b2 else 1.0)
    k0 = km.mean(axis=0)
    rhs = np.einsum("mij,mj->mi", km, v).mean(axis=0)
    return np.linalg.solve(k0, rhs), k0


def _ht_residual(b: np.ndarray, v: np.ndarray, frame: np.ndarray, weight_by_b2: bool) -> float:
    """D(V) = <|(v - V) x B|^2> (mV/m)^2, or Q(V) = <|(v - V) x B|^2 / B^2> (km/s)^2."""
    e = np.cross(v - frame, b)
    sq = np.einsum("mi,mi->m", e, e)
    if weight_by_b2:
        return float(sq.mean()) * 1e-6  # (km/s nT)^2 -> (mV/m)^2
    return float((sq / np.einsum("mi,mi->m", b, b)).mean())


def dehoffmann_teller(b: np.ndarray, v: np.ndarray, n_cm3: Optional[np.ndarray] = None,
                      normal: Optional[np.ndarray] = None, n_bootstrap: int = 0, seed: int = 1) -> Dict[str, Any]:
    """
    deHoffmann-Teller frame velocity from M simultaneous field (nT) and plasma velocity (km/s)
    vectors, after Khrabrov & Sonnerup (1998, ISSI SR-001, ch. 9): V_HT minimises the mean
    square convection electric field in the moving frame, D(V) = <|(v - V) x B|^2>
    (eq. 9.10), and, as a second estimate, the mean square cross-field velocity Q(V)
    (eq. 9.14). The quality of the frame is the correlation coefficient c between the
    components of -v x B and -V_HT x B and the ratio D(V_HT)/D(0); uncertainties come from
    the variance matrix S = D(V_HT) K0^-1 / (2M - 3) (eq. 9.16; Q(V_HT) P0^-1 / (2M - 3) for
    Q), given as the standard deviations along its principal axes. With a normal, the
    normal velocity u_n = V_HT . n and its error follow (eq. 9.17). With densities, the
    Walen test regresses the components of v - V_HT on the proton Alfven velocity
    B / sqrt(mu0 n m_p): a slope near +-1 indicates a rotational discontinuity, near 0 a
    tangential discontinuity. Optional bootstrap resampling of the vector pairs (Sect. 9.4.2).
    """
    b, v = np.asarray(b, dtype=float), np.asarray(v, dtype=float)
    ok = np.all(np.isfinite(b), axis=1) & np.all(np.isfinite(v), axis=1)
    if n_cm3 is not None:
        n_cm3 = np.asarray(n_cm3, dtype=float)
        ok &= np.isfinite(n_cm3) & (n_cm3 > 0)
    b, v = b[ok], v[ok]
    m = len(b)
    if m < 4:
        raise ValueError("The deHoffmann-Teller analysis needs at least 4 pairs of field and velocity vectors.")
    out = {"n_vectors": m}
    for name, w in (("D", True), ("Q", False)):
        vht, k0 = _ht_solve(b, v, w)
        res = _ht_residual(b, v, vht, w)
        res0 = _ht_residual(b, v, np.zeros(3), w)
        lam, vec = np.linalg.eigh(k0)
        sig = np.sqrt((res * (1e6 if w else 1.0)) / ((2 * m - 3) * lam))  # km/s; D back to (km/s nT)^2
        s_mat = (res * (1e6 if w else 1.0)) / (2 * m - 3) * np.linalg.inv(k0)
        entry = {
            "v_ht_kms": vht.tolist(),
            "residual": res, "residual_units": "(mV/m)^2" if w else "(km/s)^2",
            "residual_ratio": res / res0 if res0 > 0 else None,
            "error_axes": [{"sigma_kms": float(sig[i]), "axis": vec[:, i].tolist()} for i in np.argsort(sig)[::-1]],
            "covariance_kms2": s_mat.tolist(),
        }
        if normal is not None:
            nn = np.asarray(normal, dtype=float)
            nn = nn / np.linalg.norm(nn)
            entry["normal_velocity_kms"] = float(vht @ nn)
            entry["normal_velocity_error_kms"] = float(math.sqrt(nn @ s_mat @ nn))
        out[name] = entry
    vht = np.array(out["D"]["v_ht_kms"])
    ec, eht = -np.cross(v, b).ravel(), -np.cross(np.broadcast_to(vht, v.shape), b).ravel()
    out["correlation_ec_eht"] = float(np.corrcoef(ec, eht)[0, 1])
    if n_cm3 is not None:
        va = b * 1e-9 / np.sqrt(MU0 * n_cm3[ok][:, None] * 1e6 * PROTON_MASS_KG) / 1e3  # km/s
        x, y = va.ravel(), (v - vht).ravel()
        slope = float(np.dot(x, y) / np.dot(x, x))  # regression through the origin
        out["walen"] = {"slope": slope, "correlation": float(np.corrcoef(x, y)[0, 1]),
                        "note": "Slope of (v - V_HT) against the proton Alfven velocity; |slope| near 1: "
                                "rotational discontinuity, near 0: tangential discontinuity."}
    if n_bootstrap and n_bootstrap > 0:
        rng = np.random.default_rng(seed)
        draws = np.array([_ht_solve(b[i], v[i], True)[0] for i in rng.integers(0, m, size=(int(n_bootstrap), m))])
        cov = np.cov(draws.T)
        lam, vec = np.linalg.eigh(cov)
        boot = {"n_samples": int(n_bootstrap), "v_ht_kms": draws.mean(axis=0).tolist(),
                "error_axes": [{"sigma_kms": float(math.sqrt(max(lam[i], 0.0))), "axis": vec[:, i].tolist()}
                               for i in np.argsort(lam)[::-1]]}
        if normal is not None:
            boot["normal_velocity_kms"] = float(draws.mean(axis=0) @ nn)
            boot["normal_velocity_error_kms"] = float((draws @ nn).std(ddof=1))
        out["bootstrap"] = boot
    out["method"] = ("deHoffmann-Teller analysis, Khrabrov & Sonnerup (1998): minimisation of D (eq. 9.10) and "
                     "Q (eq. 9.14), errors from eq. 9.16")
    return out


def field_at_plasma_times(field: pd.DataFrame, plasma: pd.DataFrame) -> np.ndarray:
    """Mean field vector over each plasma sample interval (half the median plasma spacing either side)."""
    pidx, fidx = plasma.index.as_unit("ns"), field.index.as_unit("ns")
    half = float(np.median(np.diff(pidx.asi8))) / 2.0 if len(pidx) > 1 else 30e9
    edges = np.concatenate([pidx.asi8 - half, [pidx.asi8[-1] + half]])
    inside = (fidx.asi8 >= edges[0]) & (fidx.asi8 < edges[-1])
    which = np.searchsorted(edges, fidx.asi8[inside], side="right") - 1
    return field[inside][["bx", "by", "bz"]].groupby(which).mean().reindex(range(len(plasma))).to_numpy(float)


# ----------------------------------------------------------------------------
# Coupling functions with propagated measurement uncertainties
# ----------------------------------------------------------------------------
COUPLING_FUNCTIONS = {
    "newell_dphi_dt": "Newell et al. (2007) dPhi/dt = V^4/3 B_T^2/3 sin^8/3(theta/2) [(km/s)^4/3 nT^2/3]",
    "akasofu_epsilon_gw": "Perreault & Akasofu (1978) epsilon = (4 pi/mu0) V B^2 sin^4(theta/2) l0^2, l0 = 7 R_E [GW]",
    "vbs_mv_m": "Rectified dawn-dusk electric field V Bs, Bs = max(0, -Bz GSM) [mV/m]",
    "dynamic_pressure_npa": "Proton dynamic pressure m_p n V^2 [nPa]",
    "proton_beta": "Proton plasma beta 2 mu0 n k T / B^2 (protons only; OMNI's beta adds alphas and electrons)",
    "alfven_mach": "Alfven Mach number V / V_A, V_A = B / sqrt(mu0 m_p n) (proton mass density; OMNI's adds 4 % alphas)",
}


def coupling_with_errors(field: pd.DataFrame, plasma: pd.DataFrame) -> Dict[str, Any]:
    """
    Coupling functions on every plasma sample (field averaged over the sample, rotated from
    GSE to GSM) and their interval means, with 1-sigma uncertainties propagated to first
    order from the archive's per-sample uncertainties of the bulk speed and density where it
    gives them (WIND SWE non-linear fits): relative errors (4/3) sV/V for dPhi/dt, sV/V for
    epsilon and V Bs, sqrt((sn/n)^2 + (2 sV/V)^2) for the dynamic pressure,
    sqrt((sn/n)^2 + (sT/T)^2) for the proton beta (sT/T = 2 sW/W from the thermal speed) and
    sqrt((sV/V)^2 + (sn/2n)^2) for the Alfven Mach number. Field uncertainties are not in the
    archive and are not included. Each mean carries two
    uncertainties: the propagated measurement error sqrt(sum s_i^2) / N (independent sample
    errors) and the 95 % sampling interval of the mean from the effective sample size.
    """
    from helios.core.coordinates import gse_to_gsm
    from helios.core.science import SpaceWeatherPhysics as swp
    from helios.core.statistics import mean_interval

    plasma = plasma.dropna(subset=["vx", "vy", "vz"])
    if len(plasma) < 3:
        raise ValueError(f"Only {len(plasma)} plasma samples; at least 3 are needed.")
    b = field_at_plasma_times(field, plasma)
    ok = np.all(np.isfinite(b), axis=1)
    plasma, b = plasma[ok], b[ok]
    if len(plasma) < 3:
        raise ValueError("Fewer than 3 plasma samples have magnetic field data.")
    _, by, bz = gse_to_gsm(plasma.index, b[:, 0], b[:, 1], b[:, 2])
    btot = np.linalg.norm(b, axis=1)
    v = np.sqrt(plasma["vx"] ** 2 + plasma["vy"] ** 2 + plasma["vz"] ** 2).to_numpy(float)
    n = plasma["n"].to_numpy(float)
    sv = plasma["sigma_v"].to_numpy(float) if "sigma_v" in plasma else np.full(len(v), np.nan)
    sn = plasma["sigma_n"].to_numpy(float) if "sigma_n" in plasma else np.full(len(v), np.nan)
    t_k = plasma["t"].to_numpy(float) if "t" in plasma else np.full(len(v), np.nan)
    st = plasma["sigma_t"].to_numpy(float) if "sigma_t" in plasma else np.full(len(v), np.nan)
    rv, rn, rt = sv / v, sn / n, st / t_k
    n_m3, b_t = n * 1e6, btot * 1e-9

    values = {
        "newell_dphi_dt": np.array([swp.newell_coupling(vi, y, z) for vi, y, z in zip(v, by, bz)]),
        "akasofu_epsilon_gw": np.array([swp.akasofu_epsilon(vi, bt, y, z) for vi, bt, y, z in zip(v, btot, by, bz)]),
        "vbs_mv_m": v * np.maximum(0.0, -bz) * 1e-3,
        "dynamic_pressure_npa": PROTON_MASS_KG * n * 1e6 * (v * 1e3) ** 2 * 1e9,
        "proton_beta": 2.0 * MU0 * n_m3 * BOLTZMANN_J_K * t_k / b_t ** 2,
        "alfven_mach": v * 1e3 * np.sqrt(MU0 * PROTON_MASS_KG * n_m3) / b_t,
    }
    rel = {"newell_dphi_dt": 4.0 / 3.0 * rv, "akasofu_epsilon_gw": rv, "vbs_mv_m": rv,
           "dynamic_pressure_npa": np.sqrt(rn ** 2 + (2.0 * rv) ** 2),
           "proton_beta": np.sqrt(rn ** 2 + rt ** 2), "alfven_mach": np.sqrt(rv ** 2 + (rn / 2.0) ** 2)}
    out: Dict[str, Any] = {}
    for key, val in values.items():
        sig = np.abs(val) * rel[key]
        stats = mean_interval(val)
        valid = np.isfinite(val)  # e.g. no temperature for a sample: no beta
        have = np.isfinite(sig)
        out[key] = {
            "definition": COUPLING_FUNCTIONS[key],
            "mean": stats["mean"],
            "measurement_sigma_of_mean": (float(np.sqrt(np.sum(sig[valid] ** 2)) / valid.sum())
                                          if valid.any() and have[valid].all() else None),
            "sampling_ci95_of_mean": list(stats["ci95"]) if stats["ci95"] else None,
            "n_eff": stats["n_eff"],
            "median_relative_sigma": float(np.median(rel[key][have])) if have.any() else None,
            "series": [None if not np.isfinite(x) else float(x) for x in val],
            "series_sigma": [None if not np.isfinite(x) else float(x) for x in sig],
        }
    return {
        "n_samples": int(len(plasma)),
        "time_tags": [t.strftime("%Y-%m-%d %H:%M:%S") for t in plasma.index],
        "uncertainties_available": bool(np.isfinite(rv).all()),
        "functions": out,
        "method": ("Coupling functions per plasma sample (field averaged over the sample, GSE->GSM); "
                   "first-order propagation of the archive's 1-sigma speed and density uncertainties; "
                   "sampling interval of the mean from the lag-1 effective sample size"),
        "note": ("The measurement error of a mean is usually far smaller than its sampling interval: the "
                 "variability of the solar wind, not the instrument, limits interval averages."),
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


def _upstream_waves(n_cm3: float, t_k: Optional[float], bmag: float, tbn_deg: float) -> Dict[str, Optional[float]]:
    """
    Alfven speed (protons), sound speed with the OMNI definition C_s = 0.12 sqrt(T + 1.28e5 K)
    km/s (electron temperature not measured), and the fast magnetosonic speed along n.
    """
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
                  seed: int = 1, exclude_after_minutes: Optional[float] = None) -> Dict[str, Any]:
    """
    Normals, theta_Bn, shock speed, jump ratios and upstream Mach numbers of a shock at
    `shock_time` from field and plasma frames (GSE). Averaging windows are taken on each
    side, `exclude_minutes` away from the shock (`exclude_after_minutes` after it, when given:
    the IPShocks database leaves out 1 min before and 2 min after). Uncertainties come from `n_draws` Monte
    Carlo draws of the window means within their standard errors.
    """
    t_guess = _utc(shock_time)
    t0 = refine_shock_time(field, t_guess) if refine else None
    t0 = t0 if t0 is not None else t_guess

    before = (-exclude_minutes - upstream_minutes, -exclude_minutes)
    gap_after = exclude_minutes if exclude_after_minutes is None else exclude_after_minutes
    after = (gap_after, gap_after + downstream_minutes)
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

    # |B| of each side is the mean of the sample magnitudes, as in the IPShocks database: the
    # magnitude of the mean vector drops where the field turns within a window (ACE, 5 Aug
    # 2000: 2.1 against 9.7 nT downstream), which made fast shocks read as slow ones.
    mb, ma_ = (float(np.nanmean(np.linalg.norm(_window(field, t0, *w)[fcols].to_numpy(dtype=float), axis=1)))
               for w in (before, after))
    shock_type = classify_shock(pb[3], pa[3], mb, ma_)
    # Upstream is the side the shock propagates into: before the shock in time for a forward
    # shock, after it for a reverse shock.
    if shock_type.endswith("F"):
        (b1, b1e, b2, b2e, p1, p1e, p2, p2e, m1, m2) = (bb, bb_e, ba, ba_e, pb, pb_e, pa, pa_e, mb, ma_)
        k_up, k_dn = (kbb, kpb), (kba, kpa)
    else:
        (b1, b1e, b2, b2e, p1, p1e, p2, p2e, m1, m2) = (ba, ba_e, bb, bb_e, pa, pa_e, pb, pb_e, ma_, mb)
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
        waves = _upstream_waves(p1[3], p1[4], m1, tbn)
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

    def side(b, be, bm, p, pe, k):
        return {"B_gse_nT": b.tolist(), "B_sigma_nT": be.tolist(), "B_magnitude_nT": bm,
                "V_gse_kms": p[:3].tolist(), "V_sigma_kms": pe[:3].tolist(),
                "density_cm3": float(p[3]), "temperature_K": float(p[4]) if np.isfinite(p[4]) else None,
                "field_samples": k[0], "plasma_samples": k[1]}

    waves = _upstream_waves(p1[3], p1[4], m1, best[PREFERRED_METHOD][1] if PREFERRED_METHOD in best else 90.0)
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
        "upstream": side(b1, b1e, m1, p1, p1e, k_up),
        "downstream": side(b2, b2e, m2, p2, p2e, k_dn),
        "density_ratio": density_ratio,
        "field_ratio": m2 / m1,
        "upstream_waves_kms": waves,
        "methods": methods,
        "preferred_method": PREFERRED_METHOD if PREFERRED_METHOD in methods else next(iter(methods), None),
        "warnings": warnings,
        "conventions": ("GSE. Normal points into the upstream plasma (n . dV > 0); shock speed along n in the "
                        "spacecraft frame from mass flux conservation (negative for a reverse shock, which moves "
                        "away from the Sun while n points sunward; the IPShocks database lists its magnitude); "
                        "theta_Bn from the upstream mean field; |B| the mean of the sample magnitudes. "
                        "Sound speed C_s = 0.12 sqrt(T + 1.28e5 K) km/s (OMNI definition, electrons not measured)."),
        "references": [
            "Schwartz, S. J. (1998), Shock and discontinuity normals, Mach numbers, and related parameters, "
            "ISSI Scientific Report SR-001, ch. 10",
            "Abraham-Shrauner, B. (1972), J. Geophys. Res. 77, 736, doi:10.1029/JA077i004p00736",
            "Harvard-Smithsonian CfA Interplanetary Shock Database, https://www.cfa.harvard.edu/shocks/",
        ],
    }


# ----------------------------------------------------------------------------
# Multi-spacecraft timing
# ----------------------------------------------------------------------------
def position_at(position: Optional[pd.DataFrame], t: pd.Timestamp) -> Optional[np.ndarray]:
    """GSE position (km) at time t, linearly interpolated; None without position data."""
    if position is None or position.empty:
        return None
    secs = (position.index - t).total_seconds().to_numpy()
    if secs[0] > 3600 or secs[-1] < -3600:
        return None  # no sample within an hour of t
    return np.array([float(np.interp(0.0, secs, position[c].to_numpy(dtype=float))) for c in ("x", "y", "z")])


def predict_arrival(normal, speed_kms: float, t_ref: pd.Timestamp, r_ref_km, r_km) -> Dict[str, Any]:
    """
    Arrival time of a planar shock with unit normal n moving at V_sh along n (spacecraft
    frame) at a spacecraft at r, given its arrival at r_ref: t = t_ref + n . (r - r_ref) / V_sh.
    """
    n = np.asarray(normal, dtype=float)
    dr = np.asarray(r_km, dtype=float) - np.asarray(r_ref_km, dtype=float)
    dt = float(np.dot(n, dr)) / speed_kms
    return {"delay_s": dt, "predicted_time": t_ref + pd.Timedelta(seconds=dt),
            "baseline_km": dr.tolist(), "baseline_along_normal_km": float(np.dot(n, dr))}


def timing_comparison(normal, speed_kms: float, t_ref: pd.Timestamp, r_ref_km,
                      target_field: Optional[pd.DataFrame], r_target_km,
                      search_minutes: float = 20.0) -> Dict[str, Any]:
    """
    Predicted arrival at a second spacecraft and the observed one (largest |B| jump within
    `search_minutes` of the prediction), with the residual and the speed along n that the
    observed delay implies, V = n . dr / dt.
    """
    pred = predict_arrival(normal, speed_kms, t_ref, r_ref_km, r_target_km)
    observed = refine_shock_time(target_field, pred["predicted_time"], search_minutes=search_minutes)
    out = {
        "predicted_time": pred["predicted_time"].strftime("%Y-%m-%d %H:%M:%S"),
        "predicted_delay_s": pred["delay_s"],
        "baseline_gse_km": pred["baseline_km"],
        "baseline_along_normal_km": pred["baseline_along_normal_km"],
        "observed_time": None, "observed_delay_s": None, "residual_s": None, "implied_speed_kms": None,
    }
    if observed is not None:
        dt_obs = (observed - t_ref).total_seconds()
        out.update({"observed_time": observed.strftime("%Y-%m-%d %H:%M:%S"), "observed_delay_s": dt_obs,
                    "residual_s": dt_obs - pred["delay_s"],
                    "implied_speed_kms": (pred["baseline_along_normal_km"] / dt_obs) if abs(dt_obs) >= 30 else None})
    return out


# ----------------------------------------------------------------------------
# Magnetic cloud: force-free (Lundquist) flux rope fit
# ----------------------------------------------------------------------------
BESSEL_J0_ZERO = 2.404825557695773


def _bessel_j(order: int, x: np.ndarray) -> np.ndarray:
    """J0 or J1 from their power series; accurate to 1e-12 for 0 <= x <= 2.41 (inside the rope)."""
    x = np.asarray(x, dtype=float)
    term = np.ones_like(x) if order == 0 else x / 2.0
    total = term.copy()
    q = -(x / 2.0) ** 2
    for k in range(1, 30):
        term = term * q / (k * (k + order))
        total = total + term
    return total


def _axis(phi_deg: float, theta_deg: float) -> np.ndarray:
    p, t = math.radians(phi_deg), math.radians(theta_deg)
    return np.array([math.cos(t) * math.cos(p), math.cos(t) * math.sin(p), math.sin(t)])


def lundquist_field(t_hours: np.ndarray, phi_deg: float, theta_deg: float, y0: float, t0_hours: float,
                    handedness: int, duration_hours: float, speed_kms: float, b0: float = 1.0) -> np.ndarray:
    """
    Field (N x 3, GSE) seen by a spacecraft crossing a Lundquist flux rope that moves
    radially (along -X_GSE) at `speed_kms`: B = B0 [J0(a r) e_axis + H J1(a r) e_phi], with
    a R0 = 2.4048, so the field is azimuthal at the boundary (Lepping et al. 1990). The axis
    has GSE longitude phi and latitude theta; y0 is the closest approach in units of R0
    (signed), t0 the time of closest approach, and R0 follows from the crossing duration.
    """
    a = _axis(phi_deg, theta_deg)
    xp = np.array([1.0, 0.0, 0.0]) - a[0] * a  # path direction projected perpendicular to the axis
    s = float(np.linalg.norm(xp))
    if s < 1e-6 or abs(y0) >= 1.0:
        return np.full((len(t_hours), 3), np.nan)
    xp /= s
    c = np.cross(xp, a)  # closest-approach direction; sign as Y0 in the WIND MFI cloud table
    r0 = speed_kms * duration_hours * 3600.0 * s / (2.0 * math.sqrt(1.0 - y0 * y0))
    d = speed_kms * (np.asarray(t_hours) - t0_hours) * 3600.0 * s  # distance along the projected path (km)
    rvec = y0 * r0 * c[None, :] + d[:, None] * xp[None, :]
    rho = np.linalg.norm(rvec, axis=1)
    arg = np.clip(BESSEL_J0_ZERO * rho / r0, 0.0, BESSEL_J0_ZERO)
    ephi = np.cross(a[None, :], rvec / np.where(rho > 0, rho, 1.0)[:, None])
    return b0 * (_bessel_j(0, arg)[:, None] * a[None, :] + handedness * _bessel_j(1, arg)[:, None] * ephi)


def _nelder_mead(f: Callable, x0: np.ndarray, steps: np.ndarray, iters: int = 400) -> Tuple[np.ndarray, float]:
    """Minimal Nelder-Mead simplex minimiser (numpy only)."""
    x0 = np.asarray(x0, dtype=float)
    pts = [x0] + [x0 + np.eye(len(x0))[i] * steps[i] for i in range(len(x0))]
    vals = [f(p) for p in pts]
    for _ in range(iters):
        order = np.argsort(vals)
        pts, vals = [pts[i] for i in order], [vals[i] for i in order]
        centroid = np.mean(pts[:-1], axis=0)
        xr = centroid + (centroid - pts[-1])
        fr = f(xr)
        if fr < vals[0]:
            xe = centroid + 2.0 * (centroid - pts[-1])
            fe = f(xe)
            pts[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = xr, fr
        else:
            xc = centroid + 0.5 * (pts[-1] - centroid)
            fc = f(xc)
            if fc < vals[-1]:
                pts[-1], vals[-1] = xc, fc
            else:
                pts = [pts[0]] + [pts[0] + 0.5 * (p - pts[0]) for p in pts[1:]]
                vals = [vals[0]] + [f(p) for p in pts[1:]]
        if abs(vals[-1] - vals[0]) < 1e-10:
            break
    i = int(np.argmin(vals))
    return pts[i], float(vals[i])


def fit_flux_rope(field: pd.DataFrame, plasma: Optional[pd.DataFrame], start, end,
                  average_minutes: int = 30, speed_kms: Optional[float] = None) -> Dict[str, Any]:
    """
    Least-squares fit of the Lundquist flux rope to a magnetic cloud between `start` and
    `end` (the cloud boundaries), as in Lepping et al. (1990): the model is fitted to the
    field directions (unit vectors of `average_minutes` means) for the axis longitude and
    latitude, the closest approach and its time, for both signs of the handedness; B0 then
    follows from the full vectors. R0 comes from the duration and the mean solar wind speed
    in the cloud. chi_R = sqrt(sum |b_obs - b_model|^2 / (3N - 5)) on the unit vectors and
    the axial flux 1.36 B0 R0^2 are defined as in the WIND MFI magnetic cloud table.
    The 1-sigma uncertainties follow from chi_R, the closest approach and the cone angle
    through the error study of Lepping et al. (2003) (helios.core.lepping_errors).
    """
    t_start, t_end = _utc(start), _utc(end)
    duration = (t_end - t_start).total_seconds() / 3600.0
    if duration <= 1.0:
        raise ValueError("The cloud interval must be longer than one hour.")
    sub = field[(field.index >= t_start) & (field.index < t_end)][["bx", "by", "bz"]]
    avg = sub.resample(f"{average_minutes}min", origin=t_start).mean().dropna()
    if len(avg) < 6:
        raise ValueError(f"Only {len(avg)} field averages in the interval; at least 6 are needed.")
    if speed_kms is None:
        p = plasma[(plasma.index >= t_start) & (plasma.index < t_end)] if plasma is not None else pd.DataFrame()
        speed_kms = float(np.sqrt(p["vx"] ** 2 + p["vy"] ** 2 + p["vz"] ** 2).mean()) if not p.empty else float("nan")
        if not np.isfinite(speed_kms):
            raise ValueError("No solar wind speed for the cloud interval: give speed_kms.")
    th = ((avg.index - t_start).total_seconds().to_numpy() + average_minutes * 30.0) / 3600.0  # bin centres (h)
    bobs = avg.to_numpy(dtype=float)
    bhat = bobs / np.linalg.norm(bobs, axis=1)[:, None]
    n = len(bhat)

    def cost(x, h):
        phi, theta, y0, t0 = x
        if abs(theta) > 90 or abs(y0) >= 0.99 or not (0.25 * duration <= t0 <= 0.75 * duration):
            return 1e9
        m = lundquist_field(th, phi, theta, y0, t0, h, duration, speed_kms)
        mh = m / np.linalg.norm(m, axis=1)[:, None]
        val = float(np.sum((bhat - mh) ** 2))
        return val if np.isfinite(val) else 1e9

    best = None
    for h in (1, -1):
        seeds = []
        for phi in range(0, 360, 15):
            for theta in range(-75, 90, 15):
                for y0 in (-0.6, -0.2, 0.2, 0.6):
                    x0 = (phi, theta, y0, duration / 2)
                    seeds.append((cost(x0, h), x0))
        seeds.sort(key=lambda s: s[0])
        for _, x0 in seeds[:4]:
            x, v = _nelder_mead(lambda x: cost(x, h), np.array(x0, dtype=float),
                                np.array([10.0, 10.0, 0.2, 0.05 * duration]))
            if best is None or v < best[2]:
                best = (h, x, v)
    h, (phi, theta, y0, t0), chi2 = best
    unit = lundquist_field(th, phi, theta, y0, t0, h, duration, speed_kms)
    b0 = float(np.sum(bobs * unit) / np.sum(unit * unit))
    if b0 < 0:  # reverse the axis so that it points along the axial field (B0 > 0)
        b0, phi, theta, y0 = -b0, phi + 180.0, -theta, -y0
    phi = phi % 360.0
    a = _axis(phi, theta)
    s = float(np.linalg.norm(np.array([1.0, 0.0, 0.0]) - a[0] * a))
    r0_km = speed_kms * duration * 3600.0 * s / (2.0 * math.sqrt(1.0 - y0 * y0))
    flux_wb = 1.36 * b0 * 1e-9 * (r0_km * 1e3) ** 2  # 2 pi B0 R0^2 J1(x0)/x0
    chi_r = math.sqrt(chi2 / max(1, 3 * n - 5))
    return {
        "start": t_start.strftime("%Y-%m-%d %H:%M"),
        "end": t_end.strftime("%Y-%m-%d %H:%M"),
        "duration_hours": duration,
        "average_minutes": average_minutes,
        "n_averages": n,
        "speed_kms": speed_kms,
        "axis_longitude_deg": float(phi),
        "axis_latitude_deg": float(theta),
        "axis_gse": a.tolist(),
        "b0_nT": b0,
        "handedness": "R" if h > 0 else "L",
        "closest_approach_percent": float(100.0 * y0),
        "closest_approach_time": (t_start + pd.Timedelta(hours=float(t0))).strftime("%Y-%m-%d %H:%M"),
        "diameter_au": 2.0 * r0_km / AU_KM,
        "axial_flux_1e20_Mx": flux_wb * 1e8 / 1e20,
        "chi_r": chi_r,
        "uncertainties": lepping_uncertainties(b0, chi_r, 100.0 * y0, phi, theta),
        "model": {"time_tags": [(t_start + pd.Timedelta(hours=float(x))).strftime("%Y-%m-%d %H:%M") for x in th],
                  "observed_gse_nT": bobs.round(3).tolist(), "model_gse_nT": (b0 * unit).round(3).tolist()},
        "conventions": ("GSE. The axis points along the axial (core) field, so B0 > 0; closest approach in % of the "
                        "radius; R0 from duration and speed, the cloud moving radially along -X."),
        "references": ["Lepping, R. P., Jones, J. A. & Burlaga, L. F. (1990), J. Geophys. Res. 95, 11957, "
                       "doi:10.1029/JA095iA08p11957",
                       "Burlaga, L. F. (1988), J. Geophys. Res. 93, 7217, doi:10.1029/JA093iA07p07217",
                       "Lepping, R. P., Berdichevsky, D. B. & Ferguson, T. J. (2003), J. Geophys. Res. 108(A10), "
                       "1356, doi:10.1029/2002JA009657 (fit-parameter errors)",
                       "Lepping, R. P. et al. (2006), Ann. Geophys. 24, 215, doi:10.5194/angeo-24-215-2006",
                       "WIND MFI magnetic cloud table, https://wind.nasa.gov/mfi/mag_cloud_S1.html"],
    }


# ----------------------------------------------------------------------------
# Automatic magnetic cloud identification (Lepping, Wu & Berdichevsky 2005)
# ----------------------------------------------------------------------------
# Identification test parameters of Lepping et al. (2005, Ann. Geophys. 23, 2687), Table 4,
# and the large-scale smoothness limit of their Sect. 4.3.
MC_CRITERIA = {
    "loose": {"window_minutes": 25, "beta_max": 0.3, "theta_chi2_max": 500.0, "min_hours": 8.0,
              "b_min_nt": 7.0, "vth_max_kms": 30.0, "vth_central_third": True, "dtheta_min_deg": 35.0,
              "chi_m_over_b_max": 0.42, "bridge_minutes": 25},
    "strict": {"window_minutes": 30, "beta_max": 0.3, "theta_chi2_max": 450.0, "min_hours": 8.0,
               "b_min_nt": 8.0, "vth_max_kms": 30.0, "vth_central_third": False, "dtheta_min_deg": 45.0,
               "chi_m_over_b_max": 0.42, "bridge_minutes": 30},
}
# Windows need plasma for at least this fraction of their minutes (WIND SWE has gaps).
MC_PLASMA_COVERAGE = 0.5


def _quadratic_residual_ss(y: np.ndarray, length: int) -> np.ndarray:
    """Sum of squared residuals of a least-squares quadratic fit in every window of `length` samples."""
    x = np.arange(length, dtype=float)
    X = np.column_stack([np.ones(length), x, x * x])
    resid = np.eye(length) - X @ np.linalg.pinv(X)  # (I - H): residual operator of the fit
    win = np.lib.stride_tricks.sliding_window_view(y, length)
    r = win @ resid.T
    return (r * r).sum(axis=1)


def detect_magnetic_clouds(frame: pd.DataFrame, criteria: str = "loose") -> Dict[str, Any]:
    """
    Magnetic cloud candidates in 1-minute field (GSE) and proton plasma data with the
    scheme of Lepping et al. (2005). Over running windows of 25 min (30 min for the strict
    set) stepped by 1 min, the mean proton beta must be <= 0.3 and the chi^2 of a
    quadratic fit to the field latitude theta_B (deg^2, 1-min values) <= 500 (450); runs of
    such windows lasting >= 8 h form a candidate region (failing stretches no longer than one
    window are bridged, and windows need plasma data for half their minutes). A region is kept when the mean
    |B| >= 7 nT (8), the mean proton thermal speed over its central third (whole region)
    <= 30 km/s and theta_B spans >= 35 deg (45). The large-scale test fits a quadratic to
    each component of the 15-min averages; chi_M / <B> <= 0.42 with
    chi_M^2 = sum_j sum_n (B_jn - fit_jn)^2 / N.
    `frame` needs bx_gse, by_gse, bz_gse (nT), density (cm^-3) and temperature (K).
    """
    if criteria not in MC_CRITERIA:
        raise ValueError(f"criteria must be one of {', '.join(MC_CRITERIA)}.")
    c = MC_CRITERIA[criteria]
    need = ["bx_gse", "by_gse", "bz_gse", "density", "temperature"]
    missing = [k for k in need if k not in frame.columns]
    if missing:
        raise ValueError(f"Missing columns for magnetic cloud identification: {', '.join(missing)}.")
    df = frame[need].copy()
    df.index = pd.DatetimeIndex(df.index)
    df = df[~df.index.duplicated()].sort_index()
    if len(df) < 2:
        raise ValueError("Not enough data for magnetic cloud identification.")
    df = df.resample("1min").mean()
    # WIND SWE spectra come every 92 s, so some minutes have field but no plasma: bridge gaps of up to 5 min.
    df = df.interpolate(limit=5, limit_area="inside")
    bmag = np.sqrt(df["bx_gse"] ** 2 + df["by_gse"] ** 2 + df["bz_gse"] ** 2)
    theta = np.degrees(np.arcsin(np.clip(df["bz_gse"] / bmag, -1.0, 1.0)))
    beta = (df["density"] * 1e6 * BOLTZMANN_J_K * df["temperature"]) / ((bmag * 1e-9) ** 2 / (2 * MU0))
    vth = np.sqrt(2.0 * BOLTZMANN_J_K * df["temperature"] / PROTON_MASS_KG) / 1e3  # km/s

    L = int(c["window_minutes"])
    if len(df) < L:
        raise ValueError(f"At least {L} minutes of data are needed.")
    th = theta.to_numpy(float)
    be = beta.to_numpy(float)
    field_ok = np.lib.stride_tricks.sliding_window_view(np.isfinite(th), L).all(axis=1)
    chi2 = np.where(field_ok, _quadratic_residual_ss(np.nan_to_num(th), L), np.inf)
    bwin = np.lib.stride_tricks.sliding_window_view(be, L)
    nb = np.isfinite(bwin).sum(axis=1)
    beta_mean = np.where(nb >= MC_PLASMA_COVERAGE * L, np.nansum(bwin, axis=1) / np.maximum(nb, 1), np.inf)
    ok = (beta_mean <= c["beta_max"]) & (chi2 <= c["theta_chi2_max"])
    # A single noisy minute fails every window that contains it; failing runs no longer
    # than one window inside a passing stretch do not end the region (Lepping et al. give
    # no rule for this; without it most 1-min WIND clouds break into pieces shorter than 8 h).
    e2 = np.diff(np.concatenate([[1], ok.astype(int), [1]]))
    for a, b in zip(np.where(e2 == -1)[0], np.where(e2 == 1)[0]):
        if 0 < a and b < len(ok) and b - a <= c["bridge_minutes"]:
            ok[a:b] = True

    # Runs of consecutive passing windows; a run of windows i0..i1 covers minutes i0 .. i1 + L - 1.
    regions = []
    edges = np.diff(np.concatenate([[0], ok.astype(int), [0]]))
    for i0, i1 in zip(np.where(edges == 1)[0], np.where(edges == -1)[0] - 1):
        t0, t1 = df.index[i0], df.index[i1 + L - 1] + pd.Timedelta(minutes=1)
        hours = (t1 - t0).total_seconds() / 3600.0
        if hours < c["min_hours"]:
            continue
        sl = slice(i0, i1 + L)
        b_mean = float(np.nanmean(bmag.iloc[sl]))
        v = vth.iloc[sl].to_numpy(float)
        v_used = v[len(v) // 3: 2 * len(v) // 3] if c["vth_central_third"] else v
        vth_mean = float(np.nanmean(v_used))
        dtheta = float(np.nanmax(th[sl]) - np.nanmin(th[sl]))
        avg = df[["bx_gse", "by_gse", "bz_gse"]].iloc[sl].resample("15min", origin=t0).mean().dropna()
        chi_m_over_b = None
        if len(avg) >= 4:
            x = (avg.index - avg.index[0]).total_seconds().to_numpy() / 3600.0
            chi_sq = 0.0
            for col in ("bx_gse", "by_gse", "bz_gse"):
                y = avg[col].to_numpy(float)
                fit = np.polyval(np.polyfit(x, y, 2), x)
                chi_sq += float(np.mean((y - fit) ** 2))
            chi_m_over_b = math.sqrt(chi_sq) / b_mean if b_mean > 0 else None
        tests = {
            "mean_b": b_mean >= c["b_min_nt"],
            "thermal_speed": vth_mean <= c["vth_max_kms"],
            "latitude_change": dtheta >= c["dtheta_min_deg"],
            "large_scale_smoothness": chi_m_over_b is not None and chi_m_over_b <= c["chi_m_over_b_max"],
        }
        bz = df["bz_gse"].iloc[sl].to_numpy(float)
        half = len(bz) // 2
        regions.append({
            "start": t0.strftime("%Y-%m-%d %H:%M"), "end": t1.strftime("%Y-%m-%d %H:%M"),
            "duration_hours": round(hours, 2),
            "mean_b_nt": round(b_mean, 2), "mean_beta": round(float(np.nanmean(be[sl])), 3),
            "mean_thermal_speed_kms": round(vth_mean, 1), "theta_b_range_deg": round(dtheta, 1),
            "chi_m_over_b": None if chi_m_over_b is None else round(chi_m_over_b, 3),
            "bz_sense": ("N=>S" if np.nanmean(bz[:half]) > 0 > np.nanmean(bz[half:]) else
                         "S=>N" if np.nanmean(bz[:half]) < 0 < np.nanmean(bz[half:]) else
                         "all N" if np.nanmean(bz) > 0 else "all S"),
            "tests": tests, "accepted": all(tests.values()),
        })
    return {
        "criteria": criteria, "parameters": dict(c),
        "candidates": regions,
        "accepted": [r for r in regions if r["accepted"]],
        "method": ("Automatic magnetic cloud identification, Lepping, Wu & Berdichevsky (2005), "
                   f"{criteria} identification test parameters (Table 4) and the chi_M/<B> smoothness test"),
        "notes": ("theta_B chi^2 is the sum of squared residuals (deg^2) of the quadratic fit to the 1-min "
                  "latitudes of each window. Thermal speed sqrt(2kT/m_p). Plasma gaps up to 5 min are "
                  "interpolated (WIND SWE spectra every 92 s); failing stretches no longer than one window "
                  "are bridged (an addition: the paper gives no rule). Lepping et al. found 88 % of the visually "
                  "identified WIND clouds with the loose set, and about twice as many cloud-like regions."),
        "references": ["Lepping, R. P., C.-C. Wu and D. B. Berdichevsky (2005), Automatic identification of "
                       "magnetic clouds and cloud-like regions at 1 AU: occurrence rate and other properties, Ann. Geophys. 23, 2687, "
                       "doi:10.5194/angeo-23-2687-2005"],
    }


# ----------------------------------------------------------------------------
# Superposed epoch analysis
# ----------------------------------------------------------------------------
SEA_PARAMETERS = ("sym_h", "asy_h", "ae", "al", "au", "kp", "hp30", "bz_gsm", "by_gsm", "bt", "speed", "density",
                  "temperature", "dynamic_pressure", "akasofu_gw")


def _bootstrap_bands(g: np.ndarray, n_boot: int, seed: int, min_events: int = 3) -> Dict[str, Any]:
    """
    95 % bootstrap confidence intervals of the per-bin mean (and, for grids of up to 300 000
    values, the median) of an events x bins grid, resampling whole events with replacement
    (percentile method). Bins with fewer than `min_events` events give None.
    """
    n_ev, n_bins = g.shape
    rng = np.random.default_rng(seed)
    # A resample is a multinomial count per event: its bin means are weighted means.
    counts = rng.multinomial(n_ev, np.full(n_ev, 1.0 / n_ev), size=int(n_boot)).astype(float)  # [B, E]
    finite = np.isfinite(g)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        means = (counts @ np.where(finite, g, 0.0)) / (counts @ finite)                      # [B, bins]
        arrays = {"mean": means}
        if n_ev * n_bins <= 300_000:
            idx = np.array([np.repeat(np.arange(n_ev), c.astype(int)) for c in counts])  # [B, E]
            # In blocks of resamples: g[idx] at once is B x events x bins (2 GB for 60 events
            # of 3 days at 1-minute bins).
            step = max(1, 10_000_000 // (n_ev * n_bins))
            arrays["median"] = np.concatenate([np.nanmedian(g[idx[i:i + step]], axis=1)
                                               for i in range(0, len(idx), step)])
        enough = finite.sum(axis=0) >= min_events
        out: Dict[str, Any] = {}
        for name, arr in arrays.items():
            lo, hi = np.nanpercentile(arr, 2.5, axis=0), np.nanpercentile(arr, 97.5, axis=0)
            out[f"{name}_ci95_low"] = [None if not (e and np.isfinite(v)) else round(float(v), 3) for v, e in zip(lo, enough)]
            out[f"{name}_ci95_high"] = [None if not (e and np.isfinite(v)) else round(float(v), 3) for v, e in zip(hi, enough)]
    out["n_bootstrap"] = int(n_boot)
    return out


def superposed_epoch(events: List[Tuple[pd.Timestamp, List[Dict[str, Any]]]], parameters: List[str],
                     before_hours: float, after_hours: float, cadence_minutes: int = 10,
                     n_bootstrap: int = 1000, seed: int = 1) -> Dict[str, Any]:
    """
    Superposed epoch analysis: each event's records are put on a common grid of epoch times
    (minutes from its onset, bins [k*cadence, (k+1)*cadence) labelled by their start) and the
    events are combined per bin into mean, median, quartiles and the number of events with
    data, with 95 % bootstrap confidence intervals of the mean and median (events resampled
    with replacement; bins with at least 3 events). Per event, the extremes of every
    parameter at the records' own cadence and their epoch times are listed.
    `events` = [(onset, records with "time_tag")].
    """
    if not events:
        raise ValueError("No events.")
    cad = int(cadence_minutes)
    # Bin edges on multiples of the cadence, so the onset is always a bin edge (a window of
    # 1.25 h at 10-min bins used to put epoch zero inside the bin labelled -5 min).
    offsets = np.arange(-math.ceil(round(before_hours * 60) / cad) * cad, int(round(after_hours * 60)), cad)
    grids = {p: np.full((len(events), len(offsets)), np.nan) for p in parameters}
    summaries = []
    for k, (onset, recs) in enumerate(events):
        onset = _utc(onset)
        summary: Dict[str, Any] = {"onset": onset.strftime("%Y-%m-%d %H:%M"), "n_records": len(recs)}
        if recs:
            t = pd.to_datetime([r["time_tag"] for r in recs], utc=True)
            epoch_min = ((t - onset).total_seconds() / 60.0).to_numpy()
            idx = np.floor((epoch_min - offsets[0]) / cad).astype(int)
            inside = (idx >= 0) & (idx < len(offsets))
            for p in parameters:
                vals = np.array([np.nan if r.get(p) is None else float(r[p]) for r in recs])
                ok = inside & np.isfinite(vals)
                if ok.any():
                    sums = np.bincount(idx[ok], weights=vals[ok], minlength=len(offsets))
                    counts = np.bincount(idx[ok], minlength=len(offsets))
                    grids[p][k] = np.where(counts > 0, sums / np.maximum(counts, 1), np.nan)
                    masked = np.where(ok, vals, np.nan)
                    i_min, i_max = int(np.nanargmin(masked)), int(np.nanargmax(masked))
                    summary[p] = {"min": vals[i_min], "min_epoch_hours": epoch_min[i_min] / 60.0,
                                  "max": vals[i_max], "max_epoch_hours": epoch_min[i_max] / 60.0}
        summaries.append(summary)

    def clean(a):
        return [None if not np.isfinite(v) else round(float(v), 3) for v in a]

    stats = {}
    for p in parameters:
        g = grids[p]
        n = np.sum(np.isfinite(g), axis=0)
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", RuntimeWarning)  # bins without any event give NaN, kept as null
            stats[p] = {"mean": clean(np.nanmean(g, axis=0)), "median": clean(np.nanmedian(g, axis=0)),
                        "q25": clean(np.nanpercentile(g, 25, axis=0)), "q75": clean(np.nanpercentile(g, 75, axis=0)),
                        "n_events": n.astype(int).tolist(),
                        "per_event": [clean(row) for row in g]}
        if n_bootstrap and len(events) >= 3:
            stats[p].update(_bootstrap_bands(g, n_bootstrap, seed))
    return {
        "epoch_hours": (offsets / 60.0).tolist(),
        "cadence_minutes": cad,
        "n_events": len(events),
        "parameters": list(parameters),
        "statistics": stats,
        "events": summaries,
        "method": ("Superposed epoch analysis: block means on a common epoch grid (bins labelled by their start), "
                   "then mean, median and quartiles over the events with data in each bin; 95 % confidence "
                   "intervals of the mean and median by bootstrap resampling of the events"),
    }
