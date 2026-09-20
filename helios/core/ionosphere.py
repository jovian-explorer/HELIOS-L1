"""
D-Region Ionospheric Radio Absorption (D-RAP) & High-Frequency (HF) Blackout Engine.
Models solar flare X-ray and energetic proton induced ionization of the ionospheric D-layer (60-90 km),
quantifying signal attenuation (dB) across 3-30 MHz HF communications for aviation and maritime operations.
"""
import math
from typing import Dict, List, Any

class IonosphericModel:
    """Calculates D-region absorption, highest affected frequency (HAF), and polar blackout risk."""

    @staticmethod
    def calculate_drap_absorption(
        xray_flux_watts_m2: float = 2.5e-5,
        zenith_angle_deg: float = 30.0
    ) -> Dict[str, Any]:
        """
        Computes ionospheric absorption based on Sauer & Wilkinson (2008) D-RAP formulation.
        
        Parameters:
        - xray_flux_watts_m2: GOES 0.1-0.8 nm soft X-ray irradiance (e.g. M1.0 = 1e-5, X1.0 = 1e-4)
        - zenith_angle_deg: Solar zenith angle chi (0 deg = subsolar point, 90 deg = terminator)
        """
        f_x = max(1e-8, xray_flux_watts_m2)
        chi_rad = math.radians(min(89.0, max(0.0, zenith_angle_deg)))

        # Subsolar 10 MHz baseline absorption in dB: A_0 = 10 * sqrt(F_x / 1e-4)
        a_subsolar_10mhz = 10.0 * math.sqrt(f_x / 1.0e-4)

        # Zenith correction: cos(chi)^0.75
        cos_chi = max(0.01, math.cos(chi_rad))
        a_local_10mhz = a_subsolar_10mhz * (cos_chi ** 0.75)

        # Highest Affected Frequency (HAF) in MHz (where attenuation A >= 1.0 dB):
        # A(f) = A_local * (10 / f)^1.5 >= 1.0  ==>  f <= 10 * (A_local)^(2/3)
        if a_local_10mhz > 0.05:
            haf_mhz = min(35.0, max(3.0, 10.0 * (a_local_10mhz ** (2.0 / 3.0))))
        else:
            haf_mhz = 0.0

        # Frequency profile across HF band (3 MHz to 30 MHz in 1 MHz steps)
        hf_frequencies = [3, 5, 7, 10, 14, 18, 21, 24, 28, 30]
        absorption_spectrum = []
        for freq in hf_frequencies:
            # Power-law attenuation: A(f) = A_10 * (10 / f)^1.5
            att_db = a_local_10mhz * ((10.0 / freq) ** 1.5)
            absorption_spectrum.append({
                "frequency_mhz": freq,
                "attenuation_db": round(att_db, 2),
                "signal_degradation_pct": round(min(100.0, (1.0 - 10.0 ** (-att_db / 10.0)) * 100.0), 1),
                "usability": "Complete Blackout" if att_db > 10.0 else ("Severely Degraded" if att_db > 3.0 else "Operational")
            })

        # NOAA R-scale Radio Blackout classification
        if f_x >= 2.0e-3:
            r_scale = "R5 - Extreme (X20+)"
            hazard_level = "Catastrophic Dayside HF Radio Blackout"
        elif f_x >= 1.0e-3:
            r_scale = "R4 - Severe (X10)"
            hazard_level = "Widespread Dayside HF Radio Blackout"
        elif f_x >= 1.0e-4:
            r_scale = "R3 - Strong (X1)"
            hazard_level = "Wide Area Loss of HF Radio Communications"
        elif f_x >= 5.0e-5:
            r_scale = "R2 - Moderate (M5)"
            hazard_level = "Limited Blackout of HF Radio on Sunlit Earth"
        elif f_x >= 1.0e-5:
            r_scale = "R1 - Minor (M1)"
            hazard_level = "Weak or Minor Degradation of HF Radio"
        else:
            r_scale = "R0 - Nominal"
            hazard_level = "No Significant Ionospheric Radio Blackout"

        return {
            "status": "success",
            "xray_flux_watts_m2": f_x,
            "r_scale": r_scale,
            "hazard_level": hazard_level,
            "zenith_angle_deg": round(zenith_angle_deg, 1),
            "highest_affected_frequency_mhz": round(haf_mhz, 2),
            "attenuation_at_10mhz_db": round(a_local_10mhz, 2),
            "subsolar_peak_absorption_db": round(a_subsolar_10mhz, 2),
            "polar_aviation_impact": "Loss of primary trans-polar ATC communications" if haf_mhz > 15.0 else ("Selective degradation on lower HF bands" if haf_mhz > 5.0 else "Normal ATC communications"),
            "absorption_spectrum": absorption_spectrum
        }
