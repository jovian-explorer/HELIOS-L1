"""
FastAPI REST API server for HELIOS-L1.
Bridges scientific backend engines with interactive frontend dashboard.
"""
from typing import Optional, Dict, Any, List, Tuple
from pydantic import BaseModel, Field
from fastapi import Depends, FastAPI, Query, HTTPException, Request, Response
from fastapi.staticfiles import StaticFiles
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
import logging
import os
import importlib.util
import io
import asyncio
import csv
import json
import math
import re
import numpy as np
import pandas as pd
from datetime import datetime, timezone, timedelta

from helios import __version__
from helios.api.guard import LocalRequestGuard
from helios import settings_review, updates
from helios.config import (
    MISSIONS, STATIC_DIR, DATA_PROVIDERS,
    SCIENTIFIC_REFERENCES, PARAMETER_DEFINITIONS,
    get_system_settings, update_system_settings, run_in_workers, NOAA_SWPC_ENDPOINTS
)
from helios import config as helios_config
from helios.core import cme_tracking, icme_catalog, shock_catalog, solar_images
from helios.core.coverage import frame_coverage, describe as describe_coverage
from helios.core.downloader import DataDownloader, UnknownEventError, infer_cadence_seconds, regular_series
from helios.core.archive import ARCHIVE_SOURCES, HAPI_SERVER
from helios.core.event_analysis import (EVENT_SOURCES, MAX_EVENT_HOURS, SEA_PARAMETERS, SHOCK_METHODS,
                                        MC_CRITERIA, analyze_shock, coupling_with_errors, dehoffmann_teller,
                                        detect_magnetic_clouds,
                                        field_at_plasma_times, superposed_epoch,
                                        fit_flux_rope, minimum_variance, position_at, timing_comparison)
from helios.core.comparator import SatelliteComparator
from helios.core import timeshift
from helios.core import sudden_commencement as sc
from helios.core import gfz_indices
from helios.core import omni_statistics
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

async def reject_non_finite_numbers(request: Request) -> None:
    """
    422 for 'nan', 'inf' or overflowing numbers in the query string. FastAPI accepts them
    as floats; they ran through the models and failed JSON encoding as a 500.
    """
    for key, value in request.query_params.multi_items():
        try:
            x = float(value)
        except ValueError:
            continue
        if not math.isfinite(x):
            raise HTTPException(status_code=422, detail=f"'{key}' must be a finite number.")


app = FastAPI(
    title="HELIOS-L1 API",
    description="Heliophysical Exploration, Lagrange-1 Interplanetary Observation & Space-weather Suite",
    version=__version__,
    dependencies=[Depends(reject_non_finite_numbers)],
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

@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc: RequestValidationError):
    """
    The usual 422 list (loc, msg, type), with the offending input as text: FastAPI's own
    handler echoed it as JSON and failed with a 500 when it was NaN or Infinity, which
    Python's JSON parser accepts in request bodies.
    """
    errors = [{"loc": list(e.get("loc", ())), "msg": e.get("msg", ""), "type": e.get("type", ""),
               "input": repr(e.get("input"))[:200]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": errors})

# No CORS middleware: the interface is served by this server (same origin). The former
# allow_origins=["*"] with credentials let any web page open in the browser read every
# answer and send JSON POSTs (settings, imports) after an approved preflight.
# The guard rejects cross-site and DNS-rebinding requests before routing (helios.api.guard).
# Request body limits: an imported file (a year of 1-minute data as CSV is ~50 MB) and
# small JSON forms everywhere else.
MAX_IMPORT_BYTES = 64 * 1024 * 1024
MAX_FORM_BYTES = 64 * 1024
app.add_middleware(LocalRequestGuard, body_limits={"/api/custom/import": MAX_IMPORT_BYTES},
                   default_body_limit=MAX_FORM_BYTES)

downloader = DataDownloader()
solar_image_client = solar_images.SolarImageClient(lambda u: downloader.fetch_text(u), lambda u: downloader.fetch_bytes(u),
                                                   downloader.cache_dir)
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


def kp_from_solar_wind(rec: Dict[str, Any], drivers_kind: str = "observed") -> Tuple[Optional[float], str]:
    """
    Kp from the L1 solar wind with the Newell et al. (2008) fit, used only when no observed
    Kp can be fetched (it replaced a Bz-only step function and an ad hoc speed/Bz blend).
    (None, reason) without speed, density and Bz.
    """
    kp = SpaceWeatherForecaster.newell_2008_kp(rec.get("speed"), SpaceWeatherForecaster._density(rec),
                                              rec.get("by_gsm"), rec.get("bz_gsm"))
    if kp is None:
        return None, "unavailable (no observed Kp and no solar wind to estimate it)"
    src = "Estimated from L1 solar wind (Newell et al. 2008 fit; observed Kp unavailable)"
    return round(kp, 2), src if drivers_kind == "observed" else src + f", {drivers_kind} drivers, not measured"


def kp_interval(start: Optional[str]) -> str:
    """'2026-10-10 06:00-09:00 UTC' for a Kp time stamp, which marks the start of its 3-hour interval."""
    try:
        t0 = datetime.fromisoformat(str(start).replace("T", " ")[:19])
    except ValueError:
        return f"{start} UTC"
    return f"{t0:%Y-%m-%d %H:%M}-{t0 + timedelta(hours=3):%H:%M} UTC"


async def classify_current_conditions(latest: Dict[str, Any], drivers_kind: str = "observed") -> Dict[str, Any]:
    """
    NOAA G/R/S classification from observed indices (planetary Kp, GOES 0.1-0.8 nm X-rays,
    GOES >=10 MeV protons). Kp falls back to the Newell et al. (2008) solar wind estimate,
    flagged as such (with the kind of drivers); missing data is reported as missing, never
    replaced by a default.
    """
    indices = await downloader.get_space_weather_indices()
    if indices.get("kp") is not None:
        kp, kp_source = indices["kp"], f"Observed planetary Kp (NOAA SWPC, {kp_interval(indices.get('kp_time'))})"
    else:
        kp, kp_source = kp_from_solar_wind(latest, drivers_kind)
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
    # Ranges keep NaN/Infinity (valid in Python's JSON parser) and impossible values out;
    # they produced a 500 or a 200 answer with an "error" field.
    r1_rsun: float = Field(2.5, gt=1.0, le=300.0, allow_inf_nan=False)
    r2_rsun: float = Field(6.0, gt=1.0, le=300.0, allow_inf_nan=False)
    dt_minutes: float = Field(30.0, gt=0.0, le=10080.0, allow_inf_nan=False)
    launch_time_iso: Optional[str] = Field(None, max_length=64)
    ambient_wind_kms: float = Field(420.0, ge=100.0, le=1500.0, allow_inf_nan=False)
    gamma_drag: float = Field(1.0e-7, gt=0.0, le=1.0e-5, allow_inf_nan=False)

class JmapRequest(BaseModel):
    instrument: str = Field("lasco_c3", max_length=32)
    start: str = Field(..., max_length=40)
    end: str = Field(..., max_length=40)
    n: int = Field(24, ge=3, le=48)
    pa_deg: float = Field(270.0, ge=0.0, lt=360.0, allow_inf_nan=False)
    width_deg: float = Field(3.0, gt=0.0, le=30.0, allow_inf_nan=False)
    r_min: float = Field(2.5, gt=0.0, le=100.0, allow_inf_nan=False)
    r_max: float = Field(30.0, gt=0.0, le=100.0, allow_inf_nan=False)
    mode: str = Field("running", max_length=10)
    k_sigma: float = Field(3.0, gt=0.0, le=20.0, allow_inf_nan=False)

class TrackPoint(BaseModel):
    time: str = Field(..., max_length=40)
    r_rsun: float = Field(..., gt=0.0, le=300.0, allow_inf_nan=False)

class FrontFitRequest(BaseModel):
    points: List[TrackPoint] = Field(..., max_length=500)
    order: int = Field(1, ge=1, le=2)
    instrument: str = Field("lasco_c3", max_length=32)
    source_lon_deg: Optional[float] = Field(None, ge=-180.0, le=180.0, allow_inf_nan=False)
    source_lat_deg: Optional[float] = Field(None, ge=-90.0, le=90.0, allow_inf_nan=False)

class CustomImportRequest(BaseModel):
    content: str
    mission_name: Optional[str] = Field("User Spacecraft / OMNI", max_length=200)

class SettingsUpdateRequest(BaseModel):
    processors: Optional[int] = None
    theme: Optional[str] = None
    font_size: Optional[str] = None
    timezone: Optional[str] = None
    auto_update: Optional[bool] = None


class SettingsReviewRequest(BaseModel):
    settings: Dict[str, Any] = Field(default_factory=dict)

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
            timezone=req.timezone,
            auto_update=req.auto_update
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/api/updates")
async def get_update_status():
    """Automatic update: setting, last and next check, a build waiting to be installed, the running check."""
    return updates.status()


@app.post("/api/updates/check")
async def check_for_update():
    """Check now (also when automatic updates are off): download a newer build to install at the next start."""
    return updates.start_check(force=True)


@app.get("/api/settings/review")
async def get_settings_review():
    """Settings added, removed, changed or not usable since the version the user last reviewed (shown once)."""
    return settings_review.pending(release_notes=updates.installed_notes())


@app.post("/api/settings/review")
async def acknowledge_settings_review(req: SettingsReviewRequest):
    """The user has reviewed the changes: apply the values they picked and remember this version."""
    try:
        return settings_review.acknowledge(req.settings)
    except (ValueError, TypeError) as exc:
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
    classification = await classify_current_conditions(latest, bundle["provenance"]["kind"])

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


def attachment(filename: str) -> Dict[str, str]:
    """
    Content-Disposition header for a download. The name is reduced to ASCII letters, digits,
    '.', '_' and '-': names built from request values (an imported file's mission name) could
    carry path separators, quotes, CR/LF (header injection) or characters outside Latin-1,
    which made the export fail with a 500.
    """
    stem, dot, ext = filename.rpartition(".")
    if not dot:
        stem, ext = filename, ""
    clean = re.sub(r"[^A-Za-z0-9_-]+", "_", stem).strip("_.-")[:120] or "helios_export"
    ext = re.sub(r"[^A-Za-z0-9]+", "", ext)[:8]
    return {"Content-Disposition": f'attachment; filename="{clean}.{ext}"' if ext else f'attachment; filename="{clean}"'}


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
        for group, cov in (prov.get("coverage") or {}).get("groups", {}).items():
            meta[f"coverage_{group.replace(' ', '_').lower()}"] = describe_coverage(cov)
        stamp = f"{t0:%Y%m%dT%H%M}_{t1:%Y%m%dT%H%M}"
        return Response(content=DataExporter.to_csv(data, metadata=meta), media_type="text/csv",
                        headers=attachment(f"HELIOS_{key}_archive_{stamp}.csv"))
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

    custom_span = None
    if "CUSTOM" in (key_a, key_b):
        if not latest_custom_dataset or not latest_custom_dataset.get("records"):
            raise HTTPException(status_code=400, detail="No custom dataset imported for comparison.")
        tags = [r["time_tag"] for r in latest_custom_dataset["records"] if r.get("time_tag")]
        custom_span = (_parse_utc(min(tags), "time_tag"), _parse_utc(max(tags), "time_tag"))

    async def side(key):
        """Records, provenance and display name of one side of the comparison."""
        if key == "CUSTOM":
            name = latest_custom_dataset.get("mission_name", "Custom Spacecraft")
            return latest_custom_dataset["records"], {"kind": "imported", "description": f"User-imported file ({name})."}, name
        if key not in MISSIONS:
            raise HTTPException(status_code=400, detail=f"Invalid mission ID '{key}' for comparison.")
        name = MISSIONS[key]["name"]
        # An imported file usually covers an interval in the past, which the live window
        # (the last span_days) never overlaps: take the archive for the file's interval.
        if custom_span and key in ARCHIVE_SOURCES:
            t0, t1 = custom_span
            live_start = datetime.now(timezone.utc) - timedelta(days=span_days)
            if t1 < live_start:
                t0 = max(t0, t1 - timedelta(days=ARCHIVE_MAX_DAYS))
                bundle = await downloader.get_archive_bundle(key, t0, t1 + timedelta(minutes=1))
                return bundle["records"], bundle["provenance"], name
        bundle = await downloader.get_telemetry_bundle(key, span_days=span_days)
        return bundle["records"], bundle["provenance"], name

    (data_a, prov_a, name_a), (data_b, prov_b, name_b) = await asyncio.gather(side(key_a), side(key_b))

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
        position_b=pos_b,
        # An imported file carries no spacecraft position (its name used to be matched to a
        # model orbit, e.g. "my_solar_wind.csv" to WIND, giving a 0 km baseline).
        position_unknown="imported file without spacecraft position" if "CUSTOM" in (key_a, key_b) else ""
    )
    # A correlation between a measured and a simulated series says nothing about the
    # instruments; expose what each side actually is.
    comparison["provenance_a"] = prov_a
    comparison["provenance_b"] = prov_b
    if comparison.get("status") != "success":
        def cover(data):
            tags = [r["time_tag"] for r in data if r.get("time_tag") and r.get(parameter) is not None]
            return f"{min(tags)} to {max(tags)} UTC" if tags else "no values"
        comparison["message"] = (f"Fewer than 5 common minutes with {parameter}: {name_a} has {cover(data_a)}, "
                                 f"{name_b} has {cover(data_b)}.")
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

def recent_dst(obs: List[Dict[str, Any]], max_age_hours: float = 3.0) -> Optional[float]:
    """
    Latest Kyoto Dst if its hour ended less than max_age_hours ago, else None (the model is
    used): a cached copy from days ago used to start the 12 h trajectory as "observed".
    """
    if not obs:
        return None
    end = _parse_utc(obs[-1]["time_tag"], "time_tag") + timedelta(hours=1)
    return obs[-1]["dst"] if datetime.now(timezone.utc) - end < timedelta(hours=max_age_hours) else None


@app.get("/api/forecast/ml")
async def get_ml_forecast(mission_id: str = Query("DSCOVR")):
    mission_key = mission_id.upper()
    if mission_key not in MISSIONS:
        mission_key = "DSCOVR"
    data, kyoto, noaa = await asyncio.gather(downloader.get_satellite_telemetry(mission_key, span_days=1),
                                             downloader.get_kyoto_dst(), downloader.get_noaa_geomag_forecast())
    out = SpaceWeatherForecaster.forecast_geomagnetic_storm(
        data, observed_dst=recent_dst(kyoto["records"]), noaa_forecast=noaa)
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
        # Gaps in the data behind the analysis (native cadence): gaps longer than five
        # sample intervals and at least a minute.
        "coverage": {name: frame_coverage(data.get(name), t0, t1) for name in ("field", "plasma")
                     if data.get(name) is not None},
    }


