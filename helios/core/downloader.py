"""
Data acquisition and caching engine for Sun-Earth L1 and heliospheric missions.
Supports NOAA SWPC Real-Time Solar Wind (RTSW) telemetry, NASA CDAWeb archive data
through HAPI (WIND, ACE, DSCOVR, OMNI; see core.archive), GOES X-ray / proton and
planetary Kp indices, and
historical space weather events (real OMNI data where it exists).

Every record carries a "data_source" label ("observed"; imported files "imported")
and every bundle a provenance description, so measured and modelled values can
never be confused downstream (plots, exports, reports).
"""
import os
import json
import logging
import time
import re
import math
import asyncio
import functools
import gzip
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import httpx

from helios.config import CACHE_DIR, NOAA_SWPC_ENDPOINTS, MISSIONS
from helios.core.cache import cached_text
from helios.core.science import SpaceWeatherPhysics
from helios.core.aurora_model import AuroralModel
from helios.core.coverage import describe as describe_coverage, records_coverage
from helios.core.archive import ARCHIVE_SOURCES, AWAY_FROM_L1, HAPI_SERVER, INDEX_COLUMNS, ArchiveClient, frame_to_records
from helios.core.omni_statistics import OmniHourlyClient
from helios.core.event_analysis import EventDataClient

# Primary plasma / field quantities carried by telemetry records.
PRIMARY_FIELDS = ("density", "speed", "temperature", "bx_gsm", "by_gsm", "bz_gsm", "bt",
                  "bx_gse", "by_gse", "bz_gse")

# Missions that have their own "source"-tagged rows in the NOAA RTSW feed.
RTSW_SOURCES = {"DSCOVR": "DSCOVR", "ACE": "ACE"}

# RTSW records older than this are flagged as not current (the feed normally lags minutes).
STALE_AFTER_HOURS = 0.5


# SOHO CELIAS/MTOF Proton Monitor near-real-time solar wind (University of Maryland): the last
# two days at about 2-minute cadence, speed and density (SOHO has no magnetometer).
SOHO_PM_URL = "https://space.umd.edu/pm/pmsw.used"
SOHO_PM_TTL_S = 120.0


def parse_soho_pm(text: Optional[str]) -> List[Dict[str, Any]]:
    """Rows 'Year DOY:HH:MM:SS VSW Dens Vth Angle PM_Min PM_Max [F]' as records; flagged rows (F) and
    non-positive values are left out."""
    out = []
    for line in (text or "").splitlines():
        parts = line.split()
        if len(parts) != 8 or not parts[0].isdigit():
            continue
        try:
            doy, hms = parts[1].split(":", 1)
            t = datetime(int(parts[0]), 1, 1, tzinfo=timezone.utc) + timedelta(days=int(doy) - 1)
            h, m, sec = (int(x) for x in hms.split(":"))
            t = t.replace(hour=h, minute=m, second=sec)
            v, n = float(parts[2]), float(parts[3])
        except ValueError:
            continue
        if v > 0 and n > 0:
            out.append({"time_tag": t.strftime("%Y-%m-%d %H:%M:%S"), "mission": "SOHO", "source_spacecraft": "SOHO",
                        "speed": v, "density": n, "temperature": None, "bt": None, "bx_gsm": None,
                        "by_gsm": None, "bz_gsm": None, "data_source": "observed"})
    return out


# STEREO-A space weather beacon (STEREO Science Center): daily CDF files of IMPACT (magnetic field,
# RTN) and PLASTIC (proton speed and density), updated through the day.
STA_BEACON = "https://stereo-ssc.nascom.nasa.gov/data/beacon/ahead"
STA_BEACON_TTL_S = 600.0


def parse_stereo_beacon(impact_path: Optional[str], plastic_path: Optional[str]) -> List[Dict[str, Any]]:
    """Records from one day's beacon files: |B| from IMPACT and speed and density from PLASTIC (fill
    values left out). The field components are in RTN at STEREO-A, far from Earth, so no GSM
    components are given."""
    import cdflib
    import numpy as np
    out: List[Dict[str, Any]] = []

    def stamps(cdf, var):
        return [str(t)[:19].replace("T", " ") for t in cdflib.cdfepoch.to_datetime(cdf.varget(var))]

    base = {"mission": "STEREO-A", "source_spacecraft": "STEREO-A", "data_source": "observed",
            "bx_gsm": None, "by_gsm": None, "bz_gsm": None, "temperature": None}
    if impact_path:
        c = cdflib.CDF(impact_path)
        b = np.asarray(c.varget("MAGBField"), dtype=float)
        for t, (br, bt_, bn) in zip(stamps(c, "Epoch_MAG"), b):
            if max(abs(br), abs(bt_), abs(bn)) < 1e4:
                out.append({**base, "time_tag": t, "bt": float(np.sqrt(br * br + bt_ * bt_ + bn * bn))})
    if plastic_path:
        c = cdflib.CDF(plastic_path)
        for t, n, v in zip(stamps(c, "Epoch1"), c.varget("Density"), c.varget("Bulk_Speed")):
            if 0 < v < 3000 and 0 < n < 1000:
                out.append({**base, "time_tag": t, "speed": float(v), "density": float(n)})
    return sorted(out, key=lambda r: r["time_tag"])


class UnknownEventError(LookupError):
    """No historical event with that id."""


# UTC windows for the historical events covered by OMNI: 48 h around the shock arrival;
# Halloween 2003 runs to 31 Oct 06 UT to include the second CME and the Dst minimum
# (-383 nT at 22 UT on 30 Oct); the quiet baseline is 6-8 Dec 2019 (GFZ Kp <= 1- throughout).
EVENT_WINDOWS = {
    "may_2024_g5": ("2024-05-10 06:00", "2024-05-12 06:00"),
    "st_patricks_2015": ("2015-03-16 12:00", "2015-03-18 12:00"),
    "halloween_2003": ("2003-10-28 12:00", "2003-10-31 06:00"),
    "bastille_2000": ("2000-07-14 12:00", "2000-07-16 12:00"),
    "quebec_1989": ("1989-03-12 12:00", "1989-03-14 12:00"),
    "quiet_baseline": ("2019-12-06 12:00", "2019-12-08 12:00"),
}

