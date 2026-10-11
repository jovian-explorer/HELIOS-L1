"""
Event correlation for remote sensing: a disturbance seen at time t, height h (R_sun) and
position angle PA (degrees from solar north through east, as seen from Earth), e.g. in a radio
occultation or a white-light image, matched with the CMEs of the catalogues and the flares
before it.

Catalogues (read when asked for and cached; months more than 40 days old are kept for good):
* SOHO/LASCO CDAW CME catalogue (Yashiro et al. 2004, JGR 109, A07105, doi:10.1029/2003JA010282;
  cdaw.gsfc.nasa.gov, monthly lists): first C2 time, central PA
  and angular width, linear speed, measurement PA. The first height is read from the
  catalogue's height-time file of the CME.
* CACTus (Robbrecht & Berghmans 2004, A&A 425, 1097, doi:10.1051/0004-6361:20041302; SIDC,
  sidc.be/cactus, LASCO C2/C3 monthly lists): onset time t0, principal angle,
  width and median speed. t0 is taken at 2.2 R_sun (the inner edge of the C2 field where the
  detection starts), an approximation.
* DONKI (NASA CCMC, ccmc.gsfc.nasa.gov/DONKI-API): CMEs with the most accurate cone-model
  analysis (time at 21.5 R_sun, speed, direction and half angle) and their linked flares.
* Flares: GOES events of the NOAA SWPC list through the Heliophysics Event Knowledge base
  (HEK, frm_name SWPC) and DONKI flares (class, peak time, source location, active region).

Arrival at height h along a CME: t_h = t_ref + (h - h_ref) R_sun / v at the catalogue speed
(constant speed: for decelerating fast CMEs the arrival far out is later). A CME matches when
the PA lies inside its angular extent (central PA +- width / 2; halos and, for DONKI, cones
containing the Sun-Earth line cover every PA) and |t_h - t| is within the window. DONKI cone
directions are put on the sky as seen from Earth: PA = atan2(-cos(lat) sin(lon), sin(lat)).
"""
from __future__ import annotations

import json
import math
import os
import re
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional
from helios.core.constants import R_SUN_KM
from helios.core.timeutil import parse_utc as _t, utc as _utc
from helios.core.cache import cached_text

CDAW = "https://cdaw.gsfc.nasa.gov/CME_list/UNIVERSAL_ver2/"
CACTUS = "https://www.sidc.be/cactus/catalog/LASCO/2_5_0/qkl/"
DONKI = "https://ccmc.gsfc.nasa.gov/DONKI-API/get/"
HEK = "https://www.lmsal.com/hek/her"
CACTUS_H0 = 2.2
RECENT_TTL_S = 6 * 3600


