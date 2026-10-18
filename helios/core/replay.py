"""
Event replay: where the solar wind spacecraft were (Earth-fixed HEE frame) and what each measured
(solar wind speed and |B|) over an interval, on one time grid.

Data: the archive loaders (WIND, ACE, DSCOVR, SOHO, STEREO-A; 1-min) and the Event Analysis sources
(Solar Orbiter, Parker Solar Probe; their own cadence), all NASA CDAWeb. Positions: the SPICE
ephemeris (JPL Horizons), a few epochs per interval; the client interpolates between them.
"""
import math
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import pandas as pd

from helios.core.constants import AU_KM

MAX_HOURS = 72  # as Event Analysis (Solar Orbiter's plasma moments come every 4 s)
POSITION_EPOCHS = 12
POINTS = 432  # about 10-min means over 72 h
# (label, archive mission or None, Event Analysis mission or None, ephemeris id)
CRAFT = [("WIND", "WIND", None, "WIND"), ("ACE", "ACE", None, "ACE"), ("DSCOVR", "DSCOVR", None, "DSCOVR"),
         ("SOHO", "SOHO", None, "SOHO"), ("STEREO-A", "STEREO_A", None, "STEREO_A"),
         ("Solar Orbiter", None, "SOLO", "SOLAR_ORBITER"), ("Parker Solar Probe", None, "PSP", "PARKER_SOLAR_PROBE")]


def step_minutes(start: datetime, end: datetime) -> int:
    return max(1, math.ceil((end - start).total_seconds() / 60.0 / POINTS))


def on_grid(series: Optional[pd.Series], grid: pd.DatetimeIndex, minutes: int) -> List[Optional[float]]:
    """Block means of `series` on `grid` (bins labelled by their start); None where there is no sample."""
    if series is None or series.dropna().empty:
        return [None] * len(grid)
    s = series.dropna().resample(f"{minutes}min", origin=grid[0]).mean().reindex(grid)
    return [None if pd.isna(v) else round(float(v), 1) for v in s]


def hee_au(engine, ephemeris_id: str, iso: str, earth_au: float) -> Optional[List[float]]:
    """Heliocentric Earth ecliptic position (AU): X Sun to Earth, Z ecliptic north. The GSE vector
    from the Sun (Sun at x = 1 Earth distance) with X and Y reversed."""
    st = engine.get_spacecraft_state(ephemeris_id, iso)
    if not st.get("available", True) or "gse_coordinates" not in st:
        return None
    g = st["gse_coordinates"]
    return [round(earth_au - g["x_km"] / AU_KM, 5), round(-g["y_km"] / AU_KM, 5), round(g["z_km"] / AU_KM, 5)]


def positions(engine, start: datetime, end: datetime) -> Dict[str, Any]:
    """Earth and spacecraft HEE positions at POSITION_EPOCHS + 1 epochs (None without an ephemeris)."""
    times = [start + (end - start) * k / POSITION_EPOCHS for k in range(POSITION_EPOCHS + 1)]
    out: Dict[str, Any] = {"times": [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in times], "earth_au": [], "craft": {}}
    for t in times:
        iso = t.strftime("%Y-%m-%dT%H:%M:%S")
        earth = engine.get_spacecraft_state("EARTH", iso)
        d = earth["heliocentric"]["distance_km"] / AU_KM if earth.get("available", True) else 1.0
        out["earth_au"].append(round(d, 5))
        for label, _, _, eph in CRAFT:
            out["craft"].setdefault(label, []).append(hee_au(engine, eph, iso, d))
    return out


async def measurements(downloader, start: datetime, end: datetime) -> Dict[str, Any]:
    """Speed and |B| of each spacecraft on one grid, with the datasets used."""
    minutes = step_minutes(start, end)
    grid = pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq=f"{minutes}min", inclusive="left")
    craft = []
    for label, arch, event, _ in CRAFT:
        speed = bt = None
        datasets: List[str] = []
        if arch:
            res = await downloader.archive.fetch_mission(arch, start, end)
            f = res["frame"]
            if not f.empty:
                speed = f.get("speed")
                bt = f["bt"] if "bt" in f else None
                if bt is None and {"bx_gse", "by_gse", "bz_gse"} <= set(f.columns):
                    bt = (f["bx_gse"] ** 2 + f["by_gse"] ** 2 + f["bz_gse"] ** 2) ** 0.5
            datasets = [d["id"] for d in res["datasets"]]
        else:
            res = await downloader.events.fetch(event, start, end)
            p, f = res["plasma"], res["field"]
            if p is not None:
                speed = (p["vx"] ** 2 + p["vy"] ** 2 + p["vz"] ** 2) ** 0.5
            if f is not None:
                bt = (f["bx"] ** 2 + f["by"] ** 2 + f["bz"] ** 2) ** 0.5
            datasets = [d["id"] for d in res["datasets"]]
        craft.append({"name": label, "speed_kms": on_grid(speed, grid, minutes), "bt_nt": on_grid(bt, grid, minutes),
                      "datasets": datasets})
    return {"step_minutes": minutes, "times": [t.strftime("%Y-%m-%dT%H:%M:%SZ") for t in grid], "craft": craft}


def first_jump(times: List[str], speed: List[Optional[float]], jump_kms: float = 100.0) -> Optional[str]:
    """Start of the first grid step from which the speed stays at least `jump_kms` above the median of the
    three steps before it for three steps (a lasting rise: a shock or a fast stream). The three before must
    lie within `jump_kms` of each other (noisy series give none); they and the first step after must have data,
    and at least two of the three after."""
    for i in range(3, len(speed) - 2):
        before, after = speed[i - 3:i], [v for v in speed[i:i + 3] if v is not None]
        if None in before or speed[i] is None or len(after) < 2:
            continue
        before = sorted(before)
        if before[2] - before[0] < jump_kms and min(after) - before[1] >= jump_kms:
            return times[i]
    return None
