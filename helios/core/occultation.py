"""
Radio occultation of a spacecraft signal by the solar corona: SPICE ray geometry between a
spacecraft and a ground station, the closest approach of the ray to the Sun, and the
electron column, Faraday rotation and Doppler shift along the ray through a coronal density
and magnetic field model.

Kernels (downloaded once into the cache and furnished with SpiceyPy):
* NAIF generic kernels: DE440s planetary ephemeris, the ITRF93 positions of the tracking
  stations (earthstns_itrf93_*.bsp; the DSN antennas are named DSS-14, DSS-43, DSS-63 ...),
  and the Earth orientation binary PCKs (earth_latest_high_prec.bpc and the long-term
  prediction) that put the stations in space. The newest file of each name is taken from the
  NAIF directory listing.
* Spacecraft: either an SPK file the user names from the NAIF or ESA SPICE servers, or one
  written here (SPK type 13, Hermite, degree 7) from JPL Horizons state vectors of the
  spacecraft over the interval (solar system barycentre, ICRF), at a step of interval/1000
  between 2 and 60 minutes.

Geometry at each receive time t at the station: the spacecraft position at emission time
(light time, spkezr 'CN'), the unit ray vector u from the station, the Sun vector S, the
closest-approach distance along the ray d = S.u and the impact parameter p = |S - d u|; the
solar elongation is the angle between u and S. The heliographic position of the closest
point is given in the IAU_SUN frame (Carrington-like longitude).

Along the ray, at the angle theta from the closest point (s = d + p tan theta, r = p sec theta,
dl = p sec^2 theta dtheta, which samples densely where the density is high):
* electron density, cm^-3 with r in solar radii: Leblanc, Dulk & Bougeret (1998, Sol. Phys.
  183, 165, doi:10.1023/A:1005049730506) n = 3.3e5 r^-2 + 4.1e6 r^-4 + 8.0e7 r^-6 (corona to
  1 AU), or Baumbach-Allen (Allen 1947, MNRAS 107, 426, doi:10.1093/mnras/107.5-6.426)
  n = 1e8 (2.99 r^-16 + 1.55 r^-6) (inner corona, below about 3 R_sun);
* magnetic field: a Parker spiral, B_r = B_r(1 AU) (1 AU / r)^2 with the polarity given,
  B_phi = -B_r Omega r cos(lat) / V; or, with a PFSS solution (helios.core.pfss_model), the
  radial field of the source surface at the footpoint of the spiral through the point,
  B_r = B_ss (r_ss / r)^2 (also inside r_ss, an approximation), with the same B_phi;
* electron column TEC = integral n dl; rotation measure RM = 2.63e-13 integral n B.dl
  (SI; B.dl along the propagation, spacecraft to station; RM > 0 for field towards the
  station), Faraday rotation chi = RM lambda^2;
* Doppler (one-way downlink at f): geometric -f (drho/dt)/c and plasma +(40.3/(c f)) dTEC/dt
  (the phase path is rho - 40.3 TEC / f^2), dTEC/dt by central differences over 120 s.

Compared with the VLA rotation measures of Ingleby, Spangler & Whiting (2007, ApJ 668, 520,
doi:10.1086/521140) at 5.6-9.7 R_sun: n and B at 6.2 R_sun are within a factor of two of the
values they infer, but with a flat current sheet the rotation measures are about 4 times too
small in rms and mostly of the wrong sign: the actual current sheet (PFSS) is needed.

Measured polarization angles are known modulo 180 deg: `unwrap_180` removes the 180-deg jumps
of a time series and, given model values, adds the multiple of 180 deg that brings the series
closest to the model.
"""
from __future__ import annotations

import math
import os
import re
import threading
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence

import numpy as np

NAIF = "https://naif.jpl.nasa.gov/pub/naif/generic_kernels/"
GENERIC = [("spk/planets/", r"de440s\.bsp"), ("spk/stations/", r"earthstns_itrf93_\d+\.bsp"),
           ("pck/", r"earth_latest_high_prec\.bpc"), ("pck/", r"earth_\d{4}_\d+_\d+_predict\.bpc")]
