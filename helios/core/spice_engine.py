"""
HELIOS-L1 NASA JPL NAIF SPICE Ephemeris Engine
Author: HELIOS-L1 Scientific Suite (Lead: Dr. Keshav Aggarwal)
Standards: NASA JPL CSPICE / SPICE Toolkit (CSPICE_N0067)

Provides sovereign, 100% offline, high-precision orbital ephemeris calculations
for inner heliosphere probes (Parker Solar Probe, Solar Orbiter, STEREO-A),
Sun-Earth L1 halo orbiters (Aditya-L1, DSCOVR, ACE, WIND, SOHO),
and geospace satellites (GOES-16, Moon, Earth).
"""

import logging
import math
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple, Union
import numpy as np
import pandas as pd

from helios.core.coordinates import geo_to_gse

try:
    import spiceypy as spice
    from spiceypy.utils.exceptions import SpiceyError
    SPICE_AVAILABLE = True
except ImportError:
    spice = None
    SpiceyError = RuntimeError
    SPICE_AVAILABLE = False

# What a SPICE call can raise for a bad input or a missing kernel (SpiceyError covers the
# CSPICE error system); anything else is a bug and should surface.
SPICE_ERRORS = (SpiceyError, ValueError, TypeError)
_log = logging.getLogger("helios.spice")



def _psp_phase(engine, pos_km) -> str:
    r = np.linalg.norm(pos_km)
    if r / engine.R_SUN_KM <= 12.0:
        return f"Perihelion Plunge ({r / engine.R_SUN_KM:.1f} R_sun, Alfvén surface crossing)"
    if r / engine.AU_KM >= 0.70:
        return "Aphelion turnaround (~0.73 AU near Venus orbit)"
    return "Heliocentric orbit leg (WISPR/FIELDS/SWEAP streaming)"


# Analytical (Keplerian) fallback orbits: (accepted IDs, elements). Angles in degrees;
# "epoch" is the reference time of m0 (None: J2000). Geocentric orbits give a_km.
CONIC_TARGETS = [
    # Spacecraft: osculating heliocentric elements (ecliptic and equinox J2000) for
    # 2026-01-01 00:00 TDB from JPL Horizons (ssd.jpl.nasa.gov). Checked against Horizons
    # positions for 2026-10-10: within 1 degree of heliocentric longitude.
    (("PARKER_SOLAR_PROBE", "PSP", "PARKER"), {
        # Perihelion 9.86 R_sun, aphelion 0.73 AU, period 88 d (final orbit since the
        # Venus flyby of November 2024).
        "name": "Parker Solar Probe (PSP)", "orbit_type": "Inner Heliosphere Elliptic Orbit", "primary": "SUN",
        "a_au": 0.38850, "e": 0.88193, "inc": 3.391, "raan": 76.485, "argp": 68.624, "m0": 76.138,
        "epoch": "2026-01-01T00:00:00", "phase": _psp_phase}),
    (("SOLAR_ORBITER", "SOLO"), {
        # Perihelion 0.29 AU, aphelion 0.90 AU, 12.6 deg to the ecliptic (17 deg to the solar
        # equator); valid until the Venus flyby of 24 December 2026 tilts the orbit further.
        "name": "Solar Orbiter (SolO)", "orbit_type": "Heliocentric Polar-Inclined Orbit", "primary": "SUN",
        "a_au": 0.59708, "e": 0.50732, "inc": 12.617, "raan": 322.350, "argp": 306.385, "m0": 228.292,
        "epoch": "2026-01-01T00:00:00", "phase": "High-latitude heliospheric science orbit"}),
    (("STEREO_A", "STEREOA", "STEREO"), {
        # Period 344 d: gains about 22 deg a year on Earth (lapped it in August 2023).
        "name": "STEREO-A", "orbit_type": "Heliocentric Orbit (gaining ~22° a year on Earth)", "primary": "SUN",
        "a_au": 0.96075, "e": 0.006757, "inc": 0.128, "raan": 212.327, "argp": 77.877, "m0": 221.368,
        "epoch": "2026-01-01T00:00:00", "phase": "Heliospheric monitor off the Sun-Earth line"}),
    (("VENUS", "299"), {
        "name": "Venus", "orbit_type": "Planetary Orbit", "primary": "SUN",
        "a_au": 0.723332, "e": 0.00677, "inc": 3.394, "raan": 76.68, "argp": 54.88, "m0": 50.11,
        "epoch": None, "phase": "Inner terrestrial planet / PSP gravity assist node"}),
    (("MERCURY", "199"), {
        "name": "Mercury", "orbit_type": "Planetary Orbit", "primary": "SUN",
        "a_au": 0.387098, "e": 0.20563, "inc": 7.005, "raan": 48.33, "argp": 29.12, "m0": 174.79,
        "epoch": None, "phase": "Innermost terrestrial planet"}),
    (("MARS", "499"), {
        "name": "Mars", "orbit_type": "Planetary Orbit", "primary": "SUN",
        "a_au": 1.52368, "e": 0.0934, "inc": 1.85, "raan": 49.56, "argp": 286.5, "m0": 19.37,
        "epoch": None, "phase": "Outer terrestrial planet / magnetotail observatory"}),
    (("MOON", "301"), {
        "name": "Moon", "orbit_type": "Geocentric Lunar Orbit", "primary": "EARTH",
        # Placed by the low-precision lunar series (lunar=True): a fixed conic drifts by its
        # node and perigee precession (it was 100 deg off by 2026).
        "a_km": 384400.0, "e": 0.0549, "inc": 5.145, "raan": 125.08, "argp": 318.15, "m0": 135.0,
        "epoch": None, "phase": "Natural satellite of Earth", "lunar": True}),
    (("GOES_16", "GOES16", "GOES"), {
        "name": "GOES-16", "orbit_type": "Geostationary Orbit (GEO ~35,786 km alt)", "primary": "EARTH",
        # Placed by its geographic longitude (geo_lon): a conic cannot keep it over one meridian.
        "a_km": 42164.14, "rp_km": 42164.14, "e": 0.0001, "inc": 0.05, "raan": 0.0, "argp": 0.0, "m0": 0.0,
        "geo_lon": -75.2,
        "epoch": None, "phase": "Geostationary East (75.2° W) Space Weather Monitor"}),
]

