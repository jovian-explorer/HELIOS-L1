"""
Build tests/data/icmecat_lineups.json, the inputs of two reproductions in tests/test_reproductions.py:

* the spacecraft positions of the multipoint ICME list of Moestl et al. (2022, ApJL 924, L6, Table 1;
  arXiv:2109.07200): HELIOS-L1's SPICE positions (GSE vectors from the Sun and the Sun's longitude)
  at each in situ arrival at Parker Solar Probe, Solar Orbiter, BepiColombo, STEREO-A and Wind;
  and, for the PSP, Solar Orbiter and BepiColombo rows, at the magnetic obstacle start of the same ICMEs in ICMECAT;
* ICME lineups in the HELIO4CAST ICMECAT (Moestl et al. 2017, 2020; figshare doi:10.6084/m9.figshare.6356420,
  MIT licence): every ICME at PSP or Solar Orbiter inside 0.9 AU with a mean ICME speed, paired with the
  one ICME at Wind, STEREO-A or BepiColombo within 10 deg of HEEQ longitude whose start implies a transit speed of
  250-1000 km/s (pairs with two such candidates are left out), with the SPICE distances of both
  spacecraft at the ICME starts and the mean measured solar wind speed at the outer spacecraft in the
  24 h before its ICME start (OMNI for Wind, PLASTIC for STEREO-A; none for BepiColombo), and the
  inner ICME's mean sheath speed where ICMECAT has one, and the shock speed and normal that HELIOS-L1's
  Event Analysis measures at the inner ICME start (PSP SPAN-I or Solar Orbiter SWA-PAS; kept only for a fast
  forward shock with density and |B| ratios of at least 1.2 and three or more plasma samples on each side).

    python scripts/icmecat_lineups.py              # latest ICMECAT version on figshare
    python scripts/icmecat_lineups.py icmecat.csv  # a downloaded HELIO4CAST_ICMECAT_v*.csv

Needs the network for the SPICE kernels (JPL Horizons) and, without a file, figshare.
"""
import csv
import io
import json
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from helios.core.constants import AU_KM  # noqa: E402
from helios.core.event_analysis import heeq_position  # noqa: E402
from helios.core.spice_engine import get_spice_engine  # noqa: E402

ARTICLE = "https://api.figshare.com/v2/articles/6356420"
OUT = ROOT / "tests" / "data" / "icmecat_lineups.json"
EPHEMERIS = {"PSP": "PARKER_SOLAR_PROBE", "SolarOrbiter": "SOLAR_ORBITER", "STEREO-A": "STEREO_A", "Wind": "WIND",
             "BepiColombo": "BEPICOLOMBO"}
# Solar wind upstream of the outer spacecraft (HELIOS-L1 archive): OMNI for Wind, PLASTIC for STEREO-A;
# BepiColombo has no public solar wind speed.
UPSTREAM = {"Wind": "OMNI", "STEREO-A": "STEREO_A"}
UPSTREAM_HOURS = 24
# Moestl et al. (2022), Table 1: in situ arrivals at the spacecraft HELIOS-L1 has an ephemeris for
# (time UT, ICMECAT spacecraft name, R in AU, HEEQ longitude in deg).
TABLE1 = [("2020-04-19 05:06", "SolarOrbiter", 0.808, -4.0), ("2020-04-20 01:34", "Wind", 0.996, 0.2),
          ("2020-04-20 03:09", "BepiColombo", 1.011, -1.3), ("2020-05-29 15:27", "BepiColombo", 0.977, -5.2),
          ("2020-06-29 09:44", "BepiColombo", 0.881, -3.9), ("2020-10-08 10:27", "BepiColombo", 0.694, 79.5),
          ("2020-10-10 04:07", "BepiColombo", 0.698, 80.4),
          ("2020-05-28 12:45", "SolarOrbiter", 0.564, 28.2), ("2020-05-29 21:20", "Wind", 1.005, -0.2),
          ("2020-06-03 07:54", "STEREO-A", 0.965, -71.5), ("2020-06-25 11:39", "PSP", 0.523, 19.9),
          ("2020-06-30 01:12", "Wind", 1.007, -0.2), ("2020-07-09 14:17", "STEREO-A", 0.962, -68.0),
          ("2020-07-13 20:18", "Wind", 1.006, -0.2), ("2020-08-19 21:11", "STEREO-A", 0.958, -64.6),
          ("2020-09-12 10:23", "PSP", 0.473, 13.0), ("2020-10-05 06:52", "Wind", 0.991, 0.2),
          ("2020-11-01 11:54", "Wind", 0.984, 0.1), ("2020-12-01 02:22", "PSP", 0.804, -96.8),
          ("2020-12-01 07:28", "STEREO-A", 0.959, -57.6), ("2020-12-03 18:04", "STEREO-A", 0.960, -57.5),
          ("2021-02-15 18:58", "Wind", 0.977, 0.1), ("2021-02-23 10:34", "STEREO-A", 0.967, -55.7),
          ("2021-02-24 04:08", "Wind", 0.979, 0.2), ("2021-03-26 18:00", "Wind", 0.989, 0.2),
          ("2021-04-04 21:52", "Wind", 0.992, 0.2), ("2021-04-06 01:27", "STEREO-A", 0.967, -54.4)]


