"""
Event correlation (helios.core.event_catalogs) on catalogue extracts of 10 September 2017:
a CDAW row and height-time file, CACTus lines and a DONKI CME, as served by their sites.
"""
import asyncio
import json
from datetime import datetime, timezone

import pytest

from helios.core import event_catalogs as ec

CDAW_ROW = '''<tr>
<td headers="hd_date_time"> <! date>
<a href="../../daily_movies/2017/09/10/">2017/09/10
</a>
</td>
<td headers="hd_date_time"> <! time>
<a href="yht/20170910.160005.w360h.v3163.p262g.yht" title="see height-time digital file">
16:00:05
</a>
</td>
<td headers="hd_cpa" align=right> <! pa>
Halo
</td>
<td headers="hd_wd" align=right> <! width>
 360
</td>
<td headers="hd_v1" align=right> <! linear fit>
<a href="htpng/20170910.160005.p262g.htp.html">3163</a>
</td>
</tr>
<tr>
<td headers="hd_date_time">2017/09/10</td><td headers="hd_date_time">05:00:05</td>
<td headers="hd_cpa">273</td><td headers="hd_wd">32</td><td headers="hd_v1">664</td>
</tr>'''
YHT = "#VERSION=3\n# HEIGHT DATE TIME\n  3.00 2017/09/10 16:00:05 260.4 C2\n  5.10 2017/09/10 16:06:05 260.7 C3\n"
CACTUS = """# CME |          t0    | dt0| pa | da |  v  |  dv | minv| maxv| halo?
  0037|2017/09/10 16:48| 36 | 144| 360| 0948| 0618| 0104| 2013|  IV
  0036|2017/09/10 05:00| 03 | 273| 032| 0664| 0493| 0224| 1644|
# Flow|          t0    | dt0| pa | da |  v  |  dv | minv| maxv| halo?
  0011|2017/09/10 18:36| 01 | 261| 012| 0475| 0512| 0280| 1314|
"""
DONKI_CME = [{"activityID": "2017-09-10T16:09:00-CME-001", "startTime": "2017-09-10T16:09Z", "sourceLocation": "S09W91",
              "cmeAnalyses": [{"time21_5": "2017-09-10T17:18Z", "speed": 2650.0, "latitude": -12.0, "longitude": 85.0,
                               "halfAngle": 54.0, "isMostAccurate": True}],
              "linkedEvents": [{"activityID": "2017-09-10T15:35:00-FLR-001"}]}]
DONKI_FLR = [{"flrID": "2017-09-10T15:35:00-FLR-001", "beginTime": "2017-09-10T15:35Z", "peakTime": "2017-09-10T16:06Z",
              "classType": "X8.2", "sourceLocation": "S08W88", "activeRegionNum": 12673}]
HEK = {"result": [{"event_starttime": "2017-09-10T15:35:00", "event_peaktime": "2017-09-10T16:06:00", "frm_name": "SWPC",
                   "fl_goescls": "X8.2", "ar_noaanum": 12673, "hpc_x": 0, "hpc_y": -120.7},
                  {"event_starttime": "2017-09-10T17:05:00", "event_peaktime": "2017-09-10T17:10:00", "frm_name": "SWPC",
                   "fl_goescls": "C2.0"},
                  {"event_starttime": "2017-09-10T15:37:20", "event_peaktime": "2017-09-10T16:15:56",
                   "frm_name": "Flare Detective - Trigger Module", "fl_goescls": ""}]}


def _cat(tmp_path):
    async def fetch(url):
        if "univ2017_09.html" in url:
            return "<table>" + CDAW_ROW + "</table>"
        if url.endswith(".yht"):
            return YHT
        if "cactus" in url and "2017/09" in url:
            return CACTUS
        if "DONKI-API/get/CME" in url:
            return json.dumps(DONKI_CME)
        if "DONKI-API/get/FLR" in url:
            return json.dumps(DONKI_FLR)
        if "lmsal" in url:
            return json.dumps(HEK)
        return None
    return ec.Catalogs(fetch, tmp_path)


def test_parsers():
    rows = ec.parse_cdaw(CDAW_ROW, datetime(2017, 9, 1))
    assert rows[0] == {"catalog": "CDAW", "time": "2017-09-10 16:00:05", "central_pa_deg": None, "width_deg": 360.0,
                       "speed_kms": 3163.0, "yht": "yht/20170910.160005.w360h.v3163.p262g.yht"}
    assert rows[1]["central_pa_deg"] == 273.0 and rows[1]["yht"] is None
    bad = CDAW_ROW.replace("<td headers=\"hd_cpa\">273</td>", "<td headers=\"hd_cpa\">----</td>")
    assert len(ec.parse_cdaw(bad, datetime(2017, 9, 1))) == 1  # the row without a PA is left out, not an error
    cac = ec.parse_cactus(CACTUS)
    assert [c["time"] for c in cac] == ["2017-09-10 16:48:00", "2017-09-10 05:00:00"]  # the flow is left out
    assert ec.donki_pa(90.0, 0.0) == pytest.approx(270.0) and ec.donki_pa(-90.0, 0.0) == pytest.approx(90.0)
    assert ec.pa_inside(262, 273, 32) and not ec.pa_inside(300, 273, 32) and ec.pa_inside(10, 350, 60)


def test_match_of_the_10_september_2017_cme(tmp_path):
    # LASCO C3 front at 15.8 R_sun, PA 262, at 16:42 UT (CDAW height-time file: 15.77 R_sun at 16:42:05).
    res = asyncio.run(ec.match(_cat(tmp_path), datetime(2017, 9, 10, 16, 42, tzinfo=timezone.utc), 15.8, 262.0, 2.0))
    by = {c["catalog"]: c for c in res["cmes"]}
    assert set(by) == {"CDAW", "DONKI"}  # CACTus onset 16:48 is after the event
    # CDAW: from 3.0 R_sun at 16:00:05 at 3163 km/s -> 15.8 R_sun at 16:47
    assert by["CDAW"]["reference_height_rsun"] == 3.0 and by["CDAW"]["arrival_at_height"] == "2017-09-10 16:47:00"
    assert by["DONKI"]["pa_inside"] and by["DONKI"]["linked_flares"] == ["2017-09-10T15:35:00-FLR-001"]
    assert [f["class"] for f in res["flares"]] == ["X8.2", "X8.2"]  # GOES (HEK, SWPC only) and DONKI


def test_endpoint_offline():
    from fastapi.testclient import TestClient
    from helios.api import server
    c = TestClient(server.app, base_url="http://127.0.0.1:8765")
    r = c.post("/api/events/match", json={"time": "2017-09-10T16:42", "height_rsun": 15.8, "pa_deg": 262})
    assert r.status_code == 200 and r.json()["cmes"] == []  # nothing to read offline
    assert c.post("/api/events/match", json={"time": "x", "height_rsun": 15.8, "pa_deg": 262}).status_code == 422
