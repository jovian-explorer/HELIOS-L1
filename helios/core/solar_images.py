"""
Solar images by time and instrument from the Helioviewer Project (api.helioviewer.org):
SDO/AIA and HMI, SOHO/LASCO C2 and C3 and EIT, STEREO-A/SECCHI EUVI, COR1 and COR2, and
Solar Orbiter/EUI. The Helioviewer server keeps the image archives of these missions as
JPEG 2000 files and renders them; this module asks it for

* the image closest to a time (getClosestImage: observation time, native plate scale, solar
  radius in pixels), and
* a Sun-centred PNG of that image at a chosen field of view (takeScreenshot with x0 = y0 = 0
  arcsec), so every frame of an instrument has the same geometry: the Sun's centre is the
  centre of the picture and the scale in arcsec per pixel is known. Heights in solar radii
  follow from the distance to the centre (see `frame_geometry`).

Science-grade files (FITS, calibrated levels) are a different product: `fits_search` finds
them with SunPy's Fido (VSO, JSOC and other providers) when SunPy is installed.

Answers are cached on disk; requests for times more than a day in the past are kept for
good (the archive does not change), recent ones for an hour.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import urlencode

API = "https://api.helioviewer.org/v2"
CREDIT = ("Images: Helioviewer Project (helioviewer.org) from SDO/AIA and HMI (NASA/SDO and the AIA and HMI "
          "science teams), SOHO/LASCO and EIT (ESA/NASA), STEREO/SECCHI (NASA, NRL) and Solar Orbiter/EUI "
          "(ESA/NASA, EUI consortium).")
RECENT_TTL_S = 3600

# key -> (Helioviewer sourceId, label, kind, half width of the picture in solar radii)
SOURCES: Dict[str, tuple] = {
    "aia_94": (8, "SDO/AIA 94 Å", "euv", 1.3),
    "aia_131": (9, "SDO/AIA 131 Å", "euv", 1.3),
    "aia_171": (10, "SDO/AIA 171 Å", "euv", 1.3),
    "aia_193": (11, "SDO/AIA 193 Å", "euv", 1.3),
    "aia_211": (12, "SDO/AIA 211 Å", "euv", 1.3),
    "aia_304": (13, "SDO/AIA 304 Å", "euv", 1.3),
    "aia_335": (14, "SDO/AIA 335 Å", "euv", 1.3),
    "aia_1600": (15, "SDO/AIA 1600 Å", "euv", 1.3),
    "hmi_mag": (19, "SDO/HMI magnetogram", "disk", 1.1),
    "eit_195": (1, "SOHO/EIT 195 Å", "euv", 1.3),
    "lasco_c2": (4, "SOHO/LASCO C2", "coronagraph", 6.5),
    "lasco_c3": (5, "SOHO/LASCO C3", "coronagraph", 30.0),
    "euvi_195": (21, "STEREO-A/EUVI 195 Å", "euv", 1.4),
    "euvi_304": (23, "STEREO-A/EUVI 304 Å", "euv", 1.4),
    "cor1": (28, "STEREO-A/COR1", "coronagraph", 4.0),
    "cor2": (29, "STEREO-A/COR2", "coronagraph", 15.0),
    "eui_fsi_174": (84, "Solar Orbiter/EUI FSI 174 Å", "euv", 1.6),
    "eui_fsi_304": (85, "Solar Orbiter/EUI FSI 304 Å", "euv", 1.6),
}
MAX_FRAMES = 48
SIZES = (256, 512, 1024)


def _utc(t: datetime) -> datetime:
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


def _iso(t: datetime) -> str:
    return _utc(t).strftime("%Y-%m-%dT%H:%M:%SZ")


def source(key: str) -> tuple:
    if key not in SOURCES:
        raise ValueError(f"Unknown instrument '{key}'; available: {', '.join(SOURCES)}.")
    return SOURCES[key]


def catalog() -> List[Dict[str, Any]]:
    return [{"key": k, "label": label, "kind": kind, "half_width_rsun": hw, "helioviewer_source_id": sid}
            for k, (sid, label, kind, hw) in SOURCES.items()]


def frame_geometry(meta: Dict[str, Any], size: int, half_width_rsun: float) -> Dict[str, Any]:
    """
    Geometry of the Sun-centred picture of one image: the solar radius in arcsec (native radius
    in pixels times the native plate scale), the picture scale in arcsec per pixel and the
    solar radius in picture pixels. The Sun's centre is at (size/2, size/2).
    """
    rsun_arcsec = float(meta["rsun"]) * float(meta["scale"])
    scale = 2.0 * half_width_rsun * rsun_arcsec / size
    return {"rsun_arcsec": round(rsun_arcsec, 2), "scale_arcsec_per_px": scale,
            "rsun_px": rsun_arcsec / scale, "center_px": [size / 2.0, size / 2.0], "size_px": size}


class SolarImageClient:
    """`fetch_text(url)` and `fetch_bytes(url)` are async and return None on any failure."""

    def __init__(self, fetch_text: Callable, fetch_bytes: Callable, cache_dir):
        self.fetch_text, self.fetch_bytes = fetch_text, fetch_bytes
        self.cache_dir = os.path.join(str(cache_dir), "solar_images")
        os.makedirs(self.cache_dir, exist_ok=True)

    def _fresh(self, path: str, t: datetime) -> bool:
        if not os.path.exists(path):
            return False
        old = datetime.now(timezone.utc) - _utc(t) > timedelta(days=1)
        return old or time.time() - os.path.getmtime(path) < RECENT_TTL_S

    async def closest(self, key: str, t: datetime) -> Optional[Dict[str, Any]]:
        """Metadata of the image closest to t (id, date, native scale, rsun in pixels), or None."""
        sid = source(key)[0]
        path = os.path.join(self.cache_dir, f"closest_{sid}_{_utc(t):%Y%m%dT%H%M%S}.json")
        if self._fresh(path, t):
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        body = await self.fetch_text(f"{API}/getClosestImage/?" + urlencode({"date": _iso(t), "sourceId": sid}))
        try:
            meta = json.loads(body) if body else None
        except ValueError:
            meta = None
        if not meta or "date" not in meta or "error" in meta:
            return None
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f)
        return meta

    async def frames(self, key: str, start: datetime, end: datetime, n: int, size: int = 512) -> Dict[str, Any]:
        """
        Up to n images between start and end: the images closest to n evenly spaced times,
        each listed once and only if taken inside [start, end], oldest first.
        """
        sid, label, kind, half = source(key)
        start, end = _utc(start), _utc(end)
        if end <= start:
            raise ValueError("The end must be after the start.")
        n = max(1, min(MAX_FRAMES, int(n)))
        times = [start + (end - start) * (i / max(1, n - 1)) for i in range(n)] if n > 1 else [start]
        seen, out, failed = set(), [], 0
        for t in times:
            meta = await self.closest(key, t)
            if meta is None:
                failed += 1
                continue
            taken = datetime.strptime(meta["date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
            if meta["id"] in seen or not start - timedelta(minutes=1) <= taken <= end + timedelta(minutes=1):
                continue
            seen.add(meta["id"])
            out.append({"id": meta["id"], "date": meta["date"], "observatory_instrument": meta.get("name", label),
                        **frame_geometry(meta, size, half),
                        "image_url": "/api/solar_images/image?" + urlencode(
                            {"instrument": key, "date": taken.strftime("%Y-%m-%dT%H:%M:%S"), "size": size})})
        out.sort(key=lambda f: f["date"])
        return {"instrument": key, "label": label, "kind": kind, "half_width_rsun": half, "frames": out,
                "requested": n, "unreachable_requests": failed, "source": "Helioviewer Project API v2",
                "credit": CREDIT}

    async def image(self, key: str, t: datetime, size: int = 512) -> Optional[bytes]:
        """Sun-centred PNG of the image closest to t (cached), or None if it cannot be had."""
        if size not in SIZES:
            raise ValueError(f"size must be one of {SIZES}.")
        sid, _, _, half = source(key)
        meta = await self.closest(key, t)
        if meta is None:
            return None
        taken = datetime.strptime(meta["date"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        path = os.path.join(self.cache_dir, f"img_{sid}_{taken:%Y%m%dT%H%M%S}_{size}.png")
        if os.path.exists(path):
            with open(path, "rb") as f:
                return f.read()
        geo = frame_geometry(meta, size, half)
        png = await self.fetch_bytes(f"{API}/takeScreenshot/?" + urlencode({
            "date": _iso(taken), "imageScale": f"{geo['scale_arcsec_per_px']:.4f}", "layers": f"[{sid},1,100]",
            "x0": 0, "y0": 0, "width": size, "height": size, "display": "true", "watermark": "false"}))
        if not png or not png.startswith(b"\x89PNG"):
            return None
        with open(path + ".tmp", "wb") as f:
            f.write(png)
        os.replace(path + ".tmp", path)
        return png


# SunPy Fido instrument attributes for the science files of each instrument family.
FIDO_QUERIES = {
    "aia": ("AIA", "wavelength"), "hmi_mag": ("HMI", None), "eit": ("EIT", "wavelength"),
    "lasco_c2": ("LASCO", "C2"), "lasco_c3": ("LASCO", "C3"), "euvi": ("SECCHI", "EUVI"),
    "cor1": ("SECCHI", "COR1"), "cor2": ("SECCHI", "COR2"), "eui_fsi": ("EUI", "wavelength"),
}


def fits_search(key: str, start: datetime, end: datetime, limit: int = 20,
                download_to: Optional[str] = None) -> Dict[str, Any]:
    """
    Science files (FITS) for an instrument and interval through SunPy's Fido (VSO, JSOC and
    the other providers SunPy knows); with download_to, the first `limit` files are fetched
    into that folder. Raises ImportError when SunPy is not installed.
    """
    from sunpy.net import Fido, attrs as a  # optional dependency
    import astropy.units as u
    _, label, _, _ = source(key)
    family = next(f for f in FIDO_QUERIES if key.startswith(f))
    inst, extra = FIDO_QUERIES[family]
    q = [a.Time(_utc(start).replace(tzinfo=None), _utc(end).replace(tzinfo=None)), a.Instrument(inst)]
    if extra == "wavelength":
        q.append(a.Wavelength(int(key.rsplit("_", 1)[1]) * u.AA))
    elif extra in ("C2", "C3", "EUVI", "COR1", "COR2"):
        q.append(a.Detector(extra))
    if key.startswith(("euvi", "cor")):
        q.append(a.Source("STEREO_A"))
    res = Fido.search(*q)
    rows = []
    for table in res:
        for r in table[:limit - len(rows)] if len(rows) < limit else []:
            rows.append({k: str(r[k]) for k in r.colnames if k in ("Start Time", "End Time", "Source", "Instrument",
                                                                    "Provider", "Physobs", "Wavelength", "fileid", "Size")})
    out = {"instrument": key, "label": label, "n_found": int(sum(len(t) for t in res)), "listed": rows,
           "searched_with": "SunPy Fido"}
    if download_to and out["n_found"]:
        os.makedirs(download_to, exist_ok=True)
        files = Fido.fetch(res[0][:limit], path=os.path.join(download_to, "{file}"), progress=False)
        out["downloaded"] = [{"path": str(f), "bytes": os.path.getsize(f)} for f in files]
        out["download_errors"] = [str(e) for e in getattr(files, "errors", [])]
    return out
