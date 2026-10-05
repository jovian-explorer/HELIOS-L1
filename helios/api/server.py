"""
FastAPI REST API server for HELIOS-L1.
Bridges scientific backend engines with interactive frontend dashboard.
"""
from typing import Optional, Dict, Any, List, Tuple
from pydantic import BaseModel
from fastapi import FastAPI, Query, HTTPException, Response
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
import logging
import os
import io
import asyncio
import csv
import json
import math
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta

from helios import __version__
from helios.api.guard import LocalRequestGuard
from helios.config import (
    MISSIONS, STATIC_DIR, DATA_PROVIDERS,
    SCIENTIFIC_REFERENCES, PARAMETER_DEFINITIONS,
    get_system_settings, update_system_settings, run_in_workers, NOAA_SWPC_ENDPOINTS
)
from helios.core.downloader import DataDownloader, infer_cadence_seconds, regular_series
from helios.core.archive import ARCHIVE_SOURCES, HAPI_SERVER
from helios.core.event_analysis import (EVENT_SOURCES, MAX_EVENT_HOURS, SEA_PARAMETERS, SHOCK_METHODS,
                                        analyze_shock, superposed_epoch,
                                        fit_flux_rope, minimum_variance, position_at, timing_comparison)
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

@app.exception_handler(Exception)
async def unexpected_error(request, exc: Exception):
    """
    Unexpected failures answer JSON like every other error, naming the endpoint and the
    exception (the plain-text 'Internal Server Error' page made the interface fail with a
    JSON parse error instead of a message). The traceback goes to the log file.
    """
    logging.getLogger("helios.api").exception("Unhandled error in %s", request.url.path)
    return JSONResponse(status_code=500, content={
        "detail": f"Internal error in {request.url.path}: {type(exc).__name__}: {exc}"[:500]})

# No CORS middleware: the interface is served by this server (same origin). The former
# allow_origins=["*"] with credentials let any web page open in the browser read every
# answer and send JSON POSTs (settings, imports) after an approved preflight.
# The guard rejects cross-site and DNS-rebinding requests before routing (helios.api.guard).
app.add_middleware(LocalRequestGuard)

downloader = DataDownloader()
latest_custom_dataset: Optional[Dict[str, Any]] = None

