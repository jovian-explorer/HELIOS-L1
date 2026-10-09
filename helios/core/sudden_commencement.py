"""
Sudden commencements (SC) in 1-minute SYM-H, and the lists of the International Service on
Rapid Magnetic Variations (Observatori de l'Ebre, for ISGI) to compare them with.

Detection (an empirical rule set of this application, not a published method):

1. SYM-H rises by at least 10 nT within 4 minutes, with a 1-minute step of at least 2 nT;
   candidate minutes less than 10 minutes apart form one event.
2. The onset is the first minute whose increase to the next is at least 1 nT and 10 % of
   the rise; the amplitude is the highest SYM-H in the 10 minutes after the onset minus
   SYM-H at the onset (at least 10 nT), the rise time the minutes between them. The rise
   holds a 1-minute step of at least 4 nT (the Ebre lists ask for 3 nT/min at
   low-latitude observatories).
3. The record before is quiet: the median absolute 1-minute change of SYM-H over the hour
   before the onset is at most 0.5 nT, or the largest step of the rise is at least 20 times
   that median. (Small steps in a disturbed record cannot be told from other variations;
   the Ebre lists, made by eye from magnetograms, rarely list them.)
4. The step persists: SYM-H over the 15 minutes from the peak stays on average at least
   half the amplitude above the onset value.
5. The solar wind pushed: OMNI's flow pressure (shifted to the bow shock nose) over the
   hour from the onset is at least 1.5 times its value 60 to 10 minutes before (medians of
   at least 10 valid minutes each). The hour-long windows absorb OMNI time-shift errors of
   tens of minutes. Events without pressure data are kept and marked.

Validation against the Ebre lists 1995-2024 (OMNI_HRO_1MIN SYM_H and Pressure from CDAWeb;
a listed SC counts as found with an onset within 3 minutes; the thresholds of rules 2 to 5
were chosen on the odd years, the even years held out): VALIDATION below. Detections
not in the lists include SYM-H steps under a fast forward interplanetary shock at L1 in the
IPShocks database (Zenodo doi:10.5281/zenodo.19730292, CC BY 4.0); the lists leave out
many clear steps.

The Ebre lists (https://obsebre.es/en/variations/rapid; definitive to 2022 at the time of
writing, preliminary since) are distributed under the Creative Commons
Attribution-NonCommercial 4.0 licence: they are read from the observatory when asked for
and cached, not bundled.
"""
from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional

import numpy as np
import pandas as pd

RISE_WINDOW_MIN = 4
MIN_RISE_NT = 10.0
MIN_STEP_NT = 2.0
MIN_MAX_STEP_NT = 4.0
GROUP_GAP_MIN = 10
PEAK_WINDOW_MIN = 10
MAX_QUIET_NT = 0.5
QUIET_STEP_RATIO = 20.0
QUIET_WINDOW_MIN = 60
MIN_PERSISTENCE = 0.5
PERSIST_WINDOW_MIN = 15
PRESSURE_BEFORE_MIN = (-60, -10)
PRESSURE_AFTER_MIN = (0, 60)
MIN_PRESSURE_MINUTES = 10
MIN_PRESSURE_RATIO = 1.5
MATCH_TOLERANCE_MIN = 3.0
# Data needed around an onset: the quiet hour and the pressure before it, the peak, the
# persistence window and the pressure hour after it.
MARGIN_BEFORE_MIN = 60
MARGIN_AFTER_MIN = 60

METHOD = ("SYM-H rise >= 10 nT within 4 min (onset at the first 1-min increase >= 1 nT and 10 % of the rise, "
          "a >= 4 nT 1-min step in the rise); quiet hour before (median |dSYM-H| <= 0.5 nT/min, or the largest step "
          ">= 20 times it); step persisting (15-min mean from the peak >= 50 % of the amplitude); OMNI flow pressure "
          "up by >= 50 % (median of the hour from the onset against 60-10 min before)")
