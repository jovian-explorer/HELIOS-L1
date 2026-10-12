"""
HELIOS-L1 magnetospheric coupling and storm trajectory engine (empirical relations, no machine learning).
Implements:
1. Newell Solar Wind Magnetosphere Coupling Function (Newell et al., 2007)
2. O'Brien & McPherron (2000) ring current Dst model (helios.core.aurora_model), started from observed Dst
3. 12-hour Kp trajectory (Newell et al. 2008 fit, persisted drivers); NOAA SWPC storm probabilities
4. Critical Infrastructure Hazard Impact Evaluator (GIC, Aviation, Satellites, HF Radio)
"""
import math
from typing import Dict, Any, List, Optional
from datetime import datetime, timezone, timedelta

from helios.core.aurora_model import AuroralModel
from helios.core.science import PDYN_NPA_PER_CM3_KMS2, SpaceWeatherPhysics

# Newell et al. (2008) Kp fit: Kp = a + b dPhi/dt + c n^(1/2) v^2
NEWELL_2008_KP = (0.05, 2.244e-4, 2.844e-6)
# Persistence assumption for the 12 h trajectory: the drivers relax to these quiet values
QUIET_DRIVERS = {"speed": 400.0, "density": 5.0, "bz_gsm": -1.0}
RELAXATION_PER_HOUR = 0.05

