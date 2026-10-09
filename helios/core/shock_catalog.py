"""
Interplanetary shocks observed at L1 (WIND, ACE, DSCOVR) in the IPShocks database of the
University of Helsinki, for cross-matching with the shock analysis and the sudden
commencement search.

Source: E. Kilpua et al., The IPShocks Database, Zenodo, doi:10.5281/zenodo.19730292
(licence CC BY 4.0), described in Kilpua et al. (2015), J. Geophys. Res. 120, 4112,
doi:10.1002/2015JA021138. A snapshot of the L1 rows is bundled
(helios/data/ipshocks_l1.json, made with scripts/update_shock_catalog.py).

Method of the database (E. Lumme et al., Database of Heliospheric Shock Waves, method
documentation, 31 Oct 2019): 8-minute averages upstream ([t-9, t-1] min for a fast forward
shock) and downstream ([t+2, t+10] min); the mixed-mode normal MX3 (magnetic coplanarity
without velocity data); shock speed from mass flux; M_A = |V_up.n - V_sh| / V_A; the
magnetosonic Mach number with V_ms = sqrt(V_A^2 + c_s^2), c_s from T_p plus a fixed
T_e = 146277 K and gamma 5/3. Errors: the sample standard deviations of the window means,
propagated.
"""
from __future__ import annotations

import json
import math
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "ipshocks_l1.json"
DOI = "10.5281/zenodo.19730292"
LICENCE = "CC BY 4.0"
CITATION = ("Kilpua, E., Good, S., Soljento, J., Price, D. J., Isavnin, A., Lumme, E., Mäkelä, T. V., Isavnina, K. & "
            "Andréeová, K., The IPShocks Database, Zenodo, doi:10.5281/zenodo.19730292; Kilpua et al. (2015), "
            "J. Geophys. Res. 120, 4112, doi:10.1002/2015JA021138")
SPACECRAFT = {"Wind": "WIND", "ACE": "ACE", "DSCOVR": "DSCOVR"}
WINDOWS_MINUTES = {"upstream": [-9, -1], "downstream": [2, 10]}  # fast forward shocks
MATCH_MINUTES = 5.0
DRIVER_MINUTES = 15.0
RE_KM = 6371.2


@lru_cache(maxsize=1)
def load() -> Dict[str, Any]:
    """The bundled snapshot: {"events": [...], "version", "doi", "licence", "citation", ...}."""
    return json.loads(SNAPSHOT.read_text(encoding="utf-8"))


def event_time(e: Dict[str, Any]) -> datetime:
    return datetime.strptime(e["time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)


def events_between(events: List[Dict[str, Any]], start: datetime, end: datetime,
                   spacecraft: Optional[str] = None) -> List[Dict[str, Any]]:
    return [e for e in events if start <= event_time(e) < end and (spacecraft is None or e["spacecraft"] == spacecraft)]


def nearest(events: List[Dict[str, Any]], spacecraft: str, t: datetime,
            minutes: float = MATCH_MINUTES) -> Optional[Dict[str, Any]]:
    """The listed shock at `spacecraft` closest to t, within `minutes`."""
    best, gap = None, timedelta(minutes=minutes)
    for e in events:
        if e["spacecraft"] == spacecraft and abs(event_time(e) - t) <= gap:
            best, gap = e, abs(event_time(e) - t)
    return best


def planar_arrival(e: Dict[str, Any]) -> Optional[datetime]:
    """
    When a listed fast forward shock reaches the plane through the Earth's centre normal to
    it, for a planar front moving at the listed speed: t + |n . r| / V_sh. At 382 sudden
    commencements of 1995-2023 the SYM-H onset came 0.0 min after this on median (IQR -1.7
    to +1.6 min); the radial X / V_sh was 4 min late on median, 90 % within 20 min.
    """
    v = e.get("shock_speed_kms")
    if e["type"] != "FF" or not v or v < 150:
        return None
    n, r = e["normal_gse"], e["position_gse_re"]
    reach = abs(sum(a * b for a, b in zip(n, r))) / math.sqrt(sum(a * a for a in n)) * RE_KM
    return event_time(e) + timedelta(seconds=reach / v)


def driver_of(events: List[Dict[str, Any]], t: datetime, minutes: float = DRIVER_MINUTES) -> Optional[Dict[str, Any]]:
    """The listed fast forward shock whose planar arrival is closest to t, within `minutes`."""
    best, gap = None, timedelta(minutes=minutes)
    for e in events:
        a = planar_arrival(e)
        if a is not None and abs(a - t) <= gap:
            best, gap = e, abs(a - t)
    return best


def angle_deg(n1, n2) -> float:
    """Angle between two normals, ignoring their sense (0-90 deg)."""
    dot = abs(sum(a * b for a, b in zip(n1, n2)))
    norm = math.sqrt(sum(a * a for a in n1) * sum(b * b for b in n2))
    return math.degrees(math.acos(min(1.0, dot / norm)))
