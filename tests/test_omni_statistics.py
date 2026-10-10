"""Hourly OMNI statistics, filters and the Xu & Borovsky (2015) solar wind types."""
import gzip
import math
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from helios.core import omni_statistics as om
from helios.core.archive import parse_hapi_csv

DATA = Path(__file__).parent / "data" / "hapi" / "events"
LOCAL = "http://127.0.0.1:8765"


def _fixture_text():
    with gzip.open(DATA / "omni2_hourly_20031025_1105.csv.gz", "rt", encoding="utf-8") as f:
        return f.read()


def _frame():
    return om.decode(parse_hapi_csv(_fixture_text()))


def test_daily_means_match_nasa_omni_daily_averages():
    """NASA's omni_01_av.dat (daily means of the hourly values) for 25 Oct - 5 Nov 2003."""
    nasa = {  # day of year: |B|, Bz GSM, N, V, Dst
        298: (15.4, 7.5, 8.2, 540, -26), 299: (11.9, 2.1, 1.9, 459, -17), 300: (9.6, -1.8, 1.3, 467, -39),
        301: (12.6, 0.7, 3.2, 638, -15), 302: (28.0, -3.0, None, None, -128), 303: (16.4, -3.0, None, None, -221),
        304: (15.8, 8.1, 4.3, 1003, -117), 305: (5.1, -1.3, 1.8, 679, -46), 306: (5.6, -1.7, 2.5, 541, -27),
        307: (5.8, 0.9, 2.9, 530, -14), 308: (9.1, 3.5, 5.8, 641, -33), 309: (5.5, 2.1, 3.7, 552, -25),
    }
    df = _frame()
    assert df.index[0] == pd.Timestamp("2003-10-25 00:00", tz="UTC")  # start of the hourly average
    daily = df.groupby(df.index.dayofyear).mean()
    for doy, vals in nasa.items():
        for col, v, tol in zip(("b", "bz_gsm", "density", "speed", "dst"), vals, (0.05, 0.05, 0.05, 0.5, 0.5)):
            if v is None:  # plasma gap at the Halloween storm in the NASA file as well
                assert math.isnan(daily.loc[doy, col])
            else:
                assert abs(daily.loc[doy, col] - v) <= tol + 1e-9, (doy, col)
    assert df["kp"].max() == 9.0 and df["dst"].min() == -383.0


def test_xb15_planes_against_published_inequalities():
    """Point-normal planes of the implementation vs the inequality coefficients of Xu & Borovsky (2015)."""
    rng = np.random.default_rng(4)
    n = 20000
    v = rng.uniform(250, 900, n)
    dens = 10 ** rng.uniform(-0.5, 1.6, n)
    t = 10 ** rng.uniform(3.5, 6.0, n)
    b = 10 ** rng.uniform(0.2, 1.5, n)
    types = om.xb15_type(v, dens, t, b)
    t_ev = t / 11604.518
    ls = np.log10(t_ev / dens ** (2 / 3))
    la = np.log10(21.81 * b / np.sqrt(dens))
    lr = np.log10((v / 258) ** 3.113 / t_ev)
    ej = la > 0.277 * ls + 0.055 * lr + 1.83
    ch = ls > -0.525 * lr - 0.676 * la + 1.74
    sr = ls < -0.125 * lr - 0.658 * la + 1.04
    expected = np.where(ej, 1, np.where(ch, 2, np.where(sr, 3, 4)))
    # The published coefficients are rounded to 2-3 digits: points within that of a plane may differ.
    assert np.mean(types == expected) > 0.995
    assert set(np.unique(types)) == {1, 2, 3, 4}
    assert om.xb15_type([400], [np.nan], [1e5], [5])[0] == 0
    # Typical cases: cold, strong-field cloud plasma; hot fast wind; dense, cold slow wind.
    assert om.xb15_type([450], [8], [2e4], [20])[0] == 1
    assert om.xb15_type([700], [2.5], [2.5e5], [5])[0] == 2
    assert om.xb15_type([330], [15], [3e4], [5])[0] == 3


