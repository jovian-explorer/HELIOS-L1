"""
Sudden commencements in SYM-H (helios.core.sudden_commencement) and the comparison with the
lists of the International Service on Rapid Magnetic Variations (Observatori de l'Ebre).

Real data: OMNI_HRO_1MIN Pressure and SYM_H from CDAWeb HAPI for 16-18 March 2015 and
10 May 2024 12-24 UT. The Ebre list lines below are quoted from
https://obsebre.es/php/geomagnetisme/vrapides/ssc_2015_d.txt, ssc_2024_p.txt, ssc_2003_d.txt
and ssc_2005_d.txt (Lists of the International Service on Rapid Magnetic Variations,
Observatori de l'Ebre, for ISGI; CC BY-NC 4.0).
"""
import asyncio
import gzip
import os
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import numpy as np
import pandas as pd
import pytest

from helios.core import sudden_commencement as sc

LOCAL = "http://127.0.0.1:8765"
EVENTS = Path(__file__).parent / "data" / "hapi" / "events"

EBRE_2015 = """SC 2015
CONTRIBUTING OBSERVATORIES
SOD NUR LER ESK WNG NGK VAL HAD DOU BDV HRB NAG GCK MMB EBR SPT KAK KNY GUI HYB GNG CNB
YYYY MM dd hh  min  Rise-time           Amplitude (nT)       Qualification   Observatories    Type
2015 03 11 05 12.0  4  5  5  5  5   6.3   9.2   8.8  20.4  13.3  1 1 1 2 2  HON SJG MBO ABG KNY\t SSC
2015 03 17 04 45.0  3  3  3  2  2  33.7  33.1  36.2  47.1  49.3  3 3 3 3 3  HON SJG MBO HYB KNY\t SSC
2015 03 25 13 20.0  5  5  5  5  5  17.4  11.7  35.4  23.0  26.0  2 1 2 2 2  HON SJG MBO ABG KNY\t SSC
"""
EBRE_2024 = """SC 2024
CONTRIBUTING OBSERVATORIES
LER ESK HAD WNG NGK VAL DOU BDV NAG GCK MMB EBR KAK KNY GUI GNG CNB LIV HYB CLF TAM PHU MBO KOU
YYYY MM dd hh min   Rise-time         Amplitude (nT)         Qualification Observatories     Type
2024 05 02 14 07    4 5 5 5 5  16.7   9.3  11.3  17.1  27.6  3 2 3 3 3  HON SJG GUI ABG KNY  SSC
2024 05 10 17 05    2 2 3 3 3  40.4  49.5  71.3  95.2  89.6  3 3 3 3 3  HON SJG GUI ABG KNY  SSC
"""
EBRE_2003 = """<pre>
SC 2003
YYYY MM dd hh  min  Duration  Amplitude Qualification    Observatories
                     (min)      (nT)
2003 10 26 19  8.0    2.6        8.9      1 1 2 2 1   ABG HON KNY MBO SJG
2003 10 29  6 10.0    3.4       68.4      3 3 3 3 3   ABG HON KNY MBO SJG
"""
EBRE_2005 = """<pre>
SC 2005
2005 01 17 07 48.4  4 5 4 4 5  12.4 12.0 16.6 11.8 06.6   2 1 2 1 0   ABG HON KNY MBO SJG
"""


def _text(name):
    with gzip.open(EVENTS / f"{name}.csv.gz", "rt", encoding="utf-8") as f:
        return f.read()


def _minutes(start, values):
    return pd.Series(np.asarray(values, dtype=float), index=pd.date_range(start, periods=len(values), freq="min", tz="UTC"))


