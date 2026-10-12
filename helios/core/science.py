"""
Scientific calculations and space weather physics engine for HELIOS-L1.
Includes magnetohydrodynamic metrics, solar-terrestrial coupling, shock detection,
and Fourier spectral analysis.
"""
import math
import numpy as np
from typing import Dict, List, Any, Optional, Tuple

# OMNI flow pressure factor, nPa per (cm^-3 (km/s)^2): 1.67e-6 x (1 + 4 x 0.05), see dynamic_pressure.
PDYN_NPA_PER_CM3_KMS2 = 2.0e-6


# Lower end of the spectral fit: the 1/f range of the solar wind at 1 AU reaches up to about
# 1e-4 Hz (Bruno & Carbone 2013, Living Rev. Sol. Phys. 10, 2, doi:10.12942/lrsp-2013-2), the inertial range above.
PSD_FIT_FMIN_HZ = 1e-4


class SpaceWeatherPhysics:
    """Core physics and geomagnetic coupling calculations."""

    @staticmethod
    def dynamic_pressure(density_cm3: float, speed_kms: float) -> float:
        """
        Solar wind flow pressure in nPa with the OMNI definition, which the magnetopause and Dst
        models were fitted with: P = 1.67e-6 Np V^2 (1 + 4 Na/Np), with Na/Np = 0.05 when the
        alpha density is not measured, i.e. P = 2.0e-6 Np V^2 (Np in cm^-3, V in km/s). The
        proton-only value m_p n V^2 = 1.6726e-6 n V^2 is 20 % lower than OMNI's (checked against
        OMNI HRO 1-min "Pressure", 17 March 2015).
        """
        if density_cm3 is None or speed_kms is None or density_cm3 <= 0 or speed_kms <= 0:
            return 0.0
        return float(PDYN_NPA_PER_CM3_KMS2 * density_cm3 * (speed_kms ** 2))

    @staticmethod
    def magnetopause_standoff(dynamic_pressure_npa: float, bz_gsm_nt: float) -> float:
        """
        Estimate Earth's magnetopause subsolar standoff distance (R_mp) in Earth Radii (R_E)
        using the empirical Shue et al. (1998) model.
        Geostationary satellites are at 6.6 R_E. If R_mp < 6.6 R_E, satellites are exposed directly to solar wind!
        """
        if dynamic_pressure_npa <= 0.0:
            return 10.0
        r0, _ = SpaceWeatherPhysics.shue1998_magnetopause(dynamic_pressure_npa, bz_gsm_nt)
        return round(r0, 2)

    # Chao et al. (2002) bow shock coefficients a1..a14 (a12 is the eccentricity epsilon).
    # The COSPAR chapter itself is not openly available; the functional form is reproduced in
    # Zhou et al. (2020, Chin. J. Space Sci. 40(6), 990) and Mo et al. (2025, JGR 130,
    # e2025JA033966, open access), whose Table 1 lists these values to three decimals and a
    # standoff of 13.325 R_E for P_dyn = 2.42 nPa, Bz = -0.35 nT, beta = 3.02, M_ms = 5.77.
    CHAO_2002_BS = (11.1266, 0.0010, -0.0005, 2.5966, 0.8182, -0.0170, -0.0122,
                    1.3007, -0.0049, -0.0328, 6.047, 1.029, 0.0231, -0.002)

    @staticmethod
    def shue1998_magnetopause(dynamic_pressure_npa: float, bz_gsm_nt: float) -> Tuple[float, float]:
        """
        Shue et al. (1998) magnetopause: r = r0 * (2 / (1 + cos(theta)))^alpha with
          r0    = (10.22 + 1.29 * tanh(0.184 * (Bz + 8.14))) * P_dyn^(-1/6.6)
          alpha = (0.58 - 0.007 * Bz) * (1 + 0.024 * ln(P_dyn))
        Returns (r0 in R_E, alpha), unrounded.
        """
        pdyn = max(0.01, float(dynamic_pressure_npa))
        bz = float(bz_gsm_nt if bz_gsm_nt is not None else 0.0)
        r0 = (10.22 + 1.29 * math.tanh(0.184 * (bz + 8.14))) * pdyn ** (-1.0 / 6.6)
        alpha = (0.58 - 0.007 * bz) * (1.0 + 0.024 * math.log(pdyn))
        return float(r0), float(alpha)

    @staticmethod
    def shue1997_standoff(dynamic_pressure_npa: float, bz_gsm_nt: float) -> float:
        """
        Shue et al. (1997) subsolar magnetopause, as used for the OMNI bow shock nose:
          r0 = (11.4 + K * Bz) * P_dyn^(-1/6.6),  K = 0.013 (Bz >= 0), 0.140 (Bz < 0)
        """
        pdyn = max(0.01, float(dynamic_pressure_npa))
        bz = float(bz_gsm_nt if bz_gsm_nt is not None else 0.0)
        k = 0.013 if bz >= 0.0 else 0.140
        return float((11.4 + k * bz) * pdyn ** (-1.0 / 6.6))

    @staticmethod
    def plasma_beta(density_cm3: float, temp_k: float, b_total_nt: float) -> Optional[float]:
        """
        Solar wind plasma beta with the OMNI definition (protons plus a fixed electron and
        alpha contribution): beta = [(T * 4.16e-5) + 5.34] * Np / B^2, B in nT.
        """
        if not density_cm3 or not temp_k or not b_total_nt or b_total_nt <= 0 or density_cm3 <= 0:
            return None
        return float((temp_k * 4.16e-5 + 5.34) * density_cm3 / b_total_nt ** 2)

    @staticmethod
    def chao_bow_shock(
        dynamic_pressure_npa: float,
        bz_gsm_nt: float,
        mach_number: float = 8.0,
        theta_rad: float = 0.0,
        plasma_beta: float = 2.0
    ) -> Dict[str, Any]:
        """
        Chao et al. (2002) bow shock: r = r0 * ((1 + eps) / (1 + eps * cos(theta)))^alpha, eps = a12,
          r0    = a1 (1 + a2 Bz)(1 + a9 beta)(1 + a4 ((a8 - 1) M_ms^2 + 2) / ((a8 + 1) M_ms^2)) P_dyn^(-1/a11)
          alpha = a5 (1 + a13 Bz)(1 + a7 P_dyn)(1 + a10 ln(1 + beta))(1 + a14 M_ms)
        for Bz >= 0; for Bz < 0, a3 replaces a2 and a6 replaces a13.
        mach_number is the magnetosonic Mach number M_ms; theta is measured from the
        (aberrated) Sun-Earth line.
        """
        a1, a2, a3, a4, a5, a6, a7, a8, a9, a10, a11, eps, a13, a14 = SpaceWeatherPhysics.CHAO_2002_BS
        pdyn = max(0.01, float(dynamic_pressure_npa if dynamic_pressure_npa is not None else 2.0))
        bz = float(bz_gsm_nt if bz_gsm_nt is not None else 0.0)
        m = max(1.0, float(mach_number if mach_number is not None else 8.0))
        beta = max(0.0, float(plasma_beta if plasma_beta is not None else 2.0))

        rh = ((a8 - 1.0) * m ** 2 + 2.0) / ((a8 + 1.0) * m ** 2)
        common_r = (1.0 + a9 * beta) * (1.0 + a4 * rh) * pdyn ** (-1.0 / a11)
        common_a = (1.0 + a7 * pdyn) * (1.0 + a10 * math.log(1.0 + beta)) * (1.0 + a14 * m)
        if bz >= 0.0:
            r0 = a1 * (1.0 + a2 * bz) * common_r
            alpha = a5 * (1.0 + a13 * bz) * common_a
        else:
            r0 = a1 * (1.0 + a3 * bz) * common_r
            alpha = a5 * (1.0 + a6 * bz) * common_a

        r_theta = SpaceWeatherPhysics.conic_radius(r0, alpha, eps, theta_rad)
        return {
            "standoff_r0_re": round(float(r0), 2),
            "standoff_km": round(float(r0) * 6371.0, 1),
            "flaring_alpha": round(float(alpha), 3),
            "eccentricity": eps,
            "radial_distance_re": round(r_theta, 2) if r_theta is not None else None,
            "mach_number": round(float(m), 2),
            "plasma_beta": round(float(beta), 2),
            "model": "Chao et al. (2002)"
        }

    @staticmethod
    def farris_russell_bow_shock(r0_mp_re: float, mach_number: float, theta_rad: float = 0.0) -> Dict[str, Any]:
        """
        Farris & Russell (1994) standoff from the magnetopause nose distance and the
        magnetosonic Mach number (gamma = 5/3), as used for the OMNI bow shock nose:
          R_bs = R_mp * [1 + 1.1 * ((gamma - 1) M_ms^2 + 2) / ((gamma + 1)(M_ms^2 - 1))]
        Shape: Farris et al. (1991) conic r = R_bs (1 + eps) / (1 + eps cos(theta)), eps = 0.81.
        Undefined for M_ms <= 1 (no shock).
        """
        gamma = 5.0 / 3.0
        m = float(mach_number if mach_number is not None else 8.0)
        if m <= 1.0:
            raise ValueError("Farris & Russell (1994) needs a super-magnetosonic flow (M_ms > 1)")
        r0 = float(r0_mp_re) * (1.0 + 1.1 * ((gamma - 1.0) * m ** 2 + 2.0) / ((gamma + 1.0) * (m ** 2 - 1.0)))
        eps = 0.81
        r_theta = SpaceWeatherPhysics.conic_radius(r0, 1.0, eps, theta_rad)
        return {
            "standoff_r0_re": round(r0, 2),
            "standoff_km": round(r0 * 6371.0, 1),
            "flaring_alpha": 1.0,
            "eccentricity": eps,
            "radial_distance_re": round(r_theta, 2) if r_theta is not None else None,
            "mach_number": round(m, 2),
            "model": "Farris & Russell (1994)"
        }

    @staticmethod
    def conic_radius(r0: float, alpha: float, eps: float, theta_rad: float) -> Optional[float]:
        """r = r0 * ((1 + eps) / (1 + eps * cos(theta)))^alpha; None beyond an open (eps >= 1) conic's asymptote."""
        den = 1.0 + eps * math.cos(theta_rad)
        if den <= 1e-6:
            return None
        return float(r0 * ((1.0 + eps) / den) ** alpha)

    @staticmethod
    def calculate_magnetospheric_boundaries(
        dynamic_pressure_npa: float,
        bz_gsm_nt: float,
        mach_number: float = 8.0,
        model: str = "chao",
        num_points: int = 60,
        plasma_beta: float = 2.0
    ) -> Dict[str, Any]:
        """
        Generate complete 2D GSE profiles (X, Y in Earth Radii) for both
        the terrestrial Magnetopause and Bow Shock.
        The magnetopause is always Shue et al. (1998). The bow shock is Chao et al. (2002)
        for model 'chao' and Farris & Russell (1994) for model 'shue' (alias 'farris').
        mach_number is the magnetosonic Mach number M_ms; plasma_beta uses the OMNI definition.
        """
        pdyn = max(0.05, float(dynamic_pressure_npa if dynamic_pressure_npa is not None else 2.0))
        bz = float(bz_gsm_nt if bz_gsm_nt is not None else 0.0)
        m = max(1.15, float(mach_number if mach_number is not None else 8.0))
        beta = max(0.0, float(plasma_beta if plasma_beta is not None else 2.0))
        mod = model.lower().strip()

        r0_mp_raw, alpha_mp_raw = SpaceWeatherPhysics.shue1998_magnetopause(pdyn, bz)
        r0_mp, alpha_mp = round(r0_mp_raw, 2), alpha_mp_raw
        if mod in ("shue", "farris"):
            bs_res = SpaceWeatherPhysics.farris_russell_bow_shock(r0_mp_raw, m)
            model_name = "Shue et al. (1998) magnetopause + Farris & Russell (1994) bow shock"
        else:
            bs_res = SpaceWeatherPhysics.chao_bow_shock(pdyn, bz, mach_number=m, plasma_beta=beta)
            model_name = "Shue et al. (1998) magnetopause + Chao et al. (2002) bow shock"
        r0_bs = bs_res["standoff_r0_re"]
        alpha_bs = bs_res["flaring_alpha"]
        eps_bs = bs_res["eccentricity"]

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

            r_bs = SpaceWeatherPhysics.conic_radius(r0_bs, alpha_bs, eps_bs, th)
            if r_bs is None:
                continue
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
            "magnetopause_model": "Shue et al. (1998)",
            "bow_shock_model": bs_res["model"],
            "dynamic_pressure_npa": pdyn,
            "bz_gsm_nt": bz,
            "mach_number": m,
            "plasma_beta": beta,
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
                "eccentricity": eps_bs,
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
        Calculate the proton sound speed C_s:
        C_s = sqrt(gamma * k_B * T_p / m_p) ≈ 0.1174 * sqrt(T_p [K]) km/s
        for polytropic index gamma = 5/3. Electron pressure is not included
        (with T_e ≈ T_p the speed would be sqrt(2) larger).
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
        # Unrounded wave speeds (the rounded public helpers made M_A and M_ms differ from
        # the in-browser calculator in the second decimal)
        b = max(0.01, float(b_total_nt if b_total_nt is not None else 5.0))
        n = max(0.01, float(density_cm3 if density_cm3 is not None else 5.0))
        t = max(1000.0, float(temp_k if temp_k is not None else 100000.0))
        va = 21.812 * b / math.sqrt(n)
        cs = 0.1174 * math.sqrt(t)
        vms = max(1.0, math.sqrt(va**2 + cs**2))

        ma = vsw / max(1.0, va)
        mms = vsw / vms
        return {
            "alfven_speed_kms": round(va, 1),
            "sound_speed_kms": round(cs, 1),
            "magnetosonic_speed_kms": round(vms, 1),
            "alfven_mach": round(float(ma), 2),
            "magnetosonic_mach": round(float(mms), 2)
        }

    @staticmethod
    def omni_magnetosonic_mach(speed_kms: Optional[float], b_total_nt: Optional[float],
                               density_cm3: Optional[float], temp_k: Optional[float]) -> Optional[float]:
        """
        Magnetosonic Mach number with the OMNI definitions (alphas and electrons included):
        V_A = 20 B / sqrt(N), C_s = 0.12 sqrt(T + 1.28e5) km/s, M_ms = V / sqrt(V_A^2 + C_s^2).
        This is the M_ms the bow shock models use (orbits.js solarWindMachBeta). None when an
        input is missing.
        """
        if not speed_kms or not b_total_nt or not density_cm3 or not temp_k or min(speed_kms, b_total_nt, density_cm3, temp_k) <= 0:
            return None
        va = 20.0 * b_total_nt / math.sqrt(density_cm3)
        cs = 0.12 * math.sqrt(temp_k + 1.28e5)
        return float(speed_kms / math.sqrt(va * va + cs * cs))

    @staticmethod
    def polar_cap_potential(speed_kms: float, by_gsm_nt: float, bz_gsm_nt: float,
                            b_total_nt: Optional[float] = None) -> Dict[str, Any]:
        """
        Empirical Cross Polar Cap Potential drop (Phi_PC in kV) via Boyle et al. (1997):
        Phi_PC = 10^-4 * v^2 + 11.7 * B * sin^3(theta / 2)  [kV]
        where B is the IMF magnitude |B| (including Bx). When b_total_nt is not given,
        |B| is approximated by sqrt(By^2 + Bz^2).
        """
        v = max(100.0, float(speed_kms if speed_kms is not None else 400.0))
        by = float(by_gsm_nt if by_gsm_nt is not None else 0.0)
        bz = float(bz_gsm_nt if bz_gsm_nt is not None else 0.0)
        b_trans = math.sqrt(by**2 + bz**2)
        b_mag = float(b_total_nt) if b_total_nt is not None else b_trans
        theta = math.atan2(abs(by), bz) if b_trans > 0 else 0.0

        phi = (1e-4 * (v ** 2)) + (11.7 * b_mag * (math.sin(theta / 2.0) ** 3))
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
            "formula": "Boyle et al. (1997) Phi_PC = 10^-4*v^2 + 11.7*|B|*sin^3(theta/2)"
        }

    @staticmethod
    def auroral_electrojet_ae(speed_kms: float, by_gsm_nt: float, bz_gsm_nt: float) -> Dict[str, Any]:
        """
        Rough auroral electrojet (AE in nT) proxy from the Newell universal coupling:
        AE ≈ 0.048 * (dPhi/dt)^0.85 + 25  [nT]
        This scaling is HELIOS-L1's own, not a published fit (no source was found for it);
        observed AE comes from OMNI (archive and storm indices).
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
    def propagation_delay_minutes(distance_km: float, speed_kms: float) -> Optional[float]:
        """
        Travel time in minutes from the spacecraft's sunward distance (GSE x, about 1.5 million km
        at L1) to Earth's bow shock (about 14 R_E, 90,000 km); None without a speed.
        """
        if not speed_kms or speed_kms <= 0:
            return None
        effective_dist = max(0.0, distance_km - 90000.0)
        delay_seconds = effective_dist / speed_kms
        return round(float(delay_seconds / 60.0), 1)

    @staticmethod
    def goes_flare_class(xray_flux: Optional[float]) -> Optional[str]:
        """
        GOES 0.1-0.8 nm flare class from peak flux in W/m^2, e.g. 5.3e-4 -> 'X5.3',
        2.1e-6 -> 'C2.1', 4e-8 -> 'A4.0'. The multiplier is truncated (not rounded)
        to one decimal, so 9.99e-5 is 'M9.9' rather than 'M10.0'.
        """
        if xray_flux is None or not xray_flux > 0:
            return None
        for letter, base in (("X", 1e-4), ("M", 1e-5), ("C", 1e-6), ("B", 1e-7), ("A", 1e-8)):
            if xray_flux >= base or letter == "A":
                multiplier = math.floor(round(xray_flux / base, 9) * 10.0) / 10.0
                return f"{letter}{multiplier:.1f}"
        return None

    @staticmethod
    def noaa_g_level(kp: Optional[float]) -> int:
        """
        NOAA geomagnetic storm level 0-5 for a Kp value. Kp comes in thirds; the scale counts
        a "minus" value with its integer (G1 = Kp 5-, 5o, 5+; G4 = Kp 8- to 9-; G5 = 9o, 9+),
        as in the noaa_scale field of SWPC's Kp products (Kp 4.67 -> G1). The thresholds sit
        between the thirds so that model estimates with other decimals classify sensibly.
        """
        if kp is None:
            return 0
        for level, threshold in ((5, 8.83), (4, 7.5), (3, 6.5), (2, 5.5), (1, 4.5)):
            if kp >= threshold:
                return level
        return 0

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
        # Kp 5- (4.67) is already G1: the scale used to start at Kp 5.0, one third too high.
        level = SpaceWeatherPhysics.noaa_g_level(kp)
        if kp is None:
            g_scale, g_color = "G-- (No Kp data)", "#64748b"
        elif level:
            g_scale, g_level, g_color = {
                5: ("G5 (Extreme)", 5, "#dc2626"), 4: ("G4 (Severe)", 4, "#ea580c"),
                3: ("G3 (Strong)", 3, "#f59e0b"), 2: ("G2 (Moderate)", 2, "#eab308"),
                1: ("G1 (Minor)", 1, "#3b82f6")}[level]

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
        # Thresholds: R1 >= M1, R2 >= M5, R3 >= X1, R4 >= X10, R5 >= X20.
        # Like the S scale: no X-ray measurement is no classification, not "R0 (None)".
        r_scale = "R-- (No X-ray data)"
        r_level = 0
        flare_class = "No data"
        if xray_flux is not None and xray_flux > 0:
            r_scale = "R0 (None)"
            flare_class = f"{SpaceWeatherPhysics.goes_flare_class(xray_flux)} ({xray_flux:.1e} W/m^2)"
            if xray_flux >= 2e-3:
                r_scale, r_level = "R5 (Extreme)", 5
            elif xray_flux >= 1e-3:
                r_scale, r_level = "R4 (Severe)", 4
            elif xray_flux >= 1e-4:
                r_scale, r_level = "R3 (Strong)", 3
            elif xray_flux >= 5e-5:
                r_scale, r_level = "R2 (Moderate)", 2
            elif xray_flux >= 1e-5:
                r_scale, r_level = "R1 (Minor)", 1

        # 4. Solar Radiation Storm (S-Scale based on >= 10 MeV proton flux in pfu)
        # No measurement means no classification: never substitute a made-up flux.
        s_scale = "S0 (Nominal)"
        s_level = 0
        s_color = "#10b981"
        pfu_val = float(proton_flux) if (proton_flux is not None and proton_flux >= 0) else None
        if pfu_val is None:
            s_scale, s_color = "S-- (No proton data)", "#64748b"
        elif pfu_val >= 1e5:
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
            "proton_flux_pfu": round(pfu_val, 2) if pfu_val is not None else None
        }

    @staticmethod
    def detect_interplanetary_shocks(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Interplanetary Shock Detection using Rankine-Hugoniot jump proxies.
        A fast forward shock (driven by a CME or CIR) exhibits:
        - Sudden velocity jump Delta V >= 45 km/s over three samples
        - Density compression ratio N2 / N1 >= 1.5
        - Magnetic field magnitude jump B2 / B1 >= 1.35
        These are screening thresholds of this application, not a published criterion.

        Each record is compared with the one three samples earlier, so a single jump
        satisfies the criteria at up to three consecutive samples. Those detections are
        merged into one event (the sample with the largest speed jump), so the number of
        events is not tripled.
        """
        shocks = []
        last_index = None
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
                # Speed-jump proxy 1 + delta_v / 70 km/s (not a Mach number: that needs the upstream fast-mode speed)
                mach_proxy = round(1.0 + (delta_v / 70.0), 2)
                event = {
                    "time": curr.get("time_tag", ""),
                    "delta_speed_kms": round(delta_v, 1),
                    "density_ratio": round(ratio_n, 2),
                    "magnetic_ratio": round(ratio_b, 2),
                    "mach_proxy": mach_proxy,
                    "upstream_speed": round(v1, 1),
                    "downstream_speed": round(v2, 1),
                    "classification": "Fast Forward CME Shock" if delta_v > 100 else "Interplanetary Shock / CIR"
                }
                if last_index is not None and i - last_index <= 3:
                    if delta_v > shocks[-1]["delta_speed_kms"]:
                        shocks[-1] = event
                else:
                    shocks.append(event)
                last_index = i

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

        `values` must be evenly sampled every `dt_seconds`; missing samples (None/NaN)
        are linearly interpolated across interior gaps rather than removed, because
        removing them would splice the series and corrupt the frequency axis. Leading
        and trailing gaps are trimmed. The PSD is one-sided and normalised by the
        window power, so it is in (input unit)^2 / Hz and integrates to the variance.
        """
        raw = np.array([np.nan if v is None else float(v) for v in values], dtype=float)
        finite = np.isfinite(raw)
        if finite.any():
            idx = np.flatnonzero(finite)
            raw = raw[idx[0]:idx[-1] + 1]
            finite = np.isfinite(raw)
        gap_fraction = float(1.0 - finite.mean()) if raw.size else 1.0
        if raw.size and not finite.all():
            pos = np.arange(raw.size)
            raw[~finite] = np.interp(pos[~finite], pos[finite], raw[finite])
        clean_vals = raw.tolist() if finite.any() else []
        if len(clean_vals) < 32:
            return {
                "frequencies_hz": [],
                "power_density": [],
                "spectral_slope_alpha": None,
                "r_squared": None,
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

        # Real FFT -> one-sided PSD normalised by the window power:
        # P(f_k) = 2 |X_k|^2 / (f_s * sum(w^2)), without doubling DC and Nyquist.
        fft_vals = np.fft.rfft(arr_windowed)
        fs = 1.0 / dt_seconds
        psd_raw = (np.abs(fft_vals) ** 2) / (fs * float(np.sum(window ** 2)))
        if len(arr) % 2 == 0:
            psd_raw[1:-1] *= 2.0
        else:
            psd_raw[1:] *= 2.0
        freqs_raw = np.fft.rfftfreq(len(arr), d=dt_seconds)

        # Every mode but DC (only the first 120 were kept, so a day of 1-min data was fitted
        # between 0.01 and 1.4 mHz, across the 1/f range and the start of the inertial range).
        freqs = [float(f) for f in freqs_raw[1:]]
        psd = [float(p) for p in psd_raw[1:]]

        # Slope fitted to the spectrum averaged in logarithmic bins (10 per decade) between
        # PSD_FIT_FMIN_HZ (above the 1/f range at 1 AU) and half the Nyquist frequency (the top
        # octave of averaged data is distorted by aliasing): the raw periodogram has 100 %
        # scatter per mode and most modes at the top, which dominated the fit.
        f_arr = np.array(freqs)
        p_arr = np.array(psd)
        f_hi = 0.5 * fs / 2.0
        in_range = (p_arr > 0) & (f_arr >= PSD_FIT_FMIN_HZ) & (f_arr <= f_hi)
        if np.sum(in_range) < 8:  # short series: the whole spectrum below half the Nyquist frequency
            in_range = (p_arr > 0) & (f_arr <= f_hi)
        fit_f, fit_p = [], []
        if np.any(in_range):
            lf, lp = np.log10(f_arr[in_range]), np.log10(p_arr[in_range])
            edges = np.arange(lf.min(), lf.max() + 0.1, 0.1)
            which = np.digitize(lf, edges)
            for b in np.unique(which):
                sel = which == b
                fit_f.append(float(np.mean(lf[sel])))
                fit_p.append(float(np.mean(lp[sel])))  # log-mean: the periodogram's log bias is a constant
        fit_f, fit_p = np.array(fit_f), np.array(fit_p)
        valid_mask = np.isfinite(fit_p)
        alpha_err = None

        # No fit (e.g. a constant series has no power): no slope rather than a made-up -5/3.
        alpha = None
        r2 = None
        kolmogorov_psd = []
        iroshnikov_psd = []
        regime = "No power-law fit (flat or zero spectrum)"

        if np.sum(valid_mask) >= 6:
            log_f = fit_f[valid_mask]
            log_p = fit_p[valid_mask]

            # Linear regression
            slope, intercept = np.polyfit(log_f, log_p, 1)
            alpha = float(-slope)

            y_pred = slope * log_f + intercept
            ss_tot = np.sum((log_p - np.mean(log_p)) ** 2)
            ss_res = np.sum((log_p - y_pred) ** 2)
            r2 = float(1.0 - (ss_res / max(1e-9, ss_tot))) if ss_tot > 0 else 0.0
            # Standard error of the slope from the residuals of the binned fit
            sxx = float(np.sum((log_f - log_f.mean()) ** 2))
            alpha_err = float(np.sqrt(ss_res / max(1, len(log_f) - 2) / sxx)) if sxx > 0 else None

            # Reference curves anchored at median log_f / log_p
            f_mid = float(np.median(log_f))
            p_mid = float(np.median(log_p))

            # Kolmogorov -5/3 (-1.667)
            log_kolmo = - (5.0 / 3.0) * (np.log10(f_arr) - f_mid) + p_mid
            kolmogorov_psd = [float(f"{10 ** val:.6g}") for val in log_kolmo]

            # Iroshnikov-Kraichnan -3/2 (-1.50)
            log_ik = - 1.5 * (np.log10(f_arr) - f_mid) + p_mid
            iroshnikov_psd = [float(f"{10 ** val:.6g}") for val in log_ik]

            # What the slope is consistent with, within two standard errors. 1-minute data reach
            # 8 mHz at most: the dissipation range (near 1 Hz) is out of reach, so a steep slope
            # here is not "dissipation".
            tol = 2.0 * (alpha_err or 0.0)
            k41, ik = abs(alpha - 5.0 / 3.0) <= tol, abs(alpha - 1.5) <= tol
            if k41 and ik:
                regime = "Between -3/2 and -5/3 (the fit cannot tell Kolmogorov from Iroshnikov-Kraichnan)"
            elif k41:
                regime = "Consistent with Kolmogorov f⁻⁵/³"
            elif ik:
                regime = "Consistent with Iroshnikov-Kraichnan f⁻³/²"
            elif alpha > 5.0 / 3.0:
                regime = "Steeper than f⁻⁵/³"
            elif alpha >= 0.8:
                regime = "Shallower than f⁻³/² (towards the 1/f range)"
            else:
                regime = f"Flat spectrum (α = {alpha:.2f})"

        v_sw = max(250.0, float(v_sw_kms))
        # Taylor hypothesis: lambda = v_sw / f. At f = 1 mHz (0.001 Hz), lambda = v_sw * 1000 km
        taylor_km_1mhz = v_sw * 1000.0
        r_earth_km = 6371.0
        taylor_re_1mhz = taylor_km_1mhz / r_earth_km

        return {
            # Significant figures, not fixed decimals: PSD values span many decades.
            "frequencies_hz": [float(f"{f:.6g}") for f in freqs],
            "power_density": [float(f"{p:.6g}") for p in psd],
            "dt_seconds": float(dt_seconds),
            "gap_fraction": round(gap_fraction, 4),
            "spectral_slope_alpha": round(alpha, 3) if alpha is not None else None,
            "spectral_slope_error": round(alpha_err, 3) if alpha_err is not None else None,
            "fit_range_hz": [float(f"{10 ** fit_f.min():.3g}"), float(f"{10 ** fit_f.max():.3g}")] if len(fit_f) else None,
            "r_squared": round(max(0.0, min(1.0, r2)), 3) if r2 is not None else None,
            "cascade_regime": regime,
            "fluctuation_rms": round(rms_val, 3),
            "taylor_scale_km_1mhz": round(taylor_km_1mhz, 1),
            "taylor_scale_re_1mhz": round(taylor_re_1mhz, 1),
            "kolmogorov_psd": kolmogorov_psd,
            "iroshnikov_psd": iroshnikov_psd
        }
