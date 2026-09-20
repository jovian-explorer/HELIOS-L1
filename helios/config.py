"""
Configuration and mission catalog for HELIOS-L1.
"""
import sys
import os
from pathlib import Path
from typing import Dict, Any

# Root directories - resilient across source, PyInstaller onedir, PyInstaller onefile, and Windows installed path
if getattr(sys, 'frozen', False):
    bundle_root = Path(getattr(sys, '_MEIPASS', Path(sys.executable).parent))
    if (bundle_root / "helios" / "gui" / "static").exists():
        BASE_DIR = bundle_root / "helios"
    elif (bundle_root / "gui" / "static").exists():
        BASE_DIR = bundle_root
    elif (Path(sys.executable).parent / "_internal" / "helios" / "gui" / "static").exists():
        BASE_DIR = Path(sys.executable).parent / "_internal" / "helios"
    else:
        BASE_DIR = Path(sys.executable).parent / "helios"
    PROJECT_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).resolve().parent
    PROJECT_DIR = BASE_DIR.parent

STATIC_DIR = BASE_DIR / "gui" / "static"
SAMPLE_EVENTS_DIR = BASE_DIR / "data" / "sample_events"
try:
    SAMPLE_EVENTS_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    pass

# Safe writable Cache Directory:
# Uses user home directory to guarantee write permissions and bypass Windows Store AppContainer virtualization
CACHE_DIR = Path.home() / ".helios" / "cache"

try:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    import tempfile
    CACHE_DIR = Path(tempfile.gettempdir()) / "helios_cache"
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

# Network & Server Settings
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765