# The same OMNI intervals as fetched from CDAWeb (scripts/update_omni_events.py), used offline.
OMNI_SNAPSHOT = Path(__file__).resolve().parent.parent / "data" / "omni_events.json.gz"
SNAPSHOT_COLUMNS = ["time_tag", "density", "speed", "temperature", "bx_gsm", "by_gsm", "bz_gsm", "bt",
                    "bx_gse", "by_gse", "bz_gse", "sym_h", "asy_h", "ae", "al", "au"]

@functools.lru_cache(maxsize=None)
def _omni_snapshot_all() -> Dict[str, Any]:
    return json.loads(gzip.decompress(OMNI_SNAPSHOT.read_bytes()))


def omni_snapshot(event_id: str) -> Dict[str, Any]:
    """Bundled OMNI data of one event: {"provenance", "columns", "rows"}."""
    return _omni_snapshot_all()[event_id]



def _num(value) -> Optional[float]:
    """Float conversion that maps None, blanks, NaN and non-numeric values to None."""
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def _iso_space(time_tag: str) -> str:
    """'2026-10-02T18:02:00.000Z' -> '2026-10-02 18:02:00' (UTC, second precision)."""
    return str(time_tag).replace("T", " ").replace("Z", "")[:19]


def add_derived_fields(rec: Dict[str, Any], distance_km: Optional[float] = 1500000.0) -> Dict[str, Any]:
    """
    Fill the derived quantities of a telemetry record from its primary fields.
    A derived value whose inputs are missing is None (a data gap), never a default.
    distance_km=None (data already propagated to Earth, e.g. OMNI) leaves the travel time empty.
    """
    dens, spd = rec.get("density"), rec.get("speed")
    bt, by, bz = rec.get("bt"), rec.get("by_gsm"), rec.get("bz_gsm")
    p_dyn = SpaceWeatherPhysics.dynamic_pressure(dens, spd) if (dens and spd and dens > 0 and spd > 0) else None
    rec["dynamic_pressure"] = round(p_dyn, 3) if p_dyn is not None else None
    rec["magnetopause_re"] = (SpaceWeatherPhysics.magnetopause_standoff(p_dyn, bz)
                              if (p_dyn is not None and bz is not None) else None)
    rec["akasofu_gw"] = (round(SpaceWeatherPhysics.akasofu_epsilon(spd, bt, by, bz), 2)
                         if (spd and bt is not None and by is not None and bz is not None) else None)
    rec["l1_travel_time_min"] = (SpaceWeatherPhysics.propagation_delay_minutes(distance_km, spd)
                                 if (spd and spd > 0 and distance_km is not None) else None)
    return rec


def block_average(records: List[Dict[str, Any]], minutes: int = 5,
                  distance_km: Optional[float] = 1500000.0) -> List[Dict[str, Any]]:
    """
    Average records onto a regular `minutes` grid (time stamps mark bin starts).
    Primary quantities are averaged and the nonlinear derived quantities are recomputed
    from the averages; empty bins are dropped. Unlike keeping every n-th sample this
    does not alias sub-bin fluctuations into the result.
    """
    if not records:
        return []
    import pandas as pd
    df = pd.DataFrame(records)
    df["_t"] = pd.to_datetime(df["time_tag"])
    cols = [c for c in PRIMARY_FIELDS + INDEX_COLUMNS if c in df.columns]
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    binned = df.set_index("_t")[cols].resample(f"{int(minutes)}min").mean().dropna(how="all")
    # Text fields (mission, data source, source spacecraft) per bin, from its last record: the
    # first record's labels used to be stamped on every bin, e.g. after a change of the
    # operational spacecraft or on the RTSW tail after archive bins.
    str_cols = [c for c in df.columns if c not in cols and c not in ("time_tag", "_t")
                and df[c].map(lambda v: isinstance(v, str)).any()]
    labels = df.set_index("_t")[str_cols].resample(f"{int(minutes)}min").last()
    out = []
    for t, row in binned.iterrows():
        rec = {c: v for c, v in labels.loc[t].items() if isinstance(v, str)} if str_cols else {}
        rec["time_tag"] = t.strftime("%Y-%m-%d %H:%M:%S")
        for c in cols:
            v = row[c]
            rec[c] = round(float(v), 3) if pd.notna(v) else None
        out.append(add_derived_fields(rec, distance_km))
    return out


def infer_cadence_seconds(records: List[Dict[str, Any]], default: float = 60.0) -> float:
    """Median spacing of the record time stamps, in seconds."""
    if not records or len(records) < 2:
        return default
    try:
        import pandas as pd
        t = pd.to_datetime([r["time_tag"] for r in records])
        diffs = pd.Series(t).diff().dt.total_seconds().dropna()
        diffs = diffs[diffs > 0]
        return float(diffs.median()) if len(diffs) else default
    except (KeyError, TypeError, ValueError):  # missing or unreadable time tags
        return default


def regular_series(records: List[Dict[str, Any]], key: str, dt_seconds: float) -> List[Optional[float]]:
    """
    Values of `key` on a regular dt_seconds grid spanning the records, with None where a
    sample is missing (either a null value or a missing row). Needed for spectral analysis,
    which assumes even sampling.
    """
    if not records:
        return []
    import pandas as pd
    df = pd.DataFrame(records)
    if key not in df.columns:
        return []
    series = pd.Series(pd.to_numeric(df[key], errors="coerce").to_numpy(),
                       index=pd.to_datetime(df["time_tag"])).sort_index()
    series = series[~series.index.duplicated(keep="last")]
    gridded = series.resample(f"{max(1, int(round(dt_seconds)))}s").mean()
    return [None if pd.isna(v) else float(v) for v in gridded.to_numpy()]


_SSL_CONTEXT = None


def _ssl_context():
    """
    One TLS context for every request. Building it loads the CA bundle (~0.35 s on
    Windows); creating it per httpx client blocked the event loop for seconds when a
    view started a dozen downloads at once.
    """
    global _SSL_CONTEXT
    if _SSL_CONTEXT is None:
        _SSL_CONTEXT = httpx.create_ssl_context()
    return _SSL_CONTEXT


def _decode_and_store(body: bytes, cache_path: str) -> Any:
    """Parse a JSON body and write the original bytes to the cache (atomically). Runs in a thread."""
    data = json.loads(body)
    # Atomic replace so an interrupted write never leaves a truncated cache file.
    tmp_path = cache_path + ".tmp"
    with open(tmp_path, "wb") as f:
        f.write(body)
    os.replace(tmp_path, cache_path)
    return data


