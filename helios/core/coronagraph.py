"""
Coronagraph imagery pipeline and CME kinematic shock speed & transit analyzer.
Integrates SOHO/LASCO C2/C3 and GOES/SUVI EUV image feeds (Aditya-L1 VELC has no public real-time feed),
and empirical CME deceleration and shock arrival forecasting.
"""
import math
from datetime import datetime, timezone, timedelta
from typing import Dict, Any, Optional
from helios.core.constants import AU_KM, R_SUN_KM

# Drag-based model defaults of the Hvar Observatory DBM tools (Dumbovic et al. 2021, Front.
# Astron. Space Sci. 8, 639986, doi:10.3389/fspas.2021.639986): gamma = 0.2e-7 /km with
# w = 450 km/s, "found as an optimal value" in the statistics of Vrsnak et al. (2013, 2014),
# and a start at >= 20 R_sun. The earlier default 1e-7 /km slowed every CME to the ambient
# wind (on 44 DONKI CMEs of 2023-2025: shocks at L1 predicted +9.4 h late on average, mean
# absolute error 15.5 h; with these values -6.9 h and 14.4 h, close to the ~14 h reported
# for the model by Vrsnak et al. 2014).
DBM_GAMMA_PER_KM = 0.2e-7
DBM_W_KMS = 450.0
DBM_START_RSUN = 20.0


def dbm_distance(t_sec: float, r0_km: float, v0_kms: float, w_kms: float, gamma: float) -> float:
    """Drag-based model (Vrsnak et al. 2013): heliocentric distance (km) t seconds after r0 at speed v0."""
    u0 = v0_kms - w_kms
    if abs(u0) < 1e-4:
        return r0_km + w_kms * t_sec
    s = 1.0 if u0 > 0 else -1.0
    return r0_km + w_kms * t_sec + s / gamma * math.log(max(1e-12, 1.0 + gamma * abs(u0) * t_sec))


def dbm_speed(t_sec: float, v0_kms: float, w_kms: float, gamma: float) -> float:
    """Drag-based model speed (km/s) t seconds after the start at v0."""
    u0 = v0_kms - w_kms
    if abs(u0) < 1e-4:
        return w_kms
    return w_kms + u0 / max(1e-12, 1.0 + gamma * abs(u0) * t_sec)


def dbm_transit_seconds(r0_km: float, v0_kms: float, w_kms: float, gamma: float, target_km: float) -> float:
    """Time (s) for the drag-based model started at r0 with v0 to reach target_km (Newton-Raphson, 100 km)."""
    if target_km <= r0_km:
        return 0.0
    t = (target_km - r0_km) / max(300.0, (v0_kms + w_kms) / 2.0)
    for _ in range(25):
        f = dbm_distance(t, r0_km, v0_kms, w_kms, gamma) - target_km
        if abs(f) < 100.0:
            break
        t -= f / max(100.0, dbm_speed(t, v0_kms, w_kms, gamma))
        if t < 0:
            t = 3600.0
    return max(0.0, t)


