"""
Refresh the bundled snapshot of the Richardson & Cane ICME list
(helios/data/icme_richardson_cane.json), used when the live page cannot be read.

    python scripts/update_icme_catalog.py              # reads the live page
    python scripts/update_icme_catalog.py page.htm     # or a saved copy of it

The list is published under CC0 1.0 on Harvard Dataverse (doi:10.7910/DVN/C2MHTH).
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from helios.core import icme_catalog as ic  # noqa: E402


def main():
    if len(sys.argv) > 1:
        page = Path(sys.argv[1]).read_text(encoding="cp1252", errors="replace")
        retrieved = datetime.fromtimestamp(Path(sys.argv[1]).stat().st_mtime, timezone.utc)
    else:
        retrieved = datetime.now(timezone.utc)
        import httpx
        page = httpx.get(ic.SOURCE_URL, timeout=60.0, follow_redirects=True).content.decode("cp1252", errors="replace")
    events = ic.parse_table(page)
    if len(events) < 500:
        sys.exit(f"Only {len(events)} events parsed: the page layout may have changed; snapshot not written.")
    data = {"source": ic.SOURCE_URL, "doi": ic.DOI, "licence": ic.LICENCE, "citation": ic.CITATION,
            "revision": ic.revision(page), "retrieved_utc": retrieved.strftime("%Y-%m-%d"),
            "events": events}
    ic.SNAPSHOT.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {ic.SNAPSHOT.relative_to(ROOT)}: {len(events)} ICMEs, revision {data['revision']}")


if __name__ == "__main__":
    main()
