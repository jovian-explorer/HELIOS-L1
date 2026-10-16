"""
Equatorward edges of electron precipitation in DMSP SSJ passes during four storms, for the
auroral oval check (tests/data/dmsp_ssj_edges_storms.json).

    python scripts/dmsp_oval_edges.py

Edge: on each auroral-zone crossing (|AACGM lat| > 35 deg, at least 10 min), on each side of the
highest latitude, the lowest |lat| where the 15-s running median of the electron total energy flux
reaches 0.25 erg cm-2 s-1 (4.97e10 eV cm-2 s-1 sr-1, isotropic over pi sr). Kp from GFZ.
"""
import json
import math
import urllib.request
import warnings
from datetime import date, timedelta
from pathlib import Path

import numpy as np
from numpy.lib.stride_tricks import sliding_window_view

OUT = Path(__file__).resolve().parent.parent / "tests" / "data" / "dmsp_ssj_edges_storms.json"
STORMS = {("2003-10-29", "2003-11-01"): ["F13", "F15", "F16"], ("2004-11-07", "2004-11-11"): ["F13", "F14", "F15", "F16"],
          ("2012-09-30", "2012-10-03"): ["F16", "F17", "F18"], ("2013-03-17", "2013-03-19"): ["F16", "F17", "F18"]}
warnings.filterwarnings("ignore", "All-NaN slice")  # windows inside data gaps
THRESHOLD = 0.25 / (math.pi * 1.602e-12)


def day_edges(sat, day):
    url = (f"https://cdaweb.gsfc.nasa.gov/hapi/data?id=DMSP-{sat}_SSJ_PRECIPITATING-ELECTRONS-IONS&parameters="
           f"ELE_TOTAL_ENERGY_FLUX,SC_AACGM_LAT,SC_AACGM_LTIME&time.min={day}T00:00Z&time.max={day + timedelta(days=1)}T00:00Z")
    rows = [ln.split(",") for ln in urllib.request.urlopen(url, timeout=600).read().decode().splitlines()]
    rows = [r for r in rows if len(r) == 4]
    if not rows:
        return []
    t = [r[0][:19] for r in rows]
    f = np.array([float(r[1].strip('"')) if r[1].strip('"') not in ("", "NaN") else np.nan for r in rows])
    lat, mlt = (np.array([float(r[i]) for r in rows]) for i in (2, 3))
    med = np.nanmedian(sliding_window_view(np.concatenate([np.full(7, np.nan), f, np.full(7, np.nan)]), 15), axis=1)
    out = []
    zone = np.abs(lat) > 35.0
    idx = np.flatnonzero(np.diff(np.concatenate([[0], zone.astype(int), [0]])))
    for s, e in zip(idx[::2], idx[1::2]):
        if e - s < 600:
            continue
        top = s + int(np.argmax(np.abs(lat[s:e])))
        for a, b in ((s, top), (top, e)):
            if b - a < 300:
                continue
            ok = a + np.flatnonzero(med[a:b] >= THRESHOLD)
            if len(ok):
                j = ok[np.argmin(np.abs(lat[ok]))]
                if abs(lat[j]) > 35.5:
                    out.append((t[j], sat, float(mlt[j]), float(abs(lat[j]))))
    return out


rows = []
for (a, b), sats in STORMS.items():
    kp_url = f"https://kp.gfz.de/app/json/?start={a}T00:00:00Z&end={b}T23:59:59Z&index=Kp"
    g = json.load(urllib.request.urlopen(kp_url, timeout=120))
    kp = {t[:13]: k for t, k in zip(g["datetime"], g["Kp"])}
    d = date.fromisoformat(a)
    while d < date.fromisoformat(b):
        for sat in sats:
            for t, s, mlt, lat in day_edges(sat, d):
                k = kp.get(f"{t[:10]}T{int(t[11:13]) // 3 * 3:02d}")
                if k is not None:
                    rows.append([t, s, k, round(mlt, 2), round(lat, 2)])
        d += timedelta(days=1)
OUT.write_text(json.dumps({
    "source": "DMSP F13-F18 SSJ (NASA CDAWeb, DMSP-F1x_SSJ_PRECIPITATING-ELECTRONS-IONS), made with scripts/dmsp_oval_edges.py",
    "edge": "lowest |AACGM latitude| of each auroral-zone crossing where the 15-s median electron total energy flux "
            ">= 0.25 erg cm-2 s-1 (4.97e10 eV cm-2 s-1 sr-1, isotropic); Kp from GFZ",
    "columns": ["time", "satellite", "kp", "mlt", "edge_lat"], "rows": sorted(rows)}, separators=(",", ":")))
print(len(rows), "edges")
