"""
Orbital mechanics and 3D coordinate modeling for Sun-Earth Lagrange points
and space weather missions.
"""
import math
from typing import Dict, List, Any

class OrbitalMechanics:
    """Computes coordinates and halo orbit paths in GSE/rotating reference frame."""

    AU_KM = 149597870.7
    L1_OFFSET_KM = 1496000.0  # ~1.5 million km from Earth towards Sun
    EARTH_GEO_KM = 42164.0

    @classmethod
    def get_lagrange_points(cls) -> Dict[str, Dict[str, Any]]:
        """Returns fundamental Sun-Earth Lagrange point coordinates (in million km relative to Earth)."""
        return {
            "L1": {
                "name": "Sun-Earth L1",
                "x_mkm": -1.496,  # 1.5 Mkm Sunward (-X in GSE)
                "y_mkm": 0.0,
                "z_mkm": 0.0,
                "desc": "Gravitational equilibrium point upstream of Earth. Uninterrupted solar wind view ~1 hour before hitting Earth."
            },
            "L2": {
                "name": "Sun-Earth L2",
                "x_mkm": 1.496,   # 1.5 Mkm anti-Sunward (+X in GSE)
                "y_mkm": 0.0,
                "z_mkm": 0.0,
                "desc": "Deep space point behind Earth (home of JWST, Euclid)."
            },
            "L4": {
                "name": "Sun-Earth L4",
                "x_mkm": -74.8,
                "y_mkm": 129.5,
                "z_mkm": 0.0,
                "desc": "Leading triangular Lagrange point (60° ahead of Earth)."
            },
            "L5": {
                "name": "Sun-Earth L5",
                "x_mkm": -74.8,
                "y_mkm": -129.5,
                "z_mkm": 0.0,
                "desc": "Trailing triangular Lagrange point (60° behind Earth - early warning of solar active regions rotating into view)."
            }
        }

    @classmethod
    def get_satellite_orbits(cls, num_points: int = 60) -> Dict[str, Dict[str, Any]]:
        """
        Generates 3D orbit tracks (in GSE frame, 1000s of km relative to Earth).
        Uses parametric Halo & Lissajous approximations for L1 satellites.
        """
        orbits = {}

        # 1. DSCOVR (Lissajous orbit around L1)
        # Period ~ 180 days, Ax ~ 50k km, Ay ~ 280k km, Az ~ 160k km
        dscovr_path = []
        for i in range(num_points):
            phi = 2 * math.pi * (i / num_points)
            x = -1496.0 + 45.0 * math.cos(2 * phi)
            y = 280.0 * math.sin(phi)
            z = 160.0 * math.sin(2 * phi + 0.5)
            dscovr_path.append({"x": round(x, 1), "y": round(y, 1), "z": round(z, 1)})
        orbits["DSCOVR"] = {
            "name": "DSCOVR",
            "type": "Lissajous Orbit at L1",
            "path": dscovr_path,
            "current_pos": dscovr_path[int(num_points * 0.25)],
            "color": "#3b82f6"
        }

        # 2. ACE (Halo orbit around L1)
        # Ax ~ 80k km, Ay ~ 210k km, Az ~ 140k km
        ace_path = []
        for i in range(num_points):
            phi = 2 * math.pi * (i / num_points)
            x = -1480.0 + 60.0 * math.cos(2 * phi)
            y = 210.0 * math.sin(phi + 1.2)
            z = 140.0 * math.cos(phi + 1.2)
            ace_path.append({"x": round(x, 1), "y": round(y, 1), "z": round(z, 1)})
        orbits["ACE"] = {
            "name": "ACE",
            "type": "Halo Orbit at L1",
            "path": ace_path,
            "current_pos": ace_path[int(num_points * 0.65)],
            "color": "#10b981"
        }

        # 3. Aditya-L1 (ISRO Halo Orbit around L1)
        # Halo orbit with Ay ~ 240k km, Az ~ 150k km
        aditya_path = []
        for i in range(num_points):
            phi = 2 * math.pi * (i / num_points)
            x = -1510.0 + 50.0 * math.cos(2 * phi + 0.8)
            y = 240.0 * math.sin(phi + 2.4)
            z = -150.0 * math.cos(phi + 2.4)
            aditya_path.append({"x": round(x, 1), "y": round(y, 1), "z": round(z, 1)})
        orbits["ADITYA_L1"] = {
            "name": "Aditya-L1",
            "type": "Halo Orbit at L1",
            "path": aditya_path,
            "current_pos": aditya_path[int(num_points * 0.40)],
            "color": "#f59e0b"
        }

        # 4. WIND (L1 Baseline Orbit)
        wind_path = []
        for i in range(num_points):
            phi = 2 * math.pi * (i / num_points)
            x = -1520.0 + 70.0 * math.cos(2 * phi + 1.5)
            y = 190.0 * math.sin(phi + 3.14)
            z = 120.0 * math.cos(phi + 3.14)
            wind_path.append({"x": round(x, 1), "y": round(y, 1), "z": round(z, 1)})
        orbits["WIND"] = {
            "name": "WIND",
            "type": "L1 Orbit",
            "path": wind_path,
            "current_pos": wind_path[int(num_points * 0.85)],
            "color": "#06b6d4"
        }

        # 5. SOHO (L1 Halo Orbit)
        soho_path = []
        for i in range(num_points):
            phi = 2 * math.pi * (i / num_points)
            x = -1500.0 + 40.0 * math.cos(2 * phi)
            y = 200.0 * math.sin(phi + 0.5)
            z = 110.0 * math.cos(phi + 0.5)
            soho_path.append({"x": round(x, 1), "y": round(y, 1), "z": round(z, 1)})
        orbits["SOHO"] = {
            "name": "SOHO",
            "type": "Halo Orbit at L1",
            "path": soho_path,
            "current_pos": soho_path[int(num_points * 0.10)],
            "color": "#8b5cf6"
        }

        # 6. GOES-16 (Geostationary Orbit around Earth ~ 42.164k km)
        goes_path = []
        for i in range(num_points):
            phi = 2 * math.pi * (i / num_points)
            x = 42.164 * math.cos(phi)
            y = 42.164 * math.sin(phi)
            z = 0.0
            goes_path.append({"x": round(x, 1), "y": round(y, 1), "z": round(z, 1)})
        orbits["GOES_16"] = {
            "name": "GOES-16",
            "type": "Geostationary Orbit (~35,786 km alt)",
            "path": goes_path,
            "current_pos": goes_path[int(num_points * 0.75)],
            "color": "#ec4899"
        }

        # 7. STEREO-A (Heliocentric Orbit ahead of Earth, 0.96 AU)
        # Scaled to represent relative geometry
        stereo_path = []
        for i in range(num_points):
            phi = 2 * math.pi * (i / num_points) * 0.3 + 0.4
            # Approximately 18-24 degrees ahead in orbit
            x = -12000.0 + 1000.0 * math.cos(phi)
            y = 35000.0 + 1500.0 * math.sin(phi)
            z = 500.0 * math.sin(phi)
            stereo_path.append({"x": round(x, 1), "y": round(y, 1), "z": round(z, 1)})
        orbits["STEREO_A"] = {
            "name": "STEREO-A",
            "type": "Heliocentric Orbit (~21° ahead)",
            "path": stereo_path,
            "current_pos": stereo_path[0],
            "color": "#f97316"
        }

        return orbits
