"""
Coronagraph measurements on the Sun-centred archive images (helios.core.solar_images):
running-difference images, height-time maps (J-maps) along a position angle, CME front
tracking and height-time fits, with a projection correction to the radial speed.

* Running difference: brightness of a frame minus that of the previous frame. The archive
  pictures are display images (colour tables of the Helioviewer Project), so the brightness
  is their luminance, not calibrated radiance: good for locating fronts, not for masses.
* J-map (Sheeley et al. 1999, JGR 104, 24739, doi:10.1029/1999JA900308): for each frame the
  difference brightness along a radial line at position angle PA (degrees counterclockwise
  from solar north, through east; north up and east left in the pictures), averaged over a
  few degrees of PA, from r_min to r_max solar radii; frames stacked in time. An outward
  moving front is a bright track rising with time.
* Automatic front: in every frame, the largest height where the difference exceeds k times
  its robust noise (1.4826 median absolute deviation) along the line, with a few
  neighbouring heights above it too; a point lower than the previous one, or reached faster
  than 4000 km/s from it, is skipped and the track ends at the edge of the field. Points can also be
  set by hand, and should be checked on the map: bright streamers, other CMEs and proton
  "snow" can be picked up.
* Fit: least squares of h(t) = h0 + v t (linear) or + a t^2 / 2 (quadratic), with the
  standard errors from the covariance of the fit (scaled by the residuals).
* Projection: for radial motion along the direction of the source region (Stonyhurst
  longitude and latitude, as seen from Earth), an observer sees the plane-of-sky part
  v_pos = v sin(psi), psi the angle between that direction and the observer's line of sight
  to the Sun, cos(psi) = cos(lat) cos(lon - lon_observer) (projection effects as discussed
  by Vrsnak et al. 2007, A&A 469, 339, doi:10.1051/0004-6361:20077175). The correction
  v = v_pos / sin(psi) is not given for psi < 20 deg (near-halo events), where it diverges.
  The observer longitude is 0 for SOHO and SDO and the angle of STEREO-A or Solar Orbiter
  from Earth (ecliptic longitude difference of the orbit model; the solar equator's tilt of
  7 deg is ignored).
"""
from __future__ import annotations

import base64
import io
import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence

import numpy as np
from helios.core.constants import R_SUN_KM

MIN_PSI_DEG = 20.0
MAX_FRONT_KMS = 4000.0  # faster than any CME measured by LASCO (about 3500 km/s)
OBSERVERS = {"lasco": "SOHO", "eit": "SOHO", "aia": "SDO", "hmi": "SDO", "euvi": "STEREO_A", "cor": "STEREO_A",
             "eui": "SOLAR_ORBITER"}


def luminance(png: bytes) -> np.ndarray:
    """Brightness (0-255) of a picture: Rec. 601 luminance of its RGB, transparent pixels as 0."""
    from PIL import Image  # installed with matplotlib
    im = Image.open(io.BytesIO(png)).convert("RGBA")
    a = np.asarray(im, dtype=float)
    lum = 0.299 * a[..., 0] + 0.587 * a[..., 1] + 0.114 * a[..., 2]
    return lum * (a[..., 3] / 255.0)


def to_png(img: np.ndarray, lo: float, hi: float) -> bytes:
    """Grey PNG of img scaled from lo (black) to hi (white)."""
    from PIL import Image
    g = np.clip((img - lo) / max(hi - lo, 1e-9), 0.0, 1.0) * 255.0
    buf = io.BytesIO()
    Image.fromarray(g.astype(np.uint8)).save(buf, format="PNG")
    return buf.getvalue()


def robust_sigma(x: np.ndarray) -> float:
    x = x[np.isfinite(x)]
    return float(1.4826 * np.median(np.abs(x - np.median(x)))) if x.size else 0.0


def difference_png(current: bytes, previous: bytes, clip_sigma: float = 4.0) -> bytes:
    """Running-difference picture: current minus previous, grey 0 = no change, +-clip_sigma noise to white/black."""
    d = luminance(current) - luminance(previous)
    s = robust_sigma(d) or 1.0
    return to_png(d, -clip_sigma * s, clip_sigma * s)