def test_detection_rules_on_synthetic_steps():
    v = np.full(8 * 60, -5.0)
    v[:100:7] = -4.0                                    # isolated 1-nT wiggles: median |dSYM-H| stays 0
    v[121:] += np.r_[5, 20, 30 * np.ones(len(v) - 123)]  # A: persistent 30-nT step from 02:00
    v[241:244] += [8, 20, 9]                            # B: 20-nT spike at 04:00, back in 3 minutes
    v[361:] += np.r_[10, 25 * np.ones(len(v) - 362)]    # C: 25-nT step at 06:00
    symh = _minutes("2020-01-01", v)
    p = np.full(len(v), 2.0)
    p[120:] = 6.0                                       # pressure x3 with A,
    p[240:] = 18.0                                      # x3 with B, unchanged with C
    pressure = _minutes("2020-01-01", p)
    ev = sc.detect(symh, pressure)
    assert list(ev["time"]) == [pd.Timestamp("2020-01-01 02:00", tz="UTC")]  # B fails persistence, C the pressure test
    a = ev.iloc[0]
    assert (a.amplitude_nt, a.rise_minutes, a.max_step_nt, a.quiet_nt) == (30, 3, 15, 0)
    assert a.pressure_ratio == pytest.approx(3.0) and a.pressure_jump and a.persistence > 0.9
    no_p = sc.detect(symh)                              # without pressure, A and C are kept, unconfirmed
    assert [t.strftime("%H:%M") for t in no_p["time"]] == ["02:00", "06:00"]
    assert no_p["pressure_jump"].isna().all()
    # Disturbed record (median |dSYM-H| = 2 nT): a 12-nT step is not told from the variations,
    # a 60-nT step with a 45-nT minute (>= 20 x 2) is.
    noisy = np.where(np.arange(5 * 60) % 2, 2.0, 0.0)
    small, big = noisy.copy(), noisy.copy()
    small[181:] += np.r_[6, 12 * np.ones(len(noisy) - 182)]
    big[181:] += np.r_[45, 60 * np.ones(len(noisy) - 182)]
    assert sc.detect(_minutes("2020-01-01", small)).empty
    ev = sc.detect(_minutes("2020-01-01", big))
    assert len(ev) == 1 and abs((ev.iloc[0].time - pd.Timestamp("2020-01-01 03:00", tz="UTC")).total_seconds()) <= 60
    assert ev.iloc[0].quiet_nt == 2.0 and ev.iloc[0].max_step_nt >= 43
    assert sc.detect(_minutes("2020-01-01", [1.0, 2.0])).empty


def test_parse_ebre_lists_of_three_formats():
    e15 = sc.parse_ebre(EBRE_2015)
    assert [e["time"].strftime("%Y-%m-%d %H:%M:%S") for e in e15] == [
        "2015-03-11 05:12:00", "2015-03-17 04:45:00", "2015-03-25 13:20:00"]
    assert e15[1]["type"] == "SSC" and e15[1]["amplitude_nt"] == pytest.approx(39.9)  # mean of the five stations
    assert sc.parse_ebre(EBRE_2024)[1]["time"] == pd.Timestamp("2024-05-10 17:05", tz="UTC")
    e03 = sc.parse_ebre(EBRE_2003)                     # 1995-2004: duration, one amplitude
    assert [(e["time"].strftime("%m-%d %H:%M"), e["type"], e["amplitude_nt"]) for e in e03] == [
        ("10-26 19:08", "SC", 8.9), ("10-29 06:10", "SC", 68.4)]
    e05 = sc.parse_ebre(EBRE_2005)                     # 2005: five rise times and amplitudes, no type
    assert e05[0]["time"].strftime("%H:%M:%S") == "07:48:24" and e05[0]["amplitude_nt"] == pytest.approx(11.9)
    det = pd.DataFrame({"time": [pd.Timestamp("2015-03-17 04:46", tz="UTC"), pd.Timestamp("2015-03-20", tz="UTC")]})
    matches, missed = sc.cross_match(det, e15)
    assert matches[0]["offset_minutes"] == 1.0 and matches[0]["type"] == "SSC" and matches[1] is None
    assert [e["time"].day for e in missed] == [11, 25]