def latest_valid_record(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Most recent record with both speed and Bz present (the newest row is often a partial gap)."""
    for rec in reversed(records or []):
        if rec.get("speed") is not None and rec.get("bz_gsm") is not None:
            return rec
    return records[-1] if records else {}


def propagate_to_earth(records: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Copies of L1 records with time stamps moved forward by their L1-to-Earth travel time
    (l1_travel_time_min), sorted by the new time. Records without a travel time (no speed,
    or OMNI data that are already shifted) keep their time stamp.
    """
    out = []
    for r in records:
        lag = r.get("l1_travel_time_min")
        if lag is None:
            out.append(r)
            continue
        try:
            t = datetime.fromisoformat(str(r["time_tag"]).replace("T", " ")[:19]) + timedelta(minutes=float(lag))
        except (KeyError, TypeError, ValueError):
            out.append(r)
            continue
        out.append(dict(r, time_tag=t.strftime("%Y-%m-%d %H:%M:%S")))
    out.sort(key=lambda r: str(r.get("time_tag", "")))
    return out


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
    ambient_wind_kms: float = 420.0
    gamma_drag: float = 1.0e-7

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
    try:
        return update_system_settings(
            processors=req.processors,
            theme=req.theme,
            font_size=req.font_size,
            timezone=req.timezone
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

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

ARCHIVE_MAX_DAYS = 31


def _parse_utc(value: str, name: str) -> datetime:
    """ISO 8601 date or date-time; naive values are UTC, offsets are converted to UTC."""
    try:
        t = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        raise HTTPException(status_code=422, detail=f"'{name}' must be an ISO 8601 UTC time, e.g. 2024-05-10T12:00.")
    return t.replace(tzinfo=timezone.utc) if t.tzinfo is None else t.astimezone(timezone.utc)


@app.get("/api/archive")
async def get_archive_catalog():
    """Missions and CDAWeb datasets available for archive retrieval (preferred dataset first)."""
    return {
        "server": HAPI_SERVER,
        "max_days": ARCHIVE_MAX_DAYS,
        "missions": {
            key: [[{"id": d["id"], "level": d["level"], "label": d["label"]} for d in group]
                  for group in src["groups"]]
            for key, src in ARCHIVE_SOURCES.items()
        },
    }


@app.get("/api/archive/{mission_id}")
async def get_archive(
    mission_id: str,
    start: str = Query(..., description="UTC start, ISO 8601 (e.g. 2024-05-10T00:00)"),
    end: str = Query(..., description="UTC end (exclusive), ISO 8601"),
    cadence_minutes: int = Query(1, ge=1, le=60, description="1 = 1-minute means; larger values are block averages"),
    format: str = Query("json", pattern="^(json|csv)$")
):
    """Measured solar wind for any interval from the NASA CDAWeb archive (WIND, ACE, DSCOVR, OMNI)."""
    key = mission_id.upper()
    if key not in ARCHIVE_SOURCES:
        raise HTTPException(status_code=404, detail=f"No archive source for '{mission_id}'. Available: {', '.join(ARCHIVE_SOURCES)}.")
    t0, t1 = _parse_utc(start, "start"), _parse_utc(end, "end")
    if t1 <= t0:
        raise HTTPException(status_code=422, detail="'end' must be after 'start'.")
    if t1 - t0 > timedelta(days=ARCHIVE_MAX_DAYS):
        raise HTTPException(status_code=422, detail=f"Intervals are limited to {ARCHIVE_MAX_DAYS} days.")

    bundle = await downloader.get_archive_bundle(key, t0, t1, cadence_minutes=cadence_minutes)
    data, prov = bundle["records"], bundle["provenance"]
    if format == "csv":
        meta = {
            "title": f"HELIOS-L1 archive export: {key}",
            "software": f"HELIOS-L1 {__version__}",
            "data_kind": prov.get("kind"),
            "provenance": prov.get("description"),
            "datasets": ", ".join(d["id"] for d in prov.get("datasets", [])) or "n/a",
            "archive": HAPI_SERVER,
            "time_standard": "UTC",
            "time_coverage": f"{prov.get('time_coverage_start')} to {prov.get('time_coverage_end')}",
            "cadence_seconds": prov.get("cadence_seconds"),
            "retrieved_utc": prov.get("retrieved_utc"),
            "missing_values": "empty cell",
        }
        stamp = f"{t0:%Y%m%dT%H%M}_{t1:%Y%m%dT%H%M}"
        return Response(content=DataExporter.to_csv(data, metadata=meta), media_type="text/csv", headers={
            "Content-Disposition": f"attachment; filename=HELIOS_{key}_archive_{stamp}.csv"
        })
    return {
        "mission": {"id": key, "name": MISSIONS.get(key, {}).get("name", key)},
        "provenance": prov,
        "data_points": len(data),
        "latest": latest_valid_record(data),
        "detected_shocks": SpaceWeatherPhysics.detect_interplanetary_shocks(data),
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
        prov_a = {"kind": "imported", "description": f"User-imported file ({name_a})."}
    else:
        if key_a not in MISSIONS:
            raise HTTPException(status_code=400, detail=f"Invalid mission ID '{key_a}' for comparison.")
        bundle_a = await downloader.get_telemetry_bundle(key_a, span_days=span_days)
        data_a, prov_a = bundle_a["records"], bundle_a["provenance"]
        name_a = MISSIONS[key_a]["name"]

    if key_b == "CUSTOM":
        if not latest_custom_dataset or not latest_custom_dataset.get("records"):
            raise HTTPException(status_code=400, detail="No custom dataset imported for comparison.")
        data_b = latest_custom_dataset["records"]
        name_b = latest_custom_dataset.get("mission_name", "Custom Spacecraft")
        prov_b = {"kind": "imported", "description": f"User-imported file ({name_b})."}
    else:
        if key_b not in MISSIONS:
            raise HTTPException(status_code=400, detail=f"Invalid mission ID '{key_b}' for comparison.")
        bundle_b = await downloader.get_telemetry_bundle(key_b, span_days=span_days)
        data_b, prov_b = bundle_b["records"], bundle_b["provenance"]
        name_b = MISSIONS[key_b]["name"]

    # Observed RTSW data: place each side at the spacecraft that actually supplied it
    # (e.g. SOLAR1 for the operational "DSCOVR" stream) instead of the mission's model orbit.
    def supplier(data, prov):
        if prov.get("kind") != "observed" or not data:
            return None
        return data[-1].get("source_spacecraft") or (
            prov["source_spacecraft"][0] if len(prov.get("source_spacecraft") or []) == 1 else None)

    pos_a, pos_b = await asyncio.gather(downloader.get_rtsw_position(supplier(data_a, prov_a)),
                                        downloader.get_rtsw_position(supplier(data_b, prov_b)))
    comparison = await run_in_workers(
        SatelliteComparator.compare_satellites,
        telemetry_a=data_a,
        telemetry_b=data_b,
        mission_a_name=name_a,
        mission_b_name=name_b,
        parameter=parameter,
        position_a=pos_a,
        position_b=pos_b
    )
    # A correlation between a measured and a simulated series says nothing about the
    # instruments; expose what each side actually is.
    comparison["provenance_a"] = prov_a
    comparison["provenance_b"] = prov_b
    return comparison

@app.get("/api/compare/matrix")
async def get_comparison_matrix(
    parameter: str = Query("bz_gsm"),
    span_days: int = Query(1, ge=1, le=7)
):
    fleet_keys = ["DSCOVR", "ACE", "ADITYA_L1", "WIND", "SOHO"]
    bundles = await asyncio.gather(*(downloader.get_telemetry_bundle(k, span_days=span_days) for k in fleet_keys))
    telemetry_map = {k: b["records"] for k, b in zip(fleet_keys, bundles)}
    result = await run_in_workers(SatelliteComparator.compute_fleet_matrix, telemetry_map, parameter=parameter)
    result["provenance"] = {k: b["provenance"]["kind"] for k, b in zip(fleet_keys, bundles)}
    return result

@app.get("/api/forecast/ml")
async def get_ml_forecast(mission_id: str = Query("DSCOVR")):
    mission_key = mission_id.upper()
    if mission_key not in MISSIONS:
        mission_key = "DSCOVR"
    data, kyoto, noaa = await asyncio.gather(downloader.get_satellite_telemetry(mission_key, span_days=1),
                                             downloader.get_kyoto_dst(), downloader.get_noaa_geomag_forecast())
    obs = kyoto["records"]
    out = SpaceWeatherForecaster.forecast_geomagnetic_storm(
        data, observed_dst=obs[-1]["dst"] if obs else None, noaa_forecast=noaa)
    if out.get("status") == "error":
        raise HTTPException(status_code=503, detail=out["message"])
    return out


@app.get("/api/storm/indices")
async def get_storm_indices(
    start: str = Query(..., description="UTC start, ISO 8601"),
    end: str = Query(..., description="UTC end (exclusive), ISO 8601"),
    cadence_minutes: int = Query(5, ge=1, le=60)
):
    """
    Observed geomagnetic indices from OMNI (SYM-H, ASY-H, AE, AL, AU; WDC Kyoto) for an
    interval of up to 31 days, with the O'Brien & McPherron (2000) and Burton et al.
    (1975) ring current models driven by the OMNI solar wind and scored against SYM-H.
    """
    t0, t1 = _parse_utc(start, "start"), _parse_utc(end, "end")
    if t1 <= t0:
        raise HTTPException(status_code=422, detail="'end' must be after 'start'.")
    if t1 - t0 > timedelta(days=ARCHIVE_MAX_DAYS):
        raise HTTPException(status_code=422, detail=f"Intervals are limited to {ARCHIVE_MAX_DAYS} days.")
    bundle = await downloader.get_archive_bundle("OMNI", t0, t1, cadence_minutes=cadence_minutes)
    recs = bundle["records"]
    keys = ("sym_h", "asy_h", "ae", "al", "au")
    return {
        "provenance": bundle["provenance"],
        "data_points": len(recs),
        "indices": {k: [r.get(k) for r in recs] for k in keys},
        "time_tags": [r["time_tag"] for r in recs],
        "dst_comparison": AuroralModel.compare_dst_models(recs) if recs else None,
    }

# ----------------------------------------------------------------------------
# Event analysis on native-cadence archive data (helios.core.event_analysis)
# ----------------------------------------------------------------------------
def _event_mission(mission: str) -> str:
    key = mission.upper()
    if key not in EVENT_SOURCES:
        raise HTTPException(status_code=404, detail=f"No event analysis source for '{mission}'. "
                            f"Available: {', '.join(EVENT_SOURCES)}.")
    return key


def _event_series(field, plasma, max_points: int = 2500) -> Dict[str, Any]:
    """Field and plasma time series for plotting, block-averaged to at most `max_points` samples each."""
    def thin(df, cols):
        if df is None or df.empty:
            return {"time_tags": [], **{c: [] for c in cols}}
        df = df[cols]
        span = (df.index[-1] - df.index[0]).total_seconds()
        if len(df) > max_points and span > 0:
            df = df.resample(f"{max(1, int(math.ceil(span / max_points)))}s").mean().dropna(how="all")
        out = {"time_tags": [t.strftime("%Y-%m-%d %H:%M:%S") for t in df.index]}
        for c in cols:
            out[c] = [None if not np.isfinite(v) else round(float(v), 3) for v in df[c].to_numpy(dtype=float)]
        return out

    f = thin(field, ["bx", "by", "bz"])
    f["bt"] = [None if None in (x, y, z) else round(math.sqrt(x * x + y * y + z * z), 3)
               for x, y, z in zip(f["bx"], f["by"], f["bz"])]
    return {"field_gse": f, "plasma_gse": thin(plasma, ["vx", "vy", "vz", "n", "t"])}


def _analysis_provenance(key: str, data: Dict[str, Any], t0: datetime, t1: datetime, method: str,
                         parameters: Dict[str, Any]) -> Dict[str, Any]:
    """Everything needed to reproduce an analysis: data sets and requests, method, parameters, software."""
    return {
        "kind": "observed" if data.get("field") is not None else "unavailable",
        "spacecraft": key,
        "archive": HAPI_SERVER,
        "datasets": data.get("datasets", []),
        "requested_start": t0.strftime("%Y-%m-%d %H:%M:%S"),
        "requested_end": t1.strftime("%Y-%m-%d %H:%M:%S"),
        "coordinates": "GSE",
        "time_standard": "UTC",
        "method": method,
        "parameters": parameters,
        "software": f"HELIOS-L1 {__version__}",
        "retrieved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }


def _analysis_answer(body: Dict[str, Any], download: bool, name: str):
    """The analysis as JSON, or as a JSON file (results, inputs and provenance) when `download` is set."""
    if not download:
        return body
    return Response(content=json.dumps(body, indent=1, default=str), media_type="application/json", headers={
        "Content-Disposition": f"attachment; filename={name}.json"})


async def _run_shock(key: str, tc: datetime, upstream_minutes: float, downstream_minutes: float,
                     exclude_minutes: float, refine: bool):
    """Fetch native-cadence data around tc and analyse the shock: (data, result, t0, t1)."""
    margin = 12.0  # minutes of context, and room for the refined shock time
    t0 = tc - timedelta(minutes=upstream_minutes + exclude_minutes + margin)
    t1 = tc + timedelta(minutes=downstream_minutes + exclude_minutes + margin)
    data = await downloader.events.fetch(key, t0, t1)
    if data["field"] is None or data["plasma"] is None:
        missing = "magnetic field" if data["field"] is None else "plasma"
        msg = ("The CDAWeb HAPI server could not be reached and nothing is cached for this interval."
               if data["offline"] else f"CDAWeb has no {key} {missing} data for this interval.")
        raise HTTPException(status_code=404, detail=msg)
    try:
        result = await run_in_workers(analyze_shock, data["field"], data["plasma"], tc, upstream_minutes,
                                      downstream_minutes, exclude_minutes, refine)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return data, result, t0, t1


SHOCK_METHOD_TEXT = "Interplanetary shock normals (MC, VC, MX1-3) and mass flux shock speed, Schwartz (1998)"


@app.get("/api/analysis/shock")
async def analyse_shock(
    mission: str = Query("WIND", description="WIND, ACE or DSCOVR"),
    time: str = Query(..., description="Approximate UTC shock time, ISO 8601"),
    upstream_minutes: float = Query(10.0, ge=1.0, le=60.0),
    downstream_minutes: float = Query(10.0, ge=1.0, le=60.0),
    exclude_minutes: float = Query(1.0, ge=0.0, le=15.0, description="Gap left out on each side of the shock"),
    refine: bool = Query(True, description="Move the shock time to the |B| ramp within 10 minutes"),
    download: bool = Query(False, description="Answer as a JSON file with the full provenance"),
):
    """
    Shock normal (MC, VC, MX1-3), theta_Bn, shock speed, jumps and Mach numbers from WIND,
    ACE or DSCOVR data at the instruments' cadence (Schwartz 1998; CfA shock database
    conventions).
    """
    key = _event_mission(mission)
    tc = _parse_utc(time, "time")
    data, result, t0, t1 = await _run_shock(key, tc, upstream_minutes, downstream_minutes, exclude_minutes, refine)
    params = {"time": tc.strftime("%Y-%m-%d %H:%M:%S"), "upstream_minutes": upstream_minutes,
              "downstream_minutes": downstream_minutes, "exclude_minutes": exclude_minutes, "refine": refine}
    prov = _analysis_provenance(key, data, t0, t1, SHOCK_METHOD_TEXT, params)
    body = {"provenance": prov, "result": result, "series": _event_series(data["field"], data["plasma"])}
    return _analysis_answer(body, download, f"HELIOS_shock_{key}_{tc:%Y%m%dT%H%M}")


@app.get("/api/analysis/timing")
async def analyse_timing(
    reference: str = Query("WIND", description="Spacecraft whose shock normal and speed are used"),
    time: str = Query(..., description="Approximate UTC shock time at the reference spacecraft"),
    targets: str = Query("ACE,DSCOVR,WIND", description="Comma-separated spacecraft to check"),
    method: str = Query("MX3", description="Normal used for the prediction (MC, VC, MX1, MX2, MX3)"),
    upstream_minutes: float = Query(10.0, ge=1.0, le=60.0),
    downstream_minutes: float = Query(10.0, ge=1.0, le=60.0),
    exclude_minutes: float = Query(1.0, ge=0.0, le=15.0),
    search_minutes: float = Query(20.0, ge=2.0, le=60.0, description="Search for the observed jump around the prediction"),
    download: bool = Query(False, description="Answer as a JSON file with the full provenance"),
):
    """
    Multi-spacecraft timing: the shock normal and speed at the reference spacecraft predict
    the arrival at the others from their measured positions (t = t_ref + n . dr / V_sh); the
    observed arrival (|B| ramp near the prediction), the residual and the implied speed along
    n test whether the shock is planar over the baseline.
    """
    key = _event_mission(reference)
    method = method.upper()
    if method not in SHOCK_METHODS:
        raise HTTPException(status_code=422, detail=f"'method' must be one of {', '.join(SHOCK_METHODS)}.")
    tc = _parse_utc(time, "time")
    data, result, t0, t1 = await _run_shock(key, tc, upstream_minutes, downstream_minutes, exclude_minutes, True)
    if method not in result["methods"]:
        raise HTTPException(status_code=422, detail=f"The {method} normal is undefined for this shock.")
    t_ref = pd.Timestamp(result["shock_time"], tz="UTC")
    r_ref = position_at(data["position"], t_ref)
    if r_ref is None:
        raise HTTPException(status_code=422, detail=f"No {key} position near the shock time.")
    m = result["methods"][method]

    names = [s.strip().upper() for s in targets.split(",") if s.strip()]
    names = [n for n in dict.fromkeys(names) if n in EVENT_SOURCES and n != key]
    span = timedelta(minutes=90)

    async def one(name):
        tdata = await downloader.events.fetch(name, (t_ref - span).to_pydatetime(), (t_ref + span).to_pydatetime())
        entry = {"spacecraft": name, "datasets": tdata["datasets"]}
        r = position_at(tdata["position"], t_ref)
        if r is None or tdata["field"] is None:
            if r is None and tdata["field"] is None:
                entry["status"] = "no data for this interval" + (" (CDAWeb not reached)" if tdata["offline"] else "")
            else:
                entry["status"] = "no position" if r is None else "no magnetic field data"
            return entry
        cmp = await run_in_workers(timing_comparison, m["normal_gse"], m["shock_speed_kms"], t_ref, r_ref,
                                   tdata["field"], r, search_minutes)
        entry.update(cmp, status="ok", position_gse_km=r.tolist())
        return entry

    checks = await asyncio.gather(*(one(n) for n in names))
    params = {"time": tc.strftime("%Y-%m-%d %H:%M:%S"), "method": method, "targets": names,
              "upstream_minutes": upstream_minutes, "downstream_minutes": downstream_minutes,
              "exclude_minutes": exclude_minutes, "search_minutes": search_minutes}
    prov = _analysis_provenance(key, data, t0, t1, SHOCK_METHOD_TEXT + "; planar-shock timing t = t_ref + n.dr/V_sh",
                                params)
    prov["datasets"] = prov["datasets"] + [dict(d, spacecraft=c["spacecraft"]) for c in checks for d in c["datasets"]]
    body = {
        "provenance": prov,
        "reference": {"spacecraft": key, "shock_time": result["shock_time"], "position_gse_km": r_ref.tolist(),
                      "method": method, "normal_gse": m["normal_gse"], "shock_speed_kms": m["shock_speed_kms"],
                      "shock_type": result["shock_type"], "warnings": result["warnings"]},
        "targets": [{k: v for k, v in c.items() if k != "datasets"} for c in checks],
        "note": ("Residual = observed - predicted delay. Residuals of a minute or two over baselines of several "
                 "hundred thousand km are common: interplanetary shocks are not planar on these scales and the "
                 "single-spacecraft normal has an uncertainty of several degrees."),
    }
    return _analysis_answer(body, download, f"HELIOS_timing_{key}_{tc:%Y%m%dT%H%M}")


@app.get("/api/analysis/fluxrope")
async def analyse_flux_rope(
    mission: str = Query("WIND", description="WIND, ACE or DSCOVR"),
    start: str = Query(..., description="UTC start of the magnetic cloud, ISO 8601"),
    end: str = Query(..., description="UTC end of the magnetic cloud, ISO 8601"),
    average_minutes: int = Query(30, ge=5, le=120, description="Field averages used in the fit"),
    speed_kms: Optional[float] = Query(None, gt=100, lt=3000, description="Cloud speed; default: mean measured speed"),
    download: bool = Query(False, description="Answer as a JSON file with the full provenance"),
):
    """
    Force-free (Lundquist) flux rope fit to a magnetic cloud (Lepping et al. 1990): axis
    direction, B0, handedness, closest approach, diameter, axial flux and chi_R, as listed
    in the WIND MFI magnetic cloud table.
    """
    key = _event_mission(mission)
    t0, t1 = _parse_utc(start, "start"), _parse_utc(end, "end")
    if t1 - t0 < timedelta(hours=3):
        raise HTTPException(status_code=422, detail="A magnetic cloud interval must be at least 3 hours long.")
    if t1 - t0 > timedelta(hours=MAX_EVENT_HOURS):
        raise HTTPException(status_code=422, detail=f"Intervals are limited to {MAX_EVENT_HOURS} hours.")
    data = await downloader.events.fetch(key, t0, t1, coarse=True)
    if data["field"] is None:
        raise HTTPException(status_code=404, detail="No magnetic field data for this interval"
                            + (" (CDAWeb could not be reached)." if data["offline"] else "."))
    try:
        result = await run_in_workers(fit_flux_rope, data["field"], data["plasma"], t0, t1, average_minutes, speed_kms)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    params = {"average_minutes": average_minutes, "speed_kms": speed_kms}
    prov = _analysis_provenance(key, data, t0, t1, "Lundquist force-free flux rope fit, Lepping et al. (1990)", params)
    return _analysis_answer({"provenance": prov, "result": result}, download, f"HELIOS_fluxrope_{key}_{t0:%Y%m%dT%H%M}")


SEA_MAX_EVENTS = 60
SEA_MAX_HOURS = 240


@app.get("/api/analysis/superposed")
async def analyse_superposed_epoch(
    onsets: str = Query(..., description="Comma-separated UTC onset times (epoch zero), ISO 8601"),
    parameters: str = Query("sym_h,bz_gsm,speed,dynamic_pressure", description="OMNI quantities to superpose"),
    before_hours: float = Query(12.0, ge=0.0, le=120.0),
    after_hours: float = Query(48.0, gt=0.0, le=240.0),
    cadence_minutes: int = Query(10, ge=1, le=180),
    format: str = Query("json", pattern="^(json|csv)$"),
    download: bool = Query(False, description="Answer as a JSON file with the full provenance"),
):
    """
    Superposed epoch analysis of OMNI 1-min data (SYM-H, AE, solar wind drivers) keyed on
    the given onset times, e.g. storm sudden commencements or shock arrivals.
    """
    try:
        times = [_parse_utc(s, "onsets") for s in onsets.split(",") if s.strip()]
    except HTTPException:
        raise HTTPException(status_code=422, detail="'onsets' must be comma-separated ISO 8601 UTC times.")
    if not times:
        raise HTTPException(status_code=422, detail="Give at least one onset time.")
    if len(times) > SEA_MAX_EVENTS:
        raise HTTPException(status_code=422, detail=f"At most {SEA_MAX_EVENTS} onsets.")
    if before_hours + after_hours > SEA_MAX_HOURS:
        raise HTTPException(status_code=422, detail=f"The epoch window is limited to {SEA_MAX_HOURS} hours.")
    params = [p.strip().lower() for p in parameters.split(",") if p.strip()]
    unknown = [p for p in params if p not in SEA_PARAMETERS]
    if unknown or not params:
        raise HTTPException(status_code=422, detail=f"Unknown parameter(s) {', '.join(unknown) or '(none)'}; "
                                                    f"available: {', '.join(SEA_PARAMETERS)}.")
    sem = asyncio.Semaphore(4)

    async def one(t):
        async with sem:
            return await downloader.get_archive_bundle("OMNI", t - timedelta(hours=before_hours),
                                                       t + timedelta(hours=after_hours), cadence_minutes=1)

    bundles = await asyncio.gather(*(one(t) for t in times))
    result = await run_in_workers(superposed_epoch, [(t, b["records"]) for t, b in zip(times, bundles)],
                                  params, before_hours, after_hours, cadence_minutes)
    if not any(b["records"] for b in bundles):
        raise HTTPException(status_code=404, detail="OMNI has no data for any of the windows"
                            + (" (CDAWeb could not be reached)." if all(b["provenance"].get("kind") != "observed"
                                                                        for b in bundles) else "."))
    prov = {
        "kind": "observed",
        "archive": HAPI_SERVER,
        "datasets": [{"onset": t.strftime("%Y-%m-%d %H:%M"), "kind": b["provenance"].get("kind"),
                      "datasets": b["provenance"].get("datasets", []),
                      "coverage": [b["provenance"].get("time_coverage_start"), b["provenance"].get("time_coverage_end")]}
                     for t, b in zip(times, bundles)],
        "time_standard": "UTC",
        "note": "OMNI 1-min values are time-shifted to the bow shock nose; SYM-H, ASY-H, AE, AL and AU are WDC Kyoto.",
        "method": result["method"],
        "parameters": {"onsets": [t.strftime("%Y-%m-%d %H:%M:%S") for t in times], "parameters": params,
                       "before_hours": before_hours, "after_hours": after_hours, "cadence_minutes": cadence_minutes},
        "software": f"HELIOS-L1 {__version__}",
        "retrieved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    }
    stamp = f"{times[0]:%Y%m%dT%H%M}_{len(times)}events"
    if format == "csv":
        out = io.StringIO()
        out.write(f"# title: HELIOS-L1 superposed epoch analysis ({len(times)} events, OMNI 1-min)\n")
        out.write(f"# onsets: {' '.join(prov['parameters']['onsets'])}\n")
        out.write(f"# method: {result['method']}\n# cadence_minutes: {cadence_minutes}\n")
        out.write(f"# software: {prov['software']}\n# retrieved_utc: {prov['retrieved_utc']}\n")
        w = csv.writer(out, lineterminator="\n")
        cols = ["epoch_hours"] + [f"{p}_{s}" for p in params for s in ("mean", "median", "q25", "q75", "n_events")]
        w.writerow(cols)
        for i, e in enumerate(result["epoch_hours"]):
            row = [round(e, 4)]
            for p in params:
                st = result["statistics"][p]
                row += ["" if st[s][i] is None else st[s][i] for s in ("mean", "median", "q25", "q75")] + [st["n_events"][i]]
            w.writerow(row)
        return Response(content=out.getvalue(), media_type="text/csv", headers={
            "Content-Disposition": f"attachment; filename=HELIOS_superposed_epoch_{stamp}.csv"})
    return _analysis_answer({"provenance": prov, "result": result}, download, f"HELIOS_superposed_epoch_{stamp}")


@app.get("/api/analysis/mva")
async def analyse_mva(
    mission: str = Query("WIND", description="WIND, ACE or DSCOVR"),
    start: str = Query(..., description="UTC start, ISO 8601"),
    end: str = Query(..., description="UTC end (exclusive), ISO 8601"),
    average_seconds: int = Query(0, ge=0, le=3600, description="0 = native cadence; otherwise block averages"),
    download: bool = Query(False, description="Answer as a JSON file with the full provenance"),
):
    """Minimum variance analysis of the magnetic field (Sonnerup & Scheible 1998) for an interval of up to 72 h."""
    key = _event_mission(mission)
    t0, t1 = _parse_utc(start, "start"), _parse_utc(end, "end")
    if t1 <= t0:
        raise HTTPException(status_code=422, detail="'end' must be after 'start'.")
    if t1 - t0 > timedelta(hours=MAX_EVENT_HOURS):
        raise HTTPException(status_code=422, detail=f"Intervals are limited to {MAX_EVENT_HOURS} hours.")
    data = await downloader.events.fetch(key, t0, t1)
    field = data["field"]
    if field is None:
        raise HTTPException(status_code=404, detail="No magnetic field data for this interval"
                            + (" (CDAWeb could not be reached)." if data["offline"] else "."))
    field = field[(field.index >= pd.Timestamp(t0)) & (field.index < pd.Timestamp(t1))]
    if average_seconds:
        field = field.resample(f"{average_seconds}s").mean().dropna()
    try:
        result = await run_in_workers(minimum_variance, field[["bx", "by", "bz"]].to_numpy())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    prov = _analysis_provenance(key, data, t0, t1, result["method"], {"average_seconds": average_seconds})
    body = {"provenance": prov, "result": result, "series": _event_series(field, None)}
    return _analysis_answer(body, download, f"HELIOS_mva_{key}_{t0:%Y%m%dT%H%M}")


@app.get("/api/events")
async def get_events():
    return [
        {"id": "may_2024_g5", "title": "May 2024 Extreme G5 Superstorm (AR 3664)", "severity": "Extreme G5 (Kp=9)", "icon": "fa-bolt", "badge_color": "#dc2626"},
        {"id": "halloween_2003", "title": "Halloween 2003 Storms (X17+ Flare)", "severity": "Extreme G5 (Kp=9)", "icon": "fa-radiation", "badge_color": "#dc2626"},
        {"id": "bastille_2000", "title": "Bastille Day 2000 Superstorm (X5.7)", "severity": "Extreme G5 / S5 (Kp=9)", "icon": "fa-fire-flame-curved", "badge_color": "#ea580c"},
        {"id": "quebec_1989", "title": "Hydro-Québec Blackout (March 1989)", "severity": "Extreme G5 (Dst -589)", "icon": "fa-plug-circle-xmark", "badge_color": "#e11d48"},
        {"id": "carrington_1859", "title": "Carrington Event (September 1859)", "severity": "Superstorm (Dst <-850)", "icon": "fa-meteor", "badge_color": "#9333ea"},
        {"id": "st_patricks_2015", "title": "St. Patrick's Day Storm (March 2015)", "severity": "Severe G4 (Kp=8-)", "icon": "fa-cloud-bolt", "badge_color": "#f59e0b"},
        {"id": "quiet_baseline", "title": "Quiet Sun Solar Wind Baseline", "severity": "Quiet G0 (Kp=1)", "icon": "fa-sun", "badge_color": "#10b981"}
    ]

@app.get("/api/event/{event_id}")
@app.get("/api/events/{event_id}")
async def get_event(event_id: str):
    return await downloader.get_historical_event(event_id)

def check_epoch(epoch: Optional[str]) -> None:
    """422 for an epoch the ephemeris engine cannot read (it used to fall back to a fixed date)."""
    if epoch:
        try:
            get_spice_engine().epoch_to_et(epoch)
        except ValueError as e:
            raise HTTPException(status_code=422, detail=str(e))


@app.get("/api/orbits")
async def get_orbits(epoch: Optional[str] = Query(None, description="UTC ISO epoch for spacecraft position calculations")):
    check_epoch(epoch)
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
    check_epoch(epoch)
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
    check_epoch(epoch)
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

async def observed_al(when: datetime) -> Tuple[Optional[float], Optional[str]]:
    """Mean OMNI 1-min AL (nT) over the hour before `when`, if at least 30 minutes have data."""
    try:
        bundle = await downloader.get_archive_bundle("OMNI", when - timedelta(hours=1), when)
    except Exception:  # archive unreachable: the oval falls back to Kp
        return None, None
    values = [r["al"] for r in bundle["records"] if r.get("al") is not None]
    if len(values) < 30:
        return None, None
    return float(np.mean(values)), f"OMNI 1-min AL (WDC Kyoto), mean of {len(values)} min before {when:%Y-%m-%d %H:%M} UTC"

@app.get("/api/aurora")
async def get_aurora(kp: Optional[float] = Query(None, ge=0.0, le=9.0),
                     bz_gsm: Optional[float] = None,
                     al: Optional[float] = Query(None, ge=-5000.0, le=5000.0, description="AL index (nT) driving the Starkov oval; default: OMNI AL, else Kp converted to AL"),
                     time: Optional[str] = Query(None, description="UTC time of the oval, ISO 8601 (default now)"),
                     dst_model: str = Query("obrien", description="Ring current model: 'obrien' (O'Brien & McPherron 2000) or 'burton' (Burton et al. 1975)")):
    try:
        model_key = AuroralModel.dst_model_key(dst_model)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    oval_time = _parse_utc(time, "time") if time else datetime.now(timezone.utc)
    historical = time is not None and datetime.now(timezone.utc) - oval_time > timedelta(hours=3)
    bundle, kyoto = await asyncio.gather(downloader.get_telemetry_bundle("DSCOVR", span_days=1),
                                         downloader.get_kyoto_dst())
    data = bundle["records"]
    latest_rec = latest_valid_record(data)

    if bz_gsm is None:
        bz_val = latest_rec.get("bz_gsm")
        bz_val = float(bz_val) if bz_val is not None else -3.0
    else:
        bz_val = float(bz_gsm)

    # Starkov (1994) is driven by AL: user value, else the OMNI 1-min AL averaged over the
    # hour before the oval time (OMNI lags real time by days or more), else Kp -> AL.
    al_val, al_source = (float(al), "user input") if al is not None else (None, None)
    if al_val is None:
        al_val, al_source = await observed_al(oval_time)
    if historical and al_val is None and kp is None:
        raise HTTPException(status_code=404, detail=f"No OMNI AL index for the hour before {oval_time:%Y-%m-%d %H:%M} UTC; pass kp or al to draw the oval for that time.")

    kp_source = "user input"
    if kp is None and historical:
        kp_val, kp_source = 0.0, "not used (OMNI AL drives the oval)"
    elif kp is None:
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

    boundaries = AuroralModel.calculate_auroral_boundaries(kp_val, bz_val, al_nt=al_val, al_source=al_source)
    oval_polygon = AuroralModel.generate_auroral_oval_coordinates(kp_val, bz_val, al_nt=al_val, when=oval_time)
    if historical and kp is None:
        boundaries["hemispheric_power_gw"] = None  # the Kp-based estimate has no Kp to use
    # The L1 drivers reach Earth ~45-60 min later: time-shift them before comparing with
    # observed Kyoto Dst over the same window. The model starts from the observed value.
    drivers = propagate_to_earth(data)
    obs = kyoto["records"]
    t0 = drivers[0]["time_tag"] if drivers else None
    t1 = drivers[-1]["time_tag"] if drivers else None
    obs_window = [o for o in obs if t0 and t0[:13] <= o["time_tag"][:13] <= t1[:13]]
    initial = AuroralModel.observed_at(obs, t0) if t0 else None
    dst_sim = AuroralModel.simulate_dst_evolution(drivers, model=model_key, initial_dst=initial)
    return {
        "kp": kp_val,
        "kp_source": kp_source,
        "al_nt": boundaries["al_used_nt"],
        "al_source": boundaries["al_source"],
        "oval_time_utc": oval_time.strftime("%Y-%m-%d %H:%M:%S"),
        "bz_gsm": bz_val,
        "boundaries": boundaries,
        "oval_polygon": oval_polygon,
        "dst_model": AuroralModel.DST_MODELS[model_key]["name"],
        "dst_initial_observed_nt": initial,
        "dst_evolution": dst_sim,
        "dst_observed": obs_window,
        "dst_observed_source": kyoto["source"],
        "dst_skill": AuroralModel.dst_skill(AuroralModel.hourly_pairs(dst_sim, obs_window)),
        "drivers_provenance": bundle["provenance"],
        "drivers_time_shift": "L1 records shifted by their L1-to-Earth travel time (distance / speed)"
    }

@app.get("/api/magnetosphere/boundaries")
async def get_magnetospheric_boundaries(
    dynamic_pressure: float = Query(2.0, ge=0.01, le=120.0, description="Solar wind dynamic pressure P_dyn (nPa)"),
    bz_gsm: float = Query(0.0, ge=-80.0, le=80.0, description="Interplanetary Magnetic Field Bz component (nT)"),
    mach_number: float = Query(8.0, ge=1.2, le=30.0, description="Solar wind magnetosonic Mach number M_ms"),
    plasma_beta: float = Query(2.0, ge=0.0, le=100.0, description="Solar wind plasma beta (OMNI definition)"),
    model: str = Query("chao", description="Bow shock model: 'chao' (Chao et al., 2002) or 'shue' (Farris & Russell, 1994, from the Shue et al. 1998 magnetopause)")
):
    """
    Computes magnetopause and bow shock standoff distances, flaring parameters and
    GSE coordinate profiles. The magnetopause is Shue et al. (1998); the bow shock is
    Chao et al. (2002) or Farris & Russell (1994).
    """
    if model.lower().strip() not in ("chao", "shue", "farris"):
        raise HTTPException(status_code=400, detail="model must be 'chao' or 'shue'")
    return SpaceWeatherPhysics.calculate_magnetospheric_boundaries(
        dynamic_pressure_npa=dynamic_pressure,
        bz_gsm_nt=bz_gsm,
        mach_number=mach_number,
        model=model,
        plasma_beta=plasma_beta
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
    phi_pc = SpaceWeatherPhysics.polar_cap_potential(speed_kms=speed_kms, by_gsm_nt=by_gsm_nt, bz_gsm_nt=bz_gsm_nt,
                                                     b_total_nt=b_total_nt)
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

@app.get("/api/solar/regions")
async def get_solar_regions():
    """Observed numbered active regions (NOAA SWPC solar region summary, latest day)."""
    return await downloader.get_solar_regions()

@app.get("/api/coronagraph/feeds")
async def get_coronagraph_feeds():
    return CoronagraphAnalyzer.get_coronagraph_feeds()

@app.post("/api/coronagraph/kinematics")
async def calculate_cme_kinematics(req: CMEKinematicsRequest):
    return CoronagraphAnalyzer.calculate_cme_kinematics(
        r1_rsun=req.r1_rsun,
        r2_rsun=req.r2_rsun,
        dt_minutes=req.dt_minutes,
        launch_time_iso=req.launch_time_iso,
        ambient_wind_kms=req.ambient_wind_kms,
        gamma_drag=req.gamma_drag
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
    """Returns currently loaded custom ingested telemetry ({"status": "empty"} if none yet)."""
    if not latest_custom_dataset:
        # Not an error: the import tab asks on every visit, before anything was imported.
        return {"status": "empty", "total_records": 0, "detail": "No custom telemetry dataset has been ingested yet."}
    return latest_custom_dataset

@app.get("/api/custom/export/{export_format}")
async def export_custom_telemetry(export_format: str):
    """Exports currently ingested custom dataset as CSV or JSON."""
    if not latest_custom_dataset or "records" not in latest_custom_dataset:
        raise HTTPException(status_code=404, detail="No custom telemetry available to export.")
    records = latest_custom_dataset["records"]
    mission_slug = latest_custom_dataset.get("mission_name", "custom").lower().replace(" ", "_")

    if export_format.lower() == "csv":
        times = [r["time_tag"] for r in records if r.get("time_tag")]
        meta = {
            "title": f"HELIOS-L1 imported telemetry: {latest_custom_dataset.get('mission_name', 'custom')}",
            "software": f"HELIOS-L1 {__version__}",
            "data_kind": "imported",
            "provenance": "User file imported into HELIOS-L1; derived quantities computed by HELIOS-L1.",
            "import_warnings": " | ".join(latest_custom_dataset.get("warnings") or []) or "none",
            "time_standard": "UTC",
            "time_coverage": f"{times[0]} to {times[-1]}" if times else "n/a",
            "missing_values": "empty cell",
        }
        return Response(
            content=DataExporter.to_csv(records, metadata=meta),
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
async def get_solar_cycle(year: Optional[float] = Query(None, ge=2019.9, le=2031.0)):
    """Observed cycle 25 indices and NOAA's predicted cycle; the analytic model only when NOAA is unreachable."""
    observed, predicted = await asyncio.gather(
        downloader.fetch_json(NOAA_SWPC_ENDPOINTS["solar_cycle_observed"], "solar_cycle_observed"),
        downloader.fetch_json(NOAA_SWPC_ENDPOINTS["solar_cycle_predicted"], "solar_cycle_predicted"))
    res = SolarCycleEngine.from_noaa(observed if isinstance(observed, list) else None,
                                     predicted if isinstance(predicted, list) else None, current_year_float=year)
    if res is not None:
        return res
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
    bundle = await downloader.get_telemetry_bundle(mission_key, span_days=1)
    data = bundle["records"]
    latest = latest_valid_record(data)
    classification = await classify_current_conditions(latest)
    shocks = SpaceWeatherPhysics.detect_interplanetary_shocks(data)
    auroral_data = AuroralModel.calculate_auroral_boundaries(classification["kp"], latest.get("bz_gsm") or 0.0)

    html = ScientificReportGenerator.generate_html_bulletin(
        mission_name=MISSIONS[mission_key]["name"],
        telemetry=data,
        classification=classification,
        shocks=shocks,
        auroral_data=auroral_data,
        provenance=bundle["provenance"]
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
    bundle = await downloader.get_telemetry_bundle(mission_key, span_days=1)
    data = bundle["records"]
    latest = latest_valid_record(data)
    classification = await classify_current_conditions(latest)
    shocks = SpaceWeatherPhysics.detect_interplanetary_shocks(data)
    auroral_data = AuroralModel.calculate_auroral_boundaries(classification["kp"], latest.get("bz_gsm") or 0.0)

    md = ScientificReportGenerator.generate_markdown_executive_summary(
        mission_name=MISSIONS[mission_key]["name"],
        telemetry=data,
        classification=classification,
        shocks=shocks,
        auroral_data=auroral_data,
        provenance=bundle["provenance"]
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
    values = await run_in_workers(regular_series, data, parameter, dt_seconds)
    speeds = [float(d.get("speed")) for d in data if d.get("speed") is not None and isinstance(d.get("speed"), (int, float))]
    v_mean = float(np.mean(speeds)) if speeds else 450.0
    res = await run_in_workers(SpaceWeatherPhysics.power_spectral_density, values,
                               dt_seconds=dt_seconds, v_sw_kms=v_mean)
    res["mission_id"] = mission_key
    res["parameter"] = parameter
    res["span_days"] = span_days
    return res

@app.get("/api/export/csv")
async def export_csv(
    mission_id: str = "DSCOVR",
    span_days: int = Query(1, ge=1, le=7),
    metadata: bool = Query(True, description="Prepend '# key: value' provenance and unit lines")
):
    if mission_id.upper() not in MISSIONS:
        raise HTTPException(status_code=404, detail=f"Mission '{mission_id}' not recognized.")
    bundle = await downloader.get_telemetry_bundle(mission_id.upper(), span_days=span_days)
    data = bundle["records"]
    meta = None
    if metadata:
        prov = bundle["provenance"]
        meta = {
            "title": f"HELIOS-L1 telemetry export: {MISSIONS[mission_id.upper()]['name']}",
            "software": f"HELIOS-L1 {__version__}",
            "data_kind": prov.get("kind"),
            "provenance": prov.get("description"),
            "source_spacecraft": prov.get("source_spacecraft") or "n/a",
            "time_standard": "UTC",
            "time_coverage": f"{prov.get('time_coverage_start')} to {prov.get('time_coverage_end')}",
            "cadence_seconds": prov.get("cadence_seconds"),
            "retrieved_utc": prov.get("retrieved_utc"),
            "missing_values": "empty cell",
        }
    csv_str = DataExporter.to_csv(data, metadata=meta)
    return Response(content=csv_str, media_type="text/csv", headers={
        "Content-Disposition": f"attachment; filename=HELIOS_{mission_id}_telemetry.csv"
    })

@app.get("/api/export/plot")
async def export_plot(mission_id: str = "DSCOVR", span_days: int = Query(1, ge=1, le=7)):
    mission_key = mission_id.upper()
    if mission_key not in MISSIONS:
        raise HTTPException(status_code=404, detail=f"Mission '{mission_id}' not recognized.")
    bundle = await downloader.get_telemetry_bundle(mission_key, span_days=span_days)
    name = MISSIONS.get(mission_key, {}).get("name", mission_id)
    png_bytes = await run_in_workers(DataExporter.generate_overview_chart, bundle["records"], name, bundle["provenance"])
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
