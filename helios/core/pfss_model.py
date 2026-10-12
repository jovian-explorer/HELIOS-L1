"""
Coronal magnetic field from photospheric synoptic maps with the potential field source
surface (PFSS) model of sunkit-magex (the successor of pfsspy; Stansby, Yeates & Badman
2020, JOSS 5, 2732, doi:10.21105/joss.02732).

* Maps (read with SunPy, downloaded once and cached): GONG zero-point corrected synoptic
  maps (NSO, public; the default), ADAPT maps (NSO; realization 0 of the 12, Carrington
  longitudes), and HMI synoptic maps (JSOC hmi.synoptic_mr_polfil_720s; JSOC asks for a
  registered e-mail address to export data).
* Solution on a grid of nrho radial cells up to the source surface radius r_ss (2.5 R_sun by
  default), the map resampled to 360 x 180.
* Field lines traced (streamtracer) from any point between the photosphere and r_ss, in
  Carrington coordinates: the photospheric footpoint, open (reaching r_ss) or closed, the
  polarity, the photospheric field at the footpoint and a class:
  open field in a coronal hole (|B_r| < AR_THRESHOLD_G at the footpoint) or from the edge of
  an active region, and closed field in an active region or the quiet Sun.
* Heliospheric current sheet: the B_r = 0 line on the source surface; the distance of a point
  to it is the smallest great-circle angle to that line.
* Earth connection: the solar wind now at Earth left the source surface at the Carrington
  longitude of the sub-Earth point plus Omega (1 AU - r_ss) / V (ballistic mapping at constant
  speed, Neugebauer et al. 1998, JGR 103, 14587, doi:10.1029/98JA00798), at the latitude of
  the sub-Earth point; the field line traced down from there gives the solar source.

SunPy and sunkit-magex are optional ("pip install helios-l1[solar]"); without them the
functions raise ImportError.
"""
from __future__ import annotations

import base64
import io
import math
import os
import threading
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import numpy as np
from helios.core.constants import AU_KM, OMEGA_SUN_SIDEREAL as OMEGA_SIDEREAL, R_SUN_KM
from helios.core.timeutil import utc as _utc

AR_THRESHOLD_G = 50.0
SOURCES = ("gong", "adapt", "hmi")
MAP_LOOKBACK = timedelta(days=1)
_SOLUTIONS: Dict[tuple, Any] = {}
_LOCK = threading.Lock()


def fetch_map(source: str, when: datetime, cache_dir: str, jsoc_email: Optional[str] = None) -> str:
    """Local path of the synoptic map of `source` nearest before `when` (downloaded once)."""
    from sunpy.net import Fido, attrs as a
    if source not in SOURCES:
        raise ValueError(f"source must be one of {', '.join(SOURCES)}.")
    folder = os.path.join(str(cache_dir), "magnetograms", source)
    os.makedirs(folder, exist_ok=True)
    t = _utc(when).replace(tzinfo=None)
    # GONG maps are hourly and ADAPT ones 2-hourly, with gaps of several hours: look back a day.
    if source == "gong":
        res = Fido.search(a.Time(t - MAP_LOOKBACK, t), a.Instrument("GONG"))
    elif source == "adapt":
        res = Fido.search(a.Time(t - MAP_LOOKBACK, t), a.Instrument("ADAPT"), a.adapt.ADAPTLonType("0"))
    else:
        if not jsoc_email:
            raise ValueError("HMI maps come from JSOC, which exports data only to an e-mail address registered at "
                             "jsoc.stanford.edu/ajax/register_email.html: enter it in the JSOC e-mail field.")
        from sunpy.coordinates.sun import carrington_rotation_number
        cr = int(carrington_rotation_number(t))
        res = Fido.search(a.jsoc.Series("hmi.synoptic_mr_polfil_720s"), a.jsoc.PrimeKey("CAR_ROT", cr),
                          a.jsoc.Notify(jsoc_email))
    if not len(res) or not len(res[0]):
        raise LookupError(f"No {source.upper()} map found in the day before {t:%Y-%m-%d %H:%M} UTC.")
    table = res[0]
    table.sort("Start Time")
    row = table[-1:]  # the latest before the time asked for
    files = Fido.fetch(row, path=os.path.join(folder, "{file}"), progress=False)
    if not files:
        raise LookupError(f"The {source.upper()} map could not be downloaded.")
    return str(files[0])


