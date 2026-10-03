"""
FastAPI REST API server for HELIOS-L1.
Bridges scientific backend engines with interactive frontend dashboard.
"""
from typing import Optional, Dict, Any, List
from pydantic import BaseModel
from fastapi import FastAPI, Query, HTTPException, Response, Body
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, FileResponse
import os
import io
import csv
import json
import math
import numpy as np
from datetime import datetime, timezone

from helios import __version__
from helios.config import (
    MISSIONS, STATIC_DIR, DATA_PROVIDERS,
    SCIENTIFIC_REFERENCES, PARAMETER_DEFINITIONS,
    get_system_settings, update_system_settings
)
from helios.core.downloader import DataDownloader, infer_cadence_seconds, regular_series
from helios.core.comparator import SatelliteComparator
from helios.core.orbital_mechanics import OrbitalMechanics
from helios.core.science import SpaceWeatherPhysics
from helios.core.exporter import DataExporter
from helios.core.aurora_model import AuroralModel
from helios.core.coronagraph import CoronagraphAnalyzer
from helios.core.parker_spiral import ParkerSpiralModel
from helios.core.report_generator import ScientificReportGenerator
from helios.core.importer import TelemetryImporter
from helios.core.ml_forecast import SpaceWeatherForecaster
from helios.core.solar_cycle import SolarCycleEngine
from helios.core.ionosphere import IonosphericModel
from helios.core.gic_model import GICHazardModel
from helios.core.spice_engine import get_spice_engine

