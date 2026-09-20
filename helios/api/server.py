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
from datetime import datetime, timezone

from helios.config import (
    MISSIONS, STATIC_DIR, DATA_PROVIDERS,
    SCIENTIFIC_REFERENCES, PARAMETER_DEFINITIONS
)
from helios.core.downloader import DataDownloader
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

app = FastAPI(
    title="HELIOS-L1 API",
    description="Heliophysical Exploration, Lagrange-1 Interplanetary Observation & Space-weather Suite",
    version="1.2.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

downloader = DataDownloader()

class CMEKinematicsRequest(BaseModel):
    r1_rsun: float = 2.5
    r2_rsun: float = 6.0
    dt_minutes: float = 30.0
    launch_time_iso: Optional[str] = None

class CustomImportRequest(BaseModel):
    content: str
    mission_name: Optional[str] = "User Spacecraft / OMNI"

@app.get("/api/status")
async def get_status():
    return {
        "status": "online",
        "app_name": "HELIOS-L1",
        "full_name": "Heliophysical Exploration, Lagrange-1 Interplanetary Observation & Space-weather Suite",
        "version": "1.2.0",
        "missions_count": len(MISSIONS)
    }

@app.get("/api/missions")
async def get_missions():
    return list(MISSIONS.values())

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
    
    data = await downloader.get_satellite_telemetry(mission_key, span_days=span_days)
    
    latest = data[-1] if data else {}
    kp_proxy = 3.0
    if latest.get("bz_gsm", 0) < -15:
        kp_proxy = 8.5
    elif latest.get("bz_gsm", 0) < -10:
        kp_proxy = 7.0
    elif latest.get("bz_gsm", 0) < -5:
        kp_proxy = 5.0

    classification = SpaceWeatherPhysics.classify_noaa_scales(
        kp=kp_proxy,
        bz_gsm=latest.get("bz_gsm"),
        xray_flux=latest.get("xray_flux_long", 1.5e-6)
    )

    shocks = SpaceWeatherPhysics.detect_interplanetary_shocks(data)

    return {
        "mission": MISSIONS[mission_key],
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
    if key_a not in MISSIONS or key_b not in MISSIONS:
        raise HTTPException(status_code=400, detail="Invalid mission ID for comparison.")

    data_a = await downloader.get_satellite_telemetry(key_a, span_days=span_days)
    data_b = await downloader.get_satellite_telemetry(key_b, span_days=span_days)

    name_a = MISSIONS[key_a]["name"]
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
        {"id": "may_2024_g5", "title": "May 10-12, 2024 Extreme G5 Solar Superstorm", "severity": "Extreme (G5, Kp=9)", "icon": "fa-bolt"},
        {"id": "st_patricks_2015", "title": "St. Patrick's Day 2015 Storm", "severity": "Severe (G4, Kp=8)", "icon": "fa-cloud-bolt"},
        {"id": "halloween_2003", "title": "Halloween 2003 Solar Storms (X17+ Flare)", "severity": "Extreme (G5, Kp=9)", "icon": "fa-radiation"},
        {"id": "quiet_baseline", "title": "Quiet Sun Solar Wind Baseline", "severity": "Quiet (G0, Kp=1)", "icon": "fa-sun"}
    ]

@app.get("/api/event/{event_id}")
async def get_event(event_id: str):
    return await downloader.get_historical_event(event_id)

@app.get("/api/orbits")
async def get_orbits():
    lagrange = OrbitalMechanics.get_lagrange_points()
    orbits = OrbitalMechanics.get_satellite_orbits()
    return {
        "lagrange_points": lagrange,
        "orbits": orbits
    }

@app.get("/api/aurora")
async def get_aurora(kp: float = 3.0, bz_gsm: float = -3.0):
    boundaries = AuroralModel.calculate_auroral_boundaries(kp, bz_gsm)
    oval_polygon = AuroralModel.generate_auroral_oval_coordinates(kp, bz_gsm)
    data = await downloader.get_satellite_telemetry("DSCOVR", span_days=1)
    dst_sim = AuroralModel.simulate_dst_evolution(data)
    return {
        "boundaries": boundaries,
        "oval_polygon": oval_polygon,
        "dst_evolution": dst_sim
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
async def get_parker_spiral(speed_kms: float = 450.0):
    pitch = ParkerSpiralModel.spiral_pitch_angle(speed_kms)
    footpoint = ParkerSpiralModel.magnetic_footpoint_longitude(speed_kms)
    streamlines = ParkerSpiralModel.generate_parker_spiral_lines(speed_kms)
    return {
        "speed_kms": speed_kms,
        "spiral_pitch_angle_deg": pitch,
        "connected_footpoint_deg_west": footpoint,
        "streamlines": streamlines
    }

@app.post("/api/custom/import")
async def import_custom_data(req: CustomImportRequest):
    res = TelemetryImporter.parse_csv_or_text(req.content, req.mission_name)
    if "error" in res:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

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
async def get_html_report(mission_id: str = "DSCOVR"):
    mission_key = mission_id.upper()
    if mission_key not in MISSIONS:
        mission_key = "DSCOVR"
    data = await downloader.get_satellite_telemetry(mission_key, span_days=1)
    latest = data[-1] if data else {}
    kp_proxy = 3.0
    if latest.get("bz_gsm", 0) < -15:
        kp_proxy = 8.5
    elif latest.get("bz_gsm", 0) < -10:
        kp_proxy = 7.0
    elif latest.get("bz_gsm", 0) < -5:
        kp_proxy = 5.0
    classification = SpaceWeatherPhysics.classify_noaa_scales(
        kp=kp_proxy,
        bz_gsm=latest.get("bz_gsm"),
        xray_flux=latest.get("xray_flux_long", 1.5e-6)
    )
    shocks = SpaceWeatherPhysics.detect_interplanetary_shocks(data)
    auroral_data = AuroralModel.calculate_auroral_boundaries(kp_proxy, latest.get("bz_gsm", 0))

    html = ScientificReportGenerator.generate_html_bulletin(
        mission_name=MISSIONS[mission_key]["name"],
        telemetry=data,
        classification=classification,
        shocks=shocks,
        auroral_data=auroral_data
    )
    return Response(content=html, media_type="text/html")

@app.get("/api/spectrum")
async def get_spectrum(mission_id: str = "DSCOVR", parameter: str = "bz_gsm"):
    mission_key = mission_id.upper()
    if mission_key not in MISSIONS:
        mission_key = "DSCOVR"
    data = await downloader.get_satellite_telemetry(mission_key, span_days=1)
    values = [d.get(parameter) for d in data if d.get(parameter) is not None]
    return SpaceWeatherPhysics.power_spectral_density(values)

@app.get("/api/export/csv")
async def export_csv(mission_id: str = "DSCOVR", span_days: int = 1):
    data = await downloader.get_satellite_telemetry(mission_id.upper(), span_days=span_days)
    csv_str = DataExporter.to_csv(data)
    return Response(content=csv_str, media_type="text/csv", headers={
        "Content-Disposition": f"attachment; filename=HELIOS_{mission_id}_telemetry.csv"
    })

@app.get("/api/export/plot")
async def export_plot(mission_id: str = "DSCOVR", span_days: int = 1):
    mission_key = mission_id.upper()
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