class SpaceWeatherForecaster:
    """Empirical coupling functions, Kp and Dst trajectories and hazard categories."""

    @staticmethod
    def calculate_newell_coupling(speed_kms: float, b_total_nt: float, bz_gsm_nt: float, by_gsm_nt: float = 0.0) -> float:
        """Newell et al. (2007) dPhi/dt in (km/s)^(4/3) nT^(2/3) (SpaceWeatherPhysics.newell_coupling),
        rounded to 0.1; b_total_nt is kept for API compatibility and is not used (Bx does not enter)."""
        return round(SpaceWeatherPhysics.newell_coupling(speed_kms, by_gsm_nt, bz_gsm_nt), 1)

    @staticmethod
    def newell_2008_kp(speed_kms: Optional[float], density_cm3: Optional[float],
                       by_gsm_nt: Optional[float], bz_gsm_nt: Optional[float]) -> Optional[float]:
        """
        Kp from the solar wind with the merging + viscous pair of Newell et al. (2008,
        JGR 113, A04218, doi:10.1029/2007JA012825):
            Kp = 0.05 + 2.244e-4 dPhi/dt + 2.844e-6 n^(1/2) v^2
        with dPhi/dt = v^(4/3) B_T^(2/3) sin^(8/3)(theta_c/2) (v in km/s, B in nT, n in cm^-3).
        Coefficients as implemented in JHUAPL kaipy (kaiTools.newellkp). Clipped to 0-9.
        None when a driver is missing.
        """
        if speed_kms is None or density_cm3 is None or bz_gsm_nt is None:
            return None
        v, n = float(speed_kms), max(0.0, float(density_cm3))
        dphi = SpaceWeatherForecaster.calculate_newell_coupling(v, None, float(bz_gsm_nt), float(by_gsm_nt or 0.0))
        a, b, c = NEWELL_2008_KP
        return max(0.0, min(9.0, a + b * dphi + c * math.sqrt(n) * v * v))

    @staticmethod
    def _density(rec: Dict[str, Any]) -> Optional[float]:
        """Proton density, or the one implied by the dynamic pressure when only that is present."""
        if rec.get("density") is not None:
            return float(rec["density"])
        if rec.get("dynamic_pressure") is not None and rec.get("speed"):
            return float(rec["dynamic_pressure"]) / (PDYN_NPA_PER_CM3_KMS2 * float(rec["speed"]) ** 2)
        return None

    @staticmethod
    def forecast_geomagnetic_storm(
        telemetry_records: List[Dict[str, Any]],
        observed_dst: Optional[float] = None,
        noaa_forecast: Optional[Dict[str, Any]] = None,
        observed_dst_end: Optional[datetime] = None,
        earth_drivers: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        12-hour Kp and Dst trajectory from the latest L1 solar wind.

        Kp: Newell et al. (2008) from the drivers. Dst: O'Brien & McPherron (2000) stepped
        hourly from the latest observed (Kyoto) value when given, else from the model run
        over the records. The drivers are not forecast: they relax from the latest values
        towards quiet values by 5 % per hour (an assumption, listed in the response). The
        Kp band is the range of Newell Kp over the last 3 h of data, not a statistical
        interval. Storm probabilities are NOAA SWPC's own forecast (noaa_forecast) when
        available; this model does not compute probabilities.
        """
        if not telemetry_records:
            return {"status": "error", "message": "No telemetry data provided"}

        # Newest record with the drivers present (the last row is often a partial gap).
        latest = next((r for r in reversed(telemetry_records)
                       if r.get("speed") is not None and r.get("bz_gsm") is not None), None)
        if latest is None:
            return {"status": "error", "message": "No record with solar wind speed and Bz"}

        v_now = float(latest["speed"])
        bz_now = float(latest["bz_gsm"])
        by_now = float(latest.get("by_gsm") or 0.0)
        n_now = SpaceWeatherForecaster._density(latest)

        newell_now = SpaceWeatherForecaster.calculate_newell_coupling(v_now, None, bz_now, by_now)
        kp_now = SpaceWeatherForecaster.newell_2008_kp(v_now, n_now, by_now, bz_now)

        # Spread of Newell Kp over the last 3 h of data (records with all drivers)
        def parse(t):
            try:
                return datetime.fromisoformat(str(t).replace("Z", "").replace("T", " "))
            except ValueError:
                return None
        t_last = parse(latest.get("time_tag"))
        recent = []
        for r in telemetry_records:
            t = parse(r.get("time_tag"))
            if t_last is not None and (t is None or t > t_last or (t_last - t).total_seconds() > 3 * 3600):
                continue
            k = SpaceWeatherForecaster.newell_2008_kp(r.get("speed"), SpaceWeatherForecaster._density(r),
                                                      r.get("by_gsm"), r.get("bz_gsm"))
            if k is not None:
                recent.append(k)
        if kp_now is not None:
            recent.append(kp_now)
            band = (min(recent) - kp_now, max(recent) - kp_now)
        else:
            band = (0.0, 0.0)

        # Starting Dst: the latest observed (Kyoto) value carried forward by the model with the L1
        # wind already measured, shifted to Earth by its travel time (earth_drivers), to the last
        # time those drivers reach; without an observed value, the model over the whole day.
        # (It used to start from the observed hour itself, up to 3 h old, and label it "now".)
        drivers = earth_drivers if earth_drivers is not None else telemetry_records

        def t_of(r):
            t = parse(r.get("time_tag"))
            return t.replace(tzinfo=timezone.utc) if t is not None else None
        timed = [r for r in drivers if t_of(r) is not None]
        if observed_dst is not None and observed_dst_end is not None:
            after = [r for r in timed if t_of(r) > observed_dst_end]
            sim = AuroralModel.simulate_dst_evolution(after, initial_dst=float(observed_dst)) if after else []
            current_dst = sim[-1]["dst_predicted_nt"] if sim else round(float(observed_dst), 1)
            start_time = t_of(after[-1]) if after else observed_dst_end
            dst_source = (f"observed (WDC Kyoto real-time Dst, {observed_dst:g} nT for the hour to "
                          f"{observed_dst_end:%H:%M} UTC), carried forward with the measured L1 wind")
        elif observed_dst is not None:
            current_dst, dst_source = round(float(observed_dst), 1), "observed (WDC Kyoto real-time Dst)"
            start_time = datetime.now(timezone.utc)
        else:
            sim = AuroralModel.simulate_dst_evolution(timed)
            current_dst = sim[-1]["dst_predicted_nt"] if sim else 0.0
            start_time = t_of(timed[-1]) if timed else datetime.now(timezone.utc)
            dst_source = "O'Brien & McPherron (2000) model over the last day of solar wind"

        predictions = []
        now_time = start_time
        sim_dst = current_dst
        q = QUIET_DRIVERS
        for h in range(1, 13):
            # Persistence relaxing towards quiet conditions (assumption, not a forecast)
            w = max(0.0, 1.0 - RELAXATION_PER_HOUR * h)
            eff_v = v_now * w + q["speed"] * (1.0 - w)
            eff_bz = bz_now * w + q["bz_gsm"] * (1.0 - w)
            eff_by = by_now * w
            eff_n = (n_now * w + q["density"] * (1.0 - w)) if n_now is not None else None
            eff_pdyn = PDYN_NPA_PER_CM3_KMS2 * eff_n * eff_v ** 2 if eff_n is not None else None

            sim_dst = round(AuroralModel.dst_step(sim_dst, eff_v, eff_bz, eff_pdyn, dt_hours=1.0), 1)
            kp = SpaceWeatherForecaster.newell_2008_kp(eff_v, eff_n, eff_by, eff_bz)

            fut_time = now_time + timedelta(hours=h)
            predictions.append({
                "horizon_hours": h,
                "time_iso": fut_time.isoformat(),
                "time_label": fut_time.strftime("%H:%M UTC"),
                "predicted_kp": round(kp, 1) if kp is not None else None,
                "kp_confidence_interval": [max(0.0, round(kp + band[0], 1)), min(9.0, round(kp + band[1], 1))]
                                          if kp is not None else [None, None],
                "predicted_dst_nt": sim_dst,
                # Starkov (1994) equatorward midnight boundary for this Kp (Kp converted to AL)
                "auroral_midnight_boundary_lat": round(float(AuroralModel.starkov_latitude(
                    AuroralModel.kp_to_al(kp), 0.0, "equatorward")), 1) if kp is not None else None
            })

        kps = [p["predicted_kp"] for p in predictions[:6] if p["predicted_kp"] is not None]
        max_pred_kp = max(kps) if kps else (kp_now or 0.0)

        hazards = SpaceWeatherForecaster.assess_hazards(v_now, bz_now, None, max_pred_kp)

        if bz_now < -5.0:
            coupling_state = "Strong southward IMF (Bz < -5 nT): enhanced dayside reconnection"
        elif bz_now < 0.0:
            coupling_state = "Southward IMF: dayside reconnection"
        else:
            coupling_state = "Northward IMF: weak dayside coupling"

        return {
            "model_version": "Newell et al. (2008) Kp + O'Brien & McPherron (2000) Dst, persisted L1 drivers",
            "current_coupling": {
                "newell_coupling_rate": newell_now,
                "newell_units": "(km/s)^4/3 nT^2/3",
                "newell_kp_now": round(kp_now, 1) if kp_now is not None else None,
                "coupling_state": coupling_state,
                "estimated_dst_nt": current_dst,
                "dst_source": dst_source
            },
            "storm_probabilities": SpaceWeatherForecaster.noaa_probabilities(noaa_forecast),
            "noaa_kp_forecast": (noaa_forecast or {}).get("kp_forecast", []),
            "predictions_timeline": predictions,
            "trajectory_start_utc": start_time.strftime("%Y-%m-%d %H:%M"),
            "kp_band_description": "Range of Newell (2008) Kp over the last 3 h of solar wind data, carried along the trajectory; not a statistical confidence interval.",
            "assumptions": [
                f"The L1 drivers are not forecast: they relax linearly from the latest values towards {q['speed']:.0f} km/s, "
                f"{q['density']:.0f} cm^-3 and Bz {q['bz_gsm']:.0f} nT by {RELAXATION_PER_HOUR * 100:.0f}% per hour.",
                "Kp is the Newell et al. (2008) solar wind fit, a statistical relation with substantial scatter, not an official Kp forecast.",
                "Storm probabilities are NOAA SWPC's forecast for the next UTC day, not computed here.",
            ],
            "hazard_assessment": hazards
        }

    @staticmethod
    def noaa_probabilities(noaa_forecast: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        """Day-1 geomagnetic activity probabilities of the NOAA SWPC 3-day forecast (None when unavailable)."""
        f = noaa_forecast or {}
        p = f.get("probabilities") or {}
        return {
            "minor_storm_g1_percent": p.get("minor_storm"),
            "moderate_storm_g2_percent": p.get("moderate_storm"),
            "strong_extreme_storm_g3_g5_percent": p.get("strong_extreme_storm"),
            "active_percent": p.get("active"),
            "day": f.get("day"),
            "issued": f.get("issued"),
            "source": ("NOAA SWPC 3-day geomagnetic forecast, probabilities for the next UTC day" if p
                       else "unavailable (the NOAA SWPC forecast could not be loaded)")
        }

    @staticmethod
    def assess_hazards(speed: float, bz: float, pdyn: float, max_kp: float) -> Dict[str, Any]:
        """Evaluates operational risk levels for critical infrastructure from the NOAA G level of max_kp."""
        g = SpaceWeatherPhysics.noaa_g_level(max_kp)
        # 1. Power Grids & Geomagnetically Induced Currents (GIC)
        if g >= 4:
            gic_risk = "CRITICAL / SEVERE"
            gic_color = "#ff2a6d"
            gic_advice = "Widespread voltage regulation alarms and protective transformer trip risks. GIC monitoring active."
        elif g >= 2:
            gic_risk = "MODERATE / ELEVATED"
            gic_color = "#ffb703"
            gic_advice = "Weak power grid fluctuations possible in high-latitude systems (>55° geomag)."
        else:
            gic_risk = "NOMINAL / LOW"
            gic_color = "#00ff9d"
            gic_advice = "No transmission network mitigation required."

        # 2. Polar Aviation & High-Frequency (HF) Communications
        if g >= 3 or bz < -10.0:
            aviation_risk = "HIGH / SEVERE ABSORPTION"
            aviation_color = "#ff2a6d"
            aviation_advice = "HF fading and absorption at high latitudes and GNSS scintillation likely. (Polar cap absorption needs a solar proton event: see the S scale.)"
        elif g >= 1:
            aviation_risk = "MODERATE"
            aviation_color = "#ffb703"
            aviation_advice = "HF radio fadeouts on sub-auroral routes; GNSS scintillation degradation expected."
        else:
            aviation_risk = "NOMINAL"
            aviation_color = "#00ff9d"
            aviation_advice = "Normal trans-polar navigation and HF propagation."

        # 3. Satellite Operations (Surface Charging & Atmospheric Drag)
        # Categories follow the NOAA G scale; the drag increase itself is not modelled (it was
        # given as an invented 1 + 0.45 (Kp - 3) multiplier).
        if g >= 3:
            sat_risk = "CRITICAL / DRAG ACCELERATION"
            sat_color = "#ff2a6d"
            sat_advice = "Thermospheric heating raises LEO drag strongly (NOAA G3+: surface charging, orientation and tracking problems possible)."
        elif g >= 1:
            sat_risk = "ELEVATED"
            sat_color = "#ffb703"
            sat_advice = "Increased LEO drag and orbit prediction errors possible (NOAA G1-G2)."
        else:
            sat_risk = "NOMINAL"
            sat_color = "#00ff9d"
            sat_advice = "Standard orbit ephemeris and telemetry downlink nominal."

        return {
            "power_grid_gic": {"risk_level": gic_risk, "color": gic_color, "advisory": gic_advice},
            "aviation_hf": {"risk_level": aviation_risk, "color": aviation_color, "advisory": aviation_advice},
            "satellite_ops": {"risk_level": sat_risk, "color": sat_color, "drag_multiplier": None, "advisory": sat_advice}
        }
