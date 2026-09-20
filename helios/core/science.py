"""
Scientific calculations and space weather physics engine for HELIOS-L1.
Includes magnetohydrodynamic metrics, solar-terrestrial coupling, shock detection,
and Fourier spectral analysis.
"""
import math
import numpy as np
from typing import Dict, List, Any, Optional, Tuple

class SpaceWeatherPhysics:
    """Core physics and geomagnetic coupling calculations."""

    @staticmethod
    def dynamic_pressure(density_cm3: float, speed_kms: float) -> float:
        """
        Calculate solar wind dynamic pressure (P_dyn) in nanoPascals (nPa).
        P_dyn = rho * v^2 = (1.6726e-27 kg * n * 1e6 m^-3) * (v * 1e3 m/s)^2 * 1e9 nPa/Pa
        P_dyn approx 1.6726e-6 * n * v^2
        """
        if density_cm3 is None or speed_kms is None or density_cm3 <= 0 or speed_kms <= 0:
            return 0.0
        return float(1.6726e-6 * density_cm3 * (speed_kms ** 2))

    @staticmethod
    def magnetopause_standoff(dynamic_pressure_npa: float, bz_gsm_nt: float) -> float:
        """
        Estimate Earth's magnetopause subsolar standoff distance (R_mp) in Earth Radii (R_E)
        using the empirical Shue et al. (1998) model.
        Geostationary satellites are at 6.6 R_E. If R_mp < 6.6 R_E, satellites are exposed directly to solar wind!
        """
        if dynamic_pressure_npa <= 0.0:
            return 10.0
        bz = float(bz_gsm_nt if bz_gsm_nt is not None else 0.0)
        # Shue et al.: r0 = (10.22 + 1.29 * tanh(0.184 * (Bz + 8.14))) * (Pdyn)^(-1/6.6)
        r0 = (10.22 + 1.29 * math.tanh(0.184 * (bz + 8.14))) * (dynamic_pressure_npa ** (-1.0 / 6.6))
        return round(float(r0), 2)

    @staticmethod
    def clock_angle(by_gsm_nt: float, bz_gsm_nt: float) -> float:
        """
        Calculate IMF clock angle theta in radians: theta = arctan2(|By|, Bz).
        Clock angle determines reconnection efficiency with Earth's dayside magnetosphere.
        """
        by = float(by_gsm_nt if by_gsm_nt is not None else 0.0)
        bz = float(bz_gsm_nt if bz_gsm_nt is not None else 0.0)
        return float(math.atan2(abs(by), bz))

    @staticmethod
    def akasofu_epsilon(speed_kms: float, b_total_nt: float, by_gsm_nt: float, bz_gsm_nt: float) -> float:
        """
        Calculate Akasofu solar wind energy coupling parameter epsilon (in Gigawatts).
        Epsilon = (v * B^2 / mu_0) * sin^4(theta / 2) * l_0^2
        where l_0 approx 7 R_E (Earth radii = 6371 km).
        Values > 100 GW cause substorms; > 1000 GW trigger major geomagnetic storms.
        """
        if not speed_kms or not b_total_nt or speed_kms <= 0 or b_total_nt <= 0:
            return 0.0
        
        v_ms = speed_kms * 1000.0
        b_tesla = b_total_nt * 1e-9
        mu_0 = 1.25663706e-6
        l0_m = 7.0 * 6371000.0  # ~4.46e7 m
        theta = SpaceWeatherPhysics.clock_angle(by_gsm_nt, bz_gsm_nt)

        sin_term = math.sin(theta / 2.0) ** 4
        energy_rate_watts = (v_ms * (b_tesla ** 2) / mu_0) * sin_term * (l0_m ** 2)
        return float(energy_rate_watts / 1e9)  # Return in Gigawatts (GW)

    @staticmethod
    def newell_coupling(speed_kms: float, by_gsm_nt: float, bz_gsm_nt: float) -> float:
        """
        Newell et al. (2007) universal solar wind-magnetosphere coupling function:
        dPhi/dt = v^(4/3) * B_T^(2/3) * sin^(8/3)(theta / 2)
        """
        if not speed_kms or speed_kms <= 0:
            return 0.0
        by = float(by_gsm_nt if by_gsm_nt is not None else 0.0)
        bz = float(bz_gsm_nt if bz_gsm_nt is not None else 0.0)
        bt = math.sqrt(by**2 + bz**2)
        if bt <= 0:
            return 0.0
        theta = math.atan2(abs(by), bz)
        coupling = (speed_kms ** (4.0 / 3.0)) * (bt ** (2.0 / 3.0)) * (math.sin(theta / 2.0) ** (8.0 / 3.0))
        return float(coupling)

    @staticmethod
    def propagation_delay_minutes(distance_km: float, speed_kms: float) -> float:
        """
        Calculate propagation travel time from satellite location (e.g. L1 at ~1.5 million km)
        to Earth's bow shock (~14 R_E upstream, ~90,000 km) in minutes.
        """
        if not speed_kms or speed_kms <= 0:
            return 45.0  # Nominal default
        effective_dist = max(0.0, distance_km - 90000.0)
        delay_seconds = effective_dist / speed_kms
        return round(float(delay_seconds / 60.0), 1)

    @staticmethod
    def classify_noaa_scales(kp: Optional[float], bz_gsm: Optional[float], xray_flux: Optional[float]) -> Dict[str, Any]:
        """
        Classify Space Weather according to NOAA G-scale (Geomagnetic),
        Bz southward severity, and R-scale (Radio Blackout via X-ray flux).
        """
        # 1. Geomagnetic Storm (G-Scale)
        g_scale = "G0 (Quiet)"
        g_level = 0
        g_color = "#10b981"
        if kp is not None:
            if kp >= 9.0:
                g_scale, g_level, g_color = "G5 (Extreme)", 5, "#dc2626"
            elif kp >= 8.0:
                g_scale, g_level, g_color = "G4 (Severe)", 4, "#ea580c"
            elif kp >= 7.0:
                g_scale, g_level, g_color = "G3 (Strong)", 3, "#f59e0b"
            elif kp >= 6.0:
                g_scale, g_level, g_color = "G2 (Moderate)", 2, "#eab308"
            elif kp >= 5.0:
                g_scale, g_level, g_color = "G1 (Minor)", 1, "#3b82f6"

        # 2. Southward Bz Alert Level
        bz_alert = "Northward (Shielded)"
        bz_color = "#10b981"
        if bz_gsm is not None:
            if bz_gsm <= -15.0:
                bz_alert = "CRITICAL: Intense Southward Reconnection (Bz <= -15 nT)"
                bz_color = "#dc2626"
            elif bz_gsm <= -10.0:
                bz_alert = "WARNING: Strong Southward IMF (Bz <= -10 nT)"
                bz_color = "#ea580c"
            elif bz_gsm < 0.0:
                bz_alert = "CAUTION: Moderate Southward Component (Bz < 0 nT)"
                bz_color = "#f59e0b"
            else:
                bz_alert = "NOMINAL: Northward IMF (Magnetosphere Stable)"
                bz_color = "#10b981"

        # 3. Solar Flare Radio Blackout (R-Scale based on GOES X-ray W/m^2)
        r_scale = "R0 (None)"
        r_level = 0
        flare_class = "A/B"
        if xray_flux is not None and xray_flux > 0:
            if xray_flux >= 2e-3:
                r_scale, r_level, flare_class = "R5 (Extreme)", 5, f"X20+ ({xray_flux:.1e})"
            elif xray_flux >= 1e-3:
                r_scale, r_level, flare_class = "R4 (Severe)", 4, f"X10 ({xray_flux:.1e})"
            elif xray_flux >= 1e-4:
                r_scale, r_level, flare_class = "R3 (Strong)", 3, f"X1 ({xray_flux:.1e})"
            elif xray_flux >= 5e-5:
                r_scale, r_level, flare_class = "R2 (Moderate)", 2, f"M5 ({xray_flux:.1e})"
            elif xray_flux >= 1e-5:
                r_scale, r_level, flare_class = "R1 (Minor)", 1, f"M1 ({xray_flux:.1e})"
            elif xray_flux >= 1e-6:
                flare_class = f"C ({xray_flux:.1e})"
            else:
                flare_class = f"B ({xray_flux:.1e})"

        return {
            "g_scale": g_scale,
            "g_level": g_level,
            "g_color": g_color,
            "bz_alert": bz_alert,
            "bz_color": bz_color,
            "r_scale": r_scale,
            "r_level": r_level,
            "flare_class": flare_class
        }

    @staticmethod
    def detect_interplanetary_shocks(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Interplanetary Shock Detection using Rankine-Hugoniot jump proxies.
        A fast forward shock (driven by a CME or CIR) exhibits:
        - Sudden velocity jump Delta V >= 40 km/s within <= 15 minutes
        - Density compression ratio N2 / N1 >= 1.5
        - Magnetic field magnitude jump B2 / B1 >= 1.3
        """
        shocks = []
        if len(records) < 5:
            return shocks

        for i in range(3, len(records)):
            curr = records[i]
            prev = records[i - 3]  # Compare over ~10-15 min window

            v1, v2 = prev.get("speed"), curr.get("speed")
            b1, b2 = prev.get("bt"), curr.get("bt")
            n1, n2 = prev.get("density"), curr.get("density")

            if None in (v1, v2, b1, b2, n1, n2):
                continue
            if v1 <= 0 or b1 <= 0 or n1 <= 0:
                continue

            delta_v = v2 - v1
            ratio_b = b2 / b1
            ratio_n = n2 / n1

            # Shock identification criteria
            if delta_v >= 45.0 and ratio_b >= 1.35 and ratio_n >= 1.5:
                # Estimate Mach number: M_ms ~ delta_v / v_fast ~ delta_v / 60 km/s + 1
                mach_proxy = round(1.0 + (delta_v / 70.0), 2)
                shocks.append({
                    "time": curr.get("time_tag", ""),
                    "delta_speed_kms": round(delta_v, 1),
                    "density_ratio": round(ratio_n, 2),
                    "magnetic_ratio": round(ratio_b, 2),
                    "mach_proxy": mach_proxy,
                    "upstream_speed": round(v1, 1),
                    "downstream_speed": round(v2, 1),
                    "classification": "Fast Forward CME Shock" if delta_v > 100 else "Interplanetary Shock / CIR"
                })

        return shocks

    @staticmethod
    def power_spectral_density(values: List[float], dt_seconds: float = 60.0) -> Dict[str, List[float]]:
        """
        Fast Fourier Transform (FFT) power spectral density analysis for solar wind
        magnetic field / plasma turbulence (identifies 1/f and Kolmogorov -5/3 inertial subrange).
        """
        clean_vals = [v for v in values if v is not None and not np.isnan(v)]
        if len(clean_vals) < 32:
            return {"frequencies_hz": [], "power_density": []}

        arr = np.array(clean_vals)
        arr = arr - np.mean(arr)  # Detrend
        window = np.hanning(len(arr))
        arr_windowed = arr * window

        fft_vals = np.fft.rfft(arr_windowed)
        psd = (np.abs(fft_vals) ** 2) / (len(arr) * (1.0 / dt_seconds))
        freqs = np.fft.rfftfreq(len(arr), d=dt_seconds)

        # Slice off DC component (first index)
        return {
            "frequencies_hz": [float(f) for f in freqs[1:100]],
            "power_density": [float(p) for p in psd[1:100]]
        }