class Catalogs:
    """`fetch_text(url)` is async and returns None on failure."""

    def __init__(self, fetch_text: Callable, cache_dir):
        self.fetch_text = fetch_text
        self.dir = os.path.join(str(cache_dir), "event_catalogs")
        os.makedirs(self.dir, exist_ok=True)

    async def _get(self, url: str, key: str, period_end: datetime) -> Optional[str]:
        # For good if fetched more than 40 days after the period (catalogues are revised for a while).
        path = os.path.join(self.dir, re.sub(r"[^A-Za-z0-9_.-]", "_", key))
        text, _ = await cached_text(path, url, self.fetch_text, RECENT_TTL_S, period_end + timedelta(days=40))
        return text

    @staticmethod
    def _months(start: datetime, end: datetime) -> List[datetime]:
        m, out = datetime(start.year, start.month, 1, tzinfo=timezone.utc), []
        while m <= end:
            out.append(m)
            m = datetime(m.year + (m.month == 12), m.month % 12 + 1, 1, tzinfo=timezone.utc)
        return out

    async def cdaw(self, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        out = []
        for m in self._months(start, end):
            nxt = datetime(m.year + (m.month == 12), m.month % 12 + 1, 1, tzinfo=timezone.utc)
            html = await self._get(f"{CDAW}{m:%Y_%m}/univ{m:%Y_%m}.html", f"cdaw_{m:%Y_%m}.html", nxt)
            if html:
                out += parse_cdaw(html, m)
        return [c for c in out if start <= _t(c["time"]) <= end]

    async def cdaw_first_height(self, cme: Dict[str, Any]) -> Optional[float]:
        if not cme.get("yht"):
            return None
        m = _t(cme["time"])
        text = await self._get(f"{CDAW}{m:%Y_%m}/{cme['yht']}", "cdaw_" + cme["yht"].replace("/", "_"), m + timedelta(days=31))
        rows = [ln.split() for ln in (text or "").splitlines() if ln and not ln.startswith("#")]
        try:
            return float(rows[0][0])
        except (IndexError, ValueError):
            return None

    async def cactus(self, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        out = []
        for m in self._months(start, end):
            nxt = datetime(m.year + (m.month == 12), m.month % 12 + 1, 1, tzinfo=timezone.utc)
            text = await self._get(f"{CACTUS}{m:%Y/%m}/cmecat.txt", f"cactus_{m:%Y_%m}.txt", nxt)
            if text:
                out += parse_cactus(text)
        return [c for c in out if start <= _t(c["time"]) <= end]

    async def donki(self, kind: str, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        url = f"{DONKI}{kind}?startDate={start:%Y-%m-%d}&endDate={end:%Y-%m-%d}"
        text = await self._get(url, f"donki_{kind}_{start:%Y%m%d}_{end:%Y%m%d}.json", end)
        try:
            return json.loads(text) if text else []
        except ValueError:
            return []

    async def hek_flares(self, start: datetime, end: datetime) -> List[Dict[str, Any]]:
        q = (f"{HEK}?cosec=2&cmd=search&type=column&event_type=fl&event_coordsys=helioprojective&x1=-5000&x2=5000"
             f"&y1=-5000&y2=5000&event_starttime={start:%Y-%m-%dT%H:%M:%S}&event_endtime={end:%Y-%m-%dT%H:%M:%S}"
             "&return=event_starttime,event_peaktime,event_endtime,fl_goescls,frm_name,hpc_x,hpc_y,ar_noaanum")
        text = await self._get(q, f"hek_fl_{start:%Y%m%dT%H%M%S}_{end:%Y%m%dT%H%M%S}.json", end)
        try:
            rows = json.loads(text)["result"] if text else []
        except (ValueError, KeyError):
            return []
        return [r for r in rows if r.get("frm_name") == "SWPC" and r.get("fl_goescls")
                and start <= _t(r.get("event_peaktime") or r["event_starttime"]) <= end]


def _cells(row: str) -> Dict[str, str]:
    cells = {}
    for name, body in re.findall(r'<td headers="(hd_[a-z0-9_]+)"[^>]*>(.*?)</td>', row, re.S):
        text = re.sub(r"<[^>]+>|<!.*?>", " ", body)
        cells.setdefault(name, []).append(" ".join(text.split()))
    return cells


def parse_cdaw(html: str, month: datetime) -> List[Dict[str, Any]]:
    """Rows of a CDAW monthly list: time, central PA (None for halos), width, linear speed, MPA."""
    out = []
    for row in html.split("<tr")[1:]:
        c = _cells(row)
        if "hd_date_time" not in c or len(c["hd_date_time"]) < 2:
            continue
        date, tm = c["hd_date_time"][0], c["hd_date_time"][1]
        cpa = c.get("hd_cpa", [""])[0]
        try:  # rows with a missing value (e.g. "----") are left out instead of failing the whole month
            t = datetime.strptime(f"{date} {tm}", "%Y/%m/%d %H:%M:%S").replace(tzinfo=timezone.utc)
            width = float(c["hd_wd"][0])
            speed = float(c["hd_v1"][0])
            center = None if cpa.lower().startswith("halo") else float(cpa)
        except (KeyError, IndexError, ValueError):
            continue
        yht = re.search(r'href="(yht/[^"]+\.yht)"', row)
        out.append({"catalog": "CDAW", "time": t.strftime("%Y-%m-%d %H:%M:%S"),
                    "central_pa_deg": center,
                    "width_deg": width, "speed_kms": speed, "yht": yht.group(1) if yht else None})
    return out


def parse_cactus(text: str) -> List[Dict[str, Any]]:
    out = []
    for ln in text.splitlines():
        if ln.replace(" ", "").lower().startswith("#flow|"):
            break  # the list of flows (suspicious detections) follows the CMEs
        p = [x.strip() for x in ln.split("|")]
        if len(p) < 10 or not p[0].isdigit():
            continue
        try:
            t = datetime.strptime(p[1], "%Y/%m/%d %H:%M").replace(tzinfo=timezone.utc)
            out.append({"catalog": "CACTus", "time": t.strftime("%Y-%m-%d %H:%M:%S"), "central_pa_deg": float(p[3]),
                        "width_deg": float(p[4]), "speed_kms": float(p[5]), "halo": p[9] or None})
        except ValueError:
            continue
    return out


def pa_inside(pa: float, center: Optional[float], width: float) -> bool:
    if center is None or width >= 360.0:
        return True
    return abs((pa - center + 180.0) % 360.0 - 180.0) <= width / 2.0


def donki_pa(lon: float, lat: float) -> float:
    """Sky position angle (from north through east, Earth view) of a Stonyhurst direction."""
    x = math.cos(math.radians(lat)) * math.sin(math.radians(lon))  # west positive
    y = math.sin(math.radians(lat))
    return math.degrees(math.atan2(-x, y)) % 360.0


def arrival(t_ref: datetime, h_ref: float, h: float, v_kms: float) -> Optional[datetime]:
    if not v_kms or v_kms <= 0:
        return None
    return t_ref + timedelta(seconds=(h - h_ref) * R_SUN_KM / v_kms)


async def match(cat: Catalogs, when: datetime, height_rsun: float, pa_deg: float,
                window_hours: float = 3.0) -> Dict[str, Any]:
    """Catalogue CMEs reaching height_rsun at pa_deg within window_hours of `when`, and the flares before."""
    when = _utc(when)
    lead = timedelta(hours=max(24.0, height_rsun * R_SUN_KM / 200.0 / 3600.0 + window_hours))  # slow CMEs
    start, end = when - lead, when + timedelta(hours=window_hours)
    cands: List[Dict[str, Any]] = []

    def add(c, t_ref, h_ref, pa_ok, extra=None):
        t_h = arrival(t_ref, h_ref, height_rsun, c["speed_kms"])
        if t_h is None:
            return
        dt = (t_h - when).total_seconds() / 3600.0
        if abs(dt) <= window_hours:
            cands.append({**c, **(extra or {}), "reference_height_rsun": h_ref, "pa_inside": pa_ok,
                          "arrival_at_height": t_h.strftime("%Y-%m-%d %H:%M:%S"), "arrival_minus_event_h": round(dt, 2)})

    for c in await cat.cdaw(start, end):
        h0 = await cat.cdaw_first_height(c) if pa_inside(pa_deg, c["central_pa_deg"], c["width_deg"]) else None
        add(c, _t(c["time"]), h0 or 2.6, pa_inside(pa_deg, c["central_pa_deg"], c["width_deg"]),
            {"reference_height_source": "first height of the CDAW height-time file" if h0 else "assumed 2.6 R_sun"})
    for c in await cat.cactus(start, end):
        add(c, _t(c["time"]), CACTUS_H0, pa_inside(pa_deg, c["central_pa_deg"], c["width_deg"]),
            {"reference_height_source": f"onset taken at {CACTUS_H0} R_sun"})
    donki = await cat.donki("CME", start, end)
    for d in donki:
        an = next((a for a in d.get("cmeAnalyses") or [] if a.get("isMostAccurate")), None)
        if not an or an.get("time21_5") is None or an.get("speed") is None or an.get("longitude") is None:
            continue
        half = float(an.get("halfAngle") or 0.0)
        lon, lat = float(an["longitude"]), float(an.get("latitude") or 0.0)
        to_earth = math.degrees(math.acos(math.cos(math.radians(lat)) * math.cos(math.radians(lon))))
        center = donki_pa(lon, lat)
        pa_ok = to_earth <= half or pa_inside(pa_deg, center, 2 * half)
        c = {"catalog": "DONKI", "time": _t(d["startTime"]).strftime("%Y-%m-%d %H:%M:%S"), "central_pa_deg": round(center, 1),
             "width_deg": 2 * half, "speed_kms": float(an["speed"]), "activity_id": d.get("activityID"),
             "source_location": d.get("sourceLocation"), "direction_lon_lat": [lon, lat],
             "linked_flares": [l["activityID"] for l in d.get("linkedEvents") or [] if "FLR" in l["activityID"]]}
        add(c, _t(an["time21_5"]), 21.5, pa_ok, {"reference_height_source": "DONKI time at 21.5 R_sun"})
    cands.sort(key=lambda c: (not c["pa_inside"], abs(c["arrival_minus_event_h"])))
    f0 = when - timedelta(hours=24)
    flares = [{"catalog": "GOES (NOAA SWPC via HEK)", "start": r["event_starttime"], "peak": r["event_peaktime"],
               "class": r["fl_goescls"], "noaa_ar": r.get("ar_noaanum"),
               "hpc_arcsec": [r.get("hpc_x"), r.get("hpc_y")]} for r in await cat.hek_flares(f0, when)]
    flares += [{"catalog": "DONKI", "start": f["beginTime"], "peak": f["peakTime"], "class": f.get("classType"),
                "noaa_ar": f.get("activeRegionNum"), "source_location": f.get("sourceLocation"), "id": f.get("flrID")}
               for f in await cat.donki("FLR", f0, when) if f0 <= _t(f["peakTime"]) <= when]
    flares.sort(key=lambda f: f["peak"])
    return {"event": {"time": when.strftime("%Y-%m-%d %H:%M:%S"), "height_rsun": height_rsun, "pa_deg": pa_deg,
                      "window_hours": window_hours},
            "cmes": cands, "flares": flares,
            "method": "constant catalogue speed from the catalogue's reference height; PA inside the angular extent",
            "sources": ["SOHO/LASCO CDAW CME catalogue", "CACTus (SIDC)", "DONKI (NASA CCMC)", "HEK (GOES flares, NOAA SWPC)"]}
