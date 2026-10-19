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


# Recorded payloads (tests/data): NOAA NCEI DSCOVR f1m file of 19 Jan 2026 with its S3 listing, and the PSP
# SPAN-I L3 moments excerpt of the same day (CDAWeb HAPI). Every other request answers "no data".
_DATA = __import__("pathlib").Path(__file__).parent / "data"
_NCEI_F1M = _DATA / "ncei" / "oe_f1m_dscovr_s20260119000000_e20260119235959_p20260120020420_pub.nc.gz"


def _recorded_archive(cache_dir):
    import gzip
    from urllib.parse import parse_qs, urlparse
    from helios.core.archive import ArchiveClient
    from helios.core.ncei import NCEI_BUCKET
    no_data = (_DATA / "hapi" / "wi_h1_swe_nodata.csv").read_text()
    psp = gzip.decompress((_DATA / "hapi" / "events" / "psp_spi_20201201_20260119.csv.gz").read_bytes()).decode()

    async def text(url):
        q = parse_qs(urlparse(url).query)
        if url.startswith(NCEI_BUCKET):
            day = q["prefix"][0][-8:]
            return (_DATA / "ncei" / "listing_20260119.xml").read_text() if day == "20260119" else "<ListBucketResult></ListBucketResult>"
        if q["id"][0] == "PSP_SWP_SPI_SF00_L3_MOM" and q["time.min"][0][:10] == "2026-01-19":
            return psp
        return no_data

    async def data(url):
        return _NCEI_F1M.read_bytes() if url.endswith(_NCEI_F1M.name) else None
    return ArchiveClient(text, cache_dir, data)


def test_replay_measurements_from_recorded_archive_days(tmp_path):
    """measurements(): every craft on one 5-min grid for a day, block means of the archive's 1-min frame,
    the datasets named; craft without data all None."""
    import asyncio
    from datetime import datetime, timezone
    archive = _recorded_archive(tmp_path)
    t0, t1 = datetime(2026, 1, 19, tzinfo=timezone.utc), datetime(2026, 1, 20, tzinfo=timezone.utc)
    out = asyncio.run(replay.measurements(archive, t0, t1))
    assert out["step_minutes"] == 5 and len(out["times"]) == 288
    assert out["times"][0] == "2026-01-19T00:00:00Z" and out["times"][-1] == "2026-01-19T23:55:00Z"
    craft = {c["name"]: c for c in out["craft"]}
    assert list(craft) == [label for label, _, _ in replay.CRAFT]
    assert craft["DSCOVR"]["datasets"] == ["NCEI_DSCOVR_F1M"] and craft["Parker Solar Probe"]["datasets"] == ["PSP_SWP_SPI_SF00_L3_MOM"]
    for name in ("WIND", "ACE", "SOHO", "STEREO-A", "Solar Orbiter"):
        assert craft[name]["datasets"] == [] and set(craft[name]["speed_kms"]) == {None} and set(craft[name]["bt_nt"]) == {None}
    # The 18:55 bin is the mean of the kept DSCOVR minutes 18:55-18:59 (the shock minute 18:58 at 539.5 km/s).
    frame = asyncio.run(archive.fetch_mission("DSCOVR", t0, t1))["frame"]
    minutes = frame.loc["2026-01-19 18:55":"2026-01-19 18:59", "speed"].dropna()
    assert len(minutes) >= 1 and 539.5 in list(minutes.round(1))
    i = out["times"].index("2026-01-19T18:55:00Z")
    assert craft["DSCOVR"]["speed_kms"][i] == pytest.approx(round(minutes.mean(), 1))
    # PSP: only bins holding valid SPAN-I moments have a speed, and none is 0 (no-count samples are missing).
    psp = [v for v in craft["Parker Solar Probe"]["speed_kms"] if v is not None]
    assert psp and min(psp) > 50


def test_replay_positions_of_18_20_january_2026_from_the_recorded_ephemeris():
    """positions(): HEE (AU) from the recorded JPL Horizons vectors at 25 epochs. L1 craft ~0.01 AU sunward
    of Earth; at the 19 Jan 12 UT epoch (Solar Orbiter's shock) Solar Orbiter 0.74 AU from the Sun, 8 deg
    ahead of Earth (west of the Sun-Earth line), STEREO-A 51 deg ahead, PSP on the far side."""
    import math
    from datetime import datetime, timezone
    from helios.core.spice_engine import get_spice_engine
    p = replay.positions(get_spice_engine(), datetime(2026, 1, 18, tzinfo=timezone.utc), datetime(2026, 1, 21, tzinfo=timezone.utc))
    assert len(p["times"]) == replay.POSITION_EPOCHS + 1 and p["times"][12] == "2026-01-19T12:00:00Z"
    assert all(0.983 < d < 0.985 for d in p["earth_au"])
    lon = {k: math.degrees(math.atan2(v[12][1], v[12][0])) for k, v in p["craft"].items()}
    r = {k: math.hypot(*v[12]) for k, v in p["craft"].items()}
    for l1 in ("WIND", "ACE", "DSCOVR", "SOHO"):
        assert p["earth_au"][12] - p["craft"][l1][12][0] == pytest.approx(0.01, abs=0.002) and abs(lon[l1]) < 0.3
    assert r["Solar Orbiter"] == pytest.approx(0.74, abs=0.01) and lon["Solar Orbiter"] == pytest.approx(8.0, abs=0.5)
    assert lon["STEREO-A"] == pytest.approx(51.2, abs=0.5) and abs(lon["Parker Solar Probe"]) > 150


def test_replay_route_end_to_end_offline(tmp_path, monkeypatch):
    """/api/replay with the recorded archive and ephemeris: grid, positions and first speed jump per craft."""
    from fastapi.testclient import TestClient
    from helios.api import server
    monkeypatch.setattr(server.downloader, "archive", _recorded_archive(tmp_path))
    r = TestClient(server.app, base_url="http://127.0.0.1:8765").get("/api/replay?start=2026-01-19T12:00&end=2026-01-20T00:00")
    assert r.status_code == 200
    body = r.json()
    assert body["step_minutes"] == 2 and len(body["times"]) == 360 and "HEE" in body["frame"]
    assert set(body["positions"]["craft"]) == {label for label, _, _ in replay.CRAFT}
    assert all("first_speed_jump" in c for c in body["craft"])
    assert {c["name"]: c["first_speed_jump"] for c in body["craft"]}["WIND"] is None
