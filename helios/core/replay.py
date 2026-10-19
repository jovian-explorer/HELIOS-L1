"""
Event replay: where the solar wind spacecraft were (Earth-fixed HEE frame) and what each measured
(solar wind speed and |B|) over an interval, on one time grid.

Data: the archive loaders (1-min means of NASA CDAWeb data, and of NOAA NCEI DSCOVR plasma after June 2019,
cached by day; Solar Orbiter's 4-s plasma moments too). Positions: the SPICE ephemeris (JPL Horizons) at a few epochs; the client interpolates.
"""
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from helios.core.constants import AU_KM

MAX_DAYS = 14
POSITION_EPOCHS = 24
POINTS = 432  # 10-min means over 72 h
# (label, archive mission, ephemeris id)
CRAFT = [("WIND", "WIND", "WIND"), ("ACE", "ACE", "ACE"), ("DSCOVR", "DSCOVR", "DSCOVR"), ("SOHO", "SOHO", "SOHO"),
         ("STEREO-A", "STEREO_A", "STEREO_A"), ("Solar Orbiter", "SOLO", "SOLAR_ORBITER"),
         ("Parker Solar Probe", "PSP", "PARKER_SOLAR_PROBE")]


def step_minutes(start: datetime, end: datetime) -> int:
    """The shortest round step giving at most POINTS steps: 10 min for 72 h, 60 min for 14 days."""
    need = (end - start).total_seconds() / 60.0 / POINTS
    return next(m for m in (1, 2, 5, 10, 15, 20, 30, 60) if m >= need)


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
        for label, _, eph in CRAFT:
            out["craft"].setdefault(label, []).append(hee_au(engine, eph, iso, d))
    return out


async def measurements(archive, start: datetime, end: datetime) -> Dict[str, Any]:
    """Speed and |B| of each spacecraft on one grid, with the datasets used (all fetched at once)."""
    minutes = step_minutes(start, end)
    grid = pd.date_range(pd.Timestamp(start), pd.Timestamp(end), freq=f"{minutes}min", inclusive="left")
    results = await asyncio.gather(*(archive.fetch_mission(m, start, end) for _, m, _ in CRAFT))
    craft = []
    for (label, _, _), res in zip(CRAFT, results):
        f = res["frame"]
        craft.append({"name": label, "speed_kms": on_grid(f.get("speed"), grid, minutes),
                      "bt_nt": on_grid(f.get("bt"), grid, minutes), "datasets": [d["id"] for d in res["datasets"]]})
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
