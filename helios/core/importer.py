"""
Custom telemetry ingestion and file import engine for HELIOS-L1.
Supports NASA CDAWeb / OMNI ASCII formats, ISRO Aditya-L1 formats,
and arbitrary user-uploaded CSV / JSON space weather time-series.
"""
import io
import re
import csv
import json
import pandas as pd
from datetime import datetime
from typing import Dict, List, Any, Optional

from helios.core.science import SpaceWeatherPhysics

class TelemetryImporter:
    """Parses, validates, and normalizes space weather telemetry files."""

    COLUMN_MAPPINGS = {
        "speed": ["speed", "vsw", "v_sw", "velocity", "flow_speed", "bulk_speed", "v_bulk", "ion_speed"],
        "density": ["density", "np", "n_p", "proton_density", "ion_density", "plasma_density"],
        "temperature": ["temperature", "temp", "tp", "t_p", "thermal_temp"],
        "bx_gsm": ["bx_gsm", "bx", "b_x", "b_gsm_x"],
        "by_gsm": ["by_gsm", "by", "b_y", "b_gsm_y"],
        "bz_gsm": ["bz_gsm", "bz", "b_z", "b_gsm_z"],
        "bt": ["bt", "b_total", "total_b", "b_mag", "magnitude"],
        "time_tag": ["time_tag", "time", "timestamp", "datetime", "date_time", "epoch", "utc"]
    }

    @classmethod
    def _find_column(cls, df_columns: List[str], target: str) -> Optional[str]:
        target_candidates = cls.COLUMN_MAPPINGS.get(target, [target])
        col_lower_map = {c.lower().strip(): c for c in df_columns}
        for candidate in target_candidates:
            if candidate in col_lower_map:
                return col_lower_map[candidate]
        return None

    @classmethod
    def parse_csv_or_text(cls, content: str, mission_name: str = "Custom Spacecraft") -> Dict[str, Any]:
        """
        Parse CSV or delimited ASCII text telemetry.
        Auto-identifies NASA OMNI, NOAA, or custom header schemas.
        """
        try:
            # Check for header
            df = pd.read_csv(io.StringIO(content), sep=None, engine="python")
        except Exception as e:
            return {"error": f"Failed to parse text format: {str(e)}"}

        if df.empty or len(df.columns) < 2:
            return {"error": "Dataset must contain at least 2 columns (time and physical parameter)."}

        # Resolve columns
        time_col = cls._find_column(df.columns, "time_tag")
        if not time_col:
            # Assume first column is time
            time_col = df.columns[0]

        speed_col = cls._find_column(df.columns, "speed")
        density_col = cls._find_column(df.columns, "density")
        bz_col = cls._find_column(df.columns, "bz_gsm")
        by_col = cls._find_column(df.columns, "by_gsm")
        bx_col = cls._find_column(df.columns, "bx_gsm")
        bt_col = cls._find_column(df.columns, "bt")

        records: List[Dict[str, Any]] = []
        for _, row in df.iterrows():
            t_raw = str(row[time_col]).strip()
            # Clean numeric values
            spd = float(row[speed_col]) if (speed_col and pd.notna(row[speed_col])) else 400.0
            dens = float(row[density_col]) if (density_col and pd.notna(row[density_col])) else 5.0
            bz = float(row[bz_col]) if (bz_col and pd.notna(row[bz_col])) else 0.0
            by = float(row[by_col]) if (by_col and pd.notna(row[by_col])) else 0.0
            bx = float(row[bx_col]) if (bx_col and pd.notna(row[bx_col])) else 0.0
            bt = float(row[bt_col]) if (bt_col and pd.notna(row[bt_col])) else (bx**2 + by**2 + bz**2)**0.5

            pdyn = SpaceWeatherPhysics.dynamic_pressure(dens, spd)
            standoff = SpaceWeatherPhysics.magnetopause_standoff(pdyn, bz)
            eps = SpaceWeatherPhysics.akasofu_epsilon(spd, bt, by, bz)
            delay = SpaceWeatherPhysics.propagation_delay_minutes(1500000.0, spd)

            records.append({
                "time_tag": t_raw,
                "mission": mission_name,
                "speed": round(spd, 1),
                "density": round(dens, 2),
                "bx_gsm": round(bx, 2),
                "by_gsm": round(by, 2),
                "bz_gsm": round(bz, 2),
                "bt": round(bt, 2),
                "dynamic_pressure": round(pdyn, 2),
                "magnetopause_re": standoff,
                "akasofu_gw": round(eps, 1),
                "l1_travel_time_min": delay
            })

        shocks = SpaceWeatherPhysics.detect_interplanetary_shocks(records)

        return {
            "status": "success",
            "mission_name": mission_name,
            "total_records": len(records),
            "records": records,
            "detected_shocks": shocks
        }