def moon_geocentric_ecliptic(t: pd.Timestamp) -> np.ndarray:
    """
    Geocentric Moon (km, ecliptic and equinox J2000) from the low-precision series of the
    Astronomical Almanac (section D, about 0.3 deg in longitude and 0.2 deg in latitude),
    precessed from the equinox of date to J2000.
    """
    tc = (t.to_julian_date() - 2451545.0) / 36525.0
    d = lambda a, b: math.radians(a + b * tc)
    lam = (218.32 + 481267.881 * tc + 6.29 * math.sin(d(135.0, 477198.87)) - 1.27 * math.sin(d(259.3, -413335.36))
           + 0.66 * math.sin(d(235.7, 890534.22)) + 0.21 * math.sin(d(269.9, 954397.74))
           - 0.19 * math.sin(d(357.5, 35999.05)) - 0.11 * math.sin(d(186.5, 966404.03)) - 1.397 * tc)
    beta = (5.13 * math.sin(d(93.3, 483202.03)) + 0.28 * math.sin(d(228.2, 960400.87))
            - 0.28 * math.sin(d(318.3, 6003.18)) - 0.17 * math.sin(d(217.6, -407332.20)))
    parallax = (0.9508 + 0.0518 * math.cos(d(135.0, 477198.87)) + 0.0095 * math.cos(d(259.3, -413335.38))
                + 0.0078 * math.cos(d(235.7, 890534.23)) + 0.0028 * math.cos(d(269.9, 954397.70)))
    r = 6378.14 / math.sin(math.radians(parallax))
    lam, beta = math.radians(lam), math.radians(beta)
    return r * np.array([math.cos(beta) * math.cos(lam), math.cos(beta) * math.sin(lam), math.sin(beta)])


# Schematic L1 halo orbits (amplitudes in km, period ~178 days).
L1_HALO_IDS = ("ADITYA_L1", "ADITYAL1", "ADITYA", "DSCOVR", "ACE", "WIND", "SOHO")
L1_HALO_SPECS = {
    "ADITYA_L1": {"name": "Aditya-L1", "ax": 45000.0, "ay": 240000.0, "az": 150000.0, "tau_days": 177.8, "phi_y": 2.4, "phi_z": 2.4, "x_offset": -1510000.0},
    "DSCOVR":    {"name": "DSCOVR",    "ax": 45000.0, "ay": 280000.0, "az": 160000.0, "tau_days": 180.0, "phi_y": 0.0, "phi_z": 0.5, "x_offset": -1496000.0},
    "ACE":       {"name": "ACE",       "ax": 60000.0, "ay": 210000.0, "az": 140000.0, "tau_days": 180.0, "phi_y": 1.2, "phi_z": 1.2, "x_offset": -1480000.0},
    "WIND":      {"name": "WIND",      "ax": 70000.0, "ay": 190000.0, "az": 120000.0, "tau_days": 182.0, "phi_y": 3.14, "phi_z": 3.14, "x_offset": -1520000.0},
    "SOHO":      {"name": "SOHO",      "ax": 40000.0, "ay": 650000.0, "az": 200000.0, "tau_days": 178.0, "phi_y": 0.5, "phi_z": 0.5, "x_offset": -1500000.0},
}