def test_ebre_lists_are_cached_definitive_for_good_preliminary_for_a_week(tmp_path):
    served = {sc.EBRE_URL.format(year=2015, kind="d"): EBRE_2015, sc.EBRE_URL.format(year=2024, kind="p"): EBRE_2024,
              sc.EBRE_URL.format(year=2016, kind="d"): "<!DOCTYPE html><html>not found</html>"}
    asked = []

    async def fetch(url):
        asked.append(url)
        return served.get(url)

    got = asyncio.run(sc.load_ebre(fetch, tmp_path, [2015, 2016, 2024]))
    assert got["years"] == {2015: "definitive", 2016: None, 2024: "preliminary"}
    assert [e["time"].year for e in got["events"]] == [2015] * 3 + [2024] * 2
    asked.clear()
    assert asyncio.run(sc.load_ebre(fetch, tmp_path, [2015, 2024]))["years"] == {2015: "definitive", 2024: "preliminary"}
    assert asked == []                                  # both from the cache
    old = time.time() - 8 * 86400
    os.utime(tmp_path / "catalogs" / "ebre_ssc_2024_p.txt", (old, old))
    served.clear()                                      # offline: the stale preliminary list is used
    assert asyncio.run(sc.load_ebre(fetch, tmp_path, [2024]))["years"] == {2024: "preliminary"}
    assert asked == [sc.EBRE_URL.format(year=2024, kind="d"), sc.EBRE_URL.format(year=2024, kind="p")]
    served[sc.EBRE_URL.format(year=2024, kind="d")] = EBRE_2024  # published as definitive
    assert asyncio.run(sc.load_ebre(fetch, tmp_path, [2024]))["years"] == {2024: "definitive"}
    assert not (tmp_path / "catalogs" / "ebre_ssc_2024_p.txt").exists()


def _client(monkeypatch, tmp_path, omni, ebre):
    from fastapi.testclient import TestClient
    from helios.api import server
    from helios.core.downloader import DataDownloader
    from helios.core.event_analysis import EventDataClient

    asked = []

    async def fake(url, timeout=120.0):
        asked.append(url)
        if url in ebre:
            return ebre[url]
        if url.startswith("https://kp.gfz.de/"):  # GFZ Hp30 answers recorded for the storm days
            year = parse_qs(urlparse(url).query)["start"][0][:4]
            name = {"2015": "hp30_20150316", "2024": "hp30_20240509"}.get(year)
            return (Path(__file__).parent / "data" / "gfz" / f"{name}.json").read_text() if name else None
        q = parse_qs(urlparse(url).query)
        return _text(omni[q["time.min"][0][:7]]) if q.get("id") == ["OMNI_HRO_1MIN"] and q["time.min"][0][:7] in omni else None

    dl = DataDownloader()
    dl.fetch_text = fake
    dl.events = EventDataClient(lambda url: dl.fetch_text(url), tmp_path)
    monkeypatch.setattr(server, "downloader", dl)
    monkeypatch.setattr(server.helios_config, "CACHE_DIR", tmp_path)
    return TestClient(server.app, base_url=LOCAL), asked