SPK_HOSTS = ("https://naif.jpl.nasa.gov/", "https://spiftp.esac.esa.int/")
HORIZONS = "https://ssd.jpl.nasa.gov/api/horizons.api"
C_KMS = 299792.458
R_SUN_KM = 695700.0
AU_KM = 149597870.7
OMEGA_SUN = 2.865e-6
RM_CONST = 2.63e-13  # e^3 / (8 pi^2 eps0 m_e^2 c^3), SI
STATIONS = ["DSS-14", "DSS-24", "DSS-25", "DSS-26", "DSS-34", "DSS-35", "DSS-36", "DSS-43", "DSS-54",
            "DSS-55", "DSS-56", "DSS-63", "DSS-65"]
SPACECRAFT = {"-41": "Mars Express", "-61": "Juno", "-121": "BepiColombo", "-144": "Solar Orbiter",
              "-96": "Parker Solar Probe", "-234": "STEREO-A", "-202": "MAVEN", "-74": "MRO", "-5": "Akatsuki"}
MAX_DAYS = 14
_LOCK = threading.Lock()
_FURNISHED: List[str] = []


def _spice():
    import spiceypy
    return spiceypy


def _get(url: str) -> bytes:
    import httpx
    with httpx.Client(timeout=300.0, follow_redirects=True) as c:
        r = c.get(url)
        r.raise_for_status()
        return r.content


def _download(url: str, path: str, fetch: Callable[[str], bytes] = _get) -> str:
    if not os.path.exists(path):
        data = fetch(url)
        with open(path + ".tmp", "wb") as f:
            f.write(data)
        os.replace(path + ".tmp", path)
    return path


def generic_kernels(cache_dir: str, fetch: Callable[[str], bytes] = _get) -> List[str]:
    """Local paths of the generic kernels (newest of each name in the NAIF listing), downloaded once."""
    folder = os.path.join(str(cache_dir), "spice_kernels")
    os.makedirs(folder, exist_ok=True)
    paths = []
    for sub, pattern in GENERIC:
        have = sorted(f for f in os.listdir(folder) if re.fullmatch(pattern, f))
        if have:
            paths.append(os.path.join(folder, have[-1]))
            continue
        listing = fetch(NAIF + sub).decode("utf-8", "replace")
        names = sorted(set(re.findall(r'href="(' + pattern + ')"', listing)))
        if not names:
            raise LookupError(f"No kernel matching {pattern} at {NAIF + sub}.")
        paths.append(_download(NAIF + sub + names[-1], os.path.join(folder, names[-1]), fetch))
    return paths


def horizons_spk(naif_id: str, start: datetime, end: datetime, cache_dir: str,
                 fetch: Callable[[str], bytes] = _get) -> str:
    """SPK (type 13) of a spacecraft over [start, end] from JPL Horizons state vectors (cached)."""
    from urllib.parse import urlencode
    sp = _spice()
    start, end = _utc(start) - timedelta(hours=1), _utc(end) + timedelta(hours=1)
    minutes = int(min(60, max(2, (end - start).total_seconds() / 60.0 / 1000.0)))
    folder = os.path.join(str(cache_dir), "spice_kernels", "spacecraft")
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"hz{naif_id.replace('-', 'm')}_{start:%Y%m%d%H%M}_{end:%Y%m%d%H%M}_{minutes}m.bsp")
    if os.path.exists(path):
        return path
    q = {"format": "text", "COMMAND": f"'{naif_id}'", "EPHEM_TYPE": "'VECTORS'", "CENTER": "'500@0'",
         "REF_SYSTEM": "'ICRF'", "REF_PLANE": "'FRAME'", "VEC_TABLE": "'2'", "OUT_UNITS": "'KM-S'",
         "CSV_FORMAT": "'YES'", "TIME_TYPE": "'TDB'", "START_TIME": f"'{start:%Y-%m-%d %H:%M}'",
         "STOP_TIME": f"'{end:%Y-%m-%d %H:%M}'", "STEP_SIZE": f"'{minutes} m'"}
    text = fetch(HORIZONS + "?" + urlencode(q)).decode("utf-8", "replace")
    if "$$SOE" not in text:
        raise LookupError(f"JPL Horizons has no ephemeris of {naif_id} for this interval: "
                          + text.strip().splitlines()[-1][:200])
    rows = [ln.split(",") for ln in text.split("$$SOE")[1].split("$$EOE")[0].strip().splitlines()]
    jd = np.array([float(r[0]) for r in rows])
    states = np.array([[float(x) for x in r[2:8]] for r in rows])
    epochs = (jd - 2451545.0) * 86400.0
    with _LOCK:
        handle = sp.spkopn(path + ".tmp", "HELIOS-L1 Horizons", 0)
        sp.spkw13(handle, int(naif_id), 0, "J2000", epochs[0], epochs[-1], f"Horizons {naif_id}"[:40], 7,
                  len(epochs), states, epochs)
        sp.spkcls(handle)
    os.replace(path + ".tmp", path)
    return path


