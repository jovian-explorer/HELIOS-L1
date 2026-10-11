"""
Astronomical constants shared by the HELIOS-L1 models (one definition each).

* R_SUN_KM: nominal solar radius, IAU 2015 Resolution B3 (695,700 km).
* AU_KM: astronomical unit, IAU 2012 Resolution B2 (149,597,870.7 km).
* OMEGA_SUN_SIDEREAL: the Sun's sidereal rotation rate of the Carrington system,
  2 pi / 25.38 d (the synodic Carrington period, seen from Earth, is 27.2753 d). The Parker
  spiral, the ballistic mapping of the solar wind and the corotation of the field along a ray
  use the sidereal rate: the wind moves radially in an inertial frame.
"""
import math

R_SUN_KM = 695700.0
AU_KM = 149597870.7
OMEGA_SUN_SIDEREAL = 2.0 * math.pi / (25.38 * 86400.0)  # rad/s, 2.8653e-6
