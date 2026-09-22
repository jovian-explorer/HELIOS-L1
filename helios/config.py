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

# System Performance & Hardware Concurrency Settings
TOTAL_CPU_CORES = os.cpu_count() or 4
ACTIVE_PROCESSOR_CORES = max(1, min(TOTAL_CPU_CORES, 4))
ACTIVE_THEME = "mission-slate"
ACTIVE_FONT_SIZE = "normal"
ACTIVE_TIMEZONE = "UTC"

def get_system_settings() -> Dict[str, Any]:
    """Returns current system execution and user preference configuration."""
    return {
        "total_cpu_cores": TOTAL_CPU_CORES,
        "active_processors": ACTIVE_PROCESSOR_CORES,
        "theme": ACTIVE_THEME,
        "font_size": ACTIVE_FONT_SIZE,
        "timezone": ACTIVE_TIMEZONE,
        "python_version": sys.version.split()[0],
        "platform": sys.platform
    }

def update_system_settings(processors: int = None, theme: str = None, font_size: str = None, timezone: str = None) -> Dict[str, Any]:
    """Updates runtime system settings."""
    global ACTIVE_PROCESSOR_CORES, ACTIVE_THEME, ACTIVE_FONT_SIZE, ACTIVE_TIMEZONE
    if processors is not None and 1 <= processors <= max(1, TOTAL_CPU_CORES * 2):
        ACTIVE_PROCESSOR_CORES = int(processors)
    if theme is not None:
        ACTIVE_THEME = str(theme)
    if font_size is not None:
        ACTIVE_FONT_SIZE = str(font_size)
    if timezone is not None:
        ACTIVE_TIMEZONE = str(timezone)
    return get_system_settings()

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
        "coordinate_system": "GSE & GSM (Geocentric Solar Ecliptic / Magnetospheric)",
        "cadence": "1-minute real-time stream / 60-second verified Level 2",
        "data_portal_name": "NOAA SWPC Data Access / NCEI Archive",
        "data_portal_url": "https://services.swpc.noaa.gov/products/solar-wind/",
        "data_license": "U.S. Public Domain (NOAA Open Data / 17 U.S.C. § 105)",
        "license_badge": "Public Domain",
        "doi": "10.1007/s11214-016-0243-7",
        "primary_citation": "Burt, J., & Smith, C. W. (2012). Deep Space Climate Observatory: The DSCOVR Mission. Space Sci. Rev.",
        "instruments": [
            {"id": "PlasMag_FC", "name": "Faraday Cup", "measures": "Proton density, bulk velocity, thermal speed"},
            {"id": "PlasMag_MAG", "name": "Fluxgate Magnetometer", "measures": "IMF Bx, By, Bz (GSM/GSE), Total B"}
        ],
        "primary_params": ["bz_gsm", "bt", "speed", "density", "temperature"],
        "color": "#38bdf8"
    },
    "ACE": {
        "name": "ACE",
        "full_name": "Advanced Composition Explorer",
        "agency": "NASA / Caltech",
        "location": "Sun-Earth L1 (Halo Orbit)",
        "orbit_distance_km": 1480000,
        "launch_year": 1997,
        "status": "Active (Secondary / Backup L1 Monitor)",
        "coordinate_system": "GSE & GSM Coordinates",
        "cadence": "16-second magnetic / 64-second plasma moments",
        "data_portal_name": "NASA CDAWeb / Caltech ACE Science Center",
        "data_portal_url": "https://cdaweb.gsfc.nasa.gov/",
        "data_license": "NASA Open Data Policy (Public Domain / CC0 1.0 Universal)",
        "license_badge": "CC0 / Open Access",
        "doi": "10.1007/978-94-011-4762-0_1",
        "primary_citation": "Stone, E. C., et al. (1998). The Advanced Composition Explorer. Space Sci. Rev., 86, 1–22.",
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
        "coordinate_system": "Sun-Earth L1 Halo Reference Frame / GSE",
        "cadence": "8-second vector MAG / 1-minute ASPEX ion distributions",
        "data_portal_name": "ISRO Indian Space Science Data Centre (ISSDC / PRADAN)",
        "data_portal_url": "https://www.issdc.gov.in/",
        "data_license": "ISRO Open Science Data Policy (Academic & Research Fair Use)",
        "license_badge": "ISRO Open Science",
        "doi": "10.1007/s12036-021-09724-4",
        "primary_citation": "Seetha, S., & Megala, S. (2017). Aditya-L1 Mission. Current Science, 113(4), 610–612.",
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
        "coordinate_system": "GSE & GSM Coordinates",
        "cadence": "3-second fluxgate / 92-second ion moments",
        "data_portal_name": "NASA CDAWeb / Goddard Space Flight Center",
        "data_portal_url": "https://cdaweb.gsfc.nasa.gov/",
        "data_license": "NASA Open Data Policy (CC0 1.0 Universal)",
        "license_badge": "CC0 / Open Access",
        "doi": "10.1007/BF00751320",
        "primary_citation": "Acuña, M. H., et al. (1995). The Global Geospace Science Program. Space Sci. Rev., 71, 5–21.",
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
        "coordinate_system": "Heliocentric Carrington / Stonyhurst",
        "cadence": "12-minute LASCO C2/C3 coronagraphs / 30-second CELIAS moments",
        "data_portal_name": "ESA SOAR Science Archive & NASA SOHO Archive",
        "data_portal_url": "https://soar.esac.esa.int/",
        "data_license": "ESA Open Access Policy (CC-BY-SA 3.0 IGO) & NASA Public Domain",
        "license_badge": "CC-BY-SA 3.0 IGO",
        "doi": "10.1007/BF00744537",
        "primary_citation": "Domingo, V., Fleck, B., & Poland, A. I. (1995). The SOHO Mission: an overview. Sol. Phys., 162, 1–37.",
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
        "coordinate_system": "Geostationary Coordinate Frame (HP, HE, HN)",
        "cadence": "1-second magnetometer / 1-second XRS irradiance",
        "data_portal_name": "NOAA SWPC Data Portal / NOAA NCEI",
        "data_portal_url": "https://services.swpc.noaa.gov/json/goes/primary/",
        "data_license": "U.S. Public Domain (NOAA Open Data / 17 U.S.C. § 105)",
        "license_badge": "Public Domain",
        "doi": "10.1029/2019SW002214",
        "primary_citation": "Kress, B. T., et al. (2020). Real-time GOES-16 space environment monitor data products. Space Weather, 18.",
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
        "coordinate_system": "Heliocentric Radial Tangential Normal (RTN)",
        "cadence": "1-minute in-situ magnetic / 10-minute SECCHI imaging",
        "data_portal_name": "NASA CDAWeb / STEREO Science Center",
        "data_portal_url": "https://stereo-ssc.nascom.nasa.gov/",
        "data_license": "NASA Open Data Policy (CC0 1.0 Universal)",
        "license_badge": "CC0 / Open Access",
        "doi": "10.1007/s11214-007-9277-0",
        "primary_citation": "Kaiser, M. L., et al. (2008). The STEREO Mission: An overview. Space Sci. Rev., 136, 5–16.",
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
        "coordinate_system": "Helioprojective Cartesian (Solar-X, Solar-Y)",
        "cadence": "12-second AIA multi-wavelength EUV / 45-second HMI magnetograms",
        "data_portal_name": "Stanford JSOC / NASA SDO Data Portal",
        "data_portal_url": "https://sdo.gsfc.nasa.gov/data/",
        "data_license": "NASA Open Data Policy (CC0 1.0 Universal)",
        "license_badge": "CC0 / Open Access",
        "doi": "10.1007/s11207-011-9776-8",
        "primary_citation": "Pesnell, W. D., Thompson, B. J., & Chamberlin, P. C. (2012). The Solar Dynamics Observatory (SDO). Sol. Phys., 275, 3–15.",
        "instruments": [
            {"id": "AIA", "name": "Atmospheric Imaging Assembly", "measures": "Multi-wavelength EUV solar coronal dynamics (94Å, 131Å, 171Å, 193Å, 211Å, 304Å)"},
            {"id": "HMI", "name": "Helioseismic and Magnetic Imager", "measures": "Photospheric vector magnetic field & active region sunspots"}
        ],
        "primary_params": ["euv_flares", "magnetic_complexity"],
        "color": "#e11d48"
    },
    "PARKER_SOLAR_PROBE": {
        "name": "Parker Solar Probe",
        "full_name": "NASA Parker Solar Probe (PSP)",
        "agency": "NASA / JHUAPL",
        "location": "Inner Heliosphere (Perihelion 9.86 R☉ ~ 0.046 AU, Aphelion 0.73 AU)",
        "orbit_distance_km": 6850000,
        "launch_year": 2018,
        "status": "Active (Solar Corona Plunge & Alfvén Surface Penetration)",
        "coordinate_system": "Heliocentric Radial Tangential Normal (RTN)",
        "cadence": "High-rate FIELDS vector magnetic & SWEAP plasma moments",
        "data_portal_name": "NASA CDAWeb & JHUAPL PSP Science Gateway",
        "data_portal_url": "https://parkersolarprobe.jhuapl.edu/",
        "data_license": "NASA Open Data Policy (CC0 1.0 Universal)",
        "license_badge": "CC0 / Open Access",
        "doi": "10.1007/s11214-015-0211-6",
        "primary_citation": "Fox, N. J., et al. (2016). The Solar Probe Plus Mission: Humanity's First Visit to Our Star. Space Sci. Rev., 204, 7–48.",
        "instruments": [
            {"id": "FIELDS", "name": "Electromagnetic Fields Suite", "measures": "DC/AC magnetic fields, Poynting flux, and magnetic switchbacks"},
            {"id": "SWEAP", "name": "Solar Wind Electrons Alphas and Protons", "measures": "Thermal electrons, protons, and alpha velocity distributions"},
            {"id": "ISOIS", "name": "Integrated Science Investigation of the Sun", "measures": "Energetic solar particles across wide energy spectra"},
            {"id": "WISPR", "name": "Wide-field Imager for Solar PRobe", "measures": "Heliospheric white-light imaging of coronal streamers and CMEs"}
        ],
        "primary_params": ["v_vis_viva_kms", "r_heliocentric_au", "switchback_deflections"],
        "color": "#f43f5e"
    },
    "SOLAR_ORBITER": {
        "name": "Solar Orbiter",
        "full_name": "ESA / NASA Solar Orbiter (SolO)",
        "agency": "ESA / NASA",
        "location": "Inclined Heliocentric Orbit (Perihelion 0.28 AU, Aphelion 0.91 AU)",
        "orbit_distance_km": 42000000,
        "launch_year": 2020,
        "status": "Active (High-Latitude Solar Polar & Coronal In-Situ)",
        "coordinate_system": "Heliocentric Stonyhurst & RTN Coordinates",
        "cadence": "Continuous MAG / SWA plasma composition streams",
        "data_portal_name": "ESA Solar Orbiter Archive (SOAR)",
        "data_portal_url": "https://soar.esac.esa.int/",
        "data_license": "ESA Open Access (CC-BY-SA 3.0 IGO)",
        "license_badge": "CC-BY-SA 3.0",
        "doi": "10.1051/0004-6361/202038570",
        "primary_citation": "Müller, D., et al. (2020). The Solar Orbiter mission: Science overview. Astronomy & Astrophysics, 642, A1.",
        "instruments": [
            {"id": "MAG", "name": "Magnetometer", "measures": "High-precision vector magnetic field measurements"},
            {"id": "SWA", "name": "Solar Wind Analyser", "measures": "Solar wind ion and electron velocity distributions and composition"},
            {"id": "EPD", "name": "Energetic Particle Detector", "measures": "Supra-thermal and energetic particles"},
            {"id": "RPW", "name": "Radio and Plasma Waves", "measures": "Magnetic and electric fields and radio emissions"},
            {"id": "EUI", "name": "Extreme Ultraviolet Imager", "measures": "High-resolution solar atmospheric imaging up to solar poles"}
        ],
        "primary_params": ["v_vis_viva_kms", "r_heliocentric_au", "polar_magnetic_field"],
        "color": "#06b6d4"
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

# Global Data Repositories, Observatories & Open Data Licenses
DATA_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "NOAA_SWPC": {
        "id": "NOAA_SWPC",
        "name": "NOAA Space Weather Prediction Center (SWPC)",
        "agency": "National Oceanic and Atmospheric Administration (NOAA)",
        "country": "United States",
        "url": "https://services.swpc.noaa.gov/",
        "data_license": "U.S. Public Domain (NOAA Open Data / 17 U.S.C. § 105)",
        "license_badge": "Public Domain",
        "data_products": [
            "DSCOVR Real-Time Solar Wind (RTSW) 1-min / 5-min Plasma & MAG",
            "GOES-16/18 High-Energy Solar X-ray Irradiance (XRS 0.05-0.4 nm & 0.1-0.8 nm)",
            "Planetary K-index (Kp) & Geomagnetic Storm Classification (G1-G5)",
            "Active Space Weather Watches, Warnings, and Sudden Impulses"
        ],
        "terms_of_use": "Freely available worldwide for public, operational, and commercial use with attribution."
    },
    "NASA_CDAWEB": {
        "id": "NASA_CDAWEB",
        "name": "NASA Coordinated Data Analysis Web (CDAWeb)",
        "agency": "NASA Goddard Space Flight Center / SPDF",
        "country": "United States",
        "url": "https://cdaweb.gsfc.nasa.gov/",
        "data_license": "NASA Open Data Policy (Open Access / CC0 1.0 Universal)",
        "license_badge": "CC0 / Open Data",
        "data_products": [
            "ACE SWEPAM Calibrated Solar Wind Proton & Electron Moments",
            "ACE MAG High-Resolution 16-sec Interplanetary Vector Magnetic Field",
            "WIND SWE Ion Velocity Distributions & MFI Vector Time Series",
            "NASA OMNIWeb Cross-Calibrated Multi-Spacecraft Heliophysics Sets"
        ],
        "terms_of_use": "Open access. Acknowledgement of NASA CDAWeb and SPDF requested in scientific publications."
    },
    "ISRO_ISSDC": {
        "id": "ISRO_ISSDC",
        "name": "Indian Space Science Data Centre (ISSDC / PRADAN)",
        "agency": "ISRO (Indian Space Research Organisation)",
        "country": "India",
        "url": "https://www.issdc.gov.in/",
        "data_license": "ISRO Science Data Policy for Aditya-L1 Payloads",
        "license_badge": "ISRO Open Science",
        "data_products": [
            "Aditya-L1 ASPEX (SWIS / STEPS) Solar Wind Proton & Alpha Distribution",
            "Aditya-L1 PAPA Solar Wind Composition & Energy Spectra",
            "Aditya-L1 MAG Tri-Axial Interplanetary Magnetic Field Vectors",
            "Aditya-L1 VELC Solar Coronal Emission Line Observations"
        ],
        "terms_of_use": "Accessible for academic research, education, and global heliophysics collaboration."
    },
    "ESA_SOAR": {
        "id": "ESA_SOAR",
        "name": "ESA Solar and Heliospheric Science Archive (SOAR / ESAC)",
        "agency": "European Space Agency (ESA)",
        "country": "Europe / International",
        "url": "https://soar.esac.esa.int/",
        "data_license": "ESA Open Access Policy (Creative Commons Attribution-ShareAlike 3.0 IGO)",
        "license_badge": "CC-BY-SA 3.0 IGO",
        "data_products": [
            "SOHO LASCO C2 and C3 White-Light Coronal Mass Ejection Imaging",
            "SOHO CELIAS MTOF Solar Wind Charge and Elemental Abundances",
            "SOHO EIT Extreme Ultraviolet Solar Disk Imagery"
        ],
        "terms_of_use": "Open access under ESA Open Access Policy. Citation of SOHO and ESA/NASA requested."
    },
    "GFZ_POTSDAM": {
        "id": "GFZ_POTSDAM",
        "name": "Helmholtz Centre Potsdam - GFZ German Research Centre for Geosciences",
        "agency": "GFZ Potsdam",
        "country": "Germany",
        "url": "https://www.gfz-potsdam.de/en/kp-index/",
        "data_license": "Creative Commons Attribution 4.0 International (CC-BY 4.0)",
        "license_badge": "CC-BY 4.0",
        "data_products": [
            "Definitive and Real-Time 3-Hour Planetary Kp Index (0 to 9)",
            "International Quiet and Disturbed Days (Q-days / D-days)",
            "Hpo High-Cadence Half-Hourly Planetary Geomagnetic Activity Indices"
        ],
        "terms_of_use": "Open access under CC-BY 4.0. Citation: Matzka, J., et al. (2021), doi:10.5880/Hpo.0001."
    },
    "WDC_KYOTO": {
        "id": "WDC_KYOTO",
        "name": "World Data Center for Geomagnetism, Kyoto",
        "agency": "Data Analysis Center for Geomagnetism, Kyoto University",
        "country": "Japan",
        "url": "https://wdc.kugi.kyoto-u.ac.jp/",
        "data_license": "ICSU World Data System Fair Use Policy",
        "license_badge": "WDS Open Policy",
        "data_products": [
            "Hourly Equatorial Dst Index (Disturbance Storm Time, in nT)",
            "Auroral Electrojet Indices (AE, AL, AU) for High-Latitude Currents",
            "ASyS / ASyD Mid-Latitude Geomagnetic Asymmetry Indices"
        ],
        "terms_of_use": "Freely accessible for research. Formal citation of WDC Kyoto requested."
    }
}

