"""
Refresh the bundled OMNI data of the historical events (helios/data/omni_events.json.gz): the
5-minute means the event viewer shows when NASA CDAWeb cannot be reached.

    python scripts/update_omni_events.py
"""
import asyncio
import gzip
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from helios.core.downloader import EVENT_WINDOWS, OMNI_SNAPSHOT, SNAPSHOT_COLUMNS, DataDownloader  # noqa: E402


async def main():
    dl = DataDownloader()
    out = {}
    for event_id, (a, b) in EVENT_WINDOWS.items():
        start, end = (datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in (a, b))
        bundle = await dl.get_archive_bundle("OMNI", start, end, cadence_minutes=5)
        if not bundle["records"]:
            sys.exit(f"{event_id}: {bundle['provenance']['description']}")
        rows = [[r["time_tag"]] + [None if r.get(c) is None else round(r[c], 2) for c in SNAPSHOT_COLUMNS[1:]]
                for r in bundle["records"]]
        out[event_id] = {"provenance": bundle["provenance"], "columns": SNAPSHOT_COLUMNS, "rows": rows}
        print(event_id, len(bundle["records"]))
    OMNI_SNAPSHOT.write_bytes(gzip.compress(json.dumps(out, separators=(",", ":")).encode(), mtime=0))


if __name__ == "__main__":
    asyncio.run(main())