class CoronagraphAnalyzer:
    """CME expansion kinematics."""

    R_SUN_KM = R_SUN_KM
    AU_KM = AU_KM
    L1_DIST_KM = AU_KM - 1496000.0  # ~1.481e8 km from Sun

    @classmethod
    def gopalswamy_2001_arrival(cls, speed_kms: float, r0_km: float = 0.0) -> Dict[str, Any]:
        """
        Gopalswamy et al. (2001) empirical arrival of the ejecta (ICME, not the shock ahead of
        it): a = 2.193 - 0.0054 u m/s^2 from the Sun until 0.76 AU, then constant speed to
        1 AU. As in the paper the motion starts at the Sun; the hours returned count from the
        time the model CME passes r0 (the measured height), so they follow the measurement.
        """
        a = (2.193 - 0.0054 * speed_kms) / 1000.0  # km/s^2

        def time_to(d_km: float) -> Optional[float]:
            if abs(a) < 1e-12:
                return d_km / speed_kms
            disc = speed_kms ** 2 + 2.0 * a * d_km
            return None if disc < 0 else (-speed_kms + math.sqrt(disc)) / a

        t1 = time_to(0.76 * cls.AU_KM)
        if t1 is None:  # the CME would stop before 0.76 AU: outside the model
            return {"transit_hours": None, "arrival_speed_kms": None, "acceleration_ms2": round(a * 1000.0, 3)}
        v1 = speed_kms + a * t1
        t = t1 + 0.24 * cls.AU_KM / v1 - time_to(min(r0_km, 0.76 * cls.AU_KM))
        return {"transit_hours": round(t / 3600.0, 1), "arrival_speed_kms": round(v1, 1),
                "acceleration_ms2": round(a * 1000.0, 3)}

    @classmethod
    def calculate_cme_kinematics(
        cls,
        r1_rsun: float,
        r2_rsun: float,
        dt_minutes: float,
        launch_time_iso: str = None,
        ambient_wind_kms: float = DBM_W_KMS,
        gamma_drag: float = DBM_GAMMA_PER_KM
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

        # 2. Vršnak et al. (2013) Drag-Based Model (DBM), w = ambient solar wind speed and
        # gamma = drag parameter (1/km), as given (they were clamped to 250-900 km/s and
        # 0.1-3e-7 /km without a word). The model applies beyond ~20 R_sun: below that the
        # measured speed is carried at constant speed to 20 R_sun, where the model starts.
        w = float(ambient_wind_kms)
        gamma = float(gamma_drag)
        if w <= 0 or gamma <= 0:
            return {"error": "The ambient wind speed and the drag parameter must be positive."}
        start_rsun = max(r2_rsun, DBM_START_RSUN)
        t_coast = (start_rsun - r2_rsun) * cls.R_SUN_KM / v_initial_kms
        r0_km = start_rsun * cls.R_SUN_KM
        dbm_v = lambda t_sec: dbm_speed(t_sec, v_initial_kms, w, gamma)

        def dbm_accel(t_sec: float) -> float:
            """Aerodynamic acceleration a(t) in m/s^2."""
            rel = dbm_v(t_sec) - w
            return -gamma * rel * abs(rel) * 1000.0  # convert km/s^2 to m/s^2

        def solve_dbm_transit_sec(target_dist_km: float) -> float:
            return dbm_transit_seconds(r0_km, v_initial_kms, w, gamma, target_dist_km)

        # Solve transit to Sun-Earth L1 and Earth
        t_sec_l1 = solve_dbm_transit_sec(cls.L1_DIST_KM)
        t_sec_earth = solve_dbm_transit_sec(cls.AU_KM)

        transit_l1_hours = (t_coast + t_sec_l1) / 3600.0
        transit_earth_hours = (t_coast + t_sec_earth) / 3600.0

        v_arrival_l1 = dbm_v(t_sec_l1)
        v_arrival_earth = dbm_v(t_sec_earth)

        # 3. Gopalswamy et al. (2001, JGR 106, 29207) empirical CME arrival model: constant
        # effective acceleration a = 2.193 - 0.0054 u (m/s^2, u in km/s) that ceases at
        # 0.76 AU, constant speed afterwards. (The earlier value here was distance over a
        # mean of (u + 400)/2 km/s with a 10 h floor, labelled as this model.)
        gopal = cls.gopalswamy_2001_arrival(v_initial_kms, r2_rsun * cls.R_SUN_KM)

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

        return {
            "initial_speed_kms": round(v_initial_kms, 1),
            "v_arrival_l1_kms": round(v_arrival_l1, 1),
            "v_arrival_earth_kms": round(v_arrival_earth, 1),
            "model": "Vršnak et al. (2013) Drag-Based Model (DBM)",
            "ambient_solar_wind_kms": round(w, 1),
            "ambient_wind_kms": round(w, 1),
            "drag_parameter_gamma": gamma,
            "initial_accel_ms2": round(dbm_accel(0), 4),
            "transit_to_l1_hours": round(transit_l1_hours, 1),
            "transit_to_earth_hours": round(transit_earth_hours, 1),
            "l1_to_earth_lead_time_minutes": round(lead_time_min, 1),
            "gopalswamy_2001_transit_hours": gopal["transit_hours"],
            "gopalswamy_2001_arrival_speed_kms": gopal["arrival_speed_kms"],
            "gopalswamy_2001_acceleration_ms2": gopal["acceleration_ms2"],
            "gopalswamy_2001_earth_arrival": (base_dt + timedelta(hours=gopal["transit_hours"])).strftime("%Y-%m-%d %H:%M:%S UTC")
                                             if gopal["transit_hours"] is not None else None,
            "assumptions": [
                "Plane-of-sky speed from two heights; no correction for projection (halo CMEs are faster along the Sun-Earth line).",
                "The drag-based model follows the CME front from 20 R_sun (constant speed before); the shock ahead of it can arrive hours earlier. Typical arrival-time errors of such models are about 10-14 h (Vrsnak et al. 2014; Dumbovic et al. 2021).",
                "The Gopalswamy et al. (2001) time is the arrival of the ejecta, which follows the shock.",
                "One drag parameter for every CME: the errors grow with speed. On 44 DONKI CMEs above 1000 km/s the predicted shock arrivals at L1 were 11 h early on average (DONKI 3D speeds), while extreme plane-of-sky cases come out late (Halloween 2003 preset 32 h against ~18.5 h observed). A speed-dependent gamma (Calogovic et al. 2021: 0.5, 0.2, 0.1e-7 /km below 600, 600-1000, above 1000 km/s) made those fast CMEs worse here (18 h early; all CMEs: mean absolute error 15.9 h against 14.4 h), as it did in that paper (17.3 h against 14.5 h with a fixed gamma).",
            ],
            "predicted_l1_arrival": arrival_l1.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "predicted_earth_arrival": arrival_earth.strftime("%Y-%m-%d %H:%M:%S UTC"),
            "start_height_rsun": r2_rsun,  # transit times count from the time of this height
            "dbm_start_rsun": start_rsun,
            "measurement_span_solar_radii": round(r2_rsun - r1_rsun, 2),
            "measurement_dt_minutes": dt_minutes
        }