# Authoritative Scientific Literature, Equations, and DOI Citations
SCIENTIFIC_REFERENCES = [
    {
        "id": "newell_coupling_2007",
        "title": "A nearly universal solar wind-magnetosphere coupling function inferred from 10 magnetospheric state variables",
        "authors": "Newell, P. T., Sotirelis, T., Liou, K., Meng, C.-I., & Rich, F. J.",
        "journal": "Journal of Geophysical Research: Space Physics",
        "year": 2007,
        "volume": "112",
        "issue": "A01206",
        "doi": "10.1029/2006JA012015",
        "doi_url": "https://doi.org/10.1029/2006JA012015",
        "category": "Coupling & Magnetospheric Physics",
        "formula": "dPhi_MP/dt = v^(4/3) * B_T^(2/3) * sin^(8/3)(theta_c / 2)",
        "parameters": ["v (bulk solar wind speed)", "B_T (transverse IMF magnitude)", "theta_c (IMF clock angle)"],
        "physical_meaning": "Measures the rate of magnetic flux reconnection at the dayside magnetopause, universally predicting auroral power, polar cap size, and geomagnetic storms."
    },
    {
        "id": "burton_dst_1975",
        "title": "An empirical relationship between interplanetary conditions and Dst",
        "authors": "Burton, R. K., McPherron, R. L., & Russell, C. T.",
        "journal": "Science",
        "year": 1975,
        "volume": "189",
        "issue": "4204",
        "pages": "717-718",
        "doi": "10.1126/science.189.4204.717",
        "doi_url": "https://doi.org/10.1126/science.189.4204.717",
        "category": "Geomagnetic Storm Modeling",
        "formula": "d(Dst*)/dt = Q(t) - Dst* / tau, with Q(t) = -a * (v * B_s - E_c)",
        "parameters": ["Dst* (pressure-corrected Dst)", "Q(t) (ring current injection rate)", "tau (ring current decay timescale)", "B_s (southward IMF)"],
        "physical_meaning": "Dynamically models the growth and decay of the equatorial ring current driven by interplanetary electric field dawn-dusk penetration."
    },
    {
        "id": "akasofu_epsilon_1981",
        "title": "Energy coupling between the solar wind and the magnetosphere",
        "authors": "Akasofu, S.-I.",
        "journal": "Space Science Reviews",
        "year": 1981,
        "volume": "28",
        "issue": "2",
        "pages": "121-190",
        "doi": "10.1007/BF00218810",
        "doi_url": "https://doi.org/10.1007/BF00218810",
        "category": "Energy Flux Formulation",
        "formula": "epsilon = (4 * pi / mu_0) * v * B_T^2 * sin^4(theta_c / 2) * l_0^2",
        "parameters": ["epsilon (Poynting energy flux in Watts)", "l_0 (magnetospheric cross-section length ~ 7 R_E)"],
        "physical_meaning": "Quantifies the total electromagnetic Poynting flux transmitted into Earth's magnetosphere-ionosphere system."
    },
    {
        "id": "shue_magnetopause_1997",
        "title": "A new functional form to study the solar wind control of the magnetopause size and shape",
        "authors": "Shue, J.-H., Chao, J. K., Fu, H. C., Russell, C. T., Song, P., Tsurutani, B. T., & Petrinec, S. M.",
        "journal": "Journal of Geophysical Research: Space Physics",
        "year": 1997,
        "volume": "102",
        "issue": "A5",
        "pages": "9497-9511",
        "doi": "10.1029/97JA00196",
        "doi_url": "https://doi.org/10.1029/97JA00196",
        "category": "Magnetospheric Cavity Geometry",
        "formula": "r = r_0 * (2 / (1 + cos(theta)))^alpha, with r_0 = (10.22 + 1.29 * tanh(0.184 * (Bz + 8.14))) * (P_dyn)^(-1/6.6)",
        "parameters": ["r_0 (subsolar standoff distance in Earth radii R_E)", "alpha (flaring angle)", "P_dyn (solar wind dynamic pressure)"],
        "physical_meaning": "Predicts the compression and erosion of the dayside magnetopause standoff distance under intense solar wind dynamic pressure and southward Bz."
    },
    {
        "id": "vrsnak_dbm_cme_2013",
        "title": "Propagation of coronal mass ejections: The drag-based model",
        "authors": "Vršnak, B., Žic, T., Vrbanec, D., Temmer, M., Rollett, T., Möstl, C., Veronig, A., Čalogović, J., Dumbović, M., Liewer, P., & De Jong, E.",
        "journal": "Solar Physics",
        "year": 2013,
        "volume": "285",
        "issue": "1-2",
        "pages": "295-315",
        "doi": "10.1007/s11207-012-0035-4",
        "doi_url": "https://doi.org/10.1007/s11207-012-0035-4",
        "category": "CME Propagation & Kinematics",
        "formula": "dv/dt = -gamma * (v - w) * |v - w|",
        "parameters": ["gamma (aerodynamic drag parameter ~ 1.8e-7 km^-1)", "w (ambient solar wind speed)", "v (CME shock speed)"],
        "physical_meaning": "Models hydrodynamic and magnetohydrodynamic drag deceleration/acceleration of CMEs traversing from the solar corona to L1 and 1 AU."
    },
    {
        "id": "parker_spiral_1958",
        "title": "Dynamics of the interplanetary gas and magnetic fields",
        "authors": "Parker, E. N.",
        "journal": "The Astrophysical Journal",
        "year": 1958,
        "volume": "128",
        "pages": "664-676",
        "doi": "10.1086/146579",
        "doi_url": "https://doi.org/10.1086/146579",
        "category": "Heliospheric Magnetic Topology",
        "formula": "tan(psi) = (Omega_sun * r * sin(theta)) / v_sw",
        "parameters": ["psi (spiral pitch angle at 1 AU ~ 45 deg)", "Omega_sun (solar rotation rate ~ 2.87e-6 rad/s)"],
        "physical_meaning": "Predicts the Archimedean spiral configuration of the interplanetary magnetic field lines connecting solar active regions to Earth and L1."
    },
    {
        "id": "richardson_cr3bp_1980",
        "title": "Analytic construction of periodic orbits about the collinear points",
        "authors": "Richardson, D. L.",
        "journal": "Celestial Mechanics",
        "year": 1980,
        "volume": "22",
        "issue": "3",
        "pages": "241-253",
        "doi": "10.1007/BF01229511",
        "doi_url": "https://doi.org/10.1007/BF01229511",
        "category": "Astrodynamics & Lagrange Orbits",
        "formula": "x(t) = a_21 * A_x^2 + a_22 * A_z^2 - A_x * cos(omega_p * t + phi) + ...",
        "parameters": ["A_x, A_y, A_z (in-plane and out-of-plane Halo amplitudes)", "omega_p (orbital frequency)"],
        "physical_meaning": "Third-order analytical perturbation solution for stable periodic Halo and Lissajous trajectories at Sun-Earth L1."
    },
    {
        "id": "starkov_aurora_1994",
        "title": "Mathematical model of the auroral boundaries",
        "authors": "Starkov, G. V.",
        "journal": "Geomagnetism and Aeronomy",
        "year": 1994,
        "volume": "34",
        "issue": "3",
        "pages": "331-336",
        "doi": "10.1016/0032-0633(94)90059-0",
        "doi_url": "https://doi.org/10.1016/0032-0633(94)90059-0",
        "category": "Auroral Oval & Ionosphere",
        "formula": "Lambda_eq(MLT, Kp) = Lambda_0 - alpha * Kp - beta * cos(15 deg * (MLT - phi_0))",
        "parameters": ["Lambda_eq (equatorward boundary of diffuse aurora)", "MLT (Magnetic Local Time)"],
        "physical_meaning": "Empirical formulation relating planetary geomagnetic disturbance Kp to the latitudinal expansion and shape of the day/night auroral ovals."
    },
    {
        "id": "bruno_turbulence_2013",
        "title": "The solar wind as a turbulence laboratory",
        "authors": "Bruno, R., & Carbone, V.",
        "journal": "Living Reviews in Solar Physics",
        "year": 2013,
        "volume": "10",
        "pages": "2",
        "doi": "10.12942/lrsp-2013-2",
        "doi_url": "https://doi.org/10.12942/lrsp-2013-2",
        "category": "MHD Waves & Spectral Analysis",
        "formula": "E(f) proportional to f^(-5/3) (Kolmogorov inertial range) -> f^(-1) (1/f low-frequency energy reservoir)",
        "parameters": ["f (fluctuation frequency in Hz)", "E(f) (magnetic field trace power spectral density)"],
        "physical_meaning": "Describes the non-linear cascade of magnetic and kinetic energy in interplanetary space plasma turbulence."
    },
    {
        "id": "hale_magnetic_1919",
        "title": "The magnetic polarity of sun-spots",
        "authors": "Hale, G. E., Ellerman, F., Nicholson, S. B., & Joy, A. H.",
        "journal": "The Astrophysical Journal",
        "year": 1919,
        "volume": "49",
        "pages": "153-178",
        "doi": "10.1086/142452",
        "doi_url": "https://doi.org/10.1086/142452",
        "category": "Solar Flare & Sunspot Classification",
        "formula": "Classes: alpha (unipolar), beta (bipolar), beta-gamma (mixed polarity), beta-gamma-delta (extreme shear)",
        "parameters": ["delta-configuration (opposite polarity umbrae within same penumbra < 2 deg)"],
        "physical_meaning": "Establishes magnetic complexity criteria for active regions that determine the probability of M-class and X-class solar eruptive flares."
    },
    {
        "id": "sauer_drap_2008",
        "title": "Global D-region absorption model (D-RAP) for HF communications",
        "authors": "Sauer, H. H., & Wilkinson, D. C.",
        "journal": "Space Weather",
        "year": 2008,
        "volume": "6",
        "issue": "12",
        "pages": "S12002",
        "doi": "10.1029/2008SW000396",
        "doi_url": "https://doi.org/10.1029/2008SW000396",
        "category": "Ionospheric D-Region & Radio Blackout",
        "formula": "A(f, chi) = 10 * sqrt(F_x / 1e-4) * (10 / f)^1.5 * cos(chi)^0.75,  HAF = 10 * A_0^(2/3)",
        "parameters": ["F_x (GOES soft X-ray flux in W/m^2)", "chi (solar zenith angle)", "f (frequency in MHz)", "HAF (Highest Affected Frequency)"],
        "physical_meaning": "Empirical model computing dayside HF radio signal attenuation (dB) and total blackout thresholds across polar and trans-oceanic aviation corridors."
    },
    {
        "id": "boteler_gic_2017",
        "title": "Modeling geomagnetically induced currents from regional geoelectric fields",
        "authors": "Boteler, D. H., & Pirjola, R. J.",
        "journal": "Space Weather",
        "year": 2017,
        "volume": "15",
        "issue": "1",
        "pages": "258-276",
        "doi": "10.1002/2016SW001499",
        "doi_url": "https://doi.org/10.1002/2016SW001499",
        "category": "Geomagnetically Induced Currents (GIC)",
        "formula": "E_H = sqrt(rho / (mu_0 * omega)) * |dB_H / dt|,  I_neutral = (E_H * L) / R_loop",
        "parameters": ["rho (Earth subsurface resistivity in ohm-m)", "dB_H/dt (geomagnetic perturbation rate in nT/min)", "I_neutral (quasi-DC transformer current)"],
        "physical_meaning": "Relates ground magnetic disturbances to horizontal induced electric fields that drive damaging quasi-DC saturation currents through high-voltage transformer neutrals."
    },
    {
        "id": "hathaway_solar_cycle_2015",
        "title": "The Solar Cycle",
        "authors": "Hathaway, D. H.",
        "journal": "Living Reviews in Solar Physics",
        "year": 2015,
        "volume": "12",
        "issue": "1",
        "pages": "4",
        "doi": "10.1007/lrsp-2015-4",
        "doi_url": "https://doi.org/10.1007/lrsp-2015-4",
        "category": "Solar Cycle 25 Dynamo & Modulation",
        "formula": "SSN(t) = a * (t - t0)^c / (exp((t - t0)^2 / b^2) - 1),  F10.7 = 63.7 + 0.728*SSN + 0.00089*SSN^2",
        "parameters": ["SSN (monthly smoothed sunspot number)", "F10.7 (10.7 cm radio flux in s.f.u.)", "t0 (cycle minimum epoch)"],
        "physical_meaning": "Comprehensive empirical dynamo model describing 11-year sunspot cycle progression, solar maximum timing, and EUV/radio irradiance variations."
    },
    {
        "id": "kolmogorov_turbulence_1941",
        "title": "The Local Structure of Turbulence in Incompressible Viscous Fluid for Very Large Reynolds Numbers",
        "authors": "Kolmogorov, A. N.",
        "journal": "Proceedings of the USSR Academy of Sciences",
        "year": 1941,
        "volume": "30",
        "pages": "301-305",
        "doi": "10.1098/rspa.1991.0075",
        "doi_url": "https://doi.org/10.1098/rspa.1991.0075",
        "category": "MHD Turbulence & Spectral Cascade",
        "formula": "P(k) = C_K * epsilon^(2/3) * k^(-5/3),  log10 P(f) = -5/3 * log10 f + C",
        "parameters": ["epsilon (turbulent energy transfer rate)", "k (wavenumber)", "f (Doppler frequency under Taylor hypothesis)"],
        "physical_meaning": "Governing law of hydrodynamic and plasma turbulence, predicting the universal -5/3 (-1.67) inertial range power spectral density cascade in interplanetary space."
    },
    {
        "id": "iroshnikov_kraichnan_mhd_1965",
        "title": "Inertial-Range Spectrum of Hydromagnetic Turbulence",
        "authors": "Iroshnikov, R. S. (1963) / Kraichnan, R. H. (1965)",
        "journal": "The Physics of Fluids",
        "year": 1965,
        "volume": "8",
        "issue": "7",
        "pages": "1385-1387",
        "doi": "10.1063/1.1761412",
        "doi_url": "https://doi.org/10.1063/1.1761412",
        "category": "MHD Wave & Alfvénic Cascades",
        "formula": "P(k) = C_IK * (epsilon * v_A)^(1/2) * k^(-3/2),  alpha = -1.50",
        "parameters": ["v_A (Alfvén velocity B / sqrt(mu_0 * rho))", "epsilon (energy cascade rate)", "alpha (spectral slope)"],
        "physical_meaning": "Weak MHD wave turbulence model describing the resonant three-wave interaction of counter-propagating Alfvén wave packets in magnetized solar wind plasma."
    },
    {
        "id": "vinas_scudder_shocks_1986",
        "title": "Fast and slow Rankine-Hugoniot shock solution for any arbitrary equation of state and magnetic field orientation",
        "authors": "Viñas, A. F., & Scudder, J. D.",
        "journal": "Journal of Geophysical Research: Space Physics",
        "year": 1986,
        "volume": "91",
        "issue": "A1",
        "pages": "39-58",
        "doi": "10.1029/JA091iA01p00039",
        "doi_url": "https://doi.org/10.1029/JA091iA01p00039",
        "category": "Interplanetary Shocks & Discontinuities",
        "formula": "[rho * v_n] = 0,  [rho * v_n^2 + P + B_t^2 / (2 * mu_0)] = 0,  Delta v > 50 km/s,  r = rho_2 / rho_1 > 1.2",
        "parameters": ["rho (mass density)", "v_n (shock normal velocity)", "P (plasma pressure)", "B_t (transverse magnetic field)"],
        "physical_meaning": "Fundamental conservation laws across fast-forward interplanetary shock boundaries driven by super-Alfvénic coronal mass ejection fronts."
    },
    {
        "id": "gopalswamy_cme_acceleration_2001",
        "title": "Predicting the arrival times of coronal mass ejections",
        "authors": "Gopalswamy, N., Lara, A., Yashiro, S., Kaiser, M. L., & Howard, R. A.",
        "journal": "Journal of Geophysical Research: Space Physics",
        "year": 2001,
        "volume": "106",
        "issue": "A12",
        "pages": "29207-29217",
        "doi": "10.1029/2001JA000177",
        "doi_url": "https://doi.org/10.1029/2001JA000177",
        "category": "Coronal Mass Ejection Kinematics",
        "formula": "a_cme = 2.19 - 0.0054 * v_cme [m/s^2],  T_transit = (-v_0 + sqrt(v_0^2 + 2 * a * d)) / a",
        "parameters": ["v_cme (initial coronagraph plane-of-sky CME velocity in km/s)", "a_cme (interplanetary acceleration / deceleration)", "d (1 AU distance)"],
        "physical_meaning": "Empirical heliospheric aerodynamic interaction formula establishing that fast CMEs (>405 km/s) decelerate while slow CMEs accelerate toward background solar wind."
    },
    {
        "id": "chao_boundaries_2002",
        "title": "Models for the size and shape of the Earth's magnetopause and bow shock",
        "authors": "Chao, J. K., Wu, D. J., Lin, C. H., Yang, Y. H., Wang, X. Y., Kessel, M., Chen, S. H., & Lepping, R. P.",
        "journal": "Space Weather Study Using Multipoint Techniques, COSPAR Colloquia Series",
        "year": 2002,
        "volume": "12",
        "pages": "127-135",
        "doi": "10.1016/S0964-2749(02)80214-7",
        "doi_url": "https://doi.org/10.1016/S0964-2749(02)80214-7",
        "category": "Magnetospheric Cavity & Bow Shock Geometry",
        "formula": "r(theta) = r_0 * [2 / (1 + cos(theta))]^alpha,  r_0,mp = (11.12 + 0.541*Bz)*Pdyn^(-1/6.6),  r_0,bs = (14.5 + 0.08*Bz)*Pdyn^(-1/6.6)*f(M_A)",
        "parameters": ["r_0,mp (subsolar magnetopause distance in R_E)", "r_0,bs (subsolar bow shock standoff distance in R_E)", "M_A (Alfvén Mach number)", "alpha (tail flaring exponent)"],
        "physical_meaning": "Coupled empirical models parameterizing both the dayside magnetopause and upstream bow shock standoffs and flaring geometry based on solar wind dynamic pressure, IMF Bz, and upstream Mach number."
    },
    {
        "id": "boyle_polar_cap_1997",
        "title": "Empirical polar cap potentials",
        "authors": "Boyle, C. B., Reiff, P. H., & Hairston, M. R.",
        "journal": "Journal of Geophysical Research: Space Physics",
        "year": 1997,
        "volume": "102",
        "issue": "A1",
        "pages": "111-125",
        "doi": "10.1029/96JA03058",
        "doi_url": "https://doi.org/10.1029/96JA03058",
        "category": "Cross Polar Cap Potential & Convection",
        "formula": "Phi_PC = 1e-4 * v^2 + 11.7 * B_T * sin^3(theta / 2) [kV]",
        "parameters": ["v (solar wind bulk speed in km/s)", "B_T (IMF transverse field magnitude in nT)", "theta (IMF clock angle)"],
        "physical_meaning": "Quantifies the electric potential drop across the northern/southern polar caps driving high-latitude ionospheric plasma convection and Joule heating."
    },
    {
        "id": "newell_coupling_2007",
        "title": "A nearly universal solar wind-magnetosphere coupling function inferred from 10 magnetospheric state variables",
        "authors": "Newell, P. T., Sotirelis, T., Liou, K., Meng, C.-I., & Rich, F. J.",
        "journal": "Journal of Geophysical Research: Space Physics",
        "year": 2007,
        "volume": "112",
        "issue": "A1",
        "pages": "A01206",
        "doi": "10.1029/2006JA012015",
        "doi_url": "https://doi.org/10.1029/2006JA012015",
        "category": "Universal Solar Wind-Magnetosphere Coupling",
        "formula": "dPhi/dt = v^(4/3) * B_T^(2/3) * sin^(8/3)(theta / 2),  AE ~ 0.048 * (dPhi/dt)^0.85 + 25 [nT]",
        "parameters": ["dPhi/dt (rate of magnetic flux reconnection at dayside magnetopause)", "AE (Auroral Electrojet substorm index)"],
        "physical_meaning": "Universal scaling law correlating solar wind drivers with 10 global magnetospheric response indices including Dst, Kp, AE, and polar cap boundary dynamics."
    }
]

