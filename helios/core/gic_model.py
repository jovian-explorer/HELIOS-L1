"""
Geomagnetically Induced Currents (GIC) & Ground Geoelectric Field (E-field) Hazard Engine.
Calculates ground electric fields (V/km) induced by space weather geomagnetic perturbations (dB/dt),
quantifying power grid transformer core saturation, pipeline corrosion, and railway signaling risks.
"""
import math
from typing import Dict, Any

class GICHazardModel:
    """Computes surface geoelectric fields and power transmission grid vulnerability."""

    # Standard regional 1-D Earth conductivity profiles (USGS / NRC / EPRI models)
    GEOLOGICAL_ZONES = {
        "precambrian_shield": {
            "name": "Precambrian Crystalline Shield (High Risk)",
            "description": "Granitic, resistive basement rock with very low conductivity. Drives maximum geoelectric fields.",
            "resistivity_ohm_m": 5000.0,
            "apparent_conductivity_s_m": 0.0002,
            "example_regions": "Canadian Shield, Fennoscandia, Northern US, Baltic craton"
        },
        "sedimentary_basin": {
            "name": "Sedimentary Rock Basin (Low/Moderate Risk)",
            "description": "Porous, conductive sediments with high moisture/salinity that attenuate induced voltages.",
            "resistivity_ohm_m": 50.0,
            "apparent_conductivity_s_m": 0.02,
            "example_regions": "US Gulf Coast, Central Europe, Indo-Gangetic Plains"
        },
        "coastal_margin": {
            "name": "Coastal Ocean Transition (Edge Enhancement)",
            "description": "Coast effect where high-conductivity seawater contrasts with continental crust, focusing GIC.",
            "resistivity_ohm_m": 500.0,
            "apparent_conductivity_s_m": 0.002,
            "example_regions": "US Atlantic Coast, North Sea Coast, Japanese Archipelago"
        }
    }

    @staticmethod
    def calculate_geoelectric_field(
        db_dt_nt_per_min: float = 120.0,
        geology_type: str = "precambrian_shield",
        transformer_neutral_resistance_ohms: float = 0.5,
        transmission_line_length_km: float = 200.0
    ) -> Dict[str, Any]:
        """
        Calculates horizontal geoelectric field E_H and quasi-DC neutral current based on
        Boteler & Pirjola (2017) plane-wave surface impedance formulation:
        E_H = sqrt(rho / (mu_0 * omega)) * |dB/dt|
        """
        zone = GICHazardModel.GEOLOGICAL_ZONES.get(geology_type, GICHazardModel.GEOLOGICAL_ZONES["precambrian_shield"])
        rho = zone["resistivity_ohm_m"]

        # Magnetic permeability of free space
        mu_0 = 4.0 * math.pi * 1e-7  # H/m

        # Dominant geomagnetic pulsation frequency (typically period T ~ 100 to 300 s, omega = 2*pi / T)
        t_period_s = 180.0
        omega = 2.0 * math.pi / t_period_s

        # Convert dB/dt from nT/min to Tesla/sec: 1 nT = 1e-9 T, 1 min = 60 s
        db_dt_t_per_s = (abs(db_dt_nt_per_min) * 1e-9) / 60.0

        # Surface impedance magnitude: |Z| = sqrt(omega * mu_0 * rho)
        # E = |Z| * (Delta B / mu_0)  ==> E = sqrt(rho / (mu_0 * omega)) * (dB/dt)
        # Result in Volts per meter, then convert to Volts per kilometer (x 1000)
        e_field_v_per_m = math.sqrt(rho / (mu_0 * omega)) * db_dt_t_per_s
        e_field_v_per_km = e_field_v_per_m * 1000.0

        # Induced voltage along transmission line length L: V = E * L
        induced_voltage_volts = e_field_v_per_km * transmission_line_length_km

        # Quasi-DC current entering transformer grounded neutral: I = V / R_loop
        # Approximate loop resistance: R_neutral + R_line (approx 1.5 - 3.0 ohms total)
        r_loop = max(0.2, transformer_neutral_resistance_ohms + 1.2)
        neutral_gic_amperes = induced_voltage_volts / r_loop

        # Risk categories (HELIOS-L1's own bands, not from a standard; NERC TPL-007 uses an
        # 8 V/km benchmark event at 60 deg geomagnetic latitude)
        if e_field_v_per_km >= 5.0:
            hazard_level = "CRITICAL (Carrington / Quebec 1989 Scale)"
            grid_impact = "Widespread transformer half-cycle saturation, voltage collapse, and relay tripping imminent."
            color = "#f43f5e"
        elif e_field_v_per_km >= 2.0:
            hazard_level = "SEVERE (High Grid Stress)"
            grid_impact = "Elevated reactive power consumption, harmonic distortion, and localized transformer heating."
            color = "#f97316"
        elif e_field_v_per_km >= 0.5:
            hazard_level = "MODERATE (Operational Vigilance)"
            grid_impact = "Observable quasi-DC neutral currents; monitored by grid dispatch centers."
            color = "#eab308"
        else:
            hazard_level = "NOMINAL (Normal System Operation)"
            grid_impact = "Minimal ground induced potentials; well within equipment tolerances."
            color = "#10b981"

        return {
            "status": "success",
            "db_dt_nt_per_min": round(db_dt_nt_per_min, 1),
            "geology_selected": zone["name"],
            "resistivity_ohm_m": rho,
            "geoelectric_field_v_km": round(e_field_v_per_km, 3),
            "induced_voltage_volts": round(induced_voltage_volts, 1),
            "transformer_neutral_current_amps": round(neutral_gic_amperes, 1),
            "hazard_classification": hazard_level,
            "grid_impact_assessment": grid_impact,
            "status_color": color,
            "assumptions": [
                f"Uniform half-space of {rho:g} ohm m and a single geomagnetic period of {t_period_s:g} s (plane wave).",
                "Loop resistance = neutral resistance + 1.2 ohm (assumed line and winding resistance).",
                "Hazard bands (0.5 / 2 / 5 V/km) are HELIOS-L1 categories, not a standard.",
            ],
            "benchmarks": {
                "hydro_quebec_1989": "No single measured field value; 9-hour province-wide blackout",
                "halloween_2003_malmo": "About 2 V/km at 20:04 UT on 30 October 2003 (Wik et al. 2009, Ann. Geophys. 27, 1775); 130 kV line tripped",
                "sweden_july_1982": "4-5 V/km near Stockholm (Wik et al. 2009); railway signals disturbed",
                "nerc_tpl_007": "8 V/km benchmark event at 60 deg geomagnetic latitude"
            }
        }