def _read_map(path: str):
    import astropy.units as u
    import sunpy.map
    from astropy.io import fits
    if "adapt" in os.path.basename(path).lower():
        with fits.open(path) as hdul:  # 12 realizations: the first
            data, header = hdul[0].data[0], hdul[0].header.copy()
        header["NAXIS"] = 2
        for k in ("NAXIS3", "CTYPE3", "CRPIX3", "CRVAL3", "CDELT3", "CUNIT3"):
            header.pop(k, None)
        m = sunpy.map.Map(data, header)
    else:
        m = sunpy.map.Map(path)
    if m.wcs.wcs.ctype[0].strip().endswith("CAR"):  # ADAPT: plate carree, PFSS needs sine latitude
        from sunkit_magex.pfss.utils import car_to_cea
        m = car_to_cea(m)
    m = m.resample([360, 180] * u.pix)
    return m


def solve(path: str, rss: float = 2.5, nrho: int = 35):
    """PFSS solution of a map file (kept in memory for repeated tracing)."""
    from sunkit_magex import pfss
    key = (path, round(rss, 3), nrho)
    with _LOCK:
        if key in _SOLUTIONS:
            return _SOLUTIONS[key]
    m = _read_map(path)
    out = pfss.pfss(pfss.Input(m, nrho, rss))
    with _LOCK:
        if len(_SOLUTIONS) > 4:
            _SOLUTIONS.pop(next(iter(_SOLUTIONS)))
        _SOLUTIONS[key] = out
    return out


def _br_at(m, lon_deg: float, lat_deg: float) -> float:
    """Photospheric B_r of the input map (nearest pixel) at a Carrington lon/lat."""
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    c = SkyCoord(lon_deg * u.deg, lat_deg * u.deg, frame=m.coordinate_frame)
    x, y = m.world_to_pixel(c)
    i, j = int(round(float(y.value))) % m.data.shape[0], int(round(float(x.value))) % m.data.shape[1]
    return float(m.data[i, j])


def classify(is_open: bool, br_foot_g: float) -> str:
    strong = abs(br_foot_g) >= AR_THRESHOLD_G
    if is_open:
        return "open field from the edge of an active region" if strong else "open field (coronal hole)"
    return "closed field in an active region" if strong else "closed field (quiet Sun)"


def hcs_lines(out) -> List[np.ndarray]:
    """B_r = 0 lines on the source surface as arrays of (Carrington lon, lat) in degrees."""
    import contourpy
    from sunpy.map import all_coordinates_from_map
    ss = out.source_surface_br
    coords = all_coordinates_from_map(ss)
    # Columns in increasing longitude 0-360: the maps start at the central longitude of the
    # map, and contouring across that seam drew a spurious line along a latitude.
    lon = coords.lon.to_value("deg")[0] % 360.0
    lat = coords.lat.to_value("deg")[:, 0]
    order = np.argsort(lon)
    gen = contourpy.contour_generator(lon[order], lat, np.asarray(ss.data, dtype=float)[:, order])
    return [ln for ln in gen.lines(0.0) if len(ln) > 2]


def angular_distance_deg(lon1, lat1, lon2, lat2):
    l1, b1, l2, b2 = (np.radians(np.asarray(v, dtype=float)) for v in (lon1, lat1, lon2, lat2))
    c = np.sin(b1) * np.sin(b2) + np.cos(b1) * np.cos(b2) * np.cos(l1 - l2)
    return np.degrees(np.arccos(np.clip(c, -1.0, 1.0)))


