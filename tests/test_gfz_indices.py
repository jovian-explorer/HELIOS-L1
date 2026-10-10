"""
GFZ Kp / Hp30 reading, caching and holding over their intervals (helios.core.gfz_indices).
tests/data/gfz holds answers of the GFZ web service (kp.gfz.de; Kp and Hp30, GFZ German Research Centre for
Geosciences, CC BY 4.0) for 16-18 March 2015 and 9-12 May 2024.
"""
import asyncio
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from helios.core import gfz_indices as gi

GFZ = Path(__file__).parent / "data" / "gfz"


def test_year_cache_offline_copy_and_interval_holding(tmp_path):
    asked = []
    answer = {"text": (GFZ / "hp30_20240509.json").read_text()}

    async def fetch(url):
        asked.append(url)
        return answer["text"]

    s = asyncio.run(gi.year_series(fetch, tmp_path, "hp30", 2015))
    assert asked == [gi.API.format(year=2015, index="Hp30")] and s.max() == 11.333
    assert asyncio.run(gi.year_series(fetch, tmp_path, "hp30", 2015)) is not None and len(asked) == 1  # kept for good
    mid_2015 = datetime(2015, 6, 1, tzinfo=timezone.utc).timestamp()
    os.utime(tmp_path / "gfz_indices" / "Hp30_2015.json", (mid_2015, mid_2015))
    asyncio.run(gi.year_series(fetch, tmp_path, "hp30", 2015))  # a copy taken during its year is renewed
    assert len(asked) == 2
    asked.pop()
    this_year = datetime.now(timezone.utc).year
    asyncio.run(gi.year_series(fetch, tmp_path, "hp30", this_year))
    os.utime(tmp_path / "gfz_indices" / f"Hp30_{this_year}.json", (time.time() - 3 * 86400,) * 2)
    answer["text"] = None  # a recent year is asked again after a day; offline, the last copy is used
    assert asyncio.run(gi.year_series(fetch, tmp_path, "hp30", this_year)).max() == 11.333 and len(asked) == 3
    answer["text"] = "<html>maintenance</html>"  # not the service's JSON: never cached
    assert asyncio.run(gi.year_series(fetch, tmp_path, "kp", 2023)) is None
    assert not (tmp_path / "gfz_indices" / "Kp_2023.json").exists()

    recs = gi.step_records(s, "hp30", datetime(2024, 5, 10, 22, 28, tzinfo=timezone.utc),
                           datetime(2024, 5, 10, 23, 2, tzinfo=timezone.utc))
    values = [r["hp30"] for r in recs]
    assert len(recs) == 34 and recs[2]["time_tag"] == "2024-05-10 22:30:00"
    assert values[:2] == [s["2024-05-10 22:00"]] * 2 and set(values[2:32]) == {11.333} and values[32] == s["2024-05-10 23:00"]
