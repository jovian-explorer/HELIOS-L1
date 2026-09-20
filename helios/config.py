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
    }
}