def test_api_finds_the_listed_commencements_of_17_march_2015_and_10_may_2024(monkeypatch, tmp_path):
    client, asked = _client(monkeypatch, tmp_path, {"2015-03": "omni_hro_1min_psymh_20150316",
                                                    "2024-05": "omni_hro_1min_psymh_20240510"},
                            {sc.EBRE_URL.format(year=2015, kind="d"): EBRE_2015,
                             sc.EBRE_URL.format(year=2024, kind="p"): EBRE_2024})
    r = client.get("/api/analysis/sudden_commencements?start=2015-03-16&end=2015-03-19")
    assert r.status_code == 200, r.text
    body = r.json()
    q = parse_qs(urlparse(asked[0]).query)              # whole calendar months are requested
    assert (q["time.min"][0], q["time.max"][0], q["parameters"][0]) == ("2015-03-01T00:00:00Z", "2015-04-01T00:00:00Z",
                                                                          "Pressure,SYM_H")
    (e,) = body["result"]["events"]
    assert e["time"] == "2015-03-17 04:45" and e["detected"]
    assert (e["amplitude_nt"], e["rise_minutes"], e["max_step_nt"], e["quiet_nt"]) == (50, 3, 28, 0.0)
    assert e["pressure_ratio"] == pytest.approx(2.97, abs=0.01) and e["pressure_jump"] is True
    assert e["listed"] == {"time": "2015-03-17 04:45:00", "type": "SSC", "amplitude_nt": 39.9, "offset_minutes": 0.0}
    # IPShocks: WIND 04:00:03, MX3 normal (-0.92, -0.17, 0.37), 561.7 km/s, at (252.85, 54.35, 12.57) R_E:
    # |n.r| / V_sh = 44.6 min, so the planar front reaches the Earth at 04:44:37, 0.4 min before the onset.
    assert e["l1_shock"] == {"time": "2015-03-17 04:00:03", "spacecraft": "WIND", "shock_speed_kms": 561.7,
                             "predicted_arrival": "2015-03-17 04:44:37", "onset_minus_predicted_minutes": 0.4}
    assert e["hp30_max_24h"] == {"value": 8.667, "interval_start": "2015-03-17 13:30"}  # GFZ: 9- at 13:30
    assert len(e["window"]["sym_h"]) == len(body["series"]["window_minutes"]) == 151
    assert e["window"]["sym_h"][60] == 17 and e["window"]["sym_h"][63] == 67   # onset 17 nT, peak 3 min later
    c = body["result"]["comparison"]
    assert (c["listed"], c["found"], c["detections"], c["not_listed"], c["years"]) == (1, 1, 1, 0, {"2015": "definitive"})
    assert c["with_l1_shock"] == 1 and c["l1_shock_list"]["window_minutes"] == 15
    assert body["series"]["cadence_minutes"] == 1 and len(body["series"]["sym_h"]) == 3 * 1440
    prov = body["provenance"]
    assert prov["reference_list"]["licence"] == "CC BY-NC 4.0" and prov["coverage"]["sym_h"]["gaps"] == 0
    text = client.get("/api/analysis/sudden_commencements?start=2015-03-16&end=2015-03-19&format=csv").text
    lines = text.splitlines()
    assert lines[0].startswith("# title: HELIOS-L1 sudden commencements in OMNI SYM-H")
    assert "1 of 1 listed SCs found, 0 of 1 detections not listed" in text
    assert lines[-1].startswith("2015-03-17 04:45,1,50.0,3,28.0,")
    assert lines[-1].endswith(",2015-03-17 04:45:00,SSC,39.9,0.0,2015-03-17 04:00:03,WIND,561.7,0.4,8.667,2015-03-17 13:30")

    # 10 May 2024: SYM-H was already disturbed (median 1-min change 1 nT); the 35-nT minute
    # passes as at least 20 times that. The 2024 list is preliminary.
    body = client.get("/api/analysis/sudden_commencements?start=2024-05-10T12:00&end=2024-05-11").json()
    (e,) = body["result"]["events"]
    assert e["time"] == "2024-05-10 17:05" and e["quiet_nt"] == 1.0 and e["max_step_nt"] == 35
    assert e["listed"]["type"] == "SSC" and e["listed"]["offset_minutes"] == 0.0
    assert e["l1_shock"] is None  # the database ends in March 2024
    assert e["hp30_max_24h"] == {"value": 11.333, "interval_start": "2024-05-10 22:30"}  # GFZ: 11- at 22:30
    assert body["result"]["comparison"]["l1_shock_list"]["last_shock"] == "2024-03-25 10:04:50"
    assert body["result"]["comparison"]["years"] == {"2024": "preliminary"}


def test_api_limits_and_offline(monkeypatch, tmp_path):
    client, _ = _client(monkeypatch, tmp_path, {}, {})
    base = "/api/analysis/sudden_commencements"
    assert client.get(f"{base}?start=2015-03-02&end=2015-03-01").status_code == 422
    assert client.get(f"{base}?start=2015-01-01&end=2016-01-03").status_code == 422
    assert client.get(f"{base}?start=yesterday&end=2015-03-01").status_code == 422
    r = client.get(f"{base}?start=2015-03-01&end=2015-03-02")
    assert r.status_code == 503 and "could not be reached" in r.json()["detail"]
