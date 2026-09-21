"""
Multi-mission satellite comparator and cross-calibration engine.
Performs time synchronization, cross-correlation, lag estimation,
and sensor residual analysis between L1 and space weather spacecraft.
"""
import math
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional, Tuple
from helios.core.orbital_mechanics import OrbitalMechanics

class SatelliteComparator:
    """Compares and calibrates observations across multiple satellites."""

    @staticmethod
    def align_time_series(
        data_a: List[Dict[str, Any]],
        data_b: List[Dict[str, Any]],
        parameter: str = "bz_gsm",
        freq: str = "5min"
    ) -> pd.DataFrame:
        """
        Resample and align two satellite telemetry streams to a uniform time grid.
        Handles asynchronous timestamps and missing readings.
        """
        if not data_a or not data_b:
            return pd.DataFrame()

        df_a = pd.DataFrame(data_a)
        df_b = pd.DataFrame(data_b)

        if "time_tag" not in df_a.columns or "time_tag" not in df_b.columns:
            return pd.DataFrame()

        df_a["time"] = pd.to_datetime(df_a["time_tag"])
        df_b["time"] = pd.to_datetime(df_b["time_tag"])

        # Keep parameter and resample
        if parameter not in df_a.columns or parameter not in df_b.columns:
            return pd.DataFrame()

        s_a = df_a.set_index("time")[parameter].resample(freq).mean().interpolate(method="time")
        s_b = df_b.set_index("time")[parameter].resample(freq).mean().interpolate(method="time")

        combined = pd.DataFrame({
            "val_a": s_a,
            "val_b": s_b
        }).dropna()

        return combined

    @staticmethod
    def compute_metrics(series_a: np.ndarray, series_b: np.ndarray) -> Dict[str, float]:
        """
        Compute rigorous scientific comparison statistics:
        - Pearson correlation coefficient (r)
        - Coefficient of determination (R^2)
        - Root Mean Square Error (RMSE)
        - Mean Absolute Error (MAE)
        - Mean Bias (mean(A) - mean(B))
        - Linear calibration slope and intercept
        """
        if len(series_a) < 3 or len(series_b) < 3:
            return {
                "correlation_r": 0.0,
                "r_squared": 0.0,
                "rmse": 0.0,
                "mae": 0.0,
                "bias": 0.0,
                "slope": 1.0,
                "intercept": 0.0
            }

        diff = series_a - series_b
        rmse = float(np.sqrt(np.mean(diff ** 2)))
        mae = float(np.mean(np.abs(diff)))
        bias = float(np.mean(diff))

        # Pearson r
        corr_matrix = np.corrcoef(series_a, series_b)
        r = float(corr_matrix[0, 1]) if not np.isnan(corr_matrix[0, 1]) else 0.0
        r2 = float(r ** 2)

        # Linear regression calibration: A = slope * B + intercept
        p = np.polyfit(series_b, series_a, 1)
        slope = float(p[0])
        intercept = float(p[1])

        return {
            "correlation_r": round(r, 4),
            "r_squared": round(r2, 4),
            "rmse": round(rmse, 3),
            "mae": round(mae, 3),
            "bias": round(bias, 3),
            "slope": round(slope, 4),
            "intercept": round(intercept, 3)
        }

    @staticmethod
    def cross_correlation_lag(
        series_a: np.ndarray,
        series_b: np.ndarray,
        max_lags: int = 24,
        dt_minutes: float = 5.0
    ) -> Dict[str, Any]:
        """
        Calculate cross-correlation as a function of time lag tau.
        Used to experimentally measure the solar wind transit delay
        between satellites at different L1 positions or between L1 and Earth.
        """
        if len(series_a) < max_lags * 2 or len(series_b) < max_lags * 2:
            return {"lags_minutes": [], "correlation": [], "optimal_lag_minutes": 0.0, "max_correlation": 0.0}

        a_norm = (series_a - np.mean(series_a)) / (np.std(series_a) if np.std(series_a) > 0 else 1.0)
        b_norm = (series_b - np.mean(series_b)) / (np.std(series_b) if np.std(series_b) > 0 else 1.0)

        corr = np.correlate(a_norm, b_norm, mode="full") / len(series_a)
        lags = np.arange(-len(series_a) + 1, len(series_a))

        # Filter within [-max_lags, +max_lags]
        mask = (lags >= -max_lags) & (lags <= max_lags)
        sub_lags = lags[mask]
        sub_corr = corr[mask]

        best_idx = np.argmax(sub_corr)
        optimal_lag_min = float(sub_lags[best_idx] * dt_minutes)
        max_r = float(sub_corr[best_idx])

        return {
            "lags_minutes": [float(l * dt_minutes) for l in sub_lags],
            "correlation": [round(float(c), 4) for c in sub_corr],
            "optimal_lag_minutes": round(optimal_lag_min, 1),
            "max_correlation": round(max_r, 4)
        }

    @classmethod
    def compute_spatial_baseline(
        cls,
        mission_a_name: str,
        mission_b_name: str,
        v_sw_mean: float = 450.0
    ) -> Dict[str, Any]:
        """
        Compute inter-spacecraft separation vector (GSE coordinates)
        and theoretical solar wind propagation delay between two missions.
        """
        orbits = OrbitalMechanics.get_satellite_orbits()

        def find_pos(name: str):
            clean = name.upper().replace("-", "_").replace(" ", "_")
            for k, orb in orbits.items():
                if k in clean or clean in k or orb["name"].upper() in clean:
                    return orb["current_pos"]
            return {"x": -1496.0, "y": 0.0, "z": 0.0}

        pos_a = find_pos(mission_a_name)
        pos_b = find_pos(mission_b_name)

        # Positions are in 1000s of km relative to Earth
        dx_km = (pos_a["x"] - pos_b["x"]) * 1000.0
        dy_km = (pos_a["y"] - pos_b["y"]) * 1000.0
        dz_km = (pos_a["z"] - pos_b["z"]) * 1000.0

        r_e_km = 6371.0
        dist_km = math.sqrt(dx_km**2 + dy_km**2 + dz_km**2)
        dist_re = dist_km / r_e_km

        # Theoretical Sunward propagation delay delta_t = delta_x / v_sw
        # In GSE frame, -X is Sunward. If Spacecraft A is more Sunward than B (pos_a.x < pos_b.x),
        # then dx = (x_a - x_b) < 0, meaning plasma arrives at A before B.
        v_sw = max(250.0, float(v_sw_mean))
        theoretical_delay_sec = (-dx_km) / v_sw
        theoretical_delay_min = theoretical_delay_sec / 60.0

        return {
            "dx_km": round(dx_km, 1),
            "dy_km": round(dy_km, 1),
            "dz_km": round(dz_km, 1),
            "distance_km": round(dist_km, 1),
            "distance_re": round(dist_re, 2),
            "theoretical_delay_min": round(theoretical_delay_min, 1),
            "v_sw_assumed_kms": round(v_sw, 1)
        }

    @classmethod
    def compare_satellites(
        cls,
        telemetry_a: List[Dict[str, Any]],
        telemetry_b: List[Dict[str, Any]],
        mission_a_name: str,
        mission_b_name: str,
        parameter: str = "bz_gsm"
    ) -> Dict[str, Any]:
        """Full comparative analysis between two satellite telemetry sets."""
        aligned_df = cls.align_time_series(telemetry_a, telemetry_b, parameter=parameter)
        if aligned_df.empty or len(aligned_df) < 5:
            return {
                "status": "insufficient_data",
                "mission_a": mission_a_name,
                "mission_b": mission_b_name,
                "parameter": parameter,
                "data_points": 0
            }

        arr_a = aligned_df["val_a"].to_numpy()
        arr_b = aligned_df["val_b"].to_numpy()

        metrics = cls.compute_metrics(arr_a, arr_b)
        lag_analysis = cls.cross_correlation_lag(arr_a, arr_b)

        # Estimate average solar wind speed in window for baseline delay
        speeds = [r["speed"] for r in telemetry_a if "speed" in r and isinstance(r["speed"], (int, float))]
        v_mean = float(np.mean(speeds)) if speeds else 450.0
        spatial_baseline = cls.compute_spatial_baseline(mission_a_name, mission_b_name, v_sw_mean=v_mean)

        # Cross-calibration fidelity & coherence index (0 - 100%)
        r = metrics.get("correlation_r", 0.0)
        rmse = metrics.get("rmse", 0.0)
        mean_mag = float(np.mean(np.abs(arr_a))) if len(arr_a) > 0 else 1.0
        rel_err = min(1.0, rmse / max(1.0, mean_mag))
        fidelity = max(5.0, min(100.0, (max(0.0, r)**2 * 60.0 + (1.0 - rel_err) * 40.0)))
        metrics["fidelity_index_pct"] = round(fidelity, 1)

        # Discrepancy between theoretical transit delay and observed empirical lag
        optimal_lag = lag_analysis.get("optimal_lag_minutes", 0.0)
        theory_lag = spatial_baseline["theoretical_delay_min"]
        spatial_baseline["lag_discrepancy_min"] = round(optimal_lag - theory_lag, 1)

        # Scatter samples for plotting
        sample_step = max(1, len(aligned_df) // 100)
        scatter_points = [
            {"x": round(float(b), 2), "y": round(float(a), 2), "time": str(t)}
            for t, a, b in zip(
                aligned_df.index[::sample_step],
                arr_a[::sample_step],
                arr_b[::sample_step]
            )
        ]

        # Residuals
        residuals = [round(float(a - b), 3) for a, b in zip(arr_a[::sample_step], arr_b[::sample_step])]

        return {
            "status": "success",
            "mission_a": mission_a_name,
            "mission_b": mission_b_name,
            "parameter": parameter,
            "data_points": len(aligned_df),
            "metrics": metrics,
            "lag_analysis": lag_analysis,
            "spatial_baseline": spatial_baseline,
            "scatter_points": scatter_points,
            "residuals": residuals,
            "times": [str(t) for t in aligned_df.index[::sample_step]]
        }

    @classmethod
    def compute_fleet_matrix(
        cls,
        telemetry_map: Dict[str, List[Dict[str, Any]]],
        parameter: str = "bz_gsm"
    ) -> Dict[str, Any]:
        """
        Computes mutual NxN cross-correlation and discrepancy matrices
        across all active space weather spacecraft.
        """
        missions = list(telemetry_map.keys())
        n = len(missions)
        matrix_r = [[1.0] * n for _ in range(n)]
        matrix_rmse = [[0.0] * n for _ in range(n)]
        pairs_summary = {}

        for i in range(n):
            for j in range(i + 1, n):
                m_a = missions[i]
                m_b = missions[j]
                data_a = telemetry_map[m_a]
                data_b = telemetry_map[m_b]

                aligned = cls.align_time_series(data_a, data_b, parameter=parameter)
                if not aligned.empty and len(aligned) >= 5:
                    arr_a = aligned["val_a"].to_numpy()
                    arr_b = aligned["val_b"].to_numpy()
                    met = cls.compute_metrics(arr_a, arr_b)
                    r_val = met["correlation_r"]
                    rmse_val = met["rmse"]
                else:
                    r_val = 0.0
                    rmse_val = 0.0

                matrix_r[i][j] = r_val
                matrix_r[j][i] = r_val
                matrix_rmse[i][j] = rmse_val
                matrix_rmse[j][i] = rmse_val

                pair_key = f"{m_a}__{m_b}"
                pairs_summary[pair_key] = {
                    "mission_a": m_a,
                    "mission_b": m_b,
                    "r": r_val,
                    "rmse": rmse_val
                }

        return {
            "missions": missions,
            "parameter": parameter,
            "matrix_r": matrix_r,
            "matrix_rmse": matrix_rmse,
            "pairs": pairs_summary
        }

