"""
Published results reproduced with HELIOS-L1's own tools on the same input data (the table in
docs/USER_GUIDE.md, "Reproductions"). Each test names its source; the published numbers are
copied from it, not fitted here.
"""
import gzip
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from helios.core.coronagraph import CoronagraphAnalyzer as C

LOCAL = "http://127.0.0.1:8765"
DATA = Path(__file__).parent / "data"


# Dumbovic et al. (2021), Front. Astron. Space Sci. 8, 639986, Table 2: basic 1D DBM for the
# CME of 3 April 2010, R0 = 20 R_sun, gamma = 0.2e-7 /km, w = 450 km/s, target 1 AU.
# (lift-off time at R0, v0, published arrival time, published arrival speed)
DBM_TOOLS_TABLE2 = [
    ("2010-04-03T13:24", 920, "2010-04-05 17:39", 620),
    ("2010-04-03T12:19", 920, "2010-04-05 16:34", 620),
    ("2010-04-03T13:29", 920, "2010-04-05 17:44", 620),
    ("2010-04-03T11:47", 812, "2010-04-05 19:43", 597),
]


@pytest.mark.parametrize("t0, v0, toa, soa", DBM_TOOLS_TABLE2)
def test_drag_based_model_reproduces_the_dbm_tools_paper(t0, v0, toa, soa):
    """Within 5 min and 1 km/s (HELIOS is 3-3.5 min later on every row). The fifth column
    (Wood et al. 2017, v0 = 960 km/s) is left out: its published basic-DBM transit, 52.25 h,
    is that of the 920 km/s rows; with 960 km/s HELIOS gives 15:37 and 627 km/s, the values
    the paper lists for that column's 2D flattening-cone run."""
    k = C.calculate_cme_kinematics(20.0 - v0 * 600.0 / C.R_SUN_KM, 20.0, 10.0, t0, 450.0, 0.2e-7)
    got = datetime.strptime(k["predicted_earth_arrival"], "%Y-%m-%d %H:%M:%S UTC")
    assert abs((got - datetime.strptime(toa, "%Y-%m-%d %H:%M")).total_seconds()) <= 300
    assert k["v_arrival_earth_kms"] == pytest.approx(soa, abs=1.0)


def test_flux_rope_fit_reproduces_the_wind_magnetic_cloud_table(monkeypatch, tmp_path):
    """WIND MFI magnetic cloud table (Lepping et al. 1990 model; wind.nasa.gov/mfi/mag_cloud_S1.html,
    version 12/13/11), cloud 6.0 of 18-20 October 1995: phi_A 287, theta_A -8 deg, B0 25.9 nT,
    2R0 0.257 AU, right-handed, CA 12 %. HELIOS on WIND 1-min field and SWE data of the same
    interval, hour averages as the table: every parameter within its 1-sigma uncertainty
    (Lepping et al. 2003)."""
    import math
    from fastapi.testclient import TestClient
    from helios.api import server
    from helios.core.downloader import DataDownloader
    from helios.core.event_analysis import EventDataClient

    served = {"WI_H0_MFI@0": "wi_h0_mfi1m_19951018", "WI_H1_SWE": "wi_h1_swe_19951018"}

    async def fake(url, timeout=120.0):
        ds = parse_qs(urlparse(url).query)["id"][0]
        if ds not in served:
            return None
        return gzip.decompress((DATA / "hapi" / "events" / f"{served[ds]}.csv.gz").read_bytes()).decode()

    dl = DataDownloader()
    dl.fetch_text = fake
    dl.events = EventDataClient(lambda url: dl.fetch_text(url), tmp_path)
    monkeypatch.setattr(server, "downloader", dl)
    r = TestClient(server.app, base_url=LOCAL).get(
        "/api/analysis/fluxrope?mission=WIND&start=1995-10-18T19:48&end=1995-10-20T01:18&average_minutes=60")
    assert r.status_code == 200, r.text
    f = r.json()["result"]
    u = f["uncertainties"]
    assert f["handedness"] == "R"
    assert abs(f["b0_nT"] - 25.9) <= u["b0_nT"]
    assert abs(f["diameter_au"] - 0.257) <= u["diameter_au"]
    assert abs(f["axis_latitude_deg"] - (-8.0)) <= u["axis_latitude_deg"]
    assert abs(f["closest_approach_percent"] - 12.0) <= u["closest_approach_percent"]
    d = math.radians
    cos_sep = (math.cos(d(f["axis_latitude_deg"])) * math.cos(d(-8.0)) * math.cos(d(f["axis_longitude_deg"] - 287.0))
               + math.sin(d(f["axis_latitude_deg"])) * math.sin(d(-8.0)))
    assert math.degrees(math.acos(min(1.0, cos_sep))) <= u["axis_cone_deg"]