def _analysis_answer(body: Dict[str, Any], download: bool, name: str):
    """The analysis as JSON, or as a JSON file (results, inputs and provenance) when `download` is set."""
    if not download:
        return body
    return Response(content=json.dumps(body, indent=1, default=str), media_type="application/json",
                    headers=attachment(f"{name}.json"))


async def _run_shock(key: str, tc: datetime, upstream_minutes: float, downstream_minutes: float,
                     exclude_minutes: float, refine: bool, exclude_after_minutes: Optional[float] = None):
    """Fetch native-cadence data around tc and analyse the shock: (data, result, t0, t1)."""
    margin = 12.0  # minutes of context, and room for the refined shock time
    gap_after = exclude_minutes if exclude_after_minutes is None else exclude_after_minutes
    t0 = tc - timedelta(minutes=upstream_minutes + exclude_minutes + margin)
    t1 = tc + timedelta(minutes=downstream_minutes + gap_after + margin)
    data = await downloader.events.fetch(key, t0, t1)
    if data["field"] is None or data["plasma"] is None:
        missing = "magnetic field" if data["field"] is None else "plasma"
        msg = ("The CDAWeb HAPI server could not be reached and nothing is cached for this interval."
               if data["offline"] else f"CDAWeb has no {key} {missing} data for this interval.")
        raise HTTPException(status_code=404, detail=msg)
    try:
        result = await run_in_workers(analyze_shock, data["field"], data["plasma"], tc, upstream_minutes,
                                      downstream_minutes, exclude_minutes, refine, exclude_after_minutes=gap_after)
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
    exclude_after_minutes: Optional[float] = Query(None, ge=0.0, le=15.0, description="Gap after the shock, if "
                                                   "different (IPShocks: 1 min before, 2 min after)"),
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
    data, result, t0, t1 = await _run_shock(key, tc, upstream_minutes, downstream_minutes, exclude_minutes, refine,
                                            exclude_after_minutes)
    params = {"time": tc.strftime("%Y-%m-%d %H:%M:%S"), "upstream_minutes": upstream_minutes,
              "downstream_minutes": downstream_minutes, "exclude_minutes": exclude_minutes,
              "exclude_after_minutes": exclude_after_minutes, "refine": refine}
    prov = _analysis_provenance(key, data, t0, t1, SHOCK_METHOD_TEXT, params)
    cat = await _icme_catalog()
    result["icme_list"] = _icme_disturbance_near(cat["events"], result.get("shock_time"))
    result["icme_catalog"] = _icme_meta(cat)
    result["ipshocks"] = _ipshocks_match(key, result)
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
    exclude_after_minutes: Optional[float] = Query(None, ge=0.0, le=15.0, description="Gap after the shock, if different"),
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
    data, result, t0, t1 = await _run_shock(key, tc, upstream_minutes, downstream_minutes, exclude_minutes, True,
                                            exclude_after_minutes)
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
        # The arrival listed in the IPShocks database at this spacecraft, as an independent observed time.
        t_pred = datetime.strptime(cmp["predicted_time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        listed = shock_catalog.nearest(shock_catalog.load()["events"], name, t_pred, search_minutes)
        entry["ipshocks"] = None if listed is None else {
            "time": listed["time"], "type": listed["type"],
            "minus_predicted_s": round((shock_catalog.event_time(listed) - t_pred).total_seconds()),
            "minus_observed_s": None if not cmp["observed_time"] else round((shock_catalog.event_time(listed) - datetime.strptime(
                cmp["observed_time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)).total_seconds())}
        return entry

    checks = await asyncio.gather(*(one(n) for n in names))
    params = {"time": tc.strftime("%Y-%m-%d %H:%M:%S"), "method": method, "targets": names,
              "upstream_minutes": upstream_minutes, "downstream_minutes": downstream_minutes,
              "exclude_minutes": exclude_minutes, "exclude_after_minutes": exclude_after_minutes,
              "search_minutes": search_minutes}
    prov = _analysis_provenance(key, data, t0, t1, SHOCK_METHOD_TEXT + "; planar-shock timing t = t_ref + n.dr/V_sh",
                                params)
    prov["datasets"] = prov["datasets"] + [dict(d, spacecraft=c["spacecraft"]) for c in checks for d in c["datasets"]]
    body = {
        "provenance": prov,
        "reference": {"spacecraft": key, "shock_time": result["shock_time"], "position_gse_km": r_ref.tolist(),
                      "method": method, "normal_gse": m["normal_gse"], "shock_speed_kms": m["shock_speed_kms"],
                      "shock_type": result["shock_type"], "warnings": result["warnings"]},
        "targets": [{k: v for k, v in c.items() if k != "datasets"} for c in checks],
        "note": ("Residual = observed - predicted delay. Interplanetary shocks are not planar on these scales and the "
                 "single-spacecraft normal has an uncertainty of several degrees: with the normals and speeds of the "
                 "IPShocks database, planar timing between WIND and ACE (219 shocks seen by both, 1998-2021) is off by "
                 "81 s on median for spacecraft less than 50 R_E apart across the Sun-Earth line, 137 s at 50-100 R_E, "
                 "222 s at 100-200 R_E and 581 s further apart. IPShocks: the shock listed at that spacecraft within "
                 "the search window."),
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


@app.get("/api/analysis/mcdetect")
async def detect_clouds(
    mission: str = Query("WIND", description="WIND, ACE, DSCOVR or OMNI"),
    start: str = Query(..., description="UTC start, ISO 8601"),
    end: str = Query(..., description="UTC end (exclusive), ISO 8601"),
    criteria: str = Query("loose", pattern="^(loose|strict)$"),
    download: bool = Query(False, description="Answer as a JSON file with the full provenance"),
):
    """
    Magnetic cloud candidates in 1-minute archive data (Lepping, Wu & Berdichevsky 2005),
    for any interval of up to 31 days. Each accepted region can be passed to
    /api/analysis/fluxrope as its start and end.
    """
    key = mission.upper()
    if key not in ARCHIVE_SOURCES:
        raise HTTPException(status_code=404, detail=f"No archive source for '{mission}'. Available: {', '.join(ARCHIVE_SOURCES)}.")
    t0, t1 = _parse_utc(start, "start"), _parse_utc(end, "end")
    if t1 - t0 < timedelta(hours=8):
        raise HTTPException(status_code=422, detail="The interval must be at least 8 hours long.")
    if t1 - t0 > timedelta(days=ARCHIVE_MAX_DAYS):
        raise HTTPException(status_code=422, detail=f"Intervals are limited to {ARCHIVE_MAX_DAYS} days.")
    res = await downloader.archive.fetch_mission(key, t0, t1)
    frame = res["frame"]
    if frame is None or frame.empty:
        raise HTTPException(status_code=404, detail="The CDAWeb HAPI server could not be reached and nothing is cached "
                            "for this interval." if res["offline"] else f"CDAWeb has no {key} data for this interval.")
    try:
        result = await run_in_workers(detect_magnetic_clouds, frame, criteria)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    # Coverage of the field and of the plasma separately (the merged table hides plasma gaps).
    field_cols = [c for c in frame.columns if c == "bt" or c[:2] in ("bx", "by", "bz")]
    plasma_cols = [c for c in ("speed", "density", "temperature") if c in frame.columns]
    prov = _analysis_provenance(key, {"field": frame[field_cols], "plasma": frame[plasma_cols] if plasma_cols else None,
                                      "datasets": res["datasets"]}, t0, t1, result["method"],
                                {"criteria": criteria, **MC_CRITERIA[criteria]})
    prov["cadence_seconds"] = 60
    cat = await _icme_catalog()
    for c in result["candidates"]:
        c["icme_list"] = _icme_overlaps(cat["events"], c["start"], c["end"])
    result["icme_catalog"] = _icme_meta(cat)
    return _analysis_answer({"provenance": prov, "result": result}, download,
                            f"HELIOS_mc_candidates_{key}_{t0:%Y%m%d}_{t1:%Y%m%d}")


SEA_MAX_EVENTS = 60
SEA_MAX_HOURS = 240
# Total OMNI data one request may fetch (events x window): 60 events of 72 h, or 18 of 240 h.
SEA_MAX_TOTAL_HOURS = 180 * 24


@app.get("/api/analysis/superposed")
async def analyse_superposed_epoch(
    onsets: str = Query("", description="Comma-separated UTC onset times (epoch zero), ISO 8601"),
    parameters: str = Query("sym_h,bz_gsm,speed,dynamic_pressure", description="OMNI quantities to superpose"),
    before_hours: float = Query(12.0, ge=0.0, le=120.0),
    after_hours: float = Query(48.0, gt=0.0, le=240.0),
    cadence_minutes: int = Query(10, ge=1, le=180),
    format: str = Query("json", pattern="^(json|csv)$"),
    download: bool = Query(False, description="Answer as a JSON file with the full provenance"),
    storm_threshold_nt: Optional[float] = Query(None, ge=-2000, le=0, description="Select storms instead of onsets: "
                                                "hourly Dst at or below this value"),
    storm_start_year: int = Query(1995, ge=omni_statistics.FIRST_YEAR, le=2100),
    storm_end_year: int = Query(2024, ge=omni_statistics.FIRST_YEAR, le=2100),
    storm_separation_hours: float = Query(6.0, ge=0, le=240),
    storm_floor_nt: Optional[float] = Query(None, ge=-2000, le=0, description="Keep storms with a minimum above this"),
    storm_driver: str = Query("", max_length=100, description="Xu & Borovsky types of the driver, comma-separated"),
    storm_epoch: str = Query("minimum", pattern="^(minimum|first_below)$"),
):
    """
    Superposed epoch analysis of OMNI 1-min data (SYM-H, AE, solar wind drivers) keyed on
    the given onset times, e.g. storm sudden commencements or shock arrivals, or on storms
    selected by their Dst (storm_threshold_nt and the other storm_* parameters, as in
    /api/statistics/storms), with the selection recorded in the provenance.
    """
    selection = None
    if storm_threshold_nt is not None:
        sel = await _select_storms(storm_start_year, storm_end_year, storm_threshold_nt, storm_separation_hours,
                                   storm_floor_nt, storm_driver)
        key = "minimum_time" if storm_epoch == "minimum" else "first_hour_below"
        onsets = ",".join(st[key].replace(" ", "T") for st in sel["result"]["storms"])
        if not onsets:
            raise HTTPException(status_code=422, detail="No storm matches the selection.")
        selection = {"epoch": "Dst minimum" if storm_epoch == "minimum" else "first hour at or below the threshold",
                     "years": [storm_start_year, storm_end_year], "filters": sel["result"]["log"],
                     "dataset": omni_statistics.OMNI_HOURLY_ID}
    try:
        times = [_parse_utc(s, "onsets") for s in onsets.split(",") if s.strip()]
    except HTTPException:
        raise HTTPException(status_code=422, detail="'onsets' must be comma-separated ISO 8601 UTC times.")
    if not times:
        raise HTTPException(status_code=422, detail="Give at least one onset time.")
    if len(times) > SEA_MAX_EVENTS:
        raise HTTPException(status_code=422, detail=f"At most {SEA_MAX_EVENTS} onsets ({len(times)} given"
                            + ("; narrow the years, lower the threshold or add a floor or driver type)." if selection
                               else ")."))
    if before_hours + after_hours > SEA_MAX_HOURS:
        raise HTTPException(status_code=422, detail=f"The epoch window is limited to {SEA_MAX_HOURS} hours.")
    if len(times) * (before_hours + after_hours) > SEA_MAX_TOTAL_HOURS:
        raise HTTPException(status_code=422, detail=f"Events x window may cover at most {SEA_MAX_TOTAL_HOURS // 24} days "
                                                    f"of data ({len(times)} x {before_hours + after_hours:g} h requested).")
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
    gfz_keys = [p for p in params if p in gfz_indices.INDICES]
    gfz_unread: List[int] = []
    if gfz_keys:  # GFZ Kp / Hp30, held over their intervals minute by minute and merged into the OMNI records
        years: Dict[Tuple[str, int], Optional[pd.Series]] = {}
        for t, b in zip(times, bundles):
            w0, w1 = t - timedelta(hours=before_hours), t + timedelta(hours=after_hours)
            by_time = {r["time_tag"]: r for r in b["records"]}
            for key in gfz_keys:
                for y in range(w0.year, w1.year + 1):
                    if (key, y) not in years:
                        years[(key, y)] = await gfz_indices.year_series(downloader.fetch_text, helios_config.CACHE_DIR, key, y)
                parts = [years[(key, y)] for y in range(w0.year, w1.year + 1) if years[(key, y)] is not None]
                gfz_unread += [y for y in range(w0.year, w1.year + 1) if years[(key, y)] is None]
                if not parts:
                    continue
                for rec in gfz_indices.step_records(pd.concat(parts).sort_index(), key, w0, w1):
                    by_time.setdefault(rec["time_tag"], {"time_tag": rec["time_tag"]})[key] = rec[key]
            b["records"] = sorted(by_time.values(), key=lambda r: r["time_tag"])
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
        "event_selection": selection or "onset times given by the user",
        "geomagnetic_indices": ({**gfz_indices.SOURCE, "held_over_interval": True, "years_unread": sorted(set(gfz_unread))}
                                if gfz_keys else None),
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
        if selection:
            out.write(f"# event selection: {selection['epoch']} of storms in {selection['dataset']} "
                      f"{selection['years'][0]}-{selection['years'][1]}\n")
            for f in selection["filters"]:
                out.write(f"# filter: {f['filter']} -> {f['storms_remaining']} storms\n")
        out.write(f"# software: {prov['software']}\n# retrieved_utc: {prov['retrieved_utc']}\n")
        w = csv.writer(out, lineterminator="\n")
        bands = [k for k in ("mean_ci95_low", "mean_ci95_high", "median_ci95_low", "median_ci95_high")
                 if k in result["statistics"][params[0]]]
        cols = ["epoch_hours"] + [f"{p}_{s}" for p in params for s in ("mean", "median", "q25", "q75", *bands, "n_events")]
        w.writerow(cols)
        for i, e in enumerate(result["epoch_hours"]):
            row = [round(e, 4)]
            for p in params:
                st = result["statistics"][p]
                row += ["" if st[s][i] is None else st[s][i] for s in ("mean", "median", "q25", "q75", *bands)]
                row += [st["n_events"][i]]
            w.writerow(row)
        return Response(content=out.getvalue(), media_type="text/csv",
                        headers=attachment(f"HELIOS_superposed_epoch_{stamp}.csv"))
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


@app.get("/api/analysis/ht")
async def analyse_dehoffmann_teller(
    mission: str = Query("WIND", description="WIND, ACE or DSCOVR"),
    start: str = Query(..., description="UTC start, ISO 8601"),
    end: str = Query(..., description="UTC end (exclusive), ISO 8601"),
    download: bool = Query(False, description="Answer as a JSON file with the full provenance"),
):
    """
    deHoffmann-Teller frame (Khrabrov & Sonnerup 1998) from the plasma velocity and the field
    averaged over each plasma sample, with analytical and bootstrap errors, the normal
    velocity along the minimum variance normal of the same field data, and the Walen test.
    """
    key = _event_mission(mission)
    t0, t1 = _parse_utc(start, "start"), _parse_utc(end, "end")
    if t1 <= t0:
        raise HTTPException(status_code=422, detail="'end' must be after 'start'.")
    if t1 - t0 > timedelta(hours=MAX_EVENT_HOURS):
        raise HTTPException(status_code=422, detail=f"Intervals are limited to {MAX_EVENT_HOURS} hours.")
    data = await downloader.events.fetch(key, t0, t1)
    if data["field"] is None or data["plasma"] is None:
        raise HTTPException(status_code=404, detail="No field or plasma data for this interval"
                            + (" (CDAWeb could not be reached)." if data["offline"] else "."))
    sel = lambda df: df[(df.index >= pd.Timestamp(t0)) & (df.index < pd.Timestamp(t1))]
    field, plasma = sel(data["field"]), sel(data["plasma"]).dropna(subset=["vx", "vy", "vz"])
    if len(plasma) < 4:
        raise HTTPException(status_code=422, detail=f"Only {len(plasma)} plasma samples in the interval; at least 4 are needed.")

    def run():
        b = field_at_plasma_times(field, plasma)
        mva = minimum_variance(field[["bx", "by", "bz"]].to_numpy(), n_bootstrap=0)
        ht = dehoffmann_teller(b, plasma[["vx", "vy", "vz"]].to_numpy(float), plasma["n"].to_numpy(float),
                               normal=mva["eigenvectors"]["min"], n_bootstrap=1000)
        ht["normal_used"] = {"vector_gse": mva["eigenvectors"]["min"],
                             "source": "minimum variance normal of the field in the same interval",
                             "ratio_intermediate_to_min": mva["ratio_intermediate_to_min"]}
        return ht

    try:
        result = await run_in_workers(run)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    prov = _analysis_provenance(key, data, t0, t1, result["method"], {})
    return _analysis_answer({"provenance": prov, "result": result}, download, f"HELIOS_ht_{key}_{t0:%Y%m%dT%H%M}")


@app.get("/api/analysis/coupling")
async def analyse_coupling(
    mission: str = Query("WIND", description="WIND, ACE or DSCOVR"),
    start: str = Query(..., description="UTC start, ISO 8601"),
    end: str = Query(..., description="UTC end (exclusive), ISO 8601"),
    download: bool = Query(False, description="Answer as a JSON file with the full provenance"),
):
    """
    Solar wind-magnetosphere coupling functions (Newell dPhi/dt, Akasofu epsilon, V Bs,
    dynamic pressure) on every plasma sample of an interval of up to 72 h, with 1-sigma
    errors propagated from the archive's speed and density uncertainties (WIND SWE) and the
    sampling interval of each mean.
    """
    key = _event_mission(mission)
    t0, t1 = _parse_utc(start, "start"), _parse_utc(end, "end")
    if t1 <= t0:
        raise HTTPException(status_code=422, detail="'end' must be after 'start'.")
    if t1 - t0 > timedelta(hours=MAX_EVENT_HOURS):
        raise HTTPException(status_code=422, detail=f"Intervals are limited to {MAX_EVENT_HOURS} hours.")
    data = await downloader.events.fetch(key, t0, t1, coarse=True)
    if data["field"] is None or data["plasma"] is None:
        raise HTTPException(status_code=404, detail="No field or plasma data for this interval"
                            + (" (CDAWeb could not be reached)." if data["offline"] else "."))
    sel = lambda df: df[(df.index >= pd.Timestamp(t0)) & (df.index < pd.Timestamp(t1))]
    try:
        result = await run_in_workers(coupling_with_errors, sel(data["field"]), sel(data["plasma"]))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    prov = _analysis_provenance(key, data, t0, t1, result["method"], {})
    prov["coordinates"] = "GSM (field rotated from GSE per sample)"
    return _analysis_answer({"provenance": prov, "result": result}, download, f"HELIOS_coupling_{key}_{t0:%Y%m%dT%H%M}")


@app.get("/api/analysis/timeshift")
async def analyse_timeshift(
    mission: str = Query("WIND", description="WIND, ACE or DSCOVR"),
    start: str = Query(..., description="UTC start of the arrival times at the bow shock nose, ISO 8601"),
    end: str = Query(..., description="UTC end (exclusive) of the arrival times"),
    format: str = Query("json", pattern="^(json|csv)$"),
    download: bool = Query(False, description="Answer as a JSON file with the full provenance"),
):
    """
    Upstream field and plasma shifted to the Earth's bow shock nose as NASA's High Resolution
    OMNI does it (phase front normals by cross products or MVAB-0, Farris & Russell bow shock),
    for arrival times over up to 48 h, with the flat (dX/Vx) delay and, for WIND and ACE, the
    agreement with OMNI's own time shifts in the minutes OMNI took from the same spacecraft.
    """
    key = _event_mission(mission)
    t0, t1 = _parse_utc(start, "start"), _parse_utc(end, "end")
    if t1 <= t0:
        raise HTTPException(status_code=422, detail="'end' must be after 'start'.")
    if t1 - t0 > timedelta(hours=timeshift.MAX_SHIFT_HOURS):
        raise HTTPException(status_code=422, detail=f"Arrival intervals are limited to {timeshift.MAX_SHIFT_HOURS} hours.")
    obs0 = t0 - timedelta(hours=timeshift.MAX_DELAY_HOURS)
    data = await downloader.events.fetch(key, obs0, t1)
    field, plasma, position = data["field"], data["plasma"], data["position"]
    datasets = list(data["datasets"])
    if key == "WIND":
        # OMNI shifts WIND with the SWE key parameters, cleaned as in its appendix 3.
        kp, rec, _, _ = await downloader.events.fetch_dataset(timeshift.WIND_KP_PLASMA, obs0, t1, "plasma")
        datasets = [d for d in datasets if d["role"] != "plasma"] + ([rec] if rec else [])
        plasma = timeshift.despike_plasma(kp) if kp is not None else None
        field = timeshift.wind_field_limit(field) if field is not None else None
    missing = [name for name, v in (("magnetic field", field), ("plasma", plasma), ("position", position)) if v is None]
    if missing:
        raise HTTPException(status_code=404, detail=f"No {key} {' or '.join(missing)} data for this interval"
                            + (" (CDAWeb could not be reached)." if data["offline"] else "."))
    try:
        res = await run_in_workers(timeshift.shift_to_bow_shock, field, plasma, position, t0, t1)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    minutes = res["minutes"]
    if minutes.empty:
        raise HTTPException(status_code=422, detail="No vector could be shifted into this interval (data gaps, "
                            "or no plasma velocity within an hour of the field).")
    comparison, omni = None, None
    if key in timeshift.OMNI_IDS:
        om, rec, _, _ = await downloader.events.fetch_dataset(timeshift.OMNI_SHIFTS, t0, t1, "comparison")
        if om is not None:
            omni = om[om["IMF"] == timeshift.OMNI_IDS[key]][["Timeshift"]]
            omni.index = omni.index.floor("min")
            comparison = timeshift.compare_with_omni(minutes, omni)
            datasets.append(rec)
        note = (None if comparison else
                f"OMNI HRO took no minute of this interval from {key}, or has no data for it yet." if om is not None
                else "OMNI HRO could not be read for this interval.")
    else:
        note = (f"{key} is not among the spacecraft High Resolution OMNI is built from, so there is no OMNI "
                "shift to compare with.")
    delays = minutes["delay_s"].dropna() / 60.0
    lag = timedelta(minutes=float(delays.median()))
    prov = _analysis_provenance(key, {"field": field, "plasma": plasma, "datasets": datasets}, t0 - lag, t1 - lag,
                                timeshift.METHOD, {"arrival_start": t0.strftime("%Y-%m-%d %H:%M:%S"),
                                                   "arrival_end": t1.strftime("%Y-%m-%d %H:%M:%S"),
                                                   "aberration_vy_kms": timeshift.ORBITAL_VY_KMS})
    prov["time_convention"] = "arrival time at the bow shock nose (start of each minute), as in OMNI"
    n_src = res["normal_sources"]
    shifted = sum(n_src[k] for k in ("cross_product", "mvab0", "interpolated"))
    summary = {
        "minutes": int(len(minutes)), "vectors": res["vectors"], "cadence_s": round(res["cadence_s"], 1),
        "delay_median_min": round(float(delays.median()), 1),
        "delay_range_min": [round(float(delays.quantile(0.1)), 1), round(float(delays.quantile(0.9)), 1)],
        "flat_delay_median_min": round(float(minutes["flat_delay_s"].dropna().median() / 60.0), 1),
        "bow_shock_nose_x_re": round(float(minutes["bsn_x"].median()), 2),
        "normals_percent": {k: round(100.0 * n_src[k] / shifted, 1) if shifted else None
                            for k in ("cross_product", "mvab0", "interpolated")},
        "vectors_not_shifted": n_src["not_shifted"],
    }
    omni_col = omni["Timeshift"].reindex(minutes.index) if omni is not None else None
    stamp = f"HELIOS_timeshift_{key}_{t0:%Y%m%dT%H%M}"
    if format == "csv":
        out = io.StringIO()
        out.write(f"# title: HELIOS-L1 {key} data shifted to the bow shock nose\n# method: {timeshift.METHOD}\n")
        out.write("# time: arrival at the bow shock nose (UTC, start of the minute); delays in seconds\n")
        out.write(f"# datasets: {', '.join(d['id'] for d in datasets)}\n")
        if comparison:
            pf = comparison["phase_front"]
            out.write(f"# OMNI comparison: {pf['minutes']} minutes from {key}, median difference "
                      f"{pf['median_difference_min']} min, {pf['within_1_min_percent']} % within 1 min\n")
        out.write(f"# software: {prov['software']}\n# retrieved_utc: {prov['retrieved_utc']}\n")
        cols = ["delay_s", "delay_rms_s", "flat_delay_s", "bsn_x", "bsn_y", "bsn_z", "bx", "by", "bz", "by_gsm",
                "bz_gsm", "speed", "vx", "vy", "vz", "density", "temperature", "points", "cross_product", "mvab0",
                "interpolated"]
        cols = [c for c in cols if c in minutes]
        w = csv.writer(out, lineterminator="\n")
        w.writerow(["time"] + cols + (["omni_timeshift_s"] if omni_col is not None else []))
        for t, row in minutes[cols].iterrows():
            vals = ["" if not np.isfinite(v) else round(float(v), 3) for v in row.to_numpy(dtype=float)]
            if omni_col is not None:
                o = omni_col.get(t)
                vals.append("" if o is None or not np.isfinite(o) else int(o))
            w.writerow([t.strftime("%Y-%m-%d %H:%M")] + vals)
        return Response(content=out.getvalue(), media_type="text/csv", headers=attachment(f"{stamp}.csv"))

    def col(name, scale=1.0, digits=2):
        if name not in minutes:
            return [None] * len(minutes)
        return [None if not np.isfinite(v) else round(float(v) * scale, digits)
                for v in minutes[name].to_numpy(dtype=float)]

    series = {"time_tags": [t.strftime("%Y-%m-%d %H:%M") for t in minutes.index],
              "delay_min": col("delay_s", 1 / 60), "delay_rms_min": col("delay_rms_s", 1 / 60),
              "flat_delay_min": col("flat_delay_s", 1 / 60), "bsn_x_re": col("bsn_x"),
              "bz_gsm": col("bz_gsm"), "speed": col("speed", 1.0, 1), "density": col("density")}
    if omni_col is not None:
        series["omni_delay_min"] = [None if not np.isfinite(v) else round(float(v) / 60, 2)
                                    for v in omni_col.to_numpy(dtype=float)]
    result = {"method": timeshift.METHOD, "summary": summary, "omni_comparison": comparison, "omni_note": note}
    return _analysis_answer({"provenance": prov, "result": result, "series": series}, download, stamp)


SC_MAX_DAYS = 366
SC_WINDOW_MIN = (-60, 90)  # minutes around each onset drawn in the panel


def _month_starts(a: datetime, b: datetime) -> List[datetime]:
    """Starts of the calendar months from a's month to the month after b's (bounds of whole-month requests)."""
    out, t = [], datetime(a.year, a.month, 1, tzinfo=timezone.utc)
    while t <= b:
        out.append(t)
        t = datetime(t.year + (t.month == 12), t.month % 12 + 1, 1, tzinfo=timezone.utc)
    return out + [t]


@app.get("/api/analysis/sudden_commencements")
async def analyse_sudden_commencements(
    start: str = Query(..., description="UTC start, ISO 8601"),
    end: str = Query(..., description=f"UTC end (exclusive), at most {SC_MAX_DAYS} days after the start"),
    format: str = Query("json", pattern="^(json|csv)$"),
    download: bool = Query(False, description="Answer as a JSON file with the full provenance"),
):
    """
    Sudden commencements in OMNI 1-min SYM-H (a quiet record before, a persistent step and a
    jump of the solar wind pressure; helios.core.sudden_commencement), compared with the lists
    of the International Service on Rapid Magnetic Variations (Observatori de l'Ebre, for ISGI).
    """
    t0, t1 = _parse_utc(start, "start"), _parse_utc(end, "end")
    if t1 <= t0:
        raise HTTPException(status_code=422, detail="'end' must be after 'start'.")
    if t1 - t0 > timedelta(days=SC_MAX_DAYS):
        raise HTTPException(status_code=422, detail=f"Intervals are limited to {SC_MAX_DAYS} days.")
    a, b = t0 - timedelta(minutes=sc.MARGIN_BEFORE_MIN), t1 + timedelta(minutes=sc.MARGIN_AFTER_MIN)
    months = _month_starts(a, b)
    sem = asyncio.Semaphore(3)

    async def month(m0, m1):  # whole months, so the cached requests serve any interval
        async with sem:
            return await downloader.events.fetch_dataset(sc.OMNI_SPEC, m0, m1, "indices")

    got = await asyncio.gather(*(month(m0, m1) for m0, m1 in zip(months[:-1], months[1:])))
    frames = [f for f, _, _, _ in got if f is not None]
    data = pd.concat(frames).sort_index() if frames else pd.DataFrame(columns=["sym_h", "pressure"], dtype=float)
    data = data[~data.index.duplicated()]
    data = data[(data.index >= a) & (data.index < b)]
    if not data["sym_h"].notna().any():
        offline = not any(reached for _, _, reached, _ in got)
        raise HTTPException(status_code=404, detail="No OMNI SYM-H for this interval"
                            + (" (CDAWeb could not be reached)." if offline else "."))
    events = await run_in_workers(sc.detect, data["sym_h"], data["pressure"])
    events = events[(events["time"] >= t0) & (events["time"] < t1)].reset_index(drop=True)
    years = range(t0.year, (t1 - timedelta(microseconds=1)).year + 1)
    ebre = await sc.load_ebre(downloader.fetch_text, helios_config.CACHE_DIR, years)
    tol = timedelta(minutes=sc.MATCH_TOLERANCE_MIN)
    near = [e for e in ebre["events"] if t0 - tol <= e["time"] < t1 + tol]
    matches, missed = sc.cross_match(events, near)
    missed = [e for e in missed if t0 <= e["time"] < t1]
    listed = [e for e in near if t0 <= e["time"] < t1 and not e["type"].endswith("-")]
    found = len(listed) - len(missed)
    comparison = {
        "listed": len(listed), "found": found, "detections": int(len(events)),
        "not_listed": sum(m is None for m in matches),
        "years": {str(y): k for y, k in ebre["years"].items()},
        "years_unread": [y for y, k in ebre["years"].items() if k is None],
        "tolerance_minutes": sc.MATCH_TOLERANCE_MIN,
    }
    sym, prs = data["sym_h"], data["pressure"]

    def num(v, d=2):
        return None if v is None or not np.isfinite(v) else round(float(v), d)

    def window(t):
        idx = pd.date_range(t + timedelta(minutes=SC_WINDOW_MIN[0]), t + timedelta(minutes=SC_WINDOW_MIN[1]), freq="min")
        return {"sym_h": [num(v, 0) for v in sym.reindex(idx).to_numpy(dtype=float)],
                "pressure": [num(v) for v in prs.reindex(idx).to_numpy(dtype=float)]}

    rows = []
    for (_, e), m in zip(events.iterrows(), matches):
        t = e["time"].to_pydatetime()
        rows.append({"time": t.strftime("%Y-%m-%d %H:%M"), "detected": True, "amplitude_nt": num(e["amplitude_nt"], 0),
                     "rise_minutes": int(e["rise_minutes"]), "max_step_nt": num(e["max_step_nt"], 0),
                     "symh_nt": num(e["symh_nt"], 0), "quiet_nt": num(e["quiet_nt"]), "persistence": num(e["persistence"]),
                     "pressure_before_npa": num(e["pressure_before_npa"]), "pressure_after_npa": num(e["pressure_after_npa"]),
                     "pressure_ratio": num(e["pressure_ratio"]), "pressure_jump": e["pressure_jump"], "listed": m,
                     "window": window(t)})
    for e in missed:
        t = e["time"].to_pydatetime()
        rows.append({"time": t.strftime("%Y-%m-%d %H:%M"), "detected": False,
                     "listed": {"time": t.strftime("%Y-%m-%d %H:%M:%S"), "type": e["type"],
                                "amplitude_nt": e["amplitude_nt"], "offset_minutes": None},
                     "window": window(t.replace(second=0))})
    rows.sort(key=lambda r: r["time"])
    shocks = shock_catalog.load()["events"]
    for r in rows:  # the fast forward shock at L1 (IPShocks) whose planar arrival is within 15 min
        t = datetime.strptime((r["listed"] or {}).get("time") if not r["detected"] else r["time"] + ":00",
                              "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        e = shock_catalog.driver_of(shocks, t)
        a = shock_catalog.planar_arrival(e) if e else None
        r["l1_shock"] = None if e is None else {
            "time": e["time"], "spacecraft": e["spacecraft"], "shock_speed_kms": e["shock_speed_kms"],
            "predicted_arrival": a.strftime("%Y-%m-%d %H:%M:%S"),
            "onset_minus_predicted_minutes": round((t - a).total_seconds() / 60.0, 1)}
    # The strongest half-hourly activity (GFZ Hp30) over the 24 h from each onset.
    hp_years = {y: await gfz_indices.year_series(downloader.fetch_text, helios_config.CACHE_DIR, "hp30", y)
                for y in range(t0.year, (t1 + timedelta(hours=24)).year + 1)}
    hp = [s for s in hp_years.values() if s is not None]
    hp = pd.concat(hp).sort_index() if hp else None
    for r in rows:
        t = pd.Timestamp((r["listed"] or {}).get("time") if not r["detected"] else r["time"], tz="UTC")
        w = hp[(hp.index + pd.Timedelta(minutes=30) > t) & (hp.index < t + pd.Timedelta(hours=24))] if hp is not None else []
        r["hp30_max_24h"] = None if len(w) == 0 else {"value": float(w.max()), "interval_start": w.idxmax().strftime("%Y-%m-%d %H:%M")}
    comparison["hp30_years_unread"] = [y for y, s in hp_years.items() if s is None]
    comparison["with_l1_shock"] = sum(1 for r in rows if r["detected"] and r["l1_shock"])
    comparison["l1_shock_list"] = {**_ipshocks_meta(), "last_shock": shocks[-1]["time"],
                                   "window_minutes": shock_catalog.DRIVER_MINUTES}
    prov = {
        "kind": "observed", "archive": HAPI_SERVER, "datasets": [r for _, r, _, _ in got if r],
        "requested_start": t0.strftime("%Y-%m-%d %H:%M:%S"), "requested_end": t1.strftime("%Y-%m-%d %H:%M:%S"),
        "time_standard": "UTC, start of each minute", "method": sc.METHOD,
        "parameters": {"rise_nt": sc.MIN_RISE_NT, "rise_window_min": sc.RISE_WINDOW_MIN, "max_step_nt": sc.MIN_MAX_STEP_NT,
                       "quiet_nt": sc.MAX_QUIET_NT, "quiet_step_ratio": sc.QUIET_STEP_RATIO,
                       "persistence": sc.MIN_PERSISTENCE, "pressure_ratio": sc.MIN_PRESSURE_RATIO},
        "reference_list": {**sc.EBRE_SOURCE, "files": [sc.EBRE_URL.format(year=y, kind=k[0])
                                                       for y, k in ebre["years"].items() if k]},
        "software": f"HELIOS-L1 {__version__}",
        "retrieved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "coverage": {"sym_h": frame_coverage(data[["sym_h"]].dropna(), t0, t1),
                     "pressure": frame_coverage(data[["pressure"]].dropna(), t0, t1)},
    }
    stamp = f"HELIOS_sudden_commencements_{t0:%Y%m%d}_{t1:%Y%m%d}"
    if format == "csv":
        out = io.StringIO()
        out.write(f"# title: HELIOS-L1 sudden commencements in OMNI SYM-H, {prov['requested_start']} to "
                  f"{prov['requested_end']} UTC\n# method: {sc.METHOD}\n")
        out.write(f"# reference list: {sc.EBRE_SOURCE['name']}, {sc.EBRE_SOURCE['url']} ({sc.EBRE_SOURCE['licence']}); "
                  f"{found} of {len(listed)} listed SCs found, {comparison['not_listed']} of {len(events)} detections "
                  f"not listed (onsets within {sc.MATCH_TOLERANCE_MIN:g} min)\n")
        out.write(f"# datasets: OMNI_HRO_1MIN (Pressure, SYM_H)\n# software: {prov['software']}\n"
                  f"# retrieved_utc: {prov['retrieved_utc']}\n")
        cols = ["amplitude_nt", "rise_minutes", "max_step_nt", "symh_nt", "quiet_nt", "persistence",
                "pressure_before_npa", "pressure_after_npa", "pressure_ratio"]
        w = csv.writer(out, lineterminator="\n")
        w.writerow(["onset", "detected"] + cols + ["listed_time", "listed_type", "listed_amplitude_nt", "offset_minutes",
                                                   "l1_shock_time", "l1_spacecraft", "l1_shock_speed_kms",
                                                   "onset_minus_predicted_minutes", "hp30_max_24h", "hp30_max_interval_start"])
        for r in rows:
            lst, l1, h = r["listed"] or {}, r["l1_shock"] or {}, r["hp30_max_24h"] or {}
            w.writerow([r["time"], int(r["detected"])] + ["" if r.get(c) is None else r[c] for c in cols]
                       + [lst.get("time", ""), lst.get("type", ""), lst.get("amplitude_nt", ""),
                          "" if lst.get("offset_minutes") is None else lst["offset_minutes"]]
                       + [l1.get(k, "") for k in ("time", "spacecraft", "shock_speed_kms", "onset_minus_predicted_minutes")]
                       + [h.get("value", ""), h.get("interval_start", "")])
        return Response(content=out.getvalue(), media_type="text/csv", headers=attachment(f"{stamp}.csv"))
    cadence = 1 if t1 - t0 <= timedelta(days=31) else 10
    s = sym[(sym.index >= t0) & (sym.index < t1)]
    if cadence > 1:
        s = s.resample(f"{cadence}min").mean()
    series = {"cadence_minutes": cadence, "time_tags": [t.strftime("%Y-%m-%d %H:%M") for t in s.index],
              "sym_h": [num(v, 1) for v in s.to_numpy(dtype=float)],
              "window_minutes": list(range(SC_WINDOW_MIN[0], SC_WINDOW_MIN[1] + 1))}
    result = {"method": sc.METHOD, "events": rows, "comparison": comparison, "validation": sc.VALIDATION}
    return _analysis_answer({"provenance": prov, "result": result, "series": series}, download, stamp)


def _omni_filters(where: str, bz_south_hours: int, bz_north_hours: int, sw_type: str,
                  min_imf_points: int, min_plasma_points: int) -> Dict[str, Any]:
    """Filter arguments of omni_statistics.apply_filters from query values (422 on bad input)."""
    try:
        conditions = omni_statistics.parse_conditions(where)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    types = [t.strip().lower() for t in sw_type.split(",") if t.strip()]
    bad = [t for t in types if t not in omni_statistics.SW_TYPES.values()]
    if bad:
        raise HTTPException(status_code=422, detail=f"Unknown solar wind type(s) {', '.join(bad)}; available: "
                                                    f"{', '.join(omni_statistics.SW_TYPES.values())}.")
    return {"conditions": conditions, "bz_south_min_hours": bz_south_hours, "bz_north_min_hours": bz_north_hours,
            "sw_types": types, "min_imf_points": min_imf_points, "min_plasma_points": min_plasma_points}


async def _omni_hourly_frame(y0: int, y1: int) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Hourly OMNI for whole years y0..y1 and the provenance of the requests."""
    sem = asyncio.Semaphore(4)

    async def one(y):
        async with sem:
            return await downloader.omni_hourly.year(y)

    got = await asyncio.gather(*(one(y) for y in range(y0, y1 + 1)))
    frames = [f for f, _ in got if f is not None]
    missing = [y for y, (f, _) in zip(range(y0, y1 + 1), got) if f is None]
    prov = {
        "kind": "observed" if frames else "unavailable",
        "archive": HAPI_SERVER,
        "dataset": omni_statistics.OMNI_HOURLY_ID,
        "label": "OMNI hourly merged solar wind (NASA OMNIWeb), field and plasma shifted to the bow shock nose; "
                 "Dst, AE, AL, AU from WDC Kyoto; Kp from GFZ; sunspot number from SILSO",
        "hapi_urls": [downloader.omni_hourly.url(y) for y in range(y0, y1 + 1)],
        "years": [y0, y1],
        "years_without_data": missing,
        "years_not_refreshed": [y for y, (_, off) in zip(range(y0, y1 + 1), got) if off],
        "time_standard": "UTC, time stamps at the start of each hourly average",
    }
    return (pd.concat(frames).sort_index() if frames else pd.DataFrame()), prov


@app.get("/api/statistics/omni")
async def omni_statistics_endpoint(
    start_year: int = Query(1995, ge=omni_statistics.FIRST_YEAR, le=2100),
    end_year: int = Query(2025, ge=omni_statistics.FIRST_YEAR, le=2100),
    analysis: str = Query("distribution", description="distribution, joint, conditional, correlation or cycle"),
    x: str = Query("speed", description="Quantity (see /api/statistics/omni/quantities)"),
    y: Optional[str] = Query(None, description="Second quantity for joint, conditional and correlation"),
    bins: int = Query(30, ge=3, le=200),
    log_x: bool = Query(False),
    log_y: bool = Query(False),
    resolution: str = Query("year", pattern="^(year|month)$"),
    min_count: int = Query(10, ge=1, le=10000, description="Fewest hours for a conditional-average bin"),
    where: str = Query("", max_length=500, description="Conditions such as 'speed>500; beta<1; dst<=-50'"),
    bz_south_hours: int = Query(0, ge=0, le=240, description="Keep hours inside runs of Bz<0 lasting this long"),
    bz_north_hours: int = Query(0, ge=0, le=240, description="Keep hours inside runs of Bz>0 lasting this long"),
    sw_type: str = Query("", max_length=100, description="Xu & Borovsky (2015) types, comma-separated"),
    min_imf_points: int = Query(0, ge=0, le=1000, description="Fewest fine-scale field points in the hour"),
    min_plasma_points: int = Query(0, ge=0, le=1000, description="Fewest fine-scale plasma points in the hour"),
    format: str = Query("json", pattern="^(json|csv)$"),
    download: bool = Query(False, description="Answer as a JSON file with the full provenance"),
):
    """
    Statistics of hourly OMNI data (1963 to the present): distributions, joint histograms,
    conditional averages, correlations and yearly or monthly statistics against the
    sunspot number, after regime, quality and storm filters. Every filter and the hours it
    kept are part of the answer and of the CSV export.
    """
    if end_year < start_year:
        raise HTTPException(status_code=422, detail="'end_year' must not be before 'start_year'.")
    if end_year - start_year + 1 > omni_statistics.MAX_YEARS:
        raise HTTPException(status_code=422, detail=f"At most {omni_statistics.MAX_YEARS} years per request.")
    filters = _omni_filters(where, bz_south_hours, bz_north_hours, sw_type, min_imf_points, min_plasma_points)
    x, y = x.strip().lower(), (y.strip().lower() if y else None)
    df, prov = await _omni_hourly_frame(start_year, end_year)
    if df.empty:
        raise HTTPException(status_code=404, detail="No OMNI hourly data for these years"
                            + (" (CDAWeb could not be reached and nothing is cached)." if prov["years_not_refreshed"] else "."))
    try:
        result = await run_in_workers(omni_statistics.run_analysis, df, analysis, x, y, filters, bins, log_x, log_y,
                                      resolution, min_count)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    prov.update({
        "method": result["method"],
        "parameters": {"analysis": analysis, "x": x, "y": y, "bins": bins, "log_x": log_x, "log_y": log_y,
                       "resolution": resolution, "min_count": min_count},
        "filters": result["filters"],
        "software": f"HELIOS-L1 {__version__}",
        "retrieved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
    })
    stamp = f"HELIOS_omni_{analysis}_{x}{'_' + y if y else ''}_{start_year}_{end_year}"
    if format == "csv":
        header, rows = omni_statistics.to_csv_rows(result)
        out = io.StringIO()
        out.write(f"# title: HELIOS-L1 OMNI hourly statistics ({analysis} of {x}{' and ' + y if y else ''}, "
                  f"{start_year}-{end_year})\n")
        out.write(f"# dataset: {prov['dataset']} ({HAPI_SERVER})\n")
        for f in result["filters"]:
            out.write(f"# filter: {f['filter']} -> {f['hours_remaining']} hours\n")
        out.write(f"# method: {result['method']}\n# software: {prov['software']}\n# retrieved_utc: {prov['retrieved_utc']}\n")
        w = csv.writer(out, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
        return Response(content=out.getvalue(), media_type="text/csv", headers=attachment(f"{stamp}.csv"))
    return _analysis_answer({"provenance": prov, "result": result}, download, stamp)


async def _select_storms(y0: int, y1: int, threshold: float, separation: float, floor: Optional[float],
                         driver: str) -> Dict[str, Any]:
    if y1 < y0 or y1 - y0 + 1 > omni_statistics.MAX_YEARS:
        raise HTTPException(status_code=422, detail=f"Give 1 to {omni_statistics.MAX_YEARS} years, start before end.")
    drivers = [t.strip().lower() for t in driver.split(",") if t.strip()]
    bad = [t for t in drivers if t not in omni_statistics.SW_TYPES.values()]
    if bad:
        raise HTTPException(status_code=422, detail=f"Unknown solar wind type(s) {', '.join(bad)}.")
    if floor is not None and floor >= threshold:
        raise HTTPException(status_code=422, detail="'floor' must be below the threshold.")
    df, prov = await _omni_hourly_frame(y0, y1)
    if df.empty:
        raise HTTPException(status_code=404, detail="No OMNI hourly data for these years.")
    result = await run_in_workers(omni_statistics.find_storms, df, threshold, separation, floor, drivers)
    cat = await _icme_catalog()
    counts = icme_catalog.annotate_storms(result["storms"], cat["events"])
    result["icme_catalog"] = {**_icme_meta(cat), "after_hours": icme_catalog.DEFAULT_AFTER_HOURS, "counts": counts,
                              "method": "Dst minimum (middle of its hour) in the sheath (disturbance to ICME start), "
                                        f"the ICME, or the {icme_catalog.DEFAULT_AFTER_HOURS:g} h after its end"}
    prov.update({"method": "Runs of hourly Dst at or below the threshold, joined across shorter recoveries "
                           "(helios.core.omni_statistics.find_storms)",
                 "parameters": {"threshold_nt": threshold, "separation_hours": separation, "floor_nt": floor,
                                "drivers": drivers},
                 "software": f"HELIOS-L1 {__version__}",
                 "retrieved_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")})
    return {"provenance": prov, "result": result}


# ----------------------------------------------------------------------------
# Richardson & Cane list of near-Earth ICMEs (helios.core.icme_catalog)
# ----------------------------------------------------------------------------
async def _icme_catalog() -> Dict[str, Any]:
    """The list: the live page (cached for a week) or the bundled snapshot when it cannot be read."""
    return await run_in_workers(icme_catalog.load, helios_config.CACHE_DIR, True)


def _icme_meta(cat: Dict[str, Any]) -> Dict[str, Any]:
    return {"name": "Richardson & Cane list of near-Earth ICMEs since 1996", "origin": cat.get("origin"),
            "revision": cat.get("revision"), "source": cat.get("source"), "doi": cat.get("doi"),
            "licence": cat.get("licence"), "citation": cat.get("citation")}


def _icme_overlaps(events: List[Dict[str, Any]], start: str, end: str) -> List[Dict[str, Any]]:
    """Listed ICMEs overlapping [start, end] with the fraction of the interval inside the ICME body."""
    a = datetime.strptime(start, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    b = datetime.strptime(end, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    out = []
    for e in icme_catalog.events_between(events, a, b):
        s, en = icme_catalog._dt(e["icme_start"]), icme_catalog._dt(e["icme_end"])
        inside = max(0.0, (min(b, en) - max(a, s)).total_seconds())
        out.append({**icme_catalog.summary(e),
                    "fraction_inside_icme": round(inside / max(1.0, (b - a).total_seconds()), 2)})
    return out


def _icme_disturbance_near(events: List[Dict[str, Any]], shock_time: Optional[str]) -> Optional[Dict[str, Any]]:
    """
    The listed disturbance (usually the sudden commencement at Earth) 1 h before to 3 h
    after a shock seen at L1, where the shock-driven disturbance is expected, nearest first.
    """
    if not shock_time:
        return None
    t = datetime.strptime(shock_time[:16], "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc)
    best = None
    for e in events:
        d = icme_catalog._dt(e["disturbance"])
        dt_min = (d - t).total_seconds() / 60.0
        if -60.0 <= dt_min <= 180.0 and (best is None or abs(dt_min) < abs(best["delay_minutes"])):
            best = {**icme_catalog.summary(e), "disturbance_source": e["disturbance_source"],
                    "delay_minutes": round(dt_min, 1)}
    return best


@app.get("/api/catalogs/icme")
async def icme_list(
    start: str = Query("1996-01-01", description="UTC start, ISO 8601"),
    end: str = Query("2100-01-01", description="UTC end, ISO 8601"),
    format: str = Query("json", pattern="^(json|csv)$"),
):
    """
    The Richardson & Cane list of near-Earth ICMEs (disturbance, ICME start and end,
    magnetic cloud, shock, Dst ...) overlapping an interval, with its source, revision,
    DOI and licence (CC0).
    """
    t0, t1 = _parse_utc(start, "start"), _parse_utc(end, "end")
    if t1 <= t0:
        raise HTTPException(status_code=422, detail="'end' must be after 'start'.")
    cat = await _icme_catalog()
    events = icme_catalog.events_between(cat["events"], t0, t1)
    meta = _icme_meta(cat)
    if format == "csv":
        cols = ["disturbance", "disturbance_source", "icme_start", "icme_end", "quality", "weak_signatures",
                "speed_jump_kms", "fast_forward_shock", "v_icme_kms", "v_max_kms", "b_mean_nt", "magnetic_cloud",
                "dst_min_nt", "dst_kind", "v_transit_kms", "cme"]
        out = io.StringIO()
        for k in ("name", "source", "doi", "licence", "revision", "origin", "citation"):
            out.write(f"# {k}: {meta[k]}\n")
        w = csv.writer(out, lineterminator="\n")
        w.writerow(cols)
        for e in events:
            w.writerow(["" if e.get(c) is None else e.get(c) for c in cols])
        return Response(content=out.getvalue(), media_type="text/csv",
                        headers=attachment(f"HELIOS_ICME_list_{t0:%Y%m%d}_{t1:%Y%m%d}.csv"))
    return {"catalog": meta, "count": len(events), "events": events}


# IPShocks database, shocks at L1 (helios.core.shock_catalog)
def _ipshocks_meta() -> Dict[str, Any]:
    cat = shock_catalog.load()
    return {"name": "IPShocks database (University of Helsinki): shocks at WIND, ACE and DSCOVR", "version": cat["version"],
            "source": cat["source"], "doi": cat["doi"], "licence": cat["licence"], "citation": cat["citation"],
            "windows_minutes": cat["windows_minutes"]}


def _ipshocks_match(key: str, result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """The listed shock at the same spacecraft within 5 min of the analysed one, and its normal against ours."""
    t = datetime.strptime(result["shock_time"], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    e = shock_catalog.nearest(shock_catalog.load()["events"], key, t)
    if e is None:
        return None
    ours = result["methods"].get(result.get("preferred_method")) or {}
    angle = shock_catalog.angle_deg(ours["normal_gse"], e["normal_gse"]) if ours.get("normal_gse") else None
    return {**e, "offset_seconds": round((shock_catalog.event_time(e) - t).total_seconds()),
            "normal_angle_deg": None if angle is None else round(angle, 1), "catalog": _ipshocks_meta()}


@app.get("/api/catalogs/shocks")
async def shock_list(
    start: str = Query("1994-01-01", description="UTC start, ISO 8601"),
    end: str = Query("2100-01-01", description="UTC end, ISO 8601"),
    spacecraft: str = Query("", description="WIND, ACE or DSCOVR; empty for all"),
    format: str = Query("json", pattern="^(json|csv)$"),
):
    """Interplanetary shocks at L1 in the IPShocks database (normal, theta_Bn, speed, Mach numbers, jumps)."""
    t0, t1 = _parse_utc(start, "start"), _parse_utc(end, "end")
    if t1 <= t0:
        raise HTTPException(status_code=422, detail="'end' must be after 'start'.")
    craft = spacecraft.strip().upper() or None
    if craft and craft not in shock_catalog.SPACECRAFT.values():
        raise HTTPException(status_code=422, detail="'spacecraft' must be WIND, ACE or DSCOVR.")
    events = shock_catalog.events_between(shock_catalog.load()["events"], t0, t1, craft)
    meta = _ipshocks_meta()
    if format == "csv":
        cols = [k for k in events[0]] if events else ["time", "spacecraft", "type"]
        out = io.StringIO()
        for k in ("name", "source", "doi", "licence", "version", "citation"):
            out.write(f"# {k}: {meta[k]}\n")
        w = csv.writer(out, lineterminator="\n")
        w.writerow(cols)
        for e in events:
            w.writerow([" ".join(map(str, e[c])) if isinstance(e[c], list) else ("" if e[c] is None else e[c]) for c in cols])
        return Response(content=out.getvalue(), media_type="text/csv",
                        headers=attachment(f"HELIOS_IPShocks_{t0:%Y%m%d}_{t1:%Y%m%d}.csv"))
    return {"catalog": meta, "count": len(events), "events": events}


@app.get("/api/statistics/storms")
async def omni_storm_list(
    start_year: int = Query(1995, ge=omni_statistics.FIRST_YEAR, le=2100),
    end_year: int = Query(2024, ge=omni_statistics.FIRST_YEAR, le=2100),
    threshold_nt: float = Query(-100.0, ge=-2000, le=0, description="Hourly Dst at or below this value"),
    separation_hours: float = Query(6.0, ge=0, le=240, description="Join runs separated by shorter recoveries"),
    floor_nt: Optional[float] = Query(None, ge=-2000, le=0, description="Keep storms with a minimum above this"),
    driver: str = Query("", max_length=100, description="Xu & Borovsky types of the driver, comma-separated"),
    download: bool = Query(False, description="Answer as a JSON file with the full provenance"),
):
    """
    Geomagnetic storms in hourly Dst (OMNI, WDC Kyoto) by strength, with the solar wind
    before each minimum; the onset times feed /api/analysis/superposed.
    """
    body = await _select_storms(start_year, end_year, threshold_nt, separation_hours, floor_nt, driver)
    return _analysis_answer(body, download, f"HELIOS_storms_{start_year}_{end_year}_{int(threshold_nt)}nT")


@app.get("/api/statistics/dst_models")
async def omni_dst_model_skill(
    start_year: int = Query(1998, ge=omni_statistics.FIRST_YEAR, le=2100),
    end_year: int = Query(2006, ge=omni_statistics.FIRST_YEAR, le=2100),
    threshold_nt: float = Query(-100.0, ge=-2000, le=0, description="Hourly Dst at or below this value"),
    separation_hours: float = Query(6.0, ge=0, le=240),
    floor_nt: Optional[float] = Query(None, ge=-2000, le=0),
    driver: str = Query("", max_length=100),
    download: bool = Query(False, description="Answer as a JSON file with the full provenance"),
):
    """
    Skill of the Burton and O'Brien-McPherron ring current models over every storm of a
    selection (as /api/statistics/storms): per-storm r, RMSE, bias and minimum error against
    hourly Dst, and their means over the storms with 95 % intervals.
    """
    if end_year - start_year + 1 > 30:
        raise HTTPException(status_code=422, detail="At most 30 years per request (the models run over every hour).")
    body = await _select_storms(start_year, end_year, threshold_nt, separation_hours, floor_nt, driver)
    storms = body["result"]["storms"]
    if not storms:
        raise HTTPException(status_code=422, detail="No storm matches the selection.")
    df, _ = await _omni_hourly_frame(start_year, end_year)
    result = await run_in_workers(omni_statistics.dst_model_skill, df, storms)
    result["selection"] = body["result"]["log"]
    body["provenance"]["method"] = result["method"]
    body["provenance"]["filters"] = body["result"]["log"]
    return _analysis_answer({"provenance": body["provenance"], "result": result}, download,
                            f"HELIOS_dst_model_skill_{start_year}_{end_year}_{int(threshold_nt)}nT")


@app.get("/api/statistics/omni/quantities")
async def omni_statistics_quantities():
    """Quantities, solar wind types and analyses available to /api/statistics/omni."""
    return {"quantities": omni_statistics.QUANTITIES, "solar_wind_types": list(omni_statistics.SW_TYPES.values()),
            "analyses": list(omni_statistics.ANALYSES)}


@app.get("/api/events")
async def get_events():
    return [
        {"id": "may_2024_g5", "title": "May 2024 Extreme G5 Superstorm (AR 3664)", "severity": "Extreme G5 (Kp=9)", "icon": "fa-bolt", "badge_color": "#dc2626"},
        {"id": "halloween_2003", "title": "Halloween 2003 Storms (X17+ Flare)", "severity": "Extreme G5 (Kp=9)", "icon": "fa-radiation", "badge_color": "#dc2626"},
        {"id": "bastille_2000", "title": "Bastille Day 2000 Superstorm (X5.7)", "severity": "Extreme G5 / S4 (Kp=9)", "icon": "fa-fire-flame-curved", "badge_color": "#ea580c"},
        {"id": "quebec_1989", "title": "Hydro-Québec Blackout (March 1989)", "severity": "Extreme G5 (Dst -589)", "icon": "fa-plug-circle-xmark", "badge_color": "#e11d48"},
        {"id": "carrington_1859", "title": "Carrington Event (September 1859)", "severity": "Superstorm (Dst <-850)", "icon": "fa-meteor", "badge_color": "#9333ea"},
        {"id": "st_patricks_2015", "title": "St. Patrick's Day Storm (March 2015)", "severity": "Severe G4 (Kp=8-)", "icon": "fa-cloud-bolt", "badge_color": "#f59e0b"},
        {"id": "quiet_baseline", "title": "Quiet Sun Solar Wind Baseline", "severity": "Quiet G0 (Kp=1)", "icon": "fa-sun", "badge_color": "#10b981"}
    ]

@app.get("/api/event/{event_id}")
@app.get("/api/events/{event_id}")
async def get_event(event_id: str):
    try:
        return await downloader.get_historical_event(event_id)
    except UnknownEventError:
        raise HTTPException(status_code=404, detail=f"Unknown event '{event_id}'; see /api/events.")

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

MAX_EPHEMERIS_IDS = 40


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
    sc_list = list(dict.fromkeys(s.strip().upper() for s in satellites.split(",") if s.strip())) if satellites else None
    if sc_list and len(sc_list) > MAX_EPHEMERIS_IDS:
        raise HTTPException(status_code=422, detail=f"At most {MAX_EPHEMERIS_IDS} spacecraft per request.")
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
    except (OSError, ValueError, KeyError):  # archive unreadable: the oval falls back to Kp
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

    # Reported only (the Starkov oval does not use Bz); no value is no value, not -3 nT. A past
    # oval time gets no live Bz (it used to show today's value next to the 2003 oval).
    bz_val = float(bz_gsm) if bz_gsm is not None else (None if historical else latest_rec.get("bz_gsm"))

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
            kp_val, kp_source = kp_from_solar_wind(latest_rec, bundle["provenance"]["kind"])
            if kp_val is None:
                if al_val is None:
                    raise HTTPException(status_code=503, detail="No observed Kp, AL or solar wind to draw the auroral oval.")
                kp_val, kp_source = 0.0, "not used (OMNI AL drives the oval)"
    else:
        kp_val = float(kp)

    boundaries = AuroralModel.calculate_auroral_boundaries(kp_val, bz_val, al_nt=al_val, al_source=al_source)
    oval_polygon = AuroralModel.generate_auroral_oval_coordinates(kp_val, bz_val, al_nt=al_val, when=oval_time)
    if kp_source.startswith("not used"):
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
    out = {
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
    if historical:  # the Dst model and Kyoto Dst are the last day of live data, not the oval's time
        out.update({k: None for k in ("dst_initial_observed_nt", "dst_evolution", "dst_observed", "dst_skill",
                                      "drivers_provenance")})
        out["dst_note"] = "The Dst panel covers the last 24 h of live data; it is not shown for a past oval time."
    return out

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

@app.get("/api/solar_images/sources")
async def get_solar_image_sources():
    """Instruments whose images can be had by time (Helioviewer Project)."""
    return {"instruments": solar_images.catalog(), "credit": solar_images.CREDIT,
            "fits_available": importlib.util.find_spec("sunpy") is not None}


@app.get("/api/solar_images/frames")
async def get_solar_image_frames(instrument: str = Query("lasco_c2"), start: str = Query(...), end: str = Query(...),
                                 n: int = Query(12, ge=1, le=solar_images.MAX_FRAMES),
                                 size: int = Query(512)):
    """Images of one instrument between start and end (closest to n evenly spaced times), Sun-centred."""
    t0, t1 = _parse_utc(start, "start"), _parse_utc(end, "end")
    try:
        res = await solar_image_client.frames(instrument, t0, t1, n, size)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not res["frames"] and res["unreachable_requests"]:
        raise HTTPException(status_code=503, detail="The Helioviewer image service could not be reached.")
    return res


@app.get("/api/solar_images/image")
async def get_solar_image(instrument: str = Query("lasco_c2"), date: str = Query(...), size: int = Query(512)):
    """Sun-centred PNG of the image of `instrument` closest to `date`."""
    try:
        png = await solar_image_client.image(instrument, _parse_utc(date, "date"), size)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if png is None:
        raise HTTPException(status_code=503, detail="No image: the Helioviewer image service could not be reached.")
    return Response(content=png, media_type="image/png")


@app.get("/api/solar_images/fits")
async def get_solar_image_fits(instrument: str = Query("lasco_c2"), start: str = Query(...), end: str = Query(...),
                               download: int = Query(0, ge=0, le=10, description="files to download (0: list only)")):
    """Science FITS files through SunPy Fido (optional dependency: pip install helios-l1[solar])."""
    t0, t1 = _parse_utc(start, "start"), _parse_utc(end, "end")
    folder = os.path.join(str(helios_config.CACHE_DIR), "fits", instrument) if download else None
    try:  # network-bound: a thread, not the worker pool
        return await asyncio.to_thread(solar_images.fits_search, instrument, t0, t1, download or 20, folder)
    except ImportError:
        raise HTTPException(status_code=501, detail="Science FITS files need SunPy: pip install \"helios-l1[solar]\".")
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))


@app.get("/api/coronagraph/difference")
async def get_running_difference(instrument: str = Query("lasco_c2"), date: str = Query(...),
                                 previous: str = Query(...), size: int = Query(512)):
    """Running-difference picture: the image closest to `date` minus the one closest to `previous`."""
    try:
        cur, prev = await asyncio.gather(solar_image_client.image(instrument, _parse_utc(date, "date"), size),
                                         solar_image_client.image(instrument, _parse_utc(previous, "previous"), size))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if cur is None or prev is None:
        raise HTTPException(status_code=503, detail="The Helioviewer image service could not be reached.")
    return Response(content=await run_in_workers(cme_tracking.difference_png, cur, prev), media_type="image/png")


@app.post("/api/coronagraph/jmap")
async def post_jmap(req: JmapRequest):
    """Height-time map along a position angle from the archive images, with an automatic front track."""
    t0, t1 = _parse_utc(req.start, "start"), _parse_utc(req.end, "end")
    try:
        listing = await solar_image_client.frames(req.instrument, t0, t1, req.n, 512)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    sem = asyncio.Semaphore(4)

    async def picture(f):
        async with sem:
            return await solar_image_client.image(req.instrument, _parse_utc(f["date"], "date"), 512)
    pngs = await asyncio.gather(*(picture(f) for f in listing["frames"]))
    frames = [dict(f, png=p) for f, p in zip(listing["frames"], pngs) if p is not None]
    try:
        jm = await run_in_workers(cme_tracking.jmap, frames, req.pa_deg, req.r_min, req.r_max, 200, req.width_deg, req.mode)
    except ValueError as exc:
        raise HTTPException(status_code=422 if frames else 503,
                            detail=str(exc) if frames else "The Helioviewer image service could not be reached.")
    track = cme_tracking.auto_track(jm.pop("values"), jm["r_rsun"], jm["times"], req.k_sigma)
    return {**jm, "instrument": req.instrument, "label": listing["label"], "n_frames": len(frames),
            "auto_track": track, "field_half_width_rsun": listing["half_width_rsun"], "credit": listing["credit"],
            "method": "Sheeley et al. (1999) J-map of difference brightness (display images, not calibrated radiance)"}


@app.post("/api/coronagraph/fit")
async def post_front_fit(req: FrontFitRequest):
    """Height-time fit of front points, projection-corrected speed and inputs for the CME arrival solver."""
    pts = [p.model_dump() for p in req.points]
    try:
        fit = cme_tracking.fit_height_time(pts, req.order)
        when = cme_tracking._t(fit["time_end"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    out = {"fit": fit, "projection": None, "observer": None}
    speed = fit["speed_kms"]
    if req.source_lon_deg is not None and req.source_lat_deg is not None:
        obs = cme_tracking.observer_longitude(req.instrument, when)
        proj = cme_tracking.projection(speed, req.source_lon_deg, req.source_lat_deg, obs["longitude_deg"])
        out.update(observer=obs, projection=proj)
        if proj["radial_speed_kms"] is not None:
            speed = proj["radial_speed_kms"]
    out["solver_inputs"] = cme_tracking.solver_inputs(fit, speed)
    return out


@app.get("/api/coronagraph/feeds")
async def get_coronagraph_feeds():
    return CoronagraphAnalyzer.get_coronagraph_feeds()

@app.post("/api/coronagraph/kinematics")
async def calculate_cme_kinematics(req: CMEKinematicsRequest):
    try:
        res = CoronagraphAnalyzer.calculate_cme_kinematics(
            r1_rsun=req.r1_rsun,
            r2_rsun=req.r2_rsun,
            dt_minutes=req.dt_minutes,
            launch_time_iso=req.launch_time_iso,
            ambient_wind_kms=req.ambient_wind_kms,
            gamma_drag=req.gamma_drag
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if "error" in res:
        raise HTTPException(status_code=422, detail=res["error"])
    return res

@app.get("/api/parker_spiral")
@app.get("/api/parker/spiral")
async def get_parker_spiral(speed_kms: float = Query(450.0, ge=150.0, le=3000.0, description="Solar wind speed (km/s)")):
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
            headers=attachment(f"helios_{mission_slug}_telemetry.csv")
        )
    elif export_format.lower() == "json":
        return Response(
            content=json.dumps(latest_custom_dataset, indent=2),
            media_type="application/json",
            headers=attachment(f"helios_{mission_slug}_telemetry.json")
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
    db_dt: float = Query(120.0, ge=0.0, le=10000.0, description="Rate of magnetic change dB/dt (nT/min)"),
    geology: str = Query("precambrian_shield", description="Geological conductivity profile")
):
    # An unknown profile used to be replaced by the high-risk shield and reported as the user's choice.
    if geology not in GICHazardModel.GEOLOGICAL_ZONES:
        raise HTTPException(status_code=422, detail=f"Unknown geology '{geology}'; one of {', '.join(GICHazardModel.GEOLOGICAL_ZONES)}.")
    return GICHazardModel.calculate_geoelectric_field(db_dt_nt_per_min=db_dt, geology_type=geology)


@app.get("/api/report/html")
async def get_html_report(mission_id: str = "DSCOVR", download: bool = False):
    mission_key = mission_id.upper()
    if mission_key not in MISSIONS:
        mission_key = "DSCOVR"
    bundle = await downloader.get_telemetry_bundle(mission_key, span_days=1)
    data = bundle["records"]
    latest = latest_valid_record(data)
    classification = await classify_current_conditions(latest, bundle["provenance"]["kind"])
    shocks = SpaceWeatherPhysics.detect_interplanetary_shocks(data)
    auroral_data = (AuroralModel.calculate_auroral_boundaries(classification["kp"], latest.get("bz_gsm"))
                    if classification["kp"] is not None else {})

    html = ScientificReportGenerator.generate_html_bulletin(
        mission_name=MISSIONS[mission_key]["name"],
        telemetry=data,
        classification=classification,
        shocks=shocks,
        auroral_data=auroral_data,
        provenance=bundle["provenance"]
    )
    headers = attachment(f"HELIOS-L1-{mission_key}-Bulletin.html") if download else {}
    return Response(content=html, media_type="text/html", headers=headers)

@app.get("/api/report/markdown")
async def get_markdown_report(mission_id: str = "DSCOVR", download: bool = False):
    mission_key = mission_id.upper()
    if mission_key not in MISSIONS:
        mission_key = "DSCOVR"
    bundle = await downloader.get_telemetry_bundle(mission_key, span_days=1)
    data = bundle["records"]
    latest = latest_valid_record(data)
    classification = await classify_current_conditions(latest, bundle["provenance"]["kind"])
    shocks = SpaceWeatherPhysics.detect_interplanetary_shocks(data)
    auroral_data = (AuroralModel.calculate_auroral_boundaries(classification["kp"], latest.get("bz_gsm"))
                    if classification["kp"] is not None else {})

    md = ScientificReportGenerator.generate_markdown_executive_summary(
        mission_name=MISSIONS[mission_key]["name"],
        telemetry=data,
        classification=classification,
        shocks=shocks,
        auroral_data=auroral_data,
        provenance=bundle["provenance"]
    )
    headers = attachment(f"HELIOS-L1-{mission_key}-Executive-Summary.md") if download else {}
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
    return Response(content=csv_str, media_type="text/csv", headers=attachment(f"HELIOS_{mission_id}_telemetry.csv"))

@app.get("/api/export/plot")
async def export_plot(mission_id: str = "DSCOVR", span_days: int = Query(1, ge=1, le=7)):
    mission_key = mission_id.upper()
    if mission_key not in MISSIONS:
        raise HTTPException(status_code=404, detail=f"Mission '{mission_id}' not recognized.")
    bundle = await downloader.get_telemetry_bundle(mission_key, span_days=span_days)
    name = MISSIONS.get(mission_key, {}).get("name", mission_id)
    png_bytes = await run_in_workers(DataExporter.generate_overview_chart, bundle["records"], name, bundle["provenance"])
    return Response(content=png_bytes, media_type="image/png", headers=attachment(f"HELIOS_{mission_id}_chart.png"))


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
