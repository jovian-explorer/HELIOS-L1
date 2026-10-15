"""
Solar Cycle 25 progression, Sunspot Number (SSN), and 10.7 cm Radio Flux (F10.7) engine.
Uses the observed monthly indices and the predicted cycle published by NOAA SWPC
(SILSO international sunspot number, Penticton F10.7), or a copy of them bundled with
HELIOS-L1 when they cannot be fetched.
"""
import gzip
import json
import math
from pathlib import Path
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "solar_cycle.json.gz"

class SolarCycleEngine:
    """Computes Solar Cycle 25 trajectory, historical baselines, and radio flux proxies."""

    CYCLE_25_START = "2019-12"  # cycle 24/25 minimum (SIDC)
    CYCLE_24_START = "2008-12"  # cycle 23/24 minimum (SIDC)

    @staticmethod
    def _month_index(tag: str) -> int:
        y, m = tag[:7].split("-")
        return int(y) * 12 + int(m) - 1

    @classmethod
    def from_noaa(cls, observed: Optional[List[Dict[str, Any]]], predicted: Optional[List[Dict[str, Any]]],
                  current_year_float: Optional[float] = None) -> Optional[Dict[str, Any]]:
        """
        Cycle 25 status from the NOAA SWPC solar-cycle products: observed monthly and
        13-month smoothed sunspot number and F10.7 (observed-solar-cycle-indices.json, -1 =
        not yet available) and the predicted cycle with its range (predicted-solar-cycle.json).
        Returns None when the observed product is missing.
        """
        def val(v):
            return None if v is None or (isinstance(v, (int, float)) and v < 0) else float(v)

        rows = [r for r in (observed or []) if isinstance(r, dict) and r.get("time-tag")]
        if not rows:
            return None
        by_month = {cls._month_index(r["time-tag"]): r for r in rows}
        start25, start24 = cls._month_index(cls.CYCLE_25_START), cls._month_index(cls.CYCLE_24_START)
        last_obs = max(by_month)
        pred = {cls._month_index(p["time-tag"]): p for p in (predicted or []) if isinstance(p, dict) and p.get("time-tag")}

        if current_year_float is not None:
            target = int(math.floor(current_year_float)) * 12 + int((current_year_float % 1) * 12)
        else:
            now = datetime.now(timezone.utc)
            target = now.year * 12 + now.month - 1
        # Latest values at or before the target month
        obs_months = [m for m in sorted(by_month) if m <= target]
        latest = by_month[obs_months[-1]] if obs_months else None
        smoothed_months = [m for m in obs_months if val(by_month[m].get("smoothed_ssn")) is not None]
        sm = by_month[smoothed_months[-1]] if smoothed_months else None

        # Peak so far as of the target month (a past date used to get the later maximum).
        cyc = [(m, val(by_month[m].get("smoothed_ssn"))) for m in smoothed_months if m >= start25]
        cyc = [(m, v) for m, v in cyc if v is not None]
        peak_m, peak_v = max(cyc, key=lambda x: x[1]) if cyc else (None, None)
        if peak_m is None:
            phase = None
        elif smoothed_months[-1] > peak_m + 6:  # six smoothed months below the peak
            phase = "Declining phase"
        elif peak_m == smoothed_months[-1]:
            phase = "Ascending phase"  # still at a new high: a maximum is known only once passed
        else:
            phase = "Near maximum"

        def tag(m):
            return f"{m // 12}-{m % 12 + 1:02d}"

        timeline = []
        for m in range(start25, start25 + 11 * 12 + 1):
            o = by_month.get(m)
            p = pred.get(m)
            c24 = by_month.get(start24 + (m - start25))
            timeline.append({
                "year_month": tag(m),
                "year_fraction": round(m / 12.0, 3),
                "ssn_monthly": val(o.get("ssn")) if o else None,
                "ssn_smoothed": val(o.get("smoothed_ssn")) if o else None,
                "f107_sfu": val(o.get("f10.7")) if o else None,
                "ssn_predicted": val(p.get("predicted_ssn")) if p and m > last_obs - 6 else None,
                "ssn_predicted_low": val(p.get("low_ssn")) if p and m > last_obs - 6 else None,
                "ssn_predicted_high": val(p.get("high_ssn")) if p and m > last_obs - 6 else None,
                "cycle_24_comparison_ssn": val(c24.get("smoothed_ssn")) if c24 else None,
            })
        progress = min(100.0, max(0.0, (target - start25) / (11 * 12) * 100.0))
        return {
            "status": "success",
            "data_kind": "observed",
            "source": "NOAA SWPC solar-cycle products (SILSO international sunspot number, Penticton F10.7; predicted cycle with range)",
            "solar_cycle": 25,
            "current_year": round(target / 12.0, 2),
            "month": tag(obs_months[-1]) if obs_months else None,
            "monthly_sunspot_number": val(latest.get("ssn")) if latest else None,
            "monthly_f107_sfu": val(latest.get("f10.7")) if latest else None,
            "smoothed_sunspot_number": val(sm.get("smoothed_ssn")) if sm else None,
            "smoothed_month": tag(smoothed_months[-1]) if smoothed_months else None,
            "f107_radio_flux_sfu": val(sm.get("smoothed_f10.7")) if sm else None,
            "cycle_progress_percent": round(progress, 1),
            "cycle_progress_basis": "months since the December 2019 minimum over a nominal 11-year cycle",
            "current_phase": phase,
            "peak_sunspot_number": peak_v,
            "peak_month": tag(peak_m) if peak_m is not None else None,
            "peak_year": round(peak_m / 12.0, 2) if peak_m is not None else None,
            "polar_magnetic_reversal": "Not tracked (no polar field data source)",
            "timeline": timeline,
        }

    @classmethod
    def bundled(cls, current_year_float: Optional[float] = None) -> Dict[str, Any]:
        """from_noaa on the copy of the NOAA products bundled with HELIOS-L1 (used when NOAA is unreachable)."""
        snap = json.loads(gzip.decompress(SNAPSHOT.read_bytes()))
        res = cls.from_noaa(snap["observed"], snap["predicted"], current_year_float)
        res["source"] += f"; NOAA unreachable: copy bundled with HELIOS-L1 (retrieved {snap['retrieved_utc']})"
        return res