def test_filters_and_run_lengths():
    idx = pd.date_range("2020-01-01", periods=12, freq="h", tz="UTC")
    bz = [1, -1, -2, -3, 1, -1, -1, 2, -4, -4, -4, -4]
    df = pd.DataFrame({"bz_gsm": bz, "speed": [400 + 20 * i for i in range(12)], "imf_points": [60] * 11 + [3],
                       "plasma_points": [30] * 12}, index=idx)
    mask, log = om.apply_filters(df, bz_south_min_hours=3)
    assert mask.tolist() == [False, True, True, True, False, False, False, False, True, True, True, True]
    mask, log = om.apply_filters(df, conditions=om.parse_conditions("speed>=500; speed<600"), min_imf_points=10)
    assert mask.sum() == 5 and [entry["hours_remaining"] for entry in log] == [12, 7, 5, 5]
    # A gap breaks a run: without 02:00 the southward hours 01:00 and 03:00 are no longer one run.
    mask, _ = om.apply_filters(df.drop(idx[2]), bz_south_min_hours=2)
    assert mask.tolist() == [False, False, False, False, True, True, False, True, True, True, True]
    with pytest.raises(ValueError):
        om.parse_conditions("speed >> 3")
    with pytest.raises(ValueError):
        om.parse_conditions("warp>1")


def test_mean_interval_with_gaps_covers_true_mean():
    rng = np.random.default_rng(11)
    hits, trials = 0, 300
    for _ in range(trials):
        n, phi = 1500, 0.9
        e = rng.normal(size=n)
        x = np.empty(n)
        x[0] = e[0] / math.sqrt(1 - phi ** 2)
        for i in range(1, n):
            x[i] = phi * x[i - 1] + e[i]
        idx = pd.date_range("2000-01-01", periods=n, freq="h", tz="UTC")
        keep = rng.random(n) > 0.2  # 20 % of the hours missing at random
        st = om.mean_with_interval(x[keep] + 5.0, idx[keep])
        hits += st["ci95"][0] <= 5.0 <= st["ci95"][1]
    assert 0.90 <= hits / trials <= 0.99


def test_analyses_on_fixture():
    df = _frame()
    r = om.run_analysis(df, "distribution", "speed", None, {}, bins=20)["result"]
    assert r["n"] == int(df["speed"].notna().sum()) and sum(r["counts"]) + r["outside_range"] == r["n"]
    assert r["percentiles"]["median"] == pytest.approx(float(df["speed"].median()))
    out = om.run_analysis(df, "conditional", "vbs", "dst", {}, bins=6, min_count=5)
    assert len(out["result"]["x_center"]) == 6
    out = om.run_analysis(df, "correlation", "speed", "temperature", {})
    both = df[["speed", "temperature"]].dropna()
    assert out["result"]["r"] == pytest.approx(both.speed.corr(both.temperature))
    lo, hi = out["result"]["ci95"]
    assert lo < out["result"]["r"] < hi
    out = om.run_analysis(df, "joint", "speed", "density", {}, bins=8)
    assert np.sum(out["result"]["counts"]) + out["result"]["outside_range"] == len(df[["speed", "density"]].dropna())
    with pytest.raises(ValueError):
        om.run_analysis(df, "joint", "speed", None, {})
    with pytest.raises(ValueError):
        om.run_analysis(df, "distribution", "speed", None, {"conditions": [("speed", ">", 5000.0)]})


