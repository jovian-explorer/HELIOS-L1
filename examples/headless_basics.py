"""
HELIOS-L1 without the window: its models called from Python, offline (no network needed).

    pip install "helios-l1 @ git+https://github.com/jovian-explorer/HELIOS-L1.git"
    python examples/headless_basics.py

Every function used here is in helios.core and takes plain numbers, lists or NumPy arrays.
"""
from datetime import datetime, timedelta

import numpy as np

from helios.core.aurora_model import AuroralModel
from helios.core.event_analysis import minimum_variance
from helios.core.parker_spiral import ParkerSpiralModel
from helios.core.science import SpaceWeatherPhysics as swp

# 1. A solar wind sample: 650 km/s, 15 per cm^3, IMF By = 5 nT, Bz = -20 nT (a CME sheath)
v, n, by, bz = 650.0, 15.0, 5.0, -20.0
p = swp.dynamic_pressure(n, v)                              # nPa (OMNI flow pressure)
r0, alpha = swp.shue1998_magnetopause(p, bz)                # Shue et al. (1998)
print(f"Dynamic pressure {p:.1f} nPa, magnetopause stand-off {r0:.2f} Earth radii (flaring {alpha:.2f})")
print(f"Newell coupling dPhi/dt {swp.newell_coupling(v, by, bz):.0f} (km/s)^(4/3) nT^(2/3)")

# 2. NOAA scales for Kp 8, an X2 flare (2e-4 W/m^2) and 150 pfu of >= 10 MeV protons
s = swp.classify_noaa_scales(8.0, bz, 2e-4, 150.0)
print(f"NOAA scales: {s['g_scale']}, {s['r_scale']}, {s['s_scale']}")

# 3. Auroral oval (Starkov 1994): equatorward edge at magnetic midnight for Kp 8
al = AuroralModel.kp_to_al(8.0)
print(f"Kp 8 -> |AL| {al:.0f} nT; oval edge at midnight {AuroralModel.starkov_latitude(al, 0.0):.1f} deg CGM latitude")

# 4. Ring current: 12 hours of that solar wind after quiet conditions (O'Brien & McPherron 2000)
t0 = datetime(2024, 5, 10, 18)
wind = [{"time_tag": (t0 + timedelta(minutes=10 * k)).strftime("%Y-%m-%d %H:%M:%S"),
         "speed": v, "density": n, "bz_gsm": bz, "dynamic_pressure": p} for k in range(73)]
dst = AuroralModel.simulate_dst_evolution(wind, model="obrien", initial_dst=-10.0)
print(f"Dst after 12 h of this wind: {dst[-1]['dst_predicted_nt']:.0f} nT")

# 5. Parker spiral at 1 AU for 400 km/s
print(f"Parker spiral angle {ParkerSpiralModel.spiral_pitch_angle(400.0)} deg; "
      f"Earth connects to {ParkerSpiralModel.magnetic_footpoint_longitude(400.0)} deg W on the Sun")

# 6. Minimum variance analysis of a field rotating about x (a flux rope crossing)
t = np.linspace(-1.0, 1.0, 200)
b = np.c_[np.full_like(t, 2.0), 5 * np.cos(np.pi * t / 2), 5 * np.sin(np.pi * t / 2)]
b += np.random.default_rng(0).normal(0.0, 0.1, b.shape)
mva = minimum_variance(b, n_bootstrap=200)
print(f"MVA: minimum variance direction {np.round(mva['eigenvectors']['min'], 3)}, "
      f"lambda2/lambda3 = {mva['ratio_intermediate_to_min']:.0f}")