def user_spk(url: str, cache_dir: str, fetch: Callable[[str], bytes] = _get) -> str:
    """An SPK named by URL on the NAIF or ESA SPICE servers, downloaded once."""
    if not url.startswith(SPK_HOSTS) or not url.lower().endswith(".bsp"):
        raise ValueError("The SPK must be a .bsp file on naif.jpl.nasa.gov or spiftp.esac.esa.int.")
    folder = os.path.join(str(cache_dir), "spice_kernels", "spacecraft")
    os.makedirs(folder, exist_ok=True)
    return _download(url, os.path.join(folder, os.path.basename(url)), fetch)


def furnish(paths: Sequence[str]) -> None:
    """Load kernels (again if another part of the program cleared the pool)."""
    from helios.core.spice_engine import get_spice_engine
    sp = _spice()
    get_spice_engine()  # leap seconds and the IAU_SUN orientation
    with _LOCK:
        loaded = {sp.kdata(i, "ALL")[0] for i in range(sp.ktotal("ALL"))}
        for p in paths:
            if p not in loaded:
                sp.furnsh(p)


def _utc(t: datetime) -> datetime:
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def _et(t: datetime) -> float:
    return float(_spice().str2et(_utc(t).strftime("%Y-%m-%dT%H:%M:%S.%f")))


def density_cm3(r_rsun, model: str = "leblanc"):
    r = np.asarray(r_rsun, dtype=float)
    if model == "leblanc":
        return 3.3e5 * r ** -2 + 4.1e6 * r ** -4 + 8.0e7 * r ** -6
    if model == "allen":
        return 1e8 * (2.99 * r ** -16 + 1.55 * r ** -6)
    raise ValueError("density model must be 'leblanc' or 'allen'.")


def ray_geometry(sc: str, station: str, et: float) -> Dict[str, Any]:
    """Station-to-spacecraft ray at receive time et (see module notes); positions in km, J2000."""
    sp = _spice()
    with _LOCK:
        state, lt = sp.spkezr(sc, et, "J2000", "CN", station)
        sun, _ = sp.spkpos("SUN", et, "J2000", "CN", station)
        rot = np.array(sp.pxform("J2000", "IAU_SUN", et))
    r_sc, v_sc = np.array(state[:3]), np.array(state[3:])
    length = float(np.linalg.norm(r_sc))
    u = r_sc / length
    s_vec = np.array(sun)
    d = float(s_vec @ u)
    closest = s_vec - d * u  # Sun to the closest point, reversed: from closest point to Sun
    p = float(np.linalg.norm(closest))
    elong = math.degrees(math.acos(max(-1.0, min(1.0, d / float(np.linalg.norm(s_vec))))))
    x_cp = rot @ (-closest)  # closest point from the Sun, IAU_SUN
    return {"u": u, "sun": s_vec, "rot": rot, "length_km": length, "d_km": d, "impact_km": p,
            "impact_rsun": p / R_SUN_KM, "elongation_deg": elong, "closest_on_ray": 0.0 < d < length,
            "closest_lon": math.degrees(math.atan2(x_cp[1], x_cp[0])) % 360.0,
            "closest_lat": math.degrees(math.asin(max(-1.0, min(1.0, x_cp[2] / max(p, 1e-9))))),
            "range_km": length, "range_rate_kms": float(r_sc @ v_sc) / length, "light_time_s": float(lt)}


