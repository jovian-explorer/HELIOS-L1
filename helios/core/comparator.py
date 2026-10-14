"""
Multi-mission satellite comparator and cross-calibration engine.
Performs time synchronization, cross-correlation, lag estimation,
and sensor residual analysis between L1 and space weather spacecraft.
"""
import math
import numpy as np
import pandas as pd
from typing import Dict, List, Any, Optional
from helios.core.orbital_mechanics import OrbitalMechanics
from helios.core.statistics import correlation, effective_sample_size

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

        # Parse as UTC so naive stamps ("2026-10-02 18:00:00") and ones carrying an offset
        # ("...Z", "+05:30") can be aligned; mixing them used to raise a pandas TypeError.
        df_a["time"] = pd.to_datetime(df_a["time_tag"], utc=True, errors="coerce")
        df_b["time"] = pd.to_datetime(df_b["time_tag"], utc=True, errors="coerce")
        df_a = df_a.dropna(subset=["time"])
        df_b = df_b.dropna(subset=["time"])

        # Keep parameter and resample
        if parameter not in df_a.columns or parameter not in df_b.columns:
            return pd.DataFrame()

        # Bridge only short interior gaps (up to 3 bins); longer gaps stay missing and are
        # excluded, instead of being filled with straight lines that inflate correlations.
        def to_grid(df, max_gap_bins: int = 3):
            values = pd.to_numeric(df.set_index("time")[parameter], errors="coerce")
            gridded = values.resample(freq).mean()
            missing = gridded.isna()
            run_id = (missing != missing.shift()).cumsum()
            run_len = missing.groupby(run_id).transform("sum")
            filled = gridded.interpolate(method="time", limit_area="inside")
            # pandas' `limit` would still fill the first bins of a long gap; blank whole long gaps.
            filled[missing & (run_len > max_gap_bins)] = np.nan
            return filled

        s_a = to_grid(df_a)
        s_b = to_grid(df_b)

        combined = pd.DataFrame({
            "val_a": s_a,
            "val_b": s_b
        }).dropna()

        return combined

    @staticmethod
    def compute_metrics(series_a: np.ndarray, series_b: np.ndarray) -> Dict[str, float]:
        """
        Compute rigorous scientific comparison statistics:
        - Pearson correlation coefficient (r), with its 95 % interval from the Fisher z
          transform and the effective sample size of the two autocorrelated series
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
        # A constant series has no correlation: None, not 0 (which reads as "measured to disagree").
        r = float(corr_matrix[0, 1]) if not np.isnan(corr_matrix[0, 1]) else None
        r2 = float(r ** 2) if r is not None else None

        # Linear regression calibration: A = slope * B + intercept
        p = np.polyfit(series_b, series_a, 1)
        slope = float(p[0])
        intercept = float(p[1])

        corr = correlation(series_a, series_b)  # 95 % interval allowing for autocorrelation
        return {
            "correlation_r": round(r, 4) if r is not None else None,
            "correlation_ci95": [round(v, 4) for v in corr["ci95"]] if corr["ci95"] else None,
            "n_eff": round(corr["n_eff"], 1) if corr["n_eff"] is not None else None,
            "r_squared": round(r2, 4) if r2 is not None else None,
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

        Sign convention: a positive lag means spacecraft B observes the same structure
        later than spacecraft A, i.e. b(t) ~ a(t - lag). This matches the sign of the
        theoretical_delay_min returned by compute_spatial_baseline.
        """
        if len(series_a) < max_lags * 2 or len(series_b) < max_lags * 2:
            return {"lags_minutes": [], "correlation": [], "optimal_lag_minutes": 0.0, "max_correlation": 0.0}

        # Missing samples (NaN) keep their place on the time grid, so a shift of L samples is
        # always L * dt minutes.
        a_norm = (series_a - np.nanmean(series_a)) / (np.nanstd(series_a) or 1.0)
        b_norm = (series_b - np.nanmean(series_b)) / (np.nanstd(series_b) or 1.0)

        # corr[k]: Pearson r of the pairs (a[n], b[n + L]) with both present, L = lags[k];
        # peaks at L > 0 when B lags A.
        n = len(series_a)
        lags = np.arange(-max_lags, max_lags + 1)
        corr = np.zeros(len(lags))
        for k, lag in enumerate(lags):
            x, y = (series_a[:n - lag], series_b[lag:]) if lag >= 0 else (series_a[-lag:], series_b[:n + lag])
            ok = np.isfinite(x) & np.isfinite(y)
            if ok.sum() > 2 and np.std(x[ok]) > 0 and np.std(y[ok]) > 0:
                corr[k] = np.corrcoef(x[ok], y[ok])[0, 1]
        sub_lags, sub_corr = lags, corr

        best_idx = np.argmax(sub_corr)
        optimal_lag_min = float(sub_lags[best_idx] * dt_minutes)
        max_r = float(sub_corr[best_idx])

        return {
            "lags_minutes": [float(l * dt_minutes) for l in sub_lags],
            "correlation": [round(float(c), 4) for c in sub_corr],
            "optimal_lag_minutes": round(optimal_lag_min, 1),
            "max_correlation": round(max_r, 4),
            "lag_convention": "positive = B observes later than A",
            **SatelliteComparator.lag_uncertainty(a_norm, b_norm, sub_lags, dt_minutes),
        }

    @staticmethod
    def lag_uncertainty(a_norm: np.ndarray, b_norm: np.ndarray, lags: np.ndarray, dt_minutes: float,
                        n_boot: int = 500, seed: int = 1) -> Dict[str, Any]:
        """
        95 % interval of the cross-correlation lag from a moving-block bootstrap (Kunsch 1989)
        of the lagged products a[n] b[n + L]: blocks of consecutive samples n are resampled,
        every lag is re-evaluated on the same resampled samples and the peak is located again.
        Blocks are as long as the decorrelation length n / n_eff of the pair (at least the
        largest lag), so that the resamples keep the autocorrelation of the data.
        """
        n = len(a_norm)
        lags = np.asarray(lags, dtype=int)
        prod = np.full((len(lags), n), np.nan)
        for k, lag in enumerate(lags):
            if lag >= 0:
                prod[k, :n - lag] = a_norm[:n - lag] * b_norm[lag:]
            else:
                prod[k, -lag:] = a_norm[-lag:] * b_norm[:n + lag]
        # Missing pairs (gaps, ends) are left out: the mean product over the pairs present.
        valid = np.isfinite(prod)
        prod = np.where(valid, prod, 0.0)
        ok = np.isfinite(a_norm) & np.isfinite(b_norm)
        n_eff = effective_sample_size(a_norm[ok], b_norm[ok])
        block = int(min(max(int(np.max(np.abs(lags))), math.ceil(n / max(n_eff, 1.0))), max(1, n // 4)))
        rng = np.random.default_rng(seed)
        n_blocks = int(math.ceil(n / block))
        starts = rng.integers(0, n - block + 1, size=(n_boot, n_blocks))
        idx = (starts[:, :, None] + np.arange(block)[None, None, :]).reshape(n_boot, -1)[:, :n]
        counts = np.zeros((n_boot, n))
        np.add.at(counts, (np.repeat(np.arange(n_boot), n), idx.ravel()), 1.0)
        boot_lags = lags[np.argmax((counts @ prod.T) / np.maximum(counts @ valid.T, 1.0), axis=1)] * dt_minutes
        lo, hi = np.percentile(boot_lags, [2.5, 97.5])
        return {
            "lag_ci95_minutes": [round(float(lo), 1), round(float(hi), 1)],
            "lag_std_minutes": round(float(np.std(boot_lags)), 1),
            "lag_uncertainty_method": (f"moving-block bootstrap of the lagged products ({n_boot} resamples, "
                                       f"blocks of {block} samples); lag resolution {dt_minutes:g} min"),
        }

    @classmethod
    def compute_spatial_baseline(
        cls,
        mission_a_name: str,
        mission_b_name: str,
        v_sw_mean: float = 450.0,
        position_a: Optional[Dict[str, Any]] = None,
        position_b: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Compute inter-spacecraft separation vector (GSE coordinates)
        and theoretical solar wind propagation delay between two missions.

        position_a / position_b ({"x_km", "y_km", "z_km", "source"}, GSE) override the model
        orbit of a mission, e.g. with the NOAA ephemeris of the spacecraft that actually
        supplied the data (SOLAR1 for the operational "DSCOVR" stream).
        """
        orbits = OrbitalMechanics.get_satellite_orbits()

        def find_pos(name: str):
            clean = name.upper().replace("-", "_").replace(" ", "_")
            for k, orb in orbits.items():
                if k in clean or clean in k or orb["name"].upper() in clean:
                    return orb["current_pos"]
            return {"x": -1496.0, "y": 0.0, "z": 0.0}

        def resolve(name: str, override: Optional[Dict[str, Any]]):
            if override and all(override.get(k) is not None for k in ("x_km", "y_km", "z_km")):
                # True GSE has +X towards the Sun; the model orbits use the visualizer
                # convention with the Sun at -X, so X changes sign (Y and Z are kept).
                pos = {"x": -override["x_km"] / 1000.0, "y": override["y_km"] / 1000.0,
                       "z": override["z_km"] / 1000.0}
                return pos, override.get("source", "ephemeris")
            return find_pos(name), "HELIOS model orbit"

        pos_a, src_a = resolve(mission_a_name, position_a)
        pos_b, src_b = resolve(mission_b_name, position_b)

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
            "v_sw_assumed_kms": round(v_sw, 1),
            "position_source_a": src_a,
            "position_source_b": src_b
        }

    @classmethod
    def compare_satellites(
        cls,
        telemetry_a: List[Dict[str, Any]],
        telemetry_b: List[Dict[str, Any]],
        mission_a_name: str,
        mission_b_name: str,
        parameter: str = "bz_gsm",
        position_a: Optional[Dict[str, Any]] = None,
        position_b: Optional[Dict[str, Any]] = None,
        position_unknown: str = ""
    ) -> Dict[str, Any]:
        """
        Full comparative analysis between two satellite telemetry sets.
        position_a / position_b: optional measured GSE positions (see compute_spatial_baseline).
        position_unknown: why one side has no position (e.g. an imported file); the baseline is
        then left empty instead of being guessed from the name.
        """
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
        # The lag needs the regular time grid: rows dropped for gaps would make a shift of
        # k samples span more than k bins.
        gridded = aligned_df.asfreq("5min")
        lag_analysis = cls.cross_correlation_lag(gridded["val_a"].to_numpy(), gridded["val_b"].to_numpy())

        # Estimate average solar wind speed in window for baseline delay
        speeds = [r["speed"] for r in telemetry_a if "speed" in r and isinstance(r["speed"], (int, float))]
        v_mean = float(np.mean(speeds)) if speeds else 450.0
        if position_unknown:
            spatial_baseline = {k: None for k in ("dx_km", "dy_km", "dz_km", "distance_km", "distance_re",
                                                  "theoretical_delay_min")}
            spatial_baseline.update(v_sw_assumed_kms=None, position_unknown=position_unknown,
                                    position_source_a=None, position_source_b=None)
        else:
            spatial_baseline = cls.compute_spatial_baseline(mission_a_name, mission_b_name, v_sw_mean=v_mean,
                                                            position_a=position_a, position_b=position_b)

        # Cross-calibration fidelity & coherence index (0 - 100%)
        r = metrics.get("correlation_r") or 0.0
        rmse = metrics.get("rmse", 0.0)
        mean_mag = float(np.mean(np.abs(arr_a))) if len(arr_a) > 0 else 1.0
        rel_err = min(1.0, rmse / max(1.0, mean_mag))
        fidelity = max(5.0, min(100.0, (max(0.0, r)**2 * 60.0 + (1.0 - rel_err) * 40.0)))
        metrics["fidelity_index_pct"] = round(fidelity, 1)

        # Discrepancy between theoretical transit delay and observed empirical lag
        optimal_lag = lag_analysis.get("optimal_lag_minutes", 0.0)
        theory_lag = spatial_baseline["theoretical_delay_min"]
        spatial_baseline["lag_discrepancy_min"] = None if theory_lag is None else round(optimal_lag - theory_lag, 1)
        reach = max((abs(x) for x in lag_analysis.get("lags_minutes", [])), default=0.0)
        if theory_lag is not None and abs(theory_lag) > reach:
            # e.g. STEREO-A against an L1 monitor: the same solar wind reaches them days apart
            spatial_baseline["note"] = (f"The expected delay ({theory_lag:.0f} min) lies outside the lag search "
                                        f"(+/-{reach:.0f} min): the two series sample different solar wind, so r "
                                        "and the lag do not describe a calibration.")

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
        # The diagonal is 1 / 0 only for a spacecraft that measured the parameter (SOHO has no
        # magnetometer: its Bz row is empty, diagonal included)
        has = [any(r.get(parameter) is not None for r in telemetry_map[m]) for m in missions]
        matrix_r = [[(1.0 if has[i] else None) if i == j else None for j in range(n)] for i in range(n)]
        matrix_rmse = [[(0.0 if has[i] else None) if i == j else None for j in range(n)] for i in range(n)]
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
                else:  # no common data: nothing to show, not r = 0
                    r_val = None
                    rmse_val = None

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

