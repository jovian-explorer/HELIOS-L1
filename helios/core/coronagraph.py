"""
Coronagraph imagery pipeline and CME kinematic shock speed & transit analyzer.
Integrates SOHO/LASCO C2/C3, SDO/AIA coronal feeds, Aditya-L1 VELC models,
and empirical CME deceleration and shock arrival forecasting.
"""
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any

class CoronagraphAnalyzer:
    """Manages solar coronagraph feeds and CME expansion kinematics."""

    R_SUN_KM = 696340.0
    AU_KM = 149597870.7
    L1_DIST_KM = 149597870.7 - 1496000.0  # ~1.481e8 km from Sun

    @classmethod
    def get_coronagraph_feeds(cls) -> Dict[str, Dict[str, Any]]:
        """Returns direct URLs and metadata for active solar coronagraph and EUV imagers."""
        return {
            "SOHO_LASCO_C2": {
                "name": "SOHO / LASCO C2",
                "instrument": "White Light Coronagraph (2.0 to 6.0 R_sun)",
                "mission": "SOHO (ESA/NASA)",
                "location": "Sun-Earth L1",
                "purpose": "Inner corona CME formation and initial ejection kinematics",
                "url": "https://services.swpc.noaa.gov/images/animations/lasco-c2/latest.jpg",
                "color_map": "Red / Orange Coronagraph"
            },
            "SOHO_LASCO_C3": {
                "name": "SOHO / LASCO C3",
                "instrument": "Wide Angle Coronagraph (3.7 to 32.0 R_sun)",
                "mission": "SOHO (ESA/NASA)",
                "location": "Sun-Earth L1",
                "purpose": "Interplanetary CME propagation, halo CME wavefronts, and shock fronts",
                "url": "https://services.swpc.noaa.gov/images/animations/lasco-c3/latest.jpg",
                "color_map": "Deep Blue Coronagraph"
            },
            "SDO_AIA_193": {
                "name": "SDO / AIA 193 Å",
                "instrument": "Extreme Ultraviolet Telescope (Fe XII ~1.25 MK)",
                "mission": "SDO (NASA)",
                "location": "Geosynchronous",
                "purpose": "Coronal holes (high speed solar wind sources) and coronal dimmings",
                "url": "https://services.swpc.noaa.gov/images/animations/suvi-primary-195/latest.png",
                "color_map": "Bronze EUV"
            },
            "SDO_AIA_304": {
                "name": "SDO / AIA 304 Å",
                "instrument": "He II ~50,000 K Chromosphere & Transition Region",
                "mission": "SDO (NASA)",
                "location": "Geosynchronous",
                "purpose": "Solar filament eruptions and prominence liftoffs",
                "url": "https://services.swpc.noaa.gov/images/animations/suvi-primary-304/latest.png",
                "color_map": "Red/Orange EUV"
            },
            "ADITYA_VELC": {
                "name": "Aditya-L1 / VELC",
                "instrument": "Visible Emission Line Coronagraph (1.05 to 3.0 R_sun)",
                "mission": "Aditya-L1 (ISRO)",
                "location": "Sun-Earth L1 Halo",
                "purpose": "High-cadence inner coronal spectroscopy and CME inception dynamics",
                "url": "https://services.swpc.noaa.gov/images/animations/lasco-c2/latest.jpg",
                "color_map": "Green Line 530.3 nm Coronal"
            }
        }

    @classmethod
    def calculate_cme_kinematics(
        cls,
        r1_rsun: float,
        r2_rsun: float,
        dt_minutes: float,
        launch_time_iso: str = None
    ) -> Dict[str, Any]:
        """
        Calculate CME plane-of-sky expansion velocity, aerodynamic drag deceleration,
        and predicted arrival time at Sun-Earth L1 and Earth (1 AU).
        Uses the Gopalswamy et al. (2001) empirical interplanetary CME acceleration model:
        a = -0.0054 * (V_init - 406)  [m/s^2]
        """
        if dt_minutes <= 0 or r2_rsun <= r1_rsun:
            return {"error": "Invalid kinematic inputs. r2 must be > r1 and dt > 0."}

        # Plane-of-sky expansion velocity
        delta_r_km = (r2_rsun - r1_rsun) * cls.R_SUN_KM
        dt_seconds = dt_minutes * 60.0
        v_initial_kms = delta_r_km / dt_seconds

        # Gopalswamy empirical interplanetary deceleration (drag with background solar wind)
        # a is in m/s^2; convert to km/s^2: / 1000
        a_kms2 = -0.0054 * (v_initial_kms - 406.0) / 1000.0

        # Transit distance to L1 and 1 AU from coronagraph height r2
        dist_to_l1_km = cls.L1_DIST_KM - (r2_rsun * cls.R_SUN_KM)
        dist_to_earth_km = cls.AU_KM - (r2_rsun * cls.R_SUN_KM)

        # Solve kinematics with constant acceleration/drag: d = v0*t + 0.5*a*t^2
        # If deceleration is very large, speed asymptotes to background solar wind (~400 km/s)
        def solve_transit_hours(dist_km, v0_kms, a_acc):
            if abs(a_acc) < 1e-9:
                return dist_km / v0_kms / 3600.0
            discriminant = (v0_kms ** 2) + 2 * a_acc * dist_km
            if discriminant > 0:
                t_sec = (-v0_kms + math.sqrt(discriminant)) / a_acc
                if t_sec > 0:
                    return t_sec / 3600.0
            # Fallback average speed model
            avg_speed = max(350.0, (v0_kms + 400.0) / 2.0)
            return dist_km / avg_speed / 3600.0

        transit_l1_hours = solve_transit_hours(dist_to_l1_km, v_initial_kms, a_kms2)
        transit_earth_hours = solve_transit_hours(dist_to_earth_km, v_initial_kms, a_kms2)

        # Calculate arrival timestamps
        now_dt = datetime.now(timezone.utc)
        if launch_time_iso:
            try:
                base_dt = datetime.fromisoformat(launch_time_iso.replace("Z", "+00:00"))
            except Exception:
                base_dt = now_dt
        else:
            base_dt = now_dt

        arrival_l1 = base_dt + timedelta(hours=transit_l1_hours)
        arrival_earth = base_dt + timedelta(hours=transit_earth_hours)

        # Spacecraft lead time (warning time between L1 detection and Earth impact)
        lead_time_min = (transit_earth_hours - transit_l1_hours) * 60.0

        # Classification of CME Speed
        if v_initial_kms >= 1500.0:
            speed_class = "Extreme High-Velocity Shock (Fast CME)"
            threat_level = "Severe / Extreme (G4 - G5 potential)"
        elif v_initial_kms >= 900.0:
            speed_class = "Fast CME"
            threat_level = "Strong (G2 - G3 potential)"
        elif v_initial_kms >= 500.0:
            speed_class = "Moderate CME"
            threat_level = "Minor to Moderate (G1 - G2 potential)"
        else:
            speed_class = "Slow / Ambient CME"
            threat_level = "Quiet / Low (G0 - G1)"

        return {
            "initial_speed_kms": round(v_initial_kms, 1),
            "speed_classification": speed_class,
            "threat_level": threat_level,
            "interplanetary_accel_ms2": round(a_kms2 * 1000.0, 4),
            "transit_to_l1_hours": round(transit_l1_hours, 1),
            "transit_to_earth_hours": round(transit_earth_hours, 1),
            "l1_to_earth_lead_time_minutes": round(lead_time_min, 1),
            "predicted_l1_arrival": arrival_l1.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "predicted_earth_arrival": arrival_earth.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "measurement_span_solar_radii": round(r2_rsun - r1_rsun, 2),
            "measurement_dt_minutes": dt_minutes
        }
