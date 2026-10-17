"""
NOAA OVATION Prime nowcast (helios.core.ovation, /api/aurora/ovation) on a recorded snapshot
(16 October 2026, forecast for 12:52 UTC, Kp 2.3) with HELIOS-L1's Starkov oval for the same time.
"""
import gzip
import json
from pathlib import Path

import numpy as np
import pytest

from helios.core import ovation

SNAP = json.load(gzip.open(Path(__file__).parent / "data" / "ovation_starkov_snapshot.json.gz", "rt", encoding="utf-8"))


def test_grid_and_probability_at_a_place():
    g = ovation.parse(SNAP["ovation"])["grid"]
    assert g.shape == (181, 360) and g.max() > 0
    lon, lat, p = next(c for c in SNAP["ovation"]["coordinates"] if c[2] >= 5)
    assert ovation.probability_at(g, lat, lon) == p
    assert ovation.probability_at(g, lat, lon - 360) == p  # west longitudes
    assert ovation.probability_at(g, 0.0, 0.0) == 0.0  # the grid has 1-3 % at the equator: ignored
    assert ovation.parse({"coordinates": "x"}) is None


def _equatorward_edge(grid: np.ndarray, threshold: float, north: bool = True) -> list:
    """Per longitude 0..359, the lowest |latitude| of the hemisphere where the probability
    reaches `threshold` % (None where it never does)."""
    rows = range(90 + ovation.MIN_ABS_LAT, 181) if north else range(90 - ovation.MIN_ABS_LAT, -1, -1)  # equatorward end outwards
    out = []
    for j in range(360):
        hit = next((r for r in rows if grid[r, j] >= threshold), None)
        out.append(None if hit is None else abs(hit - 90))
    return out


def test_starkov_lies_poleward_of_the_ovation_edge_in_quiet_time():
    """The comparison of the user guide: every 15 deg of longitude in the north, the Starkov
    equatorward boundary minus the lowest latitude where OVATION reaches 5 % (3 %): +2.4 deg
    (+4.1) on average, scatter 4.6 deg (on 12 October 2026, Kp 3.3: +0.3 and +1.5 deg)."""
    g = ovation.parse(SNAP["ovation"])["grid"]
    pts = sorted((p["lon"] % 360, p["lat"]) for p in SNAP["starkov_north_equatorward"])
    lons = np.arange(0, 360, 15)
    starkov = np.interp(lons, [a for a, _ in pts], [b for _, b in pts], period=360)
    for threshold, mean in ((5, 2.44), (3, 4.14)):
        edge = _equatorward_edge(g, threshold, north=True)
        d = np.array([starkov[i] - edge[lo] for i, lo in enumerate(lons) if edge[lo] is not None])
        assert len(d) >= 23 and d.mean() == pytest.approx(mean, abs=0.05) and d.std() == pytest.approx(4.6, abs=0.1)


def test_ovation_endpoint(monkeypatch):
    from fastapi.testclient import TestClient
    from helios.api import server

    async def fake(url, key):
        return SNAP["ovation"] if key == "ovation_aurora" else None

    monkeypatch.setattr(server.downloader, "fetch_json", fake)
    client = TestClient(server.app, base_url="http://127.0.0.1:8765")
    lon, lat, p = next(c for c in SNAP["ovation"]["coordinates"] if c[2] >= 5)
    d = client.get(f"/api/aurora/ovation?lat={lat}&lon={lon}").json()
    assert d["forecast_time"] == "2026-10-16T12:52:00Z" and d["probability_at"] == p
    assert all(c[2] >= 1 for c in d["cells"])

    async def down(url, key):
        return None

    monkeypatch.setattr(server.downloader, "fetch_json", down)
    assert client.get("/api/aurora/ovation").status_code == 503


def test_aurora_map_shows_the_live_nowcast():
    static = Path(__file__).parent.parent / "helios" / "gui" / "static"
    if not static.is_dir():
        import helios
        static = Path(helios.__file__).parent / "gui" / "static"
    aurora = (static / "js" / "aurora.js").read_text(encoding="utf-8")
    assert "if (this.ovationLive()) {" in aurora and "probability of aurora at your place" in aurora
    assert "toggleAuroraLayer('ovation'" in (static / "index.html").read_text(encoding="utf-8")