def position(craft: str, t: datetime):
    """(GSE vector from the Sun in km, the Sun's ecliptic longitude) from HELIOS-L1's SPICE ephemeris."""
    eng = get_spice_engine()
    iso = t.strftime("%Y-%m-%dT%H:%M:%S")
    sc, earth = eng.get_spacecraft_state(EPHEMERIS[craft], iso), eng.get_spacecraft_state("EARTH", iso)
    if not (sc.get("is_spice_verified") and earth.get("available")):
        raise RuntimeError(f"no SPICE position for {craft} at {iso}")
    g = sc["gse_coordinates"]
    r = np.array([g["x_km"], g["y_km"], g["z_km"]]) - np.array([earth["heliocentric"]["distance_km"], 0.0, 0.0])
    return [round(float(x), 1) for x in r], round(earth["heliocentric"]["ecliptic_longitude_deg"] + 180.0, 5)


def upstream_speed(craft: str, t: datetime):
    """Mean measured solar wind speed (km/s) at the outer spacecraft in the UPSTREAM_HOURS before the ICME
    start; None without data for at least half of them."""
    import asyncio
    from helios.core.archive import ArchiveClient
    from helios.core.downloader import DataDownloader
    mission = UPSTREAM.get(craft)
    if mission is None:
        return None
    t = t.replace(tzinfo=timezone.utc)
    dl = DataDownloader()
    res = asyncio.run(ArchiveClient(dl.fetch_text, dl.cache_dir).fetch_mission(mission, t - timedelta(hours=UPSTREAM_HOURS), t))
    v = res["frame"]["speed"].dropna() if "speed" in res["frame"] else []
    return round(float(v.mean()), 1) if len(v) >= 30 * UPSTREAM_HOURS else None


def inner_shock(craft: str, t: datetime):
    """(shock speed in km/s, radial component of the normal) of a clear fast forward shock at the inner ICME
    start from HELIOS-L1's Event Analysis on the spacecraft's own field and plasma; (None, None) otherwise."""
    import asyncio
    import pandas as pd
    from helios.core.downloader import DataDownloader
    from helios.core.event_analysis import analyze_shock
    t = t.replace(tzinfo=timezone.utc)
    d = asyncio.run(DataDownloader().events.fetch({"PSP": "PSP", "SolarOrbiter": "SOLO"}[craft],
                                                   t - timedelta(hours=2), t + timedelta(hours=2)))
    if d["field"] is None or d["plasma"] is None:
        return None, None
    try:
        a = analyze_shock(d["field"], d["plasma"], pd.Timestamp(t))
    except ValueError:  # too few samples
        return None, None
    m = a["methods"][a["preferred_method"]]
    if (a["shock_type"] != "FF" or min(a["density_ratio"], a["field_ratio"]) < 1.2 or m["shock_speed_kms"] is None
            or min(a["upstream"]["plasma_samples"], a["downstream"]["plasma_samples"]) < 3):
        return None, None
    return round(m["shock_speed_kms"], 1), round(abs(m["normal_gse"][0]), 3)


def icmecat_rows(path=None):
    if path:
        text = Path(path).read_text(encoding="utf-8")
    else:
        meta = json.load(urllib.request.urlopen(ARTICLE, timeout=60))
        f = next(f for f in meta["files"] if f["name"].endswith(".csv") and "ICMECAT" in f["name"])
        text = urllib.request.urlopen(f["download_url"], timeout=300).read().decode("utf-8")
        print(f"ICMECAT {meta['doi']}: {f['name']}")
    return list(csv.DictReader(io.StringIO(text)))


