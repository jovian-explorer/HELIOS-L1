"""
Refresh the bundled copy of NOAA SWPC's solar-cycle products (helios/data/solar_cycle.json.gz):
observed monthly indices since the cycle 23/24 minimum and the predicted cycle, shown when
NOAA cannot be reached.

    python scripts/update_solar_cycle.py
"""
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from helios.config import NOAA_SWPC_ENDPOINTS  # noqa: E402
from helios.core.solar_cycle import SNAPSHOT, SolarCycleEngine  # noqa: E402

keep = ("time-tag", "ssn", "smoothed_ssn", "f10.7", "smoothed_f10.7")
observed = [{k: r.get(k) for k in keep} for r in httpx.get(NOAA_SWPC_ENDPOINTS["solar_cycle_observed"], timeout=60).json()
            if r["time-tag"] >= SolarCycleEngine.CYCLE_24_START]
predicted = httpx.get(NOAA_SWPC_ENDPOINTS["solar_cycle_predicted"], timeout=60).json()
out = {"retrieved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d"), "observed": observed, "predicted": predicted}
SNAPSHOT.write_bytes(gzip.compress(json.dumps(out, separators=(",", ":")).encode(), mtime=0))
print(len(observed), len(predicted))