app = FastAPI(
    title="HELIOS-L1 API",
    description="Heliophysical Exploration, Lagrange-1 Interplanetary Observation & Space-weather Suite",
    version=__version__
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

downloader = DataDownloader()
latest_custom_dataset: Optional[Dict[str, Any]] = None

def latest_valid_record(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Most recent record with both speed and Bz present (the newest row is often a partial gap)."""
    for rec in reversed(records or []):
        if rec.get("speed") is not None and rec.get("bz_gsm") is not None:
            return rec
    return records[-1] if records else {}


def kp_proxy_from_bz(bz: Optional[float]) -> float:
    """Crude Kp estimate from IMF Bz, used only when no observed Kp can be fetched."""
    if bz is None:
        return 3.0
    if bz < -15:
        return 8.5
    if bz < -10:
        return 7.0
    if bz < -5:
        return 5.0
    return 3.0


async def classify_current_conditions(latest: Dict[str, Any]) -> Dict[str, Any]:
    """
    NOAA G/R/S classification from observed indices (planetary Kp, GOES 0.1-0.8 nm X-rays,
    GOES >=10 MeV protons). Kp falls back to a Bz-based estimate, flagged as such; missing
    X-ray or proton data is reported as missing, never replaced by a default.
    """
    indices = await downloader.get_space_weather_indices()
    if indices.get("kp") is not None:
        kp, kp_source = indices["kp"], f"Observed planetary Kp (NOAA SWPC, {indices.get('kp_time')} UTC)"
    else:
        kp, kp_source = kp_proxy_from_bz(latest.get("bz_gsm")), "Estimated from IMF Bz (observed Kp unavailable)"
    cls = SpaceWeatherPhysics.classify_noaa_scales(
        kp=kp,
        bz_gsm=latest.get("bz_gsm"),
        xray_flux=indices.get("xray_flux_long"),
        proton_flux=indices.get("proton_flux_10mev")
    )
    cls["kp"] = kp
    cls["kp_source"] = kp_source
    cls["indices"] = indices
    return cls


class CMEKinematicsRequest(BaseModel):
    r1_rsun: float = 2.5
    r2_rsun: float = 6.0
    dt_minutes: float = 30.0
    launch_time_iso: Optional[str] = None

class CustomImportRequest(BaseModel):
    content: str
    mission_name: Optional[str] = "User Spacecraft / OMNI"

class SettingsUpdateRequest(BaseModel):
    processors: Optional[int] = None
    theme: Optional[str] = None
    font_size: Optional[str] = None
    timezone: Optional[str] = None

@app.get("/api/status")
async def get_status():
    settings = get_system_settings()
    return {
        "status": "online",
        "app_name": "HELIOS-L1",
        "full_name": "Heliophysical Exploration, Lagrange-1 Interplanetary Observation & Space-weather Suite",
        "version": __version__,
        "missions_count": len(MISSIONS),
        "system": settings
    }

@app.get("/api/settings")
async def get_settings():
    return get_system_settings()

@app.post("/api/settings")
async def save_settings(req: SettingsUpdateRequest):
    return update_system_settings(
        processors=req.processors,
        theme=req.theme,
        font_size=req.font_size,
        timezone=req.timezone
    )

@app.get("/api/missions")
async def get_missions():
    missions = list(MISSIONS.values())
    if latest_custom_dataset and latest_custom_dataset.get("records"):
        name = latest_custom_dataset.get("mission_name", "Custom Spacecraft")
        missions.append({
            "name": name,
            "full_name": f"{name} (User Telemetry Ingestion)",
            "agency": "User Custom Ingestion",
            "location": "User Defined Coordinates / OMNI",
            "orbit_distance_km": 1500000,
            "launch_year": datetime.now(timezone.utc).year,
            "status": f"Active ({latest_custom_dataset.get('total_records', 0)} records ingested)",
            "coordinate_system": "GSM / User Delimited",
            "cadence": "User Cadence",
            "data_portal_name": "Local HELIOS Ingestion Studio",
            "data_portal_url": "#tab-import",
            "data_license": "User Defined / Open Science",
            "license_badge": "User Telemetry",
            "doi": "N/A",
            "primary_citation": f"Local telemetry dataset ingested via HELIOS-L1 Custom Studio ({name}).",
            "instruments": [
                {"id": "USER_INST", "name": "Custom Spacecraft Sensor Suite", "measures": "In-situ plasma & magnetic field"}
            ],
            "primary_params": ["bz_gsm", "bt", "speed", "density"],
            "color": "#a855f7"
        })
    return missions

@app.get("/api/references")
async def get_scientific_references():
    """Returns comprehensive peer-reviewed citations, equations, data repositories, and licenses."""
    return {
        "status": "success",
        "total_references": len(SCIENTIFIC_REFERENCES),
        "references": SCIENTIFIC_REFERENCES,
        "scientific_references": SCIENTIFIC_REFERENCES,
        "data_providers": list(DATA_PROVIDERS.values()),
        "parameter_definitions": PARAMETER_DEFINITIONS
    }

@app.get("/api/providers")
async def get_data_providers():
    """Returns global space weather data observatories and their open science licenses."""
    return {
        "status": "success",
        "total_providers": len(DATA_PROVIDERS),
        "providers": list(DATA_PROVIDERS.values())
    }

@app.get("/api/parameters")
async def get_parameter_catalog():
    """Returns dictionary of all physical space weather parameters with formulas and units."""
    return {
        "status": "success",
        "total_parameters": len(PARAMETER_DEFINITIONS),
        "parameters": PARAMETER_DEFINITIONS
    }

@app.get("/api/parameters/{param_id}")
async def get_parameter_detail(param_id: str):
    p_id = param_id.lower()
    if p_id in PARAMETER_DEFINITIONS:
        return PARAMETER_DEFINITIONS[p_id]
    alias_map = {
        "v_sw": "speed",
        "vsw": "speed",
        "velocity": "speed",
        "bz": "bz_gsm",
        "b_z": "bz_gsm",
        "imf_bz": "bz_gsm",
        "b_t": "bt",
        "total_b": "bt",
        "np": "density",
        "n_p": "density",
        "proton_density": "density",
        "p_dyn": "pdyn",
        "pressure": "pdyn",
        "rmp": "standoff",
        "r_mp": "standoff",
        "magnetopause": "standoff",
        "akasofu": "epsilon",
        "poynting": "epsilon",
        "propagation_delay": "speed"
    }
    if p_id in alias_map:
        return PARAMETER_DEFINITIONS[alias_map[p_id]]
    raise HTTPException(status_code=404, detail=f"Parameter '{param_id}' not found in scientific handbook.")


@app.get("/api/telemetry/{mission_id}")
async def get_telemetry(mission_id: str, span_days: int = Query(1, ge=1, le=7)):
    mission_key = mission_id.upper()
    if mission_key not in MISSIONS:
        raise HTTPException(status_code=404, detail=f"Mission '{mission_id}' not recognized.")
    
    bundle = await downloader.get_telemetry_bundle(mission_key, span_days=span_days)
    data = bundle["records"]

    latest = latest_valid_record(data)
    classification = await classify_current_conditions(latest)

    shocks = SpaceWeatherPhysics.detect_interplanetary_shocks(data)

    mission_info = dict(MISSIONS[mission_key])
    mission_info["id"] = mission_key

    return {
        "mission": mission_info,
        "provenance": bundle["provenance"],
        "data_points": len(data),
        "latest": latest,
        "classification": classification,
        "detected_shocks": shocks,
        "records": data
    }

@app.get("/api/compare")
async def compare_missions(
    mission_a: str = Query("DSCOVR"),
    mission_b: str = Query("ADITYA_L1"),
    parameter: str = Query("bz_gsm"),
    span_days: int = Query(1, ge=1, le=7)
):
    key_a = mission_a.upper()
    key_b = mission_b.upper()

    if key_a == "CUSTOM":
        if not latest_custom_dataset or not latest_custom_dataset.get("records"):
            raise HTTPException(status_code=400, detail="No custom dataset imported for comparison.")
        data_a = latest_custom_dataset["records"]
        name_a = latest_custom_dataset.get("mission_name", "Custom Spacecraft")
    else:
        if key_a not in MISSIONS:
            raise HTTPException(status_code=400, detail=f"Invalid mission ID '{key_a}' for comparison.")
        data_a = await downloader.get_satellite_telemetry(key_a, span_days=span_days)
        name_a = MISSIONS[key_a]["name"]

    if key_b == "CUSTOM":
        if not latest_custom_dataset or not latest_custom_dataset.get("records"):
            raise HTTPException(status_code=400, detail="No custom dataset imported for comparison.")
        data_b = latest_custom_dataset["records"]
        name_b = latest_custom_dataset.get("mission_name", "Custom Spacecraft")
    else:
        if key_b not in MISSIONS:
            raise HTTPException(status_code=400, detail=f"Invalid mission ID '{key_b}' for comparison.")
        data_b = await downloader.get_satellite_telemetry(key_b, span_days=span_days)
        name_b = MISSIONS[key_b]["name"]

    comparison = SatelliteComparator.compare_satellites(
        telemetry_a=data_a,
        telemetry_b=data_b,
        mission_a_name=name_a,
        mission_b_name=name_b,
        parameter=parameter
    )
    return comparison

@app.get("/api/compare/matrix")
async def get_comparison_matrix(
    parameter: str = Query("bz_gsm"),
    span_days: int = Query(1, ge=1, le=7)
):
    fleet_keys = ["DSCOVR", "ACE", "ADITYA_L1", "WIND", "SOHO"]
    telemetry_map = {}
    for k in fleet_keys:
        telemetry_map[k] = await downloader.get_satellite_telemetry(k, span_days=span_days)
    return SatelliteComparator.compute_fleet_matrix(telemetry_map, parameter=parameter)

@app.get("/api/forecast/ml")
async def get_ml_forecast(mission_id: str = Query("DSCOVR")):
    mission_key = mission_id.upper()
    if mission_key not in MISSIONS:
        mission_key = "DSCOVR"
    data = await downloader.get_satellite_telemetry(mission_key, span_days=1)
    return SpaceWeatherForecaster.forecast_geomagnetic_storm(data)

@app.get("/api/events")
async def get_events():
    return [
        {"id": "may_2024_g5", "title": "May 2024 Extreme G5 Superstorm (AR 3664)", "severity": "Extreme G5 (Kp=9)", "icon": "fa-bolt", "badge_color": "#dc2626"},
        {"id": "halloween_2003", "title": "Halloween 2003 Storms (X17+ Flare)", "severity": "Extreme G5 (Kp=9)", "icon": "fa-radiation", "badge_color": "#dc2626"},
        {"id": "bastille_2000", "title": "Bastille Day 2000 Superstorm (X5.7)", "severity": "Extreme G5 / S5 (Kp=9)", "icon": "fa-fire-flame-curved", "badge_color": "#ea580c"},
        {"id": "quebec_1989", "title": "Hydro-Québec Blackout (March 1989)", "severity": "Extreme G5 (Dst -589)", "icon": "fa-plug-circle-xmark", "badge_color": "#e11d48"},
        {"id": "carrington_1859", "title": "Carrington Event (September 1859)", "severity": "Superstorm (Dst <-850)", "icon": "fa-meteor", "badge_color": "#9333ea"},
        {"id": "st_patricks_2015", "title": "St. Patrick's Day Storm (March 2015)", "severity": "Severe G4 (Kp=8)", "icon": "fa-cloud-bolt", "badge_color": "#f59e0b"},
        {"id": "quiet_baseline", "title": "Quiet Sun Solar Wind Baseline", "severity": "Quiet G0 (Kp=1)", "icon": "fa-sun", "badge_color": "#10b981"}
    ]

@app.get("/api/event/{event_id}")
@app.get("/api/events/{event_id}")
async def get_event(event_id: str):
    return await downloader.get_historical_event(event_id)

@app.get("/api/orbits")
async def get_orbits(epoch: Optional[str] = Query(None, description="UTC ISO epoch for spacecraft position calculations")):
    lagrange = OrbitalMechanics.get_lagrange_points()
    orbits = OrbitalMechanics.get_satellite_orbits(epoch_utc=epoch)
    return {
        "lagrange_points": lagrange,
        "orbits": orbits
    }

@app.get("/api/ephemeris/spice")
async def get_spice_ephemeris(
    satellites: Optional[str] = Query(None, description="Comma-separated spacecraft IDs (e.g. PARKER_SOLAR_PROBE,ADITYA_L1,SOLAR_ORBITER)"),
    epoch: Optional[str] = Query(None, description="Epoch timestamp in UTC ISO format (defaults to current time)"),
    frame: str = Query("ECLIPJ2000", description="Coordinate reference frame: ECLIPJ2000 or GSE")
):
    """
    Computes rigorous state vectors [x, y, z, vx, vy, vz] using NASA JPL NAIF SPICE (CSPICE_N0067).
    Returns verified positions (km, AU), orbital velocities (km/s, AU/day),
    heliocentric distances, Earth-relative distances, true anomalies, and orbital elements.
    """
    engine = get_spice_engine()
    sc_list = [s.strip().upper() for s in satellites.split(",")] if satellites else None
    return engine.get_fleet_states(spacecraft_ids=sc_list, epoch_utc=epoch, frame=frame)

@app.get("/api/ephemeris/spice/trajectory")
async def get_spice_trajectory(
    satellite: str = Query("PARKER_SOLAR_PROBE", description="Spacecraft ID (e.g. PARKER_SOLAR_PROBE, SOLAR_ORBITER, ADITYA_L1)"),
    points: int = Query(120, ge=10, le=500, description="Number of trajectory track points"),
    epoch: Optional[str] = Query(None, description="Reference epoch in UTC ISO format")
):
    """
    Generates full 3D orbital path track points across an entire orbital period using SPICE.
    """
    engine = get_spice_engine()
    trajectory = engine.get_orbit_trajectory(spacecraft_id=satellite, num_points=points, epoch_utc=epoch)
    return {
        "satellite": satellite,
        "points_count": len(trajectory),
        "trajectory": trajectory
    }

@app.get("/api/ephemeris/spice/status")
async def get_spice_status():
    """
    Returns NASA JPL NAIF SPICE kernel repository status, loaded kernels, and planetary constants.
    """
    engine = get_spice_engine()
    return {
        "spice_available": engine.is_spice_available,
        "toolkit_version": engine.toolkit_version,
        "kernel_count": len(engine.loaded_kernels),
        "loaded_kernels": [os.path.basename(k) for k in engine.loaded_kernels],
        "sun_gm": engine.get_body_gm("10"),
        "earth_gm": engine.get_body_gm("399"),
        "earth_radii_km": [6378.1366, 6378.1366, 6356.7519]
    }

@app.get("/api/aurora")
async def get_aurora(kp: Optional[float] = None, bz_gsm: Optional[float] = None):
    data = await downloader.get_satellite_telemetry("DSCOVR", span_days=1)
    latest_rec = latest_valid_record(data)

    if bz_gsm is None:
        bz_val = latest_rec.get("bz_gsm")
        bz_val = float(bz_val) if bz_val is not None else -3.0
    else:
        bz_val = float(bz_gsm)

    kp_source = "user input"
    if kp is None:
        indices = await downloader.get_space_weather_indices()
        if indices.get("kp") is not None:
            kp_val, kp_source = float(indices["kp"]), "observed planetary Kp (NOAA SWPC)"
        else:
            speed_val = latest_rec.get("speed")
            speed_val = float(speed_val) if speed_val is not None else 420.0
            kp_est = max(0.5, min(9.0, 2.0 + max(0.0, (speed_val - 400.0) / 80.0) + max(0.0, -bz_val) * 0.35))
            kp_val, kp_source = round(kp_est, 1), "estimated from solar wind speed and Bz"
    else:
        kp_val = float(kp)

    boundaries = AuroralModel.calculate_auroral_boundaries(kp_val, bz_val)
    oval_polygon = AuroralModel.generate_auroral_oval_coordinates(kp_val, bz_val)
    dst_sim = AuroralModel.simulate_dst_evolution(data)
    return {
        "kp": kp_val,
        "kp_source": kp_source,
        "bz_gsm": bz_val,
        "boundaries": boundaries,
        "oval_polygon": oval_polygon,
        "dst_evolution": dst_sim
    }

@app.get("/api/magnetosphere/boundaries")
async def get_magnetospheric_boundaries(
    dynamic_pressure: float = Query(2.0, ge=0.01, le=120.0, description="Solar wind dynamic pressure P_dyn (nPa)"),
    bz_gsm: float = Query(0.0, ge=-80.0, le=80.0, description="Interplanetary Magnetic Field Bz component (nT)"),
    mach_number: float = Query(8.0, ge=1.2, le=30.0, description="Solar wind Alfvén / magnetosonic Mach number"),
    model: str = Query("chao", description="Magnetospheric boundary model: 'chao' (Chao et al., 2002) or 'shue' (Shue et al., 1997, 1998)")
):
    """
    Computes 2D/3D magnetopause and bow shock standoff distances, flaring parameters,
    and GSE spatial coordinate profiles using Chao et al. (2002) or Shue et al. (1997).
    """
    return SpaceWeatherPhysics.calculate_magnetospheric_boundaries(
        dynamic_pressure_npa=dynamic_pressure,
        bz_gsm_nt=bz_gsm,
        mach_number=mach_number,
        model=model
    )

@app.get("/api/geospace/coupling")
async def get_geospace_coupling(
    speed_kms: float = Query(450.0, ge=100.0, le=3000.0, description="Solar wind speed (km/s)"),
    density_cm3: float = Query(5.0, ge=0.01, le=250.0, description="Proton density (cm^-3)"),
    b_total_nt: float = Query(6.0, ge=0.01, le=150.0, description="Interplanetary Magnetic Field magnitude B_T (nT)"),
    by_gsm_nt: float = Query(0.0, ge=-100.0, le=100.0, description="IMF By (GSM) component (nT)"),
    bz_gsm_nt: float = Query(-3.0, ge=-100.0, le=100.0, description="IMF Bz (GSM) component (nT)"),
    temp_k: float = Query(100000.0, ge=1000.0, le=5000000.0, description="Proton thermal temperature (K)")
):
    """
    Computes real-time Geospace coupling parameters including:
    - Solar wind wave speeds (Alfvén, Sound, Fast Magnetosonic)
    - Mach numbers (Alfvénic M_A, Magnetosonic M_ms)
    - Cross-polar cap potential Phi_PC drop (Boyle et al. 1997)
    - Auroral Electrojet index AE proxy (Newell et al. 2007)
    - Perreault-Akasofu energy coupling rate Epsilon (GW)
    - Newell universal coupling function dPhi/dt (Wb/s)
    - Convective electric field E_y (mV/m)
    - Dynamic pressure P_dyn (nPa)
    """
    mach = SpaceWeatherPhysics.mach_numbers(
        speed_kms=speed_kms,
        b_total_nt=b_total_nt,
        density_cm3=density_cm3,
        temp_k=temp_k
    )
    pdyn = SpaceWeatherPhysics.dynamic_pressure(density_cm3=density_cm3, speed_kms=speed_kms)
    phi_pc = SpaceWeatherPhysics.polar_cap_potential(speed_kms=speed_kms, by_gsm_nt=by_gsm_nt, bz_gsm_nt=bz_gsm_nt)
    ae = SpaceWeatherPhysics.auroral_electrojet_ae(speed_kms=speed_kms, by_gsm_nt=by_gsm_nt, bz_gsm_nt=bz_gsm_nt)
    akasofu = SpaceWeatherPhysics.akasofu_epsilon(speed_kms=speed_kms, b_total_nt=b_total_nt, by_gsm_nt=by_gsm_nt, bz_gsm_nt=bz_gsm_nt)
    newell = SpaceWeatherPhysics.newell_coupling(speed_kms=speed_kms, by_gsm_nt=by_gsm_nt, bz_gsm_nt=bz_gsm_nt)
    ey = SpaceWeatherPhysics.convective_electric_field(speed_kms=speed_kms, bz_gsm_nt=bz_gsm_nt)
    clock = SpaceWeatherPhysics.clock_angle(by_gsm_nt=by_gsm_nt, bz_gsm_nt=bz_gsm_nt)

    return {
        "status": "success",
        "inputs": {
            "speed_kms": speed_kms,
            "density_cm3": density_cm3,
            "b_total_nt": b_total_nt,
            "by_gsm_nt": by_gsm_nt,
            "bz_gsm_nt": bz_gsm_nt,
            "temp_k": temp_k
        },
        "dynamic_pressure_npa": round(pdyn, 2),
        "clock_angle_deg": round(float(math.degrees(clock)), 1),
        "convective_efield_mvm": ey,
        "wave_speeds": {
            "alfven_speed_kms": mach["alfven_speed_kms"],
            "sound_speed_kms": mach["sound_speed_kms"],
            "magnetosonic_speed_kms": mach["magnetosonic_speed_kms"]
        },
        "mach_numbers": {
            "alfven_mach": mach["alfven_mach"],
            "magnetosonic_mach": mach["magnetosonic_mach"]
        },
        "polar_cap_potential": phi_pc,
        "auroral_electrojet": ae,
        "akasofu_epsilon_gw": round(akasofu, 2),
        "newell_coupling_dphi": round(newell, 1)
    }

@app.get("/api/coronagraph/feeds")
async def get_coronagraph_feeds():
    return CoronagraphAnalyzer.get_coronagraph_feeds()

@app.post("/api/coronagraph/kinematics")
async def calculate_cme_kinematics(req: CMEKinematicsRequest):
    return CoronagraphAnalyzer.calculate_cme_kinematics(
        r1_rsun=req.r1_rsun,
        r2_rsun=req.r2_rsun,
        dt_minutes=req.dt_minutes,
        launch_time_iso=req.launch_time_iso
    )

@app.get("/api/parker_spiral")
@app.get("/api/parker/spiral")
async def get_parker_spiral(speed_kms: float = 450.0):
    pitch = ParkerSpiralModel.spiral_pitch_angle(speed_kms)
    footpoint = ParkerSpiralModel.magnetic_footpoint_longitude(speed_kms)
    streamlines = ParkerSpiralModel.generate_parker_spiral_lines(speed_kms)
    return {
        "speed_kms": speed_kms,
        "spiral_pitch_angle_deg": pitch,
        "pitch_angle_1au_deg": pitch,
        "connected_footpoint_deg_west": footpoint,
        "earth_connected_footpoint_deg_w": footpoint,
        "streamlines": streamlines
    }

@app.post("/api/custom/import")
async def import_custom_data(req: CustomImportRequest):
    global latest_custom_dataset
    res = TelemetryImporter.parse_csv_or_text(req.content, req.mission_name)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    latest_custom_dataset = res
    return res

@app.get("/api/custom/presets")
async def get_custom_presets():
    """Returns catalog of historical superstorms and test datasets."""
    return {
        "status": "success",
        "presets": TelemetryImporter.get_presets_list()
    }

@app.get("/api/custom/presets/{preset_id}")
async def get_custom_preset(preset_id: str):
    """Returns details and CSV payload for a specific preset."""
    preset = TelemetryImporter.get_preset(preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail=f"Preset '{preset_id}' not found.")
    return {
        "status": "success",
        "preset": preset
    }

@app.get("/api/custom/latest")
async def get_latest_custom():
    """Returns currently loaded custom ingested telemetry, or 404 if none."""
    if not latest_custom_dataset:
        raise HTTPException(status_code=404, detail="No custom telemetry dataset has been ingested yet.")
    return latest_custom_dataset

@app.get("/api/custom/export/{export_format}")
async def export_custom_telemetry(export_format: str):
    """Exports currently ingested custom dataset as CSV or JSON."""
    if not latest_custom_dataset or "records" not in latest_custom_dataset:
        raise HTTPException(status_code=404, detail="No custom telemetry available to export.")
    records = latest_custom_dataset["records"]
    mission_slug = latest_custom_dataset.get("mission_name", "custom").lower().replace(" ", "_")

    if export_format.lower() == "csv":
        output = io.StringIO()
        if records:
            writer = csv.DictWriter(output, fieldnames=list(records[0].keys()))
            writer.writeheader()
            writer.writerows(records)
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=helios_{mission_slug}_telemetry.csv"}
        )
    elif export_format.lower() == "json":
        return Response(
            content=json.dumps(latest_custom_dataset, indent=2),
            media_type="application/json",
            headers={"Content-Disposition": f"attachment; filename=helios_{mission_slug}_telemetry.json"}
        )
    else:
        raise HTTPException(status_code=400, detail="Invalid export format. Choose 'csv' or 'json'.")

@app.get("/api/solar_cycle")
async def get_solar_cycle(year: Optional[float] = None):
    cur_year = year if year is not None else (datetime.now(timezone.utc).year + datetime.now(timezone.utc).timetuple().tm_yday / 365.25)
    return SolarCycleEngine.calculate_cycle_25_progression(current_year_float=cur_year)

@app.get("/api/ionosphere/absorption")
async def get_ionospheric_absorption(
    xray_flux: float = Query(2.5e-5, description="Soft X-ray flux (Watts/m^2)"),
    zenith_angle: float = Query(30.0, ge=0.0, le=90.0, description="Solar zenith angle (degrees)")
):
    return IonosphericModel.calculate_drap_absorption(xray_flux_watts_m2=xray_flux, zenith_angle_deg=zenith_angle)

@app.get("/api/gic/hazard")
async def get_gic_hazard(
    db_dt: float = Query(120.0, description="Rate of magnetic change dB/dt (nT/min)"),
    geology: str = Query("precambrian_shield", description="Geological conductivity profile")
):
    return GICHazardModel.calculate_geoelectric_field(db_dt_nt_per_min=db_dt, geology_type=geology)


@app.get("/api/report/html")
async def get_html_report(mission_id: str = "DSCOVR", download: bool = False):
    mission_key = mission_id.upper()
    if mission_key not in MISSIONS:
        mission_key = "DSCOVR"
    data = await downloader.get_satellite_telemetry(mission_key, span_days=1)
    latest = latest_valid_record(data)
    classification = await classify_current_conditions(latest)
    shocks = SpaceWeatherPhysics.detect_interplanetary_shocks(data)
    auroral_data = AuroralModel.calculate_auroral_boundaries(classification["kp"], latest.get("bz_gsm") or 0.0)

    html = ScientificReportGenerator.generate_html_bulletin(
        mission_name=MISSIONS[mission_key]["name"],
        telemetry=data,
        classification=classification,
        shocks=shocks,
        auroral_data=auroral_data
    )
    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="HELIOS-L1-{mission_key}-Bulletin.html"'
    return Response(content=html, media_type="text/html", headers=headers)

@app.get("/api/report/markdown")
async def get_markdown_report(mission_id: str = "DSCOVR", download: bool = False):
    mission_key = mission_id.upper()
    if mission_key not in MISSIONS:
        mission_key = "DSCOVR"
    data = await downloader.get_satellite_telemetry(mission_key, span_days=1)
    latest = latest_valid_record(data)
    classification = await classify_current_conditions(latest)
    shocks = SpaceWeatherPhysics.detect_interplanetary_shocks(data)
    auroral_data = AuroralModel.calculate_auroral_boundaries(classification["kp"], latest.get("bz_gsm") or 0.0)

    md = ScientificReportGenerator.generate_markdown_executive_summary(
        mission_name=MISSIONS[mission_key]["name"],
        telemetry=data,
        classification=classification,
        shocks=shocks,
        auroral_data=auroral_data
    )
    headers = {}
    if download:
        headers["Content-Disposition"] = f'attachment; filename="HELIOS-L1-{mission_key}-Executive-Summary.md"'
    return Response(content=md, media_type="text/markdown; charset=utf-8", headers=headers)

@app.get("/api/spectrum")
async def get_spectrum(mission_id: str = "DSCOVR", parameter: str = "bz_gsm", span_days: int = Query(1, ge=1, le=7)):
    mission_key = mission_id.upper()
    if mission_key not in MISSIONS:
        mission_key = "DSCOVR"
    data = await downloader.get_satellite_telemetry(mission_key, span_days=span_days)
    # Keep gaps in place (None) so the series stays evenly sampled; the sample interval
    # comes from the time stamps (1 min live, 5 min for 7-day averages and the offline model).
    dt_seconds = infer_cadence_seconds(data, default=60.0)
    values = regular_series(data, parameter, dt_seconds)
    speeds = [float(d.get("speed")) for d in data if d.get("speed") is not None and isinstance(d.get("speed"), (int, float))]
    v_mean = float(np.mean(speeds)) if speeds else 450.0
    res = SpaceWeatherPhysics.power_spectral_density(values, dt_seconds=dt_seconds, v_sw_kms=v_mean)
    res["mission_id"] = mission_key
    res["parameter"] = parameter
    res["span_days"] = span_days
    return res

@app.get("/api/export/csv")
async def export_csv(mission_id: str = "DSCOVR", span_days: int = Query(1, ge=1, le=7)):
    if mission_id.upper() not in MISSIONS:
        raise HTTPException(status_code=404, detail=f"Mission '{mission_id}' not recognized.")
    data = await downloader.get_satellite_telemetry(mission_id.upper(), span_days=span_days)
    csv_str = DataExporter.to_csv(data)
    return Response(content=csv_str, media_type="text/csv", headers={
        "Content-Disposition": f"attachment; filename=HELIOS_{mission_id}_telemetry.csv"
    })

@app.get("/api/export/plot")
async def export_plot(mission_id: str = "DSCOVR", span_days: int = Query(1, ge=1, le=7)):
    mission_key = mission_id.upper()
    if mission_key not in MISSIONS:
        raise HTTPException(status_code=404, detail=f"Mission '{mission_id}' not recognized.")
    data = await downloader.get_satellite_telemetry(mission_key, span_days=span_days)
    name = MISSIONS.get(mission_key, {}).get("name", mission_id)
    png_bytes = DataExporter.generate_overview_chart(data, name)
    return Response(content=png_bytes, media_type="image/png", headers={
        "Content-Disposition": f"attachment; filename=HELIOS_{mission_id}_chart.png"
    })


# Mount frontend static directory if exists
def get_resolved_static_dir():
    if STATIC_DIR.exists() and (STATIC_DIR / "index.html").exists():
        return STATIC_DIR
    # Try alternate search paths
    from helios.config import BASE_DIR
    candidates = [
        BASE_DIR / "gui" / "static",
        BASE_DIR.parent / "helios" / "gui" / "static",
        BASE_DIR.parent / "_internal" / "helios" / "gui" / "static",
    ]
    for c in candidates:
        if c.exists() and (c / "index.html").exists():
            return c
    return STATIC_DIR

resolved_static = get_resolved_static_dir()
if resolved_static.exists():
    app.mount("/static", StaticFiles(directory=str(resolved_static)), name="static")

@app.get("/")
@app.get("/index.html")
async def serve_index():
    cur_static = get_resolved_static_dir()
    index_file = cur_static / "index.html"
    if index_file.exists():
        return FileResponse(str(index_file))
    return Response(
        content="<html><body style='background:#060a12;color:#38bdf8;font-family:sans-serif;padding:40px;'>"
                "<h2>HELIOS-L1 Science Engine Online</h2>"
                "<p>API is active. Static GUI assets directory not located.</p></body></html>",
        media_type="text/html"
    )
