"""
Solar Cycle 25 progression, Sunspot Number (SSN), and 10.7 cm Radio Flux (F10.7) engine.
Uses the observed monthly indices and the predicted cycle published by NOAA SWPC
(SILSO international sunspot number, Penticton F10.7) and falls back to a labelled
analytic approximation when they cannot be fetched.
"""
import math
from datetime import datetime, timezone
from typing import Dict, List, Any, Optional

class SolarCycleEngine:
    """Computes Solar Cycle 25 trajectory, historical baselines, and radio flux proxies."""

    # Official Solar Cycle 25 start: December 2019 (Cycle 24/25 minimum)
    CYCLE_25_START_YEAR = 2019.92
    CYCLE_25_PEAK_YEAR = 2024.75  # Near late 2024 / 2025 solar maximum peak
    CYCLE_25_END_YEAR = 2030.50

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

        cyc = [(m, val(by_month[m].get("smoothed_ssn"))) for m in sorted(by_month) if m >= start25]
        cyc = [(m, v) for m, v in cyc if v is not None]
        peak_m, peak_v = max(cyc, key=lambda x: x[1]) if cyc else (None, None)

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
            "current_phase": "Declining phase" if peak_m is not None and target > peak_m + 6 else "Near maximum",
            "peak_sunspot_number": peak_v,
            "peak_month": tag(peak_m) if peak_m is not None else None,
            "peak_year": round(peak_m / 12.0, 2) if peak_m is not None else None,
            "polar_magnetic_reversal": "Not tracked (no polar field data source)",
            "timeline": timeline,
        }

    @staticmethod
    def calculate_cycle_25_progression(current_year_float: float = 2026.72) -> Dict[str, Any]:
        """
        Offline fallback: an analytic approximation of cycle 25 (sin^2 rise over 4.8 years
        to SSN 172, then exponential decay at 0.28 per year) with the F10.7 relation
        63.7 + 0.728 SSN + 0.00089 SSN^2. It is not the Hathaway model it used to be
        labelled as, and the response says it is a model.
        """
        t0 = SolarCycleEngine.CYCLE_25_START_YEAR
        dt = max(0.01, current_year_float - t0)

        # Hathaway 2015 empirical parameters for Cycle 25
        # Cycle 25 has exceeded initial consensus predictions, peaking near SSN ~ 160-180
        amplitude = 172.0
        rise_time = 4.8  # years to peak

        # Parametric progression
        progress_pct = min(100.0, max(0.0, ((current_year_float - t0) / (SolarCycleEngine.CYCLE_25_END_YEAR - t0)) * 100.0))

        # Solar activity shape
        x = dt / rise_time
        if x <= 1.0:
            # Rise phase
            smoothed_ssn = amplitude * (math.sin(math.pi * x / 2.0) ** 2)
        else:
            # Decline phase (slower exponential decay)
            decay_rate = 0.28
            smoothed_ssn = amplitude * math.exp(-decay_rate * (dt - rise_time))

        smoothed_ssn = max(5.0, round(smoothed_ssn, 1))

        # F10.7 cm Solar Radio Flux proxy (s.f.u. - solar flux units, 10^-22 W m^-2 Hz^-1)
        # Empirical relationship: F10.7 ~ 63.7 + 0.728 * SSN + 0.00089 * SSN^2
        f107 = round(63.7 + 0.728 * smoothed_ssn + 0.00089 * (smoothed_ssn ** 2), 1)

        # Phase description
        if dt < 2.0:
            phase = "Solar Minimum & Early Ascending Phase"
        elif dt < 4.0:
            phase = "Fast Ascending Phase"
        elif dt < 5.8:
            phase = "Solar Maximum Peak Window (High Flaring & CME Activity)"
        elif dt < 8.5:
            phase = "Declining Phase (Frequent High-Speed Streams & Recurrent CIRs)"
        else:
            phase = "Late Declining / Solar Minimum Approach"

        # Monthly trajectory for 2019 to 2031 (11-year span)
        timeline = []
        for y_step in range(0, 133):  # 11 years in monthly steps
            t = t0 + (y_step / 12.0)
            t_dt = max(0.01, t - t0)
            t_x = t_dt / rise_time
            if t_x <= 1.0:
                ssn_val = amplitude * (math.sin(math.pi * t_x / 2.0) ** 2)
            else:
                ssn_val = amplitude * math.exp(-0.28 * (t_dt - rise_time))
            f107_val = 63.7 + 0.728 * ssn_val + 0.00089 * (ssn_val ** 2)
            timeline.append({
                "year_fraction": round(t, 2),
                "year_month": f"{int(t)}-{int((t % 1) * 12) + 1:02d}",
                "ssn_smoothed": round(ssn_val, 1),
                "f107_sfu": round(f107_val, 1),
                "cycle_24_comparison_ssn": round(ssn_val * 0.68, 1)  # Cycle 24 was ~32% weaker
            })

        return {
            "status": "success",
            "data_kind": "model",
            "source": "Analytic approximation (NOAA SWPC solar-cycle products unavailable)",
            "solar_cycle": 25,
            "current_year": round(current_year_float, 2),
            "cycle_progress_percent": round(progress_pct, 1),
            "current_phase": phase,
            "smoothed_sunspot_number": smoothed_ssn,
            "f107_radio_flux_sfu": f107,
            "peak_sunspot_number": amplitude,
            "peak_year": SolarCycleEngine.CYCLE_25_PEAK_YEAR,
            "polar_magnetic_reversal": "Not tracked (no polar field data source)",
            "timeline": timeline[::2]  # Bi-monthly points for optimal chart bandwidth
        }
