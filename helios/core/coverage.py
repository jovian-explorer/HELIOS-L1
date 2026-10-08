"""
Data coverage and gaps of a time series over a requested interval.

A gap is a stretch longer than ``threshold_s`` without a valid sample: at the start of
the interval (before the first sample), between two samples (from one nominal sample
length after a sample to the next sample) or at the end. The answer gives the fraction of
the interval outside such gaps, the number of samples against the number expected at the
nominal cadence, the first and last sample, and the gaps (the longest first in
``longest_gap``, all of them, up to ``max_list``, in time order).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

import numpy as np


def _fmt(t: datetime) -> str:
    return t.strftime("%Y-%m-%d %H:%M:%S")


def gap_report(times: Iterable[datetime], start: datetime, end: datetime, threshold_s: float,
               nominal_s: Optional[float] = None, max_list: int = 20) -> Dict[str, Any]:
    """Coverage of [start, end) by the sample times (sorted or not; tz-aware UTC)."""
    span = (end - start).total_seconds()
    ts = sorted(t for t in times if start <= t < end)
    if nominal_s is None:
        d = np.diff([t.timestamp() for t in ts]) if len(ts) > 1 else np.array([])
        nominal_s = float(np.median(d)) if d.size else 60.0
    out: Dict[str, Any] = {"samples": len(ts), "nominal_cadence_s": round(nominal_s, 3),
                           "gap_threshold_s": threshold_s}
    out["expected_samples"] = int(round(span / nominal_s)) if nominal_s > 0 else None
    out["sample_fraction"] = (round(min(1.0, len(ts) / out["expected_samples"]), 4)
                              if out["expected_samples"] else None)
    gaps: List[Dict[str, Any]] = []

    def add(a: datetime, b: datetime):
        sec = (b - a).total_seconds()
        if sec > threshold_s:
            gaps.append({"start": _fmt(a), "end": _fmt(b), "minutes": round(sec / 60.0, 1)})

    if not ts:
        add(start, end)
    else:
        add(start, ts[0])
        step = timedelta(seconds=nominal_s)
        for a, b in zip(ts[:-1], ts[1:]):
            add(a + step, b)
        add(min(end, ts[-1] + step), end)
    total = sum(g["minutes"] for g in gaps) * 60.0
    out.update({
        "first_sample": _fmt(ts[0]) if ts else None,
        "last_sample": _fmt(ts[-1]) if ts else None,
        "covered_fraction": round(max(0.0, 1.0 - total / span), 4) if span > 0 else None,
        "gaps": len(gaps),
        "gap_minutes_total": round(total / 60.0, 1),
        "longest_gap": max(gaps, key=lambda g: g["minutes"]) if gaps else None,
        "gap_list": gaps[:max_list],
        "gap_list_truncated": len(gaps) > max_list,
    })
    return out


# Quantities checked in archive records (1-minute means or block averages).
RECORD_GROUPS = {
    "magnetic field": ("bt", "bz_gsm"),
    "plasma": ("speed", "density"),
    "SYM-H": ("sym_h",),
}


def records_coverage(records: Sequence[Dict[str, Any]], start: datetime, end: datetime,
                     cadence_minutes: int = 1) -> Dict[str, Any]:
    """
    Coverage of archive records per group of quantities (a sample counts when any of the
    group's quantities is present); gaps of more than 10 minutes, or two samples at coarser
    cadences, are listed.
    """
    nominal = 60.0 * max(1, cadence_minutes)
    threshold = max(600.0, 2 * nominal)
    out = {"cadence_minutes": cadence_minutes, "gap_threshold_minutes": threshold / 60.0, "groups": {}}
    for name, keys in RECORD_GROUPS.items():
        if not any(k in r for r in records[:50] for k in keys):
            continue  # this archive has no such quantity at all (e.g. SYM-H outside OMNI)
        times = [datetime.strptime(r["time_tag"][:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                 for r in records if any(r.get(k) is not None for k in keys)]
        out["groups"][name] = gap_report(times, start, end, threshold, nominal)
    return out


def frame_coverage(frame, start: datetime, end: datetime, min_threshold_s: float = 60.0) -> Optional[Dict[str, Any]]:
    """
    Coverage of a native-cadence frame (time index, rows with any valid value): gaps longer
    than five nominal sample intervals and at least ``min_threshold_s``.
    """
    if frame is None:
        return None
    if frame.empty:
        return gap_report([], start, end, min_threshold_s, None)
    valid = frame.dropna(how="all")
    times = [t.to_pydatetime() for t in valid.index]
    d = np.diff(valid.index.as_unit("ns").asi8) / 1e9 if len(valid) > 1 else np.array([])
    nominal = float(np.median(d)) if d.size else 60.0
    return gap_report(times, start, end, max(min_threshold_s, 5 * nominal), nominal)


def describe(cov: Optional[Dict[str, Any]]) -> str:
    """One sentence: covered fraction and the longest gap."""
    if not cov:
        return ""
    lg = cov.get("longest_gap")
    s = f"{100 * cov['covered_fraction']:.1f} % covered" if cov.get("covered_fraction") is not None else "no coverage"
    if lg:
        m = lg["minutes"]
        length = f"{m / 1440:.1f} days" if m >= 1440 else (f"{m / 60:.1f} h" if m >= 60 else f"{m:g} min")
        s += f", {cov['gaps']} gap(s), longest {length} from {lg['start']}"
    return s
