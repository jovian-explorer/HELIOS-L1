"""
Scientific data export and report generation engine for HELIOS-L1.
Supports CSV, JSON, NetCDF-compatible schemas, and Matplotlib chart exports.
"""
import io
import csv
import json
from typing import Dict, List, Any
import matplotlib
matplotlib.use("Agg")  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import pandas as pd

# Physical units of the telemetry fields (exports and metadata).
FIELD_UNITS: Dict[str, str] = {
    "time_tag": "UTC (YYYY-MM-DD HH:MM:SS)",
    "speed": "km/s",
    "density": "cm^-3",
    "temperature": "K",
    "bx_gsm": "nT", "by_gsm": "nT", "bz_gsm": "nT",
    "bx_gse": "nT", "by_gse": "nT", "bz_gse": "nT",
    "bt": "nT",
    "hp_mag": "nT",
    "dynamic_pressure": "nPa",
    "magnetopause_re": "R_E",
    "akasofu_gw": "GW",
    "l1_travel_time_min": "min",
    "sym_h": "nT", "asy_h": "nT", "ae": "nT", "al": "nT", "au": "nT",
}


class DataExporter:
    """Exports space weather telemetry and scientific figures."""

    @staticmethod
    def _fieldnames(records: List[Dict[str, Any]]) -> List[str]:
        """Union of the record keys in first-seen order (records need not share keys)."""
        names: Dict[str, None] = {}
        for r in records:
            for k in r.keys():
                names.setdefault(k, None)
        return list(names)

    @staticmethod
    def to_csv(records: List[Dict[str, Any]], metadata: Dict[str, Any] = None) -> str:
        """
        Export telemetry records to a CSV string. Missing values are empty cells.
        With `metadata`, '# key: value' header lines (provenance, units, time standard)
        precede the table; read them with e.g. pandas.read_csv(path, comment='#').
        """
        if not records:
            return ""
        output = io.StringIO()
        fieldnames = DataExporter._fieldnames(records)
        if metadata:
            for key, value in metadata.items():
                if isinstance(value, (list, tuple)):
                    value = ", ".join(str(v) for v in value)
                output.write(f"# {key}: {value}\n")
            units = [f"{f}={FIELD_UNITS[f]}" for f in fieldnames if f in FIELD_UNITS]
            output.write("# units: " + "; ".join(units) + "\n")
        writer = csv.DictWriter(output, fieldnames=fieldnames, restval="", lineterminator="\n")
        writer.writeheader()
        for r in records:
            writer.writerow(r)
        return output.getvalue()

    @staticmethod
    def to_json(records: List[Dict[str, Any]], pretty: bool = True) -> str:
        """Export records to JSON string."""
        indent = 2 if pretty else None
        return json.dumps(records, indent=indent)

    @staticmethod
    def to_netcdf_schema(records: List[Dict[str, Any]], mission_name: str) -> Dict[str, Any]:
        """Format data into a NetCDF-4 / CF-1.8 compliant metadata dictionary."""
        if not records:
            return {}

        variables = {}
        for col in DataExporter._fieldnames(records):
            if col != "time_tag":
                # Units from the field table; the old substring guess labelled e.g.
                # temperature, standoff and epsilon as nPa.
                variables[col] = {
                    "data": [r.get(col) for r in records],
                    "units": FIELD_UNITS.get(col, "1")
                }

        return {
            "title": f"HELIOS-L1 Calibrated Space Weather Telemetry: {mission_name}",
            "conventions": "CF-1.8",
            "source": "HELIOS-L1 Science Data Pipeline",
            "institution": "Space Weather International Collaboration",
            "time_coverage_start": records[0].get("time_tag", ""),
            "time_coverage_end": records[-1].get("time_tag", ""),
            "dimensions": {"time": len(records)},
            "variables": variables
        }

    @staticmethod
    def generate_overview_chart(records: List[Dict[str, Any]], mission_name: str) -> bytes:
        """Generate a 4-panel publication-ready scientific plot."""
        if not records:
            fig, ax = plt.subplots(figsize=(10, 6))
            ax.text(0.5, 0.5, "No data available", ha="center", va="center")
            buf = io.BytesIO()
            plt.savefig(buf, format="png")
            plt.close(fig)
            return buf.getvalue()

        df = pd.DataFrame(records)
        df["dt"] = pd.to_datetime(df["time_tag"])

        plt.style.use("dark_background")
        fig, axes = plt.subplots(4, 1, figsize=(12, 10), sharex=True)
        fig.suptitle(f"HELIOS-L1 Scientific Telemetry: {mission_name}", fontsize=14, color="#38bdf8", weight="bold")

        # Panel 1: IMF Bz and Total B
        ax1 = axes[0]
        if "bz_gsm" in df.columns:
            ax1.plot(df["dt"], df["bz_gsm"], label="IMF Bz (GSM)", color="#f43f5e", lw=1.2)
        if "bt" in df.columns:
            ax1.plot(df["dt"], df["bt"], label="Total |B|", color="#e2e8f0", lw=1.0, alpha=0.8)
        ax1.axhline(0, color="#64748b", ls="--", lw=0.8)
        ax1.axhline(-10, color="#f59e0b", ls=":", lw=1.0, label="Bz Storm Threshold (-10 nT)")
        ax1.set_ylabel("B Field [nT]", fontsize=10)
        ax1.legend(loc="upper right", framealpha=0.3, fontsize=8)
        ax1.grid(True, alpha=0.2)

        # Panel 2: Solar Wind Speed
        ax2 = axes[1]
        if "speed" in df.columns:
            ax2.plot(df["dt"], df["speed"], label="Solar Wind Speed (Vsw)", color="#38bdf8", lw=1.2)
            ax2.axhline(450, color="#eab308", ls=":", lw=0.9, label="Fast Wind Threshold")
        ax2.set_ylabel("Speed [km/s]", fontsize=10)
        ax2.legend(loc="upper right", framealpha=0.3, fontsize=8)
        ax2.grid(True, alpha=0.2)

        # Panel 3: Proton Density
        ax3 = axes[2]
        if "density" in df.columns:
            ax3.plot(df["dt"], df["density"], label="Proton Density (Np)", color="#34d399", lw=1.2)
        ax3.set_ylabel("Density [cm⁻³]", fontsize=10)
        ax3.legend(loc="upper right", framealpha=0.3, fontsize=8)
        ax3.grid(True, alpha=0.2)

        # Panel 4: Dynamic Pressure & Akasofu Epsilon
        ax4 = axes[3]
        if "dynamic_pressure" in df.columns:
            ax4.plot(df["dt"], df["dynamic_pressure"], label="Dynamic Pressure Pdyn", color="#a855f7", lw=1.2)
        ax4.set_ylabel("Pressure [nPa]", fontsize=10)
        ax4.set_xlabel("Time (UTC)", fontsize=10)
        ax4.legend(loc="upper right", framealpha=0.3, fontsize=8)
        ax4.grid(True, alpha=0.2)

        # Format X-axis dates
        axes[3].xaxis.set_major_formatter(mdates.DateFormatter("%m-%d %H:%M"))
        fig.autofmt_xdate()
        plt.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="#0f172a")
        plt.close(fig)
        return buf.getvalue()