def hcs_distance(lines: List[np.ndarray], lon: float, lat: float) -> Optional[float]:
    if not lines:
        return None
    pts = np.vstack(lines)
    return float(np.min(angular_distance_deg(lon, lat, pts[:, 0], pts[:, 1])))


def trace(out, points: List[Dict[str, float]], hcs: Optional[List[np.ndarray]] = None) -> List[Dict[str, Any]]:
    """Field lines through points {"r_rsun", "lon", "lat"} (Carrington, deg)."""
    import astropy.constants as const
    import astropy.units as u
    from astropy.coordinates import SkyCoord
    from sunkit_magex import pfss
    rss = float(out.grid.rss)
    for p in points:
        if not 1.0 <= p["r_rsun"] <= rss:
            raise ValueError(f"Points must lie between 1 and {rss:g} R_sun.")
    seeds = SkyCoord([p["lon"] for p in points] * u.deg, [p["lat"] for p in points] * u.deg,
                     [min(p["r_rsun"], rss * 0.999) for p in points] * const.R_sun, frame=out.coordinate_frame)
    lines = pfss.tracing.PerformanceTracer().trace(seeds, out)
    res = []
    for p, fl in zip(points, lines):
        c = fl.coords
        if len(c) < 2:
            res.append({"seed": p, "traced": False})
            continue
        foot = fl.solar_footpoint
        flon, flat = float(foot.lon.to_value("deg")), float(foot.lat.to_value("deg"))
        br = _br_at(out.input_map, flon, flat)
        entry = {"seed": p, "traced": True, "open": bool(fl.is_open), "polarity": int(fl.polarity),
                 "footpoint_lon": round(flon % 360.0, 2), "footpoint_lat": round(flat, 2),
                 "footpoint_br_gauss": round(br, 1), "class": classify(bool(fl.is_open), br),
                 "line": [[round(float(lo), 2), round(float(la), 2), round(float(r), 3)] for lo, la, r in
                          zip(c.lon.to_value("deg")[::3], c.lat.to_value("deg")[::3],
                              (c.radius / const.R_sun).decompose().value[::3])]}
        if fl.is_open and hcs is not None:
            ss = fl.source_surface_footpoint
            entry["source_surface_lon"] = round(float(ss.lon.to_value("deg")) % 360.0, 2)
            entry["source_surface_lat"] = round(float(ss.lat.to_value("deg")), 2)
            entry["hcs_distance_deg"] = round(hcs_distance(hcs, entry["source_surface_lon"], entry["source_surface_lat"]), 2)
        res.append(entry)
    return res


def earth_connection(when: datetime, speed_kms: float, rss: float) -> Dict[str, float]:
    """Source-surface point of the wind now at Earth (ballistic mapping, see module notes)."""
    from sunpy.coordinates.sun import B0, L0
    t = _utc(when).replace(tzinfo=None)
    l0 = float(L0(t).to_value("deg"))
    dphi = math.degrees(OMEGA_SIDEREAL * (AU_KM - rss * R_SUN_KM) / speed_kms)
    return {"sub_earth_lon": round(l0 % 360.0, 2), "sub_earth_lat": round(float(B0(t).to_value("deg")), 2),
            "lon": round((l0 + dphi) % 360.0, 2), "lat": round(float(B0(t).to_value("deg")), 2),
            "longitude_shift_deg": round(dphi, 2), "speed_kms": speed_kms}


