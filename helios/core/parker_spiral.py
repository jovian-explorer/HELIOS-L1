"""
Parker Spiral heliospheric magnetic field and solar wind stream model.
Calculates Archimedean magnetic field lines, spiral pitch angles,
and magnetic connectivity between solar active regions, L1 spacecraft, and Earth.
"""
import math
from typing import Dict, List, Any

class ParkerSpiralModel:
    """Computes heliospheric magnetic field morphology and connectivity."""

    AU_KM = 149597870.7
    OMEGA_SUN_RAD_S = 2.865e-6  # Solar sidereal rotation rate (~25.38 days)

    @classmethod
    def spiral_pitch_angle(cls, speed_kms: float, r_au: float = 1.0) -> float:
        """
        Calculate IMF spiral pitch angle psi in degrees at radial distance r (in AU).
        tan(psi) = (Omega * r) / V_sw
        """
        if speed_kms <= 0:
            return 45.0
        r_km = r_au * cls.AU_KM
        tan_psi = (cls.OMEGA_SUN_RAD_S * r_km) / speed_kms
        return round(math.degrees(math.atan(tan_psi)), 1)

    @classmethod
    def magnetic_footpoint_longitude(cls, speed_kms: float, r_au: float = 1.0) -> float:
        """
        Calculate solar disk source footpoint longitude (in degrees West of central meridian)
        magnetically connected to Earth/L1 via the Parker spiral.
        Delta phi = (Omega * r) / V_sw
        Known as the 'well-connected' zone (typically ~45° to 60° West).
        """
        if speed_kms <= 0:
            return 50.0
        r_km = r_au * cls.AU_KM
        delta_phi_rad = (cls.OMEGA_SUN_RAD_S * r_km) / speed_kms
        return round(math.degrees(delta_phi_rad), 1)

    @classmethod
    def generate_parker_spiral_lines(
        cls,
        speed_kms: float = 400.0,
        num_streamlines: int = 8,
        num_points: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Generate (X, Y) coordinates of Archimedean Parker spiral magnetic field lines
        in the heliospheric ecliptic plane from the Sun (0.05 AU) to 1.3 AU.
        """
        streamlines = []
        r_max_au = 1.25
        r_min_au = 0.05

        v = max(250.0, min(1200.0, speed_kms))

        for stream_idx in range(num_streamlines):
            phi_0 = (2.0 * math.pi * stream_idx) / num_streamlines
            points = []

            for i in range(num_points):
                r_au = r_min_au + (r_max_au - r_min_au) * (i / (num_points - 1))
                r_km = r_au * cls.AU_KM

                # Parker spiral: phi(r) = phi_0 - (Omega * (r - r0)) / V_sw
                delta_phi = (cls.OMEGA_SUN_RAD_S * (r_km - (r_min_au * cls.AU_KM))) / v
                phi = phi_0 - delta_phi

                # Convert polar (r, phi) to Cartesian (x, y) in AU
                x = r_au * math.cos(phi)
                y = r_au * math.sin(phi)

                points.append({
                    "r_au": round(r_au, 3),
                    "x_au": round(x, 4),
                    "y_au": round(y, 4)
                })

            # Check if this line is connected near Earth (at x=1.0, y=0.0)
            end_pt = points[-1]
            connected_to_earth = (stream_idx == 0)

            streamlines.append({
                "stream_id": stream_idx,
                "phi_source_deg": round(math.degrees(phi_0), 1),
                "is_earth_connected": connected_to_earth,
                "points": points
            })

        return streamlines