def test_icme_means_reproduce_the_richardson_cane_list():
    """Richardson & Cane ICME list (doi:10.7910/DVN/C2MHTH; Cane & Richardson 2003, Richardson
    & Cane 2010), the 2015 ICMEs ending within the year: mean speed (i) and |B| (k) over the
    ICME interval and minimum Dst (m) from the disturbance to the ICME end, recomputed from the
    hourly OMNI read by helios.core.omni_statistics. Measured on 29 ICMEs: speed 5.9 km/s mean
    absolute difference (the list rounds to 10), |B| 0.62 nT, Dst minimum within 1 nT for 86 %."""
    import json
    import numpy as np
    import pandas as pd
    df = pd.read_csv(DATA / "omni_hourly_2015_v_b_dst.csv.gz", comment="#", index_col="time", parse_dates=True)
    import helios
    events = json.loads((Path(helios.__file__).parent / "data" / "icme_richardson_cane.json")
                        .read_text(encoding="utf-8"))["events"]
    dv, db, same_dst = [], [], []
    for e in events:
        if not (e["icme_start"].startswith("2015") and e["icme_end"].startswith("2015")) or e["v_icme_kms"] is None:
            continue
        s, t = pd.Timestamp(e["icme_start"]), pd.Timestamp(e["icme_end"])
        sub = df[(df.index >= s) & (df.index < t)]
        dv.append(sub["speed"].mean() - e["v_icme_kms"])
        db.append(sub["b"].mean() - e["b_mean_nt"])
        dst = df[(df.index >= pd.Timestamp(e["disturbance"]).floor("h")) & (df.index <= t)]["dst"].min()
        same_dst.append(abs(dst - e["dst_min_nt"]) <= 1)
    assert len(dv) >= 25
    assert np.mean(np.abs(dv)) < 10 and abs(np.mean(dv)) < 8
    assert np.mean(np.abs(db)) < 1.0
    assert np.mean(same_dst) >= 0.8


def test_shue_1998_reproduces_the_paper_limit_and_the_january_1997_crossing():
    """Shue et al. (1998, JGR 103, 17691; open copy on C. T. Russell's UCLA page): "the value
    of D_p needs to be at least 7 nPa in order for a geosynchronous satellite to have a
    magnetopause crossing, even when the IMF is extremely southward" - HELIOS: 7.7, 7.5 and
    7.4 nPa for Bz = -18, -20, -30 nT. On 11 January 1997 GMS 4 (near noon) entered the
    magnetosheath at 01:15 UT: at 01 UT (Bz 9.3 nT, D_p 14 nPa) the model magnetopause is
    outside 6.6 R_E, at ~02 UT (Bz ~18 nT, D_p up to 60 nPa) inside it near the subsolar point."""
    import math
    from helios.core.science import SpaceWeatherPhysics as S
    for bz in (-18.0, -20.0, -30.0):  # r0 = A(Bz) p^(-1/6.6) = 6.6 R_E  ->  p = (A / 6.6)^6.6
        assert 7.0 <= (S.shue1998_magnetopause(1.0, bz)[0] / 6.6) ** 6.6 <= 8.0

    def r(p, bz, theta_deg):
        r0, a = S.shue1998_magnetopause(p, bz)
        return r0 * (2.0 / (1.0 + math.cos(math.radians(theta_deg)))) ** a

    assert all(r(14.0, 9.3, th) > 6.6 for th in (0, 20, 30))
    assert all(r(60.0, 18.0, th) < 6.6 for th in (0, 20, 30))