def radial_profile(img: np.ndarray, center: Sequence[float], rsun_px: float, pa_deg: float,
                   r_rsun: np.ndarray, width_deg: float = 3.0) -> np.ndarray:
    """Mean of img along PA (deg from north through east; north up, east left) over +-width/2, nearest pixels."""
    h, w = img.shape
    out = np.zeros_like(r_rsun, dtype=float)
    angles = np.radians(pa_deg + np.linspace(-width_deg / 2.0, width_deg / 2.0, 5))
    for th in angles:
        x = np.rint(center[0] - r_rsun * rsun_px * np.sin(th)).astype(int)
        y = np.rint(center[1] - r_rsun * rsun_px * np.cos(th)).astype(int)
        ok = (x >= 0) & (x < w) & (y >= 0) & (y < h)
        prof = np.full(r_rsun.shape, np.nan)
        prof[ok] = img[y[ok], x[ok]]
        out += prof
    return out / len(angles)


def jmap(frames: List[Dict[str, Any]], pa_deg: float, r_min: float, r_max: float, n_r: int = 200,
         width_deg: float = 3.0, mode: str = "running") -> Dict[str, Any]:
    """
    Height-time map from frames [{"date", "png", "center_px", "rsun_px"}] (oldest first):
    rows are frames (the first is dropped for differences), columns heights in R_sun.
    mode: "running" (minus the previous frame), "base" (minus the first frame) or "direct".
    """
    if len(frames) < (2 if mode != "direct" else 1):
        raise ValueError("A J-map needs at least two frames.")
    if not 0.0 < r_min < r_max:
        raise ValueError("Heights must satisfy 0 < r_min < r_max.")
    r = np.linspace(r_min, r_max, int(n_r))
    profiles = [radial_profile(luminance(f["png"]), f["center_px"], f["rsun_px"], pa_deg, r, width_deg) for f in frames]
    if mode == "running":
        rows, times = [b - a for a, b in zip(profiles, profiles[1:])], [f["date"] for f in frames[1:]]
    elif mode == "base":
        rows, times = [p - profiles[0] for p in profiles[1:]], [f["date"] for f in frames[1:]]
    elif mode == "direct":
        rows, times = profiles, [f["date"] for f in frames]
    else:
        raise ValueError("mode must be 'running', 'base' or 'direct'.")
    m = np.array(rows)
    s = robust_sigma(m) or 1.0
    lo, hi = (-4 * s, 4 * s) if mode != "direct" else (np.nanpercentile(m, 1), np.nanpercentile(m, 99))
    # Picture: time to the right, height up (rows of the PNG are heights, top = r_max).
    png = to_png(np.nan_to_num(m.T[::-1], nan=lo), lo, hi)
    return {"times": times, "r_rsun": [round(float(x), 4) for x in r], "pa_deg": pa_deg, "width_deg": width_deg,
            "mode": mode, "values": m, "png_data_url": "data:image/png;base64," + base64.b64encode(png).decode()}


def auto_track(values: np.ndarray, r_rsun: Sequence[float], times: Sequence[str], k: float = 3.0,
               min_run: int = 3) -> List[Dict[str, Any]]:
    """Outermost height per frame where the difference exceeds k sigma for min_run consecutive heights."""
    r = np.asarray(r_rsun)
    s = robust_sigma(values) or 1.0
    points = []
    for row, t in zip(values, times):
        above = np.nan_to_num(row, nan=0.0) > k * s
        run = np.convolve(above.astype(int), np.ones(min_run, dtype=int), "valid") >= min_run
        idx = np.flatnonzero(run)
        if not idx.size:
            continue
        h = float(r[idx[-1] + min_run - 1])
        # A front only moves out, and not faster than MAX_FRONT_KMS: other points are noise
        # (or another feature). The track ends once the front has left the field of view.
        if points:
            dt = (_t(t) - _t(points[-1]["time"])).total_seconds()
            if h < points[-1]["r_rsun"] or (h - points[-1]["r_rsun"]) * R_SUN_KM > MAX_FRONT_KMS * dt:
                continue
        points.append({"time": t, "r_rsun": round(h, 3)})
        if h >= r[-1] - 2 * (r[1] - r[0]):
            break
    return points


def _t(s: str) -> datetime:
    t = datetime.fromisoformat(str(s).replace("Z", "+00:00").replace(" ", "T"))
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t


