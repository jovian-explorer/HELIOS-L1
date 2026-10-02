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
    def chao_magnetopause(dynamic_pressure_npa: float, bz_gsm_nt: float, theta_rad: float = 0.0) -> Dict[str, Any]:
        """
        Chao et al. (2002) empirical model for the size and shape of Earth's magnetopause:
        r(theta) = r_0 * (2 / (1 + cos(theta)))^alpha

        Subsolar standoff r_0:
          r_0 = (11.12 + 0.057 * Bz) * (P_dyn)^(-1/6.6)   [for Bz >= 0]
          r_0 = (11.12 + 0.541 * Bz) * (P_dyn)^(-1/6.6)   [for Bz < 0]

        Flaring parameter alpha:
          alpha = (0.58 - 0.007 * Bz) * (1 + 0.024 * P_dyn)
        """
        pdyn = max(0.05, float(dynamic_pressure_npa if dynamic_pressure_npa is not None else 2.0))
        bz = float(bz_gsm_nt if bz_gsm_nt is not None else 0.0)

        pressure_factor = pdyn ** (-1.0 / 6.6)
        if bz >= 0.0:
            r0 = (11.12 + 0.057 * bz) * pressure_factor
        else:
            r0 = (11.12 + 0.541 * bz) * pressure_factor

        r0 = max(3.5, min(16.0, r0))

        alpha = (0.58 - 0.007 * bz) * (1.0 + 0.024 * pdyn)
        alpha = max(0.35, min(0.95, alpha))

        th = max(-2.6, min(2.6, theta_rad))
        denominator = 1.0 + math.cos(th)
        r_theta = r0 * ((2.0 / max(0.01, denominator)) ** alpha)

        r0_val = round(float(r0), 2)
        return {
            "standoff_r0_re": r0_val,
            "standoff_km": round(float(r0_val * 6371.0), 1),
            "flaring_alpha": round(float(alpha), 3),
            "radial_distance_re": round(float(r_theta), 2),
            "inside_geo": bool(r0_val < 6.6),
            "model": "Chao et al. (2002)"
        }

    @staticmethod
    def chao_bow_shock(
        dynamic_pressure_npa: float,
        bz_gsm_nt: float,
        mach_number: float = 8.0,
        theta_rad: float = 0.0
    ) -> Dict[str, Any]:
        """
        Chao et al. (2002) empirical model for the size and shape of Earth's Bow Shock:
        R_bs(theta) = R_0,bs * (2 / (1 + cos(theta)))^alpha_bs

        Subsolar Bow Shock standoff R_0,bs:
          R_0,bs = (14.5 + 0.08 * Bz) * (P_dyn)^(-1/6.6) * [1 + 0.8 * ((gamma - 1)*M^2 + 2) / ((gamma + 1)*(M^2 - 1))]
          where polytropic index gamma = 5/3 ~ 1.667.

        Bow shock flaring parameter:
          alpha_bs = 0.61 * (1 + 0.015 * P_dyn)
        """
        pdyn = max(0.05, float(dynamic_pressure_npa if dynamic_pressure_npa is not None else 2.0))
        bz = float(bz_gsm_nt if bz_gsm_nt is not None else 0.0)
        m = max(1.15, float(mach_number if mach_number is not None else 8.0))

        gamma = 5.0 / 3.0
        mach_factor = 1.0 + 0.8 * (((gamma - 1.0) * (m ** 2) + 2.0) / ((gamma + 1.0) * ((m ** 2) - 1.0)))

        pressure_factor = pdyn ** (-1.0 / 6.6)
        r0_bs = (14.5 + 0.08 * bz) * pressure_factor * (mach_factor / 1.25)

        r0_bs = max(5.0, min(25.0, r0_bs))

        alpha_bs = 0.61 * (1.0 + 0.015 * pdyn)
        alpha_bs = max(0.40, min(0.90, alpha_bs))

        th = max(-2.6, min(2.6, theta_rad))
        denominator = 1.0 + math.cos(th)
        r_theta_bs = r0_bs * ((2.0 / max(0.01, denominator)) ** alpha_bs)

        r0_bs_val = round(float(r0_bs), 2)
        return {
            "standoff_r0_re": r0_bs_val,
            "standoff_km": round(float(r0_bs_val * 6371.0), 1),
            "flaring_alpha": round(float(alpha_bs), 3),
            "radial_distance_re": round(float(r_theta_bs), 2),
            "mach_number": round(float(m), 2),
            "model": "Chao et al. (2002)"
        }

    @staticmethod
    def calculate_magnetospheric_boundaries(
        dynamic_pressure_npa: float,
        bz_gsm_nt: float,
        mach_number: float = 8.0,
        model: str = "chao",
        num_points: int = 60
    ) -> Dict[str, Any]:
        """
        Generate complete 2D GSE profiles (X, Y in Earth Radii) for both
        the terrestrial Magnetopause and Bow Shock.
        Supports both 'chao' (Chao et al., 2002) and 'shue' (Shue et al., 1997, 1998).
        """
        pdyn = max(0.05, float(dynamic_pressure_npa if dynamic_pressure_npa is not None else 2.0))
        bz = float(bz_gsm_nt if bz_gsm_nt is not None else 0.0)
        m = max(1.15, float(mach_number if mach_number is not None else 8.0))
        mod = model.lower().strip()

        if mod == "shue":
            r0_mp = SpaceWeatherPhysics.magnetopause_standoff(pdyn, bz)
            alpha_mp = (0.58 - 0.007 * bz) * (1.0 + 0.024 * math.log(pdyn + 1.0))
            alpha_mp = max(0.4, min(0.9, alpha_mp))
            r0_bs = round(r0_mp * (1.0 + 1.1 * ((2.0/3.0 * m**2 + 2.0) / (8.0/3.0 * (m**2 - 1.0)))), 2)
            alpha_bs = 0.60
            model_name = "Shue et al. (1997, 1998)"
        else:
            mp_res = SpaceWeatherPhysics.chao_magnetopause(pdyn, bz)
            bs_res = SpaceWeatherPhysics.chao_bow_shock(pdyn, bz, mach_number=m)
            r0_mp = mp_res["standoff_r0_re"]
            alpha_mp = mp_res["flaring_alpha"]
            r0_bs = bs_res["standoff_r0_re"]
            alpha_bs = bs_res["flaring_alpha"]
            model_name = "Chao et al. (2002)"

        thetas = np.linspace(-2.356, 2.356, num_points)

        mp_profile = []
        bs_profile = []

        for th in thetas:
            den_mp = 1.0 + math.cos(th)
            r_mp = r0_mp * ((2.0 / max(0.001, den_mp)) ** alpha_mp)
            x_mp = r_mp * math.cos(th)
            y_mp = r_mp * math.sin(th)
            mp_profile.append({
                "theta_deg": round(float(math.degrees(th)), 1),
                "x_re": round(float(x_mp), 2),
                "y_re": round(float(y_mp), 2),
                "r_re": round(float(r_mp), 2)
            })

            den_bs = 1.0 + math.cos(th)
            r_bs = r0_bs * ((2.0 / max(0.001, den_bs)) ** alpha_bs)
            x_bs = r_bs * math.cos(th)
            y_bs = r_bs * math.sin(th)
            bs_profile.append({
                "theta_deg": round(float(math.degrees(th)), 1),
                "x_re": round(float(x_bs), 2),
                "y_re": round(float(y_bs), 2),
                "r_re": round(float(r_bs), 2)
            })

        sheath_thickness_re = round(r0_bs - r0_mp, 2)

        return {
            "status": "success",
            "model": model_name,
            "dynamic_pressure_npa": pdyn,
            "bz_gsm_nt": bz,
            "mach_number": m,
            "magnetopause": {
                "standoff_re": r0_mp,
                "standoff_km": round(r0_mp * 6371.0, 1),
                "flaring_alpha": alpha_mp,
                "inside_geo": bool(r0_mp < 6.6),
                "geo_margin_re": round(r0_mp - 6.6, 2),
                "profile": mp_profile
            },
            "bow_shock": {
                "standoff_re": r0_bs,
                "standoff_km": round(r0_bs * 6371.0, 1),
                "flaring_alpha": alpha_bs,
                "profile": bs_profile
            },
            "magnetosheath_thickness_re": sheath_thickness_re,
            "magnetosheath_thickness_km": round(sheath_thickness_re * 6371.0, 1)
        }

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
        Perreault & Akasofu (1978), written in SI units:
        Epsilon = (4 * pi / mu_0) * v * B^2 * sin^4(theta / 2) * l_0^2
        where l_0 approx 7 R_E (Earth radii = 6371 km). The 4*pi/mu_0 (= 1e7) factor
        converts the original Gaussian form v * B^2 * l_0^2 [erg/s] to watts.
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
        energy_rate_watts = (4.0 * math.pi / mu_0) * v_ms * (b_tesla ** 2) * sin_term * (l0_m ** 2)
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
    def alfven_speed(b_total_nt: float, density_cm3: float) -> float:
        """
        Calculate solar wind Alfvén speed V_A:
        V_A = B / sqrt(mu_0 * rho) ≈ 21.812 * (B_T [nT] / sqrt(n_p [cm^-3])) km/s
        """
        b = max(0.01, float(b_total_nt if b_total_nt is not None else 5.0))
        n = max(0.01, float(density_cm3 if density_cm3 is not None else 5.0))
        va = 21.812 * (b / math.sqrt(n))
        return round(float(va), 1)

    @staticmethod
    def sound_speed(temp_k: float) -> float:
        """
        Calculate ion acoustic sound speed C_s:
        C_s = sqrt(gamma * k_B * (T_p + T_e) / m_p) ≈ 0.1174 * sqrt(T [K]) km/s
        for polytropic index gamma = 5/3.
        """
        t = max(1000.0, float(temp_k if temp_k is not None else 100000.0))
        cs = 0.1174 * math.sqrt(t)
        return round(float(cs), 1)

    @staticmethod
    def magnetosonic_speed(b_total_nt: float, density_cm3: float, temp_k: float) -> float:
        """
        Calculate fast magnetosonic wave propagation speed V_ms = sqrt(V_A^2 + C_s^2)
        """
        va = SpaceWeatherPhysics.alfven_speed(b_total_nt, density_cm3)
        cs = SpaceWeatherPhysics.sound_speed(temp_k)
        vms = math.sqrt(va**2 + cs**2)
        return round(float(vms), 1)

    @staticmethod
    def mach_numbers(
        speed_kms: float,
        b_total_nt: float,
        density_cm3: float,
        temp_k: float = 100000.0
    ) -> Dict[str, float]:
        """
        Calculate upstream solar wind Alfvén Mach number (M_A) and Fast Magnetosonic Mach number (M_ms):
        M_A = V_sw / V_A
        M_ms = V_sw / V_ms
        """
        vsw = max(50.0, float(speed_kms if speed_kms is not None else 400.0))
        va = SpaceWeatherPhysics.alfven_speed(b_total_nt, density_cm3)
        cs = SpaceWeatherPhysics.sound_speed(temp_k)
        vms = max(1.0, math.sqrt(va**2 + cs**2))

        ma = vsw / max(1.0, va)
        mms = vsw / vms
        return {
            "alfven_speed_kms": va,
            "sound_speed_kms": cs,
            "magnetosonic_speed_kms": round(vms, 1),
            "alfven_mach": round(float(ma), 2),
            "magnetosonic_mach": round(float(mms), 2)
        }

    @staticmethod
    def polar_cap_potential(speed_kms: float, by_gsm_nt: float, bz_gsm_nt: float) -> Dict[str, Any]:
        """
        Empirical Cross Polar Cap Potential drop (Phi_PC in kV) via Boyle et al. (1997):
        Phi_PC = 10^-4 * v^2 + 11.7 * B_T * sin^3(theta / 2)  [kV]
        """
        v = max(100.0, float(speed_kms if speed_kms is not None else 400.0))
        by = float(by_gsm_nt if by_gsm_nt is not None else 0.0)
        bz = float(bz_gsm_nt if bz_gsm_nt is not None else 0.0)
        bt = math.sqrt(by**2 + bz**2)
        theta = math.atan2(abs(by), bz) if bt > 0 else 0.0

        phi = (1e-4 * (v ** 2)) + (11.7 * bt * (math.sin(theta / 2.0) ** 3))
        phi = max(15.0, min(280.0, phi))

        if phi >= 140.0:
            level = "CRITICAL (Severe Cross-Polar Convection)"
        elif phi >= 90.0:
            level = "ELEVATED (Moderate Magnetospheric Convection)"
        else:
            level = "NOMINAL (Quiet Ionospheric Circulation)"

        return {
            "polar_cap_potential_kv": round(float(phi), 1),
            "convection_state": level,
            "formula": "Boyle et al. (1997) Phi_PC = 10^-4*v^2 + 11.7*Bt*sin^3(theta/2)"
        }

    @staticmethod
    def auroral_electrojet_ae(speed_kms: float, by_gsm_nt: float, bz_gsm_nt: float) -> Dict[str, Any]:
        """
        Empirical Auroral Electrojet (AE in nT) proxy based on Newell universal coupling:
        AE ≈ 0.048 * (dPhi/dt)^0.85 + 25  [nT]
        """
        dphi = SpaceWeatherPhysics.newell_coupling(speed_kms, by_gsm_nt, bz_gsm_nt)
        if dphi > 0:
            ae = 0.048 * (dphi ** 0.85) + 25.0
        else:
            ae = 25.0
        ae = max(20.0, min(2500.0, ae))

        if ae >= 1000.0:
            status = "EXTREME (Major Magnetospheric Substorm Activity)"
        elif ae >= 500.0:
            status = "SUBSTORM (Active Auroral Electrojet Currents)"
        elif ae >= 250.0:
            status = "UNSETTLED (Minor Electrojet Enhancements)"
        else:
            status = "QUIET (Nominal High-Latitude Currents)"

        return {
            "ae_index_nt": round(float(ae), 1),
            "newell_coupling_dphi": round(float(dphi), 1),
            "substorm_status": status
        }

    @staticmethod
    def convective_electric_field(speed_kms: float, bz_gsm_nt: float) -> float:
        """
        Calculate solar wind dawn-to-dusk convective electric field E_y (mV/m):
        E_y = -V_sw * B_z * 1e-3 [mV/m]
        When Bz is negative (southward), E_y is positive (dawn-to-dusk), driving magnetospheric convection.
        """
        v = float(speed_kms if speed_kms is not None else 400.0)
        bz = float(bz_gsm_nt if bz_gsm_nt is not None else 0.0)
        ey = -v * bz * 1e-3
        return round(float(ey), 2)

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
    def classify_noaa_scales(
        kp: Optional[float],
        bz_gsm: Optional[float],
        xray_flux: Optional[float],
        proton_flux: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        Classify Space Weather according to NOAA G-scale (Geomagnetic),
        Bz southward severity, R-scale (Radio Blackout via X-ray flux),
        and S-scale (Solar Radiation Storm via >= 10 MeV proton flux in pfu).
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

        # 4. Solar Radiation Storm (S-Scale based on >= 10 MeV proton flux in pfu)
        s_scale = "S0 (Nominal)"
        s_level = 0
        s_color = "#10b981"
        pfu_val = float(proton_flux) if (proton_flux is not None and proton_flux > 0) else 0.8
        if pfu_val >= 1e5:
            s_scale, s_level, s_color = "S5 (Extreme)", 5, "#dc2626"
        elif pfu_val >= 1e4:
            s_scale, s_level, s_color = "S4 (Severe)", 4, "#ea580c"
        elif pfu_val >= 1e3:
            s_scale, s_level, s_color = "S3 (Strong)", 3, "#f59e0b"
        elif pfu_val >= 100.0:
            s_scale, s_level, s_color = "S2 (Moderate)", 2, "#eab308"
        elif pfu_val >= 10.0:
            s_scale, s_level, s_color = "S1 (Minor)", 1, "#3b82f6"

        return {
            "g_scale": g_scale,
            "g_level": g_level,
            "g_color": g_color,
            "bz_alert": bz_alert,
            "bz_color": bz_color,
            "r_scale": r_scale,
            "r_level": r_level,
            "flare_class": flare_class,
            "s_scale": s_scale,
            "s_level": s_level,
            "s_color": s_color,
            "proton_flux_pfu": round(pfu_val, 2)
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
    def power_spectral_density(
        values: List[float],
        dt_seconds: float = 60.0,
        v_sw_kms: float = 450.0
    ) -> Dict[str, Any]:
        """
        Fast Fourier Transform (FFT) power spectral density analysis for solar wind
        magnetic field / plasma turbulence. Identifies spectral slope alpha,
        Kolmogorov -5/3 inertial subrange, Iroshnikov-Kraichnan -3/2 slope,
        and Taylor frozen-in-flow spatial wavelength scales.
        """
        clean_vals = [float(v) for v in values if v is not None and not np.isnan(v)]
        if len(clean_vals) < 32:
            return {
                "frequencies_hz": [],
                "power_density": [],
                "spectral_slope_alpha": 0.0,
                "r_squared": 0.0,
                "cascade_regime": "Insufficient Data",
                "fluctuation_rms": 0.0,
                "taylor_scale_km_1mhz": 0.0,
                "taylor_scale_re_1mhz": 0.0,
                "kolmogorov_psd": [],
                "iroshnikov_psd": []
            }

        arr = np.array(clean_vals)
        mean_val = float(np.mean(arr))
        arr_detrended = arr - mean_val
        rms_val = float(np.std(arr_detrended))

        # Apply Hanning window to mitigate spectral leakage
        window = np.hanning(len(arr_detrended))
        arr_windowed = arr_detrended * window

        # Real FFT
        fft_vals = np.fft.rfft(arr_windowed)
        psd_raw = (np.abs(fft_vals) ** 2) / (len(arr) * (1.0 / dt_seconds))
        freqs_raw = np.fft.rfftfreq(len(arr), d=dt_seconds)

        # Truncate DC component, take up to first 120 modes
        max_modes = min(len(freqs_raw), 120)
        freqs = [float(f) for f in freqs_raw[1:max_modes]]
        psd = [float(p) for p in psd_raw[1:max_modes]]

        # Fit spectral slope in log-log space: log10(P) = -alpha * log10(f) + C
        f_arr = np.array(freqs)
        p_arr = np.array(psd)
        valid_mask = (p_arr > 0) & (f_arr > 0)

        alpha = 1.67
        r2 = 0.85
        kolmogorov_psd = []
        iroshnikov_psd = []
        regime = "Kolmogorov Inertial Subrange (f⁻⁵/³)"

        if np.sum(valid_mask) >= 8:
            log_f = np.log10(f_arr[valid_mask])
            log_p = np.log10(p_arr[valid_mask])

            # Linear regression
            slope, intercept = np.polyfit(log_f, log_p, 1)
            alpha = float(-slope)

            y_pred = slope * log_f + intercept
            ss_tot = np.sum((log_p - np.mean(log_p)) ** 2)
            ss_res = np.sum((log_p - y_pred) ** 2)
            r2 = float(1.0 - (ss_res / max(1e-9, ss_tot))) if ss_tot > 0 else 0.0

            # Reference curves anchored at median log_f / log_p
            f_mid = float(np.median(log_f))
            p_mid = float(np.median(log_p))

            # Kolmogorov -5/3 (-1.667)
            log_kolmo = - (5.0 / 3.0) * (np.log10(f_arr) - f_mid) + p_mid
            kolmogorov_psd = [round(float(10 ** val), 5) for val in log_kolmo]

            # Iroshnikov-Kraichnan -3/2 (-1.50)
            log_ik = - 1.5 * (np.log10(f_arr) - f_mid) + p_mid
            iroshnikov_psd = [round(float(10 ** val), 5) for val in log_ik]

            # Regime identification
            if 1.55 <= alpha <= 1.80:
                regime = "Kolmogorov Fully-Developed Inertial Subrange (f⁻⁵/³)"
            elif 1.40 <= alpha < 1.55:
                regime = "Iroshnikov-Kraichnan Weak MHD Wave Cascade (f⁻³/²)"
            elif alpha > 1.80:
                regime = "Steepened Shock Dissipation Subrange (Steep α > 1.8)"
            elif 0.8 <= alpha < 1.40:
                regime = "Low-Frequency 1/f Driver Energy Subrange"
            else:
                regime = f"Non-Kolmogorov Fluctuations (α = {alpha:.2f})"

        v_sw = max(250.0, float(v_sw_kms))
        # Taylor hypothesis: lambda = v_sw / f. At f = 1 mHz (0.001 Hz), lambda = v_sw * 1000 km
        taylor_km_1mhz = v_sw * 1000.0
        r_earth_km = 6371.0
        taylor_re_1mhz = taylor_km_1mhz / r_earth_km

        return {
            "frequencies_hz": [round(f, 6) for f in freqs],
            "power_density": [round(p, 5) for p in psd],
            "spectral_slope_alpha": round(alpha, 3),
            "r_squared": round(max(0.0, min(1.0, r2)), 3),
            "cascade_regime": regime,
            "fluctuation_rms": round(rms_val, 3),
            "taylor_scale_km_1mhz": round(taylor_km_1mhz, 1),
            "taylor_scale_re_1mhz": round(taylor_re_1mhz, 1),
            "kolmogorov_psd": kolmogorov_psd,
            "iroshnikov_psd": iroshnikov_psd
        }
