"""
Archive solar wind data from NASA CDAWeb through its HAPI server
(Heliophysics Application Programmer's Interface, https://cdaweb.gsfc.nasa.gov/hapi).

Covers WIND (MFI, SWE), ACE (MAG, SWEPAM), OMNI (1-min HRO, time-shifted to the bow
shock nose) and the DSCOVR science archive (magnetometer from 2015, Faraday cup
2016-2019). Dataset IDs and parameter names were checked against the live HAPI catalog.

* Every instrument has an ordered list of datasets: the definitive (Level 2 / H*) one
  first, then preliminary key-parameter (K*) data that reach closer to the present.
  The preferred dataset is used where it has data; the next one only extends it past
  its last sample. The IDs, levels and coverage of the datasets used go into the
  provenance.
* Fill values declared in the HAPI header (e.g. -1e31, 9999.99, 99999.9) and samples
  flagged bad by the instrument team become missing values.
* Data are fetched one UTC day at a time, reduced to 1-minute means and cached as JSON.
  Days that ended more than two days ago and have data are kept for good; recent or
  empty days are re-checked after six hours, because the archive fills in with a delay.
"""
import asyncio
import hashlib
import io
import json
import math
import os
import time
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlencode

import numpy as np
import pandas as pd

from helios.core.coordinates import gse_to_gsm
from helios.config import run_in_workers

HAPI_SERVER = "https://cdaweb.gsfc.nasa.gov/hapi"

PROTON_MASS_KG = 1.67262192369e-27
BOLTZMANN_J_K = 1.380649e-23

RECENT_TTL_SECONDS = 6 * 3600
PERMANENT_AFTER_DAYS = 2
# Part of the day-file cache key: raise it whenever the processing of a day changes (reduce
# functions, quality flags, unit conversions, trimming), or old files are kept for good.
# 2: day files cut to their own day (files from before kept a duplicated minute).
DAY_CACHE_VERSION = 2

STANDARD_COLUMNS = ("density", "speed", "temperature", "bt",
                    "bx_gsm", "by_gsm", "bz_gsm", "bx_gse", "by_gse", "bz_gse")

# Geomagnetic indices carried by OMNI_HRO_1MIN (WDC Kyoto, nT): SYM-H, ASY-H and the
# auroral electrojet indices AE, AL, AU. Copied into records only when present.
INDEX_COLUMNS = ("sym_h", "asy_h", "ae", "al", "au")


class HapiError(Exception):
    """The HAPI server answered with an error status."""


def parse_hapi_csv(text: str) -> pd.DataFrame:
    """
    Parse a HAPI CSV response requested with include=header.

    Returns a DataFrame indexed by UTC time with one column per scalar parameter and
    name_0, name_1, ... for vector parameters, with declared fill values set to NaN.
    An empty frame is returned for HAPI status 1201 ("no data for time range").
    """
    header_lines, body_lines = [], []
    for line in text.splitlines():
        (header_lines if line.startswith("#") else body_lines).append(line)
    body = "\n".join(body_lines).strip()
    if '"status"' in body:  # no-data answers and errors are JSON fragments, not CSV
        if "1201" in body:
            return pd.DataFrame()
        raise HapiError(body[:200])
    if not header_lines:
        raise HapiError("HAPI response without header (request include=header)")
    header = json.loads("\n".join(line[1:] for line in header_lines))
    code = header.get("status", {}).get("code")
    if code not in (None, 1200, 1201):  # a saved file may come without the status
        raise HapiError(str(header.get("status")))

    names, fills = [], []
    for p in header["parameters"]:
        size = p.get("size")
        n = int(size[0]) if size else 1
        cols = [p["name"]] if n == 1 else [f"{p['name']}_{i}" for i in range(n)]
        names.extend(cols)
        fills.extend([p.get("fill")] * n)
    if not body:
        return pd.DataFrame(columns=names[1:])
    df = pd.read_csv(io.StringIO(body), header=None, names=names)
    df.index = pd.to_datetime(df.pop(names[0]), utc=True, format="ISO8601")
    df.index.name = "time"
    for col, fill in zip(names[1:], fills[1:]):
        vals = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float, copy=True)
        bad = ~np.isfinite(vals) | (np.abs(vals) >= 1e30)
        if fill not in (None, "", "NaN", "nan"):
            f = float(fill)
            bad |= np.isclose(vals, f, rtol=1e-7, atol=0.0)
        vals[bad] = np.nan
        df[col] = vals
    return df