def ray_integrals(g: Dict[str, Any], density: str = "leblanc", field: Optional[Callable] = None,
                  n: int = 2001) -> Dict[str, float]:
    """TEC (el/m^2) and RM (rad/m^2) along the ray of `g`; field(x_sun_iau_km) -> B (T, IAU_SUN) or None."""
    p, d, length = g["impact_km"], g["d_km"], g["length_km"]
    th0, th1 = math.atan2(-d, p), math.atan2(length - d, p)
    th = np.linspace(th0, th1, n)
    s = d + p * np.tan(th)
    dl_m = p * 1e3 / np.cos(th) ** 2 * (th[1] - th[0])
    x = s[:, None] * g["u"][None, :] - g["sun"][None, :]  # from the Sun, J2000, km
    r_rsun = np.linalg.norm(x, axis=1) / R_SUN_KM
    ne = density_cm3(np.maximum(r_rsun, 1.0), density) * 1e6
    w = np.ones(n)
    w[0] = w[-1] = 0.5
    tec = float(np.sum(w * ne * dl_m))
    rm = None
    if field is not None:
        x_iau = x @ g["rot"].T
        b_iau = field(x_iau)
        b_j2000 = b_iau @ g["rot"]
        b_par = b_j2000 @ (-g["u"])  # along the propagation, spacecraft to station
        rm = float(RM_CONST * np.sum(w * ne * b_par * dl_m))
    return {"tec_el_m2": tec, "rm_rad_m2": rm}


def parker_field(b1au_nt: float = 3.5, polarity: int = 1, wind_kms: float = 400.0,
                 ss_br: Optional[Callable] = None, rss: float = 2.5) -> Callable:
    """
    Field function for ray_integrals: Parker spiral with B_r = B_r(1 AU)(1 AU/r)^2 x polarity,
    or, with ss_br(lon_deg, lat_deg) -> B_r at the source surface (T), B_ss (r_ss/r)^2 at the
    footpoint of the spiral through the point; B_phi = -B_r Omega r cos(lat) / V.
    """
    def field(x_km: np.ndarray) -> np.ndarray:
        r = np.linalg.norm(x_km, axis=1)
        lat = np.arcsin(np.clip(x_km[:, 2] / r, -1, 1))
        lon = np.arctan2(x_km[:, 1], x_km[:, 0])
        if ss_br is None:
            br = polarity * b1au_nt * 1e-9 * (AU_KM / r) ** 2
        else:
            lon_foot = np.degrees(lon + OMEGA_SUN * np.maximum(r - rss * R_SUN_KM, 0.0) / wind_kms) % 360.0
            br = ss_br(lon_foot, np.degrees(lat)) * (rss * R_SUN_KM / r) ** 2
        bphi = -br * OMEGA_SUN * r * np.cos(lat) / wind_kms
        e_r = x_km / r[:, None]
        e_phi = np.stack([-np.sin(lon), np.cos(lon), np.zeros_like(lon)], axis=1)
        return br[:, None] * e_r + bphi[:, None] * e_phi
    return field