# Standard Scientific Parameter Definitions and Units
PARAMETER_DEFINITIONS: Dict[str, Dict[str, Any]] = {
    "speed": {
        "name": "Solar Wind Bulk Velocity",
        "symbol": "V_sw",
        "unit": "km/s",
        "nominal_range": "300 - 450 km/s (Slow Wind)",
        "disturbed_range": "> 550 km/s (High-Speed Stream / CIR), > 800 km/s (CME Shock)",
        "instrument": "Faraday Cup (DSCOVR) / SWEPAM (ACE) / ASPEX-SWIS (Aditya-L1) / SWE (WIND)",
        "description": "Mean bulk drift speed of protons streaming outward from the solar corona into the heliosphere.",
        "doi": "10.1086/146579"
    },
    "bz_gsm": {
        "name": "Interplanetary Magnetic Field (IMF) Bz Component",
        "symbol": "B_z (GSM)",
        "unit": "nT",
        "nominal_range": "-3 to +5 nT (Northward / Neutral)",
        "disturbed_range": "-10 to -15 nT (Moderate Storm), < -20 nT (Severe G4/G5 Superstorm)",
        "instrument": "Fluxgate Magnetometer (DSCOVR PlasMag / ACE MAG / Aditya-L1 MAG / WIND MFI)",
        "description": "Component of the magnetic field parallel to Earth's magnetic dipole axis in Geocentric Solar Magnetospheric (GSM) coordinates. Negative (southward) Bz drives magnetic reconnection at Earth's dayside magnetopause.",
        "doi": "10.1029/2006JA012015"
    },
    "bt": {
        "name": "Total Interplanetary Magnetic Field Magnitude",
        "symbol": "|B| or B_t",
        "unit": "nT",
        "nominal_range": "3 - 8 nT",
        "disturbed_range": "> 15 nT (Interplanetary Shock), > 35 nT (Intense CME Magnetic Cloud)",
        "instrument": "Tri-axial Magnetometers",
        "description": "Vector magnitude of the heliospheric magnetic field: |B| = sqrt(Bx^2 + By^2 + Bz^2).",
        "doi": "10.1029/97JA00196"
    },
    "density": {
        "name": "Proton Number Density",
        "symbol": "N_p",
        "unit": "cm⁻³",
        "nominal_range": "3 - 8 cm⁻³",
        "disturbed_range": "> 20 cm⁻³ (CIR Compression Sheath), > 50 cm⁻³ (Extreme CME Front)",
        "instrument": "Ion Electrostatic Analyzers & Faraday Cups",
        "description": "Volumetric density of positive hydrogen ions (protons) in the solar wind plasma.",
        "doi": "10.1016/0032-0633(66)90124-3"
    },
    "pdyn": {
        "name": "Solar Wind Dynamic Pressure",
        "symbol": "P_dyn",
        "unit": "nPa",
        "nominal_range": "1.0 - 2.5 nPa",
        "disturbed_range": "> 6 nPa (Strong Compression), > 15 nPa (Severe Magnetopause Compression inside GEO)",
        "formula": "P_dyn = 1.6726e-6 * N_p * V_sw^2 [nPa with V_sw in km/s and N_p in cm⁻³]",
        "description": "Macroscopic momentum flux exerted by the solar wind on Earth's magnetosphere, directly controlling the standoff distance of the subsolar magnetopause.",
        "doi": "10.1016/0032-0633(66)90124-3"
    },
    "epsilon": {
        "name": "Akasofu Energy Coupling Parameter",
        "symbol": "epsilon (ε)",
        "unit": "GW (10⁹ W)",
        "nominal_range": "< 20 GW (Quiet magnetosphere)",
        "disturbed_range": "> 100 GW (Substorm / Moderate Storm), > 1000 GW (Major Geomagnetic Superstorm)",
        "formula": "ε = (4π / μ₀) * v * B_T² * sin⁴(θ_c / 2) * l₀²",
        "description": "Empirical Poynting energy flux transferred across the magnetopause boundary into Earth's ionosphere and ring current.",
        "doi": "10.1007/BF00218810"
    },
    "standoff": {
        "name": "Subsolar Magnetopause Standoff Distance",
        "symbol": "R_mp",
        "unit": "R_E (Earth Radii ~ 6,371 km)",
        "nominal_range": "10.0 - 11.5 R_E (Well outside Geosynchronous Orbit at 6.6 R_E)",
        "disturbed_range": "< 8.0 R_E (Compressed), < 6.6 R_E (Geosynchronous Satellites Exposed to Interplanetary Plasma)",
        "formula": "R_mp = (10.22 + 1.29 * tanh(0.184 * (Bz + 8.14))) * (P_dyn)^(-1/6.6)",
        "description": "The distance from Earth's center along the Sun-Earth line to the balance point where Earth's internal magnetic pressure balances solar wind dynamic pressure.",
        "doi": "10.1029/97JA00196"
    },
    "haf_mhz": {
        "name": "Highest Affected Frequency (D-RAP)",
        "symbol": "HAF",
        "unit": "MHz",
        "nominal_range": "0 MHz (No HF absorption)",
        "disturbed_range": "> 10 MHz (Moderate R2 Blackout), > 25 MHz (Severe R4/R5 Complete HF Blackout)",
        "formula": "HAF = 10 * (10 * sqrt(F_x / 1e-4))^(2/3) [MHz]",
        "instrument": "GOES X-Ray Sensor (XRS) & Ground Riometer Arrays",
        "description": "The highest radio frequency in the High-Frequency (HF, 3-30 MHz) spectrum experiencing at least 1 dB of ionospheric D-region absorption during solar flares.",
        "doi": "10.1029/2008SW000396"
    },
    "f107_flux": {
        "name": "10.7 cm Solar Radio Flux",
        "symbol": "F10.7",
        "unit": "s.f.u. (10⁻²² W m⁻² Hz⁻¹)",
        "nominal_range": "65 - 80 s.f.u. (Solar Minimum)",
        "disturbed_range": "> 150 s.f.u. (Elevated Solar Maximum), > 220 s.f.u. (Intense Solar Flaring Period)",
        "formula": "F10.7 ~ 63.7 + 0.728 * SSN + 0.00089 * SSN²",
        "instrument": "Penticton Radio Observatory (NRC Canada) & Learmonth Observatory",
        "description": "Standard solar activity indicator measuring radio emissions at 2800 MHz (10.7 cm wavelength), tightly correlated with solar EUV radiation driving upper atmosphere satellite drag.",
        "doi": "10.1007/lrsp-2015-4"
    },
    "gic_efield": {
        "name": "Surface Geoelectric Field",
        "symbol": "E_H",
        "unit": "V/km",
        "nominal_range": "< 0.1 V/km (Quiet conditions)",
        "disturbed_range": "> 1.0 V/km (Elevated Grid GIC), > 4.8 V/km (Catastrophic Hydro-Quebec / Carrington Level)",
        "formula": "E_H = sqrt(rho / (mu_0 * omega)) * |dB_H / dt|",
        "instrument": "Ground Magnetometer Stations (INTERMAGNET) & Magnetotelluric Arrays",
        "description": "Horizontal electric field induced at the Earth's surface by rapid geomagnetic perturbations (dB/dt), driving quasi-DC currents through grounded power grids and pipelines.",
        "doi": "10.1002/2016SW001499"
    },
    "spectral_slope": {
        "name": "MHD Turbulence Spectral Index",
        "symbol": "alpha (α)",
        "unit": "dimensionless (log-log slope)",
        "nominal_range": "1.50 - 1.67 (Inertial Range)",
        "disturbed_range": "> 1.80 (Dissipation Range), < 1.30 (Alfvénic / Energy Reservoir)",
        "formula": "log10 P(f) = -alpha * log10 f + C [Kolmogorov -5/3 = -1.67, Iroshnikov-Kraichnan -3/2 = -1.50]",
        "instrument": "High-Cadence Tri-Axial Magnetometers (DSCOVR PlasMag / ACE MAG / WIND MFI)",
        "description": "Logarithmic power-law slope of magnetic and velocity field fluctuations characterizing the turbulent energy cascade through the heliosphere.",
        "doi": "10.12942/lrsp-2013-2"
    },
    "taylor_scale": {
        "name": "Taylor Frozen-in-Flow Spatial Scale",
        "symbol": "lambda (λ)",
        "unit": "km (or Earth Radii R_E)",
        "nominal_range": "300,000 - 550,000 km at 1 mHz (~47 - 86 R_E)",
        "disturbed_range": "> 800,000 km (Fast Solar Wind Stream > 800 km/s)",
        "formula": "lambda = v_sw / f",
        "instrument": "Cross-correlation between solar wind bulk speed and temporal frequency",
        "description": "Spatial wavenumber conversion derived from Taylor's hypothesis: temporal fluctuations measured at a stationary probe reflect spatial turbulent structures swept past at bulk speed.",
        "doi": "10.1098/rspa.1938.0032"
    },
    "alfven_mach": {
        "name": "Alfvén Mach Number",
        "symbol": "M_A",
        "unit": "dimensionless",
        "nominal_range": "6.0 - 10.0 (Super-Alfvénic Wind)",
        "disturbed_range": "< 2.0 (Sub-Alfvénic / Coronal Stream), > 15.0 (Extreme Fast Shock Front)",
        "formula": "M_A = v_sw / v_A,  v_A = B_t / sqrt(mu_0 * rho)",
        "instrument": "Combined Ion Plasma Moments & Magnetometer Telemetry",
        "description": "Ratio of bulk solar wind velocity to local Alfvén wave speed. Dictates bow shock strength and compressibility of heliospheric plasma.",
        "doi": "10.1029/JA091iA01p00039"
    },
    "convective_efield": {
        "name": "Interplanetary Convection Electric Field",
        "symbol": "E_y",
        "unit": "mV/m",
        "nominal_range": "-1.5 to +1.5 mV/m",
        "disturbed_range": "> 5.0 mV/m (Moderate Reconnection), > 15.0 mV/m (Extreme Storm Injection)",
        "formula": "E_y = -v_sw * B_z * 1e-3 [with v_sw in km/s and B_z in nT]",
        "instrument": "Derived from Plasma Flow Speed & Vector IMF",
        "description": "Dawn-to-dusk interplanetary electric field driving dayside magnetic reconnection, polar cap potential saturation, and equatorial ring current intensification.",
        "doi": "10.1126/science.189.4204.717"
    },
    "bow_shock_standoff": {
        "name": "Subsolar Bow Shock Standoff Distance",
        "symbol": "R_bs",
        "unit": "R_E (Earth Radii ~ 6,371 km)",
        "nominal_range": "13.0 - 15.5 R_E (~83,000 - 99,000 km)",
        "disturbed_range": "< 10.0 R_E (Intense CME Compression), < 7.5 R_E (Severe Superstorm Shock)",
        "formula": "R_bs = r_0,bs * [2 / (1 + cos(theta))]^alpha_bs",
        "instrument": "Multi-satellite bow shock crossings (Cluster, THEMIS, MMS, Geotail)",
        "description": "Subsolar distance to Earth's detached collisionless bow shock where supersonic solar wind is decelerated and heated into the subsonic magnetosheath.",
        "doi": "10.1016/S0964-2749(02)80214-7"
    },
    "magnetosheath_thickness": {
        "name": "Subsolar Magnetosheath Thickness",
        "symbol": "Delta R",
        "unit": "R_E (Earth Radii)",
        "nominal_range": "3.0 - 4.5 R_E (~19,000 - 29,000 km)",
        "disturbed_range": "< 2.0 R_E (Thin compressed sheath under high Mach numbers)",
        "formula": "Delta R = R_bs,0 - r_mp,0",
        "instrument": "Dual-boundary satellite transit differential",
        "description": "Spatial separation along the Sun-Earth line between the collisionless bow shock and the dayside magnetopause.",
        "doi": "10.1016/S0964-2749(02)80214-7"
    },
    "polar_cap_potential": {
        "name": "Cross Polar Cap Potential Drop",
        "symbol": "Phi_PC",
        "unit": "kV",
        "nominal_range": "25 - 60 kV (Quiet to Unsettled Convection)",
        "disturbed_range": "> 90 kV (Active Convection), > 140 kV (Severe Geomagnetic Storm)",
        "formula": "Phi_PC = 1e-4 * v^2 + 11.7 * B_T * sin^3(theta / 2) [kV]",
        "instrument": "SuperDARN HF Radars & DMSP SSIES Ion Drift Meters",
        "description": "Total transpolar electric potential difference established by solar wind-magnetosphere dynamo driving high-latitude F-region ionospheric plasma convection.",
        "doi": "10.1029/96JA03058"
    },
    "ae_index": {
        "name": "Auroral Electrojet Index (AE)",
        "symbol": "AE",
        "unit": "nT",
        "nominal_range": "< 150 nT (Quiet Auroral Oval)",
        "disturbed_range": "> 500 nT (Substorm Injection), > 1000 nT (Major Magnetospheric Substorm)",
        "formula": "AE ~ 0.048 * (dPhi/dt)^0.85 + 25 [nT]",
        "instrument": "Kyoto WDC Auroral Magnetometer Chain (12 High-Latitude Stations)",
        "description": "Global quantitative measure of auroral zone magnetic activity produced by enhanced eastward and westward ionospheric electrojet currents flowing at ~100 km altitude.",
        "doi": "10.1029/2006JA012015"
    },
    "sound_speed": {
        "name": "Ion Acoustic Sound Speed",
        "symbol": "C_s",
        "unit": "km/s",
        "nominal_range": "35 - 55 km/s (Typical Solar Wind T ~ 1e5 K)",
        "disturbed_range": "> 80 km/s (Hot Interplanetary CME Ejecta)",
        "formula": "C_s = sqrt(gamma * k_B * T / m_p) ~ 0.1174 * sqrt(T [K]) [km/s]",
        "instrument": "Thermal Proton Spectrometers (SWEPAM, PlasMag, CELIAS)",
        "description": "Phase speed of longitudinal electrostatic ion acoustic compressional waves propagating through thermal solar wind plasma.",
        "doi": "10.1086/146579"
    },
    "magnetosonic_speed": {
        "name": "Fast Magnetosonic Wave Speed",
        "symbol": "V_ms",
        "unit": "km/s",
        "nominal_range": "50 - 90 km/s",
        "disturbed_range": "> 150 km/s (Strong Field Compression / CME Sheath)",
        "formula": "V_ms = sqrt(V_A^2 + C_s^2) [km/s]",
        "instrument": "Derived from combined vector B and plasma ion moments",
        "description": "Propagation speed of fast compressional MHD waves perpendicular to the ambient magnetic field, setting the fundamental Mach threshold for planetary bow shock formation.",
        "doi": "10.1029/JA091iA01p00039"
    }
}
