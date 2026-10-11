"""
Corona to L1 (helios.core.corona_link): the stream transit, the drag-based CME prediction and
the comparison with the IPShocks shocks at L1, on the CME of 10 September 2017 (west limb,
LASCO C3 front fitted at 2480 km/s, 22.9 R_sun at 17:30 UT), whose shock reached L1 on
12 September at 19:20-19:32 UT.
"""
from datetime import datetime, timezone

import pytest

from helios.core import corona_link as cl

T0 = datetime(2017, 9, 10, 17, 30, tzinfo=timezone.utc)


def test_stream_transit():
    p = cl.predict_stream(datetime(2024, 5, 1, tzinfo=timezone.utc), 400.0, 2.5)
    # (1.481e8 - 2.5 x 6.963e5) km / 400 km/s = 101.6 h
    assert p["transit_hours"] == pytest.approx((cl.L1_FROM_SUN_KM - 2.5 * cl.R_SUN_KM) / 400.0 / 3600.0, abs=0.05)
    with pytest.raises(ValueError):
        cl.predict_stream(T0, 0.0)


def test_cme_prediction_against_the_observed_shock():
    pred = cl.predict_cme(T0, 22.9, 2480.0, 420.0, 1.0e-7)
    shock = cl.observed_shock(pred["arrival_l1"], "WIND")
    assert shock["time"] == "2017-09-12 19:20:43" and shock["downstream_speed_kms"] == pytest.approx(546.6, abs=0.1)
    res = cl.compare(pred, shock, [{"time_tag": pred["arrival_l1"].strftime("%Y-%m-%d %H:%M:%S"), "speed": 480.0}])
    # Gamma = 1e-7 /km decelerates this CME to 464 km/s: 12 h late and 83 km/s too slow at L1.
    assert res["arrival_error_hours"] == pytest.approx(12.1, abs=0.3) and res["speed_error_kms"] < -50
    assert res["series"][0]["hours_from_predicted"] == 0.0 and res["measured_speed_at_predicted_kms"] == 480.0
    assert cl.observed_shock(datetime(2017, 9, 3, 12, tzinfo=timezone.utc), "WIND") is None  # none within 24 h


def test_endpoint_offline():
    from fastapi.testclient import TestClient
    from helios.api import server
    c = TestClient(server.app, base_url="http://127.0.0.1:8765")
    r = c.post("/api/link/l1", json={"mode": "cme", "time": "2017-09-10T17:30", "height_rsun": 22.9, "speed_kms": 2480})
    body = r.json()
    assert r.status_code == 200 and body["observed_shock"]["spacecraft"] == "WIND" and body["series"] == []
    assert c.post("/api/link/l1", json={"mode": "jet", "time": "2017-09-10", "speed_kms": 500}).status_code == 422