VALIDATION = {
    "reference": "Ebre lists 1995-2024 (definitive to 2022, preliminary 2023-2024)",
    "listed": 566, "found": 420, "hit_rate": 0.74,
    "detections": 663, "not_listed": 243, "false_alarm_ratio": 0.37,
    "not_listed_without_ipshocks_shock": 181, "false_alarm_ratio_without_shocks": 0.27,
    "held_out_even_years": {"listed": 277, "found": 209, "detections": 318, "not_listed": 109},
    "found_by_listed_amplitude": {"above 15 nT": "316/349", "10-15 nT": "86/146", "up to 10 nT": "18/71"},
    "tolerance_minutes": MATCH_TOLERANCE_MIN,
}

OMNI_SPEC = {"id": "OMNI_HRO_1MIN", "parameters": ["Pressure", "SYM_H"],  # HAPI order
             "reduce": lambda df: df[["SYM_H", "Pressure"]].rename(columns={"SYM_H": "sym_h", "Pressure": "pressure"}),
             "label": "OMNI HRO 1-min: SYM-H (WDC Kyoto) and flow pressure at the bow shock nose"}

EBRE_URL = "https://obsebre.es/php/geomagnetisme/vrapides/ssc_{year}_{kind}.txt"
EBRE_FIRST_YEAR = 1868
PRELIMINARY_MAX_AGE_S = 7 * 24 * 3600
EBRE_SOURCE = {
    "name": "Sudden commencements of the International Service on Rapid Magnetic Variations "
            "(Observatori de l'Ebre, for ISGI)",
    "url": "https://obsebre.es/en/variations/rapid",
    "licence": "CC BY-NC 4.0",
    "acknowledgement": "Lists of the International Service on Rapid Magnetic Variations, Observatori de l'Ebre, "
                       "for ISGI; observatory data from INTERMAGNET",
}
COLUMNS = ["time", "amplitude_nt", "rise_minutes", "max_step_nt", "symh_nt", "quiet_nt", "persistence",
           "pressure_before_npa", "pressure_after_npa", "pressure_ratio", "pressure_jump"]


def _minutes(series: pd.Series, index: pd.DatetimeIndex) -> np.ndarray:
    s = series.astype(float)
    return s.groupby(s.index.floor("min")).mean().reindex(index).to_numpy()


