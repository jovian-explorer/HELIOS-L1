"""Event replay (helios/core/replay.py, /api/replay)."""
import pandas as pd
import pytest

from helios.core import replay
from helios.core.constants import AU_KM


def test_first_speed_jump_is_a_lasting_rise_on_steady_data():
    t = [f"T{i}" for i in range(10)]
    # One missing step after the rise (WIND at the 19 Jan 2026 shock) still counts.
    assert replay.first_jump(t, [400, 405, 398, 402, 900, None, 1000, 1010, 990, 1000]) == "T4"
    # A one-step spike, a noisy series (PSP SPAN-I) and a rise after a gap (ACE) give none.
    assert replay.first_jump(t, [400, 405, 398, 402, 900, 410, 400, 405, 398, 402]) is None
    assert replay.first_jump(t, [65, 380, 150, 90, 600, 700, 650, 640, 630, 620]) is None
    assert replay.first_jump(t, [400, 405, None, 402, 900, 950, 1000, 1010, 990, 1000]) is None


def test_hee_position_reverses_gse_x_and_y_from_the_sun():
    class Engine:
        def get_spacecraft_state(self, sc, iso):  # 0.01 AU sunward of Earth, 0.002 AU towards dusk (+Y GSE)
            return {"gse_coordinates": {"x_km": 0.01 * AU_KM, "y_km": 0.002 * AU_KM, "z_km": 0.0}}
    assert replay.hee_au(Engine(), "WIND", "2026-01-18T00:00:00", 0.984) == pytest.approx([0.974, -0.002, 0.0])


def test_grid_means_and_interval_limit():
    grid = pd.date_range("2026-01-18", periods=3, freq="10min", tz="UTC")
    s = pd.Series([1.0, 3.0, 10.0], index=grid[:2].append(pd.DatetimeIndex([grid[1] + pd.Timedelta(minutes=5)])))
    assert replay.on_grid(s, grid, 10) == [1.0, 6.5, None]
    from fastapi.testclient import TestClient
    from helios.api import server
    r = TestClient(server.app, base_url="http://127.0.0.1:8765").get("/api/replay?start=2026-01-01T00:00&end=2026-01-15T00:01")
    assert r.status_code == 422 and "14 days" in r.json()["detail"]


def test_solar_orbiter_archive_source_gives_speed_and_kelvin():
    """Solar Orbiter and PSP are archive missions for the replay (1-min means, cached by day): |V| and T in K."""
    from helios.core.archive import ARCHIVE_SOURCES, EV_TO_K
    mag, plasma = (g[0]["reduce"] for g in ARCHIVE_SOURCES["SOLO"]["groups"])
    idx = pd.date_range("2026-01-19", periods=1, tz="UTC")
    p = plasma(pd.DataFrame({"N": [5.0], "V_RTN_0": [300.0], "V_RTN_1": [400.0], "V_RTN_2": [0.0], "T": [10.0]}, index=idx))
    assert p["speed"].iloc[0] == 500.0 and p["temperature"].iloc[0] == pytest.approx(10 * EV_TO_K)
    assert mag(pd.DataFrame({"B_RTN_0": [3.0], "B_RTN_1": [0.0], "B_RTN_2": [-4.0]}, index=idx))["bt"].iloc[0] == 5.0
    assert replay.step_minutes(pd.Timestamp("2026-01-18"), pd.Timestamp("2026-01-21")) == 10
