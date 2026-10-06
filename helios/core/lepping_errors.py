"""
Fit-parameter uncertainties of the Lundquist magnetic cloud model (Lepping et al. 1990)
from the error study of Lepping, Berdichevsky & Ferguson (2003, J. Geophys. Res. 108(A10),
1356, doi:10.1029/2002JA009657; correction Lepping et al. 2004), as applied to the WIND
magnetic clouds by Lepping et al. (2006, Ann. Geophys. 24, 215, Appendix B and Table 5).

The study fitted 1824 simulated clouds "noised up" with field fluctuations taken from real
WIND clouds and tabulated the spread of each fit parameter against the noise level, the
closest approach and the cone angle. This module is a port of the WIND MFI team's
interpolation program (interpolation_mc.pro, version of 18 Nov 2003, with its input table
sigcommon.pro, "errorfit-input-table" of 22 Aug 2003; https://wind.nasa.gov/mfi/):

- noise level sigma_v [nT] = (155 / 8.3666) chi_R (from Fig. 6 of the error study);
- for each tabulated closest approach (0, 0.3, 0.6, 0.9 R0) and cone angle (90, 60,
  30 deg) a least-squares quadratic in the noise level through the five tabulated noise
  levels (0, 0.5, 2, 3, 4 nT), evaluated at sigma_v;
- a final bilinear step with the weights |CA| / 0.6 and (beta_CA - 90) / (30 - 90), where
  beta_CA = acos(|cos phi_A cos theta_A|) is the cone angle (see _sigma for how the
  program applies them);
- sigma(B0) scaled by B0 / 16.4 nT (the B0 of the simulated clouds), sigma(t0) converted
  to % of the duration by 100 / 12.5 h, sigma(CA) to % of R0.

With the WIND table's chi_R, CA and axis this port gives the uncertainties of Lepping
et al. (2006) Table 5 for 48 of its 50 clouds to the printed precision (the other two
differ by 1 deg in one column, at an integer boundary).
"""
import math
from typing import Any, Dict, List

import numpy as np

NOISE_LEVELS_NT = (0.0, 0.5, 2.0, 3.0, 4.0)
CLOSEST_APPROACH = (0.0, 0.3, 0.6, 0.9)  # units of R0
CONE_ANGLES_DEG = (90.0, 60.0, 30.0)
B0_SIMULATED_NT = 16.4
DURATION_SIMULATED_H = 12.5
# Noise level of chi_R = 0.215, the highest Lepping et al. (2006) accept for a fair fit.
MAX_NOISE_NT = 4.0

# Spread of each parameter in the simulations, indexed [cone angle][closest approach][noise].
ERROR_TABLE: Dict[str, List[List[List[float]]]] = {
    "b0_nT": [
        [[0, 0.21, 0.84, 1.3, 1.78], [0, 0.35, 1.45, 2.01, 2.81], [0, 0.54, 2.09, 4.09, 5.5], [0, 0.54, 2.09, 4.09, 5.5]],
        [[0, 0.2, 0.89, 1.56, 2.28], [0, 0.46, 1.76, 2.46, 3.19], [0, 0.65, 2.45, 4.26, 7.56], [0, 0.65, 2.45, 4.26, 7.56]],
        [[0, 0.21, 0.94, 1.82, 2.78], [0, 0.57, 2.07, 2.91, 3.57], [0, 0.76, 2.81, 5, 9.62], [0, 0.76, 2.81, 5, 9.62]]],
    "r0_1e-2_au": [
        [[0, 0.15, 0.67, 0.99, 1.33], [0, 0.2, 0.76, 0.91, 1.25], [0, 0.27, 1.05, 1.84, 2.56], [0, 0.27, 1.05, 1.84, 2.56]],
        [[0, 0.2, 0.81, 1.21, 1.58], [0, 0.22, 0.94, 1.15, 1.39], [0, 0.3, 1.18, 1.88, 2.56], [0, 0.3, 1.18, 1.88, 2.56]],
        [[0, 0.24, 0.95, 1.43, 1.83], [0, 0.24, 1.12, 1.45, 2.2], [0, 0.33, 1.31, 1.92, 2.56], [0, 0.33, 1.31, 1.92, 2.56]]],
    "t0_hours": [
        [[0, 0.61, 1.73, 1.97, 2.13], [0, 0.65, 1.89, 2.1, 2.13], [0, 0.67, 1.93, 2.12, 2.13], [0, 0.67, 1.93, 2.12, 2.13]],
        [[0, 0.95, 2.18, 2.19, 2.19], [0, 0.97, 2.18, 2.19, 2.19], [0, 0.99, 2.18, 2.19, 2.19], [0, 0.99, 2.18, 2.19, 2.19]],
        [[0, 1.3, 2.19, 2.19, 2.19], [0, 1.3, 2.19, 2.19, 2.19], [0, 1.3, 2.19, 2.19, 2.19], [0, 1.3, 2.19, 2.19, 2.19]]],
    "closest_approach": [
        [[0, 0.047, 0.195, 0.286, 0.363], [0, 0.044, 0.186, 0.262, 0.38], [0, 0.045, 0.18, 0.34, 0.446], [0, 0.045, 0.18, 0.34, 0.446]],
        [[0, 0.065, 0.258, 0.389, 0.5], [0, 0.06, 0.246, 0.343, 0.5], [0, 0.05, 0.201, 0.4, 0.517], [0, 0.05, 0.201, 0.4, 0.517]],
        [[0, 0.071, 0.283, 0.471, 0.637], [0, 0.071, 0.283, 0.471, 0.637], [0, 0.071, 0.283, 0.471, 0.637], [0, 0.071, 0.283, 0.471, 0.637]]],
    "theta_a_deg": [
        [[0, 3.8, 10.8, 13.1, 15.3], [0, 4.6, 12.5, 15.5, 18], [0, 4.9, 12.7, 18.8, 22], [0, 4.9, 12.7, 18.8, 22]],
        [[0, 5, 12.2, 14, 15.3], [0, 5.7, 12.5, 15.7, 18.9], [0, 5.2, 13.2, 18.8, 22.9], [0, 5.2, 13.2, 18.8, 22.9]],
        [[0, 6.2, 13.2, 16.2, 19], [0, 6.2, 13.2, 16.2, 19], [0, 6.2, 13.2, 18.8, 22.9], [0, 6.2, 13.2, 18.8, 22.9]]],
    "cone_deg": [
        [[0, 5, 17.9, 24.7, 30.1], [0, 5.5, 18.9, 24.6, 30.4], [0, 6.3, 20, 28.4, 33.9], [0, 6.3, 20, 28.4, 33.9]],
        [[0, 6.6, 21.4, 30, 36.3], [0, 6.9, 21.9, 29.7, 36.4], [0, 6.9, 22.2, 29.9, 37], [0, 6.9, 22.2, 29.9, 37]],
        [[0, 8.2, 24.9, 34.8, 42.4], [0, 8.3, 24.9, 34.8, 42.4], [0, 8.3, 24.9, 34.8, 42.4], [0, 8.3, 24.9, 34.8, 42.4]]],
    "abs_theta_a_deg": [
        [[0, 2.8, 8.6, 10.7, 12.3], [0, 3.4, 10, 12.1, 14.4], [0, 3.8, 10.1, 14.8, 17.1], [0, 3.8, 10.1, 14.8, 17.1]],
        [[0, 3.7, 9.9, 11.4, 12.3], [0, 4.2, 10, 12, 13.9], [0, 4, 10.7, 14.6, 18.5], [0, 4, 10.7, 14.6, 18.5]],
        [[0, 4.7, 10.8, 13.4, 15.4], [0, 4.7, 10.8, 13.4, 15.4], [0, 4.7, 10.8, 14.8, 18.5], [0, 4.7, 10.8, 14.8, 18.5]]],
}


