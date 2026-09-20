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

class DataExporter:
    """Exports space weather telemetry and scientific figures."""

    @staticmethod
    def to_csv(records: List[Dict[str, Any]]) -> str:
        """Export telemetry records to clean standard CSV string."""
        if not records:
            return ""
        output = io.StringIO()
        fieldnames = list(records[0].keys())
        writer = csv.DictWriter(output, fieldnames=fieldnames)
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

        df = pd.DataFrame(records)
        variables = {}
        for col in df.columns:
            if col != "time_tag":
                variables[col] = {
                    "data": df[col].tolist(),
                    "units": "nT" if "b" in col else ("km/s" if "speed" in col else ("cm^-3" if "dens" in col else "nPa"))
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