class DataDownloader:
    """Downloader and manager for space weather telemetry."""

    def __init__(self, cache_ttl_seconds: int = 180):
        self.cache_ttl = cache_ttl_seconds
        self.cache_dir = CACHE_DIR
        # The lambda looks fetch_text up at call time, so it can be replaced (tests, offline mode).
        self.archive = ArchiveClient(lambda url: self.fetch_text(url), self.cache_dir, lambda url: self.fetch_bytes(url))
        self.events = EventDataClient(lambda url: self.fetch_text(url), self.cache_dir)
        self.omni_hourly = OmniHourlyClient(lambda url: self.fetch_text(url), self.cache_dir)

    def _get_cache_path(self, key: str) -> str:
        return os.path.join(self.cache_dir, f"{key}.json")

    def _is_cache_valid(self, cache_path: str) -> bool:
        if not os.path.exists(cache_path):
            return False
        mtime = os.path.getmtime(cache_path)
        return (time.time() - mtime) < self.cache_ttl

    @staticmethod
    def _read_cache(cache_path: str) -> Optional[Any]:
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, ValueError):  # missing, unreadable or truncated cache file
            return None

    async def fetch_json(self, url: str, cache_key: str) -> Optional[List[Any]]:
        """
        Fetch JSON data from URL with local disk caching. On any failure (network error,
        HTTP error status, or a body that is not JSON) the last cached copy is returned,
        however old, or None if there is none.
        """
        cache_path = self._get_cache_path(cache_key)
        # Large products (7-day RTSW, several MB) are parsed and written off the event loop.
        if self._is_cache_valid(cache_path):
            cached = await asyncio.to_thread(self._read_cache, cache_path)
            if cached is not None:
                return cached

        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True, verify=_ssl_context()) as client:
                resp = await client.get(url)
            if resp.status_code == 200:
                return await asyncio.to_thread(_decode_and_store, resp.content, cache_path)
        except (httpx.HTTPError, OSError, ValueError) as exc:  # network, cache write, body not JSON
            logging.getLogger("helios.download").info("%s failed (%s); using the cache", url, exc)
        if os.path.exists(cache_path):
            return await asyncio.to_thread(self._read_cache, cache_path)
        return None

    async def fetch_text(self, url: str, timeout: float = 120.0) -> Optional[str]:
        """Body of a GET request, or None on a network error or non-200 status. Not cached here."""
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=_ssl_context()) as client:
                resp = await client.get(url)
            if resp.status_code == 200:
                return resp.text
        except (httpx.HTTPError, OSError) as exc:
            logging.getLogger("helios.download").info("%s failed: %s", url, exc)
        return None

    async def fetch_bytes(self, url: str, timeout: float = 120.0) -> Optional[bytes]:
        """Body of a GET request as bytes (images), or None on a network error or non-200 status."""
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True, verify=_ssl_context()) as client:
                resp = await client.get(url)
            if resp.status_code == 200:
                return resp.content
        except (httpx.HTTPError, OSError) as exc:
            logging.getLogger("helios.download").info("%s failed: %s", url, exc)
        return None

    @staticmethod
    def _provenance(kind: str, description: str, sources: List[str],
                    records: List[Dict[str, Any]], **extra) -> Dict[str, Any]:
        prov = {
            "kind": kind,
            "description": description,
            "source_spacecraft": sources,
            "cadence_seconds": infer_cadence_seconds(records),
            "n_records": len(records),
            "time_coverage_start": records[0]["time_tag"] if records else None,
            "time_coverage_end": records[-1]["time_tag"] if records else None,
            "time_standard": "UTC",
            "retrieved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        }
        prov.update(extra)
        return prov

    # ------------------------------------------------------------------
    # NASA CDAWeb archive (HAPI)
    # ------------------------------------------------------------------
    async def get_archive_bundle(self, mission_id: str, start: datetime, end: datetime,
                                 cadence_minutes: int = 1) -> Dict[str, Any]:
        """
        Archive records for [start, end) from CDAWeb (WIND, ACE, DSCOVR, SOHO, STEREO-A, Solar Orbiter, PSP, OMNI), as 1-minute
        means or `cadence_minutes` block averages. provenance["kind"] is "observed", or
        "unavailable" when the archive has nothing for the interval (or cannot be reached).
        """
        mission_id = mission_id.upper()
        if mission_id not in ARCHIVE_SOURCES:
            raise KeyError(mission_id)
        name = MISSIONS.get(mission_id, {}).get("name", mission_id)
        # No L1-to-Earth travel time for OMNI (already at the bow shock) or spacecraft away from L1
        dist = None if mission_id == "OMNI" or mission_id in AWAY_FROM_L1 else MISSIONS.get(mission_id, {}).get("orbit_distance_km", 1500000)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
        if end.tzinfo is None:
            end = end.replace(tzinfo=timezone.utc)

        res = await self.archive.fetch_mission(mission_id, start, end)
        records = frame_to_records(res["frame"], name, add_derived_fields, dist)
        if records and cadence_minutes > 1:
            records = block_average(records, cadence_minutes, dist)

        if records:
            used = "; ".join(f"{d['id']} ({d['label']}, {d['level']})" for d in res["datasets"])
            ncei = any(d["id"].startswith("NCEI") for d in res["datasets"])
            description = (f"NASA CDAWeb archive via HAPI{' and NOAA NCEI DSCOVR archive' if ncei else ''}: {used}. "
                           + ("1-minute means." if cadence_minutes <= 1 else f"{cadence_minutes}-minute means."))
            if mission_id == "OMNI":
                description += " OMNI values are time-shifted to the bow shock nose."
            if any(d["id"] in ("DSCOVR_H0_MAG", "AC_K1_MFI") for d in res["datasets"]):
                description += " GSM components rotated from GSE (Hapgood 1992, IGRF dipole)."
        elif res["offline"]:
            description = "The CDAWeb HAPI server could not be reached and nothing is cached for this interval."
        else:
            description = (f"The CDAWeb archive has no {name} data for this interval "
                           "(archives lag real time by days to months).")
        if res["failed_days"]:
            description += f" {res['failed_days']} day file(s) could not be retrieved."
        prov = self._provenance(
            "observed" if records else "unavailable", description,
            [ARCHIVE_SOURCES[mission_id]["spacecraft"]] if records else [], records,
            archive=HAPI_SERVER, datasets=res["datasets"], short_label=f"CDAWeb {name}",
            requested_start=start.strftime("%Y-%m-%d %H:%M:%S"),
            requested_end=end.strftime("%Y-%m-%d %H:%M:%S"))
        if records:
            # Which part of the interval the archive covers, and its gaps (data outages,
            # instrument modes): field, plasma (and SYM-H for OMNI) separately.
            prov["coverage"] = records_coverage(records, start, end, cadence_minutes)
        return {"records": records, "provenance": prov}

    # ------------------------------------------------------------------
    # NOAA SWPC Real-Time Solar Wind (RTSW)
    # ------------------------------------------------------------------
    @staticmethod
    def parse_rtsw(
        mag_rows: Optional[List[Dict[str, Any]]],
        wind_rows: Optional[List[Dict[str, Any]]],
        source: Optional[str] = None,
        mission_label: str = "DSCOVR",
        distance_km: float = 1500000.0
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        """
        Merge the RTSW 1-minute magnetometer and plasma feeds into time-ordered records.

        source=None selects the operational stream (rows flagged "active"); otherwise only
        rows whose "source" equals `source` are used. Rows with a non-zero overall_quality
        flag are discarded, missing values stay None, and both GSM and GSE field components
        are kept. Returns (records, sorted list of contributing source spacecraft).
        """
        def keep(row: Dict[str, Any]) -> bool:
            if not isinstance(row, dict) or not row.get("time_tag"):
                return False
            if source is None:
                if not row.get("active"):
                    return False
            elif str(row.get("source", "")).upper() != source.upper():
                return False
            return row.get("overall_quality") in (None, 0)

        merged: Dict[str, Dict[str, Any]] = {}
        sources = set()
        for row in (mag_rows or []):
            if not keep(row):
                continue
            rec = merged.setdefault(_iso_space(row["time_tag"]), {})
            for key in ("bt", "bx_gsm", "by_gsm", "bz_gsm", "bx_gse", "by_gse", "bz_gse"):
                rec[key] = _num(row.get(key))
            rec["_src_mag"] = row.get("source")
            sources.add(str(row.get("source")))
        for row in (wind_rows or []):
            if not keep(row):
                continue
            rec = merged.setdefault(_iso_space(row["time_tag"]), {})
            rec["density"] = _num(row.get("proton_density"))
            rec["speed"] = _num(row.get("proton_speed"))
            rec["temperature"] = _num(row.get("proton_temperature"))
            rec["_src_plasma"] = row.get("source")
            sources.add(str(row.get("source")))

        records = []
        for t in sorted(merged):
            raw = merged[t]
            rec = {"time_tag": t, "mission": mission_label}
            for key in PRIMARY_FIELDS:
                rec[key] = raw.get(key)
            if all(rec[k] is None for k in PRIMARY_FIELDS):
                continue
            rec["source_spacecraft"] = raw.get("_src_plasma") or raw.get("_src_mag")
            rec["data_source"] = "observed"
            records.append(add_derived_fields(rec, distance_km))
        return records, sorted(sources)

    @staticmethod
    def parse_rtsw_ephemeris(rows: Optional[List[Any]], source: str) -> Optional[Dict[str, Any]]:
        """Latest GSE position (km) of one RTSW spacecraft (e.g. 'SOLAR1', 'ACE') from the hourly ephemeris feed."""
        best = None
        for row in (rows or []):
            if not isinstance(row, dict) or str(row.get("source", "")).upper() != source.upper():
                continue
            x, y, z = _num(row.get("x_gse")), _num(row.get("y_gse")), _num(row.get("z_gse"))
            t = row.get("time_tag")
            if None in (x, y, z) or not t:
                continue
            t = _iso_space(t)
            if best is None or t > best["time_tag"]:
                best = {"x_km": x, "y_km": y, "z_km": z, "time_tag": t,
                        "source": f"NOAA SWPC RTSW ephemeris ({source})"}
        return best

    async def get_rtsw_position(self, source: Optional[str]) -> Optional[Dict[str, Any]]:
        """GSE position of the spacecraft that supplied RTSW data, or None if unknown."""
        if not source:
            return None
        rows = await self.fetch_json(NOAA_SWPC_ENDPOINTS["rtsw_ephemerides_1h"], "rtsw_ephemerides_1h")
        return self.parse_rtsw_ephemeris(rows if isinstance(rows, list) else None, source)

    async def _lead_times_from_positions(self, records: List[Dict[str, Any]]) -> None:
        """L1-to-Earth lead time from the GSE x of the spacecraft that measured each record (NOAA
        RTSW ephemeris) instead of a fixed 1.5 million km: SOLAR1 and ACE were 1.58 and 1.42
        million km sunward on 12 October 2026, 7 minutes apart at 400 km/s."""
        srcs = sorted({r.get("source_spacecraft") for r in records if r.get("source_spacecraft")})
        pos = dict(zip(srcs, await asyncio.gather(*(self.get_rtsw_position(s) for s in srcs))))
        for r in records:
            p = pos.get(r.get("source_spacecraft"))
            if p and r.get("speed"):
                r["l1_travel_time_min"] = SpaceWeatherPhysics.propagation_delay_minutes(p["x_km"], r["speed"])

    async def _fetch_rtsw(self) -> Tuple[Optional[List[Any]], Optional[List[Any]]]:
        mag, wind = await asyncio.gather(
            self.fetch_json(NOAA_SWPC_ENDPOINTS["rtsw_mag_1m"], "rtsw_mag_1m"),
            self.fetch_json(NOAA_SWPC_ENDPOINTS["rtsw_wind_1m"], "rtsw_wind_1m"),
        )
        return (mag if isinstance(mag, list) else None), (wind if isinstance(wind, list) else None)

    async def get_telemetry_bundle(self, mission_id: str, span_days: int = 1) -> Dict[str, Any]:
        """
        Telemetry records for the last `span_days` days plus a provenance description.

        provenance["kind"] is one of:
          "observed"  - measured values: the NOAA RTSW feed (about the last 24 h) and/or the
                        NASA CDAWeb archive (WIND always; DSCOVR and ACE for spans > 1 day,
                        with RTSW filling the hours the archive does not reach yet)
          "unavailable" - no data for this mission and window (no records)
        """
        mission_id = mission_id.upper()
        meta = MISSIONS.get(mission_id, {})
        name = meta.get("name", mission_id)
        dist = meta.get("orbit_distance_km", 1500000)
        now = datetime.now(timezone.utc).replace(second=0, microsecond=0)
        window_start = now - timedelta(days=span_days)

        records: List[Dict[str, Any]] = []
        sources: List[str] = []
        kind = "unavailable"
        description = ""
        extra: Dict[str, Any] = {}
        archive_note = ""

        if mission_id in RTSW_SOURCES:
            mag, wind = await self._fetch_rtsw()
            if mag or wind:
                tag = RTSW_SOURCES[mission_id]
                records, sources = self.parse_rtsw(mag, wind, source=tag, mission_label=name, distance_km=dist)
                if records:
                    kind = "observed"
                    description = f"NOAA SWPC RTSW 1-minute data tagged source={tag}."
                elif mission_id == "DSCOVR":
                    records, sources = self.parse_rtsw(mag, wind, source=None, mission_label=name, distance_km=dist)
                    if records:
                        kind = "observed"
                        description = ("NOAA SWPC RTSW operational L1 stream. DSCOVR itself is not in the feed; "
                                       f"source spacecraft: {', '.join(sources)}.")
            if kind == "observed":
                # The feed can hold more than the window, and after a failed request the last
                # cached copy is used however old: keep span_days up to the newest record and
                # say when that record is not recent (it used to read as current conditions).
                newest = datetime.strptime(records[-1]["time_tag"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
                start_tag = (min(newest, now) - timedelta(days=span_days)).strftime("%Y-%m-%d %H:%M:%S")
                records = [r for r in records if r["time_tag"] >= start_tag]
                age_h = (now - newest).total_seconds() / 3600.0
                if age_h > STALE_AFTER_HOURS:
                    description += (f" The newest record is from {records[-1]['time_tag']} UTC, {age_h:.1f} h ago "
                                    "(the feed could not be refreshed): not current conditions.")
                    extra["newest_record_age_hours"] = round(age_h, 2)
                await self._lead_times_from_positions(records)
            if span_days > 1:
                # Archive data for the longer window; RTSW only after the last archive sample.
                arch = await self.get_archive_bundle(mission_id, window_start, now, cadence_minutes=5)
                arch_recs = arch["records"]
                if arch_recs:
                    last = arch_recs[-1]["time_tag"]
                    # The last archive bin covers [last, last + 5 min): RTSW starts after it. RTSW
                    # minutes inside it used to be averaged into the archive's last bin.
                    tail_start = (datetime.strptime(last, "%Y-%m-%d %H:%M:%S")
                                  + timedelta(minutes=5)).strftime("%Y-%m-%d %H:%M:%S")
                    tail = [r for r in records if r["time_tag"] >= tail_start] if kind == "observed" else []
                    rt_description = description
                    records = arch_recs + tail
                    description = arch["provenance"]["description"]
                    if tail:
                        description += f" After {last} UTC: {rt_description} Averaged to 5-minute bins."
                        sources = sorted(set(arch["provenance"]["source_spacecraft"]) | set(sources))
                    else:
                        sources = arch["provenance"]["source_spacecraft"]
                    kind = "observed"
                    extra = {"archive": HAPI_SERVER, "datasets": arch["provenance"]["datasets"]}
                elif kind == "observed":
                    description += (" " + arch["provenance"]["description"]
                                    + " Only the RTSW feed (about the last 24 h) is shown.")
                if kind == "observed":
                    records = block_average(records, 5, dist)  # leaves the 5-minute archive bins unchanged
                    if not arch_recs:
                        description += " Averaged to 5-minute bins."
        elif mission_id == "GOES_16":
            # The magnetometer of NOAA's primary GOES-East satellite (GOES-19 since April 2025).
            key = "goes_mag_1day" if span_days <= 1 else "goes_mag_7day"
            rows = await self.fetch_json(NOAA_SWPC_ENDPOINTS[key], key)
            records = self.parse_goes_magnetometer(rows if isinstance(rows, list) else None,
                                                   window_start.strftime("%Y-%m-%d %H:%M:%S"))
            if records:
                kind, sources = "observed", sorted({r["mission"] for r in records})
                description = ("NOAA SWPC GOES primary magnetometer, 1-minute values: Hp (parallel to Earth's "
                               "spin axis), He, Hn and |B| in nT; arcjet-thruster minutes left out.")
            else:
                kind, description = "unavailable", "The NOAA GOES magnetometer product could not be reached."
        elif mission_id == "SOHO":
            text, _ = await cached_text(os.path.join(str(self.cache_dir), "soho_pm.txt"), SOHO_PM_URL,
                                        self.fetch_text, SOHO_PM_TTL_S)
            start_tag = window_start.strftime("%Y-%m-%d %H:%M:%S")
            pm = [r for r in parse_soho_pm(text) if r["time_tag"] >= start_tag]
            if pm:
                records = block_average(pm, 5, dist)
                kind, sources = "observed", ["SOHO"]
                description = ("SOHO CELIAS/MTOF Proton Monitor near-real-time solar wind speed and density "
                               "(University of Maryland, space.umd.edu/pm), 5-minute means. SOHO has no "
                               "magnetometer: field values and the quantities that need them are empty.")
                if span_days > 2:
                    description += " The feed covers about the last two days."
        elif mission_id == "STEREO_A":
            raw: List[Dict[str, Any]] = []
            day = window_start.date()
            while day <= now.date():
                paths = [await self._stereo_beacon_file(inst, day) for inst in ("impact", "plastic")]
                try:
                    raw += parse_stereo_beacon(*paths)
                except (OSError, ValueError, KeyError, IndexError) as exc:  # a damaged file: that day is left out
                    logging.getLogger("helios.download").warning("STEREO-A beacon %s unreadable: %s", day, exc)
                day += timedelta(days=1)
            start_tag = window_start.strftime("%Y-%m-%d %H:%M:%S")
            raw = [r for r in raw if r["time_tag"] >= start_tag]
            if raw:
                records = block_average(raw, 5, None)  # not at L1: no L1-to-Earth travel time
                kind, sources = "observed", ["STEREO-A"]
                description = ("STEREO-A space weather beacon (STEREO Science Center): PLASTIC proton speed and "
                               "density and the IMPACT field magnitude, 5-minute means. STEREO-A is far from "
                               "Earth (see the orbit view), so its field components are not given as GSM and no "
                               "travel time to Earth is computed; beacon data are preliminary.")
        elif mission_id in ARCHIVE_SOURCES:
            arch = await self.get_archive_bundle(mission_id, window_start, now,
                                                 cadence_minutes=5 if span_days > 1 else 1)
            if arch["records"]:
                records = arch["records"]
                kind = "observed"
                sources = arch["provenance"]["source_spacecraft"]
                description = arch["provenance"]["description"]
                extra = {"archive": HAPI_SERVER, "datasets": arch["provenance"]["datasets"]}
                if records[-1]["time_tag"] < (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"):
                    description += f" The archive currently ends at {records[-1]['time_tag']} UTC."
            else:
                archive_note = " " + arch["provenance"]["description"]

        if kind != "observed" and not description:
            # No data: nothing is shown (it used to be a generated solar wind, or the operational
            # stream with invented instrument offsets and noise, labelled synthetic or simulated).
            records = []
            description = f"No data for {name} in this window could be reached here." + archive_note
            access = MISSIONS.get(mission_id, {}).get("data_access")
            if access:
                description += f" Data access: {access}."

        return {"records": records, "provenance": self._provenance(kind, description, sources, records, **extra)}

    async def _stereo_beacon_file(self, inst: str, day) -> Optional[str]:
        """Local copy of one day's STEREO-A beacon CDF ('impact' or 'plastic'): days before
        yesterday are kept for good, newer ones refreshed after STA_BEACON_TTL_S."""
        folder = os.path.join(str(self.cache_dir), "stereo_beacon")
        os.makedirs(folder, exist_ok=True)
        key = f"{inst}_{day:%Y%m%d}.cdf"
        path = os.path.join(folder, key)
        final = day < (datetime.now(timezone.utc) - timedelta(days=1)).date()
        if os.path.exists(path) and (final or time.time() - os.path.getmtime(path) < STA_BEACON_TTL_S):
            return path
        month = f"{STA_BEACON}/{inst}/{day:%Y}/{day:%m}/"
        listing = await self.fetch_text(month)
        names = re.findall(rf'href="(STA_LB_[A-Z_]+_{day:%Y%m%d}_V\d+\.cdf)"', listing or "")
        data = await self.fetch_bytes(month + sorted(names)[-1]) if names else None
        if data:
            tmp = path + ".part"
            with open(tmp, "wb") as f:
                f.write(data)
            os.replace(tmp, path)
            return path
        return path if os.path.exists(path) else None

    async def get_satellite_telemetry(self, mission_id: str, span_days: int = 1) -> List[Dict[str, Any]]:
        """Telemetry records for any satellite in the catalog (see get_telemetry_bundle)."""
        return (await self.get_telemetry_bundle(mission_id, span_days))["records"]

    # ------------------------------------------------------------------
    # Geomagnetic / solar indices (Kp, GOES X-rays, GOES protons)
    # ------------------------------------------------------------------
    @staticmethod
    def parse_kp(rows: Optional[List[Any]]) -> Tuple[Optional[float], Optional[str]]:
        """Latest planetary Kp from the SWPC product (list-of-dicts, or the legacy header-row format)."""
        if not rows:
            return None, None
        best: Tuple[Optional[float], Optional[str]] = (None, None)
        if isinstance(rows[0], list):
            header = rows[0]
            if "Kp" not in header or "time_tag" not in header:
                return None, None
            ki, ti = header.index("Kp"), header.index("time_tag")
            for row in rows[1:]:
                kp = _num(row[ki]) if len(row) > ki else None
                if kp is not None:
                    best = (kp, _iso_space(row[ti]))
            return best
        for row in rows:
            if isinstance(row, dict):
                kp = _num(row.get("Kp", row.get("kp_index")))
                if kp is not None and row.get("time_tag"):
                    best = (kp, _iso_space(row["time_tag"]))
        return best

    @staticmethod
    def parse_goes_magnetometer(rows: Optional[List[Any]], start_tag: str = "") -> List[Dict[str, Any]]:
        """NOAA GOES magnetometer rows as records from start_tag on; minutes flagged for arcjet firings left out."""
        out = []
        for row in rows or []:
            if not isinstance(row, dict) or row.get("arcjet_flag") or not row.get("time_tag"):
                continue
            t = _iso_space(row["time_tag"])
            if t >= start_tag and _num(row.get("Hp")) is not None:
                out.append({"time_tag": t, "mission": f"GOES-{row.get('satellite')}", "hp_mag": _num(row.get("Hp")),
                            "he_mag": _num(row.get("He")), "hn_mag": _num(row.get("Hn")),
                            "total_mag": _num(row.get("total")), "data_source": "observed"})
        return out

    @staticmethod
    def parse_goes_latest(rows: Optional[List[Any]], energy: str) -> Tuple[Optional[float], Optional[str]]:
        """Most recent GOES flux for one channel label (e.g. '0.1-0.8nm', '>=10 MeV')."""
        best_t, best_v = None, None
        want = energy.replace(" ", "")
        for row in (rows or []):
            if not isinstance(row, dict) or str(row.get("energy", "")).replace(" ", "") != want:
                continue
            v = _num(row.get("flux"))
            t = row.get("time_tag")
            if v is not None and v >= 0 and t and (best_t is None or t > best_t):
                best_t, best_v = t, v
        return best_v, (_iso_space(best_t) if best_t else None)

    async def get_space_weather_indices(self) -> Dict[str, Any]:
        """Latest observed Kp, GOES 0.1-0.8 nm X-ray flux and >=10 MeV proton flux (None when unavailable)."""
        kp_rows, xr_rows, pr_rows = await asyncio.gather(
            self.fetch_json(NOAA_SWPC_ENDPOINTS["kp_7day"], "kp_7day"),
            self.fetch_json(NOAA_SWPC_ENDPOINTS["xrays_1day"], "xrays_1day"),
            self.fetch_json(NOAA_SWPC_ENDPOINTS["protons_1day"], "protons_1day"),
        )
        kp, kp_t = self.parse_kp(kp_rows if isinstance(kp_rows, list) else None)
        xr, xr_t = self.parse_goes_latest(xr_rows if isinstance(xr_rows, list) else None, "0.1-0.8nm")
        pr, pr_t = self.parse_goes_latest(pr_rows if isinstance(pr_rows, list) else None, ">=10 MeV")
        return {
            "kp": kp, "kp_time": kp_t,
            "xray_flux_long": xr, "xray_time": xr_t,
            "proton_flux_10mev": pr, "proton_time": pr_t,
            "source": "NOAA SWPC (planetary K-index, GOES primary XRS and integral protons)"
        }

    @staticmethod
    def parse_solar_regions(rows: Optional[List[Any]]) -> Dict[str, Any]:
        """
        Numbered active regions of the latest day in the NOAA SWPC solar region summary
        (SRS) product. Positions are heliographic and valid for the report date; NOAA
        longitudes are positive to the east of the central meridian. Flare probabilities
        are SWPC's 24-hour forecasts for each region.
        """
        rows = [r for r in (rows or []) if isinstance(r, dict) and r.get("observed_date") and r.get("region")]
        if not rows:
            return {"observed_date": None, "regions": []}
        day = max(r["observed_date"] for r in rows)
        regions = []
        for r in rows:
            if r["observed_date"] != day or r.get("latitude") is None or r.get("longitude") is None:
                continue
            regions.append({
                "region": int(r["region"]),
                "location": r.get("location"),
                "latitude": float(r["latitude"]),
                "longitude_east": float(r["longitude"]),
                "carrington_longitude": r.get("carrington_longitude"),
                "area_msh": r.get("area"),
                "spot_class": r.get("spot_class"),
                "mag_class": r.get("mag_class"),
                "number_spots": r.get("number_spots"),
                "flares_today": {"C": r.get("c_xray_events"), "M": r.get("m_xray_events"), "X": r.get("x_xray_events")},
                "flare_probability_pct": {"C": r.get("c_flare_probability"), "M": r.get("m_flare_probability"),
                                          "X": r.get("x_flare_probability")},
                "proton_probability_pct": r.get("proton_probability"),
                "first_date": r.get("first_date"),
            })
        regions.sort(key=lambda r: r["region"])
        return {"observed_date": day, "regions": regions}

    async def get_solar_regions(self) -> Dict[str, Any]:
        """Latest NOAA SWPC solar region summary (observed active regions)."""
        rows = await self.fetch_json(NOAA_SWPC_ENDPOINTS["solar_regions"], "solar_regions")
        out = self.parse_solar_regions(rows if isinstance(rows, list) else None)
        out["source"] = "NOAA SWPC solar region summary (json/solar_regions.json)"
        out["kind"] = "observed" if out["regions"] else "unavailable"
        return out

    @staticmethod
    def parse_kyoto_dst(rows: Optional[List[Any]]) -> List[Dict[str, Any]]:
        """
        Hourly Kyoto Dst from the SWPC product, oldest first. The time stamp marks the start
        of the hour the value averages (T00:00 is Kyoto's hour 1, 00-01 UT).
        """
        out = []
        if not rows:
            return out
        if isinstance(rows[0], list):  # legacy header-row format
            header = rows[0]
            if "time_tag" not in header or "dst" not in header:
                return out
            ti, di = header.index("time_tag"), header.index("dst")
            rows = [{"time_tag": r[ti], "dst": r[di]} for r in rows[1:] if len(r) > max(ti, di)]
        for row in rows:
            if isinstance(row, dict) and row.get("time_tag"):
                v = _num(row.get("dst"))
                if v is not None and abs(v) < 9999:
                    out.append({"time_tag": _iso_space(row["time_tag"]), "dst": v})
        out.sort(key=lambda r: r["time_tag"])
        return out

    async def get_kyoto_dst(self) -> Dict[str, Any]:
        """Real-time (quicklook) hourly Dst of the last ~7 days from WDC Kyoto via NOAA SWPC."""
        rows = await self.fetch_json(NOAA_SWPC_ENDPOINTS["kyoto_dst"], "kyoto_dst")
        return {"records": self.parse_kyoto_dst(rows if isinstance(rows, list) else None),
                "source": "WDC for Geomagnetism, Kyoto real-time (quicklook) Dst via NOAA SWPC; hourly means, time stamp = start of hour"}

    @staticmethod
    def parse_geomag_forecast(text: Optional[str]) -> Optional[Dict[str, Any]]:
        """
        Day-1 values of the NOAA SWPC 3-day geomagnetic forecast text product: the issue
        time and the mid-latitude probabilities (%) of active, minor, moderate and
        strong-extreme storm conditions. None when the text has no probability block.
        """
        if not text:
            return None
        issued, day, probs = None, None, {}
        in_block = False
        for line in text.splitlines():
            line = line.strip()
            if line.startswith(":Issued:"):
                issued = line.split(":Issued:", 1)[1].strip()
            elif line.startswith("NOAA Geomagnetic Activity Probabilities"):
                in_block = True
                rest = line.replace("NOAA Geomagnetic Activity Probabilities", "").strip()
                day = rest.split("-")[0].strip() or None
            elif in_block:
                m = re.match(r"^(Active|Minor storm|Moderate storm|Strong-Extreme storm)\s+(\d+)/", line)
                if m:
                    probs[m.group(1).lower().replace(" ", "_").replace("-", "_")] = int(m.group(2))
                elif line:
                    in_block = False
        if not probs:
            return None
        return {"issued": issued, "day": day, "probabilities": probs}

    @staticmethod
    def parse_kp_forecast(rows: Optional[List[Any]]) -> List[Dict[str, Any]]:
        """
        Forecast 3-hourly Kp of the NOAA SWPC planetary K-index forecast product: the rows
        labelled "estimated" (the current UTC day, including its bins still to come) and
        "predicted" (the following days). Keeping only "predicted" left the 12-hour chart
        without NOAA's values for the rest of the current day.
        """
        out = []
        for row in (rows or []):
            kind = row.get("observed") if isinstance(row, dict) else None
            if kind in ("estimated", "predicted") and row.get("time_tag"):
                kp = _num(row.get("kp"))
                if kp is not None:
                    out.append({"time_tag": _iso_space(row["time_tag"]), "kp": kp, "kind": kind})
        return out

    async def get_noaa_geomag_forecast(self) -> Dict[str, Any]:
        """
        NOAA SWPC 3-day geomagnetic forecast: day-1 storm probabilities and the predicted
        3-hourly Kp. The parsed text product is cached; on a failure the cached copy is used.
        """
        text, kp_rows = await asyncio.gather(
            self.fetch_text(NOAA_SWPC_ENDPOINTS["geomag_forecast_3day"], timeout=15.0),
            self.fetch_json(NOAA_SWPC_ENDPOINTS["kp_forecast"], "kp_forecast"),
        )
        parsed = self.parse_geomag_forecast(text)
        cache_path = self._get_cache_path("geomag_forecast_3day")
        if parsed is not None:
            try:
                with open(cache_path, "w", encoding="utf-8") as f:
                    json.dump(parsed, f)
            except OSError:
                pass
        elif os.path.exists(cache_path):
            parsed = self._read_cache(cache_path)
        out = dict(parsed or {})
        out["kp_forecast"] = self.parse_kp_forecast(kp_rows if isinstance(kp_rows, list) else None)
        return out

    async def get_historical_event(self, event_id: str) -> Dict[str, Any]:
        """
        A historical space weather event: OMNI 5-minute means of its interval (EVENT_WINDOWS)
        from NASA CDAWeb, or the same data bundled with HELIOS-L1 when CDAWeb cannot be
        reached; the extremes in metadata["observed_5min"] come from those data. Carrington
        1859 has no measurements, so it has no time series. peak_kp is the published maximum.
        """
        descriptions = {
            "may_2024_g5": {
                "title": "May 10-12, 2024 Extreme G5 Solar Superstorm",
                "summary": "Strongest geomagnetic storm in over 20 years. Driven by multiple coronal mass ejections (CMEs) from Active Region 3664. Planetary Kp reached 9. Aurora visible at low latitudes.",
                "peak_kp": 9.0,
            },
            "st_patricks_2015": {
                "title": "St. Patrick's Day Storm (March 17, 2015)",
                "summary": "Classic two-step severe G4 geomagnetic storm. Sudden impulse when the interplanetary shock reached Earth, followed by sustained southward Bz. Kp reached 8-.",
                "peak_kp": 7.67,
            },
            "halloween_2003": {
                "title": "Halloween Solar Storms (October 2003)",
                "summary": "Extreme series of solar flares including an X17+ eruption from NOAA Region 486, and two fast CMEs (shocks on 29 and 30 October). The OMNI plasma record has a long gap while the solar wind instruments were saturated, so the peak speeds (about 1900-2000 km/s, Skoug et al. 2004) are missing from these data.",
                "peak_kp": 9.0,
            },
            "bastille_2000": {
                "title": "Bastille Day Superstorm (July 14, 2000)",
                "summary": "Major solar eruptive event during Solar Cycle 23 maximum. An X5.7 flare accompanied a full-halo CME (1674 km/s in the SOHO/LASCO CDAW catalogue). Triggered an S4 severe solar radiation storm (>=10 MeV protons peaking at 24,000 pfu on 15 July, NOAA SWPC event list) which blinded SOHO star trackers and degraded geostationary solar panels. Dst plunged to -301 nT.",
                "peak_kp": 9.0,
            },
            "quebec_1989": {
                "title": "Hydro-Québec Blackout Superstorm (March 13, 1989)",
                "summary": "Archetypal power grid collapse event. A powerful CME triggered geomagnetically induced currents (GIC) that saturated substation transformers, tripping protective relays within 92 seconds and leaving 6 million people without electricity for 9 hours. No spacecraft measured the solar wind during the storm: OMNI has only the ring current index (SYM-H).",
                "peak_kp": 9.0,
            },
            "carrington_1859": {
                "title": "Carrington Superstorm Event (September 1859)",
                "summary": "The archetypal space weather superstorm. White-light solar flare witnessed on 1 September; the storm began about 17.6 hours later, a mean Sun-Earth speed near 2360 km/s. Telegraph lines failed across Europe and North America; auroras were seen in Hawaii, Cuba and Colombia. No solar wind measurements exist, so there is no time series; Kp did not exist (the storm is placed beyond Kp 9).",
                "peak_kp": 9.0,
            },
            "quiet_baseline": {
                "title": "Quiet Sun Solar Wind Baseline",
                "summary": "Two quiet days at solar minimum, 6-8 December 2019: slow solar wind, weak field, GFZ Kp 1- or lower throughout.",
                "peak_kp": 0.67,
            },
        }

        if event_id not in descriptions:  # used to answer with the May 2024 storm
            raise UnknownEventError(event_id)
        event_meta = dict(descriptions[event_id])
        if event_id not in EVENT_WINDOWS:
            return {"metadata": event_meta, "telemetry": [], "records": [], "satellite": None, "shocks": [],
                    "dst_comparison": None,
                    "provenance": {"kind": "none", "time_standard": "UTC",
                                   "description": "No spacecraft data exist for this event."}}

        start, end = (datetime.fromisoformat(t).replace(tzinfo=timezone.utc) for t in EVENT_WINDOWS[event_id])
        arch = await self.get_archive_bundle("OMNI", start, end, cadence_minutes=5)
        telemetry, prov = arch["records"], arch["provenance"]
        if not telemetry:
            snap = omni_snapshot(event_id)
            telemetry = [add_derived_fields({"mission": "OMNI", "data_source": "observed", **dict(zip(snap["columns"], row))},
                                            None) for row in snap["rows"]]
            prov = dict(snap["provenance"], description=snap["provenance"]["description"]
                        + f" CDAWeb could not be reached: copy bundled with HELIOS-L1 (retrieved "
                        f"{snap['provenance']['retrieved_utc']} UTC).")
        plasma = (prov.get("coverage") or {}).get("groups", {}).get("plasma")
        if plasma and plasma.get("gaps"):
            prov["description"] += f" Solar wind plasma: {describe_coverage(plasma)}."
        observed = {}
        for key, field, fn in (("min_bz", "bz_gsm", min), ("peak_speed", "speed", max),
                               ("peak_dyn_pressure", "dynamic_pressure", max), ("min_sym_h", "sym_h", min)):
            vals = [r[field] for r in telemetry if r.get(field) is not None]
            observed[key] = round(fn(vals), 2) if vals else None
        return {
            "metadata": dict(event_meta, observed_5min=observed),
            "provenance": prov,
            "dst_comparison": AuroralModel.compare_dst_models(telemetry) if observed["min_sym_h"] is not None else None,
            "telemetry": telemetry,
            "records": telemetry,
            "satellite": "OMNI",
            "shocks": SpaceWeatherPhysics.detect_interplanetary_shocks(telemetry)
        }
