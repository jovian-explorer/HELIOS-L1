"""
The geomagnetic indices Kp (three-hourly) and Hp30 (half-hourly, not capped at 9) of GFZ
Potsdam, read from its web service by calendar year and cached.

Source: GFZ German Research Centre for Geosciences, https://kp.gfz.de (licence CC BY 4.0).
Kp: Matzka et al. (2021), Space Weather 19, e2020SW002641, doi:10.1029/2020SW002641; data
doi:10.5880/Kp.0001. Hpo (Hp30, Hp60): Yamazaki et al. (2022), Geophys. Res. Lett. 49,
e2022GL098860, doi:10.1029/2022GL098860.

Each value describes the activity in its interval (labelled by the interval start); for the
superposed epoch analysis it is held over the interval minute by minute.
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

API = "https://kp.gfz.de/app/json/?start={year}-01-01T00:00:00Z&end={year}-12-31T23:59:59Z&index={index}"
INDICES = {"kp": ("Kp", 180), "hp30": ("Hp30", 30)}  # HELIOS name: (GFZ name, interval in minutes)
SOURCE = {"name": "Kp and Hp30, GFZ German Research Centre for Geosciences", "url": "https://kp.gfz.de",
          "licence": "CC BY 4.0",
          "citation": "Matzka et al. (2021), Space Weather 19, e2020SW002641, doi:10.5880/Kp.0001 (Kp); "
                      "Yamazaki et al. (2022), Geophys. Res. Lett. 49, e2022GL098860 (Hp30)"}
RECENT_TTL_S = 86400


async def year_series(fetch_text: Callable, cache_dir, key: str, year: int) -> Optional[pd.Series]:
    """One calendar year of an index (values by interval start, UTC), or None when unreadable."""
    name, _ = INDICES[key]
    path = os.path.join(str(cache_dir), "gfz_indices", f"{name}_{year}.json")
    # The indices are definitive within months: a copy downloaded half a year after the year
    # ended is kept for good (a copy taken during the year used to be kept for good too).
    old = os.path.exists(path) and os.path.getmtime(path) > datetime(year + 1, 7, 1, tzinfo=timezone.utc).timestamp()
    body = None
    if os.path.exists(path) and (old or time.time() - os.path.getmtime(path) < RECENT_TTL_S):
        with open(path, encoding="utf-8") as f:
            body = f.read()
    else:
        fresh = await fetch_text(API.format(year=year, index=name))
        try:
            if fresh is not None and name in json.loads(fresh):
                os.makedirs(os.path.dirname(path), exist_ok=True)
                with open(path + ".tmp", "w", encoding="utf-8") as f:
                    f.write(fresh)
                os.replace(path + ".tmp", path)
                body = fresh
        except ValueError:
            pass
        if body is None and os.path.exists(path):  # offline: the last copy
            with open(path, encoding="utf-8") as f:
                body = f.read()
    if body is None:
        return None
    d = json.loads(body)
    if not d.get("datetime"):
        return None
    return pd.Series([float(v) for v in d[name]], index=pd.to_datetime(d["datetime"], utc=True), name=key)


def step_records(series: pd.Series, key: str, start: datetime, end: datetime) -> List[Dict[str, Any]]:
    """Minute records {"time_tag", key} over [start, end), each minute carrying its interval's value."""
    _, minutes = INDICES[key]
    t0 = pd.Timestamp(start).floor("min")
    grid = pd.date_range(t0, pd.Timestamp(end), freq="min", inclusive="left")
    held = series.reindex(series.index.union(grid)).ffill(limit=minutes - 1).reindex(grid)
    return [{"time_tag": t.strftime("%Y-%m-%d %H:%M:%S"), key: float(v)} for t, v in zip(grid, held.to_numpy()) if v == v]


async def records(fetch_text: Callable, cache_dir, key: str, start: datetime, end: datetime):
    """(minute records of `key` over [start, end), years that could not be read)."""
    years = range(start.year, (end - timedelta(microseconds=1)).year + 1)
    parts, missing = [], []
    for y in years:
        s = await year_series(fetch_text, cache_dir, key, y)
        (parts.append(s) if s is not None else missing.append(y))
    if not parts:
        return [], missing
    return step_records(pd.concat(parts).sort_index(), key, start, end), missing
