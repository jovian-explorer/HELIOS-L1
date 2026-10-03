"""
Auroral oval dynamics and geomagnetic storm ring current (Dst) forecasting engine.
Implements Feldstein/Starkov auroral oval empirical boundary models and
Burton et al. (1975) and O'Brien & McPherron (2000) Dst ring current models.
"""
import math
from typing import Dict, List, Any, Optional, Tuple

class AuroralModel:
    """Predicts auroral oval equatorward and poleward boundaries and Dst evolution."""

    @staticmethod
    def calculate_auroral_boundaries(kp: float, bz_gsm: float = 0.0) -> Dict[str, Any]:
        """
        Calculate equatorward and poleward auroral oval geomagnetic latitude boundaries
        at midnight, dawn, dusk, and noon based on the Starkov (1994) / Feldstein empirical models.
        """
        kp_eff = max(0.0, min(9.0, float(kp)))
        bz_eff = float(bz_gsm) if bz_gsm is not None else 0.0

        # Southward Bz exacerbates auroral oval expansion
        bz_penalty = abs(min(0.0, bz_eff)) * 0.45

        # Equatorward boundary at midnight (magnetic local time 00:00)
        eq_midnight = max(38.0, 66.5 - (2.1 * kp_eff) - bz_penalty)
        
        # Dawn/Dusk (MLT 06:00 and 18:00)
        eq_flanks = max(42.0, 68.5 - (1.9 * kp_eff) - (bz_penalty * 0.8))

        # Noon (MLT 12:00)
        eq_noon = max(55.0, 75.0 - (1.6 * kp_eff) - (bz_penalty * 0.6))

        # Poleward boundary at midnight
        pole_midnight = min(84.0, eq_midnight + 5.5 + 0.8 * kp_eff)

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

        # Auroral Power Index (in GigaWatts)
        power_gw = round(float(10.0 ** (0.21 * kp_eff + 0.5)), 1)

        return {
            "kp_used": round(kp_eff, 1),
            "bz_used": round(bz_eff, 1),
            "equatorward_midnight_lat": round(eq_midnight, 1),
            "equatorward_flanks_lat": round(eq_flanks, 1),
            "equatorward_noon_lat": round(eq_noon, 1),
            "poleward_midnight_lat": round(pole_midnight, 1),
            "hemispheric_power_gw": power_gw,
            "visible_regions": visible_regions
        }

    @classmethod
    def generate_auroral_oval_coordinates(cls, kp: float = 3.0, bz_gsm: float = -3.0, num_points: int = 48) -> List[Dict[str, float]]:
        """
        Generates geographic (lon, lat) polygon boundary points for the northern auroral oval ring.
        Geomagnetic pole: ~80.5° N, -72.5° W.
        """
        boundaries = cls.calculate_auroral_boundaries(kp, bz_gsm)
        eq_lat = boundaries["equatorward_midnight_lat"]
        
        # Colatitude radius (in degrees)
        colat_midnight = 90.0 - eq_lat
        colat_noon = 90.0 - boundaries["equatorward_noon_lat"]

        pole_lat = 80.5
        pole_lon = -72.5

        coords = []
        for i in range(num_points):
            angle_rad = (2.0 * math.pi * i) / num_points
            
            # Asymmetry between midnight (angle=0) and noon (angle=pi)
            # Oval is expanded towards midnight (sunward is compressed)
            colat = (colat_midnight + colat_noon) / 2.0 + ((colat_midnight - colat_noon) / 2.0) * math.cos(angle_rad)

            # Approximate projection from geomagnetic to geographic coordinates
            d_lat = colat * math.cos(angle_rad)
            d_lon = (colat * math.sin(angle_rad)) / math.cos(math.radians(pole_lat))

            geo_lat = max(-90.0, min(90.0, pole_lat - d_lat))
            geo_lon = ((pole_lon + d_lon + 180.0) % 360.0) - 180.0

            coords.append({
                "lat": round(geo_lat, 2),
                "lon": round(geo_lon, 2)
            })

        return coords

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
        Model-vs-observed statistics from (predicted, observed) pairs: sample count,
        Pearson r, RMSE, mean bias (predicted - observed) and both minima, in nT.
        Pairs with a missing value are skipped.
        """
        pts = [(float(p), float(o)) for p, o in pairs if p is not None and o is not None]
        n = len(pts)
        if n < 3:
            return {"n": n, "r": None, "rmse_nt": None, "bias_nt": None,
                    "min_predicted_nt": None, "min_observed_nt": None}
        pred = [p for p, _ in pts]
        obs = [o for _, o in pts]
        mp, mo = sum(pred) / n, sum(obs) / n
        sp = math.sqrt(sum((p - mp) ** 2 for p in pred))
        so = math.sqrt(sum((o - mo) ** 2 for o in obs))
        r = sum((p - mp) * (o - mo) for p, o in pts) / (sp * so) if sp > 0 and so > 0 else None
        return {
            "n": n,
            "r": round(r, 3) if r is not None else None,
            "rmse_nt": round(math.sqrt(sum((p - o) ** 2 for p, o in pts) / n), 1),
            "bias_nt": round(mp - mo, 1),
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
