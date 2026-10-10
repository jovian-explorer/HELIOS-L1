"""
Auroral oval dynamics and geomagnetic storm ring current (Dst) forecasting engine.
Implements the Starkov (1994) auroral boundary model and the Burton et al. (1975)
and O'Brien & McPherron (2000) Dst ring current models.
"""
import math
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional, Tuple

import numpy as np

from helios.core.coordinates import mlt_mlat_to_geo
from helios.core.statistics import skill_scores

# Starkov, G. V. (1994), Mathematical model of the auroral boundaries, Geomagn. Aeron. 34(3),
# 331-336, as tabulated by Sigernes et al. (2011, "Real time aurora oval forecasting -
# SvalTrack II", aurora.unis.no/doc/Sigernes_Oval.pdf, Table 2, read from the page image).
# Corrected geomagnetic colatitude of a boundary at magnetic local time t (hours):
#   theta = A0 + A1 cos[15(t + a1)] + A2 cos[15(2t + a2)] + A3 cos[15(3t + a3)]  (deg)
# and every A_i, a_i = b0 + b1 x + b2 x^2 + b3 x^3 with x = log10|AL| (AL in nT).
# Rows b0..b3; columns A0, A1, A2, A3, a1, a2, a3. Checked against the copy of the table
# in github.com/habtie-phys/auroraloval (data/starkov.mat): identical, signs included.
STARKOV_COEFFS = {
    "poleward": ((-0.07, -10.06, -4.44, -3.77, -6.61, 6.37, -4.48),
                 (24.54, 19.83, 7.47, 7.90, 10.17, -1.10, 10.16),
                 (-12.53, -9.33, -3.01, -4.73, -5.80, 0.34, -5.87),
                 (2.15, 1.24, 0.25, 0.91, 1.19, -0.38, 0.98)),
    "equatorward": ((1.61, -9.59, -12.07, -6.56, -2.22, -23.98, -20.07),
                    (23.21, 17.78, 17.49, 11.44, 1.50, 42.79, 36.67),
                    (-10.97, -7.20, -7.96, -6.73, -0.58, -26.96, -24.20),
                    (2.03, 0.96, 1.15, 1.31, 0.08, 5.56, 5.11)),
    "diffuse": ((3.44, -2.41, -0.74, -2.12, -1.68, 8.69, 8.61),
                (29.77, 7.89, 3.94, 3.24, -2.48, -20.73, -5.34),
                (-16.38, -4.32, -3.09, -1.67, 1.58, 13.03, -1.36),
                (3.35, 0.87, 0.72, 0.31, -0.28, -2.14, 0.76)),
}
# Starkov (1994, Geomagn. Aeron. 34(1), 101-103): |AL| = c0 + c1 Kp + c2 Kp^2 + c3 Kp^3 nT
# (Sigernes et al. 2011, Table 1).
STARKOV_KP_TO_AL = (18.0, -12.3, 27.2, -2.0)
# |AL| range used: 18 nT is Kp 0 and 652.5 nT is Kp 9 in the conversion above. Above
# about 780 nT the fitted equatorward boundary crosses the poleward one near 08-09 MLT
# (and the midnight equatorward boundary stops moving at ~60 deg), so the fits are not
# used beyond 750 nT: larger observed values are capped and the response says so.
STARKOV_AL_RANGE = (18.0, 750.0)

# Hemispheric power from Kp: Zhang & Paxton (2008, JASTP 70, 1231, doi:10.1016/j.jastp.2008.03.008)
# up to Kp 7, then the TIE-GCM/WACCM linear ramp to 300 GW at Kp 9.
HEMISPHERIC_POWER_SOURCE = ("Kp estimate: Zhang & Paxton (2008) HP = 16.82 exp(0.32 Kp) - 4.86 GW (Kp <= 7), "
                            "linear to 300 GW at Kp 9 above (TIE-GCM)")