# ----------------------------------------------------------------------------
# Instrument-specific reduction to the standard HELIOS columns
# ----------------------------------------------------------------------------
def _vector(df: pd.DataFrame, name: str, prefix: str, out: pd.DataFrame) -> None:
    for i, axis in enumerate("xyz"):
        out[f"b{axis}_{prefix}"] = df[f"{name}_{i}"]


def thermal_speed_to_kelvin(w_kms):
    """Most probable thermal speed W = sqrt(2kT/m_p) (km/s) to proton temperature (K)."""
    w = w_kms if isinstance(w_kms, pd.Series) else np.asarray(w_kms, dtype=float)  # keep a Series a Series
    return PROTON_MASS_KG * (w * 1e3) ** 2 / (2.0 * BOLTZMANN_J_K)


def _mag(bt: str, gsm: Optional[str] = None, gse: Optional[str] = None, flag: Optional[str] = None) -> Callable:
    def reduce(df: pd.DataFrame) -> pd.DataFrame:
        if flag:
            df = df[df[flag] == 0]
        out = pd.DataFrame(index=df.index)
        out["bt"] = df[bt]
        if gsm:
            _vector(df, gsm, "gsm", out)
        if gse:
            _vector(df, gse, "gse", out)
        return out
    return reduce


def _wind_swe_h1(df: pd.DataFrame) -> pd.DataFrame:
    # fit_flag units in the CDF: "10=He_OK, >1=P_OK": proton moments are valid above 1.
    df = df[df["fit_flag"] > 1]
    out = pd.DataFrame(index=df.index)
    out["speed"] = df["Proton_V_nonlin"]
    out["density"] = df["Proton_Np_nonlin"]
    out["temperature"] = thermal_speed_to_kelvin(df["Proton_W_nonlin"])
    return out


def _wind_swe_k0(df: pd.DataFrame) -> pd.DataFrame:
    # QF_V / QF_Np: "0=OK; 2 or 130 = caution; other values NOT VALID". The served values
    # carry extra high bits (e.g. 14338 = 0x3802); the documented code is the low byte.
    ok_v = (df["QF_V"].fillna(-1).astype(np.int64) & 0xFF).isin([0, 2, 130])
    ok_n = (df["QF_Np"].fillna(-1).astype(np.int64) & 0xFF).isin([0, 2, 130])
    out = pd.DataFrame(index=df.index)
    speed = np.sqrt(df["V_GSE_0"] ** 2 + df["V_GSE_1"] ** 2 + df["V_GSE_2"] ** 2)
    out["speed"] = speed.where(ok_v)
    out["density"] = df["Np"].where(ok_n)
    out["temperature"] = thermal_speed_to_kelvin(df["THERMAL_SPD"]).where(ok_v)
    return out


