"""
Custom telemetry ingestion and file import engine for HELIOS-L1.
Reads CSV / delimited ASCII (including OMNI YEAR DOY HR MN listings and HELIOS-L1's own
CSV exports with their '#' metadata lines) and JSON (record lists, NOAA SWPC header-row
products, HELIOS-L1 JSON exports), plus the bundled storm benchmark profiles.
"""
import io
import re
import csv
import json
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional

from helios.core.science import SpaceWeatherPhysics
from helios.core.coordinates import gse_to_gsm

class TelemetryImporter:
    """Parses, validates, normalizes, and classifies space weather telemetry files."""

    COLUMN_MAPPINGS = {
        "speed": ["speed", "vsw", "v_sw", "velocity", "flow_speed", "bulk_speed", "v_bulk", "ion_speed",
                  "vp", "v_p", "proton_speed"],  # ACE SWEPAM Vp, NOAA RTSW proton_speed
        "density": ["density", "np", "n_p", "proton_density", "ion_density", "plasma_density"],
        "temperature": ["temperature", "temp", "tp", "t_p", "thermal_temp", "tpr", "proton_temperature"],
        "bx_gsm": ["bx_gsm", "bx", "b_x", "b_gsm_x"],
        "by_gsm": ["by_gsm", "by", "b_y", "b_gsm_y"],
        "bz_gsm": ["bz_gsm", "bz", "b_z", "b_gsm_z"],
        "bt": ["bt", "b_total", "total_b", "b_mag", "magnitude"],
        "bx_gse": ["bx_gse", "b_gse_x", "bgse_x", "bxgse"],
        "by_gse": ["by_gse", "b_gse_y", "bgse_y", "bygse"],
        "bz_gse": ["bz_gse", "b_gse_z", "bgse_z", "bzgse"],
        "time_tag": ["time_tag", "time", "timestamp", "datetime", "date_time", "epoch", "utc"]
    }

    PRESETS: Dict[str, Dict[str, Any]] = {
        "may2024_g5": {
            "id": "may2024_g5",
            "name": "May 10-11, 2024 G5 Superstorm",
            "tag": "G5 EXTREME",
            "badge_color": "rose",
            "satellite": "Illustrative profile (hourly values written for this preset, not DSCOVR or OMNI measurements)",
            "description": "Historic G5 extreme storm. Fast interplanetary shock arrival jumping bulk velocity from 420 to 860 km/s, prolonged southward Bz reaching -48 nT, dynamic pressure spike above 45 nPa.",
            "csv_content": """time,speed,density,bx_gsm,by_gsm,bz_gsm,bt
2024-05-10 12:00:00,412.3,4.8,2.1,3.4,-1.2,4.4
2024-05-10 13:00:00,418.5,5.2,1.8,4.1,2.3,5.0
2024-05-10 14:00:00,425.0,5.8,2.4,3.9,-0.8,4.6
2024-05-10 15:00:00,430.1,6.5,3.1,4.5,-2.1,5.8
2024-05-10 16:00:00,438.4,7.1,3.8,5.2,-3.5,6.9
2024-05-10 16:45:00,445.0,8.2,4.2,6.0,-4.1,7.8
2024-05-10 17:00:00,740.5,28.4,-12.4,18.5,-32.8,39.6
2024-05-10 17:30:00,815.2,36.2,-15.8,22.1,-46.5,53.8
2024-05-10 18:00:00,858.0,42.5,-18.2,25.4,-48.2,57.1
2024-05-10 19:00:00,832.1,38.1,-16.5,23.0,-42.1,49.8
2024-05-10 20:00:00,795.4,31.0,-14.1,19.8,-35.6,41.9
2024-05-10 21:00:00,760.8,24.5,-11.8,16.2,-28.4,33.5
2024-05-10 22:00:00,725.3,19.2,-9.5,13.4,-21.0,25.7
2024-05-10 23:00:00,695.0,15.8,-7.2,11.0,-16.5,20.4
2024-05-11 00:00:00,670.2,13.1,-5.4,9.2,-12.8,16.1
2024-05-11 01:00:00,648.5,11.4,-4.1,8.0,-9.5,12.8"""
        },
        "bastille_2000": {
            "id": "bastille_2000",
            "name": "July 14-15, 2000 Bastille Day CME",
            "tag": "G5 SUPERSTORM",
            "badge_color": "amber",
            "satellite": "Illustrative profile (not ACE SWEPAM / MAG measurements)",
            "description": "Halo CME driven by X5.7 flare. Interplanetary shock front exceeding 1050 km/s with density peak over 50 cm^-3 and sustained southward Bz driving Dst to -301 nT.",
            "csv_content": """time,speed,density,bx_gsm,by_gsm,bz_gsm,bt
2000-07-15 12:00:00,480.0,6.5,2.0,3.0,-2.0,4.2
2000-07-15 13:00:00,495.0,7.1,2.5,3.2,-1.5,4.3
2000-07-15 14:00:00,510.0,8.0,3.1,4.0,-3.2,5.5
2000-07-15 14:35:00,920.0,34.0,-14.0,18.0,-38.0,43.2
2000-07-15 15:00:00,1050.0,48.5,-18.5,24.0,-52.0,60.2
2000-07-15 16:00:00,1085.0,52.0,-21.0,26.5,-55.4,64.9
2000-07-15 17:00:00,1020.0,41.2,-17.0,22.0,-45.0,52.4
2000-07-15 18:00:00,960.0,33.5,-13.5,18.5,-36.0,42.4
2000-07-15 19:00:00,910.0,27.0,-10.2,15.0,-28.0,32.7
2000-07-15 20:00:00,875.0,22.4,-8.0,12.5,-21.5,25.4
2000-07-15 21:00:00,840.0,18.2,-6.5,10.2,-16.0,19.3
2000-07-15 22:00:00,810.0,15.0,-5.0,8.5,-12.0,14.8"""
        },
        "carrington_1859": {
            "id": "carrington_1859",
            "name": "September 1859 Carrington Event",
            "tag": "EXTREME BENCHMARK",
            "badge_color": "purple",
            "satellite": "Illustrative profile (no in-situ data exist for 1859)",
            "description": "The archetypal benchmark space weather catastrophe. Extreme velocity ~2300 km/s, transiting Sun to Earth in 17.6 hours, Bz ~ -65 nT, compressing the dayside magnetopause inside 4.5 Earth radii.",
            "csv_content": """time,speed,density,bx_gsm,by_gsm,bz_gsm,bt
1859-09-02 00:00:00,430.0,5.0,2.0,3.0,1.0,3.7
1859-09-02 02:00:00,445.0,5.5,2.2,3.2,0.5,3.9
1859-09-02 04:00:00,460.0,6.0,2.5,3.5,-1.2,4.3
1859-09-02 04:45:00,1850.0,58.0,-24.0,35.0,-48.0,63.4
1859-09-02 05:00:00,2280.0,82.0,-32.0,48.0,-64.5,85.6
1859-09-02 06:00:00,2150.0,74.0,-28.0,42.0,-58.0,75.8
1859-09-02 07:00:00,1980.0,62.0,-24.0,36.0,-49.0,64.2
1859-09-02 08:00:00,1800.0,50.0,-20.0,30.0,-40.0,52.9
1859-09-02 10:00:00,1520.0,36.0,-15.0,22.0,-30.0,39.6
1859-09-02 12:00:00,1300.0,25.0,-11.0,16.0,-21.0,27.9
1859-09-02 14:00:00,1120.0,18.0,-8.0,12.0,-15.0,19.9"""
        },
        "halloween_2003": {
            "id": "halloween_2003",
            "name": "October 2003 Halloween Storm",
            "tag": "G5 FAST CME",
            "badge_color": "sky",
            "satellite": "Illustrative profile (not ACE SWEPAM or SOHO CELIAS measurements)",
            "description": "Fast CME originating from Active Region 10486. Interplanetary shock speed exceeded 1700 km/s, driving intense auroras visible in Florida and Australia, causing polar airline reroutes.",
            "csv_content": """time,speed,density,bx_gsm,by_gsm,bz_gsm,bt
2003-10-29 02:00:00,520.0,8.2,3.1,4.5,-2.0,5.7
2003-10-29 04:00:00,550.0,9.0,3.5,5.0,-3.2,6.7
2003-10-29 06:00:00,580.0,10.2,4.0,5.8,-4.1,7.8
2003-10-29 06:12:00,1450.0,45.0,-18.0,26.0,-38.0,48.8
2003-10-29 07:00:00,1720.0,65.0,-24.0,34.0,-52.0,65.5
2003-10-29 08:00:00,1680.0,58.0,-22.0,31.0,-46.0,58.8
2003-10-29 09:00:00,1540.0,46.0,-18.0,26.0,-36.0,47.1
2003-10-29 10:00:00,1410.0,37.0,-15.0,21.0,-28.0,37.3
2003-10-29 12:00:00,1220.0,26.0,-11.0,16.0,-20.0,26.7
2003-10-29 14:00:00,1080.0,19.0,-8.0,12.0,-14.0,19.2"""
        },
        "quiet_wind": {
            "id": "quiet_wind",
            "name": "Quiet Solar Wind Baseline",
            "tag": "G0 NOMINAL",
            "badge_color": "emerald",
            "satellite": "Illustrative profile (not DSCOVR measurements)",
            "description": "Nominal quiet heliospheric conditions. Bulk solar wind speed ~350-365 km/s, positive (northward) Bz, dynamic pressure ~1.2 nPa, magnetopause extended beyond 11 Earth radii.",
            "csv_content": """time,speed,density,bx_gsm,by_gsm,bz_gsm,bt
2026-09-21 00:00:00,352.1,4.2,2.5,1.8,2.1,3.7
2026-09-21 01:00:00,356.4,4.0,2.4,2.0,2.4,3.9
2026-09-21 02:00:00,360.8,4.3,2.2,2.2,2.8,4.1
2026-09-21 03:00:00,358.5,4.1,2.0,2.1,3.0,4.1
2026-09-21 04:00:00,362.0,3.9,2.1,1.9,2.6,3.8
2026-09-21 05:00:00,365.2,4.2,2.3,1.7,2.2,3.6
2026-09-21 06:00:00,363.8,4.4,2.4,2.0,1.9,3.6
2026-09-21 07:00:00,359.0,4.1,2.2,2.3,2.5,3.9
2026-09-21 08:00:00,361.5,4.0,2.1,2.2,2.7,4.0"""
        }
    }

    # The preset tables are hand-written illustrative profiles of famous storms (shapes and
    # peak values in the published range), not measured data. Measured OMNI data for the
    # 2000, 2003 and 2024 events are available from the Archive Interval loader and the
    # historical event viewer.
    PRESET_NOTE = ("Illustrative profile for testing the import pipeline, not measured data. "
                   "Measured OMNI data for this interval can be loaded with the dashboard's Archive Interval (NASA CDAWeb) option.")

    @classmethod
    def get_presets_list(cls) -> List[Dict[str, Any]]:
        """Returns metadata list of all available telemetry presets."""
        presets = []
        for p in cls.PRESETS.values():
            presets.append({
                "id": p["id"],
                "name": p["name"],
                "tag": p["tag"],
                "badge_color": p["badge_color"],
                "satellite": p["satellite"],
                "description": p["description"],
                # data rows of the profile (the cards showed an empty "pts" without it)
                "records_count": sum(1 for ln in p["csv_content"].strip().splitlines()[1:] if ln.strip()),
                "data_kind": "synthetic",
                "note": cls.PRESET_NOTE if p["id"] != "carrington_1859" else "Illustrative profile; no in-situ data exist for 1859."
            })
        return presets

    @classmethod
    def get_preset(cls, preset_id: str) -> Optional[Dict[str, Any]]:
        """Fetch preset by ID including raw CSV text."""
        return cls.PRESETS.get(preset_id)

    @staticmethod
    def _normalise_header(name: Any) -> str:
        """'Bz GSM (nT)' -> 'bz_gsm', 'Speed [km/s]' -> 'speed': units in brackets dropped, separators to '_'."""
        s = re.sub(r"[\(\[\{].*?[\)\]\}]", "", str(name)).strip().lower()
        return re.sub(r"[^0-9a-z]+", "_", s).strip("_")

    @classmethod
    def _find_column(cls, df_columns: List[str], target: str) -> Optional[str]:
        target_candidates = cls.COLUMN_MAPPINGS.get(target, [target])
        col_lower_map = {c.lower().strip(): c for c in df_columns}
        for c in df_columns:
            col_lower_map.setdefault(cls._normalise_header(c), c)
        for candidate in target_candidates:
            if candidate in col_lower_map:
                return col_lower_map[candidate]
        return None

    @staticmethod
    def _read_table(content: str) -> pd.DataFrame:
        """
        DataFrame from the uploaded text: JSON (a list of records, a list of rows with a
        header row as in the NOAA SWPC products, or a HELIOS-L1 JSON export with 'records'),
        or delimited text (comma, tab, semicolon or spaces). Lines starting with '#' are
        comments, so HELIOS-L1 CSV exports with their metadata header import again.
        """
        text = content.lstrip("\ufeff").strip()
        if text[:1] in ("[", "{"):
            obj = json.loads(text)
            if isinstance(obj, dict):
                obj = obj.get("records", obj.get("data", []))
            if isinstance(obj, list) and obj and isinstance(obj[0], list):
                return pd.DataFrame(obj[1:], columns=[str(c) for c in obj[0]])
            return pd.DataFrame(obj)
        lines = [ln for ln in text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
        return pd.read_csv(io.StringIO("\n".join(lines)), sep=None, engine="python")

    # Fill-value thresholds (values at or beyond these are archive fill flags, not data).
    # OMNI uses 99999.9 km/s, 999.99 cm^-3, 9999.99 / 999.99 nT and 9999999. K; CDF
    # products use +/-1e31. Physical solar wind values stay far below these limits.
    FILL_LIMITS = {
        "speed": 9999.0,
        "density": 999.0,
        "temperature": 9.0e6,
        "bx_gsm": 999.0,
        "by_gsm": 999.0,
        "bz_gsm": 999.0,
        "bt": 999.0,
        "bx_gse": 999.0,
        "by_gse": 999.0,
        "bz_gse": 999.0,
    }

    @classmethod
    def _parse_times(cls, df: pd.DataFrame, time_col: Optional[str]) -> pd.Series:
        """
        UTC time stamps for every row. Accepts one time column (ISO 8601, with or without
        'Z'/offset; offsets are converted to UTC) or OMNI-style YEAR, DOY, HR, MN columns.
        Unparseable rows become NaT.
        """
        lower = {c.lower().strip(): c for c in df.columns}
        year_c = lower.get("year") or lower.get("yyyy") or lower.get("yr")
        doy_c = lower.get("doy") or lower.get("day") or lower.get("ddd")
        if year_c and doy_c and (time_col is None or time_col in (year_c, doy_c)):
            hour_c = lower.get("hr") or lower.get("hour")
            min_c = lower.get("mn") or lower.get("min") or lower.get("minute")
            base = pd.to_datetime(pd.to_numeric(df[year_c], errors="coerce").astype("Int64").astype(str),
                                  format="%Y", errors="coerce", utc=True)
            offset = pd.to_timedelta(pd.to_numeric(df[doy_c], errors="coerce") - 1, unit="D")
            if hour_c:
                offset = offset + pd.to_timedelta(pd.to_numeric(df[hour_c], errors="coerce").fillna(0), unit="h")
            if min_c:
                offset = offset + pd.to_timedelta(pd.to_numeric(df[min_c], errors="coerce").fillna(0), unit="min")
            return base + offset
        if time_col is None:
            time_col = df.columns[0]
        raw = df[time_col].astype(str).str.strip()
        try:
            return pd.to_datetime(raw, utc=True, errors="coerce", format="mixed")
        except (TypeError, ValueError):
            return pd.to_datetime(raw, utc=True, errors="coerce")

    @classmethod
    def parse_csv_or_text(cls, content: str, mission_name: str = "Custom Spacecraft") -> Dict[str, Any]:
        """
        Parse CSV or delimited ASCII text telemetry.
        Auto-identifies NASA OMNI, NOAA, or custom header schemas.
        Computes physical state variables, shock detection, and summary statistics.

        * Missing values and archive fill values (see FILL_LIMITS) become None; nothing
          is replaced by a nominal value, and derived quantities are None when an input
          is missing.
        * Time stamps are converted to UTC 'YYYY-MM-DD HH:MM:SS'; rows whose time
          cannot be parsed are dropped and the rest are sorted in time.
        * IMF components named bx/by/bz are taken as GSM. GSE columns (bx_gse ...) are
          kept, and when a file has no GSM components they are rotated to GSM for the
          time of each row (Hapgood 1992 with the IGRF dipole; see core.coordinates).
          Bx is the same in both systems.
        """
        try:
            df = cls._read_table(content)
        except (ValueError, KeyError, TypeError, csv.Error) as e:  # pandas parser errors are ValueErrors
            return {"error": f"Could not read the file as CSV, delimited text or JSON: {str(e)}"}

        if df.empty or len(df.columns) < 2:
            return {"error": "Dataset must contain at least 2 columns (time and physical parameter)."}

        warnings: List[str] = []
        time_col = cls._find_column(df.columns, "time_tag")
        times = cls._parse_times(df, time_col)
        bad_time = int(times.isna().sum())
        if bad_time:
            warnings.append(f"{bad_time} row(s) with an unreadable time stamp were dropped.")
        df = df.loc[times.notna()].copy()
        df["_t"] = times[times.notna()]
        df = df.sort_values("_t", kind="stable")
        if df.empty:
            return {"error": "No row has a readable time stamp."}

        columns: Dict[str, Any] = {}
        found: Dict[str, bool] = {}
        n_fill = 0
        for target in ("speed", "density", "temperature", "bx_gsm", "by_gsm", "bz_gsm", "bt",
                       "bx_gse", "by_gse", "bz_gse"):
            col = cls._find_column(df.columns, target)
            found[target] = col is not None
            if col is None:
                columns[target] = np.full(len(df), np.nan)
                continue
            vals = pd.to_numeric(df[col], errors="coerce").to_numpy(dtype=float, copy=True)
            fill = np.abs(vals) >= cls.FILL_LIMITS[target]
            if target in ("speed", "density", "temperature", "bt"):
                fill |= vals < 0
            n_fill += int(np.sum(fill & np.isfinite(vals)))
            vals[fill] = np.nan
            columns[target] = vals
        if n_fill:
            warnings.append(f"{n_fill} fill / out-of-range value(s) were treated as missing.")
        if not any(found.values()):
            accepted = ", ".join(f"{k} ({'/'.join(v[:3])})" for k, v in cls.COLUMN_MAPPINGS.items() if k != "time_tag")
            return {"error": f"No recognised solar wind column among: {', '.join(str(c) for c in df.columns[:12] if c != '_t')}. "
                             f"Accepted names (case, spaces and units in brackets are ignored): {accepted}."}
        used = {cls._find_column(df.columns, t) for t in found if found[t]} | {time_col}
        ignored = [str(c) for c in df.columns if c not in used and c != "_t"
                   and cls._normalise_header(c) not in ("year", "yyyy", "yr", "doy", "day", "ddd", "hr", "hour", "mn", "min", "minute",
                                                        "mission", "data_source",
                                                        # derived quantities, recomputed from the inputs
                                                        "dynamic_pressure", "magnetopause_re", "akasofu_gw", "l1_travel_time_min")]
        if ignored:
            warnings.append(f"Column(s) not used: {', '.join(ignored[:10])}" + (" ..." if len(ignored) > 10 else "") + ".")

        # GSE -> GSM where the file has no GSM components of its own.
        has_gse = found["by_gse"] and found["bz_gse"]
        if not found["bx_gsm"] and found["bx_gse"]:
            columns["bx_gsm"] = columns["bx_gse"].copy()
        if has_gse and not (found["by_gsm"] or found["bz_gsm"]):
            _, columns["by_gsm"], columns["bz_gsm"] = gse_to_gsm(
                df["_t"].to_numpy(), columns["bx_gse"], columns["by_gse"], columns["bz_gse"])
            warnings.append("By/Bz were converted from GSE to GSM for each row's time "
                            "(Hapgood 1992, IGRF-14 dipole axis).")

        spd, dens = columns["speed"], columns["density"]
        bx, by, bz, bt = columns["bx_gsm"], columns["by_gsm"], columns["bz_gsm"], columns["bt"]
        # |B| from components only where no measured magnitude exists.
        bt = np.where(np.isfinite(bt), bt, np.sqrt(bx ** 2 + by ** 2 + bz ** 2))

        # Vectorised derived quantities (same formulas as SpaceWeatherPhysics).
        with np.errstate(invalid="ignore", divide="ignore"):
            pdyn = np.where((dens > 0) & (spd > 0), 1.6726e-6 * dens * spd ** 2, np.nan)
            standoff = (10.22 + 1.29 * np.tanh(0.184 * (bz + 8.14))) * pdyn ** (-1.0 / 6.6)
            theta = np.arctan2(np.abs(by), bz)
            eps_gw = ((4.0 * np.pi / 1.25663706e-6) * (spd * 1e3) * (bt * 1e-9) ** 2
                      * np.sin(theta / 2.0) ** 4 * (7.0 * 6371000.0) ** 2) / 1e9
            delay = np.where(spd > 0, np.maximum(0.0, 1500000.0 - 90000.0) / spd / 60.0, np.nan)

        def col_out(arr, nd):
            return [None if not np.isfinite(v) else round(float(v), nd) for v in arr]

        time_tags = df["_t"].dt.strftime("%Y-%m-%d %H:%M:%S").tolist()
        out_cols = {
            "speed": col_out(spd, 1),
            "density": col_out(dens, 2),
            "temperature": col_out(columns["temperature"], 0),
            "bx_gsm": col_out(bx, 2),
            "by_gsm": col_out(by, 2),
            "bz_gsm": col_out(bz, 2),
            "bt": col_out(bt, 2),
            "dynamic_pressure": col_out(pdyn, 3),
            "magnetopause_re": col_out(standoff, 2),
            "akasofu_gw": col_out(eps_gw, 2),
            "l1_travel_time_min": col_out(delay, 1),
        }
        if has_gse:
            for key in ("bx_gse", "by_gse", "bz_gse"):
                out_cols[key] = col_out(columns[key], 2)
        records: List[Dict[str, Any]] = []
        for i, t in enumerate(time_tags):
            rec = {"time_tag": t, "mission": mission_name}
            for key, vals in out_cols.items():
                rec[key] = vals[i]
            rec["data_source"] = "imported"
            records.append(rec)

        shocks = SpaceWeatherPhysics.detect_interplanetary_shocks(records)

        def stat(key, fn, nd):
            vals = [r[key] for r in records if r[key] is not None]
            return round(fn(vals), nd) if vals else None

        summary = {
            "total_records": len(records),
            "start_time": records[0]["time_tag"] if records else None,
            "end_time": records[-1]["time_tag"] if records else None,
            "speed_min": stat("speed", min, 1),
            "speed_max": stat("speed", max, 1),
            "speed_mean": stat("speed", lambda v: sum(v) / len(v), 1),
            "bz_min": stat("bz_gsm", min, 2),
            "bz_max": stat("bz_gsm", max, 2),
            "bz_mean": stat("bz_gsm", lambda v: sum(v) / len(v), 2),
            "pdyn_max": stat("dynamic_pressure", max, 2),
            "standoff_min": stat("magnetopause_re", min, 2),
            "akasofu_max": stat("akasofu_gw", max, 1),
            "shocks_detected": len(shocks),
            "time_standard": "UTC"
        }

        return {
            "status": "success",
            "mission_name": mission_name,
            "total_records": len(records),
            "records": records,
            "summary": summary,
            "detected_shocks": shocks,
            "warnings": warnings
        }