class AuroralModel:
    """Predicts auroral oval equatorward and poleward boundaries and Dst evolution."""

    @staticmethod
    def kp_to_al(kp: float) -> float:
        """Starkov (1994) conversion of Kp to |AL| (nT)."""
        k = max(0.0, min(9.0, float(kp)))
        c0, c1, c2, c3 = STARKOV_KP_TO_AL
        return c0 + c1 * k + c2 * k ** 2 + c3 * k ** 3

    @staticmethod
    def starkov_latitude(al_nt: float, mlt_hours, boundary: str = "equatorward"):
        """
        Corrected geomagnetic latitude (deg) of a Starkov (1994) boundary ('poleward' or
        'equatorward' edge of the auroral oval, or 'diffuse' for the equatorward edge of
        the diffuse aurora) for |AL| in nT at magnetic local time(s) in hours.
        """
        b = np.asarray(STARKOV_COEFFS[boundary])
        lo, hi = STARKOV_AL_RANGE
        x = math.log10(min(hi, max(lo, abs(float(al_nt)))))
        a0, a1, a2, a3, p1, p2, p3 = np.array([1.0, x, x * x, x ** 3]) @ b
        t = np.asarray(mlt_hours, dtype=float)
        colat = (a0 + a1 * np.cos(np.radians(15.0 * (t + p1)))
                 + a2 * np.cos(np.radians(15.0 * (2.0 * t + p2)))
                 + a3 * np.cos(np.radians(15.0 * (3.0 * t + p3))))
        return 90.0 - colat

    @staticmethod
    def hemispheric_power_from_kp(kp: float) -> float:
        """
        Hemispheric power (GW) from Kp: Zhang & Paxton (2008) TIMED/GUVI relation
        HP = 16.82 exp(0.32 Kp) - 4.86 for Kp <= 7 (as quoted by Smith-Johnsen et al. 2018,
        eq. 1, and in TIE-GCM util.F hp_from_kp); above Kp 7 the TIE-GCM/WACCM linear
        ramp from 153.13 GW to 300 GW at Kp 9 (NOAA POES value) is used.
        """
        kp = max(0.0, min(9.0, float(kp)))
        if kp <= 7.0:
            return 16.82 * math.exp(0.32 * kp) - 4.86
        return 153.13 + (kp - 7.0) / 2.0 * (300.0 - 153.13)

    @classmethod
    def calculate_auroral_boundaries(cls, kp: float, bz_gsm: float = 0.0,
                                     al_nt: Optional[float] = None,
                                     al_source: Optional[str] = None) -> Dict[str, Any]:
        """
        Starkov (1994) auroral boundaries in corrected geomagnetic latitude at midnight,
        dawn, dusk and noon. Driven by |AL| when an observed value is given, otherwise by
        Kp converted to AL with Starkov's polynomial. Bz is reported but not used: the
        model depends on AL (or Kp) and magnetic local time only.
        """
        kp_eff = max(0.0, min(9.0, float(kp)))
        bz_eff = float(bz_gsm) if bz_gsm is not None else 0.0
        if al_nt is not None:
            al_raw, source = abs(float(al_nt)), al_source or "observed AL"
        else:
            al_raw, source = cls.kp_to_al(kp_eff), "Kp converted to AL (Starkov 1994)"
        lo, hi = STARKOV_AL_RANGE
        al_used = min(hi, max(lo, al_raw))

        def lat(boundary, mlt):
            return float(cls.starkov_latitude(al_used, mlt, boundary))

        eq_midnight = lat("equatorward", 0.0)
        eq_dawn, eq_dusk = lat("equatorward", 6.0), lat("equatorward", 18.0)
        mlt_grid = np.arange(0.0, 24.0, 1.0)
        profile = {"mlt_hours": mlt_grid.tolist()}
        for name in STARKOV_COEFFS:
            profile[f"{name}_lat"] = np.round(cls.starkov_latitude(al_used, mlt_grid, name), 2).tolist()

        # Visible Geographic Regions
        visible_regions = []
        if eq_midnight <= 42.0:
            visible_regions.extend(["Extreme Low Latitudes", "Northern India (Hanle/Ladakh)", "Southern US (Florida, Texas)", "Mediterranean", "Southern Australia", "South Africa"])
        elif eq_midnight <= 50.0:
            visible_regions.extend(["Mid Latitudes", "Central Europe (France, Germany, Poland)", "Northern US (New York, Midwest, Washington)", "Southern New Zealand"])
        elif eq_midnight <= 58.0:
            visible_regions.extend(["Sub-Auroral Zone", "United Kingdom", "Southern Scandinavia", "Southern Canada", "Tasmania"])
        else:
            visible_regions.extend(["Traditional Auroral Oval", "Alaska", "Northern Canada", "Norway, Sweden, Finland (Tromsø)", "Iceland", "Antarctica"])

        power_gw = round(cls.hemispheric_power_from_kp(kp_eff), 1)

        return {
            "model": "Starkov (1994)",
            "kp_used": round(kp_eff, 1),
            "bz_used": round(bz_eff, 1),
            "al_used_nt": round(al_used, 1),
            "al_source": source,
            "al_capped": al_used != al_raw,
            "equatorward_midnight_lat": round(eq_midnight, 1),
            "equatorward_flanks_lat": round((eq_dawn + eq_dusk) / 2.0, 1),
            "equatorward_dawn_lat": round(eq_dawn, 1),
            "equatorward_dusk_lat": round(eq_dusk, 1),
            "equatorward_noon_lat": round(lat("equatorward", 12.0), 1),
            "poleward_midnight_lat": round(lat("poleward", 0.0), 1),
            "diffuse_equatorward_midnight_lat": round(lat("diffuse", 0.0), 1),
            "latitude_system": "corrected geomagnetic latitude",
            "mlt_profile": profile,
            "hemispheric_power_gw": power_gw,
            "hemispheric_power_source": HEMISPHERIC_POWER_SOURCE,
            "visible_regions": visible_regions
        }

    @staticmethod
    def _boundary_by_longitude(lat: np.ndarray, lon: np.ndarray) -> List[Dict[str, float]]:
        """Sort a boundary that encircles the geographic pole by longitude and close it at -180/180 deg."""
        order = np.argsort(lon)
        lon, lat = lon[order], lat[order]
        # Latitude at the date line, interpolated between the last and the first point
        span = lon[0] + 360.0 - lon[-1]
        lat_dl = lat[-1] + (lat[0] - lat[-1]) * (180.0 - lon[-1]) / span if span > 0 else lat[0]
        pts = [{"lat": round(float(lat_dl), 2), "lon": -180.0}]
        pts += [{"lat": round(float(a), 2), "lon": round(float(o), 2)} for a, o in zip(lat, lon)]
        pts.append({"lat": round(float(lat_dl), 2), "lon": 180.0})
        return pts

    @classmethod
    def generate_auroral_oval_coordinates(cls, kp: float = 3.0, bz_gsm: float = -3.0, num_points: int = 96,
                                          al_nt: Optional[float] = None,
                                          when: Optional[datetime] = None) -> Dict[str, Any]:
        """
        Geographic (lat, lon) boundaries of the Starkov (1994) oval in both hemispheres at
        the UTC time `when` (default now). Magnetic local time and latitude are mapped to
        geographic coordinates with the IGRF centred dipole, which puts the boundaries
        within a degree or two of their corrected geomagnetic positions. The southern oval
        mirrors the northern boundaries in magnetic latitude. Each boundary is sorted by
        longitude from -180 to 180 deg so it can be drawn on a cylindrical map.
        """
        when = when or datetime.now(timezone.utc)
        lo, hi = STARKOV_AL_RANGE
        al = min(hi, max(lo, abs(float(al_nt)) if al_nt is not None else cls.kp_to_al(kp)))
        mlt = np.linspace(0.0, 24.0, num_points, endpoint=False)
        stamp = when.strftime("%Y-%m-%d %H:%M:%S")
        out: Dict[str, Any] = {"time_utc": stamp, "model": "Starkov (1994)", "al_used_nt": round(al, 1),
                               "mapping": "IGRF centred dipole; magnetic local time from the subsolar point"}
        for hemi, sign in (("north", 1.0), ("south", -1.0)):
            out[hemi] = {}
            for name in STARKOV_COEFFS:
                glat, glon = mlt_mlat_to_geo(stamp, mlt, sign * cls.starkov_latitude(al, mlt, name))
                out[hemi][name] = cls._boundary_by_longitude(np.asarray(glat), np.asarray(glon))
        return out

    # Ring current models: dDst*/dt = Q(VBs) - Dst*/tau, Dst = Dst* + b sqrt(P_dyn) - c,
    # VBs = V * max(0, -Bz) * 1e-3 in mV/m, Q in nT/h, tau in hours.
    # Burton et al. (1975): Q = d (VBs - 0.5) with d = -1.5e-3 nT m/(mV s) = -5.4 nT/h per mV/m,
    #   decay rate a = 3.6e-5 1/s (tau = 7.7 h), b = 0.20 nT/(eV cm^-3)^1/2 = 15.8 nT/nPa^1/2, c = 20 nT.
    # O'Brien & McPherron (2000): Q = -4.4 (VBs - 0.49), tau = 2.4 exp(9.74 / (4.69 + VBs)),
    #   b = 7.26 nT/nPa^1/2, c = 11 nT.
    DST_MODELS = {
        "burton": {"name": "Burton et al. (1975)", "ec": 0.5, "q_slope": -1.5e-3 * 3600.0,
                   "tau": lambda vbs: 1.0 / (3.6e-5 * 3600.0), "b": 0.20 * math.sqrt(1e-9 / 1.602176634e-19 / 1e6), "c": 20.0},
        "obrien": {"name": "O'Brien & McPherron (2000)", "ec": 0.49, "q_slope": -4.4,
                   "tau": lambda vbs: 2.4 * math.exp(9.74 / (4.69 + vbs)), "b": 7.26, "c": 11.0},
    }

    @staticmethod
    def dst_model_key(model: str) -> str:
        m = (model or "obrien").lower().replace("-", "_").replace(" ", "_")
        if m in ("burton", "burton1975", "bmr"):
            return "burton"
        if m in ("obrien", "obrien_mcpherron", "om", "obrien2000", "o'brien"):
            return "obrien"
        raise ValueError(f"Unknown Dst model '{model}' (use 'obrien' or 'burton')")

    @staticmethod
    def simulate_dst_evolution(telemetry: List[Dict[str, Any]], model: str = "obrien",
                               initial_dst: Optional[float] = None) -> List[Dict[str, Any]]:
        """
        Simulate Disturbance Storm Time (Dst) ring current evolution with the
        O'Brien & McPherron (2000) model (default) or Burton et al. (1975):
        d(Dst*)/dt = Q(t) - Dst* / tau,  Dst = Dst* + b sqrt(P_dyn) - c

        The time step is taken from consecutive time stamps (live data are 1-minute,
        7-day views and the offline model 5-minute); a fixed 5-minute step made 1-minute
        data inject and decay five times too fast. Each step uses the exact solution for
        constant Q and tau over the step, so long gaps cannot make the integration unstable.
        Missing speed/Bz means no injection during that step; the pressure correction
        uses the most recent valid P_dyn.

        initial_dst: an observed Dst (or SYM-H) at the first time stamp to start from;
        without it the ring current starts quiet (Dst* = 0). The model was previously a mix
        of the two papers (O'Brien-McPherron injection, Burton's fixed 7.7 h decay).
        Records carrying an observed SYM-H (OMNI) get it alongside the prediction.
        """
        if not telemetry:
            return []

        from datetime import datetime

        params = AuroralModel.DST_MODELS[AuroralModel.dst_model_key(model)]

        def parse_t(tag):
            try:
                return datetime.fromisoformat(str(tag).replace("Z", "").replace("T", " ")[:19])
            except (TypeError, ValueError):
                return None

        default_dt_hours = 5.0 / 60.0
        last_pdyn = next((r.get("dynamic_pressure") for r in telemetry
                          if r.get("dynamic_pressure") is not None and r.get("dynamic_pressure") > 0), None)

        def p_term(pdyn):
            return params["b"] * math.sqrt(pdyn) - params["c"] if pdyn is not None else 0.0

        dst_star = (float(initial_dst) - p_term(last_pdyn)) if initial_dst is not None else 0.0
        prev_t = None

        results = []
        for i, row in enumerate(telemetry):
            t = parse_t(row.get("time_tag"))
            if prev_t is not None and t is not None:
                # Equal stamps (e.g. after shifting L1 data to Earth) are no time step.
                dt_hours = max(0.0, (t - prev_t).total_seconds() / 3600.0)
            elif prev_t is not None:
                # Unreadable stamp: no step of its own, the next readable row steps from prev_t
                # (a default 5 min here counted that time twice).
                dt_hours = 0.0
            else:
                dt_hours = default_dt_hours
            if t is not None and (prev_t is None or t > prev_t):
                prev_t = t

            v = row.get("speed")
            bz = row.get("bz_gsm")
            pdyn = row.get("dynamic_pressure")
            if pdyn is not None and pdyn > 0:
                last_pdyn = pdyn

            vbs = v * max(0.0, -bz) * 1e-3 if (v is not None and bz is not None) else None
            if i > 0:
                vbs_eff = vbs if vbs is not None else 0.0
                q = params["q_slope"] * (vbs_eff - params["ec"]) if vbs_eff > params["ec"] else 0.0
                tau = params["tau"](vbs_eff)
                # Exact step of d(Dst*)/dt = Q - Dst*/tau with Q and tau constant over dt.
                decay = math.exp(-dt_hours / tau)
                dst_star = dst_star * decay + q * tau * (1.0 - decay)

            total_dst = round(dst_star + p_term(last_pdyn), 1)
            entry = {
                "time_tag": row.get("time_tag", ""),
                "dst_predicted_nt": total_dst,
                "ey_electric_field_mvm": round(-v * bz * 1e-3, 2) if (v is not None and bz is not None) else None,
                "storm_category": (
                    "Extreme Superstorm (Dst <= -300)" if total_dst <= -300 else
                    "Intense Storm (Dst <= -100)" if total_dst <= -100 else
                    "Moderate Storm (Dst <= -50)" if total_dst <= -50 else
                    "Weak / Quiet (Dst > -50)"
                )
            }
            if "sym_h" in row:
                entry["sym_h_observed_nt"] = row.get("sym_h")
            results.append(entry)

        return results

    @staticmethod
    def dst_step(dst: float, speed_kms: Optional[float], bz_gsm_nt: Optional[float],
                 pdyn_npa: Optional[float], dt_hours: float, model: str = "obrien") -> float:
        """Advance Dst by dt_hours with constant drivers (exact solution of the model ODE)."""
        params = AuroralModel.DST_MODELS[AuroralModel.dst_model_key(model)]
        p = params["b"] * math.sqrt(pdyn_npa) - params["c"] if pdyn_npa else 0.0
        vbs = speed_kms * max(0.0, -bz_gsm_nt) * 1e-3 if (speed_kms is not None and bz_gsm_nt is not None) else 0.0
        q = params["q_slope"] * (vbs - params["ec"]) if vbs > params["ec"] else 0.0
        tau = params["tau"](vbs)
        decay = math.exp(-dt_hours / tau)
        return (dst - p) * decay + q * tau * (1.0 - decay) + p

    @staticmethod
    def dst_skill(pairs: List[Tuple[Optional[float], Optional[float]]]) -> Dict[str, Any]:
        """
        Model-vs-observed statistics from time-ordered (predicted, observed) pairs: sample
        count, Pearson r, RMSE, mean bias (predicted - observed) and both minima, in nT, with
        95 % intervals of r, RMSE and bias that allow for the autocorrelation of the series
        (helios.core.statistics.skill_scores). Pairs with a missing value are skipped.
        """
        pts = [(float(p), float(o)) for p, o in pairs if p is not None and o is not None]
        n = len(pts)
        if n < 3:
            return {"n": n, "r": None, "rmse_nt": None, "bias_nt": None,
                    "min_predicted_nt": None, "min_observed_nt": None}
        pred = [p for p, _ in pts]
        obs = [o for _, o in pts]
        sk = skill_scores(pred, obs)
        ci = lambda pair, nd: [round(pair[0], nd), round(pair[1], nd)] if pair is not None else None
        return {
            "n": n,
            "r": round(sk["r"], 3) if sk["r"] is not None else None,
            "r_ci95": ci(sk["r_ci95"], 3),
            "rmse_nt": round(sk["rmse"], 1),
            "rmse_ci95_nt": ci(sk["rmse_ci95"], 1),
            "bias_nt": round(sk["bias"], 1),
            "bias_ci95_nt": ci(sk["bias_ci95"], 1),
            "n_eff": round(min(v for v in (sk["n_eff_r"], sk["n_eff_bias"], n) if v is not None), 1),
            "few_independent_samples": sk["few_independent_samples"],
            "min_predicted_nt": round(min(pred), 1),
            "min_observed_nt": round(min(obs), 1),
        }

    @staticmethod
    def compare_dst_models(telemetry: List[Dict[str, Any]], observed_key: str = "sym_h") -> Dict[str, Any]:
        """
        Run both ring current models over records that carry an observed index
        (OMNI SYM-H), starting each from the first observed value, and score them.
        """
        initial = next((r.get(observed_key) for r in telemetry if r.get(observed_key) is not None), None)
        out = {"observed_index": observed_key.upper().replace("_", "-"), "models": {}}
        for key in ("obrien", "burton"):
            sim = AuroralModel.simulate_dst_evolution(telemetry, model=key, initial_dst=initial)
            pairs = [(s["dst_predicted_nt"], r.get(observed_key)) for s, r in zip(sim, telemetry)]
            out["models"][key] = {
                "name": AuroralModel.DST_MODELS[key]["name"],
                "skill": AuroralModel.dst_skill(pairs),
                "series": [s["dst_predicted_nt"] for s in sim],
            }
        out["time_tags"] = [r.get("time_tag") for r in telemetry]
        out["observed"] = [r.get(observed_key) for r in telemetry]
        return out

    @staticmethod
    def hourly_pairs(sim: List[Dict[str, Any]], observed_hourly: List[Dict[str, Any]]) -> List[Tuple[float, float]]:
        """
        (model hourly mean, observed) pairs for hourly indices such as Kyoto Dst, whose
        time stamp marks the start of the averaged hour. Hours with less than half an hour
        of model output are skipped.
        """
        from collections import defaultdict
        buckets: Dict[str, List[float]] = defaultdict(list)
        for s in sim:
            tag, v = str(s.get("time_tag", "")), s.get("dst_predicted_nt")
            if len(tag) >= 13 and v is not None:
                buckets[tag[:13]].append(float(v))
        if not buckets:
            return []
        # Samples per hour for this cadence (e.g. 60 for 1-minute, 12 for 5-minute data).
        full = max(len(v) for v in buckets.values())
        pairs = []
        for o in observed_hourly:
            vals = buckets.get(str(o.get("time_tag", ""))[:13])
            if vals and len(vals) * 2 >= full and o.get("dst") is not None:
                pairs.append((sum(vals) / len(vals), float(o["dst"])))
        return pairs

    @staticmethod
    def observed_at(observed_hourly: List[Dict[str, Any]], time_tag: str) -> Optional[float]:
        """Observed hourly value for the hour containing time_tag, if present."""
        hour = str(time_tag or "")[:13]
        return next((float(o["dst"]) for o in observed_hourly if str(o.get("time_tag", ""))[:13] == hour), None)