def _sigma(name: str, noise_nt: float, ca: float, cone_deg: float) -> float:
    a = np.asarray(ERROR_TABLE[name], dtype=float)
    at_noise = np.empty((len(CONE_ANGLES_DEG), len(CLOSEST_APPROACH)))
    for bi in range(len(CONE_ANGLES_DEG)):
        for ci in range(len(CLOSEST_APPROACH)):
            at_noise[bi, ci] = np.polyval(np.polyfit(NOISE_LEVELS_NT, a[bi, ci], 2), noise_nt)
    # The program's final step, kept exactly as written (it is what reproduces Table 5 of
    # Lepping et al. 2006): sigma_2[CA, beta] is interpolated with the weight |CA| / 0.6
    # between beta = 90 and 30 deg at CA = 0 and at CA = 0.6, and the two results with the
    # weight (beta_CA - 90) / (30 - 90), i.e. the two weights act on the other axis than
    # their names suggest.
    s0 = at_noise[0, 0] + (at_noise[2, 0] - at_noise[0, 0]) * (ca / 0.6)
    s1 = at_noise[0, 2] + (at_noise[2, 2] - at_noise[0, 2]) * (ca / 0.6)
    return float(s0 + (s1 - s0) * ((cone_deg - 90.0) / (30.0 - 90.0)))


def lepping_uncertainties(b0_nt: float, chi_r: float, closest_approach_percent: float,
                          axis_longitude_deg: float, axis_latitude_deg: float) -> Dict[str, Any]:
    """1-sigma uncertainties of the flux rope fit parameters (Lepping et al. 2003 error study)."""
    ca = abs(closest_approach_percent) / 100.0
    cone = math.degrees(math.acos(min(1.0, abs(math.cos(math.radians(axis_longitude_deg)) *
                                               math.cos(math.radians(axis_latitude_deg))))))
    noise = 155.0 / 8.3666 * chi_r
    s = {k: _sigma(k, noise, ca, cone) for k in ERROR_TABLE}
    warnings = []
    if noise > MAX_NOISE_NT:
        warnings.append(f"chi_R {chi_r:.3f} means a noise level of {noise:.1f} nT, above the 4 nT range of the "
                        "error study (Lepping et al. 2006 rate such fits poor): the errors are extrapolated.")
    if cone < 25.0:
        warnings.append(f"The axis is within {cone:.0f} deg of the Sun-Earth line, outside the cone angles of the "
                        "error study (30-90 deg): the errors are extrapolated.")
    if ca > 0.9:
        warnings.append("The closest approach is beyond 0.9 R0, outside the error study.")
    return {
        "b0_nT": s["b0_nT"] * b0_nt / B0_SIMULATED_NT,
        "diameter_au": 2.0 * s["r0_1e-2_au"] / 100.0,
        "radius_au": s["r0_1e-2_au"] / 100.0,
        "asymmetry_factor_percent": s["t0_hours"] / DURATION_SIMULATED_H * 100.0,
        "closest_approach_percent": s["closest_approach"] * 100.0,
        "axis_latitude_deg": s["theta_a_deg"],
        "axis_abs_latitude_deg": s["abs_theta_a_deg"],
        "axis_cone_deg": s["cone_deg"],
        "noise_level_nT": noise,
        "cone_angle_beta_ca_deg": cone,
        "warnings": warnings,
        "method": ("Lepping, Berdichevsky & Ferguson (2003) error study of noised-up simulated clouds, interpolated "
                   "as in the WIND MFI team's interpolation_mc.pro (Lepping et al. 2006, Appendix B)"),
    }
