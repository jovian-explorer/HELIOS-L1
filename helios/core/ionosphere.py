"""
D-Region Ionospheric Radio Absorption (D-RAP) & High-Frequency (HF) Blackout Engine.
Models solar flare X-ray and energetic proton induced ionization of the ionospheric D-layer (60-90 km),
quantifying signal attenuation (dB) across 3-30 MHz HF communications for aviation and maritime operations.
"""
import math
from typing import Dict, Any

from helios.core.science import SpaceWeatherPhysics

class IonosphericModel:
    """Calculates D-region absorption, highest affected frequency (HAF), and polar blackout risk."""

    @staticmethod
    def calculate_drap_absorption(
        xray_flux_watts_m2: float = 2.5e-5,
        zenith_angle_deg: float = 30.0
    ) -> Dict[str, Any]:
        """
        Computes ionospheric absorption with the NOAA SWPC D-RAP X-ray (flare) relation
        (D-RAP documentation; Sauer & Wilkinson 2008 describe its proton/polar part, not modelled here):
            HAF_0 = 10 * log10(F_x) + 65            [MHz, subsolar; F_x in W/m^2]
            HAF   = HAF_0 * cos(chi)^0.75           [zenith-angle reduction]
            A(f)  = (HAF / f)^1.5                   [dB]
        so the attenuation is 1 dB at the HAF by definition (M1 -> 15 MHz, X1 -> 25 MHz).
        
        Parameters:
        - xray_flux_watts_m2: GOES 0.1-0.8 nm soft X-ray irradiance (e.g. M1.0 = 1e-5, X1.0 = 1e-4)
        - zenith_angle_deg: Solar zenith angle chi (0 deg = subsolar point, 90 deg = terminator)
        """
        f_x = max(1e-8, xray_flux_watts_m2)
        chi_rad = math.radians(min(89.0, max(0.0, zenith_angle_deg)))

        # Subsolar HAF (MHz); non-positive below ~A3 (3e-7 W/m^2), i.e. no absorption.
        haf_subsolar = max(0.0, 10.0 * math.log10(f_x) + 65.0)

        # Zenith correction on the HAF: cos(chi)^0.75
        cos_chi = max(0.01, math.cos(chi_rad))
        haf_mhz = haf_subsolar * (cos_chi ** 0.75)

        # Attenuation at 10 MHz: A(10) = (HAF / 10)^1.5 dB
        a_local_10mhz = (haf_mhz / 10.0) ** 1.5 if haf_mhz > 0 else 0.0
        a_subsolar_10mhz = (haf_subsolar / 10.0) ** 1.5 if haf_subsolar > 0 else 0.0

        # Frequency profile across HF band (3 MHz to 30 MHz in 1 MHz steps)
        hf_frequencies = [3, 5, 7, 10, 14, 18, 21, 24, 28, 30]
        absorption_spectrum = []
        for freq in hf_frequencies:
            # Power-law attenuation: A(f) = (HAF / f)^1.5
            att_db = (haf_mhz / freq) ** 1.5 if haf_mhz > 0 else 0.0
            absorption_spectrum.append({
                "frequency_mhz": freq,
                "attenuation_db": round(att_db, 2),
                "signal_degradation_pct": round(min(100.0, (1.0 - 10.0 ** (-att_db / 10.0)) * 100.0), 1),
                "usability": "Complete Blackout" if att_db > 10.0 else ("Severely Degraded" if att_db > 3.0 else "Operational")
            })

        # NOAA R-scale Radio Blackout classification
        r_scale, hazard_level = (
            ("R0 - Nominal", "No Significant Ionospheric Radio Blackout"),
            ("R1 - Minor (M1)", "Weak or Minor Degradation of HF Radio"),
            ("R2 - Moderate (M5)", "Limited Blackout of HF Radio on Sunlit Earth"),
            ("R3 - Strong (X1)", "Wide Area Loss of HF Radio Communications"),
            ("R4 - Severe (X10)", "Widespread Dayside HF Radio Blackout"),
            ("R5 - Extreme (X20+)", "Catastrophic Dayside HF Radio Blackout"),
        )[SpaceWeatherPhysics.noaa_r_level(f_x)]

        return {
            "status": "success",
            "xray_flux_watts_m2": f_x,
            "r_scale": r_scale,
            "hazard_level": hazard_level,
            "zenith_angle_deg": round(zenith_angle_deg, 1),
            "highest_affected_frequency_mhz": round(haf_mhz, 2),
            "attenuation_at_10mhz_db": round(a_local_10mhz, 2),
            "subsolar_peak_absorption_db": round(a_subsolar_10mhz, 2),
            # Flare absorption acts on the sunlit side; polar routes are hit by solar proton
            # (polar cap) absorption, which this model does not include.
            "polar_aviation_impact": (f"HF below about {haf_mhz:.0f} MHz lost on the sunlit side (aviation HF voice links)" if haf_mhz > 15.0
                                      else ("Lower HF bands degraded on the sunlit side" if haf_mhz > 5.0 else "No significant flare absorption")),
            "absorption_spectrum": absorption_spectrum
        }
