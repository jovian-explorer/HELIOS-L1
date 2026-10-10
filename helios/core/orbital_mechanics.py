"""
Orbital mechanics and 3D coordinate modeling for Sun-Earth Lagrange points
and space weather missions, powered by NASA JPL NAIF SPICE.
"""
import math
from typing import Dict, List, Any, Optional

try:
    from helios.core.spice_engine import get_spice_engine
    SPICE_ENGINE_AVAILABLE = True
except ImportError:
    SPICE_ENGINE_AVAILABLE = False


class OrbitalMechanics:
    """Computes coordinates and halo orbit paths in GSE/rotating reference frame."""

    AU_KM = 149597870.7

    @classmethod
    def get_lagrange_points(cls) -> Dict[str, Dict[str, Any]]:
        """Returns fundamental Sun-Earth Lagrange point coordinates (in million km relative to Earth)."""
        return {
            "L1": {
                "name": "Sun-Earth L1",
                "x_mkm": -1.496,  # 1.5 Mkm Sunward (-X in GSE visualizer)
                "y_mkm": 0.0,
                "z_mkm": 0.0,
                "desc": "Gravitational equilibrium point upstream of Earth. Uninterrupted solar wind view ~1 hour before hitting Earth."
            },
            "L2": {
                "name": "Sun-Earth L2",
                "x_mkm": 1.496,   # 1.5 Mkm anti-Sunward (+X in GSE visualizer)
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

    @staticmethod
    def _far_position(state: Optional[Dict[str, Any]], marker: Dict[str, float]) -> Dict[str, Any]:
        """
        Heliocentric spacecraft: current_pos is the orbit model's GSE position (1000 km, Sun at
        -X like the other tracks); display_pos is the marker on the schematic near-Earth track,
        which cannot show positions an AU away (current_pos used to be that marker).
        """
        if not state:
            return {"current_pos": None, "display_pos": marker}
        g = state["gse_coordinates"]
        return {"current_pos": {"x": round(-g["x_km"] / 1000.0, 1), "y": round(g["y_km"] / 1000.0, 1),
                                "z": round(g["z_km"] / 1000.0, 1)},
                "display_pos": marker}

    @classmethod
    def get_satellite_orbits(cls, num_points: int = 60, epoch_utc: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
        """
        Generates 3D orbit tracks (in GSE frame, 1000s of km relative to Earth).
        Uses parametric Halo & Lissajous approximations for L1 satellites coupled
        with real-time NASA JPL SPICE state computation.
        """
        spice_engine = get_spice_engine() if SPICE_ENGINE_AVAILABLE else None
        orbits = {}

        # 1. DSCOVR (Lissajous orbit around L1)
        dscovr_path = []
        for i in range(num_points):
            phi = 2 * math.pi * (i / num_points)
            x = -1496.0 + 45.0 * math.cos(2 * phi)
            y = 280.0 * math.sin(phi)
            z = 160.0 * math.sin(2 * phi + 0.5)
            dscovr_path.append({"x": round(x, 1), "y": round(y, 1), "z": round(z, 1)})

        dscovr_st = spice_engine.get_spacecraft_state("DSCOVR", epoch_utc=epoch_utc) if spice_engine else None
        dscovr_cur = {
            "x": round(-abs(dscovr_st["gse_coordinates"]["x_km"]) / 1000.0, 1),
            "y": round(dscovr_st["gse_coordinates"]["y_km"] / 1000.0, 1),
            "z": round(dscovr_st["gse_coordinates"]["z_km"] / 1000.0, 1),
        } if dscovr_st else dscovr_path[int(num_points * 0.25)]

        orbits["DSCOVR"] = {
            "name": "DSCOVR",
            "type": "Lissajous Orbit at L1",
            "path": dscovr_path,
            "current_pos": dscovr_cur,
            "color": "#3b82f6",
            "spice_telemetry": dscovr_st
        }

        # 2. ACE (Halo orbit around L1)
        ace_path = []
        for i in range(num_points):
            phi = 2 * math.pi * (i / num_points)
            x = -1480.0 + 60.0 * math.cos(2 * phi)
            y = 210.0 * math.sin(phi + 1.2)
            z = 140.0 * math.cos(phi + 1.2)
            ace_path.append({"x": round(x, 1), "y": round(y, 1), "z": round(z, 1)})

        ace_st = spice_engine.get_spacecraft_state("ACE", epoch_utc=epoch_utc) if spice_engine else None
        ace_cur = {
            "x": round(-abs(ace_st["gse_coordinates"]["x_km"]) / 1000.0, 1),
            "y": round(ace_st["gse_coordinates"]["y_km"] / 1000.0, 1),
            "z": round(ace_st["gse_coordinates"]["z_km"] / 1000.0, 1),
        } if ace_st else ace_path[int(num_points * 0.65)]

        orbits["ACE"] = {
            "name": "ACE",
            "type": "Halo Orbit at L1",
            "path": ace_path,
            "current_pos": ace_cur,
            "color": "#10b981",
            "spice_telemetry": ace_st
        }

        # 3. Aditya-L1 (ISRO Halo Orbit around L1)
        aditya_path = []
        for i in range(num_points):
            phi = 2 * math.pi * (i / num_points)
            x = -1510.0 + 50.0 * math.cos(2 * phi + 0.8)
            y = 240.0 * math.sin(phi + 2.4)
            z = -150.0 * math.cos(phi + 2.4)
            aditya_path.append({"x": round(x, 1), "y": round(y, 1), "z": round(z, 1)})

        aditya_st = spice_engine.get_spacecraft_state("ADITYA_L1", epoch_utc=epoch_utc) if spice_engine else None
        aditya_cur = {
            "x": round(-abs(aditya_st["gse_coordinates"]["x_km"]) / 1000.0, 1),
            "y": round(aditya_st["gse_coordinates"]["y_km"] / 1000.0, 1),
            "z": round(aditya_st["gse_coordinates"]["z_km"] / 1000.0, 1),
        } if aditya_st else aditya_path[int(num_points * 0.40)]

        orbits["ADITYA_L1"] = {
            "name": "Aditya-L1",
            "type": "Halo Orbit at L1 (ISRO)",
            "path": aditya_path,
            "current_pos": aditya_cur,
            "color": "#f59e0b",
            "spice_telemetry": aditya_st
        }

        # 4. WIND (L1 Baseline Orbit)
        wind_path = []
        for i in range(num_points):
            phi = 2 * math.pi * (i / num_points)
            x = -1520.0 + 70.0 * math.cos(2 * phi + 1.5)
            y = 190.0 * math.sin(phi + 3.14)
            z = 120.0 * math.cos(phi + 3.14)
            wind_path.append({"x": round(x, 1), "y": round(y, 1), "z": round(z, 1)})

        wind_st = spice_engine.get_spacecraft_state("WIND", epoch_utc=epoch_utc) if spice_engine else None
        wind_cur = {
            "x": round(-abs(wind_st["gse_coordinates"]["x_km"]) / 1000.0, 1),
            "y": round(wind_st["gse_coordinates"]["y_km"] / 1000.0, 1),
            "z": round(wind_st["gse_coordinates"]["z_km"] / 1000.0, 1),
        } if wind_st else wind_path[int(num_points * 0.85)]

        orbits["WIND"] = {
            "name": "WIND",
            "type": "L1 Orbit",
            "path": wind_path,
            "current_pos": wind_cur,
            "color": "#06b6d4",
            "spice_telemetry": wind_st
        }

        # 5. SOHO (L1 Halo Orbit)
        soho_path = []
        for i in range(num_points):
            phi = 2 * math.pi * (i / num_points)
            x = -1500.0 + 40.0 * math.cos(2 * phi)
            y = 200.0 * math.sin(phi + 0.5)
            z = 110.0 * math.cos(phi + 0.5)
            soho_path.append({"x": round(x, 1), "y": round(y, 1), "z": round(z, 1)})

        soho_st = spice_engine.get_spacecraft_state("SOHO", epoch_utc=epoch_utc) if spice_engine else None
        soho_cur = {
            "x": round(-abs(soho_st["gse_coordinates"]["x_km"]) / 1000.0, 1),
            "y": round(soho_st["gse_coordinates"]["y_km"] / 1000.0, 1),
            "z": round(soho_st["gse_coordinates"]["z_km"] / 1000.0, 1),
        } if soho_st else soho_path[int(num_points * 0.10)]

        orbits["SOHO"] = {
            "name": "SOHO",
            "type": "Halo Orbit at L1 (ESA/NASA)",
            "path": soho_path,
            "current_pos": soho_cur,
            "color": "#8b5cf6",
            "spice_telemetry": soho_st
        }

        # 6. GOES-16 (Geostationary Orbit around Earth ~ 42.164k km)
        goes_path = []
        for i in range(num_points):
            phi = 2 * math.pi * (i / num_points)
            x = 42.164 * math.cos(phi)
            y = 42.164 * math.sin(phi)
            z = 0.0
            goes_path.append({"x": round(x, 1), "y": round(y, 1), "z": round(z, 1)})

        goes_st = spice_engine.get_spacecraft_state("GOES_16", epoch_utc=epoch_utc) if spice_engine else None
        goes_cur = {
            "x": round(-goes_st["gse_coordinates"]["x_km"] / 1000.0, 1),  # Sun at -X here, as for the others
            "y": round(goes_st["gse_coordinates"]["y_km"] / 1000.0, 1),
            "z": round(goes_st["gse_coordinates"]["z_km"] / 1000.0, 1),
        } if goes_st else goes_path[int(num_points * 0.75)]

        orbits["GOES_16"] = {
            "name": "GOES-16",
            "type": "Geostationary Orbit (~35,786 km alt)",
            "path": goes_path,
            "current_pos": goes_cur,
            "color": "#ec4899",
            "spice_telemetry": goes_st
        }

        # 7. STEREO-A (Heliocentric Orbit ahead of Earth, 0.96 AU)
        stereo_path = []
        for i in range(num_points):
            phi = 2 * math.pi * (i / num_points) * 0.3 + 0.4
            x = -12000.0 + 1000.0 * math.cos(phi)
            y = -35000.0 - 1500.0 * math.sin(phi)  # ahead of Earth: -Y in GSE
            z = 500.0 * math.sin(phi)
            stereo_path.append({"x": round(x, 1), "y": round(y, 1), "z": round(z, 1)})

        stereo_st = spice_engine.get_spacecraft_state("STEREO_A", epoch_utc=epoch_utc) if spice_engine else None
        orbits["STEREO_A"] = {
            "name": "STEREO-A",
            "type": "Heliocentric Orbit (ahead of Earth, schematic track)",
            "path": stereo_path,
            **cls._far_position(stereo_st, stereo_path[0]),
            "color": "#f97316",
            "spice_telemetry": stereo_st
        }

        # 8. Parker Solar Probe (PSP)
        psp_st = spice_engine.get_spacecraft_state("PARKER_SOLAR_PROBE", epoch_utc=epoch_utc) if spice_engine else None
        psp_path = []
        for i in range(num_points):
            phi = 2 * math.pi * (i / num_points)
            r_scale = 35000.0 * (1.0 - 0.88 * math.cos(phi))
            x = -r_scale * math.cos(phi)
            y = r_scale * math.sin(phi) * 0.47
            z = 200.0 * math.sin(phi)
            psp_path.append({"x": round(x, 1), "y": round(y, 1), "z": round(z, 1)})

        orbits["PARKER_SOLAR_PROBE"] = {
            "name": "Parker Solar Probe (PSP)",
            "type": "Inner Heliosphere Perihelion Orbit",
            "path": psp_path,
            **cls._far_position(psp_st, psp_path[0]),
            "color": "#ef4444",
            "spice_telemetry": psp_st
        }

        # 9. Solar Orbiter (SolO)
        solo_st = spice_engine.get_spacecraft_state("SOLAR_ORBITER", epoch_utc=epoch_utc) if spice_engine else None
        solo_path = []
        for i in range(num_points):
            phi = 2 * math.pi * (i / num_points)
            r_scale = 50000.0 * (1.0 - 0.53 * math.cos(phi))
            x = -r_scale * math.cos(phi)
            y = r_scale * math.sin(phi) * 0.85
            z = 8000.0 * math.sin(phi)
            solo_path.append({"x": round(x, 1), "y": round(y, 1), "z": round(z, 1)})

        orbits["SOLAR_ORBITER"] = {
            "name": "Solar Orbiter (SolO)",
            "type": "High-Latitude Heliospheric Science Orbit",
            "path": solo_path,
            **cls._far_position(solo_st, solo_path[0]),
            "color": "#a855f7",
            "spice_telemetry": solo_st
        }

        # Where each position comes from, for the tooltip (it showed every one as GSE fact).
        for key, orb in orbits.items():
            if not orb["spice_telemetry"]:
                orb["position_note"] = "Schematic track, no ephemeris available"
            elif key == "GOES_16":
                orb["position_note"] = "Geostationary over 75.2° W"
            elif "display_pos" in orb:
                orb["position_note"] = "Keplerian orbit from JPL Horizons elements; marker drawn on a schematic track"
            else:
                orb["position_note"] = "Schematic L1 halo orbit: typical size and period, not the spacecraft's measured position"
        return orbits