def pfss_source_surface(out) -> Callable:
    """ss_br for parker_field from a PFSS solution (nearest cell of the source-surface map, Tesla)."""
    from sunpy.map import all_coordinates_from_map
    ss = out.source_surface_br
    c = all_coordinates_from_map(ss)
    lon = c.lon.to_value("deg")[0] % 360.0
    s_lat = np.sin(np.radians(c.lat.to_value("deg")[:, 0]))
    data = np.asarray(ss.data, dtype=float) * 1e-4  # gauss -> tesla

    def br(lon_deg, lat_deg):
        j = np.argmin(np.abs(((np.asarray(lon_deg)[:, None] - lon[None, :]) + 180) % 360 - 180), axis=1)
        i = np.argmin(np.abs(np.sin(np.radians(np.asarray(lat_deg)))[:, None] - s_lat[None, :]), axis=1)
        return data[i, j]
    return br


def unwrap_180(measured_deg: Sequence[float], model_deg: Optional[Sequence[float]] = None) -> Dict[str, Any]:
    """Remove 180-deg jumps from polarization angles; with a model, shift by the n x 180 deg closest to it."""
    m = np.asarray(measured_deg, dtype=float)
    if m.size == 0:
        raise ValueError("No angles given.")
    un = np.degrees(np.unwrap(np.radians(m) * 2.0) / 2.0)
    shift = 0
    if model_deg is not None:
        md = np.asarray(model_deg, dtype=float)
        if md.size != m.size:
            raise ValueError("Measured and model angles must have the same length.")
        shift = int(np.round(np.nanmean(md - un) / 180.0))
        un = un + 180.0 * shift
    return {"corrected_deg": [round(float(v), 3) for v in un], "shift_multiples_of_180": shift,
            "jumps_removed": int(np.count_nonzero(np.diff(np.round((un - m) / 180.0))))}


def occultation(sc: str, station: str, start: datetime, end: datetime, step_minutes: float, freq_mhz: float,
                density: str = "leblanc", field: Optional[Callable] = None) -> List[Dict[str, Any]]:
    """Time series of the geometry and the plasma effects (kernels must be furnished)."""
    if (end - start).total_seconds() <= 0:
        raise ValueError("The end must be after the start.")
    if (end - start).total_seconds() / 86400.0 > MAX_DAYS:
        raise ValueError(f"At most {MAX_DAYS} days.")
    f_hz = freq_mhz * 1e6
    lam = 299792458.0 / f_hz
    rows = []
    t = _utc(start)
    while t <= _utc(end) and len(rows) < 5000:
        et = _et(t)
        g = ray_geometry(sc, station, et)
        tec = ray_integrals(g, density, field)
        tec_m = ray_integrals(ray_geometry(sc, station, et - 60.0), density)["tec_el_m2"]
        tec_p = ray_integrals(ray_geometry(sc, station, et + 60.0), density)["tec_el_m2"]
        dtec = (tec_p - tec_m) / 120.0
        rm = tec["rm_rad_m2"]
        blocked = g["closest_on_ray"] and g["impact_rsun"] < 1.0
        if blocked:  # the ray goes through the Sun: no signal, no plasma effects
            tec, rm, dtec = {"tec_el_m2": None}, None, None
        rows.append({
            "time": t.strftime("%Y-%m-%d %H:%M:%S"), "elongation_deg": round(g["elongation_deg"], 4),
            "impact_rsun": round(g["impact_rsun"], 3), "closest_on_ray": g["closest_on_ray"],
            "closest_lon_deg": round(g["closest_lon"], 2), "closest_lat_deg": round(g["closest_lat"], 2),
            "range_km": round(g["range_km"], 1), "range_rate_kms": round(g["range_rate_kms"], 5),
            "doppler_geometric_hz": round(-f_hz * g["range_rate_kms"] / C_KMS, 3),
            "blocked_by_sun": blocked,
            "tec_tecu": None if blocked else round(tec["tec_el_m2"] / 1e16, 3),
            "doppler_plasma_hz": None if blocked else round(40.3 / (299792458.0 * f_hz) * dtec, 6),
            "rm_rad_m2": None if rm is None else round(rm, 4),
            "faraday_rotation_deg": None if rm is None else round(math.degrees(rm * lam * lam), 3)})
        t += timedelta(minutes=step_minutes)
    return rows
