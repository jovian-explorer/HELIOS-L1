"""
NOAA SWPC OVATION Prime aurora nowcast (services.swpc.noaa.gov/json/ovation_aurora_latest.json):
the probability (%) of visible aurora on a 1-degree geographic grid for the "Forecast Time",
about 30-90 minutes after the "Observation Time" of the L1 solar wind that drives it
(Newell et al. 2009 model, NOAA's operational version). Used for the live aurora map and
"your place"; the Starkov (1994) oval stays for past times and offline use.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np

SOURCE = "NOAA SWPC OVATION Prime aurora nowcast (services.swpc.noaa.gov/json/ovation_aurora_latest.json)"
# NOAA's grid carries 1-3 % values within ~10 deg of the geographic equator (16 October 2026),
# far from any aurora (the oval values start beyond 40 deg); cells equatorward of this are ignored.
MIN_ABS_LAT = 20


def parse(product: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Grid (181 latitudes -90..90 x 360 longitudes 0..359 E, %) and times, or None if malformed."""
    try:
        cells = np.asarray(product["coordinates"], dtype=float)
        grid = np.zeros((181, 360))
        lon = np.mod(np.rint(cells[:, 0]).astype(int), 360)
        lat = np.clip(np.rint(cells[:, 1]).astype(int), -90, 90)
        grid[lat + 90, lon] = cells[:, 2]
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    return {"grid": grid, "observation_time": product.get("Observation Time"),
            "forecast_time": product.get("Forecast Time")}


def probability_at(grid: np.ndarray, lat: float, lon: float) -> float:
    """Probability (%) in the grid cell nearest to (lat, lon); longitude east, any range."""
    if abs(lat) < MIN_ABS_LAT:
        return 0.0
    return float(grid[int(np.clip(round(lat), -90, 90)) + 90, int(round(lon)) % 360])


def equatorward_edge(grid: np.ndarray, threshold: float, north: bool = True) -> List[Optional[int]]:
    """Per longitude 0..359, the lowest |latitude| of the hemisphere where the probability
    reaches `threshold` % (None where it never does)."""
    rows = range(90 + MIN_ABS_LAT, 181) if north else range(90 - MIN_ABS_LAT, -1, -1)  # equatorward end outwards
    out: List[Optional[int]] = []
    for j in range(360):
        hit = next((r for r in rows if grid[r, j] >= threshold), None)
        out.append(None if hit is None else abs(hit - 90))
    return out


def cells(grid: np.ndarray, minimum: float = 1.0) -> List[List[int]]:
    """[lon, lat, %] of the cells at or above `minimum` (the map layer; zeros are left out)."""
    lat_i, lon_i = np.nonzero(grid >= minimum)
    return [[int(lo), int(la) - 90, int(round(grid[la, lo]))] for la, lo in zip(lat_i, lon_i)
            if abs(int(la) - 90) >= MIN_ABS_LAT]