def plot(out, hcs: List[np.ndarray], traced: List[Dict[str, Any]], earth: Optional[Dict[str, float]] = None) -> str:
    """PNG (data URL) of the photospheric B_r with the current sheet, footpoints and seeds."""
    from matplotlib.figure import Figure  # not pyplot: its global state is not safe in worker threads
    from sunpy.map import all_coordinates_from_map
    m = out.input_map
    coords = all_coordinates_from_map(m)
    lon = coords.lon.to_value("deg")[0] % 360.0
    lat = coords.lat.to_value("deg")[:, 0]
    order = np.argsort(lon)
    fig = Figure(figsize=(9, 4.6), dpi=110)
    ax = fig.subplots()
    lim = max(10.0, float(np.nanpercentile(np.abs(m.data), 98)))
    pc = ax.pcolormesh(lon[order], lat, np.asarray(m.data)[:, order], cmap="gray", vmin=-lim, vmax=lim, shading="auto")
    fig.colorbar(pc, ax=ax, label="B_r at the photosphere (G)", fraction=0.03)
    for i, ln in enumerate(hcs):
        ax.plot(ln[:, 0], ln[:, 1], color="#ef4444", lw=1.4, label="current sheet (B_r = 0 at r_ss)" if i == 0 else None)
    for t in traced:
        if not t.get("traced"):
            continue
        col = ("#22d3ee" if t["polarity"] > 0 else "#f472b6") if t["open"] else "#facc15"
        line = np.array(t["line"])
        ax.plot(line[:, 0] % 360.0, line[:, 1], ".", ms=1.5, color=col)
        ax.plot(t["footpoint_lon"], t["footpoint_lat"], "o", color=col, mec="k", ms=6)
    if earth:
        ax.plot(earth["lon"], earth["lat"], "*", color="#38bdf8", mec="k", ms=12, label="Earth-connected point at r_ss")
    ax.set_xlim(0, 360)
    ax.set_ylim(-90, 90)
    ax.set_xlabel("Carrington longitude (deg)")
    ax.set_ylabel("latitude (deg)")
    ax.legend(loc="lower left", fontsize=7)
    fig.tight_layout()
    buf = io.BytesIO()
    fig.savefig(buf, format="png")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def analyse(source: str, when: datetime, cache_dir: str, speed_kms: float = 450.0, rss: float = 2.5,
            points: Optional[List[Dict[str, float]]] = None, jsoc_email: Optional[str] = None) -> Dict[str, Any]:
    """Map, PFSS solution, Earth connection, traced points and the plot, as one answer."""
    path = fetch_map(source, when, cache_dir, jsoc_email)
    out = solve(path, rss)
    hcs = hcs_lines(out)
    earth = earth_connection(when, speed_kms, rss)
    seeds = [{"r_rsun": rss * 0.999, "lon": earth["lon"], "lat": earth["lat"], "label": "Earth-connected"}]
    seeds += [dict(p, label=p.get("label", "user point")) for p in (points or [])]
    traced = trace(out, [{k: p[k] for k in ("r_rsun", "lon", "lat")} for p in seeds], hcs)
    for s, t in zip(seeds, traced):
        t["label"] = s["label"]
    earth_line = traced[0]
    earth_hcs = hcs_distance(hcs, earth["lon"], earth["lat"])
    m = out.input_map
    return {"source": source, "map_file": os.path.basename(path), "map_date": str(m.date.isot)[:19],
            "map_instrument": str(m.meta.get("telescop") or m.meta.get("instrume") or source.upper()),
            "rss_rsun": rss, "earth": dict(earth, hcs_distance_deg=None if earth_hcs is None else round(earth_hcs, 2)),
            "earth_source": earth_line, "traced": traced[1:],
            "hcs": [ln[:: max(1, len(ln) // 200)].round(2).tolist() for ln in hcs],
            "plot": plot(out, hcs, traced, earth),
            "method": ("PFSS (sunkit-magex), map resampled to 360 x 180, 35 radial cells; Earth connection by "
                       "ballistic mapping at constant speed (Neugebauer et al. 1998)"),
            "classes": f"active region: |B_r| >= {AR_THRESHOLD_G:g} G at the photospheric footpoint"}
