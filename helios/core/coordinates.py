"""
Geophysical coordinate transforms (GSE <-> GSM).

Follows Hapgood (1992), "Space physics coordinate transformations: a user guide",
Planet. Space Sci. 40, 711-717 (doi:10.1016/0032-0633(92)90012-D), with the
corrections of Hapgood (1997) and the recommendation of Fraenz & Harper (2002) to take
the geomagnetic dipole axis from the IGRF degree-1 coefficients for the epoch rather
than from Hapgood's 1985 linear fit.

* GSE: X towards the Sun, Z towards the ecliptic north pole.
* GSM: X towards the Sun, Z the projection of the northern dipole axis onto the GSE YZ
  plane. GSM is GSE rotated about X by the angle psi, so X components are identical.

Accuracy: the dipole tilt is good to about 0.01 deg; transformed components agree with
the GSM values published in OMNI to the 0.01 nT rounding of that dataset.
"""
from typing import Iterable, Tuple, Union

import numpy as np
import pandas as pd

# IGRF-14 (IAGA 2024) degree-1 Schmidt coefficients in nT for 1900-2025 every 5 years,
# from https://www.ngdc.noaa.gov/IAGA/vmod/coeffs/igrf14coeffs.txt (DGRF up to 2020,
# IGRF 2025), and the predictive secular variation for 2025-2030 in nT/yr.
IGRF_EPOCHS = np.arange(1900.0, 2025.0 + 1.0, 5.0)
IGRF_G10 = np.array([-31543, -31464, -31354, -31212, -31060, -30926, -30805, -30715, -30654,
                     -30594, -30554, -30500, -30421, -30334, -30220, -30100, -29992, -29873,
                     -29775, -29692, -29619.4, -29554.63, -29496.57, -29441.46, -29403.41,
                     -29350.0])
IGRF_G11 = np.array([-2298, -2298, -2297, -2306, -2317, -2318, -2316, -2306, -2292, -2285,
                     -2250, -2215, -2169, -2119, -2068, -2013, -1956, -1905, -1848, -1784,
                     -1728.2, -1669.05, -1586.42, -1501.77, -1451.37, -1410.3])
IGRF_H11 = np.array([5922, 5909, 5898, 5875, 5845, 5817, 5808, 5812, 5821, 5810, 5815, 5820,
                     5791, 5776, 5737, 5675, 5604, 5500, 5406, 5306, 5186.1, 5077.99, 4944.26,
                     4795.99, 4653.35, 4545.5])
IGRF_SV = (12.6, 10.0, -21.5)  # dg10/dt, dg11/dt, dh11/dt for 2025-2030

TimesLike = Union[str, pd.Timestamp, Iterable]


def _mjd(times: TimesLike) -> np.ndarray:
    """Modified Julian Date (UTC) of each time stamp. Naive times are taken as UTC."""
    raw = pd.Series(np.atleast_1d(np.asarray(times, dtype=object)))
    try:
        t = pd.to_datetime(raw, utc=True, format="mixed")
    except (TypeError, ValueError):
        t = pd.to_datetime(raw, utc=True)
    return ((t.dt.tz_convert(None) - pd.Timestamp("1858-11-17")) / pd.Timedelta(days=1)).to_numpy(dtype=float)


def dipole_coefficients(decimal_year: np.ndarray) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """IGRF g10, g11, h11 (nT): linear between 5-year epochs, secular variation after 2025."""
    y = np.asarray(decimal_year, dtype=float)
    g10 = np.interp(y, IGRF_EPOCHS, IGRF_G10)
    g11 = np.interp(y, IGRF_EPOCHS, IGRF_G11)
    h11 = np.interp(y, IGRF_EPOCHS, IGRF_H11)
    late = np.clip(y - IGRF_EPOCHS[-1], 0.0, None)
    return g10 + IGRF_SV[0] * late, g11 + IGRF_SV[1] * late, h11 + IGRF_SV[2] * late