def lineups(rows):
    num = lambda r, k: float(r[k]) if r.get(k) not in (None, "", "nan") else float("nan")
    when = lambda r: datetime.strptime(r["icme_start_time"], "%Y-%m-%dT%H:%MZ")
    inner = [r for r in rows if r["sc_insitu"] in ("PSP", "SolarOrbiter") and num(r, "mo_sc_heliodistance") < 0.9
             and np.isfinite(num(r, "icme_speed_mean"))]
    outer = [r for r in rows if r["sc_insitu"] in ("Wind", "STEREO-A", "BepiColombo")]
    pairs = []
    for a in inner:
        for craft in ("Wind", "STEREO-A", "BepiColombo"):
            cands = []
            for b in (b for b in outer if b["sc_insitu"] == craft):
                dlon = (num(b, "mo_sc_long_heeq") - num(a, "mo_sc_long_heeq") + 180.0) % 360.0 - 180.0
                dr = (num(b, "mo_sc_heliodistance") - num(a, "mo_sc_heliodistance")) * AU_KM
                dt = (when(b) - when(a)).total_seconds()
                if abs(dlon) <= 10.0 and dr > 0.1 * AU_KM and dr / 1000.0 < dt < dr / 250.0:
                    cands.append((b, dlon))
            if len(cands) != 1:
                continue
            b, dlon = cands[0]
            ra, _ = position(a["sc_insitu"], when(a))
            rb, _ = position(craft, when(b))
            v_sh, n_r = inner_shock(a["sc_insitu"], when(a))
            pairs.append({"inner": a["icmecat_id"], "outer": b["icmecat_id"],
                          "inner_start": when(a).strftime("%Y-%m-%d %H:%M"), "outer_start": when(b).strftime("%Y-%m-%d %H:%M"),
                          "inner_speed_kms": num(a, "icme_speed_mean"), "dlon_deg": round(dlon, 1),
                          "inner_sheath_speed_kms": num(a, "sheath_speed_mean") if np.isfinite(num(a, "sheath_speed_mean")) else None,
                          "inner_r_au": round(float(np.linalg.norm(ra)) / AU_KM, 5),
                          "outer_r_au": round(float(np.linalg.norm(rb)) / AU_KM, 5),
                          "outer_upstream_speed_kms": upstream_speed(craft, when(b)),
                          "inner_shock_speed_kms": v_sh, "inner_shock_normal_r": n_r})
    return pairs


def main():
    rows = icmecat_rows(sys.argv[1] if len(sys.argv) > 1 else None)
    table1 = []
    for t, craft, r_au, lon in TABLE1:
        r, sun_lon = position(craft, datetime.strptime(t, "%Y-%m-%d %H:%M"))
        table1.append({"time": t, "spacecraft": craft, "r_au": r_au, "lon_heeq": lon, "r_sun_gse_km": r,
                       "sun_longitude_deg": sun_lon})
        d, lo, _ = heeq_position(r, sun_lon)
        print(f"{t} {craft:12s} R {r_au:.3f} / {d:.4f} AU  lon {lon:6.1f} / {lo:6.2f}")
    # ICMECAT gives the position at the start of the magnetic obstacle: the same ICMEs at that time.
    mo_start = []
    for r in rows:
        start = r["icme_start_time"].replace("T", " ").rstrip("Z")
        if r["sc_insitu"] in ("PSP", "SolarOrbiter", "BepiColombo") and any(start == t and r["sc_insitu"] == c for t, c, _, _ in TABLE1):
            tm = datetime.strptime(r["mo_start_time"], "%Y-%m-%dT%H:%MZ")
            v, sun_lon = position(r["sc_insitu"], tm)
            mo_start.append({"time": tm.strftime("%Y-%m-%d %H:%M"), "spacecraft": r["sc_insitu"], "id": r["icmecat_id"],
                             "r_au": float(r["mo_sc_heliodistance"]), "lon_heeq": float(r["mo_sc_long_heeq"]),
                             "r_sun_gse_km": v, "sun_longitude_deg": sun_lon})
    pairs = lineups(rows)
    OUT.write_text(json.dumps({
        "sources": {"table1": "Moestl et al. (2022), ApJL 924, L6, Table 1 (arXiv:2109.07200)",
                    "icmecat": "HELIO4CAST ICMECAT, doi:10.6084/m9.figshare.6356420 (MIT licence)",
                    "positions": "HELIOS-L1 SPICE ephemeris (JPL Horizons), " + datetime.now(timezone.utc).strftime("%Y-%m-%d")},
        "table1": table1, "icmecat_mo_start": mo_start, "pairs": pairs}, indent=1) + "\n", encoding="utf-8")
    print(f"{len(pairs)} lineup pairs -> {OUT}")


if __name__ == "__main__":
    main()
