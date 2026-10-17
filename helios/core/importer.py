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

from helios.core.science import PDYN_NPA_PER_CM3_KMS2, SpaceWeatherPhysics
from helios.core.archive import parse_hapi_csv
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

    # Examples for trying the import pipeline: OMNI 5-minute data (NASA CDAWeb) of famous
    # intervals, cut from the copy bundled for the historical events (helios/data/omni_events.json.gz).
    PRESETS: Dict[str, Dict[str, Any]] = {
        "may2024_g5": {"name": "May 10-11, 2024 G5 Superstorm", "tag": "G5 EXTREME", "badge_color": "rose",
                       "event": "may_2024_g5", "window": ("2024-05-10 12:00", "2024-05-11 06:00"),
                       "description": "Shock at 17:05 UT on 10 May, then Bz down to -44 nT and over 50 nPa."},
        "bastille_2000": {"name": "July 15, 2000 Bastille Day CME", "tag": "G5 SUPERSTORM", "badge_color": "amber",
                          "event": "bastille_2000", "window": ("2000-07-15 12:00", "2000-07-16 00:00"),
                          "description": "Shock at 14:40 UT, speed above 1000 km/s, Bz down to -59 nT (Dst -301 nT)."},
        "st_patricks_2015": {"name": "March 17, 2015 St. Patrick's Day Storm", "tag": "G4 SEVERE", "badge_color": "amber",
                             "event": "st_patricks_2015", "window": ("2015-03-17 00:00", "2015-03-17 18:00"),
                             "description": "Shock near 04:45 UT, then hours of southward Bz down to -25 nT."},
        "quiet_wind": {"name": "Quiet Solar Wind, 7 December 2019", "tag": "G0 NOMINAL", "badge_color": "emerald",
                       "event": "quiet_baseline", "window": ("2019-12-07 00:00", "2019-12-07 12:00"),
                       "description": "Slow wind near 360 km/s and a weak field at solar minimum (Kp 1- or lower)."},
    }
    PRESET_NOTE = "OMNI 5-minute means (NASA CDAWeb), time-shifted to the bow shock nose."

    @classmethod
    def get_presets_list(cls) -> List[Dict[str, Any]]:
        """Metadata of the example datasets."""
        out = []
        for pid in cls.PRESETS:
            p = cls.get_preset(pid)
            out.append({k: p[k] for k in ("id", "name", "tag", "badge_color", "satellite", "description")}
                       | {"records_count": p["csv_content"].count("\n"), "data_kind": "observed", "note": cls.PRESET_NOTE})
        return out

    @classmethod
    def get_preset(cls, preset_id: str) -> Optional[Dict[str, Any]]:
        """One example dataset with its CSV text (time, speed, density, field components)."""
        spec = cls.PRESETS.get(preset_id)
        if spec is None:
            return None
        from helios.core.downloader import omni_snapshot
        snap = omni_snapshot(spec["event"])
        cols = ["time_tag", "speed", "density", "bx_gsm", "by_gsm", "bz_gsm", "bt"]
        idx = [snap["columns"].index(c) for c in cols]
        a, b = spec["window"]
        rows = [",".join("" if r[i] is None else str(r[i]) for i in idx) for r in snap["rows"] if a <= r[0][:16] < b]
        return dict(spec, id=preset_id, satellite="OMNI (NASA CDAWeb)",
                    csv_content="time,speed,density,bx_gsm,by_gsm,bz_gsm,bt\n" + "\n".join(rows))

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
            df = pd.DataFrame(obj)
            if "active" in df.columns and df["active"].isin([True, False]).all():
                # NOAA RTSW JSON lists the active spacecraft and the standby one minute by minute
                df = df[df["active"].astype(bool)]
            if "overall_quality" in df.columns:  # RTSW: non-zero means a flagged sample, as in the live feed
                df = df[df["overall_quality"].fillna(0) == 0]
            return df
        all_lines = text.splitlines()
        lines = [ln for ln in all_lines if ln.strip() and not ln.lstrip().startswith("#")]
        if all_lines[0].lstrip("#").strip().startswith("{"):
            # HAPI CSV with its '#'-commented JSON header (CDAWeb and other HAPI servers,
            # include=header): names and fill values from the header, as for the archive.
            df = parse_hapi_csv(text).reset_index()
            for c in [c for c in df.columns if c.endswith("_0")]:
                base = c[:-2]
                if f"{base}_2" in df.columns and f"{base}_3" not in df.columns:
                    df = df.rename(columns={f"{base}_{i}": f"{base}_{a}" for i, a in enumerate("xyz")})
            return df
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
        'Z'/offset; offsets are converted to UTC), OMNI-style YEAR, DOY, HR, MN columns, or
        YEAR, MONTH, DAY (day of month), HR, MN columns.
        Unparseable rows become NaT.
        """
        lower = {c.lower().strip(): c for c in df.columns}
        year_c = lower.get("year") or lower.get("yyyy") or lower.get("yr")
        month_c = lower.get("month") or lower.get("mon") or lower.get("mo")
        # With a month column, "day" is the day of the month (it used to be read as the day
        # of the year, putting every row in January).
        dom_c = (lower.get("day") or lower.get("dd") or lower.get("dom")) if month_c else None
        doy_c = lower.get("doy") or lower.get("ddd") or (None if month_c else lower.get("day"))
        day_c = dom_c or doy_c
        if year_c and day_c and (time_col is None or time_col in (year_c, day_c)):
            hour_c = lower.get("hr") or lower.get("hour")
            min_c = lower.get("mn") or lower.get("min") or lower.get("minute")
            num = lambda c: pd.to_numeric(df[c], errors="coerce")
            if dom_c:
                base = pd.to_datetime(pd.DataFrame({"year": num(year_c), "month": num(month_c), "day": num(dom_c)}),
                                      errors="coerce", utc=True)
                offset = pd.to_timedelta(pd.Series(0, index=df.index), unit="D")
            else:
                base = pd.to_datetime(num(year_c).astype("Int64").astype(str), format="%Y", errors="coerce", utc=True)
                offset = pd.to_timedelta(num(doy_c) - 1, unit="D")
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
            pdyn = np.where((dens > 0) & (spd > 0), PDYN_NPA_PER_CM3_KMS2 * dens * spd ** 2, np.nan)
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