def geo_to_gse(times: TimesLike, x, y, z) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Rotate GEO vectors to GSE (Hapgood 1992): T2 T1^-1 with T1 = <theta, Z> (GEI -> GEO)
    and T2 = <lambda_sun, Z> * <epsilon, X> (GEI -> GSE). Inputs broadcast against the times.
    """
    mjd = _mjd(times)
    mjd0 = np.floor(mjd)
    hours = (mjd - mjd0) * 24.0
    t0 = (mjd0 - 51544.5) / 36525.0  # Julian centuries from J2000 to 0h UT
    qx, qy, qz = (np.asarray(v, dtype=float) for v in (x, y, z))

    # GEO -> GEI: rotate by -theta (Greenwich mean sidereal time) about Z.
    theta = np.radians(100.461 + 36000.770 * t0 + 15.04107 * hours)
    xi = np.cos(theta) * qx - np.sin(theta) * qy
    yi = np.sin(theta) * qx + np.cos(theta) * qy
    zi = qz + 0.0 * theta

    # GEI -> GSE: obliquity of the ecliptic, then the Sun's ecliptic longitude.
    eps = np.radians(23.439 - 0.013 * t0)
    m = np.radians(357.528 + 35999.050 * t0 + 0.04107 * hours)
    lam = np.radians(280.460 + 36000.772 * t0 + 0.04107 * hours
                     + (1.915 - 0.0048 * t0) * np.sin(m) + 0.020 * np.sin(2.0 * m))
    ye_ecl = np.cos(eps) * yi + np.sin(eps) * zi
    ze = -np.sin(eps) * yi + np.cos(eps) * zi
    return np.cos(lam) * xi + np.sin(lam) * ye_ecl, -np.sin(lam) * xi + np.cos(lam) * ye_ecl, ze


def dipole_axis_gse(times: TimesLike) -> np.ndarray:
    """
    Unit vector of the northern geomagnetic dipole axis in GSE, shape (n, 3): the IGRF
    degree-1 pole in GEO (along -(g11, h11, g10)) rotated with geo_to_gse.
    """
    return np.column_stack(geo_to_gse(times, *dipole_axis_geo(times).T))


def gse_gsm_angle(times: TimesLike) -> np.ndarray:
    """Rotation angle psi (radians) about X from GSE to GSM: tan(psi) = y_e / z_e of the dipole axis."""
    q = dipole_axis_gse(times)
    return np.arctan2(q[:, 1], q[:, 2])


def dipole_tilt_deg(times: TimesLike) -> np.ndarray:
    """Dipole tilt angle (deg): angle of the dipole axis from the GSM Z axis, positive towards the Sun."""
    q = dipole_axis_gse(times)
    return np.degrees(np.arctan2(q[:, 0], np.sqrt(q[:, 1] ** 2 + q[:, 2] ** 2)))


def gse_to_gsm(times: TimesLike, x, y, z) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    Rotate GSE vectors to GSM (T3 = <-psi, X>). Inputs broadcast against the times;
    NaN components stay NaN. Returns (x, y, z) in GSM.
    """
    psi = gse_gsm_angle(times)
    x, y, z = (np.asarray(v, dtype=float) for v in (x, y, z))
    c, s = np.cos(psi), np.sin(psi)
    return x + 0.0 * psi, c * y - s * z, s * y + c * z


