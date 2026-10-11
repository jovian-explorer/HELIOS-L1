"""
Coronagraph imagery pipeline and CME kinematic shock speed & transit analyzer.
Integrates SOHO/LASCO C2/C3 and GOES/SUVI EUV image feeds (Aditya-L1 VELC has no public real-time feed),
and empirical CME deceleration and shock arrival forecasting.
"""
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, List, Any
from helios.core.constants import AU_KM, R_SUN_KM

class CoronagraphAnalyzer:
    """Manages solar coronagraph feeds and CME expansion kinematics."""

    R_SUN_KM = R_SUN_KM
    AU_KM = AU_KM
    L1_DIST_KM = AU_KM - 1496000.0  # ~1.481e8 km from Sun

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
            "GOES_SUVI_195": {
                "name": "GOES / SUVI 195 Å",
                "instrument": "Solar Ultraviolet Imager (Fe XII ~1.5 MK)",
                "mission": "GOES-R series (NOAA/NASA)",
                "location": "Geostationary",
                "purpose": "Coronal holes (high speed solar wind sources) and coronal dimmings",
                "url": "https://services.swpc.noaa.gov/images/animations/suvi/primary/195/latest.png",
                "color_map": "Bronze EUV"
            },
            "GOES_SUVI_304": {
                "name": "GOES / SUVI 304 Å",
                "instrument": "Solar Ultraviolet Imager (He II ~50,000 K chromosphere & transition region)",
                "mission": "GOES-R series (NOAA/NASA)",
                "location": "Geostationary",
                "purpose": "Solar filament eruptions and prominence liftoffs",
                "url": "https://services.swpc.noaa.gov/images/animations/suvi/primary/304/latest.png",
                "color_map": "Red/Orange EUV"
            },
            "ADITYA_VELC": {
                "name": "Aditya-L1 / VELC",
                "instrument": "Visible Emission Line Coronagraph (1.05 to 3.0 R_sun)",
                "mission": "Aditya-L1 (ISRO)",
                "location": "Sun-Earth L1 Halo",
                "purpose": "High-cadence inner coronal spectroscopy and CME inception dynamics",
                # ISSDC PRADAN serves VELC data only to registered users; there is no public
                # real-time image (this entry used to show the LASCO C2 image under the VELC name).
                "url": None,
                "status": "No public real-time image feed (ISSDC PRADAN requires a registered login)",
                "color_map": "Green Line 530.3 nm Coronal"
            }
        }

    @classmethod
    def gopalswamy_2001_arrival(cls, speed_kms: float, r0_km: float = 0.0) -> Dict[str, Any]:
        """
        Gopalswamy et al. (2001) empirical CME arrival: a = 2.193 - 0.0054 u m/s^2 until
        0.76 AU, then constant speed to 1 AU. Returns transit hours from r0 and arrival speed.
        """
        a = (2.193 - 0.0054 * speed_kms) / 1000.0  # km/s^2
        d1 = max(0.0, 0.76 * cls.AU_KM - r0_km)
        if abs(a) < 1e-12:
            t1 = d1 / speed_kms
        else:
            disc = speed_kms ** 2 + 2.0 * a * d1
            if disc < 0:  # the CME would stop before 0.76 AU: outside the model
                return {"transit_hours": None, "arrival_speed_kms": None, "acceleration_ms2": round(a * 1000.0, 3)}
            t1 = (-speed_kms + math.sqrt(disc)) / a
        v1 = speed_kms + a * t1
        t = t1 + (cls.AU_KM - max(r0_km, 0.76 * cls.AU_KM)) / v1
        return {"transit_hours": round(t / 3600.0, 1), "arrival_speed_kms": round(v1, 1),
                "acceleration_ms2": round(a * 1000.0, 3)}

    @classmethod
    def calculate_cme_kinematics(
        cls,
        r1_rsun: float,
        r2_rsun: float,
        dt_minutes: float,
        launch_time_iso: str = None,
        ambient_wind_kms: float = 420.0,
        gamma_drag: float = 1.0e-7
    ) -> Dict[str, Any]:
        """
        Calculate CME plane-of-sky expansion velocity, aerodynamic drag kinematics,
        and arrival time/speed at Sun-Earth L1 and Earth (1 AU).
        Implements the peer-reviewed Vršnak et al. (2013) Drag-Based Model (DBM):
            dv/dt = -Γ (v - w) |v - w|
        with exact closed-form analytical solutions and Newton-Raphson transit inversion,
        and the Gopalswamy et al. (2001) empirical CME arrival model for comparison.
        The speed is the plane-of-sky speed between the two heights (no projection
        correction); transit times count from the time of the second height.
        """
        if dt_minutes <= 0 or r2_rsun <= r1_rsun:
            return {"error": "Invalid kinematic inputs. r2 must be > r1 and dt > 0."}

        # 1. Plane-of-sky expansion velocity at coronagraph height r2
        delta_r_km = (r2_rsun - r1_rsun) * cls.R_SUN_KM
        dt_seconds = dt_minutes * 60.0
        v_initial_kms = delta_r_km / dt_seconds

        # 2. Vršnak et al. (2013) Drag-Based Model (DBM) Integration
        # w = ambient solar wind speed, gamma = drag parameter (1/km)
        w = max(250.0, min(900.0, ambient_wind_kms))
        gamma = max(0.1e-7, min(3.0e-7, gamma_drag))
        r0_km = r2_rsun * cls.R_SUN_KM
        u0 = v_initial_kms - w

        def dbm_r(t_sec: float) -> float:
            """Heliocentric distance R(t) from Sun in km."""
            if abs(u0) < 1e-4:
                return r0_km + w * t_sec
            if u0 > 0:
                return r0_km + w * t_sec + (1.0 / gamma) * math.log(1.0 + gamma * u0 * t_sec)
            else:
                arg = max(1e-12, 1.0 + gamma * abs(u0) * t_sec)
                return r0_km + w * t_sec - (1.0 / gamma) * math.log(arg)

        def dbm_v(t_sec: float) -> float:
            """Kinematic expansion velocity v(t) in km/s."""
            if abs(u0) < 1e-4:
                return w
            if u0 > 0:
                return w + u0 / (1.0 + gamma * u0 * t_sec)
            else:
                denom = max(1e-12, 1.0 + gamma * abs(u0) * t_sec)
                return w - abs(u0) / denom

        def dbm_accel(t_sec: float) -> float:
            """Aerodynamic acceleration a(t) in m/s^2."""
            v = dbm_v(t_sec)
            rel = v - w
            return -gamma * rel * abs(rel) * 1000.0  # convert km/s^2 to m/s^2

        def solve_dbm_transit_sec(target_dist_km: float) -> float:
            """Solves for transit time t such that R(t) = target_dist_km via Newton-Raphson."""
            if target_dist_km <= r0_km:
                return 0.0
            # Initial guess based on mean velocity
            v_mean = max(300.0, (v_initial_kms + w) / 2.0)
            t = (target_dist_km - r0_km) / v_mean
            for _ in range(25):
                r_val = dbm_r(t)
                v_val = max(100.0, dbm_v(t))
                f = r_val - target_dist_km
                if abs(f) < 100.0:  # within 100 km
                    break
                t = t - f / v_val
                if t < 0:
                    t = 3600.0
            return max(0.0, t)

        # Solve transit to Sun-Earth L1 and Earth
        t_sec_l1 = solve_dbm_transit_sec(cls.L1_DIST_KM)
        t_sec_earth = solve_dbm_transit_sec(cls.AU_KM)

        transit_l1_hours = t_sec_l1 / 3600.0
        transit_earth_hours = t_sec_earth / 3600.0

        v_arrival_l1 = dbm_v(t_sec_l1)
        v_arrival_earth = dbm_v(t_sec_earth)

        # 3. Gopalswamy et al. (2001, JGR 106, 29207) empirical CME arrival model: constant
        # effective acceleration a = 2.193 - 0.0054 u (m/s^2, u in km/s) that ceases at
        # 0.76 AU, constant speed afterwards. (The earlier value here was distance over a
        # mean of (u + 400)/2 km/s with a 10 h floor, labelled as this model.)
        gopal = cls.gopalswamy_2001_arrival(v_initial_kms, r0_km)

        # 4. Timestamps & Lead Time
        now_dt = datetime.now(timezone.utc)
        if launch_time_iso:
            # An unreadable launch time used to be replaced by the current time without a
            # word, so the arrival times looked valid but referred to now.
            try:
                base_dt = datetime.fromisoformat(launch_time_iso.strip().replace("Z", "+00:00"))
            except ValueError:
                raise ValueError(f"Unreadable launch time {launch_time_iso!r}; use ISO 8601 UTC, e.g. 2024-05-09T09:24")
            base_dt = base_dt.replace(tzinfo=timezone.utc) if base_dt.tzinfo is None else base_dt
        else:
            base_dt = now_dt

        arrival_l1 = base_dt + timedelta(hours=transit_l1_hours)
        arrival_earth = base_dt + timedelta(hours=transit_earth_hours)
        lead_time_min = max(0.0, (transit_earth_hours - transit_l1_hours) * 60.0)

        # 5. Shock Mach number & Compression Ratio
        v_alfven_assumed = 50.0  # km/s typical interplanetary Alfven speed
        mach_shock = max(1.0, (v_arrival_earth - w) / v_alfven_assumed)
        # Rankine-Hugoniot density compression ratio for gamma_mhd = 5/3:
        # r = 4 M^2 / (M^2 + 3)
        compression_ratio = round((4.0 * (mach_shock ** 2)) / ((mach_shock ** 2) + 3.0), 2)

        # Threat classification
        if v_initial_kms >= 1600.0:
            speed_class = "Extreme Hyperbolic CME Shock"
            threat_level = "Severe / Extreme (G4 - G5 Potential)"
            est_kp = 8.5
        elif v_initial_kms >= 1000.0:
            speed_class = "Fast Interplanetary CME"
            threat_level = "Strong Geomagnetic Threat (G3 Potential)"
            est_kp = 7.0
        elif v_initial_kms >= 600.0:
            speed_class = "Moderate CME Wavefront"
            threat_level = "Moderate Storm Potential (G1 - G2 Potential)"
            est_kp = 5.5
        else:
            speed_class = "Slow CME / Solar Wind Entrained"
            threat_level = "Quiet / Minor Disturbance (G0 - G1)"
            est_kp = 3.0

        return {
            "initial_speed_kms": round(v_initial_kms, 1),
            "v_arrival_l1_kms": round(v_arrival_l1, 1),
            "v_arrival_earth_kms": round(v_arrival_earth, 1),
            "speed_classification": speed_class,
            "threat_level": threat_level,
            "estimated_kp": est_kp,
            "model": "Vršnak et al. (2013) Drag-Based Model (DBM)",
            "ambient_solar_wind_kms": round(w, 1),
            "ambient_wind_kms": round(w, 1),
            "drag_parameter_gamma": gamma,
            "initial_accel_ms2": round(dbm_accel(0), 4),
            "transit_to_l1_hours": round(transit_l1_hours, 1),
            "transit_to_earth_hours": round(transit_earth_hours, 1),
            "l1_to_earth_lead_time_minutes": round(lead_time_min, 1),
            "shock_mach_number": round(mach_shock, 2),
            "shock_compression_ratio": compression_ratio,
            "gopalswamy_2001_transit_hours": gopal["transit_hours"],
            "gopalswamy_2001_arrival_speed_kms": gopal["arrival_speed_kms"],
            "gopalswamy_2001_acceleration_ms2": gopal["acceleration_ms2"],
            "gopalswamy_2001_earth_arrival": (base_dt + timedelta(hours=gopal["transit_hours"])).strftime("%Y-%m-%d %H:%M:%S UTC")
                                             if gopal["transit_hours"] is not None else None,
            "assumptions": [
                "Plane-of-sky speed from two heights; no correction for projection (halo CMEs are faster along the Sun-Earth line).",
                "Shock Mach number and compression are rough estimates: (arrival speed - ambient wind) / 50 km/s (assumed Alfven speed) and the gas-dynamic jump 4M^2/(M^2 + 3).",
                "Estimated Kp and threat level are speed categories (600 / 1000 / 1600 km/s), not a forecast model.",
            ],
            "predicted_l1_arrival": arrival_l1.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "predicted_earth_arrival": arrival_earth.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "start_height_rsun": r2_rsun,  # the trajectory and its transit times start here
            "measurement_span_solar_radii": round(r2_rsun - r1_rsun, 2),
            "measurement_dt_minutes": dt_minutes
        }