def _ace_swepam(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["speed"] = df["Vp"]
    out["density"] = df["Np"]
    out["temperature"] = df["Tpr"]  # radial proton temperature, as used by NOAA RTSW
    return out


def _dscovr_fc(df: pd.DataFrame) -> pd.DataFrame:
    df = df[df["DQF"] == 0]
    out = pd.DataFrame(index=df.index)
    out["speed"] = np.sqrt(df["V_GSE_0"] ** 2 + df["V_GSE_1"] ** 2 + df["V_GSE_2"] ** 2)
    out["density"] = df["Np"]
    out["temperature"] = df["THERMAL_TEMP"]
    return out


def _soho_pm(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["speed"] = df["V_p"]
    out["density"] = df["N_p"]
    # No temperature: the one from the PM thermal speed was 2-4 times below OMNI's on 17 March
    # 2015, and the live SOHO view shows none either.
    return out


def _stereo_a(df: pd.DataFrame) -> pd.DataFrame:
    # |B| only: the vector is in RTN, which is not GSE/GSM (the views would read it as such).
    out = pd.DataFrame(index=df.index)
    out["bt"] = df["BTOTAL"]
    out["speed"] = df["Vp"]
    out["density"] = df["Np"]
    out["temperature"] = df["Tp"]
    return out


def _omni(df: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=df.index)
    out["bt"] = df["F"]
    out["bx_gse"], out["by_gse"], out["bz_gse"] = df["BX_GSE"], df["BY_GSE"], df["BZ_GSE"]
    out["bx_gsm"], out["by_gsm"], out["bz_gsm"] = df["BX_GSE"], df["BY_GSM"], df["BZ_GSM"]
    out["speed"] = df["flow_speed"]
    out["density"] = df["proton_density"]
    out["temperature"] = df["T"]
    for col, name in zip(INDEX_COLUMNS, ("SYM_H", "ASY_H", "AE_INDEX", "AL_INDEX", "AU_INDEX")):
        out[col] = df[name]
    return out


def _dataset(ds_id: str, params: List[str], reduce: Callable, level: str, label: str) -> Dict[str, Any]:
    return {"id": ds_id, "parameters": params, "reduce": reduce, "level": level, "label": label}


# Per mission: instrument groups, each an ordered list of datasets (preferred first).
ARCHIVE_SOURCES: Dict[str, Dict[str, Any]] = {
    "WIND": {
        "spacecraft": "WIND",
        "groups": [
            [_dataset("WI_H0_MFI@0", ["BF1", "BGSM", "BGSE"], _mag("BF1", "BGSM", "BGSE"),
                      "definitive", "WIND MFI 1-min"),
             _dataset("WI_K0_MFI", ["BF1", "BGSMc", "BGSEc"], _mag("BF1", "BGSMc", "BGSEc"),
                      "key parameters (preliminary)", "WIND MFI key parameters")],
            [_dataset("WI_H1_SWE", ["fit_flag", "Proton_V_nonlin", "Proton_W_nonlin", "Proton_Np_nonlin"],
                      _wind_swe_h1, "definitive", "WIND SWE non-linear proton fits (92 s)"),
             _dataset("WI_K0_SWE", ["QF_V", "QF_Np", "V_GSE", "THERMAL_SPD", "Np"], _wind_swe_k0,
                      "key parameters (preliminary)", "WIND SWE key parameters")],
        ],
    },
    "ACE": {
        "spacecraft": "ACE",
        "groups": [
            [_dataset("AC_H0_MFI", ["Magnitude", "BGSEc", "BGSM"], _mag("Magnitude", "BGSM", "BGSEc"),
                      "Level 2", "ACE MAG 16-s Level 2"),
             _dataset("AC_K1_MFI", ["Magnitude", "BGSEc"], _mag("Magnitude", None, "BGSEc"),
                      "key parameters (preliminary)", "ACE MAG 16-s key parameters")],
            [_dataset("AC_H0_SWE", ["Np", "Vp", "Tpr"], _ace_swepam, "Level 2", "ACE SWEPAM 64-s Level 2"),
             _dataset("AC_K0_SWE", ["Np", "Vp", "Tpr"], _ace_swepam,
                      "key parameters (preliminary)", "ACE SWEPAM 5-min key parameters")],
        ],
    },
    "DSCOVR": {
        "spacecraft": "DSCOVR",
        "groups": [
            [_dataset("DSCOVR_H0_MAG", ["B1F1", "B1GSE", "FLAG1"], _mag("B1F1", None, "B1GSE", "FLAG1"),
                      "Level 2", "DSCOVR MAG 1-s")],
            [_dataset("DSCOVR_H1_FC", ["DQF", "V_GSE", "Np", "THERMAL_TEMP"], _dscovr_fc,
                      "Level 2", "DSCOVR Faraday cup 1-min (2016-2019)")],
        ],
    },
    "SOHO": {
        "spacecraft": "SOHO",
        "groups": [
            [_dataset("SOHO_CELIAS-PM_5MIN", ["V_p", "N_p"], _soho_pm,
                      "definitive", "SOHO CELIAS/MTOF Proton Monitor 5-min (no magnetometer)")],
        ],
    },
    "STEREO_A": {
        "spacecraft": "STEREO_A",
        "groups": [
            [_dataset("STA_L2_MAGPLASMA_1M", ["BTOTAL", "Np", "Vp", "Tp"], _stereo_a,
                      "Level 2", "STEREO-A IMPACT/MAG and PLASTIC 1-min (|B| only: the vector is in RTN)")],
        ],
    },
    "OMNI": {
        "spacecraft": "OMNI",
        "groups": [
            [_dataset("OMNI_HRO_1MIN",
                      ["F", "BX_GSE", "BY_GSE", "BZ_GSE", "BY_GSM", "BZ_GSM", "flow_speed", "proton_density", "T",
                       "AE_INDEX", "AL_INDEX", "AU_INDEX", "SYM_H", "ASY_H"],  # HAPI order
                      _omni, "definitive", "OMNI 1-min, time-shifted to the bow shock nose, with SYM-H, ASY-H, AE, AL, AU")],
        ],
    },
}


def hapi_data_url(ds_id: str, parameters: List[str], start: datetime, stop: datetime) -> str:
    query = urlencode({
        "id": ds_id,
        "parameters": ",".join(parameters),
        "time.min": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "time.max": stop.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "include": "header",
    })
    return f"{HAPI_SERVER}/data?{query}"


def to_minute_means(df: pd.DataFrame) -> pd.DataFrame:
    """1-minute means (bins labelled by their start); empty bins are dropped."""
    if df.empty:
        return df
    return df.resample("60s", label="left", closed="left").mean().dropna(how="all")


# ----------------------------------------------------------------------------
# Day cache
# ----------------------------------------------------------------------------
def _frame_to_json(df: pd.DataFrame) -> Dict[str, Any]:
    cols = list(df.columns)
    rows = [[None if (v is None or (isinstance(v, float) and math.isnan(v))) else round(float(v), 4) for v in row]
            for row in df.itertuples(index=False, name=None)]
    return {"columns": cols, "index": [int(t.timestamp()) for t in df.index], "rows": rows}


def _frame_from_json(obj: Dict[str, Any]) -> pd.DataFrame:
    idx = pd.to_datetime(obj.get("index", []), unit="s", utc=True)
    df = pd.DataFrame(obj.get("rows", []), columns=obj.get("columns", []), index=idx, dtype=float)
    df.index.name = "time"
    return df


class ArchiveClient:
    """
    Fetches and caches CDAWeb HAPI data. `fetch_text(url)` is an async callable that
    returns the response body, or None on any network / HTTP failure.
    """

    def __init__(self, fetch_text: Callable, cache_dir: str):
        self.fetch_text = fetch_text
        self.cache_dir = os.path.join(str(cache_dir), "hapi")
        os.makedirs(self.cache_dir, exist_ok=True)

    def _cache_path(self, spec: Dict[str, Any], day: datetime) -> str:
        # The parameter list and DAY_CACHE_VERSION are part of the key: adding parameters or
        # changing the processing must not serve day files cached (and kept for good) without it.
        safe = spec["id"].replace("@", "_at")
        key = ",".join(spec["parameters"]) + f"|v{DAY_CACHE_VERSION}"
        tag = hashlib.sha1(key.encode("ascii")).hexdigest()[:8]
        return os.path.join(self.cache_dir, f"{safe}_{tag}_{day:%Y%m%d}.json")

    @staticmethod
    def _cache_is_fresh(path: str, day: datetime, has_rows: bool) -> bool:
        # Kept for good only if written when the day was complete: a file fetched while the
        # day was still being filled used to become permanent once the day itself was old.
        written_after_days = (os.path.getmtime(path) - (day + timedelta(days=1)).timestamp()) / 86400.0
        if has_rows and written_after_days > PERMANENT_AFTER_DAYS:
            return True
        return (time.time() - os.path.getmtime(path)) < RECENT_TTL_SECONDS

    async def fetch_day(self, spec: Dict[str, Any], day: datetime) -> Optional[pd.DataFrame]:
        """1-minute means of one dataset for one UTC day; None if it could not be retrieved."""
        path = self._cache_path(spec, day)
        cached = None
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cached = _frame_from_json(json.load(f))
            except (OSError, ValueError, KeyError, TypeError):  # unreadable or old-format cache file
                cached = None
            if cached is not None and self._cache_is_fresh(path, day, not cached.empty):
                return cached

        text = await self.fetch_text(hapi_data_url(spec["id"], spec["parameters"], day, day + timedelta(days=1)))
        if text is None:
            return cached  # offline: stale cache, or None
        def decode():
            raw = parse_hapi_csv(text)
            return to_minute_means(spec["reduce"](raw)) if not raw.empty else pd.DataFrame()

        try:
            # A DSCOVR magnetometer day is 86,400 rows: decode it in a worker thread.
            frame = await run_in_workers(decode)
        except (HapiError, KeyError, ValueError):
            return cached
        if not frame.empty:
            # HAPI can return a sample just before time.min (WIND SWE, 17 March 1997 starts with
            # 16 March 23:58), which duplicated that minute of the previous day's file and made
            # the merge of the instrument groups fail.
            frame = frame[(frame.index >= pd.Timestamp(day)) & (frame.index < pd.Timestamp(day + timedelta(days=1)))]
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(_frame_to_json(frame), f)
        os.replace(tmp, path)
        return frame

    async def fetch_dataset(self, spec: Dict[str, Any], start: datetime, end: datetime) -> Tuple[Optional[pd.DataFrame], int]:
        """Concatenated 1-minute means over [start, end); (None, n_days) if nothing could be retrieved."""
        day0 = start.replace(hour=0, minute=0, second=0, microsecond=0)
        days = []
        d = day0
        while d < end:
            days.append(d)
            d += timedelta(days=1)
        sem = asyncio.Semaphore(4)

        async def one(day):
            async with sem:
                return await self.fetch_day(spec, day)

        frames = await asyncio.gather(*(one(day) for day in days))
        got = [f for f in frames if f is not None]
        failed = len(frames) - len(got)
        if not got:
            return None, failed
        nonempty = [f for f in got if not f.empty]
        if not nonempty:
            return pd.DataFrame(), failed
        df = pd.concat(nonempty).sort_index()
        df = df[(df.index >= pd.Timestamp(start)) & (df.index < pd.Timestamp(end))]
        # Day files cached before fetch_day clipped them can still hold a stray minute of the day before.
        return df[~df.index.duplicated(keep="first")], failed

    async def fetch_mission(self, mission: str, start: datetime, end: datetime) -> Dict[str, Any]:
        """
        Merged 1-minute frame for a mission over [start, end) plus the datasets used.
        Returns {"frame": DataFrame (possibly empty), "datasets": [...], "offline": bool,
        "failed_days": int}.
        """
        groups = ARCHIVE_SOURCES[mission]["groups"]

        async def pick(group):
            """Preferred dataset first; later (preliminary) datasets only extend it past its last sample."""
            parts, used, failed_total, reached = [], [], 0, False
            last = None
            for spec in group:
                df, failed = await self.fetch_dataset(spec, start, end)
                failed_total += failed
                if df is None:
                    continue
                reached = True
                if last is not None:
                    df = df[df.index > last]
                if df.empty:
                    continue
                parts.append(df)
                used.append({"id": spec["id"], "level": spec["level"], "label": spec["label"],
                             "coverage_start": df.index[0].strftime("%Y-%m-%d %H:%M:%S"),
                             "coverage_end": df.index[-1].strftime("%Y-%m-%d %H:%M:%S")})
                last = df.index[-1]
                if last >= pd.Timestamp(end) - pd.Timedelta(hours=1):
                    break  # covers the interval: no need for preliminary data
            frame = pd.concat(parts).sort_index() if parts else pd.DataFrame()
            return frame, used, failed_total, reached

        results = await asyncio.gather(*(pick(g) for g in groups))
        frames = [df for df, _, _, _ in results if not df.empty]
        # Instrument groups have disjoint columns; an outer join keeps every minute of either.
        frame = pd.concat(frames, axis=1).sort_index() if frames else pd.DataFrame()
        return {"frame": frame, "datasets": [u for _, used, _, _ in results for u in used],
                "offline": not any(r for _, _, _, r in results),
                "failed_days": sum(f for _, _, f, _ in results)}


def frame_to_records(frame: pd.DataFrame, mission_label: str, add_derived: Callable,
                     distance_km: Optional[float]) -> List[Dict[str, Any]]:
    """
    Telemetry records from a merged 1-minute frame. GSM components are computed from GSE
    (core.coordinates) where a dataset only provides GSE, |B| from the components where
    no magnitude was measured, and the derived quantities are filled in.
    """
    if frame is None or frame.empty:
        return []
    df = frame.copy()
    for col in STANDARD_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    need = df["bz_gsm"].isna() & df["bz_gse"].notna() & df["by_gse"].notna()
    if need.any():
        sub = df.loc[need]
        _, gy, gz = gse_to_gsm(sub.index.to_numpy(), sub["bx_gse"], sub["by_gse"], sub["bz_gse"])
        df.loc[need, "by_gsm"] = gy
        df.loc[need, "bz_gsm"] = gz
    df["bx_gsm"] = df["bx_gsm"].fillna(df["bx_gse"])
    comp = np.sqrt(df["bx_gsm"] ** 2 + df["by_gsm"] ** 2 + df["bz_gsm"] ** 2)
    df["bt"] = df["bt"].fillna(comp)

    digits = {"density": 2, "speed": 1, "temperature": 0}
    records = []
    times = df.index.strftime("%Y-%m-%d %H:%M:%S")
    values = {c: df[c].to_numpy(dtype=float) for c in STANDARD_COLUMNS}
    index_cols = [c for c in INDEX_COLUMNS if c in df.columns]
    index_values = {c: df[c].to_numpy(dtype=float) for c in index_cols}
    for i, t in enumerate(times):
        rec: Dict[str, Any] = {"time_tag": t, "mission": mission_label}
        for c in STANDARD_COLUMNS:
            v = values[c][i]
            rec[c] = None if not np.isfinite(v) else round(float(v), digits.get(c, 2))
        rec["data_source"] = "observed"
        for c in index_cols:
            v = index_values[c][i]
            rec[c] = None if not np.isfinite(v) else round(float(v), 1)
        records.append(add_derived(rec, distance_km))
    return records