def gsm_to_gse(times: TimesLike, x, y, z) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Inverse of gse_to_gsm."""
    psi = gse_gsm_angle(times)
    x, y, z = (np.asarray(v, dtype=float) for v in (x, y, z))
    c, s = np.cos(psi), np.sin(psi)
    return x + 0.0 * psi, c * y + s * z, -s * y + c * z


def dipole_axis_geo(times: TimesLike) -> np.ndarray:
    """Unit vector of the northern geomagnetic (centred dipole) pole in GEO, shape (n, 3)."""
    mjd = _mjd(times)
    g10, g11, h11 = dipole_coefficients(2000.0 + (mjd - 51544.0) / 365.25)
    norm = np.sqrt(g10 ** 2 + g11 ** 2 + h11 ** 2)
    return np.column_stack([-g11 / norm, -h11 / norm, -g10 / norm])


def sun_direction_geo(times: TimesLike) -> np.ndarray:
    """
    Unit vector towards the Sun in GEO, shape (n, 3), from the same low-precision solar
    ephemeris as dipole_axis_gse (Hapgood 1992; about 0.01 deg).
    """
    mjd = _mjd(times)
    mjd0 = np.floor(mjd)
    hours = (mjd - mjd0) * 24.0
    t0 = (mjd0 - 51544.5) / 36525.0
    eps = np.radians(23.439 - 0.013 * t0)
    m = np.radians(357.528 + 35999.050 * t0 + 0.04107 * hours)
    lam = np.radians(280.460 + 36000.772 * t0 + 0.04107 * hours
                     + (1.915 - 0.0048 * t0) * np.sin(m) + 0.020 * np.sin(2.0 * m))
    xi, yi, zi = np.cos(lam), np.cos(eps) * np.sin(lam), np.sin(eps) * np.sin(lam)
    # GEI -> GEO: rotate by +theta (Greenwich mean sidereal time) about Z.
    theta = np.radians(100.461 + 36000.770 * t0 + 15.04107 * hours)
    return np.column_stack([np.cos(theta) * xi + np.sin(theta) * yi,
                            -np.sin(theta) * xi + np.cos(theta) * yi, zi])


def _mag_frame(pole: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Centred dipole (MAG) frame axes in GEO: Y = Z_geo x pole (normalised), X = Y x pole."""
    y = np.cross([0.0, 0.0, 1.0], pole)
    y /= np.linalg.norm(y)
    return np.cross(y, pole), y


def mlt_mlat_to_geo(time, mlt_hours, mlat_deg) -> Tuple[np.ndarray, np.ndarray]:
    """
    Geographic latitude and longitude (deg) of points given in centred-dipole magnetic
    latitude and magnetic local time at one UTC time. MLT is measured from the magnetic
    longitude of the Sun: MLT = 12 + (mlon - mlon_sun) / 15 h.
    """
    pole = dipole_axis_geo(time)[0]
    sun = sun_direction_geo(time)[0]
    xm, ym = _mag_frame(pole)
    mlon_sun = np.arctan2(sun @ ym, sun @ xm)
    mlon = mlon_sun + np.radians((np.asarray(mlt_hours, dtype=float) - 12.0) * 15.0)
    mlat = np.radians(np.asarray(mlat_deg, dtype=float))
    v = (np.cos(mlat) * np.cos(mlon))[..., None] * xm + (np.cos(mlat) * np.sin(mlon))[..., None] * ym \
        + np.sin(mlat)[..., None] * pole
    lat = np.degrees(np.arcsin(np.clip(v[..., 2], -1.0, 1.0)))
    lon = np.degrees(np.arctan2(v[..., 1], v[..., 0]))
    return lat, lon


def geo_to_mlt_mlat(time, lat_deg, lon_deg) -> Tuple[np.ndarray, np.ndarray]:
    """Inverse of mlt_mlat_to_geo: (MLT in hours, centred-dipole magnetic latitude in deg)."""
    pole = dipole_axis_geo(time)[0]
    sun = sun_direction_geo(time)[0]
    xm, ym = _mag_frame(pole)
    lat, lon = np.radians(np.asarray(lat_deg, dtype=float)), np.radians(np.asarray(lon_deg, dtype=float))
    v = np.stack([np.cos(lat) * np.cos(lon), np.cos(lat) * np.sin(lon), np.sin(lat)], axis=-1)
    mlon = np.arctan2(v @ ym, v @ xm)
    mlt = (12.0 + np.degrees(mlon - np.arctan2(sun @ ym, sun @ xm)) / 15.0) % 24.0
    return mlt, np.degrees(np.arcsin(np.clip(v @ pole, -1.0, 1.0)))
