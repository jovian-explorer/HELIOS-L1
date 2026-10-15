"""
Orbital mechanics and 3D coordinate modeling for Sun-Earth Lagrange points
and space weather missions, powered by NASA JPL NAIF SPICE.
"""
import math
from typing import Dict, Any, Optional

try:
    from helios.core.spice_engine import get_spice_engine
    SPICE_ENGINE_AVAILABLE = True
except ImportError:
    SPICE_ENGINE_AVAILABLE = False


class OrbitalMechanics:
    """Computes coordinates and halo orbit paths in GSE/rotating reference frame."""


    @classmethod
    def get_lagrange_points(cls) -> Dict[str, Dict[str, Any]]:
        """Returns fundamental Sun-Earth Lagrange point coordinates (in million km relative to Earth)."""
        return {
            "L1": {
                "name": "Sun-Earth L1",
                "x_mkm": -1.498,  # Sunward (-X in the view); circular restricted three-body problem,
                # mu = (Earth + Moon) / total = 3.0404e-6: 1.4976 and 1.5077 million km
                "y_mkm": 0.0,
                "z_mkm": 0.0,
                "desc": "Gravitational equilibrium point upstream of Earth. Uninterrupted solar wind view ~1 hour before hitting Earth."
            },
            "L2": {
                "name": "Sun-Earth L2",
                "x_mkm": 1.508,   # anti-Sunward (+X in the view)
                "y_mkm": 0.0,
                "z_mkm": 0.0,
                "desc": "Deep space point behind Earth (home of JWST, Euclid)."
            },
            "L4": {
                "name": "Sun-Earth L4",
                "x_mkm": -74.8,
                # Earth moves towards -Y in GSE (+Y is dusk), so the leading point is at -Y.
                "y_mkm": -129.5,
                "z_mkm": 0.0,
                "desc": "Leading triangular Lagrange point (60° ahead of Earth)."
            },
            "L5": {
                "name": "Sun-Earth L5",
                "x_mkm": -74.8,
                "y_mkm": 129.5,
                "z_mkm": 0.0,
                "desc": "Trailing triangular Lagrange point (60° behind Earth - early warning of solar active regions rotating into view)."
            }
        }

    # Spacecraft of the L1 view: (key, colour). Positions and tracks come from their ephemeris
    # (helios.core.ephemeris); a spacecraft without one is listed with no position.
    L1_VIEW = [("DSCOVR", "#3b82f6"), ("ACE", "#10b981"), ("ADITYA_L1", "#f59e0b"), ("WIND", "#06b6d4"),
               ("SOHO", "#8b5cf6"), ("SWFO_L1", "#f43f5e"), ("IMAP", "#84cc16"), ("GOES_19", "#ec4899")]

    @classmethod
    def get_satellite_orbits(cls, num_points: int = 60, epoch_utc: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Tracks and current positions in GSE (1000 km, Sun at -X as drawn) from the spacecraft
        ephemerides: 180 days centred on the epoch for the L1 spacecraft, one day for GOES.
        The tracks used to be invented halo curves, 235 000-875 000 km from the real ones.
        """
        if not SPICE_ENGINE_AVAILABLE:
            return {}
        engine = get_spice_engine()

        def gse(p):  # GSE km -> drawn 1000 km with the Sun at -X
            return {"x": round(-p[0] / 1000.0, 1), "y": round(p[1] / 1000.0, 1), "z": round(p[2] / 1000.0, 1)}

        fleet = engine.get_fleet_states([k for k, _ in cls.L1_VIEW], epoch_utc=epoch_utc)["fleet"]  # in parallel
        orbits = {}
        for key, colour in cls.L1_VIEW:
            st = fleet[key]
            track = engine.get_orbit_trajectory(key, num_points=num_points, epoch_utc=epoch_utc) if st.get("available") else []
            g = st.get("gse_coordinates")
            orbits[key] = {
                "name": st["name"],
                "type": st["orbit_type"],
                "path": [gse((p["gse_x_km"], p["gse_y_km"], p["gse_z_km"])) for p in track],
                "current_pos": gse((g["x_km"], g["y_km"], g["z_km"])) if g else None,
                "color": colour,
                "spice_telemetry": st if st.get("available") else None,
                "position_note": st.get("position_source") or st.get("reason"),
            }
        return orbits