def detect(symh: pd.Series, pressure: Optional[pd.Series] = None) -> pd.DataFrame:
    """
    Sudden commencements in a 1-minute SYM-H series (index: UTC). `pressure` (nPa, any
    index) is OMNI's flow pressure; without it no event is confirmed or rejected by rule 5.
    Columns: COLUMNS (time: the onset minute; pressure_jump True, or None without data).
    """
    symh = symh.dropna()
    if len(symh) < RISE_WINDOW_MIN + 2:
        return pd.DataFrame(columns=COLUMNS)
    full = pd.date_range(symh.index[0].floor("min"), symh.index[-1].floor("min"), freq="min")
    v = _minutes(symh, full)
    n = len(v)
    d = np.full(n, np.nan)
    d[1:] = np.diff(v)                         # d[m] = v[m] - v[m-1]
    rise = np.full(n, np.nan)
    rise[:-RISE_WINDOW_MIN] = v[RISE_WINDOW_MIN:] - v[:-RISE_WINDOW_MIN]
    step = np.full(n, -np.inf)
    for k in range(1, RISE_WINDOW_MIN + 1):    # largest 1-min step in (t, t + window]
        shifted = np.full(n, np.nan)
        shifted[:-k] = d[k:]
        step = np.fmax(step, shifted)
    with np.errstate(invalid="ignore"):
        cand = np.where((rise >= MIN_RISE_NT) & (step >= MIN_STEP_NT))[0]
    groups: List[List[int]] = []
    for i in cand:
        if groups and i - groups[-1][-1] <= GROUP_GAP_MIN:
            groups[-1].append(i)
        else:
            groups.append([i])
    pv = _minutes(pressure, full) if pressure is not None else None

    def median(a: int, b: int) -> float:
        w = pv[max(0, a):max(0, b)]
        return float(np.nanmedian(w)) if np.isfinite(w).sum() >= MIN_PRESSURE_MINUTES else np.nan

    events = []
    for g in groups:
        i0, i1 = g[0], g[-1]
        amp0 = np.nanmax(v[i0:min(n, i1 + RISE_WINDOW_MIN + 1)]) - v[i0]
        j = i0
        for m in range(i0, min(n - 1, i1 + RISE_WINDOW_MIN)):
            if v[m + 1] - v[m] >= max(1.0, 0.1 * amp0):
                j = m
                break
        window = v[j:min(n, j + PEAK_WINDOW_MIN + 1)]
        if not np.isfinite(v[j]) or not np.isfinite(window).any():
            continue
        top = j + int(np.nanargmax(window))
        amp = float(v[top] - v[j])
        max_step = float(np.nanmax(np.diff(v[j:top + 1]))) if top > j else np.nan
        quiet = d[max(1, j - QUIET_WINDOW_MIN):j]  # the changes over the hour up to the onset minute
        quiet_nt = float(np.nanmedian(np.abs(quiet))) if np.isfinite(quiet).sum() >= QUIET_WINDOW_MIN // 2 else np.nan
        after = v[top:min(n, top + PERSIST_WINDOW_MIN + 1)]
        persistence = float((np.nanmean(after) - v[j]) / amp) if amp > 0 and np.isfinite(after).any() else np.nan
        quiet_ok = quiet_nt <= MAX_QUIET_NT or max_step >= QUIET_STEP_RATIO * quiet_nt
        if not (amp >= MIN_RISE_NT and max_step >= MIN_MAX_STEP_NT and quiet_ok and persistence >= MIN_PERSISTENCE):
            continue
        pb = pa = ratio = np.nan
        jump: Optional[bool] = None
        if pv is not None:
            pb, pa = median(j + PRESSURE_BEFORE_MIN[0], j + PRESSURE_BEFORE_MIN[1]), median(j, j + PRESSURE_AFTER_MIN[1])
            if np.isfinite(pb) and np.isfinite(pa) and pb > 0:
                ratio = pa / pb
                jump = bool(ratio >= MIN_PRESSURE_RATIO)
        if jump is False:
            continue
        events.append({"time": full[j], "amplitude_nt": amp, "rise_minutes": int(top - j), "max_step_nt": max_step,
                       "symh_nt": float(v[j]), "quiet_nt": quiet_nt, "persistence": persistence,
                       "pressure_before_npa": pb, "pressure_after_npa": pa, "pressure_ratio": ratio,
                       "pressure_jump": jump})
    return pd.DataFrame(events, columns=COLUMNS)


_LINE = re.compile(r"^\s*(\d{4})\s+(\d{1,2})\s+(\d{1,2})\s+(\d{1,2})\s+(\d+(?:\.\d+)?)\s+(.*)$")


def parse_ebre(text: str) -> List[Dict[str, Any]]:
    """
    Events of an Ebre SC list (one year): time (UTC, to 0.1 min), type (SSC, SI, SI- since
    2006; SC before) and the mean amplitude (nT) at the five low-latitude observatories (one
    value before 2005). Lines that are not events (titles, observatory codes, notes) are skipped.
    """
    events = []
    for line in text.splitlines():
        m = _LINE.match(line)
        if not m:
            continue
        year, month, day, hour, minute = int(m[1]), int(m[2]), int(m[3]), int(m[4]), float(m[5])
        if not (1 <= month <= 12 and 1 <= day <= 31 and hour <= 24 and minute < 60):
            continue
        tokens = m[6].split()
        numbers = []
        for tok in tokens:
            try:
                numbers.append(float(tok))
            except ValueError:
                break
        kind = tokens[-1] if tokens and tokens[-1].upper().startswith(("SSC", "SI")) else "SC"
        if len(numbers) >= 10:          # 2005 on: 5 rise times, 5 amplitudes, ...
            amplitude = float(np.mean(numbers[5:10]))
        elif len(numbers) >= 2:         # 1995-2004: duration, amplitude, ...
            amplitude = numbers[1]
        else:
            continue
        t = pd.Timestamp(year, month, day, tz="UTC") + pd.Timedelta(hours=hour, minutes=minute)
        events.append({"time": t, "type": kind.upper(), "amplitude_nt": round(amplitude, 1)})
    return events