def test_statistics_api_records_filters(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from helios.api import server
    from helios.core.downloader import DataDownloader

    text = _fixture_text()

    async def fake(url, timeout=120.0):
        return text if "time.min=2003-01-01" in url else None

    dl = DataDownloader()
    dl.fetch_text = fake
    dl.omni_hourly = om.OmniHourlyClient(lambda url: dl.fetch_text(url), tmp_path)
    monkeypatch.setattr(server, "downloader", dl)
    client = TestClient(server.app, base_url=LOCAL)
    q = ("start_year=2002&end_year=2003&analysis=distribution&x=dst&where=speed>500&bz_south_hours=2"
         "&sw_type=ejecta,sector_reversal")
    r = client.get(f"/api/statistics/omni?{q}")
    assert r.status_code == 200, r.text
    body = r.json()
    names = [f["filter"] for f in body["provenance"]["filters"]][1:]
    assert names == ["speed > 500", "IMF Bz GSM < 0 for at least 2 consecutive hours",
                     "Xu & Borovsky (2015) solar wind type in ejecta, sector_reversal"]
    assert body["provenance"]["years_without_data"] == [2002]
    csv_text = client.get(f"/api/statistics/omni?{q}&format=csv").text
    assert "# filter: speed > 500 ->" in csv_text and "bin_low,bin_high,count,density" in csv_text
    assert client.get("/api/statistics/omni?analysis=distribution&x=speed&where=speed%3E%3E1").status_code == 422
    assert client.get("/api/statistics/omni?analysis=distribution&x=speed&sw_type=plasma").status_code == 422
    assert client.get("/api/statistics/omni?start_year=1963&end_year=2040").status_code == 422
    quantities = client.get("/api/statistics/omni/quantities").json()
    assert "sw_type" in quantities["quantities"] and "ejecta" in quantities["solar_wind_types"]


def _dst_fixture():
    rows = []
    with gzip.open(Path(__file__).parent / "data" / "omni_dst_le_minus100_1996_2006.csv.gz", "rt") as f:
        for line in f:
            if not line.startswith("#"):
                t, v = line.strip().split(",")
                rows.append((pd.Timestamp(t, tz="UTC"), float(v)))
    return pd.DataFrame({"dst": [v for _, v in rows]}, index=pd.DatetimeIndex([t for t, _ in rows]))


def test_storm_counts_match_echer_2008():
    """Hours with Dst <= -100 nT in 1996-2006 (OMNI); hours absent from the file are above -100 nT."""
    df = _dst_fixture()
    intense = om.find_storms(df, -100.0, 6.0)["storms"]
    assert len(intense) == 90  # Echer et al. (2008, JGR 113, A05221): 90 intense storms
    supers = om.find_storms(df, -250.0, 6.0)["storms"]
    assert [s["minimum_time"][:10] for s in supers] == [
        "2000-04-07", "2000-07-16", "2001-03-31", "2001-04-11", "2001-11-06", "2003-10-30", "2003-10-30",
        "2003-11-20", "2004-11-08", "2004-11-10"]
    # Echer et al. (2008, GRL 35, L06S03): peak Dst of the superstorms from -263 to -422 nT.
    assert min(s["minimum_dst_nt"] for s in supers) == -422 and max(s["minimum_dst_nt"] for s in supers) == -263
    # Without joining, the two-step storm of 31 March 2001 counts twice.
    assert len(om.find_storms(df, -250.0, 0.0)["storms"]) == 11
    capped = om.find_storms(df, -100.0, 6.0, floor_nt=-250.0)
    # 82, not 90 - 10: at -100 nT the two Halloween minima (and those of 8 and 10 Nov 2004) lie in one storm.
    assert len(capped["storms"]) == 82 and capped["log"][-1]["storms_remaining"] == 82


def test_storm_driver_and_superposed_epoch_selection(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from helios.api import server
    from helios.core.downloader import DataDownloader

    df = _frame()
    res = om.find_storms(df, -200.0)
    assert [(s["minimum_time"], s["minimum_dst_nt"]) for s in res["storms"]] == [
        ("2003-10-30 00:00", -353.0), ("2003-10-30 22:00", -383.0)]
    assert res["storms"][1]["driver_bz_gsm_nt"] < -10  # strongly southward IMF before the minimum

    text = _fixture_text()

    async def fake(url, timeout=120.0):
        return text if "OMNI2_H0_MRG1HR" in url and "time.min=2003-01-01" in url else None

    dl = DataDownloader()
    dl.fetch_text = fake
    dl.omni_hourly = om.OmniHourlyClient(lambda url: dl.fetch_text(url), tmp_path)
    dl.archive.fetch_text = fake
    monkeypatch.setattr(server, "downloader", dl)
    client = TestClient(server.app, base_url=LOCAL)
    body = client.get("/api/statistics/storms?start_year=2003&end_year=2003&threshold_nt=-200").json()
    assert len(body["result"]["storms"]) == 2 and body["provenance"]["dataset"] == "OMNI2_H0_MRG1HR"
    # The superposed epoch analysis takes the same selection and records it (the 1-min data are not
    # served here, so it answers 404 after selecting the two onsets).
    r = client.get("/api/analysis/superposed?storm_threshold_nt=-200&storm_start_year=2003&storm_end_year=2003"
                   "&parameters=sym_h&before_hours=6&after_hours=12")
    assert r.status_code == 404 and "OMNI has no data" in r.text
    r = client.get("/api/analysis/superposed?storm_threshold_nt=-500&storm_start_year=2003&storm_end_year=2003")
    assert r.status_code == 422 and "No storm" in r.text
    assert client.get("/api/statistics/storms?start_year=2003&end_year=2003&driver=wind").status_code == 422
    assert client.get("/api/statistics/storms?start_year=2003&end_year=2003&threshold_nt=-100&floor_nt=-50").status_code == 422
    assert client.get("/api/analysis/superposed?parameters=sym_h").status_code == 422  # neither onsets nor storms


def test_storm_window_after_ji_2012():
    idx = pd.date_range("2001-01-01", periods=60, freq="h", tz="UTC")
    dst = pd.Series([5.0] * 10 + [12.0] + [-20.0 * k for k in range(1, 11)] + [-200 + 10 * k for k in range(39)], index=idx)
    t_min = dst.idxmin()
    a, b = om.storm_window(dst, t_min)
    assert a == idx[10]  # highest Dst in the 24 h before the minimum (the commencement)
    assert dst.loc[b] > -50 and dst.loc[:b].iloc[-2] <= -50  # first hour recovered above -50 nT


def test_dst_model_skill_over_storms(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from helios.api import server
    from helios.core.downloader import DataDownloader

    df = _frame()
    storms = om.find_storms(df, -150.0)["storms"]
    res = om.dst_model_skill(df, storms)
    for key in ("obrien", "burton"):
        m = res["models"][key]
        assert m["n_storms"] == len(storms) >= 2
        per = [s[key] for s in res["storms"] if s[key]]
        assert m["rmse_nt"]["mean"] == pytest.approx(np.mean([p["rmse_nt"] for p in per]))
        lo, hi = m["r"]["ci95"]
        assert lo <= m["r"]["mean"] <= hi

    text = _fixture_text()

    async def fake(url, timeout=120.0):
        return text if "time.min=2003-01-01" in url else None

    dl = DataDownloader()
    dl.fetch_text = fake
    dl.omni_hourly = om.OmniHourlyClient(lambda url: dl.fetch_text(url), tmp_path)
    monkeypatch.setattr(server, "downloader", dl)
    client = TestClient(server.app, base_url=LOCAL)
    r = client.get("/api/statistics/dst_models?start_year=2003&end_year=2003&threshold_nt=-150")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"]["models"]["obrien"]["n_storms"] == len(storms)
    assert body["provenance"]["filters"][0]["filter"].startswith("storms: Dst <= -150")
    assert client.get("/api/statistics/dst_models?start_year=1970&end_year=2010").status_code == 422


def test_conditional_average_keeps_values_on_the_top_edge():
    """Discrete values (Kp) at the upper limit fell outside every bin; np.histogram counts them."""
    from helios.core.omni_statistics import conditional_average
    t = pd.date_range("2024-01-01", periods=400, freq="h", tz="UTC")
    x = pd.Series(np.tile([1.0, 2.0, 3.0, 4.0], 100), index=t)
    res = conditional_average(x, x * 2, bins=3, lo=1.0, hi=4.0, min_count=1)
    assert sum(res["n"]) == 400 and res["n"][-1] == 200
    res = conditional_average(x, x, bins=3, log_x=True, lo=1.0, hi=4.0, min_count=1)
    assert sum(res["n"]) == 400
