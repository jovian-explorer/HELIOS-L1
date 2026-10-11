"""
Corona to L1: a CME or a solar wind stream followed from its coronal measurement to L1 and
compared with the in-situ data there.

* CME: the drag-based model of the CME solver (Vrsnak et al. 2013; helios.core.coronagraph)
  started at a measured height, time and speed (e.g. a fitted coronagraph front), giving the
  arrival time and speed at L1.
* Stream: constant speed from the source surface (r_ss) to L1, the inverse of the ballistic
  mapping of the PFSS panel: t_L1 = t_ss + (d_L1 - r_ss) / V.
* Observed: the fast forward shocks of the IPShocks database at WIND, ACE or DSCOVR within
  +-SEARCH_HOURS of the predicted arrival (the one nearest to it; the downstream speed is the
  upstream speed plus the speed jump), and the measured speed, density and field of the
  spacecraft (NASA CDAWeb archive, 5-minute means) from 2 days before to 2 days after.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from helios.core import shock_catalog
from helios.core.coronagraph import CoronagraphAnalyzer

R_SUN_KM = 696340.0
SEARCH_HOURS = 24.0
L1_FROM_SUN_KM = CoronagraphAnalyzer.L1_DIST_KM


def _utc(t: datetime) -> datetime:
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def predict_cme(t0: datetime, h0_rsun: float, v0_kms: float, w_kms: float = 420.0,
                gamma_per_km: float = 1.0e-7) -> Dict[str, Any]:
    """DBM arrival at L1 of a CME at h0 (R_sun) moving at v0 at time t0 (the solver's two-height input)."""
    r1 = h0_rsun - v0_kms * 600.0 / R_SUN_KM
    k = CoronagraphAnalyzer.calculate_cme_kinematics(r1, h0_rsun, 10.0, _utc(t0).strftime("%Y-%m-%dT%H:%M:%S"),
                                                    w_kms, gamma_per_km)
    if "error" in k:
        raise ValueError(k["error"])
    arr = datetime.strptime(k["predicted_l1_arrival"], "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=timezone.utc)
    return {"model": f"drag-based model, w = {k['ambient_wind_kms']:g} km/s, gamma = {k['drag_parameter_gamma']:.2g} /km",
            "arrival_l1": arr, "speed_l1_kms": k["v_arrival_l1_kms"], "transit_hours": k["transit_to_l1_hours"]}


def predict_stream(t_ss: datetime, v_kms: float, rss_rsun: float = 2.5) -> Dict[str, Any]:
    if v_kms <= 0:
        raise ValueError("The speed must be positive.")
    dt = (L1_FROM_SUN_KM - rss_rsun * R_SUN_KM) / v_kms
    return {"model": f"constant {v_kms:g} km/s from the source surface at {rss_rsun:g} R_sun",
            "arrival_l1": _utc(t_ss) + timedelta(seconds=dt), "speed_l1_kms": v_kms, "transit_hours": round(dt / 3600.0, 1)}


def observed_shock(t: datetime, spacecraft: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """IPShocks fast forward shock at L1 nearest to t within SEARCH_HOURS (any of WIND, ACE, DSCOVR unless named)."""
    events = [e for e in shock_catalog.load()["events"] if e["type"] == "FF"
              and (spacecraft is None or e["spacecraft"] == spacecraft)]
    near = [e for e in events if abs(shock_catalog.event_time(e) - t) <= timedelta(hours=SEARCH_HOURS)]
    if not near:
        return None
    e = min(near, key=lambda e: abs(shock_catalog.event_time(e) - t))
    down = (e["upstream_speed_kms"] + e["speed_jump_kms"]) if e.get("upstream_speed_kms") is not None and e.get("speed_jump_kms") is not None else None
    return {"time": e["time"], "spacecraft": e["spacecraft"], "upstream_speed_kms": e.get("upstream_speed_kms"),
            "downstream_speed_kms": None if down is None else round(down, 1), "shock_speed_kms": e.get("shock_speed_kms"),
            "source": "IPShocks database (Kilpua et al.), fast forward shocks at L1"}


def compare(pred: Dict[str, Any], shock: Optional[Dict[str, Any]], records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Prediction against the observed shock and the measured speed; series in hours from the predicted arrival."""
    t_pred = pred["arrival_l1"]
    out = {"predicted": {**pred, "arrival_l1": t_pred.strftime("%Y-%m-%d %H:%M:%S")}, "observed_shock": shock,
           "arrival_error_hours": None, "speed_error_kms": None}
    if shock:
        t_obs = datetime.strptime(shock["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        out["arrival_error_hours"] = round((t_pred - t_obs).total_seconds() / 3600.0, 2)
        if shock["downstream_speed_kms"] is not None:
            out["speed_error_kms"] = round(pred["speed_l1_kms"] - shock["downstream_speed_kms"], 1)
    series = []
    for r in records:
        try:
            t = datetime.strptime(r["time_tag"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        except (KeyError, ValueError):
            continue
        series.append({"hours_from_predicted": round((t - t_pred).total_seconds() / 3600.0, 3), "time": r["time_tag"],
                       "speed": r.get("speed"), "density": r.get("density"), "bt": r.get("bt")})
    out["series"] = series
    sp = [s for s in series if s["speed"] is not None and abs(s["hours_from_predicted"]) <= 1.0]
    out["measured_speed_at_predicted_kms"] = round(sum(s["speed"] for s in sp) / len(sp), 1) if sp else None
    return out
