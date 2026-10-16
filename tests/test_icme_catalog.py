"""
Richardson & Cane list of near-Earth ICMEs (helios/core/icme_catalog.py): parsing, the
bundled snapshot, and cross-matching storms, magnetic cloud candidates and shocks with it.
"""
import gzip
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from helios.core import icme_catalog as ic
from helios.core import omni_statistics as om

LOCAL = "http://127.0.0.1:8765"

# Rows as on the page: header row, an ACE shock time '(A)', two magnetic clouds, a missing
# CME cell, 'P'/'Q' Dst, a single-digit day, a speed jump with a reported shock 'S', a last cell
# without </td> (as in the rows of 1996-1998 and 2001-2003 on the page).
PAGE = """<html><body>Revised July  23, 2026 *<table>
<tr><td>Disturbance Y/M/D (UT) (a)</td><td>ICME Plasma/Field Start, End Y/M/D (UT) (b)</td><td>x</td></tr>
<tr><td>1997/11/06 2248</td><td>1997/11/07 0400</td><td>1997/11/09 1200</td><td>...</td><td>...</td><td>+11</td>
<td>-21 (2 MCs)</td><td>Y</td><td>N</td><td>2</td><td>140 S</td><td>400</td><td>460</td><td>11</td><td>2</td><td>-110</td>
<td>640</td><td> 1997/11/04 0610 H   </tr>
<tr><td>1998/01/28 1600(A)</td><td>1998/01/29 1300</td><td>1998/01/31 0000</td><td>ns</td><td>nc</td><td>...</td><td>...</td>
<td>SEP</td><td>..</td><td>3W</td><td>40</td><td>420</td><td>450</td><td>8</td><td>2H</td><td>-34 P</td><td>...</td></tr>
<tr><td>2024/09/04 1200</td><td>2024/09/4 1400</td><td>2024/09/05 0300</td><td>...</td><td>...</td><td>...</td><td>...</td>
<td>...</td><td>...</td><td>2</td><td>10</td><td>380</td><td>400</td><td>9</td><td>0</td><td>-21 Q</td><td>...</td><td>...</td></tr>
</table></body></html>"""


def _events():
    return json.loads(ic.SNAPSHOT.read_text(encoding="utf-8"))["events"]


def test_parse_table_columns_and_codes():
    ev = ic.parse_table(PAGE)
    assert ic.revision(PAGE) == "July 23, 2026"
    assert [e["icme_start"] for e in ev] == ["1997-11-07 04:00", "1998-01-29 13:00", "2024-09-04 14:00"]
    a, b, c = ev
    assert a["disturbance"] == "1997-11-06 22:48" and a["fast_forward_shock"] and a["speed_jump_kms"] == 140
    assert a["two_magnetic_clouds"] and a["magnetic_cloud_offsets_h"] == [11.0, -21.0] and a["magnetic_cloud"] == 2
    assert a["dst_min_nt"] == -110 and a["dst_kind"] == "final" and a["cme"] == "1997/11/04 0610 H"
    assert b["disturbance_source"] == "shock at ACE" and b["composition_offsets_h"] == ["ns", "nc"]
    assert b["weak_signatures"] and b["quality"] == 3 and b["huttunen_2005"] and b["dst_kind"] == "provisional"
    assert b["bidirectional_ions"] is None and b["cme"] is None
    assert c["dst_kind"] == "quicklook" and c["dst_min_nt"] == -21 and not c["fast_forward_shock"]


def test_bundled_snapshot_matches_the_published_list():
    """
    Snapshot of revision July 23, 2026 (doi:10.7910/DVN/C2MHTH, CC0). Checked against the
    Dataverse spreadsheet of the same list: all 644 rows agree in disturbance, start, end,
    magnetic cloud flag and Dst (one Dst cell, '0 P', is a time in the spreadsheet).
    """
    data = json.loads(ic.SNAPSHOT.read_text(encoding="utf-8"))
    assert data["doi"] == "10.7910/DVN/C2MHTH" and data["licence"].startswith("CC0")
    ev = data["events"]
    assert len(ev) == 644 and data["revision"] == "July 23, 2026"
    # Cane & Richardson (2003) listed 214 ICMEs in 1996-2002; the list has been revised
    # since (a few weak events removed, others added): 220 now. ~300 in 1996-2009
    # (Richardson & Cane 2010): 323 now.
    years = [int(e["icme_start"][:4]) for e in ev]
    assert sum(1996 <= y <= 2002 for y in years) == 220 and sum(1996 <= y <= 2009 for y in years) == 323
    assert all(e["icme_start"] <= e["icme_end"] for e in ev)
    # The ICME times are given to the nearest hour: twice the disturbance follows the start.
    late = [e["disturbance"] for e in ev if e["disturbance"] > e["icme_start"]]
    assert late == ["2007-01-14 12:48", "2011-10-07 02:47"]
    # The associated CME column (380 entries, 'dg' for a LASCO data gap among them), also in
    # the rows whose last cell is not closed: the 10 Jan 1997 cloud names the CME of 6 Jan.
    assert sum(e["cme"] is not None for e in ev) == 380
    assert next(e for e in ev if e["icme_start"] == "1997-01-10 04:00")["cme"] == "1997/01/06 1510 H"


