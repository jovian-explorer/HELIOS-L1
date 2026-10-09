"""
Refresh the bundled snapshot of the shocks observed at L1 in the IPShocks database
(helios/data/ipshocks_l1.json).

    python scripts/update_shock_catalog.py                    # latest version on Zenodo
    python scripts/update_shock_catalog.py ipshocks_database.csv

The database is published on Zenodo under CC BY 4.0 (doi:10.5281/zenodo.19730292).
"""
import csv
import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from helios.core import shock_catalog as sc  # noqa: E402

RECORD = "https://zenodo.org/api/records/19730292/versions/latest"


def _num(row, key, digits=3):
    v = row.get(key, "").strip()
    return round(float(v), digits) if v not in ("", "nan", "NaN") else None


def rows_to_events(rows):
    events = []
    for r in rows:
        craft = sc.SPACECRAFT.get(r["Spacecraft"])
        if craft is None:
            continue
        t = "{:04d}-{:02d}-{:02d} {:02d}:{:02d}:{:02d}".format(*(int(r[k]) for k in (
            "Year", "Month (1-12)", "Day (1-31)", "Hour (0-23)", "Minute (0-59)", "Second (0-59)")))
        events.append({
            "time": t, "spacecraft": craft, "type": r["Shock Type"],
            "position_gse_re": [_num(r, f"Spacecraft {c}", 2) for c in "XYZ"],
            "normal_gse": [_num(r, f"Shock Normal {c}") for c in "XYZ"],
            "normal_error": [_num(r, f"Shock Normal {c} Absolute Error") for c in "XYZ"],
            "theta_bn_deg": _num(r, "Shock Theta (degrees)", 1), "theta_bn_error_deg": _num(r, "Shock Theta Absolute Error (degrees)", 1),
            "shock_speed_kms": _num(r, "Shock Speed (km/s)", 1), "shock_speed_error_kms": _num(r, "Shock Speed Absolute Error (km/s)", 1),
            "alfven_mach": _num(r, "Alfven Mach Number", 2), "alfven_mach_error": _num(r, "Alfven Mach Number Absolute Error", 2),
            "magnetosonic_mach": _num(r, "Magnetosonic Mach Number", 2),
            "magnetosonic_mach_error": _num(r, "Magnetosonic Mach Number Absolute Error", 2),
            "field_ratio": _num(r, "Magnetic Field Ratio", 2), "density_ratio": _num(r, "Proton Density Ratio", 2),
            "speed_jump_kms": _num(r, "Speed Jump (km/s)", 1),
            "upstream_b_nt": _num(r, "Magnetic Field Upstream (nT)", 2), "upstream_density_cm3": _num(r, "Proton Density Upstream (cm^-3)", 2),
            "upstream_speed_kms": _num(r, "Speed Upstream (km/s)", 1), "plasma_beta": _num(r, "Plasma Beta Upstream", 2),
        })
    return sorted(events, key=lambda e: (e["time"], e["spacecraft"]))


def main():
    import httpx
    if len(sys.argv) > 1:
        text, version = Path(sys.argv[1]).read_text(encoding="utf-8"), "local file"
    else:
        rec = httpx.get(RECORD, timeout=60.0, follow_redirects=True).json()
        url = next(f["links"]["self"] for f in rec["files"] if f["key"].endswith(".csv"))
        text, version = httpx.get(url, timeout=120.0, follow_redirects=True).text, rec["metadata"]["publication_date"]
    events = rows_to_events(csv.DictReader(io.StringIO(text)))
    if len(events) < 500:
        sys.exit(f"Only {len(events)} L1 shocks read: the file layout may have changed; snapshot not written.")
    data = {"source": f"https://doi.org/{sc.DOI}", "doi": sc.DOI, "licence": sc.LICENCE, "citation": sc.CITATION,
            "version": version, "windows_minutes": sc.WINDOWS_MINUTES, "events": events}
    sc.SNAPSHOT.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Wrote {sc.SNAPSHOT.relative_to(ROOT)}: {len(events)} shocks at L1, version {version}")


if __name__ == "__main__":
    main()
