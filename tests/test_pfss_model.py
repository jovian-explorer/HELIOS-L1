"""
Coronal field model (helios.core.pfss_model) on a dipole map, where the answer is known: the
current sheet is the equator of the source surface, field lines from the poles are open and
those from low heights at the equator closed. Checked on real maps: see the CHANGELOG entry.
"""
from datetime import datetime

import numpy as np
import pytest

pm = pytest.importorskip("helios.core.pfss_model")
pytest.importorskip("sunkit_magex")
pytest.importorskip("sunpy")


@pytest.fixture(scope="module")
def dipole_solution(tmp_path_factory):
    import sunpy.map
    from astropy.time import Time
    from sunkit_magex import pfss
    nphi, ns = 72, 36
    s = np.linspace(-1, 1, ns + 1)
    s = 0.5 * (s[1:] + s[:-1])
    br = np.tile((10.0 * s)[:, None], (1, nphi))  # B_r = 10 G cos(theta): a dipole, polar-field strength
    header = pfss.utils.carr_cea_wcs_header(Time("2024-05-09"), br.T.shape)
    m = sunpy.map.Map(br, header)
    path = str(tmp_path_factory.mktemp("maps") / "dipole.fits")
    m.save(path)
    return pm.solve(path, 2.5, 20)


def test_dipole_current_sheet_and_field_lines(dipole_solution):
    out = dipole_solution
    hcs = pm.hcs_lines(out)
    pts = np.vstack(hcs)
    assert np.all(np.abs(pts[:, 1]) < 3.0)  # the equator
    assert pm.hcs_distance(hcs, 100.0, 30.0) == pytest.approx(30.0, abs=3.0)
    res = pm.trace(out, [{"r_rsun": 1.05, "lon": 100.0, "lat": 75.0}, {"r_rsun": 1.2, "lon": 100.0, "lat": 0.0}], hcs)
    polar, equator = res
    assert polar["open"] and polar["polarity"] == 1 and "coronal hole" in polar["class"]
    assert not equator["open"] and equator["footpoint_br_gauss"] != 0
    with pytest.raises(ValueError):
        pm.trace(out, [{"r_rsun": 3.0, "lon": 0.0, "lat": 0.0}])


def test_ballistic_earth_connection():
    e = pm.earth_connection(datetime(2024, 5, 9, 12), 450.0, 2.5)
    # Omega (1 AU - 2.5 R_sun) / V = 2.865e-6 x 1.4786e8 km / 450 km/s = 53.9 deg
    assert e["longitude_shift_deg"] == pytest.approx(53.94, abs=0.05)
    assert (e["lon"] - e["sub_earth_lon"]) % 360 == pytest.approx(53.94, abs=0.05)
    assert pm.classify(True, 120.0).startswith("open field from the edge") and pm.classify(False, 5.0).endswith("(quiet Sun)")


def test_api_without_the_optional_packages(monkeypatch):
    from fastapi.testclient import TestClient
    from helios.api import server

    def missing(*a, **k):
        raise ImportError("sunkit_magex")
    monkeypatch.setattr(pm, "analyse", missing)
    c = TestClient(server.app, base_url="http://127.0.0.1:8765")
    r = c.post("/api/pfss", json={"time": "2024-05-09T12:00"})
    assert r.status_code == 501 and "sunkit-magex" in r.json()["detail"]
    assert c.post("/api/pfss", json={"time": "2024-05-09T12:00", "points": [{"r_rsun": 3.5, "lon": 0, "lat": 0}]}).status_code == 422


def test_plot_draws_without_pyplot(dipole_solution):

    url = pm.plot(dipole_solution, pm.hcs_lines(dipole_solution), [])
    assert url.startswith("data:image/png;base64,") and len(url) > 1000


def test_map_search_looks_back_a_day_and_takes_the_latest(monkeypatch, tmp_path):
    """GONG had no map from 23:44 to after 03:00 UT on 10 November 2023; a 2 h window found none."""
    import sys
    import types
    from datetime import datetime, timedelta, timezone
    from helios.core import pfss_model

    class Table(list):
        def sort(self, key):
            list.sort(self, key=lambda r: r[key])

    seen = {}

    def search(tr, *attrs):
        seen["span"] = tr.end - tr.start
        return [Table([{"Start Time": "2023-11-09 23:44"}, {"Start Time": "2023-11-09 20:14"}])]

    def fetch(row, path, progress):
        seen["row"] = row
        return ["map.fits"]

    attrs = types.SimpleNamespace(Time=lambda a, b: types.SimpleNamespace(start=a, end=b), Instrument=lambda x: x)
    monkeypatch.setitem(sys.modules, "sunpy.net", types.SimpleNamespace(Fido=types.SimpleNamespace(search=search, fetch=fetch), attrs=attrs))
    assert pfss_model.fetch_map("gong", datetime(2023, 11, 10, 3, tzinfo=timezone.utc), str(tmp_path)) == "map.fits"
    assert seen["span"] == timedelta(days=1) and seen["row"] == [{"Start Time": "2023-11-09 23:44"}]