def cross_match(events: pd.DataFrame, listed: List[Dict[str, Any]], tolerance_min: float = MATCH_TOLERANCE_MIN):
    """
    For each detected event the nearest listed SC (or SI) within `tolerance_min` (None when
    there is none), and the listed positive events (SSC, SI, SC) with no detection that close.
    """
    matches, used = [], set()
    for t in (events["time"] if len(events) else []):
        best = None
        for k, e in enumerate(listed):
            dt = (e["time"] - t).total_seconds() / 60.0
            if abs(dt) <= tolerance_min and (best is None or abs(dt) < abs(best[1])):
                best = (k, dt)
        if best is None:
            matches.append(None)
        else:
            used.add(best[0])
            e = listed[best[0]]
            matches.append({"time": e["time"].strftime("%Y-%m-%d %H:%M:%S"), "type": e["type"],
                            "amplitude_nt": e["amplitude_nt"], "offset_minutes": round(-best[1], 1) + 0.0})
    missed = [e for k, e in enumerate(listed) if k not in used and not e["type"].endswith("-")]
    return matches, missed


def _valid_list(text: Optional[str], year: int) -> bool:
    return bool(text) and re.match(rf"\s*(<pre>\s*)?SC\s+{year}\b", text) is not None


async def load_ebre(fetch_text: Callable, cache_dir: Path, years: Iterable[int]) -> Dict[str, Any]:
    """
    The Ebre lists of `years`: {"events": [...], "years": {year: "definitive", "preliminary"
    or None}}. Definitive lists (ssc_YYYY_d.txt) are cached for good; preliminary ones (_p,
    the recent years) for a week, after which the definitive list is looked for again. None:
    not readable (offline and not cached, or not published). `fetch_text(url)` returns the
    body or None.
    """
    folder = Path(cache_dir) / "catalogs"
    events: List[Dict[str, Any]] = []
    kinds: Dict[int, Optional[str]] = {}
    for year in years:
        text, kind = None, None
        paths = {k: folder / f"ebre_ssc_{year}_{k}.txt" for k in "dp"}
        fresh_p = paths["p"].exists() and time.time() - paths["p"].stat().st_mtime < PRELIMINARY_MAX_AGE_S
        if paths["d"].exists():
            text, kind = paths["d"].read_text(encoding="utf-8"), "d"
        elif fresh_p:
            text, kind = paths["p"].read_text(encoding="utf-8"), "p"
        elif year >= EBRE_FIRST_YEAR:
            for k in "dp":
                body = await fetch_text(EBRE_URL.format(year=year, kind=k))
                if _valid_list(body, year):
                    folder.mkdir(parents=True, exist_ok=True)
                    paths[k].write_text(body, encoding="utf-8")
                    if k == "d" and paths["p"].exists():
                        paths["p"].unlink()
                    text, kind = body, k
                    break
            if text is None and paths["p"].exists():   # offline: the last preliminary list
                text, kind = paths["p"].read_text(encoding="utf-8"), "p"
        kinds[year] = {"d": "definitive", "p": "preliminary"}.get(kind)
        if text is not None:
            events.extend(parse_ebre(text))
    return {"events": sorted(events, key=lambda e: e["time"]), "years": kinds}
