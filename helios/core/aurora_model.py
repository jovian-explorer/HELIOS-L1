"""
Auroral oval dynamics and geomagnetic storm ring current (Dst) forecasting engine.
Implements Feldstein/Starkov auroral oval empirical boundary models and
Burton-McPherron-O'Brien Dst ring current injection dynamics.
"""
import math
from typing import Dict, List, Any, Tuple

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

    @staticmethod
    def simulate_dst_evolution(telemetry: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Simulate Disturbance Storm Time (Dst) ring current evolution using the
        Burton et al. (1975) & O'Brien-McPherron (2000) differential equation:
        d(Dst*)/dt = Q(t) - Dst* / tau
        """
        if not telemetry:
            return []

        dst_current = -5.0
        decay_tau_hours = 7.7
        dt_hours = 5.0 / 60.0

        results = []
        for row in telemetry:
            v = row.get("speed", 400.0) or 400.0
            bz = row.get("bz_gsm", 0.0) or 0.0
            pdyn = row.get("dynamic_pressure", 2.0) or 2.0

            ey = -v * bz * 1e-3

            if ey > 0.5:
                q_injection = -4.4 * (ey - 0.5)
            else:
                q_injection = 0.0

            d_dst = (q_injection - (dst_current / decay_tau_hours)) * dt_hours
            dst_current += d_dst

            p_term = 7.26 * math.sqrt(max(0.1, pdyn)) - 11.0
            total_dst = round(dst_current + p_term, 1)

            results.append({
                "time_tag": row.get("time_tag", ""),
                "dst_predicted_nt": total_dst,
                "ey_electric_field_mvm": round(ey, 2),
                "storm_category": (
                    "Extreme Superstorm (Dst <= -300)" if total_dst <= -300 else
                    "Intense Storm (Dst <= -100)" if total_dst <= -100 else
                    "Moderate Storm (Dst <= -50)" if total_dst <= -50 else
                    "Weak / Quiet (Dst > -50)"
                )
            })

        return results