def test_locate_regions():
    ev = ic.parse_table(PAGE)
    t = lambda s: datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    assert ic.locate(ev, t("1997-11-07 01:00"))["region"] == "sheath"
    assert ic.locate(ev, t("1997-11-08 01:00"))["region"] == "ICME"
    assert ic.locate(ev, t("1997-11-09 14:00"))["region"] == "after"
    assert ic.locate(ev, t("1997-11-09 16:00")) is None
    assert ic.locate(ev, t("1997-11-09 16:00"), after_hours=6)["region"] == "after"


def test_intense_storms_1996_2006_in_listed_icmes():
    """
    The 90 storms of Echer et al. (2008) with Dst <= -100 nT (1996-2006): 75 have their
    Dst minimum in a listed ICME (57), its sheath (14) or the 3 h after it (4); all ten
    storms below -250 nT do (7 in the ICME, 3 in the sheath), and for eight of them the
    list's Dst for that ICME is the storm minimum (2000-04-07: -288 listed, -292 in OMNI;
    2000-07-16: -301 listed, -300 in OMNI).
    """
    rows = []
    with gzip.open(Path(__file__).parent / "data" / "omni_dst_le_minus100_1996_2006.csv.gz", "rt") as f:
        for line in f:
            if not line.startswith("#"):
                t, v = line.strip().split(",")
                rows.append((pd.Timestamp(t, tz="UTC"), float(v)))
    df = pd.DataFrame({"dst": [v for _, v in rows]}, index=pd.DatetimeIndex([t for t, _ in rows]))
    storms = om.find_storms(df, -100.0, 6.0)["storms"]
    assert ic.annotate_storms(storms, _events()) == {"sheath": 14, "ICME": 57, "after": 4, "none": 15}
    supers = om.find_storms(df, -250.0, 6.0)["storms"]
    assert ic.annotate_storms(supers, _events()) == {"sheath": 3, "ICME": 7, "after": 0, "none": 0}
    same = [s for s in supers if s["icme"]["dst_min_nt"] == s["minimum_dst_nt"]]
    assert len(same) == 8
    halloween = [s for s in supers if s["minimum_time"].startswith("2003-10-30")]
    assert [(s["icme"]["region"], s["icme"]["icme_start"]) for s in halloween] == [
        ("ICME", "2003-10-29 11:00"), ("sheath", "2003-10-31 02:00")]


def test_icme_endpoint_and_csv():
    from helios.api import server
    client = TestClient(server.app, base_url=LOCAL)
    body = client.get("/api/catalogs/icme?start=2003-10-28&end=2003-11-03").json()
    assert body["catalog"]["doi"] == "10.7910/DVN/C2MHTH" and body["catalog"]["origin"] == "bundled snapshot"
    assert [e["icme_start"] for e in body["events"]] == [
        "2003-10-26 22:00", "2003-10-28 02:30", "2003-10-29 11:00", "2003-10-31 02:00"]  # all overlapping
    csv = client.get("/api/catalogs/icme?start=2003-10-28&end=2003-11-03&format=csv")
    assert csv.status_code == 200 and "# licence: CC0" in csv.text and "2003-10-29 06:11" in csv.text
    assert client.get("/api/catalogs/icme?start=2004-01-02&end=2004-01-01").status_code == 422


def test_shock_and_cloud_candidates_are_matched():
    from helios.api import server
    ev = _events()
    # WIND shock of 17 March 2015 04:00:04: the listed disturbance (sudden commencement
    # at Earth) follows it by about 45 minutes.
    near = server._icme_disturbance_near(ev, "2015-03-17 04:00:04")
    assert near["disturbance"] == "2015-03-17 04:45" and near["delay_minutes"] == 45.0
    assert server._icme_disturbance_near(ev, "2015-03-10 04:00:00") is None
    # The 18-20 October 1995 cloud predates the list; 7-8 November 1997 lies in a listed ICME
    over = server._icme_overlaps(ev, "1997-11-07 15:34", "1997-11-08 04:36")
    assert len(over) == 1 and over[0]["magnetic_cloud"] == 2 and over[0]["fraction_inside_icme"] == 1.0
    assert server._icme_overlaps(ev, "1995-10-18 19:48", "1995-10-20 01:18") == []