def fit_height_time(points: List[Dict[str, Any]], order: int = 1) -> Dict[str, Any]:
    """
    Least-squares fit of h(t) (R_sun) to the points: speed (km/s) and, for order 2, the
    acceleration (m/s^2), with 1-sigma errors; values at the last point's time.
    """
    if order not in (1, 2):
        raise ValueError("order must be 1 (constant speed) or 2 (constant acceleration).")
    pts = sorted(points, key=lambda p: _t(p["time"]))
    if len(pts) < order + 2:
        raise ValueError(f"A fit of order {order} needs at least {order + 2} points.")
    t0 = _t(pts[0]["time"])
    t = np.array([(_t(p["time"]) - t0).total_seconds() for p in pts])
    h = np.array([float(p["r_rsun"]) for p in pts]) * R_SUN_KM
    coef, cov = np.polyfit(t, h, order, cov=True)
    tl = t[-1]
    if order == 1:
        v, sv = coef[0], math.sqrt(cov[0, 0])
        a = sa = None
        h_end = coef[0] * tl + coef[1]
    else:
        a, sa = 2 * coef[0], 2 * math.sqrt(cov[0, 0])
        v = 2 * coef[0] * tl + coef[1]
        sv = math.sqrt(4 * tl * tl * cov[0, 0] + cov[1, 1] + 4 * tl * cov[0, 1])
        h_end = coef[0] * tl * tl + coef[1] * tl + coef[2]
    resid = h - np.polyval(coef, t)
    return {"order": order, "n_points": len(pts), "speed_kms": round(float(v), 1), "speed_err_kms": round(float(sv), 1),
            "acceleration_ms2": None if a is None else round(float(a) * 1000.0, 2),
            "acceleration_err_ms2": None if sa is None else round(float(sa) * 1000.0, 2),
            "height_end_rsun": round(float(h_end) / R_SUN_KM, 3), "time_end": pts[-1]["time"],
            "time_start": pts[0]["time"], "rms_residual_rsun": round(float(np.sqrt(np.mean(resid ** 2))) / R_SUN_KM, 3),
            "method": "least squares, errors from the fit covariance"}


def projection(speed_pos_kms: float, source_lon_deg: float, source_lat_deg: float,
               observer_lon_deg: float = 0.0) -> Dict[str, Any]:
    """Radial speed from the plane-of-sky speed for motion along the source direction (see module notes)."""
    cos_psi = math.cos(math.radians(source_lat_deg)) * math.cos(math.radians(source_lon_deg - observer_lon_deg))
    psi = math.degrees(math.acos(max(-1.0, min(1.0, cos_psi))))
    sin_psi = math.sin(math.radians(psi))
    ok = psi >= MIN_PSI_DEG and psi <= 180.0 - MIN_PSI_DEG
    return {"psi_deg": round(psi, 1), "projection_factor": round(sin_psi, 4),
            "radial_speed_kms": round(speed_pos_kms / sin_psi, 1) if ok else None,
            "note": None if ok else f"Direction within {MIN_PSI_DEG:g} deg of the line of sight (halo-like): "
                                    "the plane-of-sky correction is not applied.",
            "method": "v = v_pos / sin(psi), radial motion along the source direction (Vrsnak et al. 2007)"}


def observer_longitude(instrument: str, when: datetime) -> Dict[str, Any]:
    """Stonyhurst-like longitude of the instrument's spacecraft (deg west of Earth), from the orbit model."""
    craft = next((v for k, v in OBSERVERS.items() if instrument.startswith(k)), "SOHO")
    if craft in ("SOHO", "SDO"):
        return {"spacecraft": craft, "longitude_deg": 0.0, "source": "Earth's direction (L1 / geosynchronous)"}
    from helios.core.spice_engine import get_spice_engine
    eng = get_spice_engine()
    epoch = when.strftime("%Y-%m-%dT%H:%M:%S")
    lon = (eng.get_spacecraft_state(craft, epoch_utc=epoch)["heliocentric"]["ecliptic_longitude_deg"]
           - eng.get_spacecraft_state("EARTH", epoch_utc=epoch)["heliocentric"]["ecliptic_longitude_deg"])
    lon = (lon + 180.0) % 360.0 - 180.0
    return {"spacecraft": craft, "longitude_deg": round(lon, 2),
            "source": "orbit model, ecliptic longitude from Earth (solar equator tilt ignored)"}


def solver_inputs(fit: Dict[str, Any], speed_kms: float) -> Dict[str, Any]:
    """Inputs for the CME arrival solver (two heights 10 min apart at the fitted speed, ending at the last point)."""
    r2 = fit["height_end_rsun"]
    return {"r1_rsun": round(r2 - speed_kms * 600.0 / R_SUN_KM, 4), "r2_rsun": r2, "dt_minutes": 10.0,
            "launch_time": _t(fit["time_end"]).strftime("%Y-%m-%dT%H:%M"), "speed_kms": speed_kms}