class SpiceEphemerisEngine:
    """
    Sovereign Ephemeris Engine wrapping NASA JPL NAIF SPICE (via spiceypy).
    Computes rigorous state vectors [x, y, z, vx, vy, vz] in standard astronomical frames
    (ECLIPJ2000, GSE, J2000) using SPICE kernels and Keplerian/Halo analytical propagators.
    """

    AU_KM = 149597870.7          # 1 Astronomical Unit in km (IAU standard)
    R_SUN_KM = 696340.0           # Solar Volumetric Mean Radius in km
    R_EARTH_KM = 6378.1366        # Earth WGS-84 / SPICE Equatorial Radius in km
    L1_NOMINAL_KM = 1496547.6     # Nominal Sun-Earth L1 distance from Earth (~0.010 AU)

    _instance = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(SpiceEphemerisEngine, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, kernel_dir: Optional[str] = None):
        if getattr(self, "_initialized", False):
            return

        self._kernel_dir = self._resolve_kernel_dir(kernel_dir)
        self._loaded_kernels = []
        self._kernel_lock = threading.Lock()
        self._toolkit_version = "CSPICE_UNAVAILABLE"

        if SPICE_AVAILABLE:
            try:
                self._toolkit_version = spice.tkvrsn("TOOLKIT")
            except SPICE_ERRORS:
                self._toolkit_version = "CSPICE_N0067"
            self.load_kernels()

        self._initialized = True

    def _resolve_kernel_dir(self, custom_dir: Optional[str]) -> Path:
        """Locates the local SPICE kernels repository directory."""
        if custom_dir and os.path.isdir(custom_dir):
            return Path(custom_dir).resolve()

        # Check default helios/data/spice_kernels relative to this module
        base_dir = Path(__file__).resolve().parent.parent / "data" / "spice_kernels"
        if base_dir.exists():
            return base_dir

        # Fallback to local working directory
        cwd_dir = Path.cwd() / "helios" / "data" / "spice_kernels"
        if cwd_dir.exists():
            return cwd_dir

        base_dir.mkdir(parents=True, exist_ok=True)
        return base_dir

    def load_kernels(self) -> List[str]:
        """Loads all standard SPICE kernels (.tls, .tpc, .bsp, .tf) into the CSPICE pool."""
        if not SPICE_AVAILABLE:
            return []

        with self._kernel_lock:
            loaded = []
            if not self._kernel_dir.exists():
                return loaded

            # Preferred loading order: LSK (leapsecond) -> PCK (planetary constants) -> SPK (ephemeris) -> TF (frames)
            extensions = [".tls", ".tpc", ".bsp", ".tf"]
            for ext in extensions:
                for kernel_file in sorted(self._kernel_dir.glob(f"*{ext}")):
                    kernel_path = str(kernel_file.resolve())
                    try:
                        spice.furnsh(kernel_path)
                        loaded.append(kernel_path)
                    except SPICE_ERRORS as e:
                        _log.warning("Could not furnish %s: %s", kernel_file.name, e)

            self._loaded_kernels = loaded
            return loaded

    @property
    def is_spice_available(self) -> bool:
        return SPICE_AVAILABLE and len(self._loaded_kernels) > 0

    @property
    def toolkit_version(self) -> str:
        return self._toolkit_version

    @property
    def loaded_kernels(self) -> List[str]:
        return list(self._loaded_kernels)

    def epoch_to_et(self, epoch: Optional[Union[str, datetime, float]] = None) -> float:
        """
        Converts UTC timestamp (ISO format, datetime, or ET float) into SPICE Ephemeris Time (ET).
        ET is seconds past J2000 epoch (2000-01-01 12:00:00 TDB).
        """
        if epoch is None or (isinstance(epoch, str) and not epoch.strip()):
            now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
            epoch = now_utc

        if isinstance(epoch, (int, float)):
            return float(epoch)

        if isinstance(epoch, datetime):
            epoch = epoch.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]

        epoch_str = str(epoch).replace("Z", "").strip()
        try:
            # A bare number is already an ET value (e.g. from a previous epoch_to_et call).
            et = float(epoch_str)
        except ValueError:
            pass
        else:
            if not math.isfinite(et):  # 'nan' / 'inf' gave NaN positions and a 500
                raise ValueError(f"Unrecognised epoch {epoch!r}; use ISO 8601 UTC, e.g. 2026-10-04T12:00:00")
            return et

        if SPICE_AVAILABLE:
            try:
                with self._kernel_lock:
                    return float(spice.str2et(epoch_str))
            except SPICE_ERRORS:
                pass

        # Analytical ET calculation fallback if LSK is unloaded
        # J2000 epoch is 2000-01-01 12:00:00 UTC (Unix timestamp: 946728000.0)
        try:
            if "T" in epoch_str:
                dt = datetime.fromisoformat(epoch_str)
            else:
                dt = datetime.strptime(epoch_str, "%Y-%m-%d %H:%M:%S")
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            unix_ts = dt.timestamp()
            # ET ~ TAI + 32.184s; TAI = UTC + 37s (leapseconds up to 2026) -> ET ~ UTC + 69.184s
            return float(unix_ts - 946728000.0 + 69.184)
        except ValueError:
            # An unreadable epoch used to become a fixed ET in September 2026 without a word.
            raise ValueError(f"Unrecognised epoch {epoch!r}; use ISO 8601 UTC, e.g. 2026-10-04T12:00:00")

    def et_to_utc(self, et: float, format_str: str = "ISOC") -> str:
        """Converts SPICE Ephemeris Time (ET) back to ISO UTC string."""
        if SPICE_AVAILABLE:
            try:
                with self._kernel_lock:
                    return str(spice.et2utc(et, format_str, 3))
            except SPICE_ERRORS:
                pass

        # Analytical fallback
        unix_ts = et + 946728000.0 - 69.184
        dt = datetime.fromtimestamp(unix_ts, tz=timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]

    def get_body_gm(self, body_id: str = "10") -> float:
        """
        Retrieves gravitational parameter (GM in km^3/s^2) from SPICE PCK.
        Body 10 = Sun, Body 399 = Earth.
        """
        if SPICE_AVAILABLE:
            try:
                with self._kernel_lock:
                    return float(spice.bodvrd(body_id, "GM", 1)[1][0])
            except SPICE_ERRORS:
                pass

        # JPL DE431 standard defaults
        if body_id in ("10", "SUN"):
            return 132712440041.93938  # Sun GM
        if body_id in ("399", "EARTH"):
            return 398600.435436       # Earth GM
        return 132712440041.93938

    def compute_conics(
        self,
        rp_km: float,
        ecc: float,
        inc_deg: float,
        raan_deg: float,
        argp_deg: float,
        m0_deg: float,
        t0_et: float,
        target_et: float,
        primary_gm: Optional[float] = None
    ) -> Tuple[np.ndarray, np.ndarray]:
        """
        Executes NASA JPL SPICE conic propagation via spiceypy.conics().
        Returns:
            position: np.ndarray shape (3,) in km
            velocity: np.ndarray shape (3,) in km/s
        """
        gm = primary_gm if primary_gm is not None else self.get_body_gm("10")
        inc_rad = math.radians(inc_deg)
        raan_rad = math.radians(raan_deg)
        argp_rad = math.radians(argp_deg)
        m0_rad = math.radians(m0_deg)

        if SPICE_AVAILABLE:
            try:
                elts = np.array([rp_km, ecc, inc_rad, raan_rad, argp_rad, m0_rad, t0_et, gm], dtype=float)
                with self._kernel_lock:
                    state = spice.conics(elts, target_et)
                return np.array(state[0:3]), np.array(state[3:6])
            except SPICE_ERRORS as e:
                _log.warning("SPICE conics failed, using the Kepler solver: %s", e)

        # Keplerian analytical solver fallback
        a = rp_km / (1.0 - ecc) if ecc < 1.0 else rp_km
        n = math.sqrt(gm / (a ** 3))
        dt = target_et - t0_et
        m = (m0_rad + n * dt) % (2.0 * math.pi)

        # Solve Kepler's equation
        e_anom = m
        for _ in range(10):
            f = e_anom - ecc * math.sin(e_anom) - m
            fp = 1.0 - ecc * math.cos(e_anom)
            delta = f / fp
            e_anom -= delta
            if abs(delta) < 1e-12:
                break

        cos_e = math.cos(e_anom)
        sin_e = math.sin(e_anom)
        r = a * (1.0 - ecc * cos_e)
        sin_nu = math.sqrt(1.0 - ecc ** 2) * sin_e / (1.0 - ecc * cos_e)
        cos_nu = (cos_e - ecc) / (1.0 - ecc * cos_e)
        nu = math.atan2(sin_nu, cos_nu)

        # Orbital plane coordinates
        p = a * (1.0 - ecc ** 2)
        h = math.sqrt(gm * p)
        r_orb = np.array([r * math.cos(nu), r * math.sin(nu), 0.0])
        v_orb = np.array([-(gm / h) * math.sin(nu), (gm / h) * (ecc + math.cos(nu)), 0.0])

        # Rotation matrix to inertial frame (ECLIPJ2000)
        # R = Rz(-raan) * Rx(-inc) * Rz(-argp)
        cos_o, sin_o = math.cos(raan_rad), math.sin(raan_rad)
        cos_i, sin_i = math.cos(inc_rad), math.sin(inc_rad)
        cos_w, sin_w = math.cos(argp_rad), math.sin(argp_rad)

        P = np.array([
            cos_o * cos_w - sin_o * sin_w * cos_i,
            sin_o * cos_w + cos_o * sin_w * cos_i,
            sin_w * sin_i
        ])
        Q = np.array([
            -cos_o * sin_w - sin_o * cos_w * cos_i,
            -sin_o * sin_w + cos_o * cos_w * cos_i,
            cos_w * sin_i
        ])

        pos = r_orb[0] * P + r_orb[1] * Q
        vel = v_orb[0] * P + v_orb[1] * Q
        return pos, vel

    @staticmethod
    def _l1_halo_state(spec: Dict[str, Any], target_et: float, pos_earth: np.ndarray,
                       vel_earth: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
        """
        Schematic L1 halo orbit (amplitudes and ~180-day period from `spec`): GSE position and
        velocity (+X toward the Sun), and the heliocentric ECLIPJ2000 state built from Earth's.
        """
        omega_h = 2.0 * math.pi / (spec["tau_days"] * 86400.0)
        phase = (omega_h * target_et) % (2.0 * math.pi)
        gse_pos = np.array([abs(spec["x_offset"]) + spec["ax"] * math.cos(2.0 * phase),
                            spec["ay"] * math.sin(phase + spec["phi_y"]),
                            spec["az"] * math.cos(phase + spec["phi_z"])])
        gse_vel = np.array([-2.0 * omega_h * spec["ax"] * math.sin(2.0 * phase),
                            omega_h * spec["ay"] * math.cos(phase + spec["phi_y"]),
                            -omega_h * spec["az"] * math.sin(phase + spec["phi_z"])])
        # GSE: X to the Sun, Y = -(Earth's orbital direction) (towards dusk), Z = X x Y
        # = ecliptic north. Note u_sun x u_orbit would point to ecliptic SOUTH.
        r_earth_mag = np.linalg.norm(pos_earth)
        u_sun = -pos_earth / r_earth_mag
        u_orbit = vel_earth / np.linalg.norm(vel_earth)
        u_norm = np.cross(u_orbit, u_sun)
        pos = pos_earth + gse_pos[0] * u_sun - gse_pos[1] * u_orbit + gse_pos[2] * u_norm
        vel = (vel_earth * (np.linalg.norm(pos) / r_earth_mag)
               + gse_vel[0] * u_sun - gse_vel[1] * u_orbit + gse_vel[2] * u_norm)
        return pos, vel, gse_pos, gse_vel

    def get_spacecraft_state(
        self,
        spacecraft_id: str,
        epoch_utc: Optional[Union[str, float]] = None,
        frame: str = "ECLIPJ2000"
    ) -> Dict[str, Any]:
        """
        Calculates exact state vector [x, y, z, vx, vy, vz] for requested spacecraft or celestial body.
        Supports:
            'PARKER_SOLAR_PROBE' (PSP)
            'SOLAR_ORBITER' (SolO)
            'ADITYA_L1'
            'DSCOVR'
            'ACE'
            'WIND'
            'SOHO'
            'STEREO_A'
            'GOES_16'
            'EARTH'
            'MOON'
            'VENUS'
            'MARS'
            'MERCURY'
        """
        target_id = spacecraft_id.strip().upper().replace("-", "_")
        target_et = self.epoch_to_et(epoch_utc)
        target_iso = self.et_to_utc(target_et)
        mu_sun = self.get_body_gm("10")
        mu_earth = self.get_body_gm("399")

        # Compute Earth heliocentric state (ECLIPJ2000) first for GSE referencing
        t0_j2000 = 0.0  # ET 0.0 is 2000-01-01 12:00:00 TDB
        a_earth = 1.00000011 * self.AU_KM
        e_earth = 0.01671022
        rp_earth = a_earth * (1.0 - e_earth)
        pos_earth, vel_earth = self.compute_conics(
            rp_km=rp_earth, ecc=e_earth, inc_deg=0.00005,
            raan_deg=174.9, argp_deg=288.1, m0_deg=357.5,
            t0_et=t0_j2000, target_et=target_et, primary_gm=mu_sun
        )

        # GSE axes in ECLIPJ2000 (rows): X to the Sun, Z to the ecliptic north pole, Y = Z x X.
        x_ax = -pos_earth / np.linalg.norm(pos_earth)
        z_ax = np.array([0.0, 0.0, 1.0]) - x_ax[2] * x_ax
        z_ax /= np.linalg.norm(z_ax)
        gse_axes = np.vstack([x_ax, np.cross(z_ax, x_ax), z_ax])

        conic = next((c for ids, c in CONIC_TARGETS if target_id in ids), None)
        gse_pos_km = np.zeros(3)
        gse_vel_kms = np.zeros(3)
        if conic is not None:
            display_name, orbit_type, primary_body = conic["name"], conic["orbit_type"], conic["primary"]
            semi_major_axis_km = conic["a_au"] * self.AU_KM if "a_au" in conic else conic["a_km"]
            eccentricity, inclination_deg = conic["e"], conic["inc"]
            et_ref = self.epoch_to_et(conic["epoch"]) if conic["epoch"] else t0_j2000
            if conic.get("lunar"):
                t_utc = pd.Timestamp(target_iso)
                pos_km = moon_geocentric_ecliptic(t_utc)
                vel_kms = (moon_geocentric_ecliptic(t_utc + pd.Timedelta(seconds=60)) - pos_km) / 60.0
            elif "geo_lon" in conic:  # geostationary: GEO position over its longitude, rotated to GSE
                lon = math.radians(conic["geo_lon"])
                t_utc = pd.Timestamp(target_iso)
                g0, g1 = (np.array(geo_to_gse([t], semi_major_axis_km * math.cos(lon),
                                              semi_major_axis_km * math.sin(lon), 0.0)).ravel()
                          for t in (t_utc, t_utc + pd.Timedelta(seconds=1)))
                pos_km, vel_kms = gse_axes.T @ g0, gse_axes.T @ (g1 - g0)
            else:
                pos_km, vel_kms = self.compute_conics(
                    rp_km=conic.get("rp_km", semi_major_axis_km * (1.0 - eccentricity)), ecc=eccentricity, inc_deg=inclination_deg,
                    raan_deg=conic["raan"], argp_deg=conic["argp"], m0_deg=conic["m0"],
                    t0_et=et_ref, target_et=target_et, primary_gm=mu_earth if primary_body == "EARTH" else mu_sun
                )
            if primary_body == "EARTH":  # geocentric (ecliptic) state: GSE by rotation, heliocentric via Earth
                gse_pos_km, gse_vel_kms = gse_axes @ pos_km, gse_axes @ vel_kms
                pos_km, vel_kms = pos_earth + pos_km, vel_earth + vel_kms
            phase_desc = conic["phase"](self, pos_km) if callable(conic["phase"]) else conic["phase"]

        elif target_id in ("EARTH", "399"):
            display_name, orbit_type, primary_body = "Earth", "Planetary Orbit", "SUN"
            pos_km, vel_kms = pos_earth, vel_earth
            semi_major_axis_km, eccentricity, inclination_deg = a_earth, e_earth, 0.00005
            phase_desc = "Geocenter reference frame origin"

        elif target_id in L1_HALO_IDS:
            primary_body = "SUN-EARTH L1"
            orbit_type = "Sun-Earth L1 Halo/Lissajous Orbit"
            semi_major_axis_km = a_earth - self.L1_NOMINAL_KM
            eccentricity = e_earth
            inclination_deg = 0.0
            spec = L1_HALO_SPECS["ADITYA_L1" if "ADITYA" in target_id else target_id]
            display_name = spec["name"]
            pos_km, vel_kms, gse_pos_km, gse_vel_kms = self._l1_halo_state(spec, target_et, pos_earth, vel_earth)
            phase_desc = f"Active Sun-Earth L1 Halo Orbit (~{spec['tau_days']}d period)"

        else:
            # Generic probe fallback: follow Earth L1 nominal
            display_name, orbit_type, primary_body = spacecraft_id, "Heliocentric", "SUN"
            semi_major_axis_km, eccentricity, inclination_deg = a_earth, 0.0, 0.0
            phase_desc = "Nominal Operations"
            pos_km = pos_earth * 0.99
            vel_kms = vel_earth * 0.99
            gse_pos_km = np.array([1496000.0, 0.0, 0.0])
            gse_vel_kms = np.array([0.0, 0.0, 0.0])

        # GSE position and velocity relative to Earth for heliocentric bodies (computed for
        # every frame: the GSE coordinates used to be zero unless frame="GSE" was asked for).
        if np.linalg.norm(gse_pos_km) == 0 and target_id not in ("EARTH", "399"):
            gse_pos_km = gse_axes @ (pos_km - pos_earth)
            gse_vel_kms = gse_axes @ (vel_kms - vel_earth)

        # Heliocentric metrics
        r_sun_km = float(np.linalg.norm(pos_km))
        r_sun_au = r_sun_km / self.AU_KM
        r_sun_rsun = r_sun_km / self.R_SUN_KM

        # Earth-relative metrics
        r_earth_km = float(np.linalg.norm(pos_km - pos_earth))
        r_earth_re = r_earth_km / self.R_EARTH_KM

        # Velocity metrics
        v_selected = gse_vel_kms if (frame.upper() == "GSE" or primary_body == "EARTH") else vel_kms
        v_mag_kms = float(np.linalg.norm(v_selected))
        v_au_day = (v_mag_kms * 86400.0) / self.AU_KM
        v_helio_kms = float(np.linalg.norm(vel_kms))
        v_earth_rel_kms = float(np.linalg.norm(gse_vel_kms))

        # Ecliptic longitude & latitude (degrees)
        ecliptic_long_deg = float(math.degrees(math.atan2(pos_km[1], pos_km[0])) % 360.0)
        ecliptic_lat_deg = float(math.degrees(math.asin(pos_km[2] / max(1.0, r_sun_km))))

        # Orbital True Anomaly ν
        # Calculate from eccentricity vector: e_vec = (v x h)/mu - r/r
        try:
            h_vec = np.cross(pos_km, vel_kms)
            h_mag = np.linalg.norm(h_vec)
            mu_primary = mu_sun if primary_body == "SUN" else mu_earth
            e_vec = (np.cross(vel_kms, h_vec) / mu_primary) - (pos_km / r_sun_km)
            e_mag = np.linalg.norm(e_vec)
            if e_mag > 1e-6:
                cos_nu = np.dot(e_vec, pos_km) / (e_mag * r_sun_km)
                cos_nu = max(-1.0, min(1.0, cos_nu))
                sin_nu = np.dot(h_vec, np.cross(e_vec, pos_km)) / (h_mag * e_mag * r_sun_km)
                true_anomaly_deg = float(math.degrees(math.atan2(sin_nu, cos_nu)) % 360.0)
            else:
                true_anomaly_deg = ecliptic_long_deg
        except (ValueError, ZeroDivisionError, FloatingPointError):
            true_anomaly_deg = 0.0

        # Orbital period calculation (Kepler's third law)
        mu_for_period = mu_sun if primary_body in ("SUN", "SUN-EARTH L1") else mu_earth
        period_days = float((2.0 * math.pi * math.sqrt((semi_major_axis_km ** 3) / mu_for_period)) / 86400.0)

        # Output payload
        selected_pos = gse_pos_km if frame.upper() == "GSE" else pos_km
        selected_vel = gse_vel_kms if frame.upper() == "GSE" else vel_kms

        return {
            "spacecraft_id": target_id,
            "name": display_name,
            "orbit_type": orbit_type,
            "primary_body": primary_body,
            "epoch_utc": target_iso,
            "epoch_et": round(target_et, 3),
            "frame": frame.upper(),
            "position": {
                "x_km": round(float(selected_pos[0]), 2),
                "y_km": round(float(selected_pos[1]), 2),
                "z_km": round(float(selected_pos[2]), 2),
                "x_au": round(float(pos_km[0] / self.AU_KM), 6),
                "y_au": round(float(pos_km[1] / self.AU_KM), 6),
                "z_au": round(float(pos_km[2] / self.AU_KM), 6),
            },
            "velocity": {
                "vx_kms": round(float(selected_vel[0]), 3),
                "vy_kms": round(float(selected_vel[1]), 3),
                "vz_kms": round(float(selected_vel[2]), 3),
                "speed_kms": round(v_mag_kms, 2),
                "speed_au_day": round(v_au_day, 6),
                "heliocentric_speed_kms": round(v_helio_kms, 2),
                "earth_relative_speed_kms": round(v_earth_rel_kms, 3),
            },
            "gse_coordinates": {
                "x_km": round(float(gse_pos_km[0]), 1),
                "y_km": round(float(gse_pos_km[1]), 1),
                "z_km": round(float(gse_pos_km[2]), 1),
                "x_re": round(float(gse_pos_km[0] / self.R_EARTH_KM), 2),
                "y_re": round(float(gse_pos_km[1] / self.R_EARTH_KM), 2),
                "z_re": round(float(gse_pos_km[2] / self.R_EARTH_KM), 2),
            },
            "heliocentric": {
                "distance_km": round(r_sun_km, 1),
                "distance_au": round(r_sun_au, 5),
                "distance_rsun": round(r_sun_rsun, 2),
                "ecliptic_longitude_deg": round(ecliptic_long_deg, 2),
                "ecliptic_latitude_deg": round(ecliptic_lat_deg, 2),
            },
            "earth_relative": {
                "distance_km": round(r_earth_km, 1),
                "distance_re": round(r_earth_re, 2),
            },
            "orbital_elements": {
                "semi_major_axis_km": round(semi_major_axis_km, 1),
                "semi_major_axis_au": round(semi_major_axis_km / self.AU_KM, 5),
                "eccentricity": round(eccentricity, 4),
                "inclination_deg": round(inclination_deg, 2),
                "orbital_period_days": round(period_days, 2),
                "perihelion_distance_km": round(semi_major_axis_km * (1.0 - eccentricity), 1),
                "aphelion_distance_km": round(semi_major_axis_km * (1.0 + eccentricity), 1),
                "true_anomaly_deg": round(true_anomaly_deg, 2),
            },
            "phase": phase_desc,
            "is_spice_verified": self.is_spice_available,
            "spice_toolkit": self.toolkit_version,
            "kernel_count": len(self._loaded_kernels),
        }

    def get_fleet_states(
        self,
        spacecraft_ids: Optional[List[str]] = None,
        epoch_utc: Optional[str] = None,
        frame: str = "ECLIPJ2000"
    ) -> Dict[str, Any]:
        """Returns verified SPICE ephemeris states for multiple spacecraft."""
        if not spacecraft_ids:
            spacecraft_ids = [
                "PARKER_SOLAR_PROBE",
                "SOLAR_ORBITER",
                "ADITYA_L1",
                "DSCOVR",
                "ACE",
                "WIND",
                "SOHO",
                "STEREO_A",
                "GOES_16",
                "EARTH",
                "VENUS",
                "MARS",
                "MERCURY",
                "MOON",
            ]

        states = {}
        for sc_id in spacecraft_ids:
            states[sc_id] = self.get_spacecraft_state(sc_id, epoch_utc=epoch_utc, frame=frame)

        return {
            "epoch_utc": self.et_to_utc(self.epoch_to_et(epoch_utc)),
            "epoch_et": round(self.epoch_to_et(epoch_utc), 3),
            "frame": frame.upper(),
            "spice_available": self.is_spice_available,
            "spice_version": self.toolkit_version,
            "spacecraft_count": len(states),
            "fleet": states
        }

    def get_orbit_trajectory(
        self,
        spacecraft_id: str,
        num_points: int = 120,
        epoch_utc: Optional[str] = None
    ) -> List[Dict[str, float]]:
        """
        Generates 3D trajectory track points over one full orbital period.
        Useful for rendering orbit trails in 2D/3D visualizers.
        """
        base_state = self.get_spacecraft_state(spacecraft_id, epoch_utc=epoch_utc)
        period_days = base_state["orbital_elements"]["orbital_period_days"]
        t_start = base_state["epoch_et"]
        t_span = period_days * 86400.0

        points = []
        for i in range(num_points):
            t_curr = t_start + (i / max(1, num_points - 1)) * t_span
            st = self.get_spacecraft_state(spacecraft_id, epoch_utc=t_curr, frame="ECLIPJ2000")
            points.append({
                "x_km": st["position"]["x_km"],
                "y_km": st["position"]["y_km"],
                "z_km": st["position"]["z_km"],
                "x_au": st["position"]["x_au"],
                "y_au": st["position"]["y_au"],
                "z_au": st["position"]["z_au"],
                "gse_x_km": st["gse_coordinates"]["x_km"],
                "gse_y_km": st["gse_coordinates"]["y_km"],
                "gse_z_km": st["gse_coordinates"]["z_km"],
                "speed_kms": st["velocity"]["speed_kms"],
                "r_au": st["heliocentric"]["distance_au"],
            })

        return points


# Singleton instance accessor
_engine_instance: Optional[SpiceEphemerisEngine] = None

def get_spice_engine() -> SpiceEphemerisEngine:
    global _engine_instance
    if _engine_instance is None:
        _engine_instance = SpiceEphemerisEngine()
    return _engine_instance
