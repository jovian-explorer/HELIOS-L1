"""
Positions of the planets, the Moon and the spacecraft from SPICE kernels, so that what the app
draws and uses is where the bodies were, not an orbit model.

* Planets, Earth and the Moon: the NAIF generic planetary ephemeris DE440s (downloaded once,
  shared with the radio occultation tool).
* Spacecraft: SPK files (type 13) written from JPL Horizons state vectors with
  helios.core.occultation.horizons_spk, one per spacecraft and calendar month (with a day of
  margin), cached; the current month is written again when it is a day old.

state() answers None when no kernel can be had (offline and not cached, or a time Horizons does
not cover); callers then use a labelled approximation or show nothing, never an invented
position.
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, Optional, Tuple

import numpy as np

from helios.core import occultation as oc

_log = logging.getLogger("helios.ephemeris")

# NAIF / JPL Horizons IDs (checked in the Horizons spacecraft list, October 2026). Mars is its
# barycentre (4): DE440s has no body 499; the two differ by less than 1 km.
NAIF_IDS: Dict[str, str] = {
    "EARTH": "399", "MOON": "301", "MERCURY": "199", "VENUS": "299", "MARS": "4",
    "PARKER_SOLAR_PROBE": "-96", "SOLAR_ORBITER": "-144", "STEREO_A": "-234",
    "DSCOVR": "-78", "ACE": "-92", "WIND": "-8", "SOHO": "-21", "ADITYA_L1": "-156",
    "SWFO_L1": "-231", "IMAP": "-43",
    "GOES_16": "-141866", "GOES_18": "-151850", "GOES_19": "-160133",
}
PLANETARY = {"399", "301", "199", "299", "4"}
FAILURE_RETRY_S = 600.0   # after a failed download, try again for the same file only after this
CURRENT_REFRESH_S = 86400.0

_failed: Dict[str, float] = {}


def _fetch(url: str) -> bytes:
    return oc._get(url)  # looked up at call time (tests replace it)

_lock = threading.Lock()


def _windows(t: datetime):
    """Kernel spans tried for time t: about 3 months either side of its month (enough for the
    orbit tracks of the L1 spacecraft, ~178-day period), then just the month (Horizons refuses a
    span that runs past the start or end of a spacecraft's ephemeris)."""
    start = t.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    nxt = (start + timedelta(days=32)).replace(day=1)
    return [(start - timedelta(days=92), nxt + timedelta(days=92)), (start - timedelta(days=1), nxt + timedelta(days=1))]


def _clip_to_coverage(message: str, start: datetime, end: datetime):
    """Horizons names where a spacecraft's ephemeris ends ("No ephemeris for target ... after
    A.D. 2026-NOV-02 00:01:09.1825 TDB", or "prior to A.D. ..."): the span cut to it, two hours
    inside (horizons_spk asks an hour wider), or None when it names no limit."""
    lim = re.search(r"(after|prior to) A\.D\. (\d{4}-[A-Za-z]{3}-\d{2} \d{2}:\d{2}:\d{2})", message)
    if not lim:
        return None
    at = datetime.strptime(lim.group(2), "%Y-%b-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    if lim.group(1) == "after":
        return start, min(end, at - timedelta(hours=2))
    return max(start, at + timedelta(hours=2)), end


def _recently_failed(key: str) -> bool:
    with _lock:
        return time.time() - _failed.get(key, 0.0) < FAILURE_RETRY_S


def _mark_failed(key: str) -> None:
    with _lock:
        _failed[key] = time.time()


def planetary_kernel(cache_dir: str) -> Optional[str]:
    """Local path of DE440s (downloaded once), or None when it cannot be had."""
    folder = os.path.join(str(cache_dir), "spice_kernels")
    if os.path.isdir(folder):
        have = sorted(f for f in os.listdir(folder) if re.fullmatch(r"de440s\.bsp", f))
        if have:
            return os.path.join(folder, have[-1])
    if _recently_failed("de440s"):
        return None
    try:
        sub, pattern = oc.GENERIC[0]
        os.makedirs(folder, exist_ok=True)
        return oc._download(oc.NAIF + sub + "de440s.bsp", os.path.join(folder, "de440s.bsp"), _fetch)
    except Exception as exc:  # network, disk, HTTP: no kernel now
        _log.info("DE440s unavailable: %s", exc)
        _mark_failed("de440s")
        return None


def spacecraft_kernel(naif_id: str, t: datetime, cache_dir: str) -> Optional[str]:
    """SPK of a spacecraft covering t (Horizons, cached), or None."""
    spans = _windows(t)
    for start, end in spans:
        key = f"{naif_id}:{start:%Y%m%d}:{end:%Y%m%d}"
        if _recently_failed(key):
            continue
        try:
            path = oc.horizons_spk(naif_id, start, end, cache_dir, _fetch)
        except Exception as exc:  # offline, or Horizons has no ephemeris over this span
            _log.info("Horizons SPK for %s %s-%s unavailable: %s", naif_id, start.date(), end.date(), exc)
            _mark_failed(key)
            clipped = _clip_to_coverage(str(exc), start, end)
            if clipped and clipped[0] < t < clipped[1] and clipped not in spans:
                spans.append(clipped)
            continue
        # A span reaching into the future was written from Horizons' prediction: refresh daily.
        if end > datetime.now(timezone.utc) and time.time() - os.path.getmtime(path) > CURRENT_REFRESH_S:
            try:
                os.replace(path, path + ".old")
                path = oc.horizons_spk(naif_id, start, end, cache_dir, _fetch)
                os.remove(path + ".old")
            except Exception as exc:
                _log.info("Refreshing the SPK of %s failed (%s); using the cached one", naif_id, exc)
                if os.path.exists(path + ".old"):
                    os.replace(path + ".old", path)
        return path
    return None


def state(body: str, t: datetime, cache_dir: str) -> Optional[Tuple[np.ndarray, np.ndarray]]:
    """
    Heliocentric position (km) and velocity (km/s) of a body in ECLIPJ2000 at UTC time t
    (geometric, no light time), or None when no kernel covers it.
    """
    naif = NAIF_IDS.get(body)
    if naif is None:
        return None
    t = t.astimezone(timezone.utc) if t.tzinfo else t.replace(tzinfo=timezone.utc)
    de = planetary_kernel(cache_dir)
    if de is None:
        return None
    paths = [de]
    if naif not in PLANETARY:
        spk = spacecraft_kernel(naif, t, cache_dir)
        if spk is None:
            return None
        paths.append(spk)
    sp = oc._spice()
    try:
        oc.furnish(paths)
        with oc._lock():
            et = float(sp.str2et(t.strftime("%Y-%m-%dT%H:%M:%S.%f")))
            st, _ = sp.spkezr(naif, et, "ECLIPJ2000", "NONE", "10")
    except Exception as exc:  # SPICE: no coverage at this time
        _log.info("No SPICE state of %s at %s: %s", body, t, exc)
        return None
    st = np.asarray(st, dtype=float)
    return st[:3], st[3:]