# Comprehensive Space Weather Missions Metadata
MISSIONS: Dict[str, Dict[str, Any]] = {
    "DSCOVR": {
        "name": "DSCOVR",
        "full_name": "Deep Space Climate Observatory",
        "agency": "NOAA / NASA / USAF",
        "location": "Sun-Earth L1 (Lissajous Orbit)",
        "orbit_distance_km": 1500000,
        "launch_year": 2015,
        "status": "Active (Primary L1 Space Weather Monitor)",
        "instruments": [
            {"id": "PlasMag_FC", "name": "Faraday Cup", "measures": "Proton density, bulk velocity, thermal speed"},
            {"id": "PlasMag_MAG", "name": "Fluxgate Magnetometer", "measures": "IMF Bx, By, Bz (GSM/GSE), Total B"}
        ],
        "primary_params": ["bz_gsm", "bt", "speed", "density", "temperature"],
        "color": "#3b82f6"
    },
    "ACE": {
        "name": "ACE",
        "full_name": "Advanced Composition Explorer",
        "agency": "NASA / Caltech",
        "location": "Sun-Earth L1 (Halo Orbit)",
        "orbit_distance_km": 1480000,
        "launch_year": 1997,
        "status": "Active (Secondary / Backup L1 Monitor)",
        "instruments": [
            {"id": "MAG", "name": "Magnetic Field Experiment", "measures": "IMF vectors Bx, By, Bz, Bt"},
            {"id": "SWEPAM", "name": "Solar Wind Electron Proton Alpha Monitor", "measures": "Solar wind speed, density, temperature"},
            {"id": "EPAM", "name": "Electron, Proton, and Alpha Monitor", "measures": "Energetic particles & solar flare shock ions"}
        ],
        "primary_params": ["bz_gsm", "bt", "speed", "density", "temperature"],
        "color": "#10b981"
    },
    "ADITYA_L1": {
        "name": "Aditya-L1",
        "full_name": "Aditya-L1 Solar Observatory",
        "agency": "ISRO (Indian Space Research Organisation)",
        "location": "Sun-Earth L1 (Halo Orbit)",
        "orbit_distance_km": 1500000,
        "launch_year": 2023,
        "status": "Active (Operational Science Phase)",
        "instruments": [
            {"id": "ASPEX", "name": "Aditya Solar Wind Particle Experiment", "measures": "Proton & Alpha solar wind distributions (SWIS & STEPS)"},
            {"id": "PAPA", "name": "Plasma Analyser Package for Aditya", "measures": "Solar wind electron/ion composition and energy spectra"},
            {"id": "MAG", "name": "Tri-axial High Resolution Magnetometer", "measures": "Interplanetary magnetic field vectors at L1"},
            {"id": "VELC", "name": "Visible Emission Line Coronagraph", "measures": "Solar corona & CME kinematics"}
        ],
        "primary_params": ["bz_gsm", "bt", "speed", "density", "temperature"],
        "color": "#f59e0b"
    },
    "WIND": {
        "name": "WIND",
        "full_name": "WIND Spacecraft",
        "agency": "NASA / GSFC",
        "location": "Sun-Earth L1 (Halo Orbit)",
        "orbit_distance_km": 1520000,
        "launch_year": 1994,
        "status": "Active (Long-baseline Science Baseline)",
        "instruments": [
            {"id": "MFI", "name": "Magnetic Field Investigation", "measures": "High-precision vector magnetic field"},
            {"id": "SWE", "name": "Solar Wind Experiment", "measures": "Ion velocity distributions & thermal properties"},
            {"id": "3DP", "name": "3-D Plasma and Energetic Particles", "measures": "Energetic particle spectra"}
        ],
        "primary_params": ["bz_gsm", "bt", "speed", "density", "temperature"],
        "color": "#06b6d4"
    },
    "SOHO": {
        "name": "SOHO",
        "full_name": "Solar and Heliospheric Observatory",
        "agency": "ESA / NASA",
        "location": "Sun-Earth L1 (Halo Orbit)",
        "orbit_distance_km": 1500000,
        "launch_year": 1995,
        "status": "Active (Historic & Active Coronagraphy)",
        "instruments": [
            {"id": "LASCO_C2", "name": "Large Angle and Spectrometric Coronagraph C2", "measures": "White-light CME imaging (2 to 6 R_sun)"},
            {"id": "LASCO_C3", "name": "Large Angle and Spectrometric Coronagraph C3", "measures": "Outer CME trajectory (3.7 to 32 R_sun)"},
            {"id": "CELIAS_MTOF", "name": "Charge, Element, and Isotope Analysis System", "measures": "Solar wind speed & composition"}
        ],
        "primary_params": ["speed", "cme_speed", "cme_angular_width"],
        "color": "#8b5cf6"
    },
    "GOES_16": {
        "name": "GOES-16",
        "full_name": "Geostationary Operational Environmental Satellite 16",
        "agency": "NOAA / NASA",
        "location": "Geostationary Orbit (East - 75.2° W, ~35,786 km)",
        "orbit_distance_km": 42164,
        "launch_year": 2016,
        "status": "Active (Geostationary Magnetosphere & X-Ray)",
        "instruments": [
            {"id": "EXIS_XRS", "name": "Extreme Ultraviolet and X-ray Irradiance Sensors", "measures": "Solar X-ray flux (0.05-0.4 nm & 0.1-0.8 nm) for flare classification"},
            {"id": "MAG", "name": "Geostationary Magnetometer", "measures": "Earth's magnetospheric field compression (Hp, He, Hn)"},
            {"id": "SEISS", "name": "Space Environment In-Situ Suite", "measures": "Solar energetic proton (SEP) events"}
        ],
        "primary_params": ["xray_flux_short", "xray_flux_long", "hp_mag", "proton_flux"],
        "color": "#ec4899"
    },
    "STEREO_A": {
        "name": "STEREO-A",
        "full_name": "Solar Terrestrial Relations Observatory Ahead",
        "agency": "NASA",
        "location": "Heliocentric Orbit (Ahead of Earth, ~0.96 AU)",
        "orbit_distance_km": 145000000,
        "launch_year": 2006,
        "status": "Active (Off-Sun-Earth Axis Solar Wind & CME View)",
        "instruments": [
            {"id": "SECCHI", "name": "Sun Earth Connection Coronal and Heliospheric Investigation", "measures": "Stereoscopic CME side-view"},
            {"id": "PLASTIC", "name": "Plasma and SupraThermal Ion Composition", "measures": "Solar wind protons & alphas"},
            {"id": "IMPACT", "name": "In-situ Measurements of Particles and CME Transients", "measures": "Heliospheric magnetic field & SEPs"}
        ],
        "primary_params": ["bt", "speed", "density"],
        "color": "#f97316"
    },
    "SDO": {
        "name": "SDO",
        "full_name": "Solar Dynamics Observatory",
        "agency": "NASA",
        "location": "Geosynchronous Orbit (Inclined)",
        "orbit_distance_km": 42164,
        "launch_year": 2010,
        "status": "Active (Ultra-HD Solar Atmosphere Imaging)",
        "instruments": [
            {"id": "AIA", "name": "Atmospheric Imaging Assembly", "measures": "Multi-wavelength EUV solar coronal dynamics (94Å, 131Å, 171Å, 193Å, 211Å, 304Å)"},
            {"id": "HMI", "name": "Helioseismic and Magnetic Imager", "measures": "Photospheric vector magnetic field & active region sunspots"}
        ],
        "primary_params": ["euv_flares", "magnetic_complexity"],
        "color": "#e11d48"
    }
}

# Real-time Public APIs (NOAA Space Weather Prediction Center)
NOAA_SWPC_ENDPOINTS = {
    "plasma_7day": "https://services.swpc.noaa.gov/products/solar-wind/plasma-7-day.json",
    "plasma_1day": "https://services.swpc.noaa.gov/products/solar-wind/plasma-1-day.json",
    "mag_7day": "https://services.swpc.noaa.gov/products/solar-wind/mag-7-day.json",
    "mag_1day": "https://services.swpc.noaa.gov/products/solar-wind/mag-1-day.json",
    "xrays_7day": "https://services.swpc.noaa.gov/json/goes/primary/xrays-7-day.json",
    "xrays_1day": "https://services.swpc.noaa.gov/json/goes/primary/xrays-1-day.json",
    "kp_7day": "https://services.swpc.noaa.gov/products/noaa-planetary-k-index.json",
    "alerts": "https://services.swpc.noaa.gov/products/alerts.json"
}

# Physical Constants for Space Weather
CONSTANTS = {
    "AU_KM": 149597870.7,
    "L1_DISTANCE_KM": 1496000.0,
    "PROTON_MASS_KG": 1.67262192369e-27,
    "BOLTZMANN_K": 1.380649e-23,
    "MU_0": 1.25663706212e-6,
    "EARTH_RADIUS_KM": 6371.0
}
