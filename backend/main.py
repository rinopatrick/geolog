"""GeoLog — Oil & Gas Well Log Viewer."""
import logging
import traceback
from fastapi import FastAPI, Request, UploadFile, File, Depends, HTTPException, Header, WebSocket, WebSocketDisconnect, Query
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session
import numpy as np
import json
import os
import math
from typing import Any, Literal
from pydantic import BaseModel, Field

try:
    from routers.qc import router as qc_router
    from routers.correlation import router as corr_router
    from routers.zonation import router as zonation_router
    from routers.units import router as units_router
    from routers.templates import router as templates_router
    from routers.reports import router as reports_router
except ImportError:
    from backend.routers.qc import router as qc_router
    from backend.routers.correlation import router as corr_router
    from backend.routers.zonation import router as zonation_router
    from backend.routers.units import router as units_router
    from backend.routers.templates import router as templates_router
    from backend.routers.reports import router as reports_router


class SafeJSONResponse(JSONResponse):
    """JSONResponse that sanitizes NaN/Inf to null for JSON compliance."""
    def render(self, content):
        def _sanitize(obj):
            if isinstance(obj, float):
                if math.isnan(obj) or math.isinf(obj):
                    return None
                return obj
            if isinstance(obj, dict):
                return {k: _sanitize(v) for k, v in obj.items()}
            if isinstance(obj, (list, tuple)):
                return [_sanitize(v) for v in obj]
            if isinstance(obj, np.floating):
                v = float(obj)
                return None if (math.isnan(v) or math.isinf(v)) else v
            if isinstance(obj, np.integer):
                return int(obj)
            if isinstance(obj, np.ndarray):
                return _sanitize(obj.tolist())
            return obj
        sanitized = _sanitize(content)
        return super().render(sanitized)
import datetime
import csv
import io
import zipfile
import time
from concurrent.futures import ThreadPoolExecutor
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.graphics.shapes import Drawing
from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics import renderPDF
from threading import Lock
import uuid
import hashlib
import hmac
from email.utils import format_datetime, parsedate_to_datetime

try:
    from database import engine, Base, get_db, SessionLocal
    from models import Project, Well, LogRun, CurveData, FormationTop, Annotation, DSTTest, RFTPoint, CompletionData, ProductionData, Zone, CorrelationMarker, CorrelationProfile, PetroParams, LogRunDepthShift, CurveAlias, DeviationSurvey, AuditLog, User
    from las_parser import LASParser, CURVE_TRACKS
    from dlis_lis_parser import parse_dlis_content, parse_lis_content
    from security import AuthConfig, resolve_auth_context, require_min_role, role_from_request, ROLE_RANK
except ImportError:
    from backend.database import engine, Base, get_db, SessionLocal
    from backend.models import Project, Well, LogRun, CurveData, FormationTop, Annotation, DSTTest, RFTPoint, CompletionData, ProductionData, Zone, CorrelationMarker, CorrelationProfile, PetroParams, LogRunDepthShift, CurveAlias, DeviationSurvey, AuditLog, User
    from backend.las_parser import LASParser, CURVE_TRACKS
    from backend.dlis_lis_parser import parse_dlis_content, parse_lis_content
    from backend.security import AuthConfig, resolve_auth_context, require_min_role, role_from_request, ROLE_RANK

# Create tables
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("geolog")

# In-memory original-value snapshots for curve point edits.
# Keyed by "<log_run_id>:<mnemonic>" -> {"index": original_value}
CURVE_EDIT_ORIGINALS = {}

# Lightweight observability counters (Phase 2 baseline).
OBS_METRICS_LOCK = Lock()
OBS_METRICS = {
    "requests_total": 0,
    "requests_by_method": {},
    "requests_by_status": {},
    "latency_ms_sum": 0.0,
    "latency_ms_count": 0,
    "recent_events": [],
}

Base.metadata.create_all(bind=engine)


def _ensure_well_coordinate_columns():
    """Add latitude/longitude columns if missing (idempotent)."""
    with engine.begin() as conn:
        try:
            conn.execute(text("ALTER TABLE wells ADD COLUMN latitude FLOAT;"))
        except Exception:
            pass
        try:
            conn.execute(text("ALTER TABLE wells ADD COLUMN longitude FLOAT;"))
        except Exception:
            pass


_ensure_well_coordinate_columns()


def _ensure_production_table():
    """Create production table for existing deployments without migrations."""
    ddl = """
    CREATE TABLE IF NOT EXISTS production_data (
        id INTEGER PRIMARY KEY,
        well_id INTEGER NOT NULL,
        date DATE NOT NULL,
        oil_rate FLOAT,
        gas_rate FLOAT,
        water_rate FLOAT,
        water_cut FLOAT,
        gor FLOAT,
        bhp FLOAT,
        whp FLOAT,
        choke_size FLOAT,
        cumulative_oil FLOAT,
        cumulative_gas FLOAT,
        cumulative_water FLOAT,
        notes TEXT DEFAULT '',
        created_at DATETIME,
        FOREIGN KEY(well_id) REFERENCES wells(id)
    );
    """
    with engine.begin() as conn:
        try:
            conn.execute(text(ddl))
        except Exception:
            pass


_ensure_production_table()


def _ensure_audit_log_columns():
    """Backfill audit_log schema for immutable provenance chain (idempotent)."""
    ddls = [
        "ALTER TABLE audit_log ADD COLUMN request_id VARCHAR(64) DEFAULT '';",
        "ALTER TABLE audit_log ADD COLUMN auth_subject VARCHAR(120) DEFAULT '';",
        "ALTER TABLE audit_log ADD COLUMN auth_role VARCHAR(50) DEFAULT 'viewer';",
        "ALTER TABLE audit_log ADD COLUMN route_path VARCHAR(255) DEFAULT '';",
        "ALTER TABLE audit_log ADD COLUMN method VARCHAR(10) DEFAULT '';",
        "ALTER TABLE audit_log ADD COLUMN status_code INTEGER;",
        "ALTER TABLE audit_log ADD COLUMN payload_hash VARCHAR(64) DEFAULT '';",
        "ALTER TABLE audit_log ADD COLUMN prev_hash VARCHAR(64) DEFAULT '';",
        "ALTER TABLE audit_log ADD COLUMN entry_hash VARCHAR(64) DEFAULT '';",
    ]
    with engine.begin() as conn:
        for ddl in ddls:
            try:
                conn.execute(text(ddl))
            except Exception:
                pass


_ensure_audit_log_columns()


def _ensure_audit_log_immutability_triggers():
    """Prevent updates/deletes on audit_log rows (append-only)."""
    stmts = [
        """
        CREATE TRIGGER IF NOT EXISTS trg_audit_log_no_update
        BEFORE UPDATE ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'audit_log is immutable');
        END;
        """,
        """
        CREATE TRIGGER IF NOT EXISTS trg_audit_log_no_delete
        BEFORE DELETE ON audit_log
        BEGIN
            SELECT RAISE(ABORT, 'audit_log is immutable');
        END;
        """,
    ]
    with engine.begin() as conn:
        for stmt in stmts:
            try:
                conn.execute(text(stmt))
            except Exception:
                pass


_ensure_audit_log_immutability_triggers()


def _ensure_completion_table():
    """Create completion table for existing deployments without migrations."""
    ddl = """
    CREATE TABLE IF NOT EXISTS completion_data (
        id INTEGER PRIMARY KEY,
        well_id INTEGER NOT NULL,
        depth_top FLOAT NOT NULL,
        depth_base FLOAT NOT NULL,
        component_type VARCHAR(50) NOT NULL,
        size VARCHAR(100) DEFAULT '',
        description TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        created_at DATETIME,
        FOREIGN KEY(well_id) REFERENCES wells(id)
    );
    """
    with engine.begin() as conn:
        try:
            conn.execute(text(ddl))
        except Exception:
            pass


_ensure_completion_table()


def _to_float_or_none(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    # Keep numeric content and sign/dot
    cleaned = "".join(ch for ch in s if ch.isdigit() or ch in {".", "-", "+"})
    if cleaned in {"", ".", "-", "+", "-.", "+."}:
        return None
    try:
        return float(cleaned)
    except ValueError:
        return None


def _extract_las_coordinates(las):
    """Extract latitude/longitude from LAS well header/parameters when present."""
    lat = None
    lon = None

    # Try explicit attributes if parser is extended in future
    lat = _to_float_or_none(getattr(las.well, "latitude", None))
    lon = _to_float_or_none(getattr(las.well, "longitude", None))

    # Fallback: parse from location string (e.g. "29.1234, -95.5678")
    if lat is None or lon is None:
        loc = getattr(las.well, "location", "") or ""
        nums = []
        for token in loc.replace(";", " ").replace(",", " ").split():
            v = _to_float_or_none(token)
            if v is not None:
                nums.append(v)
        if len(nums) >= 2:
            if lat is None:
                lat = nums[0]
            if lon is None:
                lon = nums[1]

    # Fallback: parse common parameter mnemonics
    if lat is None or lon is None:
        for p in las.parameters:
            m = (p.mnemonic or "").strip().upper()
            v = _to_float_or_none(p.value)
            if v is None:
                continue
            if lat is None and m in {"LAT", "LATI", "LATITUDE"}:
                lat = v
            if lon is None and m in {"LON", "LONG", "LONGI", "LONGITUDE"}:
                lon = v

    # Basic sanity check
    if lat is not None and not (-90.0 <= lat <= 90.0):
        lat = None
    if lon is not None and not (-180.0 <= lon <= 180.0):
        lon = None

    return lat, lon


PETRO_TEMPLATES = [
    {
        "name": "Sandstone Standard",
        "description": "Balanced clean-sand default for conventional clastics.",
        "params": {"saturation_model": "archie", "a": 1.0, "m": 2.0, "n": 2.0, "rw": 0.08},
        "recommended_cutoffs": {"vsh_cutoff": 0.4, "phie_cutoff": 0.1, "sw_cutoff": 0.6, "gr_min": 0, "gr_max": 150},
        "suggested_rw": 0.08,
        "log_track_layout": ["GR", "RT", "NPHI", "RHOB", "DT", "VSH", "PHIE", "SW"],
    },
    {
        "name": "Carbonate",
        "description": "Conservative carbonate interpretation with tighter shale screening.",
        "params": {"saturation_model": "archie", "a": 1.0, "m": 2.0, "n": 2.0, "rw": 0.05},
        "recommended_cutoffs": {"vsh_cutoff": 0.3, "phie_cutoff": 0.05, "sw_cutoff": 0.5, "gr_min": 0, "gr_max": 100},
        "suggested_rw": 0.05,
        "log_track_layout": ["GR", "PEF", "RHOB", "NPHI", "RT", "PHIE", "SW"],
    },
    {
        "name": "Shale Gas",
        "description": "Lower-porosity unconventional shale gas workflow baseline.",
        "params": {"saturation_model": "simandoux", "a": 1.0, "m": 1.8, "n": 1.8, "rw": 0.12},
        "recommended_cutoffs": {"vsh_cutoff": 0.6, "phie_cutoff": 0.02, "sw_cutoff": 0.4, "gr_min": 0, "gr_max": 200},
        "suggested_rw": 0.12,
        "log_track_layout": ["GR", "RT", "RHOB", "NPHI", "DT", "TOC_PROXY", "SW"],
    },
    {
        "name": "Deepwater Turbidite",
        "description": "Deepwater clastic setting tuned for variable lamination and pay continuity.",
        "params": {"saturation_model": "archie", "a": 0.8, "m": 2.2, "n": 2.2, "rw": 0.09},
        "recommended_cutoffs": {"vsh_cutoff": 0.35, "phie_cutoff": 0.08, "sw_cutoff": 0.65, "gr_min": 0, "gr_max": 180},
        "suggested_rw": 0.09,
        "log_track_layout": ["GR", "RT", "NPHI", "RHOB", "DT", "VSH", "PHIE", "SW"],
    },
    {
        "name": "Tight Gas Sand",
        "description": "Tight-gas sand screening with stricter porosity and water saturation limits.",
        "params": {"saturation_model": "archie", "a": 1.0, "m": 2.5, "n": 2.0, "rw": 0.07},
        "recommended_cutoffs": {"vsh_cutoff": 0.25, "phie_cutoff": 0.03, "sw_cutoff": 0.45, "gr_min": 0, "gr_max": 120},
        "suggested_rw": 0.07,
        "log_track_layout": ["GR", "RT", "NPHI", "RHOB", "DT", "PHIE", "SW"],
    },
]


def _find_template(template_name: str):
    target = (template_name or "").strip().lower()
    for tpl in PETRO_TEMPLATES:
        if tpl["name"].lower() == target:
            return tpl
    return None


def _build_petro_summary(wid: int, params: dict, db: Session):
    well = db.query(Well).filter(Well.id == wid).first()
    latest = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    gross = None
    if latest and latest.start_depth is not None and latest.stop_depth is not None:
        gross = float(latest.stop_depth - latest.start_depth)
    return {
        "well_id": wid,
        "well_name": well.name if well else None,
        "log_run_id": latest.id if latest else None,
        "interval": {
            "top": latest.start_depth if latest else None,
            "base": latest.stop_depth if latest else None,
            "gross": gross,
        },
        "petro_params": params,
        "notes": "Template applied and petrophysical defaults updated.",
    }

app = FastAPI(
    title="GeoLog",
    description="Oil & Gas Well Log Viewer",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    default_response_class=SafeJSONResponse,
)
app.include_router(qc_router)
app.include_router(corr_router)
app.include_router(zonation_router)
app.include_router(units_router)
app.include_router(templates_router)
app.include_router(reports_router)

JOB_EXECUTOR = ThreadPoolExecutor(max_workers=2)
JOBS = {}
JOBS_LOCK = Lock()


def _safe_float(val, default=None):
    """Safely convert value to float, return default on failure."""
    if val is None or val == "":
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _utc_now_iso() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def _create_job(job_type: str) -> str:
    job_id = f"job_{uuid.uuid4().hex[:12]}"
    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id,
            "type": job_type,
            "status": "queued",
            "progress": 0,
            "result": None,
            "error": None,
            "started_at": None,
            "finished_at": None,
            "created_at": _utc_now_iso(),
        }
    return job_id


def _update_job(job_id: str, **fields):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if not job:
            return
        job.update(fields)


def _get_job(job_id: str):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        return dict(job) if job else None


def _list_jobs():
    with JOBS_LOCK:
        return [dict(j) for j in JOBS.values()]

AUTH_CONFIG = AuthConfig.from_env()
if AUTH_CONFIG.mode == "header":
    logger.warning("AUTH_MODE=header (compat mode). Set AUTH_MODE=jwt for server-verified bearer auth.")


def _require_role(min_role: str, request: Request):
    current = role_from_request(request)
    require_min_role(min_role, current)
    return current


def require_viewer(request: Request):
    return _require_role("viewer", request)


def require_interpreter(request: Request):
    return _require_role("interpreter", request)


def require_admin(request: Request):
    return _require_role("admin", request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)


def _httpdate(dt: datetime.datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    else:
        dt = dt.astimezone(datetime.timezone.utc)
    return format_datetime(dt, usegmt=True)


def _parse_if_modified_since(value: str):
    if not value:
        return None
    try:
        dt = parsedate_to_datetime(value)
        if dt is None:
            return None
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=datetime.timezone.utc)
        return dt.astimezone(datetime.timezone.utc)
    except Exception:
        return None


def _build_curve_cache_headers(lr_id: int, mnemonics, start, stop, step, max_points=None):
    key = f"{lr_id}|{','.join(sorted([str(m) for m in (mnemonics or [])]))}|{start}|{stop}|{step}|{max_points}"
    etag = f'W/"{hashlib.sha1(key.encode("utf-8")).hexdigest()}"'
    return {
        "ETag": etag,
        "Cache-Control": "private, max-age=60",
    }


def _lttb_indices(x: np.ndarray, y: np.ndarray, threshold: int):
    n = len(y)
    if threshold >= n or threshold <= 2 or n <= 2:
        return np.arange(n, dtype=np.int64)

    sampled = np.zeros(threshold, dtype=np.int64)
    sampled[0] = 0
    sampled[-1] = n - 1
    every = (n - 2) / float(threshold - 2)
    a = 0

    for i in range(threshold - 2):
        avg_start = int(np.floor((i + 1) * every)) + 1
        avg_end = int(np.floor((i + 2) * every)) + 1
        avg_end = min(avg_end, n)
        if avg_start < avg_end:
            avg_x = np.nanmean(x[avg_start:avg_end])
            avg_y = np.nanmean(y[avg_start:avg_end])
        else:
            idx = min(avg_start, n - 1)
            avg_x = x[idx]
            avg_y = y[idx]

        if np.isnan(avg_y):
            sampled[i + 1] = min(avg_start, n - 2)
            a = sampled[i + 1]
            continue

        range_offs = int(np.floor(i * every)) + 1
        range_to = int(np.floor((i + 1) * every)) + 1
        range_to = min(range_to, n - 1)

        if range_offs >= range_to:
            sampled[i + 1] = min(range_offs, n - 2)
            a = sampled[i + 1]
            continue

        ax = x[a]
        ay = y[a]
        if np.isnan(ay):
            sampled[i + 1] = min(range_offs, n - 2)
            a = sampled[i + 1]
            continue
        bx = x[range_offs:range_to]
        by = y[range_offs:range_to]
        area = np.abs((ax - avg_x) * (by - ay) - (ax - bx) * (avg_y - ay)) * 0.5
        area = np.where(np.isnan(area), 0, area)
        idx = int(np.nanargmax(area))
        a = range_offs + idx
        sampled[i + 1] = a

    return np.unique(np.clip(sampled, 0, n - 1))


def _extract_trace_id_from_traceparent(traceparent: str) -> str:
    raw = (traceparent or "").strip()
    parts = raw.split("-")
    if len(parts) != 4:
        return ""
    trace_id = parts[1].strip().lower()
    if len(trace_id) != 32:
        return ""
    if not all(ch in "0123456789abcdef" for ch in trace_id):
        return ""
    return trace_id


class RequestIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = (request.headers.get("X-Request-ID") or "").strip() or uuid.uuid4().hex[:16]
        trace_id = _extract_trace_id_from_traceparent(request.headers.get("traceparent", ""))
        request.state.request_id = request_id
        request.state.trace_id = trace_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        if trace_id:
            response.headers["X-Trace-ID"] = trace_id
        return response


class AuthContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            auth_ctx = resolve_auth_context(request, AUTH_CONFIG)
        except HTTPException as e:
            return SafeJSONResponse(status_code=e.status_code, content={"detail": e.detail})
        request.state.user_role = auth_ctx.role
        request.state.auth_subject = auth_ctx.subject
        request.state.auth_source = auth_ctx.source
        request.state.auth_claims = auth_ctx.claims
        return await call_next(request)


class RequestMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        method = request.method.upper()
        status = str(getattr(response, "status_code", 0))

        with OBS_METRICS_LOCK:
            OBS_METRICS["requests_total"] += 1
            OBS_METRICS["latency_ms_sum"] += elapsed_ms
            OBS_METRICS["latency_ms_count"] += 1
            by_method = OBS_METRICS["requests_by_method"]
            by_status = OBS_METRICS["requests_by_status"]
            by_method[method] = int(by_method.get(method, 0)) + 1
            by_status[status] = int(by_status.get(status, 0)) + 1

            recent = OBS_METRICS.get("recent_events")
            if isinstance(recent, list):
                recent.append({
                    "ts": datetime.datetime.utcnow().isoformat() + "Z",
                    "request_id": str(getattr(request.state, "request_id", "") or ""),
                    "trace_id": str(getattr(request.state, "trace_id", "") or ""),
                    "method": method,
                    "path": request.url.path,
                    "status": int(status),
                    "latency_ms": round(elapsed_ms, 2),
                })
                if len(recent) > 200:
                    del recent[:-200]

        logger.info(json.dumps({
            "event": "http_request",
            "request_id": str(getattr(request.state, "request_id", "") or ""),
            "trace_id": str(getattr(request.state, "trace_id", "") or ""),
            "method": method,
            "path": request.url.path,
            "status": int(status),
            "latency_ms": round(elapsed_ms, 2),
        }, ensure_ascii=False))
        return response


class RBACWriteGuardMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        method = request.method.upper()
        path = request.url.path
        if method in {"POST", "PUT", "DELETE"} and path.startswith("/api/"):
            role = role_from_request(request)

            # POST endpoints that are read/query-only (safe for viewer)
            viewer_safe = {
                "/api/log-runs/",       # /data, /data-decimated queries
            }

            # Admin-only paths (structural/destructive)
            admin_exact_post = {"/api/projects/", "/api/wells/"}
            admin_prefixes = ("/api/users",)

            required = "interpreter"
            if path in admin_exact_post and method == "POST":
                required = "admin"
            elif any(path.startswith(p) for p in admin_prefixes):
                required = "admin"
            elif method == "DELETE":
                required = "admin"
            elif any(path.startswith(p) for p in viewer_safe):
                required = "viewer"

            if ROLE_RANK.get(role, 0) < ROLE_RANK.get(required, 99):
                return SafeJSONResponse(status_code=403, content={"detail": f"{required} role required"})

            # Interpretation lock enforcement (admins can override)
            # Lock applies to writes under /api/wells/{wid}/...
            if role != "admin":
                parts = [p for p in path.split("/") if p]
                # ['api','wells','{wid}',...]
                if len(parts) >= 3 and parts[0] == "api" and parts[1] == "wells":
                    try:
                        wid = int(parts[2])
                    except Exception:
                        wid = None
                    if wid is not None:
                        # allow snapshot/lock metadata operations while locked
                        allow_when_locked = (
                            f"/api/wells/{wid}/snapshots",
                            f"/api/wells/{wid}/lock-status",
                        )
                        if not any(path.startswith(p) for p in allow_when_locked):
                            lock = _get_well_lock(wid)
                            if lock.get("locked", False):
                                return SafeJSONResponse(
                                    status_code=423,
                                    content={
                                        "detail": "well is locked by approved snapshot",
                                        "locked": True,
                                        "lock": lock,
                                    },
                                )

        return await call_next(request)


class ErrorLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        try:
            response = await call_next(request)
            return response
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unhandled error on {request.method} {request.url.path}: {e}")
            logger.debug(traceback.format_exc())
            return SafeJSONResponse(
                status_code=500,
                content={"detail": "internal error"},
            )


class ImmutableAuditTrailMiddleware(BaseHTTPMiddleware):
    """Append-only provenance records for successful auth-critical writes."""
    async def dispatch(self, request: Request, call_next):
        method = request.method.upper()
        path = request.url.path
        if method not in {"POST", "PUT", "DELETE"} or not path.startswith("/api/"):
            return await call_next(request)

        body = await request.body()
        response = await call_next(request)

        # log only successful/accepted writes (exclude auth failures)
        if response.status_code >= 400:
            return response

        role = (getattr(request.state, "user_role", None) or "viewer").strip().lower()
        subject = (getattr(request.state, "auth_subject", None) or "").strip()
        request_id = str(getattr(request.state, "request_id", "") or request.headers.get("X-Request-ID") or uuid.uuid4().hex[:16])

        # best effort well/project extraction
        well_id = None
        project_id = None
        parts = [p for p in path.split("/") if p]
        try:
            if len(parts) >= 3 and parts[0] == "api" and parts[1] == "wells":
                well_id = int(parts[2])
            if len(parts) >= 3 and parts[0] == "api" and parts[1] == "projects":
                project_id = int(parts[2])
        except Exception:
            pass

        payload_hash = hashlib.sha256(body).hexdigest() if body else ""

        db = SessionLocal()
        try:
            prev = db.query(AuditLog).order_by(AuditLog.id.desc()).first()
            prev_hash = getattr(prev, "entry_hash", "") if prev else ""
            canonical = json.dumps({
                "request_id": request_id,
                "subject": subject,
                "role": role,
                "method": method,
                "path": path,
                "status": int(response.status_code),
                "payload_hash": payload_hash,
                "prev_hash": prev_hash,
                "well_id": well_id,
                "project_id": project_id,
            }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
            entry_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

            db.add(AuditLog(
                project_id=project_id,
                well_id=well_id,
                action=f"write:{method.lower()}",
                entity_type="api",
                details=path,
                user_label="local",
                request_id=request_id,
                auth_subject=subject,
                auth_role=role,
                route_path=path,
                method=method,
                status_code=int(response.status_code),
                payload_hash=payload_hash,
                prev_hash=prev_hash,
                entry_hash=entry_hash,
            ))
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()

        return response

app.add_middleware(RBACWriteGuardMiddleware)
app.add_middleware(ErrorLoggingMiddleware)
app.add_middleware(ImmutableAuditTrailMiddleware)
app.add_middleware(AuthContextMiddleware)
app.add_middleware(RequestMetricsMiddleware)
app.add_middleware(RequestIdMiddleware)


# ─── Auto-seed demo data on first startup ───────────────────
@app.on_event("startup")
def _auto_seed():
    """Seed demo data if database is empty. Gate behind GEOLOG_ENABLE_DEMO_SEED=true."""
    if os.environ.get("GEOLOG_ENABLE_DEMO_SEED", "false").lower() != "true":
        return
    db = SessionLocal()
    try:
        if db.query(Project).count() > 0:
            return  # Already seeded

        # Find demo LAS file (try multiple paths for Docker compat)
        _here = os.path.dirname(os.path.abspath(__file__))
        demo_paths = [
            os.path.join(_here, "demo.las"),
            os.path.join(_here, "..", "data", "hawkins_01.las"),
            os.path.join(_here, "data", "hawkins_01.las"),
        ]
        demo_las = next((p for p in demo_paths if os.path.isfile(p)), None)
        if not demo_las:
            print("⚠️ No demo LAS found, skipping auto-seed")
            return

        las = LASParser.parse_file(demo_las)
        fname = os.path.basename(demo_las)

        proj = Project(name="Demo Field Study", field_name="Demo Field", operator="GeoLog Demo", country="US")
        db.add(proj)
        db.flush()

        # ── Helper: create a well + log run + curves from LAS data ──
        def _seed_well(name, uwi, operator, depth_offset=0.0, tops_offset=0.0):
            well = Well(
                project_id=proj.id, name=name, uwi=uwi,
                operator=operator, total_depth=las.well.stop + depth_offset,
                depth_unit="FT",
            )
            db.add(well)
            db.flush()

            curves_def = [{"mnemonic": c.mnemonic, "unit": c.unit, "description": c.description} for c in las.curves]
            lr = LogRun(
                well_id=well.id, run_number=1, filename=fname,
                las_version=las.version,
                start_depth=las.well.start + depth_offset,
                stop_depth=las.well.stop + depth_offset,
                step=las.well.step, null_value=las.well.null,
                num_points=len(las.depth),
                curves_json=json.dumps(curves_def),
            )
            db.add(lr)
            db.flush()

            for curve in las.curves:
                arr = las.data.get(curve.mnemonic)
                if arr is not None:
                    valid = arr[~np.isnan(arr)]
                    db.add(CurveData(
                        log_run_id=lr.id, mnemonic=curve.mnemonic,
                        unit=curve.unit, description=curve.description,
                        num_points=len(arr),
                        min_value=float(np.min(valid)) if len(valid) else None,
                        max_value=float(np.max(valid)) if len(valid) else None,
                        data_binary=arr.tobytes(),
                    ))

            # Formation tops (offset for structural dip between wells)
            tops_data = [
                ("Formation A", las.well.start + (las.well.stop - las.well.start) * 0.15 + tops_offset, "#e74c3c", "Sandstone"),
                ("Formation B", las.well.start + (las.well.stop - las.well.start) * 0.45 + tops_offset, "#3498db", "Limestone"),
                ("Formation C", las.well.start + (las.well.stop - las.well.start) * 0.75 + tops_offset, "#2ecc71", "Shale"),
            ]
            for tname, depth, color, lith in tops_data:
                db.add(FormationTop(well_id=well.id, formation_name=tname, depth=depth, color=color, lithology=lith))

            return well, len(las.curves), len(las.depth), len(tops_data)

        # Well 1: reference well
        w1, nc1, np1, nt1 = _seed_well(
            name=las.well.well_name or "DEMO-01",
            uwi=las.well.uwi or "00-000-00000",
            operator=las.well.operator or "GeoLog Demo",
        )
        # Well 2: offset well (25 ft structural dip, for correlation demo)
        w2, nc2, np2, nt2 = _seed_well(
            name="DEMO-02", uwi="00-000-00001", operator="GeoLog Demo",
            depth_offset=25.0, tops_offset=12.0,
        )

        db.commit()
        print(f"✅ Auto-seeded: {w1.name} ({nc1} curves, {np1} pts), {w2.name} ({nc2} curves, {np2} pts), {nt1} tops each")
    except Exception as e:
        db.rollback()
        print(f"⚠️ Auto-seed failed: {e}")
    finally:
        db.close()


# ─── Health ───────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok", "app": "GeoLog", "version": "2.0.0"}


# ─── Projects ─────────────────────────────────────────────────
@app.get("/api/projects/")
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).all()
    result = []
    for p in projects:
        d = {c.name: getattr(p, c.name) for c in Project.__table__.columns}
        d["well_count"] = len(p.wells)
        result.append(d)
    return result

@app.post("/api/projects/", status_code=201)
def create_project(data: dict, db: Session = Depends(get_db)):
    p = Project(**data)
    db.add(p)
    db.commit()
    db.refresh(p)
    return {c.name: getattr(p, c.name) for c in Project.__table__.columns}

@app.delete("/api/projects/{pid}", status_code=204)
def delete_project(pid: int, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == pid).first()
    if not p:
        raise HTTPException(404, "Project not found")
    db.delete(p)
    db.commit()


# ─── Wells ────────────────────────────────────────────────────
@app.get("/api/wells/")
def list_wells(project_id: int = None, db: Session = Depends(get_db)):
    q = db.query(Well)
    if project_id:
        q = q.filter(Well.project_id == project_id)
    wells = q.all()
    result = []
    for w in wells:
        d = {c.name: getattr(w, c.name) for c in Well.__table__.columns}
        d["log_run_count"] = len(w.log_runs)
        d["formation_top_count"] = len(w.formation_tops)
        result.append(d)
    return result

@app.post("/api/wells/", status_code=201)
def create_well(data: dict, db: Session = Depends(get_db)):
    w = Well(**data)
    db.add(w)
    db.commit()
    db.refresh(w)
    return {c.name: getattr(w, c.name) for c in Well.__table__.columns}

@app.get("/api/wells/{wid}")
def get_well(wid: int, db: Session = Depends(get_db)):
    w = db.query(Well).filter(Well.id == wid).first()
    if not w:
        raise HTTPException(404, "Well not found")
    d = {c.name: getattr(w, c.name) for c in Well.__table__.columns}
    d["log_runs"] = [{c.name: getattr(lr, c.name) for c in LogRun.__table__.columns} for lr in w.log_runs]
    d["formation_tops"] = [{c.name: getattr(ft, c.name) for c in FormationTop.__table__.columns} for ft in w.formation_tops]
    return d

@app.delete("/api/wells/{wid}", status_code=204)
def delete_well(wid: int, db: Session = Depends(get_db)):
    w = db.query(Well).filter(Well.id == wid).first()
    if not w:
        raise HTTPException(404, "Well not found")
    db.delete(w)
    db.commit()


@app.put("/api/wells/{wid}")
def update_well(wid: int, data: dict, db: Session = Depends(get_db)):
    w = db.query(Well).filter(Well.id == wid).first()
    if not w:
        raise HTTPException(404, "Well not found")
    for field in ("name", "uwi", "api_number", "operator", "field_name", "latitude", "longitude", "elevation", "depth_unit", "spud_date"):
        if field in data:
            setattr(w, field, data[field])
    db.commit()
    db.refresh(w)
    return {c.name: getattr(w, c.name) for c in Well.__table__.columns}


# ─── LAS Upload ───────────────────────────────────────────────
MAX_UPLOAD_SIZE = 50 * 1024 * 1024  # 50MB


def _persist_non_las_runs(db: Session, well: Well, filename: str, parsed, source_format: str):
    created_runs = []
    for run in parsed.runs:
        curves_def = [
            {"mnemonic": c.mnemonic, "unit": c.unit, "description": c.description}
            for c in run.curves
        ]

        lr = LogRun(
            well_id=well.id,
            run_number=len(well.log_runs) + len(created_runs) + 1,
            filename=f"{filename}::{run.run_name}" if len(parsed.runs) > 1 else filename,
            las_version=run.version,
            start_depth=run.start_depth,
            stop_depth=run.stop_depth,
            step=run.step,
            null_value=run.null_value,
            num_points=int(len(run.depth)),
            curves_json=json.dumps(curves_def),
            parameters_json=json.dumps(run.parameters or []),
        )
        db.add(lr)
        db.flush()

        for curve in run.curves:
            arr = run.data.get(curve.mnemonic)
            if arr is None:
                continue
            arr = np.asarray(arr, dtype=np.float64)
            valid = arr[~np.isnan(arr)]
            db.add(CurveData(
                log_run_id=lr.id,
                mnemonic=curve.mnemonic,
                unit=curve.unit,
                description=curve.description,
                num_points=len(arr),
                min_value=float(np.min(valid)) if len(valid) else None,
                max_value=float(np.max(valid)) if len(valid) else None,
                data_binary=arr.tobytes(),
            ))

        created_runs.append(lr)

    if parsed.well_name and (not well.name or well.name.startswith("Well")):
        well.name = parsed.well_name
    if parsed.uwi and not well.uwi:
        well.uwi = parsed.uwi
    if created_runs:
        well.total_depth = max((r.stop_depth or 0.0) for r in created_runs)

    return created_runs


@app.post("/api/wells/{wid}/upload-las")
async def upload_las(wid: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload a LAS file and attach it to a well."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    # Read and check size
    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"File too large (max {MAX_UPLOAD_SIZE // 1024 // 1024}MB)")
    if len(content) == 0:
        raise HTTPException(400, "Empty file")

    try:
        text = content.decode('utf-8', errors='replace')
        las = LASParser.parse_string(text)
    except Exception as e:
        raise HTTPException(400, f"Failed to parse LAS file: {str(e)}")

    # Create log run
    curves_def = [
        {"mnemonic": c.mnemonic, "unit": c.unit, "description": c.description}
        for c in las.curves
    ]
    params_def = [
        {"mnemonic": p.mnemonic, "unit": p.unit, "value": p.value}
        for p in las.parameters
    ]

    log_run = LogRun(
        well_id=wid,
        run_number=len(well.log_runs) + 1,
        filename=file.filename or "unknown.las",
        las_version=las.version,
        start_depth=las.well.start,
        stop_depth=las.well.stop,
        step=las.well.step,
        null_value=las.well.null,
        num_points=len(las.depth),
        curves_json=json.dumps(curves_def),
        parameters_json=json.dumps(params_def),
    )
    db.add(log_run)
    db.flush()

    # Store curve data as binary numpy arrays
    for curve in las.curves:
        arr = las.data.get(curve.mnemonic)
        if arr is not None:
            valid = arr[~np.isnan(arr)]
            curve_record = CurveData(
                log_run_id=log_run.id,
                mnemonic=curve.mnemonic,
                unit=curve.unit,
                description=curve.description,
                num_points=len(arr),
                min_value=float(np.min(valid)) if len(valid) > 0 else None,
                max_value=float(np.max(valid)) if len(valid) > 0 else None,
                data_binary=arr.tobytes(),
            )
            db.add(curve_record)

    # Update well info from LAS if not set
    if las.well.well_name and not well.name:
        well.name = las.well.well_name
    if las.well.uwi and not well.uwi:
        well.uwi = las.well.uwi
    if las.well.operator and not well.operator:
        well.operator = las.well.operator
    if las.well.start:
        well.total_depth = las.well.stop

    lat, lon = _extract_las_coordinates(las)
    if lat is not None:
        well.latitude = lat
    if lon is not None:
        well.longitude = lon

    db.commit()

    return {
        "status": "ok",
        "log_run_id": log_run.id,
        "filename": file.filename,
        "curves": [c.mnemonic for c in las.curves],
        "num_points": len(las.depth),
        "start_depth": las.well.start,
        "stop_depth": las.well.stop,
        "step": las.well.step,
    }


@app.post("/api/wells/{wid}/upload-dlis")
async def upload_dlis(wid: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload DLIS file and attach one/many frame-runs to a well."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"File too large (max {MAX_UPLOAD_SIZE // 1024 // 1024}MB)")
    if len(content) == 0:
        raise HTTPException(400, "Empty file")

    try:
        parsed = parse_dlis_content(content, file.filename or "upload.dlis")
    except Exception as e:
        raise HTTPException(400, f"Failed to parse DLIS file: {str(e)}")

    created = _persist_non_las_runs(db, well, file.filename or "unknown.dlis", parsed, "DLIS")
    if not created:
        raise HTTPException(400, "No frame data found in DLIS")
    db.commit()

    primary = parsed.runs[0]
    return {
        "status": "ok",
        "source_format": "DLIS",
        "log_run_id": created[0].id,
        "log_run_ids": [r.id for r in created],
        "filename": file.filename,
        "runs_created": len(created),
        "curves": [c.mnemonic for c in primary.curves],
        "num_points": int(primary.depth.size),
        "start_depth": primary.start_depth,
        "stop_depth": primary.stop_depth,
        "step": primary.step,
        "version": primary.version,
    }


@app.post("/api/wells/{wid}/upload-lis")
async def upload_lis(wid: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload LIS file and attach log sets as runs to a well."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    content = await file.read()
    if len(content) > MAX_UPLOAD_SIZE:
        raise HTTPException(413, f"File too large (max {MAX_UPLOAD_SIZE // 1024 // 1024}MB)")
    if len(content) == 0:
        raise HTTPException(400, "Empty file")

    try:
        parsed = parse_lis_content(content, file.filename or "upload.lis")
    except Exception as e:
        raise HTTPException(400, f"Failed to parse LIS file: {str(e)}")

    created = _persist_non_las_runs(db, well, file.filename or "unknown.lis", parsed, "LIS")
    if not created:
        raise HTTPException(400, "No data records found in LIS")
    db.commit()

    primary = parsed.runs[0]
    return {
        "status": "ok",
        "source_format": "LIS",
        "log_run_id": created[0].id,
        "log_run_ids": [r.id for r in created],
        "filename": file.filename,
        "runs_created": len(created),
        "curves": [c.mnemonic for c in primary.curves],
        "num_points": int(primary.depth.size),
        "start_depth": primary.start_depth,
        "stop_depth": primary.stop_depth,
        "step": primary.step,
        "version": primary.version,
    }


# ─── Delete Log Run ─────────────────────────────────────────────
@app.delete("/api/log-runs/{lr_id}", status_code=204)
def delete_log_run(lr_id: int, db: Session = Depends(get_db)):
    """Delete a log run and all associated data (curves, zones, markers)."""
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first()
    if not lr:
        raise HTTPException(404, "Log run not found")
    db.query(CurveData).filter(CurveData.log_run_id == lr_id).delete()
    db.query(LogRunDepthShift).filter(LogRunDepthShift.log_run_id == lr_id).delete()
    db.delete(lr)
    db.commit()


# ─── Log Run Diff (LAS comparison) ─────────────────────────────
@app.post("/api/log-runs/diff")
def diff_log_runs(req: dict, db: Session = Depends(get_db)):
    """Compare two log runs and return curve, metadata, and stats differences."""
    log_run_a_id = req.get("log_run_a_id")
    log_run_b_id = req.get("log_run_b_id")

    if log_run_a_id is None or log_run_b_id is None:
        raise HTTPException(400, "log_run_a_id and log_run_b_id are required")

    try:
        log_run_a_id = int(log_run_a_id)
        log_run_b_id = int(log_run_b_id)
    except (TypeError, ValueError):
        raise HTTPException(400, "log_run_a_id and log_run_b_id must be integers")

    run_a = db.query(LogRun).filter(LogRun.id == log_run_a_id).first()
    run_b = db.query(LogRun).filter(LogRun.id == log_run_b_id).first()

    if not run_a:
        raise HTTPException(404, f"Log run A not found: {log_run_a_id}")
    if not run_b:
        raise HTTPException(404, f"Log run B not found: {log_run_b_id}")

    curves_a_rows = db.query(CurveData).filter(CurveData.log_run_id == run_a.id).all()
    curves_b_rows = db.query(CurveData).filter(CurveData.log_run_id == run_b.id).all()

    curves_a = {c.mnemonic: c for c in curves_a_rows}
    curves_b = {c.mnemonic: c for c in curves_b_rows}

    mnemonics_a = set(curves_a.keys())
    mnemonics_b = set(curves_b.keys())
    only_in_a = sorted(mnemonics_a - mnemonics_b)
    only_in_b = sorted(mnemonics_b - mnemonics_a)
    shared = sorted(mnemonics_a & mnemonics_b)

    def _curve_stats(curve: CurveData):
        if not curve or not curve.data_binary:
            return {"mean": None, "min": None, "max": None, "std": None, "count": 0}
        arr = np.frombuffer(curve.data_binary, dtype=np.float64)
        valid = arr[~np.isnan(arr)]
        if len(valid) == 0:
            return {"mean": None, "min": None, "max": None, "std": None, "count": 0}
        return {
            "mean": float(np.mean(valid)),
            "min": float(np.min(valid)),
            "max": float(np.max(valid)),
            "std": float(np.std(valid)),
            "count": int(len(valid)),
        }

    shared_curve_statistics = []
    for mnemonic in shared:
        a_curve = curves_a[mnemonic]
        b_curve = curves_b[mnemonic]
        stats_a = _curve_stats(a_curve)
        stats_b = _curve_stats(b_curve)

        shared_curve_statistics.append({
            "mnemonic": mnemonic,
            "unit_a": a_curve.unit,
            "unit_b": b_curve.unit,
            "description_a": a_curve.description,
            "description_b": b_curve.description,
            "num_points_a": int(a_curve.num_points or 0),
            "num_points_b": int(b_curve.num_points or 0),
            "num_points_diff": int((a_curve.num_points or 0) - (b_curve.num_points or 0)),
            "stats_a": stats_a,
            "stats_b": stats_b,
            "stats_diff": {
                "mean": None if stats_a["mean"] is None or stats_b["mean"] is None else float(stats_a["mean"] - stats_b["mean"]),
                "min": None if stats_a["min"] is None or stats_b["min"] is None else float(stats_a["min"] - stats_b["min"]),
                "max": None if stats_a["max"] is None or stats_b["max"] is None else float(stats_a["max"] - stats_b["max"]),
                "std": None if stats_a["std"] is None or stats_b["std"] is None else float(stats_a["std"] - stats_b["std"]),
                "count": int(stats_a["count"] - stats_b["count"]),
            },
        })

    metadata_differences = {
        "run_a": {
            "id": run_a.id,
            "well_id": run_a.well_id,
            "well_name": run_a.well.name if getattr(run_a, "well", None) else None,
            "filename": run_a.filename,
            "start_depth": run_a.start_depth,
            "stop_depth": run_a.stop_depth,
            "step": run_a.step,
            "num_points": run_a.num_points,
        },
        "run_b": {
            "id": run_b.id,
            "well_id": run_b.well_id,
            "well_name": run_b.well.name if getattr(run_b, "well", None) else None,
            "filename": run_b.filename,
            "start_depth": run_b.start_depth,
            "stop_depth": run_b.stop_depth,
            "step": run_b.step,
            "num_points": run_b.num_points,
        },
        "differences": {
            "start_depth": None if run_a.start_depth is None or run_b.start_depth is None else float(run_a.start_depth - run_b.start_depth),
            "stop_depth": None if run_a.stop_depth is None or run_b.stop_depth is None else float(run_a.stop_depth - run_b.stop_depth),
            "step": None if run_a.step is None or run_b.step is None else float(run_a.step - run_b.step),
            "num_points": int((run_a.num_points or 0) - (run_b.num_points or 0)),
            "well_id": int((run_a.well_id or 0) - (run_b.well_id or 0)),
            "same_well": bool(run_a.well_id == run_b.well_id),
        },
    }

    return {
        "log_run_a_id": run_a.id,
        "log_run_b_id": run_b.id,
        "curve_differences": {
            "only_in_a": only_in_a,
            "only_in_b": only_in_b,
            "shared": shared,
            "shared_count": len(shared),
        },
        "metadata_differences": metadata_differences,
        "shared_curve_statistics": shared_curve_statistics,
        "data_point_count_differences": {
            "total_curves_a": len(curves_a_rows),
            "total_curves_b": len(curves_b_rows),
            "total_curve_diff": len(curves_a_rows) - len(curves_b_rows),
            "run_num_points_a": int(run_a.num_points or 0),
            "run_num_points_b": int(run_b.num_points or 0),
            "run_num_points_diff": int((run_a.num_points or 0) - (run_b.num_points or 0)),
            "shared_curve_valid_points": [
                {
                    "mnemonic": row["mnemonic"],
                    "valid_points_a": row["stats_a"]["count"],
                    "valid_points_b": row["stats_b"]["count"],
                    "valid_points_diff": row["stats_diff"]["count"],
                }
                for row in shared_curve_statistics
            ],
        },
    }


# ─── Curve Data ───────────────────────────────────────────────
@app.get("/api/log-runs/{lr_id}/curves")
def list_curves(lr_id: int, db: Session = Depends(get_db)):
    """List available curves for a log run."""
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first()
    if not lr:
        raise HTTPException(404, "Log run not found")
    curves = db.query(CurveData).filter(CurveData.log_run_id == lr_id).all()
    return [
        {
            "id": c.id, "mnemonic": c.mnemonic, "unit": c.unit,
            "description": c.description, "num_points": c.num_points,
            "min_value": c.min_value, "max_value": c.max_value,
            "track_config": CURVE_TRACKS.get(c.mnemonic, {}),
        }
        for c in curves
    ]


@app.post("/api/log-runs/{lr_id}/data")
def get_curve_data(
    lr_id: int,
    req: dict,
    if_none_match: str = Header(default=None),
    if_modified_since: str = Header(default=None),
    db: Session = Depends(get_db),
):
    """Get curve data for specified mnemonics with optional depth-range pagination."""
    mnemonics = req.get("curve_mnemonics", [])
    start = req.get("start_depth")
    stop = req.get("stop_depth")
    step = req.get("step", 1)

    if not mnemonics:
        raise HTTPException(400, "No curves requested")

    lr = db.query(LogRun).filter(LogRun.id == lr_id).first()
    if not lr:
        raise HTTPException(404, "Log run not found")

    headers = _build_curve_cache_headers(lr_id, mnemonics, start, stop, step)
    last_modified_dt = (lr.uploaded_at or datetime.datetime.utcnow()).replace(tzinfo=datetime.timezone.utc)
    headers["Last-Modified"] = _httpdate(last_modified_dt)

    if if_none_match and if_none_match.strip() == headers["ETag"]:
        return SafeJSONResponse(status_code=304, content=None, headers=headers)
    ims = _parse_if_modified_since(if_modified_since)
    if ims is not None and last_modified_dt <= ims:
        return SafeJSONResponse(status_code=304, content=None, headers=headers)

    # Get depth curve with fallback candidates, then first curve in run
    depth_curve = db.query(CurveData).filter(
        CurveData.log_run_id == lr_id,
        CurveData.mnemonic.in_(["DEPT", "DEPTH", "MD", "TVD"])
    ).first()
    if not depth_curve:
        depth_curve = db.query(CurveData).filter(CurveData.log_run_id == lr_id).order_by(CurveData.id.asc()).first()

    depth_arr = None
    mask = None
    if depth_curve and depth_curve.data_binary:
        depth_arr = np.frombuffer(depth_curve.data_binary, dtype=np.float64).copy()
        mask = np.ones(len(depth_arr), dtype=bool)
        if start is not None:
            mask &= (depth_arr >= float(start))
        if stop is not None:
            mask &= (depth_arr <= float(stop))

    curves = db.query(CurveData).filter(
        CurveData.log_run_id == lr_id,
        CurveData.mnemonic.in_(mnemonics)
    ).all()

    result = {}
    for c in curves:
        arr = np.frombuffer(c.data_binary, dtype=np.float64).copy()
        if mask is not None and len(arr) == len(depth_arr):
            arr = arr[mask]
        if step > 1:
            arr = arr[::step]
        result[c.mnemonic] = [
            None if np.isnan(v) else round(float(v), 4)
            for v in arr
        ]

    if depth_arr is not None:
        d = depth_arr[mask] if mask is not None else depth_arr
        if step > 1:
            d = d[::step]
        result["DEPTH"] = [round(float(v), 2) for v in d]

    return SafeJSONResponse(content=result, headers=headers)


def _group_flagged_intervals(depth: np.ndarray, flags: np.ndarray):
    if depth is None or flags is None or len(depth) == 0 or len(flags) == 0:
        return []
    n = min(len(depth), len(flags))
    intervals = []
    active = False
    start_idx = 0
    for i in range(n):
        is_on = bool(flags[i])
        if is_on and not active:
            active = True
            start_idx = i
        elif not is_on and active:
            end_idx = i - 1
            intervals.append({
                "top": round(float(depth[start_idx]), 2),
                "bottom": round(float(depth[end_idx]), 2),
                "thickness": round(float(max(0.0, depth[end_idx] - depth[start_idx])), 2),
            })
            active = False
    if active:
        end_idx = n - 1
        intervals.append({
            "top": round(float(depth[start_idx]), 2),
            "bottom": round(float(depth[end_idx]), 2),
            "thickness": round(float(max(0.0, depth[end_idx] - depth[start_idx])), 2),
        })
    return intervals


@app.post("/api/log-runs/{lr_id}/shoulder-bed-correction")
def shoulder_bed_correction(lr_id: int, data: dict, db: Session = Depends(get_db)):
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first()
    if not lr:
        raise HTTPException(404, "Log run not found")

    mnemonic = str(data.get("mnemonic", "")).strip().upper()
    if not mnemonic:
        raise HTTPException(400, "mnemonic is required")

    method = str(data.get("method", "linear")).strip().lower()
    if method not in {"linear", "simandoux"}:
        raise HTTPException(400, "method must be 'linear' or 'simandoux'")

    bed_thickness_threshold = float(data.get("bed_thickness_threshold", 2.0) or 2.0)
    if bed_thickness_threshold <= 0:
        raise HTTPException(400, "bed_thickness_threshold must be > 0")

    curve_cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic == mnemonic).first()
    if not curve_cd:
        raise HTTPException(404, f"Curve {mnemonic} not found")

    depth_cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic.in_(["DEPT", "DEPTH", "MD", "TVD"])).first()
    if not depth_cd:
        raise HTTPException(404, "Depth curve not found")

    z_meas = np.frombuffer(curve_cd.data_binary, dtype=np.float64).copy()
    depth = np.frombuffer(depth_cd.data_binary, dtype=np.float64).copy()
    n = min(len(depth), len(z_meas))
    depth = depth[:n]
    z_meas = z_meas[:n]
    if int(np.sum(~np.isnan(z_meas))) < 5:
        raise HTTPException(400, "Not enough valid data points")

    rt_cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic.in_(["RT", "RESD", "RILD", "ILD"])) .first()
    rxo_cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic.in_(["RXO", "RILM", "RLLS", "MSFL"])) .first()
    gr_cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic.in_(["GR", "SGR", "CGR"])) .first()
    cali_cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic.in_(["CALI", "CAL", "HCAL"])) .first()
    bs_cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic.in_(["BS", "BIT", "BITSIZE"])) .first()

    rt = np.frombuffer(rt_cd.data_binary, dtype=np.float64).copy()[:n] if rt_cd else None
    rxo = np.frombuffer(rxo_cd.data_binary, dtype=np.float64).copy()[:n] if rxo_cd else None
    gr = np.frombuffer(gr_cd.data_binary, dtype=np.float64).copy()[:n] if gr_cd else None
    cali = np.frombuffer(cali_cd.data_binary, dtype=np.float64).copy()[:n] if cali_cd else None
    bs = np.frombuffer(bs_cd.data_binary, dtype=np.float64).copy()[:n] if bs_cd else None

    dv = np.abs(np.diff(z_meas))
    dv = dv[~np.isnan(dv)]
    if len(dv) == 0:
        raise HTTPException(400, "Cannot detect bed boundaries")
    mad = np.median(np.abs(dv - np.median(dv)))
    change_threshold = max(np.percentile(dv, 75), np.median(dv) + 3.0 * mad, 1e-9)

    boundaries = [0]
    for i in range(1, n):
        p = z_meas[i - 1]
        c = z_meas[i]
        if np.isnan(p) or np.isnan(c):
            continue
        if abs(c - p) > change_threshold:
            boundaries.append(i)
    if boundaries[-1] != n - 1:
        boundaries.append(n - 1)

    z_corr = z_meas.copy()
    thin_bed_flags = np.zeros(n, dtype=bool)
    thin_beds = []

    for b in range(len(boundaries) - 1):
        i0 = boundaries[b]
        i1 = boundaries[b + 1]
        if i1 <= i0:
            continue
        top_d = float(depth[i0])
        bot_d = float(depth[i1])
        thickness = max(0.0, bot_d - top_d)
        if thickness >= bed_thickness_threshold:
            continue

        seg = z_meas[i0:i1 + 1]
        if len(seg) == 0 or np.all(np.isnan(seg)):
            continue
        thin_bed_flags[i0:i1 + 1] = True

        up_shoulder = np.nan
        down_shoulder = np.nan
        if b > 0:
            up_shoulder = np.nanmean(z_meas[boundaries[b - 1]:i0])
        if b + 2 < len(boundaries):
            down_shoulder = np.nanmean(z_meas[i1 + 1:boundaries[b + 2] + 1])
        shoulders = [v for v in (up_shoulder, down_shoulder) if np.isfinite(v)]
        z_shoulder = float(np.mean(shoulders)) if shoulders else float(np.nanmean(seg))

        for i in range(i0, i1 + 1):
            if np.isnan(z_meas[i]):
                continue
            thickness_scale = max(0.25, min(2.0, bed_thickness_threshold / max(thickness, 0.25)))
            invasion_mod = 1.0
            if rt is not None and rxo is not None and np.isfinite(rt[i]) and np.isfinite(rxo[i]) and rt[i] > 0 and rxo[i] > 0:
                ratio = rt[i] / rxo[i]
                invasion_mod = 1.0 + 0.35 * min(2.0, abs(np.log10(max(ratio, 1e-6))))
            correction_factor = float(max(0.15, min(1.5, 0.5 * thickness_scale * invasion_mod)))

            if method == "simandoux":
                vsh = 0.2
                if gr is not None:
                    gv = gr[~np.isnan(gr)]
                    if len(gv) > 5 and np.isfinite(gr[i]):
                        gmin = float(np.percentile(gv, 5))
                        gmax = float(np.percentile(gv, 95))
                        if gmax > gmin:
                            vsh = max(0.0, min(1.0, (gr[i] - gmin) / (gmax - gmin)))
                correction_factor *= (1.0 - 0.45 * vsh)

            z_corr[i] = z_meas[i] + (z_meas[i] - z_shoulder) * correction_factor

        thin_beds.append({
            "top": round(top_d, 2),
            "bottom": round(bot_d, 2),
            "thickness": round(thickness, 2),
            "indices": [int(i0), int(i1)],
        })

    bad_hole_flags = np.zeros(n, dtype=bool)
    washout_flags = np.zeros(n, dtype=bool)
    tight_flags = np.zeros(n, dtype=bool)
    bit_size = float(np.nanmedian(bs)) if bs is not None and np.sum(~np.isnan(bs)) > 0 else 8.5
    if cali is not None:
        washout_flags = np.nan_to_num(cali > (bit_size + 1.0), nan=False)
        tight_flags = np.nan_to_num(cali < (bit_size - 0.5), nan=False)
        bad_hole_flags = washout_flags | tight_flags
    bad_hole_intervals = _group_flagged_intervals(depth, bad_hole_flags)

    invaded_flags = np.zeros(n, dtype=bool)
    invasion_indicator = [None] * n
    if rt is not None and rxo is not None:
        for i in range(n):
            if not (np.isfinite(rt[i]) and np.isfinite(rxo[i])) or rt[i] <= 0 or rxo[i] <= 0:
                continue
            ratio = rt[i] / rxo[i]
            if ratio >= 1.5:
                invaded_flags[i] = True
                invasion_indicator[i] = "deep_invasion_or_oil_mud"
            elif ratio <= 0.67:
                invaded_flags[i] = True
                invasion_indicator[i] = "shallow_invasion_or_supercharged"
            else:
                invasion_indicator[i] = "normal"

    total = max(1, n)
    qc_summary = {
        "thin_beds_pct": round(float(np.sum(thin_bed_flags)) * 100.0 / total, 2),
        "bad_hole_pct": round(float(np.sum(bad_hole_flags)) * 100.0 / total, 2),
        "invaded_pct": round(float(np.sum(invaded_flags)) * 100.0 / total, 2),
        "thin_bed_count": len(thin_beds),
        "bad_hole_interval_count": len(bad_hole_intervals),
    }

    return {
        "log_run_id": lr_id,
        "mnemonic": mnemonic,
        "method": method,
        "bed_thickness_threshold": bed_thickness_threshold,
        "corrected_curve": [None if np.isnan(v) else round(float(v), 4) for v in z_corr],
        "thin_beds": thin_beds,
        "thin_bed_flags": thin_bed_flags.astype(bool).tolist(),
        "bad_hole": {
            "bit_size": round(bit_size, 3),
            "washout_flags": washout_flags.astype(bool).tolist(),
            "tight_hole_flags": tight_flags.astype(bool).tolist(),
            "bad_hole_flags": bad_hole_flags.astype(bool).tolist(),
            "intervals": bad_hole_intervals,
        },
        "invasion": {
            "flags": invaded_flags.astype(bool).tolist(),
            "indicator": invasion_indicator,
        },
        "qc_summary": qc_summary,
    }


# ─── Formation Tops ───────────────────────────────────────────
@app.get("/api/wells/{wid}/tops")
def list_tops(wid: int, db: Session = Depends(get_db)):
    tops = db.query(FormationTop).filter(FormationTop.well_id == wid).order_by(FormationTop.depth).all()
    return [{c.name: getattr(t, c.name) for c in FormationTop.__table__.columns} for t in tops]

@app.post("/api/wells/{wid}/tops", status_code=201)
def create_top(wid: int, data: dict, db: Session = Depends(get_db)):
    t = FormationTop(well_id=wid, **data)
    db.add(t)
    db.commit()
    db.refresh(t)
    return {c.name: getattr(t, c.name) for c in FormationTop.__table__.columns}

@app.delete("/api/tops/{tid}", status_code=204)
def delete_top(tid: int, db: Session = Depends(get_db)):
    t = db.query(FormationTop).filter(FormationTop.id == tid).first()
    if not t:
        raise HTTPException(404, "Formation top not found")
    db.delete(t)
    db.commit()


# ─── Zones (persisted) ─────────────────────────────────────────
@app.get("/api/wells/{wid}/zones")
def list_zones(wid: int, db: Session = Depends(get_db)):
    zones = db.query(Zone).filter(Zone.well_id == wid).order_by(Zone.sort_order.asc(), Zone.id.asc()).all()
    return [{c.name: getattr(z, c.name) for c in Zone.__table__.columns} for z in zones]


@app.post("/api/wells/{wid}/zones", status_code=201)
def replace_zones(wid: int, data: dict, db: Session = Depends(get_db)):
    zones = data.get("zones", [])
    db.query(Zone).filter(Zone.well_id == wid).delete()
    for i, z in enumerate(zones):
        top = float(z.get("top", z.get("top_depth", 0)))
        bottom = float(z.get("bottom", z.get("bottom_depth", 0)))
        if bottom <= top:
            continue
        db.add(Zone(
            well_id=wid,
            name=str(z.get("name", f"Zone-{i+1}")),
            top_depth=top,
            bottom_depth=bottom,
            color=str(z.get("color", "#1f6feb")),
            sort_order=i,
        ))
    db.commit()
    return {"status": "ok"}


# ─── Correlation Markers (persisted) ──────────────────────────
@app.get("/api/correlation-markers")
def list_correlation_markers(well_a_id: int, well_b_id: int, db: Session = Depends(get_db)):
    q = db.query(CorrelationMarker).filter(
        ((CorrelationMarker.well_a_id == well_a_id) & (CorrelationMarker.well_b_id == well_b_id)) |
        ((CorrelationMarker.well_a_id == well_b_id) & (CorrelationMarker.well_b_id == well_a_id))
    ).order_by(CorrelationMarker.id.asc())
    rows = q.all()
    out = []
    for r in rows:
        if r.well_a_id == well_a_id:
            out.append({"aDepth": r.a_depth, "bDepth": r.b_depth, "id": r.id})
        else:
            out.append({"aDepth": r.b_depth, "bDepth": r.a_depth, "id": r.id})
    return out


@app.post("/api/correlation-markers", status_code=201)
def replace_correlation_markers(data: dict, db: Session = Depends(get_db)):
    well_a_id_raw = data.get("well_a_id")
    well_b_id_raw = data.get("well_b_id")
    if well_a_id_raw is None or well_b_id_raw is None:
        raise HTTPException(400, "well_a_id and well_b_id are required")
    well_a_id = int(well_a_id_raw)
    well_b_id = int(well_b_id_raw)
    markers = data.get("markers", [])
    db.query(CorrelationMarker).filter(
        ((CorrelationMarker.well_a_id == well_a_id) & (CorrelationMarker.well_b_id == well_b_id)) |
        ((CorrelationMarker.well_a_id == well_b_id) & (CorrelationMarker.well_b_id == well_a_id))
    ).delete()
    for m in markers:
        db.add(CorrelationMarker(
            well_a_id=well_a_id,
            well_b_id=well_b_id,
            a_depth=float(m.get("aDepth")),
            b_depth=float(m.get("bDepth")),
            label=str(m.get("label", "")),
        ))
    db.commit()
    return {"status": "ok"}


# ─── Correlation Profile (shift/stretch per pair) ─────────────
@app.get("/api/correlation-profile")
def get_correlation_profile(well_a_id: int, well_b_id: int, curve: str = "GR", db: Session = Depends(get_db)):
    p = db.query(CorrelationProfile).filter(
        ((CorrelationProfile.well_a_id == well_a_id) & (CorrelationProfile.well_b_id == well_b_id)) |
        ((CorrelationProfile.well_a_id == well_b_id) & (CorrelationProfile.well_b_id == well_a_id))
    ).order_by(CorrelationProfile.updated_at.desc()).first()
    if not p:
        return {"depth_shift": 0.0, "stretch": 1.0, "snap_to_tops": 1, "curve": curve}
    return {"depth_shift": p.depth_shift, "stretch": p.stretch, "snap_to_tops": p.snap_to_tops, "curve": p.curve}


@app.post("/api/correlation-profile", status_code=201)
def save_correlation_profile(data: dict, db: Session = Depends(get_db)):
    well_a_id_raw = data.get("well_a_id")
    well_b_id_raw = data.get("well_b_id")
    if well_a_id_raw is None or well_b_id_raw is None:
        raise HTTPException(400, "well_a_id and well_b_id are required")
    well_a_id = int(well_a_id_raw)
    well_b_id = int(well_b_id_raw)
    existing = db.query(CorrelationProfile).filter(
        ((CorrelationProfile.well_a_id == well_a_id) & (CorrelationProfile.well_b_id == well_b_id)) |
        ((CorrelationProfile.well_a_id == well_b_id) & (CorrelationProfile.well_b_id == well_a_id))
    ).first()
    if existing:
        existing.depth_shift = float(data.get("depth_shift", 0))
        existing.stretch = float(data.get("stretch", 1))
        existing.snap_to_tops = int(data.get("snap_to_tops", 1))
        existing.curve = str(data.get("curve", "GR"))
    else:
        db.add(CorrelationProfile(
            well_a_id=well_a_id, well_b_id=well_b_id,
            curve=str(data.get("curve", "GR")),
            depth_shift=float(data.get("depth_shift", 0)),
            stretch=float(data.get("stretch", 1)),
            snap_to_tops=int(data.get("snap_to_tops", 1)),
        ))
    db.commit()
    return {"status": "ok"}


# ─── Formation Top Edit ──────────────────────────────────────
@app.put("/api/tops/{tid}")
def update_top(tid: int, data: dict, db: Session = Depends(get_db)):
    t = db.query(FormationTop).filter(FormationTop.id == tid).first()
    if not t:
        raise HTTPException(404, "Formation top not found")
    for field in ("formation_name", "depth", "top_depth", "base_depth", "color", "lithology", "notes", "depth_unit"):
        if field in data:
            setattr(t, field, data[field])
    db.commit()
    db.refresh(t)
    return {c.name: getattr(t, c.name) for c in FormationTop.__table__.columns}


# ─── Bulk Export ─────────────────────────────────────────────
@app.get("/api/wells/{wid}/export-package")
def export_package(wid: int, db: Session = Depends(get_db)):
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")
    well_dict = {c.name: getattr(well, c.name) for c in Well.__table__.columns}
    tops = [{c.name: getattr(t, c.name) for c in FormationTop.__table__.columns}
            for t in db.query(FormationTop).filter(FormationTop.well_id == wid).order_by(FormationTop.depth).all()]
    zones = [{c.name: getattr(z, c.name) for c in Zone.__table__.columns}
             for z in db.query(Zone).filter(Zone.well_id == wid).order_by(Zone.sort_order.asc()).all()]
    runs = [{c.name: getattr(lr, c.name) for c in LogRun.__table__.columns}
            for lr in db.query(LogRun).filter(LogRun.well_id == wid).all()]
    return {"well": well_dict, "formation_tops": tops, "zones": zones, "log_runs": runs}


# ─── Interpretation Auditability + Delivery Bundle ───────────
SNAPSHOT_DIR = os.path.join(os.path.dirname(__file__), "artifacts", "snapshots")
os.makedirs(SNAPSHOT_DIR, exist_ok=True)
LOCK_FILE = os.path.join(os.path.dirname(__file__), "artifacts", "locks.json")


def _load_locks() -> dict:
    if not os.path.exists(LOCK_FILE):
        return {}
    try:
        with open(LOCK_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_locks(data: dict):
    os.makedirs(os.path.dirname(LOCK_FILE), exist_ok=True)
    tmp = LOCK_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
    os.replace(tmp, LOCK_FILE)


def _get_well_lock(wid: int) -> dict:
    locks = _load_locks()
    return locks.get(str(wid), {"locked": False})


def _set_well_lock(wid: int, locked: bool, actor: str = "system", snapshot_id: str = None):
    locks = _load_locks()
    current = locks.get(str(wid), {}) if isinstance(locks.get(str(wid), {}), dict) else {}
    current.update({
        "locked": bool(locked),
        "actor": actor,
        "snapshot_id": snapshot_id,
        "updated_at": datetime.datetime.utcnow().isoformat() + "Z",
    })
    locks[str(wid)] = current
    _save_locks(locks)


def _default_template_lock() -> dict:
    return {
        "locked": False,
        "locked_by": None,
        "locked_at": None,
        "reason": None,
        "signature": None,
        "signed_template": None,
        "signed_params": None,
    }


def _get_template_lock(wid: int) -> dict:
    locks = _load_locks()
    entry = locks.get(str(wid), {}) if isinstance(locks.get(str(wid), {}), dict) else {}
    tpl = entry.get("template_lock") if isinstance(entry.get("template_lock"), dict) else {}
    out = _default_template_lock()
    out.update(tpl)
    return out


def _set_template_lock(wid: int, lock_payload: dict):
    locks = _load_locks()
    entry = locks.get(str(wid), {}) if isinstance(locks.get(str(wid), {}), dict) else {}
    entry["template_lock"] = lock_payload
    locks[str(wid)] = entry
    _save_locks(locks)


def _compute_template_signature(params: dict) -> str:
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _current_petro_params_payload(db: Session, wid: int) -> dict:
    pp = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    if not pp:
        return {
            "saturation_model": "archie",
            "a": 1.0,
            "m": 2.0,
            "n": 2.0,
            "rw": 0.1,
            "vsh_cutoff": 0.35,
            "phie_cutoff": 0.10,
            "sw_cutoff": 0.60,
            "template": "custom",
        }
    return {
        "saturation_model": pp.saturation_model,
        "a": float(pp.a),
        "m": float(pp.m),
        "n": float(pp.n),
        "rw": float(pp.rw),
        "vsh_cutoff": float(pp.vsh_cutoff),
        "phie_cutoff": float(pp.phie_cutoff),
        "sw_cutoff": float(pp.sw_cutoff),
        "template": pp.template,
    }


def _snapshot_template_signature(db: Session, wid: int):
    payload = _current_petro_params_payload(db, wid)
    return payload, _compute_template_signature(payload)


def _snapshot_path(wid: int) -> str:
    return os.path.join(SNAPSHOT_DIR, f"well_{wid}.json")


def _load_snapshots(wid: int):
    p = _snapshot_path(wid)
    if not os.path.exists(p):
        return []
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        # Corrupt/partial file fallback
        return []


def _save_snapshots(wid: int, snapshots):
    # Atomic write + datetime-safe serialization
    out = _snapshot_path(wid)
    tmp = out + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(snapshots, f, indent=2, default=str)
    os.replace(tmp, out)


@app.post("/api/wells/{wid}/snapshots", status_code=201)
def create_snapshot(wid: int, data: dict = None, db: Session = Depends(get_db)):
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")
    snapshots = _load_snapshots(wid)
    snap_id = str(uuid.uuid4())

    tops = [{c.name: getattr(t, c.name) for c in FormationTop.__table__.columns}
            for t in db.query(FormationTop).filter(FormationTop.well_id == wid).order_by(FormationTop.depth).all()]
    zones = [{c.name: getattr(z, c.name) for c in Zone.__table__.columns}
             for z in db.query(Zone).filter(Zone.well_id == wid).order_by(Zone.sort_order.asc()).all()]
    params = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    params_dict = {c.name: getattr(params, c.name) for c in PetroParams.__table__.columns} if params else {}

    payload = {
        "snapshot_id": snap_id,
        "well_id": wid,
        "well_name": well.name,
        "created_at": datetime.datetime.utcnow().isoformat() + "Z",
        "label": (data or {}).get("label", f"snapshot-{len(snapshots)+1}"),
        "approved": False,
        "approved_by": None,
        "approved_at": None,
        "tops": tops,
        "zones": zones,
        "petro_params": params_dict,
    }
    snapshots.append(payload)
    _save_snapshots(wid, snapshots)
    return payload


@app.get("/api/wells/{wid}/snapshots")
def list_snapshots(wid: int):
    snaps = _load_snapshots(wid)
    return {"count": len(snaps), "snapshots": snaps}


@app.get("/api/wells/{wid}/lock-status")
def lock_status(wid: int):
    return _get_well_lock(wid)


@app.get("/api/wells/{wid}/template-lock-status")
def template_lock_status(wid: int, db: Session = Depends(get_db)):
    payload, signature = _snapshot_template_signature(db, wid)
    lock = _get_template_lock(wid)
    return {
        **lock,
        "well_id": wid,
        "current_signature": signature,
        "signature_matches": (lock.get("signature") == signature) if lock.get("locked") else None,
        "current_template": payload.get("template", "custom"),
    }


@app.post("/api/wells/{wid}/template-lock")
def lock_template(wid: int, data: dict = None, db: Session = Depends(get_db), x_user_role: str = Header(default="viewer")):
    role = (x_user_role or "viewer").lower()
    if role not in {"admin", "interpreter"}:
        raise HTTPException(403, "interpreter/admin role required")

    actor = (data or {}).get("actor", role)
    reason = (data or {}).get("reason", "Template QA signed")
    payload, signature = _snapshot_template_signature(db, wid)

    lock = {
        "locked": True,
        "locked_by": actor,
        "locked_at": datetime.datetime.utcnow().isoformat() + "Z",
        "reason": reason,
        "signature": signature,
        "signed_template": payload.get("template", "custom"),
        "signed_params": payload,
    }
    _set_template_lock(wid, lock)
    _log_audit(db, "template_lock", "well", entity_id=wid, well_id=wid,
               details=f"locked_by={actor};template={payload.get('template','custom')};sig={signature[:12]}")
    return {**lock, "well_id": wid}


@app.post("/api/wells/{wid}/template-unlock")
def unlock_template(wid: int, data: dict = None, db: Session = Depends(get_db), x_user_role: str = Header(default="viewer")):
    role = (x_user_role or "viewer").lower()
    if role != "admin":
        raise HTTPException(403, "admin role required")

    actor = (data or {}).get("actor", "admin")
    cleared = _default_template_lock()
    _set_template_lock(wid, cleared)
    _log_audit(db, "template_unlock", "well", entity_id=wid, well_id=wid, details=f"unlocked_by={actor}")
    return {**cleared, "well_id": wid, "unlocked_by": actor}


@app.post("/api/wells/{wid}/unlock")
def unlock_well(wid: int, data: dict = None, x_user_role: str = Header(default="viewer")):
    role = (x_user_role or "viewer").lower()
    if role != "admin":
        raise HTTPException(403, "admin role required")
    actor = (data or {}).get("actor", "admin")
    _set_well_lock(wid, False, actor=actor, snapshot_id=None)
    return _get_well_lock(wid)


@app.get("/api/wells/{wid}/snapshots/{snapshot_id}")
def get_snapshot(wid: int, snapshot_id: str):
    snaps = _load_snapshots(wid)
    for s in snaps:
        if s.get("snapshot_id") == snapshot_id:
            return s
    raise HTTPException(404, "Snapshot not found")


@app.post("/api/wells/{wid}/snapshots/{snapshot_id}/approve")
def approve_snapshot(wid: int, snapshot_id: str, data: dict = None):
    actor = (data or {}).get("approved_by", "interpreter")
    snaps = _load_snapshots(wid)
    for s in snaps:
        if s.get("snapshot_id") == snapshot_id:
            s["approved"] = True
            s["approved_by"] = actor
            s["approved_at"] = datetime.datetime.utcnow().isoformat() + "Z"
            _save_snapshots(wid, snaps)
            _set_well_lock(wid, True, actor=actor, snapshot_id=snapshot_id)
            return s
    raise HTTPException(404, "Snapshot not found")


@app.get("/api/wells/{wid}/snapshots/{base_id}/diff/{target_id}")
def diff_snapshot(wid: int, base_id: str, target_id: str):
    snaps = _load_snapshots(wid)
    base = next((s for s in snaps if s.get("snapshot_id") == base_id), None)
    target = next((s for s in snaps if s.get("snapshot_id") == target_id), None)
    if not base or not target:
        raise HTTPException(404, "Snapshot not found")

    def key_tops(items):
        return {(i.get("formation_name"), round(float(i.get("depth", 0)), 3)): i for i in items}

    btops = key_tops(base.get("tops", []))
    ttops = key_tops(target.get("tops", []))
    added_tops = [v for k, v in ttops.items() if k not in btops]
    removed_tops = [v for k, v in btops.items() if k not in ttops]

    bz = {(z.get("name"), z.get("top_depth"), z.get("base_depth")) for z in base.get("zones", [])}
    tz = {(z.get("name"), z.get("top_depth"), z.get("base_depth")) for z in target.get("zones", [])}

    changed_params = {}
    bp = base.get("petro_params", {})
    tp = target.get("petro_params", {})
    for k in sorted(set(bp.keys()) | set(tp.keys())):
        if bp.get(k) != tp.get(k):
            changed_params[k] = {"from": bp.get(k), "to": tp.get(k)}

    return {
        "base": base_id,
        "target": target_id,
        "added_tops": added_tops,
        "removed_tops": removed_tops,
        "added_zones": list(tz - bz),
        "removed_zones": list(bz - tz),
        "changed_petro_params": changed_params,
    }


@app.get("/api/wells/{wid}/delivery-bundle")
def delivery_bundle(wid: int, db: Session = Depends(get_db)):
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    package = export_package(wid, db)
    snaps = _load_snapshots(wid)
    manifest = {
        "well_id": wid,
        "well_name": well.name,
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "files": [
            "well.json",
            "tops.json",
            "zones.json",
            "log_runs.json",
            "snapshots.json",
            "manifest.json",
        ],
    }

    mem = io.BytesIO()
    with zipfile.ZipFile(mem, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("well.json", json.dumps(package.get("well", {}), indent=2, default=str))
        zf.writestr("tops.json", json.dumps(package.get("formation_tops", []), indent=2, default=str))
        zf.writestr("zones.json", json.dumps(package.get("zones", []), indent=2, default=str))
        zf.writestr("log_runs.json", json.dumps(package.get("log_runs", []), indent=2, default=str))
        zf.writestr("snapshots.json", json.dumps(snaps, indent=2, default=str))
        zf.writestr("manifest.json", json.dumps(manifest, indent=2, default=str))

    mem.seek(0)
    return StreamingResponse(
        mem,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{well.name}_delivery_bundle.zip"'},
    )


# ─── Curve Metadata ───────────────────────────────────────────
@app.get("/api/curve-config")
def get_curve_config():
    """Return standard curve track configurations."""
    return CURVE_TRACKS



@app.get("/api/templates")
def list_templates():
    return {"templates": PETRO_TEMPLATES}


@app.post("/api/wells/{wid}/apply-template")
def apply_template_to_well(wid: int, data: dict, db: Session = Depends(get_db)):
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    tlock = _get_template_lock(wid)
    if tlock.get("locked"):
        raise HTTPException(423, "Template is locked; unlock required before edits")

    template_name = data.get("template_name") or data.get("name") or data.get("template")
    template = _find_template(template_name) if template_name else None

    if template is None and not data.get("custom_params"):
        raise HTTPException(400, "Provide valid template_name or custom_params")

    payload = template["params"].copy() if template else {}
    cutoffs = template["recommended_cutoffs"].copy() if template else {}

    custom = data.get("custom_params") or {}
    for key in ("saturation_model", "a", "m", "n", "rw"):
        if key in custom:
            payload[key] = custom[key]
    for key in ("vsh_cutoff", "phie_cutoff", "sw_cutoff"):
        if key in custom:
            cutoffs[key] = custom[key]

    fields = {
        "saturation_model": payload.get("saturation_model", "archie"),
        "a": float(payload.get("a", 1.0)),
        "m": float(payload.get("m", 2.0)),
        "n": float(payload.get("n", 2.0)),
        "rw": float(payload.get("rw", template.get("suggested_rw", 0.1) if template else 0.1)),
        "vsh_cutoff": float(cutoffs.get("vsh_cutoff", 0.35)),
        "phie_cutoff": float(cutoffs.get("phie_cutoff", 0.10)),
        "sw_cutoff": float(cutoffs.get("sw_cutoff", 0.60)),
        "template": template["name"] if template else "custom",
    }

    existing = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    if existing:
        for k, v in fields.items():
            setattr(existing, k, v)
    else:
        db.add(PetroParams(well_id=wid, **fields))
    db.commit()

    _, signature_after = _snapshot_template_signature(db, wid)
    _log_audit(db, "apply_template", "well", entity_id=wid, well_id=wid,
               details=f"template={fields['template']};sig={signature_after[:12]}")

    summary = _build_petro_summary(wid, {
        **fields,
        "gr_min": cutoffs.get("gr_min"),
        "gr_max": cutoffs.get("gr_max"),
        "log_track_layout": template.get("log_track_layout", []) if template else data.get("log_track_layout", []),
    }, db)

    return {
        "status": "ok",
        "applied_template": template["name"] if template else "custom",
        "summary": summary,
    }


# ─── Petrophysics Parameters Persistence ──────────────────────
@app.get("/api/wells/{wid}/petro-params")
def get_petro_params(wid: int, db: Session = Depends(get_db)):
    pp = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    lock = _get_template_lock(wid)
    if not pp:
        base = {"well_id": wid, "saturation_model": "archie", "a": 1.0, "m": 2.0, "n": 2.0, "rw": 0.1,
                "vsh_cutoff": 0.35, "phie_cutoff": 0.10, "sw_cutoff": 0.60, "template": "custom"}
        base["template_lock"] = lock
        return base
    out = {c.name: getattr(pp, c.name) for c in PetroParams.__table__.columns}
    out["template_lock"] = lock
    return out


@app.post("/api/wells/{wid}/petro-params")
def save_petro_params(wid: int, data: dict, db: Session = Depends(get_db)):
    tlock = _get_template_lock(wid)
    if tlock.get("locked"):
        raise HTTPException(423, "Template is locked; unlock required before edits")

    existing = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    fields = ["saturation_model", "a", "m", "n", "rw", "vsh_cutoff", "phie_cutoff", "sw_cutoff", "template"]
    if existing:
        for f in fields:
            if f in data:
                val = data[f]
                if f in ("a", "m", "n", "rw", "vsh_cutoff", "phie_cutoff", "sw_cutoff"):
                    val = float(val)
                setattr(existing, f, val)
    else:
        kwargs = {"well_id": wid}
        for f in fields:
            if f in data:
                val = data[f]
                if f in ("a", "m", "n", "rw", "vsh_cutoff", "phie_cutoff", "sw_cutoff"):
                    val = float(val)
                kwargs[f] = val
        db.add(PetroParams(**kwargs))
    db.commit()
    _, signature_after = _snapshot_template_signature(db, wid)
    _log_audit(db, "save_petro_params", "well", entity_id=wid, well_id=wid,
               details=f"template={data.get('template','custom')};sig={signature_after[:12]}")
    return {"status": "ok", "signature": signature_after}


@app.post("/api/wells/{wid}/rw-estimation")
def estimate_rw(wid: int, data: dict, db: Session = Depends(get_db)):
    """Estimate formation water resistivity (Rw) using SP, Ro, and Hingle workflows."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    method = str(data.get("method", "all")).strip().lower()
    if method not in {"sp", "ro", "hingle", "all"}:
        raise HTTPException(400, "method must be one of: sp, ro, hingle, all")

    pp = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    a_val = float(data.get("a", pp.a if pp and pp.a is not None else 1.0))
    m_default = float(pp.m) if pp and pp.m is not None else 2.0

    results = {
        "method_requested": method,
        "inputs": {},
        "methods": {},
        "catalog": {
            "fresh_water_ohm_m": [0.5, 1.0],
            "saline_water_ohm_m": [0.01, 0.1],
            "typical_gulf_coast_ohm_m": [0.02, 0.05],
            "typical_north_sea_ohm_m": [0.03, 0.08],
        },
    }

    rw_candidates = []
    weights = []

    if method in {"sp", "all"}:
        r = {"rw": None, "rw_77f": None, "confidence": 0.0, "notes": []}
        try:
            rmf = float(data.get("rmf"))
            ssp = float(data.get("ssp"))
            t_val = float(data.get("temperature"))
            t_unit = str(data.get("temperature_unit", "F")).strip().upper()
            if t_unit not in {"F", "C"}:
                raise ValueError("temperature_unit must be F or C")
            t_f = t_val if t_unit == "F" else (t_val * 9.0 / 5.0 + 32.0)
            if rmf <= 0:
                raise ValueError("Rmf must be > 0")
            if t_f <= -459.67:
                raise ValueError("Temperature below absolute zero")

            k = 61.0 + 0.133 * t_f
            denom = k * t_f
            if denom == 0:
                raise ValueError("Invalid temperature produces zero denominator")

            rw = rmf * (10.0 ** (-ssp / denom))
            rw_77 = rw * ((t_f + 6.77) / (77.0 + 6.77))

            r.update({
                "rw": float(rw),
                "rw_77f": float(rw_77),
                "k": float(k),
                "temperature_f": float(t_f),
                "formula": "Rw = Rmf * 10^(-SSP/(K*T)), K=61+0.133*T(F)",
                "confidence": 0.75,
            })
            rw_candidates.append(float(rw_77))
            weights.append(0.75)
            results["inputs"].update({"rmf": rmf, "ssp": ssp, "temperature": t_val, "temperature_unit": t_unit})
        except Exception as e:
            r["notes"].append(str(e))
        results["methods"]["sp"] = r

    if method in {"ro", "all"}:
        r = {"rw": None, "a": a_val, "confidence": 0.0, "notes": []}
        try:
            rt_clean = float(data.get("rt_clean"))
            phi_clean = float(data.get("phi_clean"))
            m_val = float(data.get("m", m_default))
            if rt_clean <= 0:
                raise ValueError("Rt_clean must be > 0")
            if phi_clean <= 0 or phi_clean > 1.0:
                raise ValueError("phi_clean must be in (0,1]")
            rw = rt_clean * (phi_clean ** m_val)
            r.update({
                "rw": float(rw),
                "m": float(m_val),
                "formula": "Rw = Rt_clean * phi_clean^m",
                "confidence": 0.80,
            })
            rw_candidates.append(float(rw))
            weights.append(0.80)
            results["inputs"].update({"rt_clean": rt_clean, "phi_clean": phi_clean, "m": m_val})
        except Exception as e:
            r["notes"].append(str(e))
        results["methods"]["ro"] = r

    if method in {"hingle", "all"}:
        r = {"rw": None, "r2": None, "a": a_val, "confidence": 0.0, "notes": []}
        try:
            rt_curve = str(data.get("rt_curve", "RT")).upper()
            phi_curve = str(data.get("phi_curve", "NPHI")).upper()
            lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
            if not lr:
                raise ValueError("No log run found")
            rt_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == rt_curve).first()
            phi_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == phi_curve).first()
            if not rt_cd or not phi_cd:
                raise ValueError("Required curves not found for Hingle")

            rt = np.frombuffer(rt_cd.data_binary, dtype=np.float64).copy()
            phi = np.frombuffer(phi_cd.data_binary, dtype=np.float64).copy()
            npts = min(len(rt), len(phi))
            rt = rt[:npts]
            phi = phi[:npts]
            with np.errstate(divide="ignore", invalid="ignore"):
                inv_rt = np.where(rt > 0, 1.0 / rt, np.nan)
            valid = (~np.isnan(inv_rt)) & (~np.isnan(phi)) & np.isfinite(inv_rt) & np.isfinite(phi) & (phi >= 0) & (phi <= 1.0)
            if np.sum(valid) < 3:
                raise ValueError("Not enough valid points for Hingle fit")

            x = phi[valid]
            y = inv_rt[valid]
            slope, intercept = np.polyfit(x, y, 1)
            yhat = slope * x + intercept
            ss_res = float(np.sum((y - yhat) ** 2))
            ss_tot = float(np.sum((y - np.mean(y)) ** 2))
            r2 = 1.0 - (ss_res / ss_tot) if ss_tot > 0 else 0.0

            rwa_intercept = float(intercept)
            rw_est = (rwa_intercept / a_val) if (a_val > 0 and rwa_intercept > 0) else None
            conf = max(0.0, min(1.0, r2)) * (1.0 if np.sum(valid) >= 50 else max(0.4, np.sum(valid) / 50.0))

            sample_step = max(1, len(x) // 400)
            x_s = x[::sample_step]
            y_s = y[::sample_step]
            r.update({
                "rw": float(rw_est) if rw_est is not None else None,
                "intercept_rwa": float(rwa_intercept),
                "slope": float(slope),
                "r2": round(float(r2), 6),
                "points": int(np.sum(valid)),
                "formula": "Linear fit on Hingle axes: (1/Rt) vs phi; intercept(phi=0)=Rw*a",
                "confidence": float(conf),
                "crossplot": {
                    "x_phi": [round(float(v), 6) for v in x_s],
                    "y_inv_rt": [round(float(v), 6) for v in y_s],
                },
            })
            if rw_est is not None:
                rw_candidates.append(float(rw_est))
                weights.append(max(0.25, float(conf)))
            results["inputs"].update({"rt_curve": rt_curve, "phi_curve": phi_curve})
        except Exception as e:
            r["notes"].append(str(e))
        results["methods"]["hingle"] = r

    if rw_candidates:
        wsum = sum(weights) if sum(weights) > 0 else float(len(rw_candidates))
        recommended = float(sum(v * w for v, w in zip(rw_candidates, weights)) / wsum)
        confidence = min(1.0, max(weights) * (0.6 + 0.4 * min(1.0, len(rw_candidates) / 3.0)))
    else:
        recommended = None
        confidence = 0.0

    results["recommended_rw"] = recommended
    results["confidence_score"] = round(confidence * 100.0, 1)
    return results


# ─── Sensitivity Analysis (Monte Carlo) ───────────────────────
@app.post("/api/wells/{wid}/sensitivity")
def sensitivity_analysis(wid: int, data: dict, db: Session = Depends(get_db)):
    """Monte Carlo uncertainty for net pay with P10/P50/P90 + driver ranking."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")
    lr_id = data.get("log_run_id")
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    rt_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["RT", "RESD", "RILD", "ILD"])).first()
    nphi_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["NPHI", "NPHI_LS"])).first()
    gr_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["GR", "SGR", "CGR"])).first()
    if not rt_cd or not nphi_cd:
        raise HTTPException(400, "Need RT and NPHI curves")

    rt = np.frombuffer(rt_cd.data_binary, dtype=np.float64).copy()
    nphi = np.frombuffer(nphi_cd.data_binary, dtype=np.float64).copy()
    gr = np.frombuffer(gr_cd.data_binary, dtype=np.float64).copy() if gr_cd else np.zeros_like(rt)

    base_a = max(float(data.get("a", 1.0)), 1e-6)
    base_m = max(float(data.get("m", 2.0)), 1e-6)
    base_n = max(float(data.get("n", 2.0)), 1e-6)
    base_rw = max(float(data.get("rw", 0.1)), 1e-6)
    base_vsh_cut = float(data.get("vsh_cutoff", 0.35))
    base_phie_cut = float(data.get("phie_cutoff", 0.10))
    base_sw_cut = float(data.get("sw_cutoff", 0.60))

    n_iter = max(50, min(int(data.get("iterations", 500)), 5000))
    pct_common = max(0.0, min(float(data.get("variation_pct", 30)) / 100.0, 0.95))

    rw_pct = max(0.0, min(float(data.get("rw_variation_pct", pct_common * 100.0)) / 100.0, 0.95))
    m_pct = max(0.0, min(float(data.get("m_variation_pct", pct_common * 100.0)) / 100.0, 0.95))
    n_pct = max(0.0, min(float(data.get("n_variation_pct", pct_common * 100.0)) / 100.0, 0.95))
    vsh_cut_pct = max(0.0, min(float(data.get("vsh_cutoff_variation_pct", pct_common * 100.0)) / 100.0, 0.95))
    phie_cut_pct = max(0.0, min(float(data.get("phie_cutoff_variation_pct", pct_common * 100.0)) / 100.0, 0.95))
    sw_cut_pct = max(0.0, min(float(data.get("sw_cutoff_variation_pct", pct_common * 100.0)) / 100.0, 0.95))

    model = data.get("saturation_model", "archie")
    seed = data.get("seed")
    start_depth = data.get("start_depth")
    stop_depth = data.get("stop_depth")

    gr_valid = gr[~np.isnan(gr) & (gr > 0)]
    gr_min = float(np.min(gr_valid)) if len(gr_valid) else 0.0
    gr_max = float(np.max(gr_valid)) if len(gr_valid) else 150.0
    if gr_max == gr_min:
        gr_max = gr_min + 1.0

    step = float(lr.step) if lr.step else 0.5
    if step == 0:
        step = 0.5

    depth_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    depth_arr = np.frombuffer(depth_cd.data_binary, dtype=np.float64).copy() if depth_cd else None
    depth_mask = np.ones(len(rt), dtype=bool)
    if depth_arr is not None and (start_depth is not None or stop_depth is not None):
        if start_depth is not None:
            depth_mask &= (depth_arr >= float(start_depth))
        if stop_depth is not None:
            depth_mask &= (depth_arr <= float(stop_depth))

    vsh = np.clip((gr - gr_min) / (gr_max - gr_min), 0.0, 1.0)
    phi_base = np.maximum(0.0, nphi * (1.0 - vsh))
    valid = depth_mask & np.isfinite(rt) & np.isfinite(phi_base) & (rt > 0) & (phi_base >= 0.01)

    rng = np.random.default_rng(seed if seed is not None else None)

    def _sample(base: float, pct: float, lo: float, hi: float) -> float:
        if pct <= 0:
            return float(np.clip(base, lo, hi))
        return float(np.clip(base * (1.0 + rng.uniform(-pct, pct)), lo, hi))

    param_track = {
        "rw": np.zeros(n_iter, dtype=np.float64),
        "m": np.zeros(n_iter, dtype=np.float64),
        "n": np.zeros(n_iter, dtype=np.float64),
        "vsh_cutoff": np.zeros(n_iter, dtype=np.float64),
        "phie_cutoff": np.zeros(n_iter, dtype=np.float64),
        "sw_cutoff": np.zeros(n_iter, dtype=np.float64),
    }
    net_pays = np.zeros(n_iter, dtype=np.float64)

    for i in range(n_iter):
        a_v = base_a
        m_v = _sample(base_m, m_pct, 0.2, 8.0)
        n_v = _sample(base_n, n_pct, 0.2, 8.0)
        rw_v = _sample(base_rw, rw_pct, 1e-6, 5.0)
        vsh_cut = _sample(base_vsh_cut, vsh_cut_pct, 0.0, 1.0)
        phie_cut = _sample(base_phie_cut, phie_cut_pct, 0.0, 0.6)
        sw_cut = _sample(base_sw_cut, sw_cut_pct, 0.0, 1.0)

        phi = phi_base
        rt_safe = np.maximum(rt, 1e-6)

        if model == "simandoux":
            inner = (a_v * rw_v) / (np.power(phi, m_v) * rt_safe + 1e-10) - vsh * rw_v / (0.4 * np.maximum(phi, 1e-6))
            sw = np.sqrt(np.maximum(0.0, inner))
        elif model == "indonesian":
            denom = np.sqrt(np.power(phi, m_v) / (a_v * rw_v + 1e-10)) + np.sqrt(np.maximum(0.0, vsh)) / np.sqrt(rt_safe)
            sw = np.where(denom > 0, 1.0 / (np.sqrt(rt_safe) * denom), 1.0)
        else:
            sw = np.power(np.maximum((a_v * rw_v) / (np.power(phi, m_v) * rt_safe + 1e-10), 0.0), 1.0 / n_v)
        sw = np.clip(sw, 0.0, 1.0)

        pay_mask = valid & (vsh < vsh_cut) & (phi > phie_cut) & (sw < sw_cut)
        net_pays[i] = float(np.sum(pay_mask) * step)

        param_track["rw"][i] = rw_v
        param_track["m"][i] = m_v
        param_track["n"][i] = n_v
        param_track["vsh_cutoff"][i] = vsh_cut
        param_track["phie_cutoff"][i] = phie_cut
        param_track["sw_cutoff"][i] = sw_cut

    p90 = float(np.percentile(net_pays, 10)) if len(net_pays) else 0.0  # conservative (low)
    p50 = float(np.percentile(net_pays, 50)) if len(net_pays) else 0.0
    p10 = float(np.percentile(net_pays, 90)) if len(net_pays) else 0.0  # optimistic (high)

    drivers = []
    for key, vals in param_track.items():
        if np.std(vals) <= 1e-12 or np.std(net_pays) <= 1e-12:
            corr = 0.0
        else:
            corr = float(np.corrcoef(vals, net_pays)[0, 1])
            if not np.isfinite(corr):
                corr = 0.0
        drivers.append({
            "parameter": key,
            "correlation": round(corr, 4),
            "impact": round(abs(corr), 4),
        })
    drivers.sort(key=lambda x: x["impact"], reverse=True)

    bin_edges = np.histogram_bin_edges(net_pays, bins=20)
    hist_counts = np.histogram(net_pays, bins=bin_edges)[0]

    return {
        "iterations": n_iter,
        "variation_pct": round(pct_common * 100, 1),
        "variation_profile": {
            "rw": round(rw_pct * 100, 1),
            "m": round(m_pct * 100, 1),
            "n": round(n_pct * 100, 1),
            "vsh_cutoff": round(vsh_cut_pct * 100, 1),
            "phie_cutoff": round(phie_cut_pct * 100, 1),
            "sw_cutoff": round(sw_cut_pct * 100, 1),
        },
        "p10_net_pay": round(p10, 2),
        "p50_net_pay": round(p50, 2),
        "p90_net_pay": round(p90, 2),
        "mean_net_pay": round(float(np.mean(net_pays)), 2) if len(net_pays) else 0,
        "std_net_pay": round(float(np.std(net_pays)), 2) if len(net_pays) else 0,
        "histogram_bins": [round(float(x), 2) for x in bin_edges.tolist()],
        "histogram_counts": hist_counts.tolist(),
        "drivers": drivers,
    }


# ─── Well Comparison (multi-well stats) ───────────────────────
@app.get("/api/projects/{pid}/well-comparison")
def well_comparison(pid: int, db: Session = Depends(get_db)):
    """Return side-by-side stats for all wells in a project."""
    wells = db.query(Well).filter(Well.project_id == pid).all()
    result = []
    for w in wells:
        lr = db.query(LogRun).filter(LogRun.well_id == w.id).order_by(LogRun.id.desc()).first()
        curves = []
        if lr:
            cds = db.query(CurveData).filter(CurveData.log_run_id == lr.id).all()
            for cd in cds:
                arr = np.frombuffer(cd.data_binary, dtype=np.float64)
                valid = arr[~np.isnan(arr)]
                curves.append({
                    "mnemonic": cd.mnemonic,
                    "unit": cd.unit,
                    "count": int(len(valid)),
                    "min": round(float(np.min(valid)), 4) if len(valid) else None,
                    "max": round(float(np.max(valid)), 4) if len(valid) else None,
                    "mean": round(float(np.mean(valid)), 4) if len(valid) else None,
                })
        tops = db.query(FormationTop).filter(FormationTop.well_id == w.id).order_by(FormationTop.depth).all()
        zones = db.query(Zone).filter(Zone.well_id == w.id).order_by(Zone.sort_order).all()
        result.append({
            "well_id": w.id,
            "name": w.name,
            "uwi": w.uwi,
            "operator": w.operator,
            "total_depth": w.total_depth,
            "depth_unit": w.depth_unit,
            "log_run_count": db.query(LogRun).filter(LogRun.well_id == w.id).count(),
            "curve_count": len(curves),
            "top_count": len(tops),
            "zone_count": len(zones),
            "curves": curves,
        })
    return {"project_id": pid, "wells": result}



# ─── Bulk LAS Upload ──────────────────────────────────────────
@app.post("/api/wells/{wid}/bulk-upload")
async def bulk_upload_las(wid: int, files: list = [], db: Session = Depends(get_db)):
    """Upload multiple LAS files to a well."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")
    results = []
    for file in files:
        try:
            content = await file.read()
            if len(content) > MAX_UPLOAD_SIZE or len(content) == 0:
                results.append({"filename": file.filename, "status": "skipped", "reason": "size"})
                continue
            text = content.decode("utf-8", errors="replace")
            las = LASParser.parse_string(text)
            curves_def = [{"mnemonic": c.mnemonic, "unit": c.unit, "description": c.description} for c in las.curves]
            lr = LogRun(
                well_id=wid, run_number=len(well.log_runs) + 1,
                filename=file.filename or "unknown.las", las_version=las.version,
                start_depth=las.well.start, stop_depth=las.well.stop,
                step=las.well.step, null_value=las.well.null, num_points=len(las.depth),
                curves_json=json.dumps(curves_def),
            )
            db.add(lr)
            db.flush()
            for curve in las.curves:
                arr = las.data.get(curve.mnemonic)
                if arr is not None:
                    valid = arr[~np.isnan(arr)]
                    db.add(CurveData(
                        log_run_id=lr.id, mnemonic=curve.mnemonic,
                        unit=curve.unit, description=curve.description,
                        num_points=len(arr),
                        min_value=float(np.min(valid)) if len(valid) else None,
                        max_value=float(np.max(valid)) if len(valid) else None,
                        data_binary=arr.tobytes(),
                    ))
            db.flush()
            results.append({"filename": file.filename, "status": "ok", "log_run_id": lr.id, "curves": len(las.curves), "points": len(las.depth)})
        except Exception as e:
            results.append({"filename": file.filename, "status": "error", "reason": str(e)[:200]})
    db.commit()
    return {"uploaded": len([r for r in results if r["status"] == "ok"]), "results": results}


# ─── Depth Shift per Log Run ──────────────────────────────────

@app.get("/api/log-runs/{lr_id}/depth-shift")
def get_depth_shift(lr_id: int, db: Session = Depends(get_db)):
    ds = db.query(LogRunDepthShift).filter(LogRunDepthShift.log_run_id == lr_id).first()
    if not ds:
        return {"log_run_id": lr_id, "shift": 0.0, "stretch": 1.0, "notes": ""}
    return {"log_run_id": lr_id, "shift": ds.shift, "stretch": ds.stretch, "notes": ds.notes or ""}


@app.post("/api/log-runs/{lr_id}/depth-shift")
def save_depth_shift(lr_id: int, data: dict, db: Session = Depends(get_db)):
    existing = db.query(LogRunDepthShift).filter(LogRunDepthShift.log_run_id == lr_id).first()
    if existing:
        existing.shift = float(data.get("shift", 0))
        existing.stretch = float(data.get("stretch", 1))
        existing.notes = str(data.get("notes", ""))
    else:
        db.add(LogRunDepthShift(
            log_run_id=lr_id,
            shift=float(data.get("shift", 0)),
            stretch=float(data.get("stretch", 1)),
            notes=str(data.get("notes", "")),
        ))
    db.commit()
    return {"status": "ok"}


# ─── Annotations CRUD ────────────────────────────────────────
@app.get("/api/wells/{wid}/annotations")
def list_annotations(wid: int, db: Session = Depends(get_db)):
    anns = db.query(Annotation).filter(Annotation.well_id == wid).order_by(Annotation.depth).all()
    return [{c.name: getattr(a, c.name) for c in Annotation.__table__.columns} for a in anns]


@app.post("/api/wells/{wid}/annotations", status_code=201)
def create_annotation(wid: int, data: dict, db: Session = Depends(get_db)):
    ann = Annotation(
        well_id=wid,
        depth=float(data["depth"]),
        text=str(data.get("text", "")),
        annotation_type=str(data.get("annotation_type", "note")),
        color=str(data.get("color", "#f39c12")),
    )
    db.add(ann)
    db.commit()
    db.refresh(ann)
    return {c.name: getattr(ann, c.name) for c in Annotation.__table__.columns}


@app.delete("/api/annotations/{aid}")
def delete_annotation(aid: int, db: Session = Depends(get_db)):
    ann = db.query(Annotation).filter(Annotation.id == aid).first()
    if not ann:
        raise HTTPException(404, "Annotation not found")
    db.delete(ann)
    db.commit()
    return {"status": "ok"}


# ─── DST / RFT Pressure Data ──────────────────────────────────
@app.post("/api/wells/{wid}/dst", status_code=201)
def create_dst(wid: int, data: dict, db: Session = Depends(get_db)):
    row = DSTTest(
        well_id=wid,
        test_number=str(data.get("test_number", "")),
        top_depth=float(data.get("top_depth")),
        bottom_depth=float(data.get("bottom_depth")),
        formation=str(data.get("formation", "")),
        choke_size=str(data.get("choke_size", "")),
        flow_rate=float(data["flow_rate"]) if data.get("flow_rate") is not None else None,
        shut_in_pressure=float(data["shut_in_pressure"]) if data.get("shut_in_pressure") is not None else None,
        flowing_pressure=float(data["flowing_pressure"]) if data.get("flowing_pressure") is not None else None,
        temperature=float(data["temperature"]) if data.get("temperature") is not None else None,
        permeability=float(data["permeability"]) if data.get("permeability") is not None else None,
        skin=float(data["skin"]) if data.get("skin") is not None else None,
        result=str(data.get("result", "")),
        notes=str(data.get("notes", "")),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {c.name: getattr(row, c.name) for c in DSTTest.__table__.columns}


@app.get("/api/wells/{wid}/dst")
def list_dst(wid: int, db: Session = Depends(get_db)):
    rows = db.query(DSTTest).filter(DSTTest.well_id == wid).order_by(DSTTest.top_depth.asc(), DSTTest.id.asc()).all()
    return [{c.name: getattr(r, c.name) for c in DSTTest.__table__.columns} for r in rows]


@app.post("/api/wells/{wid}/rft", status_code=201)
def create_rft(wid: int, data: dict, db: Session = Depends(get_db)):
    row = RFTPoint(
        well_id=wid,
        depth=float(data.get("depth")),
        pressure=float(data.get("pressure")),
        mobility=float(data["mobility"]) if data.get("mobility") is not None else None,
        fluid_type=str(data.get("fluid_type", "unknown") or "unknown").lower(),
        sample_recovered=str(data.get("sample_recovered", "")),
        notes=str(data.get("notes", "")),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {c.name: getattr(row, c.name) for c in RFTPoint.__table__.columns}


@app.get("/api/wells/{wid}/rft")
def list_rft(wid: int, db: Session = Depends(get_db)):
    rows = db.query(RFTPoint).filter(RFTPoint.well_id == wid).order_by(RFTPoint.depth.asc(), RFTPoint.id.asc()).all()
    return [{c.name: getattr(r, c.name) for c in RFTPoint.__table__.columns} for r in rows]


COMPLETION_COMPONENT_TYPES = {"casing", "tubing", "packer", "perforation", "screen", "liner", "cement", "pump", "valve"}


@app.post("/api/wells/{wid}/completion", status_code=201)
def create_completion_component(wid: int, data: dict, db: Session = Depends(get_db)):
    ctype = str(data.get("component_type", "")).strip().lower()
    if ctype not in COMPLETION_COMPONENT_TYPES:
        raise HTTPException(400, f"Invalid component_type. Allowed: {sorted(COMPLETION_COMPONENT_TYPES)}")

    top = float(data.get("depth_top"))
    base = float(data.get("depth_base"))
    if base < top:
        top, base = base, top

    row = CompletionData(
        well_id=wid,
        depth_top=top,
        depth_base=base,
        component_type=ctype,
        size=str(data.get("size", "") or ""),
        description=str(data.get("description", "") or ""),
        notes=str(data.get("notes", "") or ""),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {c.name: getattr(row, c.name) for c in CompletionData.__table__.columns}


@app.get("/api/wells/{wid}/completion")
def list_completion_components(wid: int, db: Session = Depends(get_db)):
    rows = db.query(CompletionData).filter(CompletionData.well_id == wid).order_by(CompletionData.depth_top.asc(), CompletionData.id.asc()).all()
    return [{c.name: getattr(r, c.name) for c in CompletionData.__table__.columns} for r in rows]


@app.delete("/api/completion/{cid}")
def delete_completion_component(cid: int, db: Session = Depends(get_db)):
    row = db.query(CompletionData).filter(CompletionData.id == cid).first()
    if not row:
        raise HTTPException(404, "Completion component not found")
    db.delete(row)
    db.commit()
    return {"status": "ok"}


@app.post("/api/wells/{wid}/completion/upload-csv")
async def upload_completion_csv(wid: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    text_data = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text_data))
    inserted = 0

    for rec in reader:
        if not rec:
            continue
        ctype = str(rec.get("component_type") or rec.get("ComponentType") or rec.get("type") or "").strip().lower()
        if ctype not in COMPLETION_COMPONENT_TYPES:
            continue
        top_raw = rec.get("depth_top") or rec.get("DepthTop") or rec.get("top")
        base_raw = rec.get("depth_base") or rec.get("DepthBase") or rec.get("base")
        if top_raw in (None, "") or base_raw in (None, ""):
            continue
        try:
            top = float(str(top_raw).strip())
            base = float(str(base_raw).strip())
        except Exception:
            continue
        if base < top:
            top, base = base, top

        row = CompletionData(
            well_id=wid,
            depth_top=top,
            depth_base=base,
            component_type=ctype,
            size=str(rec.get("size") or rec.get("Size") or ""),
            description=str(rec.get("description") or rec.get("Description") or ""),
            notes=str(rec.get("notes") or rec.get("Notes") or ""),
        )
        db.add(row)
        inserted += 1

    db.commit()
    return {"status": "ok", "inserted": inserted}


@app.post("/api/wells/{wid}/rft/upload-csv")
async def upload_rft_csv(wid: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    text_data = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text_data))
    inserted = 0
    for rec in reader:
        if not rec:
            continue
        depth_raw = rec.get("depth") or rec.get("Depth") or rec.get("DEPTH")
        press_raw = rec.get("pressure") or rec.get("Pressure") or rec.get("PRESSURE")
        if depth_raw is None or press_raw is None:
            continue
        try:
            depth = float(str(depth_raw).strip())
            pressure = float(str(press_raw).strip())
        except Exception:
            continue
        row = RFTPoint(
            well_id=wid,
            depth=depth,
            pressure=pressure,
            mobility=_safe_float(rec.get("mobility")),
            fluid_type=str(rec.get("fluid_type") or rec.get("FluidType") or rec.get("fluid") or "unknown").lower(),
            sample_recovered=str(rec.get("sample_recovered") or rec.get("sample") or ""),
            notes=str(rec.get("notes") or ""),
        )
        db.add(row)
        inserted += 1
    db.commit()
    return {"status": "ok", "inserted": inserted}


@app.get("/api/wells/{wid}/rft/pressure-gradient")
def rft_pressure_gradient(wid: int, db: Session = Depends(get_db)):
    rows = db.query(RFTPoint).filter(RFTPoint.well_id == wid).order_by(RFTPoint.depth.asc()).all()
    points = [{c.name: getattr(r, c.name) for c in RFTPoint.__table__.columns} for r in rows]
    valid = [{
        "id": r.id,
        "depth": float(r.depth),
        "pressure": float(r.pressure),
        "fluid_type": (r.fluid_type or "unknown").lower(),
    } for r in rows if r.depth is not None and r.pressure is not None]
    if len(valid) < 2:
        return {
            "count": len(valid),
            "points": points,
            "overall": None,
            "by_fluid": [],
            "fluid_segments": [],
            "fluid_contacts": [],
            "gradient_lines": {},
            "pressure_regime_summary": {},
            "formation_pressure": {"points": [], "intervals": []},
        }

    fluid_windows = {
        "gas": (0.05, 0.20),
        "oil": (0.25, 0.35),
        "water": (0.40, 0.50),
    }

    def classify_fluid_by_gradient(grad):
        if grad is None or not np.isfinite(grad):
            return "unknown"
        for name, (lo, hi) in fluid_windows.items():
            if lo <= grad <= hi:
                return name
        return "unknown"

    def classify_pressure_regime(grad):
        if grad is None or not np.isfinite(grad):
            return "unknown"
        if grad < 0.43:
            return "underpressure"
        if grad > 0.47:
            return "overpressure"
        return "normal"

    depths = np.array([v["depth"] for v in valid], dtype=float)
    pressures = np.array([v["pressure"] for v in valid], dtype=float)
    slope, intercept = np.polyfit(depths, pressures, 1)
    overall = {
        "gradient": float(slope),
        "intercept": float(intercept),
        "equation": f"P = {slope:.6f}*Depth + {intercept:.3f}",
        "fluid_guess": classify_fluid_by_gradient(float(slope)),
        "regime": classify_pressure_regime(float(slope)),
    }

    # Segment data by local two-point gradients into contiguous fluid-gradient clusters.
    for i in range(len(valid)):
        if i == 0:
            pair_grad = (valid[i + 1]["pressure"] - valid[i]["pressure"]) / max(valid[i + 1]["depth"] - valid[i]["depth"], 1e-9)
        elif i == len(valid) - 1:
            pair_grad = (valid[i]["pressure"] - valid[i - 1]["pressure"]) / max(valid[i]["depth"] - valid[i - 1]["depth"], 1e-9)
        else:
            pair_grad = (valid[i + 1]["pressure"] - valid[i - 1]["pressure"]) / max(valid[i + 1]["depth"] - valid[i - 1]["depth"], 1e-9)
        valid[i]["pair_gradient"] = float(pair_grad)
        valid[i]["fluid_from_gradient"] = classify_fluid_by_gradient(valid[i]["pair_gradient"])
        valid[i]["pressure_regime"] = classify_pressure_regime(valid[i]["pair_gradient"])

    segments = []
    seg_start = 0
    for i in range(1, len(valid)):
        if valid[i]["fluid_from_gradient"] != valid[i - 1]["fluid_from_gradient"]:
            segments.append((seg_start, i - 1))
            seg_start = i
    segments.append((seg_start, len(valid) - 1))

    fluid_segments = []
    for sidx, (a, b) in enumerate(segments):
        seg_pts = valid[a:b + 1]
        if len(seg_pts) < 2:
            seg_slope = seg_pts[0]["pair_gradient"]
            seg_intercept = seg_pts[0]["pressure"] - seg_slope * seg_pts[0]["depth"]
        else:
            seg_d = np.array([p["depth"] for p in seg_pts], dtype=float)
            seg_p = np.array([p["pressure"] for p in seg_pts], dtype=float)
            seg_slope, seg_intercept = np.polyfit(seg_d, seg_p, 1)
        fluid_guess = classify_fluid_by_gradient(float(seg_slope))
        fluid_segments.append({
            "segment_index": sidx,
            "start_depth": float(seg_pts[0]["depth"]),
            "end_depth": float(seg_pts[-1]["depth"]),
            "count": len(seg_pts),
            "gradient": float(seg_slope),
            "intercept": float(seg_intercept),
            "fluid_type": fluid_guess,
            "equation": f"P = {seg_slope:.6f}*Depth + {seg_intercept:.3f}",
        })

    fluid_contacts = []
    for i in range(1, len(fluid_segments)):
        prev_seg = fluid_segments[i - 1]
        curr_seg = fluid_segments[i]
        if prev_seg["fluid_type"] != curr_seg["fluid_type"]:
            contact_depth = 0.5 * (prev_seg["end_depth"] + curr_seg["start_depth"])
            fluid_contacts.append({
                "depth": float(contact_depth),
                "from_fluid": prev_seg["fluid_type"],
                "to_fluid": curr_seg["fluid_type"],
                "type": f"{prev_seg['fluid_type']}/{curr_seg['fluid_type']}",
            })

    # Legacy by_fluid from stored fluid labels (if present), plus gradient-derived summary.
    by_fluid = []
    for fluid in sorted(set(v["fluid_type"] for v in valid)):
        arr = [(d["depth"], d["pressure"]) for d in valid if d["fluid_type"] == fluid]
        if len(arr) < 2:
            continue
        d = np.array([a[0] for a in arr], dtype=float)
        p = np.array([a[1] for a in arr], dtype=float)
        s, b = np.polyfit(d, p, 1)
        by_fluid.append({
            "fluid_type": fluid,
            "count": len(arr),
            "gradient": float(s),
            "intercept": float(b),
            "equation": f"P = {s:.6f}*Depth + {b:.3f}",
        })

    td = float(np.max(depths))
    d0 = float(np.min(depths))
    # Oilfield gradients in psi/ft.
    hydro_g = 0.433
    litho_g = 1.0
    gradient_lines = {
        "overall": {"gradient": float(slope), "intercept": float(intercept), "label": "RFT Best Fit"},
        "hydrostatic": {"gradient": hydro_g, "intercept": 0.0, "label": "Hydrostatic (0.433 psi/ft)"},
        "lithostatic": {"gradient": litho_g, "intercept": 0.0, "label": "Lithostatic (1.00 psi/ft)"},
        "segments": fluid_segments,
        "plot_depth_min": d0,
        "plot_depth_max": td,
    }

    regime_counts = {"normal": 0, "underpressure": 0, "overpressure": 0, "unknown": 0}
    for p in valid:
        regime_counts[p["pressure_regime"]] = regime_counts.get(p["pressure_regime"], 0) + 1

    # Formation pressure extraction and interval communication diagnostics.
    fp_points = []
    for p in valid:
        fp_points.append({
            "id": p["id"],
            "depth": p["depth"],
            "formation_pressure": p["pressure"],
            "gradient": p["pair_gradient"],
            "fluid_type": p["fluid_from_gradient"],
            "pressure_regime": p["pressure_regime"],
        })

    intervals = []
    for i in range(1, len(valid)):
        p1, p2 = valid[i - 1], valid[i]
        dz = p2["depth"] - p1["depth"]
        if abs(dz) < 1e-9:
            continue
        g = (p2["pressure"] - p1["pressure"]) / dz
        expected = 0.433 * dz
        delta = abs((p2["pressure"] - p1["pressure"]) - expected)
        state = "communicating" if delta <= 75.0 else "sealed"
        intervals.append({
            "top_depth": float(min(p1["depth"], p2["depth"])),
            "bottom_depth": float(max(p1["depth"], p2["depth"])),
            "gradient": float(g),
            "pressure_change": float(p2["pressure"] - p1["pressure"]),
            "expected_hydrostatic_change": float(expected),
            "pressure_deviation": float(delta),
            "communication": state,
        })

    classified_points = []
    for p in valid:
        classified_points.append({
            "id": p["id"],
            "depth": p["depth"],
            "pressure": p["pressure"],
            "fluid_type": p["fluid_type"],
            "fluid_from_gradient": p["fluid_from_gradient"],
            "pair_gradient": p["pair_gradient"],
            "pressure_regime": p["pressure_regime"],
        })

    return {
        "count": len(valid),
        "points": points,
        "classified_points": classified_points,
        "overall": overall,
        "by_fluid": by_fluid,
        "fluid_segments": fluid_segments,
        "fluid_contacts": fluid_contacts,
        "gradient_lines": gradient_lines,
        "pressure_regime_summary": regime_counts,
        "formation_pressure": {"points": fp_points, "intervals": intervals},
    }


# ─── Production Data ──────────────────────────────────────────
def _parse_iso_date(value):
    if value is None:
        return None
    if isinstance(value, datetime.date):
        return value
    try:
        return datetime.datetime.strptime(str(value).strip(), "%Y-%m-%d").date()
    except Exception:
        return None


def _fit_exponential_decline(t, q):
    # ln(q) = ln(qi) - d*t
    if len(t) < 2:
        return None
    y = np.log(np.clip(q, 1e-9, None))
    m, c = np.polyfit(t, y, 1)
    d = max(0.0, -float(m))
    qi = float(np.exp(c))
    qhat = qi * np.exp(-d * t)
    sse = float(np.sum((q - qhat) ** 2))
    return {"model": "exponential", "qi": qi, "d": d, "qhat": qhat, "sse": sse}


def _fit_hyperbolic_decline(t, q):
    # q = qi / (1 + b*di*t)^(1/b)
    if len(t) < 2:
        return None
    qi0 = float(np.max(q))
    best = None
    b_grid = np.linspace(0.1, 1.5, 57)
    di_grid = np.linspace(1e-4, 2.0, 200)
    for b in b_grid:
        denom = 1.0 + (b * di_grid[:, None] * t[None, :])
        model_unit = np.power(np.clip(denom, 1e-9, None), -1.0 / b)
        # solve qi (least squares) for each di candidate
        num = np.sum(model_unit * q[None, :], axis=1)
        den = np.sum(model_unit * model_unit, axis=1)
        qi_vals = np.where(den > 0, num / den, qi0)
        qhat_all = qi_vals[:, None] * model_unit
        sse_all = np.sum((qhat_all - q[None, :]) ** 2, axis=1)
        idx = int(np.argmin(sse_all))
        sse = float(sse_all[idx])
        qi = float(max(qi_vals[idx], 1e-9))
        di = float(di_grid[idx])
        qhat = qi * np.power(np.clip(1.0 + b * di * t, 1e-9, None), -1.0 / b)
        candidate = {"model": "hyperbolic", "qi": qi, "di": di, "b": float(b), "qhat": qhat, "sse": sse}
        if best is None or sse < best["sse"]:
            best = candidate
    return best


def _compute_eur(best_fit, days_to_limit=3650.0, q_limit=1.0):
    if not best_fit:
        return None
    t = np.linspace(0, days_to_limit, 2500)
    if best_fit["model"] == "exponential":
        q = best_fit["qi"] * np.exp(-best_fit["d"] * t)
    else:
        q = best_fit["qi"] * np.power(np.clip(1.0 + best_fit["b"] * best_fit["di"] * t, 1e-9, None), -1.0 / max(best_fit["b"], 1e-6))
    q = np.clip(q, 0.0, None)
    mask = q >= q_limit
    if np.any(mask):
        t = t[mask]
        q = q[mask]
    eur = float(np.trapz(q, t))
    return eur


@app.post("/api/wells/{wid}/production", status_code=201)
def create_production_row(wid: int, data: dict, db: Session = Depends(get_db)):
    d = _parse_iso_date(data.get("date"))
    if not d:
        raise HTTPException(400, "date is required in YYYY-MM-DD format")
    row = ProductionData(
        well_id=wid,
        date=d,
        oil_rate=float(data["oil_rate"]) if data.get("oil_rate") not in (None, "") else None,
        gas_rate=float(data["gas_rate"]) if data.get("gas_rate") not in (None, "") else None,
        water_rate=float(data["water_rate"]) if data.get("water_rate") not in (None, "") else None,
        water_cut=float(data["water_cut"]) if data.get("water_cut") not in (None, "") else None,
        gor=float(data["gor"]) if data.get("gor") not in (None, "") else None,
        bhp=float(data["bhp"]) if data.get("bhp") not in (None, "") else None,
        whp=float(data["whp"]) if data.get("whp") not in (None, "") else None,
        choke_size=float(data["choke_size"]) if data.get("choke_size") not in (None, "") else None,
        cumulative_oil=float(data["cumulative_oil"]) if data.get("cumulative_oil") not in (None, "") else None,
        cumulative_gas=float(data["cumulative_gas"]) if data.get("cumulative_gas") not in (None, "") else None,
        cumulative_water=float(data["cumulative_water"]) if data.get("cumulative_water") not in (None, "") else None,
        notes=str(data.get("notes", "")),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {c.name: getattr(row, c.name) for c in ProductionData.__table__.columns}


@app.get("/api/wells/{wid}/production")
def list_production_rows(wid: int, db: Session = Depends(get_db)):
    rows = db.query(ProductionData).filter(ProductionData.well_id == wid).order_by(ProductionData.date.asc(), ProductionData.id.asc()).all()
    result = []
    for r in rows:
        d = {c.name: getattr(r, c.name) for c in ProductionData.__table__.columns}
        if d.get("date") is not None:
            d["date"] = d["date"].isoformat()
        result.append(d)
    return result


@app.post("/api/wells/{wid}/production/upload-csv")
async def upload_production_csv(wid: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    content = await file.read()
    text_data = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text_data))
    inserted = 0
    for rec in reader:
        if not rec:
            continue
        date_val = rec.get("date") or rec.get("Date") or rec.get("DATE")
        d = _parse_iso_date(date_val)
        if not d:
            continue

        def f(*keys):
            for k in keys:
                v = rec.get(k)
                if v not in (None, ""):
                    try:
                        return float(str(v).strip())
                    except Exception:
                        return None
            return None

        row = ProductionData(
            well_id=wid,
            date=d,
            oil_rate=f("oil_rate", "OilRate", "oil"),
            gas_rate=f("gas_rate", "GasRate", "gas"),
            water_rate=f("water_rate", "WaterRate", "water"),
            water_cut=f("water_cut", "WaterCut"),
            gor=f("gor", "GOR"),
            bhp=f("bhp", "BHP"),
            whp=f("whp", "WHP"),
            choke_size=f("choke_size", "ChokeSize"),
            cumulative_oil=f("cumulative_oil", "CumOil"),
            cumulative_gas=f("cumulative_gas", "CumGas"),
            cumulative_water=f("cumulative_water", "CumWater"),
            notes=str(rec.get("notes") or rec.get("Notes") or ""),
        )
        db.add(row)
        inserted += 1
    db.commit()
    return {"status": "ok", "inserted": inserted}


@app.get("/api/wells/{wid}/production/decline-curve")
def production_decline_curve(wid: int, db: Session = Depends(get_db)):
    rows = db.query(ProductionData).filter(ProductionData.well_id == wid).order_by(ProductionData.date.asc(), ProductionData.id.asc()).all()
    valid = [(r.date, float(r.oil_rate)) for r in rows if r.date is not None and r.oil_rate is not None and r.oil_rate > 0]
    if len(valid) < 3:
        return {"count": len(valid), "detail": "Need at least 3 positive oil-rate data points", "best_model": None}

    t0 = valid[0][0]
    t = np.array([(d - t0).days for d, _ in valid], dtype=float)
    q = np.array([v for _, v in valid], dtype=float)

    exp_fit = _fit_exponential_decline(t, q)
    hyp_fit = _fit_hyperbolic_decline(t, q)
    fits = [f for f in [exp_fit, hyp_fit] if f is not None]
    if not fits:
        return {"count": len(valid), "best_model": None}

    best = min(fits, key=lambda f: f["sse"])
    eur = _compute_eur(best)

    fitted_points = []
    qhat = best.get("qhat", np.array([]))
    for i, (d, q_obs) in enumerate(valid):
        fitted_points.append({
            "date": d.isoformat(),
            "t_days": float(t[i]),
            "q_obs": float(q_obs),
            "q_fit": float(qhat[i]) if i < len(qhat) else None,
        })

    payload = {
        "count": len(valid),
        "best_model": best["model"],
        "sse": float(best["sse"]),
        "eur_oil_bbl": eur,
        "fitted_points": fitted_points,
        "models": {
            "exponential": {
                "qi": exp_fit["qi"],
                "d": exp_fit["d"],
                "sse": exp_fit["sse"],
            } if exp_fit else None,
            "hyperbolic": {
                "qi": hyp_fit["qi"],
                "di": hyp_fit["di"],
                "b": hyp_fit["b"],
                "sse": hyp_fit["sse"],
            } if hyp_fit else None,
        },
    }
    return payload


# ─── Curve Alias/Mnemonic Remap ──────────────────────────────

@app.get("/api/wells/{wid}/aliases")
def list_aliases(wid: int, db: Session = Depends(get_db)):
    aliases = db.query(CurveAlias).filter(CurveAlias.well_id == wid).all()
    return [{"original": a.original_mnemonic, "alias": a.alias_mnemonic} for a in aliases]


@app.post("/api/wells/{wid}/aliases")
def save_aliases(wid: int, data: dict, db: Session = Depends(get_db)):
    items = data.get("aliases", data if isinstance(data, list) else [])
    db.query(CurveAlias).filter(CurveAlias.well_id == wid).delete()
    for item in items:
        db.add(CurveAlias(well_id=wid, original_mnemonic=item["original"], alias_mnemonic=item["alias"]))
    db.commit()
    return {"status": "ok", "count": len(items)}


# ─── Curve Splice/Merge ──────────────────────────────────────
@app.post("/api/wells/{wid}/splice")
def splice_curves(wid: int, data: dict, db: Session = Depends(get_db)):
    """Combine best intervals from multiple runs into a new composite run.
    data: {source_runs: [lr_id1, lr_id2], intervals: [{start, end, source_lr_id}], mnemonic: 'GR'}
    """
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")
    source_runs = data.get("source_runs", [])
    intervals = data.get("intervals", [])
    mnemonic = data.get("mnemonic", "GR")
    if not source_runs or not intervals:
        raise HTTPException(400, "Need source_runs and intervals")

    # Load all source data
    run_data = {}
    for lr_id in source_runs:
        lr = db.query(LogRun).filter(LogRun.id == lr_id).first()
        if not lr:
            continue
        cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic == mnemonic).first()
        if cd:
            dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
            if dept_cd:
                depth = np.frombuffer(dept_cd.data_binary, dtype=np.float64)
                values = np.frombuffer(cd.data_binary, dtype=np.float64)
                run_data[lr_id] = {"depth": depth, "values": values, "step": lr.step or 0.5}

    if not run_data:
        raise HTTPException(400, f"No data found for mnemonic {mnemonic}")

    # Build composite: use first run as base, splice intervals from others
    base_id = source_runs[0]
    base = run_data.get(base_id)
    if not base:
        raise HTTPException(400, "Base run not found")

    composite_depth = base["depth"].copy()
    composite_values = base["values"].copy()

    for interval in intervals:
        src_id = interval.get("source_lr_id")
        start = float(interval.get("start"))
        end = float(interval.get("end"))
        src = run_data.get(src_id)
        if not src:
            continue
        for i in range(len(composite_depth)):
            if composite_depth[i] >= start and composite_depth[i] <= end:
                # Find nearest in source
                idx = np.argmin(np.abs(src["depth"] - composite_depth[i]))
                if abs(src["depth"][idx] - composite_depth[i]) < (src["step"] * 2):
                    composite_values[i] = src["values"][idx]

    # Create new log run
    curves_def = [{"mnemonic": "DEPT", "unit": "FT", "description": "Depth"}, {"mnemonic": mnemonic, "unit": "", "description": f"Spliced {mnemonic}"}]
    lr = LogRun(
        well_id=wid, run_number=len(well.log_runs) + 1,
        filename=f"splice_{mnemonic}.las", las_version="2.0",
        start_depth=float(composite_depth[0]), stop_depth=float(composite_depth[-1]),
        step=float(base["step"]), num_points=len(composite_depth),
        curves_json=json.dumps(curves_def),
    )
    db.add(lr)
    db.flush()

    db.add(CurveData(log_run_id=lr.id, mnemonic="DEPT", unit="FT", num_points=len(composite_depth), data_binary=composite_depth.tobytes()))
    valid = composite_values[~np.isnan(composite_values)]
    db.add(CurveData(log_run_id=lr.id, mnemonic=mnemonic, num_points=len(composite_values), min_value=float(np.min(valid)) if len(valid) else None, max_value=float(np.max(valid)) if len(valid) else None, data_binary=composite_values.tobytes()))
    db.commit()
    return {"status": "ok", "log_run_id": lr.id, "points": len(composite_depth)}


# ─── Log Run List (for overlay/splice selection) ─────────────
@app.get("/api/wells/{wid}/log-runs")
def list_log_runs(wid: int, db: Session = Depends(get_db)):
    runs = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.run_number).all()
    result = []
    for lr in runs:
        curves = db.query(CurveData).filter(CurveData.log_run_id == lr.id).all()
        result.append({
            "id": lr.id, "run_number": lr.run_number, "filename": lr.filename,
            "las_version": lr.las_version, "start_depth": lr.start_depth,
            "stop_depth": lr.stop_depth, "step": lr.step, "num_points": lr.num_points,
            "curves": [c.mnemonic for c in curves],
        })
    return result


# ─── Print-Ready Report ──────────────────────────────────────
@app.get("/api/wells/{wid}/report")
def generate_report(wid: int, db: Session = Depends(get_db)):
    """Generate structured data for print report."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")
    tops = [{c.name: getattr(t, c.name) for c in FormationTop.__table__.columns}
            for t in db.query(FormationTop).filter(FormationTop.well_id == wid).order_by(FormationTop.depth).all()]
    zones = [{c.name: getattr(z, c.name) for c in Zone.__table__.columns}
             for z in db.query(Zone).filter(Zone.well_id == wid).order_by(Zone.sort_order).all()]
    runs = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.run_number).all()
    curve_summary = []
    for lr in runs:
        cds = db.query(CurveData).filter(CurveData.log_run_id == lr.id).all()
        for cd in cds:
            arr = np.frombuffer(cd.data_binary, dtype=np.float64)
            valid = arr[~np.isnan(arr)]
            curve_summary.append({
                "run": lr.run_number, "mnemonic": cd.mnemonic, "unit": cd.unit,
                "count": int(len(valid)),
                "min": round(float(np.min(valid)), 4) if len(valid) else None,
                "max": round(float(np.max(valid)), 4) if len(valid) else None,
                "mean": round(float(np.mean(valid)), 4) if len(valid) else None,
            })
    pp = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    petro = {c.name: getattr(pp, c.name) for c in PetroParams.__table__.columns} if pp else None
    return {
        "well": {c.name: getattr(well, c.name) for c in Well.__table__.columns},
        "formation_tops": tops, "zones": zones,
        "curve_summary": curve_summary, "petro_params": petro,
        "generated_at": datetime.datetime.utcnow().isoformat(),
    }



# ─── Electrofacies / Rock Typing ──────────────────────────────
@app.post("/api/wells/{wid}/electrofacies")
def compute_electrofacies(wid: int, data: dict, db: Session = Depends(get_db)):
    """K-means clustering on selected curves to classify rock types."""
    lr_id = data.get("log_run_id")
    n_clusters = min(int(data.get("n_clusters", 4)), 8)
    curve_names = data.get("curves", ["GR", "RHOB", "NPHI", "RT"])

    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run found")

    # Load curves
    curves_data = {}
    dept = None
    for cn in curve_names:
        cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == cn).first()
        if cd:
            curves_data[cn] = np.frombuffer(cd.data_binary, dtype=np.float64).copy()
    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if dept_cd:
        dept = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy()

    if len(curves_data) < 2 or dept is None:
        raise HTTPException(400, "Need at least 2 curves and depth for clustering")

    # Build feature matrix (filter valid rows)
    n = len(dept)
    keys = list(curves_data.keys())
    valid_mask = np.ones(n, dtype=bool)
    for k in keys:
        arr = curves_data[k]
        valid_mask &= ~np.isnan(arr) & (arr != -999.25)

    # Normalize RT to log scale
    X = np.column_stack([np.log10(curves_data[k]) if k in ("RT", "RESD", "ILD") else curves_data[k] for k in keys])
    X = X[valid_mask]
    depth_valid = dept[valid_mask]

    if len(X) < n_clusters * 10:
        raise HTTPException(400, f"Not enough valid data ({len(X)} pts) for {n_clusters} clusters")

    # Z-score normalize
    means = X.mean(axis=0)
    stds = X.std(axis=0)
    stds[stds == 0] = 1
    X_norm = (X - means) / stds

    # K-means (simple implementation)
    # Use random seed for non-deterministic clustering (pass seed param for reproducibility if needed)
    centroids = X_norm[np.random.choice(len(X_norm), n_clusters, replace=False)]
    for _ in range(50):
        dists = np.sqrt(((X_norm[:, None] - centroids[None]) ** 2).sum(axis=2))
        labels = dists.argmin(axis=1)
        new_centroids = np.array([X_norm[labels == c].mean(axis=0) if (labels == c).any() else centroids[c] for c in range(n_clusters)])
        if np.allclose(centroids, new_centroids, atol=1e-4):
            break
        centroids = new_centroids

    # Denormalize centroids
    centroids_raw = centroids * stds + means
    facies_names = [f"Facies_{i+1}" for i in range(n_clusters)]

    # Build result: per-point labels for valid data
    full_labels = np.full(n, -1, dtype=int)
    full_labels[valid_mask] = labels

    # Summary per facies
    summary = []
    for c in range(n_clusters):
        mask = labels == c
        count = int(mask.sum())
        pct = round(count / len(labels) * 100, 1) if len(labels) else 0
        center = {}
        for j, k in enumerate(keys):
            raw_val = centroids_raw[c][j]
            if k in ("RT", "RESD", "ILD"):
                raw_val = 10 ** raw_val
            center[k] = round(float(raw_val), 4)
        summary.append({"facies": facies_names[c], "count": count, "pct": pct, "centroid": center})

    return {
        "facies_labels": full_labels.tolist(),
        "depth": dept.tolist(),
        "n_clusters": n_clusters,
        "curves_used": keys,
        "summary": summary,
    }


# ─── Despike / Smooth ────────────────────────────────────────
@app.post("/api/log-runs/{lr_id}/filter")
def filter_curve(lr_id: int, data: dict, db: Session = Depends(get_db)):
    """Apply despiking (median filter) or smoothing (moving average) to a curve."""
    mnemonic = data.get("mnemonic", "GR")
    filter_type = data.get("filter", "despike")  # despike or smooth
    window = int(data.get("window", 5))
    if window % 2 == 0:
        window += 1
    window = max(3, min(window, 51))

    cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic == mnemonic).first()
    if not cd:
        raise HTTPException(404, f"Curve {mnemonic} not found")

    arr = np.frombuffer(cd.data_binary, dtype=np.float64).copy()
    result = arr.copy()

    valid_idx = ~np.isnan(arr)
    vals = arr[valid_idx]

    if filter_type == "despike":
        # Median filter
        half = window // 2
        filtered = vals.copy()
        for i in range(half, len(vals) - half):
            neighbors = vals[max(0, i - half):i + half + 1]
            med = np.median(neighbors)
            if abs(vals[i] - med) > 2 * np.std(neighbors):
                filtered[i] = med
        result[valid_idx] = filtered
    else:
        # Moving average
        half = window // 2
        filtered = vals.copy()
        for i in range(len(vals)):
            start = max(0, i - half)
            end = min(len(vals), i + half + 1)
            filtered[i] = np.mean(vals[start:end])
        result[valid_idx] = filtered

    # Create new curve with suffix
    new_mnemonic = f"{mnemonic}_{'D' if filter_type == 'despike' else 'S'}{window}"
    valid = result[~np.isnan(result)]

    lr = db.query(LogRun).filter(LogRun.id == lr_id).first()
    # Check if filtered curve already exists
    existing = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic == new_mnemonic).first()
    if existing:
        existing.data_binary = result.tobytes()
        existing.num_points = len(result)
        existing.min_value = float(np.min(valid)) if len(valid) else None
        existing.max_value = float(np.max(valid)) if len(valid) else None
    else:
        db.add(CurveData(
            log_run_id=lr_id, mnemonic=new_mnemonic, unit=cd.unit,
            description=f"{filter_type} filtered {mnemonic} (w={window})",
            num_points=len(result),
            min_value=float(np.min(valid)) if len(valid) else None,
            max_value=float(np.max(valid)) if len(valid) else None,
            data_binary=result.tobytes(),
        ))
    db.commit()
    return {"status": "ok", "new_curve": new_mnemonic, "filter": filter_type, "window": window}


# ─── Depth Match (Auto Cross-Correlation) ────────────────────
@app.post("/api/wells/{wid}/depth-match")
def auto_depth_match(wid: int, data: dict, db: Session = Depends(get_db)):
    """Compute optimal depth shift between two runs of same curve via cross-correlation."""
    run_a_raw = data.get("run_a")
    run_b_raw = data.get("run_b")
    if run_a_raw is None or run_b_raw is None:
        raise HTTPException(400, "run_a and run_b are required")
    run_a = int(run_a_raw)
    run_b = int(run_b_raw)
    mnemonic = data.get("mnemonic", "GR")
    max_shift = float(data.get("max_shift", 50))

    cd_a = db.query(CurveData).filter(CurveData.log_run_id == run_a, CurveData.mnemonic == mnemonic).first()
    cd_b = db.query(CurveData).filter(CurveData.log_run_id == run_b, CurveData.mnemonic == mnemonic).first()
    if not cd_a or not cd_b:
        raise HTTPException(404, f"Curve {mnemonic} not found in both runs")

    dept_a_cd = db.query(CurveData).filter(CurveData.log_run_id == run_a, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    dept_b_cd = db.query(CurveData).filter(CurveData.log_run_id == run_b, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if not dept_a_cd or not dept_b_cd:
        raise HTTPException(404, "Depth curve not found")

    a_vals = np.frombuffer(cd_a.data_binary, dtype=np.float64).copy()
    b_vals = np.frombuffer(cd_b.data_binary, dtype=np.float64).copy()
    a_dept = np.frombuffer(dept_a_cd.data_binary, dtype=np.float64).copy()
    b_dept = np.frombuffer(dept_b_cd.data_binary, dtype=np.float64).copy()

    # Interpolate both onto common grid
    step = float(db.query(LogRun).filter(LogRun.id == run_a).first().step or 0.5)
    d_min = max(a_dept[0], b_dept[0])
    d_max = min(a_dept[-1], b_dept[-1])
    if d_max <= d_min:
        raise HTTPException(400, "No overlapping depth range")

    common = np.arange(d_min, d_max, step)
    a_interp = np.interp(common, a_dept, a_vals)
    b_interp = np.interp(common, b_dept, b_vals)

    # Remove NaNs
    valid = ~(np.isnan(a_interp) | np.isnan(b_interp))
    a_v = a_interp[valid]
    b_v = b_interp[valid]
    if len(a_v) < 50:
        raise HTTPException(400, "Not enough overlapping valid data")

    # Cross-correlation with shifts
    max_samples = int(max_shift / step)
    best_corr = -2
    best_shift = 0
    correlations = []
    for shift in range(-max_samples, max_samples + 1):
        if shift >= 0:
            aa = a_v[shift:]
            bb = b_v[:len(aa)]
        else:
            bb = b_v[-shift:]
            aa = a_v[:len(bb)]
        if len(aa) < 30:
            continue
        corr = np.corrcoef(aa, bb)[0, 1]
        correlations.append({"shift_ft": round(shift * step, 2), "correlation": round(float(corr), 4)})
        if corr > best_corr:
            best_corr = corr
            best_shift = shift * step

    return {
        "optimal_shift_ft": round(float(best_shift), 2),
        "correlation": round(float(best_corr), 4),
        "common_depth_range": [round(float(d_min), 1), round(float(d_max), 1)],
        "step": step,
        "correlations": correlations,
    }


# ─── Curve Override ──────────────────────────────────────────
@app.post("/api/log-runs/{lr_id}/curve-override")
def curve_override(lr_id: int, data: dict, db: Session = Depends(get_db)):
    """Override curve values in a depth range."""
    mnemonic = data.get("mnemonic", "GR")
    start_raw = data.get("start")
    end_raw = data.get("end")
    value_raw = data.get("value")
    if start_raw is None or end_raw is None or value_raw is None:
        raise HTTPException(400, "start, end, and value are required")
    start = float(start_raw)
    end = float(end_raw)
    value = float(value_raw)

    cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic == mnemonic).first()
    if not cd:
        raise HTTPException(404, f"Curve {mnemonic} not found")

    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if not dept_cd:
        raise HTTPException(404, "Depth not found")

    arr = np.frombuffer(cd.data_binary, dtype=np.float64).copy()
    dept = np.frombuffer(dept_cd.data_binary, dtype=np.float64)

    count = 0
    for i in range(len(arr)):
        if dept[i] >= start and dept[i] <= end:
            arr[i] = value
            count += 1

    valid = arr[~np.isnan(arr)]
    cd.data_binary = arr.tobytes()
    cd.min_value = float(np.min(valid)) if len(valid) else None
    cd.max_value = float(np.max(valid)) if len(valid) else None
    db.commit()
    return {"status": "ok", "points_overridden": count}


@app.post("/api/log-runs/{lr_id}/curve-edit")
def curve_edit(lr_id: int, data: dict, db: Session = Depends(get_db)):
    """Apply manual point edits to a curve and track original values for undo."""
    mnemonic = str(data.get("mnemonic", "")).strip().upper()
    edits = data.get("edits") or []
    if not mnemonic:
        raise HTTPException(400, "mnemonic is required")
    if not isinstance(edits, list) or not edits:
        raise HTTPException(400, "edits[] is required")

    cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic == mnemonic).first()
    if not cd:
        raise HTTPException(404, f"Curve {mnemonic} not found")

    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr_id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])) .first()
    if not dept_cd:
        raise HTTPException(404, "Depth curve not found")

    arr = np.frombuffer(cd.data_binary, dtype=np.float64).copy()
    dept = np.frombuffer(dept_cd.data_binary, dtype=np.float64)
    if len(arr) != len(dept):
        n = min(len(arr), len(dept))
        arr = arr[:n]
        dept = dept[:n]

    key = f"{lr_id}:{mnemonic}"
    originals = CURVE_EDIT_ORIGINALS.setdefault(key, {})

    applied = []
    changed = 0
    nulled = 0
    for e in edits:
        if not isinstance(e, dict):
            continue
        depth_raw = e.get("depth")
        if depth_raw is None:
            continue
        try:
            depth = float(depth_raw)
        except Exception:
            continue

        idx = int(np.argmin(np.abs(dept - depth)))
        old_val = arr[idx]
        if idx not in originals:
            originals[idx] = None if np.isnan(old_val) else float(old_val)

        nv_raw = e.get("new_value")
        try:
            new_val = np.nan if nv_raw is None else float(nv_raw)
        except (ValueError, TypeError):
            raise HTTPException(400, f"Invalid new_value: {nv_raw}")
        arr[idx] = new_val
        changed += 1
        if np.isnan(new_val):
            nulled += 1

        applied.append({
            "index": idx,
            "depth": float(dept[idx]),
            "old_value": None if np.isnan(old_val) else float(old_val),
            "new_value": None if np.isnan(new_val) else float(new_val),
        })

    valid = arr[~np.isnan(arr)]
    cd.data_binary = arr.tobytes()
    cd.num_points = int(len(arr))
    cd.min_value = float(np.min(valid)) if len(valid) else None
    cd.max_value = float(np.max(valid)) if len(valid) else None
    db.commit()

    return {
        "status": "ok",
        "mnemonic": mnemonic,
        "applied_count": len(applied),
        "changed_count": changed,
        "nulled_count": nulled,
        "original_store_count": len(originals),
        "curve_stats": {
            "num_points": int(len(arr)),
            "valid_points": int(len(valid)),
            "null_points": int(len(arr) - len(valid)),
            "min": float(np.min(valid)) if len(valid) else None,
            "max": float(np.max(valid)) if len(valid) else None,
        },
        "applied_edits": applied,
    }


# ─── Multi-well Strip Log Data ────────────────────────────────
@app.get("/api/projects/{pid}/strip-log-data")
def strip_log_data(pid: int, curve: str = "GR", db: Session = Depends(get_db)):
    """Return data for multi-well strip log: depth + curve + tops for all wells in project."""
    wells = db.query(Well).filter(Well.project_id == pid).order_by(Well.id).all()
    result = {"wells": [], "formation_names": set()}
    for w in wells:
        lr = db.query(LogRun).filter(LogRun.well_id == w.id).order_by(LogRun.id.desc()).first()
        if not lr:
            continue
        cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == curve).first()
        dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
        if not cd or not dept_cd:
            continue
        depth = np.frombuffer(dept_cd.data_binary, dtype=np.float64)
        values = np.frombuffer(cd.data_binary, dtype=np.float64)
        # Subsample for performance (max 500 pts per well)
        step = max(1, len(depth) // 500)
        idx = list(range(0, len(depth), step))
        tops = db.query(FormationTop).filter(FormationTop.well_id == w.id).order_by(FormationTop.depth).all()
        tops_data = []
        for t in tops:
            tops_data.append({"name": t.formation_name, "depth": t.depth, "color": t.color or "#888888"})
            result["formation_names"].add(t.formation_name)
        result["wells"].append({
            "well_id": w.id, "name": w.name, "uwi": w.uwi,
            "depth_unit": w.depth_unit or "FT",
            "depth": [round(float(depth[i]), 1) for i in idx],
            "values": [round(float(values[i]), 3) if not np.isnan(values[i]) else None for i in idx],
            "tops": tops_data,
        })
    result["formation_names"] = sorted(result["formation_names"])
    return result


@app.get("/api/projects/{pid}/cross-section")
def project_cross_section(pid: int, well_ids: str = "", curve: str = "GR", db: Session = Depends(get_db)):
    """Return well-to-well cross-section payload: per-well depth/curve/tops and relative X positions."""
    all_wells = db.query(Well).filter(Well.project_id == pid).order_by(Well.id.asc()).all()
    if not all_wells:
        return {"project_id": pid, "curve": (curve or "GR").upper(), "wells": []}

    selected_ids = []
    if well_ids:
        for tok in str(well_ids).split(","):
            tok = tok.strip()
            if not tok:
                continue
            try:
                selected_ids.append(int(tok))
            except ValueError:
                continue

    if selected_ids:
        id_set = set(selected_ids)
        wells = [w for w in all_wells if w.id in id_set]
        wells.sort(key=lambda w: selected_ids.index(w.id) if w.id in selected_ids else 10**9)
    else:
        wells = all_wells

    if not wells:
        return {"project_id": pid, "curve": (curve or "GR").upper(), "wells": []}

    have_coords = all((w.latitude is not None and w.longitude is not None) for w in wells)
    if have_coords:
        lats = [float(w.latitude) for w in wells]
        lons = [float(w.longitude) for w in wells]
        lat0 = float(np.mean(lats))
        km_per_deg_lat = 111.32
        km_per_deg_lon = 111.32 * float(np.cos(np.radians(lat0)))
        xs_km = [(lon - lons[0]) * km_per_deg_lon for lon in lons]
        ys_km = [(lat - lats[0]) * km_per_deg_lat for lat in lats]
        x_positions = [0.0]
        for i in range(1, len(wells)):
            dx = xs_km[i] - xs_km[i - 1]
            dy = ys_km[i] - ys_km[i - 1]
            x_positions.append(x_positions[-1] + float(np.hypot(dx, dy)))
    else:
        x_positions = [float(i) for i in range(len(wells))]

    mn = (curve or "GR").upper()
    result_wells = []
    formation_names = set()
    for i, w in enumerate(wells):
        lr = db.query(LogRun).filter(LogRun.well_id == w.id).order_by(LogRun.id.desc()).first()
        if not lr:
            continue
        dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
        if not dept_cd:
            continue
        cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == mn).first()

        depth = np.frombuffer(dept_cd.data_binary, dtype=np.float64)
        values = np.frombuffer(cd.data_binary, dtype=np.float64) if cd else np.full_like(depth, np.nan)

        step = max(1, len(depth) // 700)
        idx = list(range(0, len(depth), step))

        tops = db.query(FormationTop).filter(FormationTop.well_id == w.id).order_by(FormationTop.depth.asc()).all()
        tops_data = []
        for t in tops:
            top_name = t.formation_name or "Top"
            formation_names.add(top_name)
            tops_data.append({
                "name": top_name,
                "depth": round(float(t.depth), 2),
                "color": t.color or "#888888",
                "lithology": t.lithology or "",
            })

        result_wells.append({
            "well_id": w.id,
            "name": w.name,
            "uwi": w.uwi,
            "x": round(float(x_positions[i]), 4),
            "depth_unit": w.depth_unit or "FT",
            "lat": float(w.latitude) if w.latitude is not None else None,
            "lon": float(w.longitude) if w.longitude is not None else None,
            "curve": mn,
            "depth": [round(float(depth[j]), 2) for j in idx],
            "values": [round(float(values[j]), 4) if not np.isnan(values[j]) else None for j in idx],
            "tops": tops_data,
        })

    return {
        "project_id": pid,
        "curve": mn,
        "x_unit": "km" if have_coords else "index",
        "has_coordinates": have_coords,
        "formation_names": sorted(formation_names),
        "wells": result_wells,
    }


# ─── Formation Top Auto-Pick ──────────────────────────────────
@app.post("/api/wells/{wid}/auto-pick-tops")
def auto_pick_tops(wid: int, data: dict, db: Session = Depends(get_db), _role: str = Depends(require_interpreter)):
    """Auto-detect formation boundaries from GR or RT curve breaks."""
    curve = data.get("curve", "GR")
    threshold = float(data.get("threshold", 1.5))  # z-score threshold for boundary detection
    min_gap = float(data.get("min_gap", 20))  # minimum depth gap between picks (ft)

    lr_id = data.get("log_run_id")
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run found")

    cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == curve).first()
    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if not cd or not dept_cd:
        raise HTTPException(404, f"Curve {curve} not found")

    values = np.frombuffer(cd.data_binary, dtype=np.float64).copy()
    depth = np.frombuffer(dept_cd.data_binary, dtype=np.float64)

    # Compute first derivative (gradient)
    grad = np.diff(values)
    valid = ~np.isnan(grad)
    grad_valid = grad[valid]
    if len(grad_valid) < 10:
        raise HTTPException(400, "Not enough valid data")

    mean_g = np.mean(np.abs(grad_valid))
    std_g = np.std(np.abs(grad_valid))
    if std_g == 0:
        raise HTTPException(400, "Curve has no variation")

    # Find peaks in absolute gradient (curve breaks)
    picks = []
    for i in range(1, len(grad) - 1):
        if np.isnan(grad[i]):
            continue
        z = abs(grad[i]) / (std_g if std_g > 0 else 1)
        if z > threshold:
            d = float(depth[i])
            if not picks or (d - picks[-1]["depth"]) > min_gap:
                picks.append({"depth": round(d, 1), "z_score": round(float(z), 2), "curve": curve})

    # Assign tentative formation names
    for i, p in enumerate(picks):
        p["formation_name"] = f"Auto_Top_{i + 1}"
        p["color"] = ["#e74c3c", "#3498db", "#2ecc71", "#f39c12", "#9b59b6", "#1abc9c", "#e67e22", "#34495e"][i % 8]

    return {"picks": picks, "threshold": threshold, "min_gap": min_gap, "curve": curve}


# ─── Save Auto-Picked Tops ───────────────────────────────────
@app.post("/api/wells/{wid}/save-picks")
def save_picks(wid: int, data: dict, db: Session = Depends(get_db)):
    """Save auto-picked or edited tops to database."""
    picks = data.get("picks", [])
    count = 0
    for p in picks:
        name = p.get("formation_name", "")
        depth = float(p.get("depth", 0))
        if not name or depth <= 0:
            continue
        db.add(FormationTop(
            well_id=wid, formation_name=name, depth=depth,
            color=p.get("color", "#888888"),
            lithology=p.get("lithology", ""),
        ))
        count += 1
    db.commit()
    return {"status": "ok", "saved": count}


# ─── CSV Data Import ──────────────────────────────────────────
@app.post("/api/wells/{wid}/upload-csv")
async def upload_csv(wid: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    """Upload CSV file and convert to log run."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(400, "Empty file")

    try:
        text = content.decode("utf-8", errors="replace")
        lines = text.strip().split("\n")
        if len(lines) < 2:
            raise HTTPException(400, "File too short")

        # Parse header
        header = [h.strip().strip('"').upper() for h in lines[0].split(",")]
        n_cols = len(header)

        # Parse data rows
        data_rows = []
        for line in lines[1:]:
            vals = [v.strip() for v in line.split(",")]
            if len(vals) != n_cols:
                continue
            try:
                row = [float(v) if v and v != "" else float("nan") for v in vals]
                data_rows.append(row)
            except ValueError:
                continue

        if not data_rows:
            raise HTTPException(400, "No valid numeric data")

        arr = np.array(data_rows, dtype=np.float64)
        depth_col = None
        for i, h in enumerate(header):
            if h in ("DEPT", "DEPTH", "MD", "TVD"):
                depth_col = i
                break
        if depth_col is None:
            depth_col = 0

        depth = arr[:, depth_col]
        step = abs(float(depth[1] - depth[0])) if len(depth) > 1 else 0.5

        curves_def = [{"mnemonic": h, "unit": "", "description": ""} for h in header]
        lr = LogRun(
            well_id=wid, run_number=len(well.log_runs) + 1,
            filename=file.filename or "data.csv", las_version="CSV",
            start_depth=float(depth[0]), stop_depth=float(depth[-1]),
            step=step, num_points=len(depth),
            curves_json=json.dumps(curves_def),
        )
        db.add(lr)
        db.flush()

        for i, h in enumerate(header):
            col = arr[:, i]
            valid = col[~np.isnan(col)]
            db.add(CurveData(
                log_run_id=lr.id, mnemonic=h, unit="", description="",
                num_points=len(col),
                min_value=float(np.min(valid)) if len(valid) else None,
                max_value=float(np.max(valid)) if len(valid) else None,
                data_binary=col.tobytes(),
            ))
        db.commit()
        return {"status": "ok", "log_run_id": lr.id, "curves": header, "points": len(depth)}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"CSV parse error: {str(e)[:200]}")


# ─── Well Trajectory / Deviation Survey ──────────────────────


@app.get("/api/wells/{wid}/trajectory")
def get_trajectory(wid: int, db: Session = Depends(get_db)):
    points = db.query(DeviationSurvey).filter(DeviationSurvey.well_id == wid).order_by(DeviationSurvey.md).all()
    if not points:
        return {"points": [], "tvd_computed": False}
    result = [{"md": p.md, "inc": p.inc, "azi": p.azi, "tvd": p.tvd, "northing": p.northing, "easting": p.easting} for p in points]
    return {"points": result, "tvd_computed": any(p.tvd is not None for p in points)}


@app.post("/api/wells/{wid}/trajectory")
def save_trajectory(wid: int, data: dict, db: Session = Depends(get_db)):
    """Save deviation survey and compute TVD using minimum curvature method."""
    points = data.get("points", [])
    # Also accept flat arrays: {"md":[...], "inc":[...], "azi":[...]}
    if not points and "md" in data and "inc" in data and "azi" in data:
        md_arr = data["md"]
        inc_arr = data["inc"]
        azi_arr = data["azi"]
        if not (len(md_arr) == len(inc_arr) == len(azi_arr)):
            raise HTTPException(400, "md, inc, azi arrays must have equal length")
        points = [{"md": md_arr[i], "inc": inc_arr[i], "azi": azi_arr[i]} for i in range(len(md_arr))]
    if not points:
        raise HTTPException(400, "No points provided")

    # Clear existing
    db.query(DeviationSurvey).filter(DeviationSurvey.well_id == wid).delete()

    # Minimum curvature method
    computed = []
    tvd_total = 0.0
    north_total = 0.0
    east_total = 0.0
    prev_md = 0.0
    prev_inc = 0.0
    prev_azi = 0.0

    for i, p in enumerate(points):
        md = float(p["md"])
        inc = float(p["inc"])  # degrees
        azi = float(p["azi"])  # degrees

        if i > 0:
            dmd = md - prev_md
            inc1_rad = np.radians(prev_inc)
            inc2_rad = np.radians(inc)
            azi1_rad = np.radians(prev_azi)
            azi2_rad = np.radians(azi)

            # Dog leg angle
            cos_dog = np.cos(inc2_rad - inc1_rad) - np.sin(inc1_rad) * np.sin(inc2_rad) * (1 - np.cos(azi2_rad - azi1_rad))
            cos_dog = max(-1, min(1, cos_dog))
            dog = np.arccos(cos_dog)

            # RF (ratio factor)
            if dog < 1e-6:
                rf = 1.0
            else:
                rf = 2 / dog * np.tan(dog / 2)

            # TVD increment
            d_tvd = dmd / 2 * (np.cos(inc1_rad) + np.cos(inc2_rad)) * rf
            d_north = dmd / 2 * (np.sin(inc1_rad) * np.cos(azi1_rad) + np.sin(inc2_rad) * np.cos(azi2_rad)) * rf
            d_east = dmd / 2 * (np.sin(inc1_rad) * np.sin(azi1_rad) + np.sin(inc2_rad) * np.sin(azi2_rad)) * rf

            tvd_total += d_tvd
            north_total += d_north
            east_total += d_east

        computed.append({"md": md, "inc": inc, "azi": azi, "tvd": round(tvd_total, 2), "northing": round(north_total, 2), "easting": round(east_total, 2)})
        prev_md, prev_inc, prev_azi = md, inc, azi

    for c in computed:
        db.add(DeviationSurvey(well_id=wid, **c))

    db.commit()
    return {"status": "ok", "points": len(computed), "tvd_range": [computed[0]["tvd"], computed[-1]["tvd"]]}


# ─── Stratigraphic Normalization ─────────────────────────────
@app.post("/api/wells/{wid}/strat-normalize")
def strat_normalize(wid: int, data: dict, db: Session = Depends(get_db)):
    """Normalize depths relative to a reference formation top for structural cross-sections."""
    ref_formation = data.get("reference_formation", "")
    lr_id = data.get("log_run_id")
    mnemonic = data.get("curve", "GR")

    if not ref_formation:
        raise HTTPException(400, "Specify reference_formation")

    # Find the reference top for this well
    top = db.query(FormationTop).filter(
        FormationTop.well_id == wid, FormationTop.formation_name == ref_formation
    ).first()
    if not top:
        raise HTTPException(404, f"Formation '{ref_formation}' not found in this well")

    ref_depth = top.depth

    # Get curve data
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == mnemonic).first()
    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if not cd or not dept_cd:
        raise HTTPException(404, f"Curve {mnemonic} not found")

    depth = np.frombuffer(dept_cd.data_binary, dtype=np.float64)
    values = np.frombuffer(cd.data_binary, dtype=np.float64)

    # Normalize: positive = above reference (shallower), negative = below (deeper)
    normalized_depth = ref_depth - depth

    # Subsample
    step = max(1, len(depth) // 500)
    idx = list(range(0, len(depth), step))

    return {
        "well_id": wid, "reference_formation": ref_formation, "reference_depth": ref_depth,
        "normalized_depth": [round(float(normalized_depth[i]), 1) for i in idx],
        "values": [round(float(values[i]), 3) if not np.isnan(values[i]) else None for i in idx],
        "md_range": [round(float(depth[0]), 1), round(float(depth[-1]), 1)],
    }


# ─── Sprint 21: Professional Petrophysics / Plotting ─────────
@app.post("/api/wells/{wid}/permeability")
def compute_permeability(wid: int, data: dict, db: Session = Depends(get_db)):
    """Compute permeability (mD) via Coates, Timur, SDR, with crossplot + FZI diagnostics."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    model = str(data.get("model", data.get("method", "timur"))).strip().lower()
    if model not in {"coates", "timur", "sdr", "all"}:
        raise HTTPException(400, "model must be one of: coates, timur, sdr, all")

    phie_curve = data.get("phie_curve", "PHIE")
    sw_curve = data.get("sw_curve", "SW")
    rhob_curve = data.get("rhob_curve", "RHOB")
    grain_density = float(data.get("grain_density", 2.65))
    water_cut = float(data.get("water_cut", 0.0) or 0.0)
    water_cut = max(0.0, min(1.0, water_cut))

    # Model constants (industry-typical defaults)
    coates_c = float(data.get("coates_c", 1e4))
    timur_a = float(data.get("timur_a", 0.136))
    sdr_a = float(data.get("sdr_a", 4.0))

    depth_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if not depth_cd:
        raise HTTPException(404, "Depth curve not found")

    phie_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == phie_curve).first()
    sw_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == sw_curve).first()

    depth = np.frombuffer(depth_cd.data_binary, dtype=np.float64).copy()

    # PHIE fallback from RHOB if needed
    if phie_cd:
        phie = np.frombuffer(phie_cd.data_binary, dtype=np.float64).copy()
    else:
        rho_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == rhob_curve).first()
        if not rho_cd:
            raise HTTPException(404, f"Curve {phie_curve} not found and no {rhob_curve} for fallback")
        rho_arr = np.frombuffer(rho_cd.data_binary, dtype=np.float64).copy()
        rho_ma = grain_density
        rho_f = 1.0
        phie = np.clip((rho_ma - rho_arr) / max(1e-9, (rho_ma - rho_f)), 0.0, 0.6)
        phie[np.isnan(rho_arr)] = np.nan

    # Sw / Swir handling
    if sw_cd:
        sw = np.frombuffer(sw_cd.data_binary, dtype=np.float64).copy()
    else:
        sw = np.full_like(phie, np.nan)

    # User Swir takes priority. Else estimate Swir = Sw * (1 - water_cut)
    user_swir = data.get("swir")
    if user_swir is not None and str(user_swir).strip() != "":
        swir = np.full_like(phie, float(user_swir), dtype=np.float64)
    else:
        swir = sw * (1.0 - water_cut)

    # If Sw missing, fall back to PetroParams sw_cutoff (legacy behavior)
    pp = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    sw_fallback = float(pp.sw_cutoff) if pp and pp.sw_cutoff is not None else 0.2
    swir[np.isnan(swir)] = sw_fallback

    # Sanitize
    phie_clip = np.clip(phie, 0.0, 0.6)
    swir_clip = np.clip(swir, 1e-4, 1.0)

    def _stats(arr: np.ndarray):
        v = arr[np.isfinite(arr) & (arr > 0)]
        if len(v) == 0:
            return {"count": 0, "min": None, "max": None, "mean": None, "median": None}
        return {
            "count": int(len(v)),
            "min": round(float(np.min(v)), 4),
            "max": round(float(np.max(v)), 4),
            "mean": round(float(np.mean(v)), 4),
            "median": round(float(np.median(v)), 4),
        }

    def _crossplot(phi_arr: np.ndarray, k_arr: np.ndarray):
        mask = np.isfinite(phi_arr) & np.isfinite(k_arr) & (phi_arr > 0) & (k_arr > 0)
        if np.sum(mask) < 3:
            return {
                "A": None, "B": None, "r2": None, "n_points": int(np.sum(mask)),
                "equation": "insufficient data",
                "phi": [], "k": [], "k_fit": []
            }
        x = phi_arr[mask]
        y = np.log10(k_arr[mask])
        A, B = np.polyfit(x, y, 1)
        yhat = A * x + B
        ss_res = float(np.sum((y - yhat) ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r2 = (1.0 - ss_res / ss_tot) if ss_tot > 0 else 0.0
        return {
            "A": round(float(A), 6),
            "B": round(float(B), 6),
            "r2": round(float(r2), 6),
            "n_points": int(len(x)),
            "equation": f"log10(k) = {A:.4f} * phi + {B:.4f}",
            "phi": [round(float(v), 6) for v in x],
            "k": [round(float(v), 6) for v in k_arr[mask]],
            "k_fit": [round(float(10 ** v), 6) for v in yhat],
        }

    def _fzi(k_arr: np.ndarray, phi_arr: np.ndarray):
        # RQI = 0.0314 * sqrt(k/phi), phi_z = phi/(1-phi), FZI = RQI/phi_z
        valid = np.isfinite(k_arr) & np.isfinite(phi_arr) & (k_arr > 0) & (phi_arr > 0) & (phi_arr < 1)
        if np.sum(valid) == 0:
            return {"values": [], "histogram": [], "hfu": []}

        phi_v = phi_arr[valid]
        k_v = k_arr[valid]
        rqi = 0.0314 * np.sqrt(k_v / np.clip(phi_v, 1e-9, None))
        phi_z = phi_v / np.clip(1.0 - phi_v, 1e-9, None)
        fzi = rqi / np.clip(phi_z, 1e-9, None)

        fzi = fzi[np.isfinite(fzi) & (fzi > 0)]
        if len(fzi) == 0:
            return {"values": [], "histogram": [], "hfu": []}

        # HFU grouping by FZI terciles
        q1, q2 = np.percentile(fzi, [33.33, 66.67])
        hfu = []
        for v in fzi:
            if v <= q1:
                hfu.append("HFU-1")
            elif v <= q2:
                hfu.append("HFU-2")
            else:
                hfu.append("HFU-3")

        hist_counts, hist_edges = np.histogram(fzi, bins=10)
        histogram = []
        for i in range(len(hist_counts)):
            histogram.append({
                "from": round(float(hist_edges[i]), 6),
                "to": round(float(hist_edges[i + 1]), 6),
                "count": int(hist_counts[i]),
            })

        return {
            "values": [round(float(v), 6) for v in fzi],
            "histogram": histogram,
            "hfu": hfu,
            "stats": _stats(fzi),
        }

    # Load optional NMR T2 geometric mean curve
    t2_cd = None
    for t2_mn in [data.get("t2gm_curve", "T2GM"), "T2LM", "T2_LOG_MEAN", "T2GEOM"]:
        if not t2_mn:
            continue
        t2_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == t2_mn).first()
        if t2_cd:
            break
    t2gm = np.frombuffer(t2_cd.data_binary, dtype=np.float64).copy() if t2_cd else None

    available = {}

    def _add_model(name: str, arr: np.ndarray):
        arr = np.where(np.isfinite(arr) & (arr > 0), arr, np.nan)
        available[name] = {
            "k_md": arr,
            "stats": _stats(arr),
            "crossplot": _crossplot(phie_clip, arr),
            "fzi": _fzi(arr, phie_clip),
        }

    # Coates: k = ((phi^4)/(Swir^2))*C
    k_coates = ((phie_clip ** 4) / (swir_clip ** 2)) * coates_c
    _add_model("coates", k_coates)

    # Timur: k = a*(phi^4.4)/(Swir^2)
    k_timur = timur_a * (phie_clip ** 4.4) / (swir_clip ** 2)
    _add_model("timur", k_timur)

    # SDR (requires NMR T2gm): k = a * phi^4 * T2gm^2
    if t2gm is not None:
        t2_clip = np.where(np.isfinite(t2gm) & (t2gm > 0), t2gm, np.nan)
        k_sdr = sdr_a * (phie_clip ** 4) * (t2_clip ** 2)
        _add_model("sdr", k_sdr)

    selected_models = list(available.keys()) if model == "all" else [model]
    selected_models = [m for m in selected_models if m in available]
    if not selected_models:
        raise HTTPException(400, "Requested model unavailable (SDR requires NMR T2gm data)")

    step = max(1, len(depth) // 800)
    idx = list(range(0, len(depth), step))

    k_values = {}
    summary = {}
    crossplot = {}
    fzi = {}

    for m in selected_models:
        k_arr = available[m]["k_md"]
        k_values[m] = [round(float(k_arr[i]), 6) if np.isfinite(k_arr[i]) else None for i in idx]
        summary[m] = available[m]["stats"]
        crossplot[m] = available[m]["crossplot"]
        fzi[m] = available[m]["fzi"]

    primary = selected_models[0]
    primary_valid = available[primary]["k_md"][np.isfinite(available[primary]["k_md"]) & (available[primary]["k_md"] > 0)]

    return {
        "well_id": wid,
        "log_run_id": lr.id,
        "model": model,
        "models_computed": selected_models,
        "units": "md",
        "curve_name": "PERM",
        "depth": [round(float(depth[i]), 3) for i in idx],
        "phi": [round(float(phie_clip[i]), 6) if np.isfinite(phie_clip[i]) else None for i in idx],
        "swir": [round(float(swir_clip[i]), 6) if np.isfinite(swir_clip[i]) else None for i in idx],
        "k_values": k_values,
        "summary": summary,
        "crossplot": crossplot,
        "fzi": fzi,
        "points": int(len(primary_valid)),
        "stats": summary[primary],
        "constants": {
            "coates_c": coates_c,
            "timur_a": timur_a,
            "sdr_a": sdr_a,
            "water_cut": water_cut,
        },
        "availability": {
            "sdr_available": t2gm is not None,
            "nmr_t2_curve": t2_cd.mnemonic if t2_cd else None,
        },
    }


@app.post("/api/wells/{wid}/probability-plot")
def probability_plot(wid: int, data: dict, db: Session = Depends(get_db)):
    """Generate cumulative frequency arrays for probability plotting."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    mnemonic = data.get("curve", "RT")
    n_bins = max(5, int(data.get("n_bins", 20)))
    start_depth = data.get("start_depth")
    stop_depth = data.get("stop_depth")

    cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == mnemonic).first()
    depth_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if not cd:
        raise HTTPException(404, f"Curve {mnemonic} not found")

    arr = np.frombuffer(cd.data_binary, dtype=np.float64).copy()
    # Apply depth filter if provided
    if depth_cd and (start_depth is not None or stop_depth is not None):
        depth_arr = np.frombuffer(depth_cd.data_binary, dtype=np.float64)
        mask = np.ones(len(arr), dtype=bool)
        if start_depth is not None:
            mask &= (depth_arr >= float(start_depth))
        if stop_depth is not None:
            mask &= (depth_arr <= float(stop_depth))
        arr = arr[mask]
    valid = arr[~np.isnan(arr)]
    valid = valid[valid > 0]
    if len(valid) == 0:
        return {
            "curve": mnemonic,
            "n": 0,
            "sorted_values": [],
            "percentiles": [],
            "p10": None,
            "p50": None,
            "p90": None,
            "mean": None,
            "std": None,
            "skewness": None,
        }

    sorted_vals = np.sort(valid)
    percentiles = (np.arange(1, len(sorted_vals) + 1) / (len(sorted_vals) + 1)) * 100.0

    # Return binned/sampled cumulative values using requested bin count
    q = np.linspace(1.0, 99.0, n_bins)
    sampled_vals = np.percentile(sorted_vals, q)

    mean_v = float(np.mean(valid))
    std_v = float(np.std(valid))
    if std_v > 0:
        skew = float(np.mean(((valid - mean_v) / std_v) ** 3))
    else:
        skew = 0.0

    return {
        "curve": mnemonic,
        "n": int(len(valid)),
        "sorted_values": [round(float(v), 3) for v in sampled_vals],
        "percentiles": [round(float(p), 3) for p in q],
        "p10": round(float(np.percentile(valid, 10)), 3),
        "p50": round(float(np.percentile(valid, 50)), 3),
        "p90": round(float(np.percentile(valid, 90)), 3),
        "mean": round(mean_v, 3),
        "std": round(std_v, 3),
        "skewness": round(skew, 3),
    }


@app.post("/api/wells/{wid}/moveable-oil")
def moveable_oil_index(wid: int, data: dict, db: Session = Depends(get_db)):
    """Compute apparent water resistivity (Rwa), flushed-zone Rwa, and moveable oil index."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    rt_curve = data.get("rt_curve", "RT")
    phie_curve = data.get("phie_curve", "PHIE")

    rt_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == rt_curve).first()
    # RXO fallback: try RXO → RS → RD → RILD → RILM
    rxo_cd = None
    for rxo_name in ["RXO", "RS", "RD", "RILD", "RILM", "RMED"]:
        rxo_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == rxo_name).first()
        if rxo_cd and rxo_cd != rt_cd:
            break
    phie_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == phie_curve).first()
    # PHIE fallback: compute from RHOB if not available
    if not phie_cd:
        rhob_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == "RHOB").first()
        if rhob_cd:
            rhob_arr = np.frombuffer(rhob_cd.data_binary, dtype=np.float64).copy()
            phie_arr = np.clip((2.65 - rhob_arr) / (2.65 - 1.0), 0, 1)
            phie_arr[rhob_arr <= 0] = np.nan
            phie_cd = rhob_cd  # reuse for length reference
            phie_computed = True
        else:
            phie_computed = False
    else:
        phie_computed = False
    depth_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if not rt_cd or not rxo_cd or not depth_cd:
        raise HTTPException(404, f"Required curves not found (need RT + at least one shallow resistivity + DEPTH). Available: {[c.mnemonic for c in db.query(CurveData).filter(CurveData.log_run_id == lr.id).all()]}")

    rt = np.frombuffer(rt_cd.data_binary, dtype=np.float64).copy()
    rxo = np.frombuffer(rxo_cd.data_binary, dtype=np.float64).copy()
    if phie_computed:
        phie = phie_arr
    else:
        phie = np.frombuffer(phie_cd.data_binary, dtype=np.float64).copy()
    depth = np.frombuffer(depth_cd.data_binary, dtype=np.float64).copy()

    pp = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    m = float(pp.m) if pp and pp.m is not None else 2.0

    phie_pow = np.power(np.clip(phie, 1e-6, 1.0), m)
    rwa = rt * phie_pow
    rxo_wa = rxo * phie_pow

    with np.errstate(divide="ignore", invalid="ignore"):
        moi = np.where((rwa > 0) & ~np.isnan(rwa) & ~np.isnan(rxo_wa), rxo_wa / rwa, np.nan)

    valid = moi[~np.isnan(moi)]
    step = max(1, len(depth) // 500)
    idx = list(range(0, len(depth), step))

    return {
        "depths": [round(float(depth[i]), 3) for i in idx],
        "rwa": [round(float(rwa[i]), 3) if not np.isnan(rwa[i]) else None for i in idx],
        "rxo_wa": [round(float(rxo_wa[i]), 3) if not np.isnan(rxo_wa[i]) else None for i in idx],
        "moi": [round(float(moi[i]), 3) if not np.isnan(moi[i]) else None for i in idx],
        "stats": {
            "min": round(float(np.min(valid)), 3) if len(valid) else None,
            "max": round(float(np.max(valid)), 3) if len(valid) else None,
            "mean": round(float(np.mean(valid)), 3) if len(valid) else None,
            "median": round(float(np.median(valid)), 3) if len(valid) else None,
        },
    }


@app.post("/api/wells/{wid}/dip-plot")
def dip_plot(wid: int, data: dict, db: Session = Depends(get_db)):
    """Generate tadpole plot arrays from stored deviation survey."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    points = db.query(DeviationSurvey).filter(DeviationSurvey.well_id == wid).order_by(DeviationSurvey.md).all()
    if not points:
        # Fallback: generate vertical well from log run depth data
        lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
        if not lr:
            raise HTTPException(404, "No deviation survey or log run data")
        depth_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
        if not depth_cd:
            depth_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id).order_by(CurveData.id.asc()).first()
        if not depth_cd or not depth_cd.data_binary:
            raise HTTPException(404, "No deviation survey and no depth data available")
        depths = np.frombuffer(depth_cd.data_binary, dtype=np.float64).copy()
        step = max(1, len(depths) // 200)
        idx = list(range(0, len(depths), step))
        return SafeJSONResponse({
            "md": [float(depths[i]) for i in idx],
            "inc": [0.0] * len(idx),
            "azi": [0.0] * len(idx),
            "dip": [0.0] * len(idx),
            "dip_direction": [0.0] * len(idx),
            "tvd": [float(depths[i]) for i in idx],
            "north": [0.0] * len(idx),
            "east": [0.0] * len(idx),
            "note": "Vertical well assumed (no deviation survey loaded)"
        })

    dip_type = str(data.get("dip_type", "structural")).lower()
    if dip_type not in ("structural", "apparent"):
        dip_type = "structural"

    md = np.array([float(p.md) for p in points], dtype=np.float64)
    inc = np.array([float(p.inc) for p in points], dtype=np.float64)
    azi = np.array([float(p.azi) for p in points], dtype=np.float64)
    tvd = np.array([float(p.tvd) if p.tvd is not None else np.nan for p in points], dtype=np.float64)
    north = np.array([float(p.northing) if p.northing is not None else np.nan for p in points], dtype=np.float64)
    east = np.array([float(p.easting) if p.easting is not None else np.nan for p in points], dtype=np.float64)

    # Structural dip approximation from consecutive survey points
    apparent_dip = np.full_like(md, np.nan)
    for i in range(1, len(md)):
        if np.isnan(tvd[i]) or np.isnan(tvd[i - 1]) or np.isnan(north[i]) or np.isnan(north[i - 1]) or np.isnan(east[i]) or np.isnan(east[i - 1]):
            continue
        dtvd = abs(tvd[i] - tvd[i - 1])
        dh = np.sqrt((north[i] - north[i - 1]) ** 2 + (east[i] - east[i - 1]) ** 2)
        if dh > 1e-6:
            apparent_dip[i] = np.degrees(np.arctan(dtvd / dh))

    step = max(1, len(md) // 500)
    idx = list(range(0, len(md), step))

    notes = "Structural dip approximated from consecutive survey TVD and horizontal displacement."
    if dip_type == "apparent":
        notes = "Apparent dip view uses inclination/azimuth arrays directly with computed TVD context."

    return {
        "md": [round(float(md[i]), 3) for i in idx],
        "inc": [round(float(inc[i]), 3) for i in idx],
        "azi": [round(float(azi[i]), 3) for i in idx],
        "tvd": [round(float(tvd[i]), 3) if not np.isnan(tvd[i]) else None for i in idx],
        "apparent_dip": [round(float(apparent_dip[i]), 3) if not np.isnan(apparent_dip[i]) else None for i in idx],
        "dip_type": dip_type,
        "notes": notes,
    }


# ─── Sprint 22: Buckles / Hingle / Curve Calculator ───────────
@app.post("/api/wells/{wid}/buckles")
def buckles_plot(wid: int, data: dict, db: Session = Depends(get_db)):
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    phie_curve = str(data.get("phie_curve", "NPHI")).upper()
    sw_curve = str(data.get("sw_curve", "SW")).upper()

    phie_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == phie_curve).first()
    depth_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH", "MD", "TVD"])).first()
    if not phie_cd or not depth_cd:
        raise HTTPException(404, f"Required curves not found (need {phie_curve} and depth)")

    sw_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == sw_curve).first()

    phie = np.frombuffer(phie_cd.data_binary, dtype=np.float64).copy()
    depth = np.frombuffer(depth_cd.data_binary, dtype=np.float64).copy()

    if sw_cd:
        sw = np.frombuffer(sw_cd.data_binary, dtype=np.float64).copy()
    else:
        # Compute Sw via Archie if SW curve missing
        rt_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["RT", "RESD", "RILD", "ILD"])).first()
        if not rt_cd:
            raise HTTPException(404, "SW curve not found and no RT curve available for Archie")
        rt = np.frombuffer(rt_cd.data_binary, dtype=np.float64).copy()

        pp = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
        a = float(pp.a) if pp and pp.a is not None else 1.0
        m = float(pp.m) if pp and pp.m is not None else 2.0
        n = float(pp.n) if pp and pp.n is not None else 2.0
        rw = float(pp.rw) if pp and pp.rw is not None else 0.1

        phi_eff = np.clip(phie, 1e-6, 1.0)
        rt_eff = np.clip(rt, 1e-6, None)
        with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
            sw = np.power((a * rw) / (rt_eff * np.power(phi_eff, m)), 1.0 / max(n, 1e-6))
        sw = np.clip(sw, 0.0, 1.0)

    npts = min(len(depth), len(phie), len(sw))
    depth = depth[:npts]
    phie = phie[:npts]
    sw = sw[:npts]

    bvw = phie * sw
    valid = ~np.isnan(depth) & ~np.isnan(phie) & ~np.isnan(sw) & ~np.isnan(bvw)
    valid &= np.isfinite(phie) & np.isfinite(sw) & np.isfinite(bvw)

    if np.any(valid):
        mean_bvw = float(np.mean(bvw[valid]))
        pay_fraction = float(np.mean(bvw[valid] < 0.12))
    else:
        mean_bvw = None
        pay_fraction = 0.0

    step = max(1, len(depth) // 500)
    idx = list(range(0, len(depth), step))

    return {
        "depths": [round(float(depth[i]), 3) if not np.isnan(depth[i]) else None for i in idx],
        "bvw": [round(float(bvw[i]), 5) if not np.isnan(bvw[i]) else None for i in idx],
        "phie": [round(float(phie[i]), 5) if not np.isnan(phie[i]) else None for i in idx],
        "sw": [round(float(sw[i]), 5) if not np.isnan(sw[i]) else None for i in idx],
        "stats": {
            "mean_bvw": round(mean_bvw, 6) if mean_bvw is not None else None,
            "pay_fraction": round(pay_fraction, 6),
        },
        "cutoffs": {"tight": 0.04, "pay": 0.12},
    }


@app.post("/api/wells/{wid}/hingle")
def hingle_plot(wid: int, data: dict, db: Session = Depends(get_db)):
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    rt_curve = str(data.get("rt_curve", "RT")).upper()
    x_curve = str(data.get("curve", data.get("x_curve", "RHOB"))).upper()
    use_log = bool(data.get("log", False))

    rt_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == rt_curve).first()
    x_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == x_curve).first()
    depth_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if not rt_cd or not x_cd or not depth_cd:
        raise HTTPException(404, "Required curves not found")

    rt = np.frombuffer(rt_cd.data_binary, dtype=np.float64).copy()
    x_raw = np.frombuffer(x_cd.data_binary, dtype=np.float64).copy()
    depth = np.frombuffer(depth_cd.data_binary, dtype=np.float64).copy()

    npts = min(len(depth), len(x_raw), len(rt))
    depth = depth[:npts]
    x_raw = x_raw[:npts]
    rt = rt[:npts]

    # Hingle plot: x-axis is the porosity-sensitive curve (RHOB, NPHI, etc.)
    # For RHOB: display as 1/RHOB (density porosity transform)
    # For NPHI: display directly
    x_label = x_curve
    if x_curve in ("RHOB", "RHOZ", "ZDEN", "RHOB_CAL"):
        with np.errstate(divide="ignore", invalid="ignore"):
            x = np.where(x_raw > 0, 1.0 / x_raw, np.nan)
        x_label = f"1/{x_curve}"
    else:
        x = x_raw
    with np.errstate(divide="ignore", invalid="ignore"):
        inv_rt = np.where(rt > 0, 1.0 / rt, np.nan)
        y = np.log(inv_rt) if use_log else inv_rt

    # Water-bearing approximation from high Sw (Sw ≈ 1) via Archie estimate
    pp = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    a = float(pp.a) if pp and pp.a is not None else 1.0
    m = float(pp.m) if pp and pp.m is not None else 2.0
    n = float(pp.n) if pp and pp.n is not None else 2.0
    rw = float(pp.rw) if pp and pp.rw is not None else 0.1

    # Estimate porosity for Sw calculation from the x-curve
    if x_curve in ("RHOB", "RHOZ", "ZDEN", "RHOB_CAL"):
        rho_ma = 2.65
        rho_f = 1.0
        phi_for_sw = np.clip((rho_ma - x_raw) / (rho_ma - rho_f), 1e-6, 1.0)
    else:
        phi_for_sw = np.clip(x_raw, 1e-6, 1.0)
    phi_eff = np.clip(phi_for_sw, 1e-6, 1.0)
    rt_eff = np.clip(rt, 1e-6, None)
    with np.errstate(divide="ignore", invalid="ignore", over="ignore"):
        sw_est = np.power((a * rw) / (rt_eff * np.power(phi_eff, m)), 1.0 / max(n, 1e-6))
    sw_est = np.clip(sw_est, 0.0, 1.0)

    water_mask = (~np.isnan(x)) & (~np.isnan(y)) & (~np.isnan(sw_est)) & (sw_est >= 0.9)
    if np.sum(water_mask) >= 2:
        slope, intercept = np.polyfit(x[water_mask], y[water_mask], 1)
        slope = float(slope)
        intercept = float(intercept)
    else:
        slope = None
        intercept = None

    valid = (~np.isnan(x)) & (~np.isnan(y))
    step = max(1, len(depth) // 500)
    idx = list(range(0, len(depth), step))

    return {
        "x": [round(float(x[i]), 6) if not np.isnan(x[i]) else None for i in idx],
        "y": [round(float(y[i]), 6) if not np.isnan(y[i]) else None for i in idx],
        "depths": [round(float(depth[i]), 3) if not np.isnan(depth[i]) else None for i in idx],
        "rw_line": {"slope": round(slope, 8) if slope is not None else None, "intercept": round(intercept, 8) if intercept is not None else None},
        "stats": {
            "points": int(np.sum(valid)),
            "water_points": int(np.sum(water_mask)),
            "mean_x": round(float(np.nanmean(x)), 6) if np.any(valid) else None,
            "mean_y": round(float(np.nanmean(y)), 6) if np.any(valid) else None,
            "mode": f"{x_label} vs {'log(1/RT)' if use_log else '1/RT'}",
        },
    }


@app.post("/api/wells/{wid}/curve-calc")
def curve_calc(wid: int, data: dict, db: Session = Depends(get_db)):
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    expression = str(data.get("expression", "")).strip()
    output_name = str(data.get("output_name", "")).strip().upper()
    if not expression or not output_name:
        raise HTTPException(400, "expression and output_name are required")

    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    all_curves = db.query(CurveData).filter(CurveData.log_run_id == lr.id).all()
    if not all_curves:
        raise HTTPException(404, "No curves found")

    # Whitelist expression safety checks
    import re
    allowed_funcs = {
        "sqrt", "log", "log10", "abs", "clip", "where",
        "sin", "cos", "tan", "arcsin", "arccos", "arctan",
        "exp", "power", "minimum", "maximum", "np"
    }
    tokens = re.findall(r"[A-Za-z_][A-Za-z0-9_]*", expression)

    safe_ns = {
        "np": np,
        "sqrt": np.sqrt,
        "log": np.log,
        "log10": np.log10,
        "abs": np.abs,
        "clip": np.clip,
        "where": np.where,
        "sin": np.sin,
        "cos": np.cos,
        "tan": np.tan,
        "arcsin": np.arcsin,
        "arccos": np.arccos,
        "arctan": np.arctan,
        "exp": np.exp,
        "power": np.power,
        "minimum": np.minimum,
        "maximum": np.maximum,
    }

    curve_arrays = {}
    for cd in all_curves:
        arr = np.frombuffer(cd.data_binary, dtype=np.float64).copy()
        safe_ns[cd.mnemonic] = arr
        curve_arrays[cd.mnemonic] = arr

    curve_names = set(curve_arrays.keys())
    for t in tokens:
        if t in allowed_funcs:
            continue
        if t in curve_names:
            continue
        raise HTTPException(400, f"Unsupported token in expression: {t}")

    try:
        result = eval(expression, {"__builtins__": {}}, safe_ns)
    except Exception as e:
        raise HTTPException(400, f"Expression evaluation error: {str(e)[:200]}")

    if np.isscalar(result):
        # broadcast scalar across longest curve length
        max_len = max(len(a) for a in curve_arrays.values())
        result_arr = np.full(max_len, float(result), dtype=np.float64)
    else:
        result_arr = np.asarray(result, dtype=np.float64)

    valid = result_arr[~np.isnan(result_arr)]

    existing = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == output_name).first()
    if existing:
        existing.data_binary = result_arr.tobytes()
        existing.num_points = len(result_arr)
        existing.min_value = float(np.min(valid)) if len(valid) else None
        existing.max_value = float(np.max(valid)) if len(valid) else None
        existing.description = f"Calculated curve: {expression}"
        curve_name = existing.mnemonic
    else:
        new_cd = CurveData(
            log_run_id=lr.id,
            mnemonic=output_name,
            unit="",
            description=f"Calculated curve: {expression}",
            num_points=len(result_arr),
            min_value=float(np.min(valid)) if len(valid) else None,
            max_value=float(np.max(valid)) if len(valid) else None,
            data_binary=result_arr.tobytes(),
        )
        db.add(new_cd)
        curve_name = output_name

    db.commit()

    return {
        "status": "ok",
        "curve_name": curve_name,
        "points": int(len(result_arr)),
        "min": round(float(np.min(valid)), 6) if len(valid) else None,
        "max": round(float(np.max(valid)), 6) if len(valid) else None,
        "mean": round(float(np.mean(valid)), 6) if len(valid) else None,
    }


@app.get("/api/wells/{wid}/data-table")
def get_data_table(
    wid: int,
    curves: str = "",
    from_depth: float = None,
    to_depth: float = None,
    limit: int = 500,
    db: Session = Depends(get_db),
):
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    selected = [c.strip().upper() for c in str(curves or "").split(",") if c.strip()]
    if not selected:
        selected = ["DEPT"]

    depth_cd = db.query(CurveData).filter(
        CurveData.log_run_id == lr.id,
        CurveData.mnemonic.in_(["DEPT", "DEPTH", "MD", "TVD"]),
    ).first()
    if not depth_cd:
        raise HTTPException(404, "Depth curve not found")

    depth = np.frombuffer(depth_cd.data_binary, dtype=np.float64).copy()
    curve_arrays = {"DEPT": depth}

    for mnem in selected:
        if mnem in ("DEPT", "DEPTH", "MD", "TVD"):
            curve_arrays[mnem] = depth
            continue
        cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == mnem).first()
        if not cd:
            raise HTTPException(404, f"Curve not found: {mnem}")
        curve_arrays[mnem] = np.frombuffer(cd.data_binary, dtype=np.float64).copy()

    columns = selected
    if not any(c in ("DEPT", "DEPTH", "MD", "TVD") for c in columns):
        columns = ["DEPT"] + columns

    min_len = min(len(curve_arrays[c]) for c in columns)
    for c in list(curve_arrays.keys()):
        curve_arrays[c] = curve_arrays[c][:min_len]

    depth_arr = curve_arrays["DEPT"]
    mask = np.ones(min_len, dtype=bool)
    if from_depth is not None:
        mask &= depth_arr >= float(from_depth)
    if to_depth is not None:
        mask &= depth_arr <= float(to_depth)

    idx = np.where(mask)[0]
    total_points = int(len(idx))

    limit = max(1, int(limit or 500))
    if len(idx) > limit:
        step = int(np.ceil(len(idx) / float(limit)))
        idx = idx[::step][:limit]

    def _clean_value(v):
        if np.isnan(v) or float(v) == -999.25:
            return None
        return round(float(v), 3)

    rows = []
    for i in idx:
        rows.append([_clean_value(curve_arrays[c][i]) for c in columns])

    return {
        "columns": columns,
        "rows": rows,
        "total_points": total_points,
        "shown_points": int(len(rows)),
    }


@app.get("/api/projects/{pid}/tops-export")
def export_project_tops(pid: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == pid).first()
    if not project:
        raise HTTPException(404, "Project not found")

    tops = (
        db.query(FormationTop, Well)
        .join(Well, FormationTop.well_id == Well.id)
        .filter(Well.project_id == pid)
        .order_by(Well.name.asc(), FormationTop.depth.asc())
        .all()
    )

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["well_name", "uwi", "formation_name", "depth", "top_depth", "base_depth", "color", "lithology", "notes"])
    for top, well in tops:
        writer.writerow([
            well.name,
            well.uwi,
            top.formation_name,
            top.depth,
            top.top_depth,
            top.base_depth,
            top.color,
            top.lithology,
            top.notes,
        ])

    csv_text = out.getvalue()
    out.close()
    headers = {"Content-Disposition": f'attachment; filename="project_{pid}_tops.csv"'}
    return StreamingResponse(iter([csv_text]), media_type="text/csv", headers=headers)


@app.post("/api/wells/{wid}/tops-import")
def import_tops_csv(wid: int, data: dict, db: Session = Depends(get_db)):
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    csv_data = data.get("csv_data")
    if not csv_data:
        raise HTTPException(400, "csv_data is required")

    imported = 0
    skipped = 0
    errors = []

    reader = csv.DictReader(io.StringIO(str(csv_data)))
    for line_no, row in enumerate(reader, start=2):
        try:
            row_well_name = (row.get("well_name") or "").strip()
            row_uwi = (row.get("uwi") or "").strip()
            if row_well_name and row_well_name != (well.name or ""):
                skipped += 1
                errors.append(f"line {line_no}: well_name mismatch ({row_well_name})")
                continue
            if row_uwi and row_uwi != (well.uwi or ""):
                skipped += 1
                errors.append(f"line {line_no}: uwi mismatch ({row_uwi})")
                continue

            formation_name = (row.get("formation_name") or "").strip()
            if not formation_name:
                skipped += 1
                errors.append(f"line {line_no}: formation_name is required")
                continue

            depth_val = row.get("depth")
            if depth_val in (None, ""):
                skipped += 1
                errors.append(f"line {line_no}: depth is required")
                continue

            top = FormationTop(
                well_id=wid,
                formation_name=formation_name,
                depth=float(depth_val),
                top_depth=float(row["top_depth"]) if row.get("top_depth") not in (None, "") else None,
                base_depth=float(row["base_depth"]) if row.get("base_depth") not in (None, "") else None,
                color=(row.get("color") or None),
                lithology=(row.get("lithology") or None),
                notes=(row.get("notes") or None),
            )
            db.add(top)
            imported += 1
        except Exception as e:
            skipped += 1
            errors.append(f"line {line_no}: {str(e)}")

    db.commit()
    return {"imported": imported, "skipped": skipped, "errors": errors}


@app.get("/api/projects/{pid}/formation-matrix")
def formation_matrix(pid: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == pid).first()
    if not project:
        raise HTTPException(404, "Project not found")

    wells = db.query(Well).filter(Well.project_id == pid).order_by(Well.name.asc()).all()
    formation_names = set()
    well_rows = []

    for w in wells:
        tops = db.query(FormationTop).filter(FormationTop.well_id == w.id).order_by(FormationTop.depth.asc()).all()
        tops_map = {}
        for t in tops:
            if t.formation_name not in tops_map:
                tops_map[t.formation_name] = round(float(t.depth), 3) if t.depth is not None else None
            formation_names.add(t.formation_name)
        well_rows.append({"name": w.name, "uwi": w.uwi, "tops": tops_map})

    return {
        "formations": sorted(formation_names),
        "wells": well_rows,
    }


@app.post("/api/projects/{pid}/batch-petro")
def batch_petro_params(pid: int, data: dict, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == pid).first()
    if not project:
        raise HTTPException(404, "Project not found")

    wells = db.query(Well).filter(Well.project_id == pid).all()
    fields = ["saturation_model", "a", "m", "n", "rw", "vsh_cutoff", "phie_cutoff", "sw_cutoff", "template"]
    numeric_fields = {"a", "m", "n", "rw", "vsh_cutoff", "phie_cutoff", "sw_cutoff"}

    updated_wells = []
    for w in wells:
        existing = db.query(PetroParams).filter(PetroParams.well_id == w.id).first()
        if existing:
            for f in fields:
                if f in data:
                    val = float(data[f]) if f in numeric_fields and data[f] is not None else data[f]
                    setattr(existing, f, val)
        else:
            kwargs = {"well_id": w.id}
            for f in fields:
                if f in data:
                    kwargs[f] = float(data[f]) if f in numeric_fields and data[f] is not None else data[f]
            db.add(PetroParams(**kwargs))
        updated_wells.append(w.name)

    db.commit()
    return {"updated": len(updated_wells), "wells": updated_wells}


@app.get("/api/projects/{pid}/summary")
def project_summary(pid: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == pid).first()
    if not project:
        raise HTTPException(404, "Project not found")

    wells = db.query(Well).filter(Well.project_id == pid).order_by(Well.name.asc()).all()

    total_log_runs = 0
    total_tops = 0
    total_zones = 0
    total_curves = 0
    unique_formations = set()
    well_rows = []

    for w in wells:
        log_runs = db.query(LogRun).filter(LogRun.well_id == w.id).all()
        tops = db.query(FormationTop).filter(FormationTop.well_id == w.id).all()
        zones = db.query(Zone).filter(Zone.well_id == w.id).all()

        log_runs_count = len(log_runs)
        tops_count = len(tops)
        zones_count = len(zones)

        curve_count = 0
        for lr in log_runs:
            curve_count += db.query(CurveData).filter(CurveData.log_run_id == lr.id).count()

        for t in tops:
            if t.formation_name:
                unique_formations.add(t.formation_name)

        gross_ft = 0.0
        for z in zones:
            if z.top_depth is not None and z.bottom_depth is not None:
                gross_ft += abs(float(z.bottom_depth) - float(z.top_depth))

        avg_thickness = (gross_ft / zones_count) if zones_count > 0 else 0.0
        net_ft = float(zones_count) * avg_thickness

        petro = db.query(PetroParams).filter(PetroParams.well_id == w.id).first()
        _avg_porosity = float(petro.phie_cutoff) if petro and petro.phie_cutoff is not None else None

        total_log_runs += log_runs_count
        total_tops += tops_count
        total_zones += zones_count
        total_curves += curve_count

        well_rows.append({
            "name": w.name,
            "uwi": w.uwi,
            "lat": float(w.latitude) if w.latitude is not None else None,
            "lon": float(w.longitude) if w.longitude is not None else None,
            "elevation": float(w.elevation) if w.elevation is not None else None,
            "total_depth": float(w.total_depth) if w.total_depth is not None else None,
            "log_runs": log_runs_count,
            "tops": tops_count,
            "zones": zones_count,
            "curves": curve_count,
            "gross_ft": round(float(gross_ft), 3),
            "net_ft": round(float(net_ft), 3),
        })

    return {
        "project": {
            "name": project.name,
            "field_name": project.field_name,
            "operator": project.operator,
            "country": project.country,
        },
        "total_wells": len(wells),
        "total_log_runs": total_log_runs,
        "total_tops": total_tops,
        "total_zones": total_zones,
        "total_curves": total_curves,
        "unique_formations": sorted(unique_formations),
        "wells": well_rows,
    }


@app.get("/api/projects/{pid}/well-locations")
def project_well_locations(pid: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == pid).first()
    if not project:
        raise HTTPException(404, "Project not found")

    wells = (
        db.query(Well)
        .filter(Well.project_id == pid)
        .filter(Well.latitude.isnot(None), Well.longitude.isnot(None))
        .order_by(Well.name.asc())
        .all()
    )

    return {
        "wells": [
            {
                "id": w.id,
                "name": w.name,
                "uwi": w.uwi,
                "lat": float(w.latitude),
                "lon": float(w.longitude),
            }
            for w in wells
        ]
    }


@app.get("/api/wells/{wid}/tops-petrel")
def export_tops_petrel(wid: int, db: Session = Depends(get_db)):
    """Export well tops in Petrel-compatible CSV format."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    tops = (
        db.query(FormationTop)
        .filter(FormationTop.well_id == wid)
        .order_by(FormationTop.depth.asc(), FormationTop.id.asc())
        .all()
    )

    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([
        "WELL", "UWI", "HORIZON", "MD", "TVD", "X_OFFSET", "Y_OFFSET", "LATITUDE", "LONGITUDE", "COMMENTS"
    ])

    for t in tops:
        depth_val = t.depth if t.depth is not None else t.top_depth
        writer.writerow([
            well.name or "",
            well.uwi or "",
            t.formation_name or "",
            depth_val if depth_val is not None else "",
            depth_val if depth_val is not None else "",
            "",
            "",
            well.latitude if well.latitude is not None else "",
            well.longitude if well.longitude is not None else "",
            t.notes or "",
        ])

    csv_text = out.getvalue()
    out.close()
    headers = {"Content-Disposition": f'attachment; filename="well_{wid}_tops_petrel.csv"'}
    return StreamingResponse(iter([csv_text]), media_type="text/csv", headers=headers)


# ─── Helper: Audit Log ────────────────────────────────────────
def _log_audit(db: Session, action: str, entity_type: str = "", entity_id: int = None,
               well_id: int = None, project_id: int = None, details: str = ""):
    """Write an audit trail entry."""
    db.add(AuditLog(
        project_id=project_id, well_id=well_id, action=action,
        entity_type=entity_type, entity_id=entity_id, details=details
    ))
    db.commit()


# ─── Audit Trail ──────────────────────────────────────────────
@app.get("/api/audit-log")
def get_audit_log(project_id: int = None, well_id: int = None, limit: int = 100,
                  db: Session = Depends(get_db)):
    """Return audit trail, optionally filtered by project or well."""
    q = db.query(AuditLog)
    if project_id:
        q = q.filter(AuditLog.project_id == project_id)
    if well_id:
        q = q.filter(AuditLog.well_id == well_id)
    rows = q.order_by(AuditLog.created_at.desc()).limit(min(limit, 500)).all()
    result = []
    for r in rows:
        d = {c.name: getattr(r, c.name) for c in AuditLog.__table__.columns}
        d["created_at"] = d["created_at"].isoformat() if d["created_at"] else ""
        result.append(d)
    return result


def _compute_audit_chain_report(limit: int, db: Session):
    rows = db.query(AuditLog).order_by(AuditLog.id.asc()).limit(min(max(limit, 1), 10000)).all()
    issues = []
    verified = 0
    prev_hash = ""

    for r in rows:
        canonical = json.dumps({
            "request_id": r.request_id or "",
            "subject": r.auth_subject or "",
            "role": r.auth_role or "viewer",
            "method": (r.method or "").upper(),
            "path": r.route_path or "",
            "status": int(r.status_code) if r.status_code is not None else 0,
            "payload_hash": r.payload_hash or "",
            "prev_hash": r.prev_hash or "",
            "well_id": r.well_id,
            "project_id": r.project_id,
        }, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        recomputed = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

        if (r.prev_hash or "") != prev_hash:
            issues.append({"id": r.id, "type": "prev_hash_mismatch", "expected": prev_hash, "actual": r.prev_hash or ""})
        if (r.entry_hash or "") != recomputed:
            issues.append({"id": r.id, "type": "entry_hash_mismatch", "expected": recomputed, "actual": r.entry_hash or ""})

        prev_hash = r.entry_hash or ""
        verified += 1

    return {
        "ok": len(issues) == 0,
        "verified_entries": verified,
        "issues": issues,
    }


@app.get("/api/audit-log/verify")
def verify_audit_log_chain(limit: int = 2000, db: Session = Depends(get_db)):
    """Recompute immutable audit chain and report tamper gaps."""
    return _compute_audit_chain_report(limit, db)


@app.get("/api/audit-log/immutability-status")
def audit_log_immutability_status(_role: str = Depends(require_viewer)):
    """Report whether append-only audit triggers are installed."""
    trigger_names = ["trg_audit_log_no_update", "trg_audit_log_no_delete"]
    present: dict[str, bool] = {k: False for k in trigger_names}

    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='trigger' AND name IN ('trg_audit_log_no_update','trg_audit_log_no_delete')")
        ).fetchall()

    for row in rows:
        n = str(row[0])
        if n in present:
            present[n] = True

    return {
        "ok": all(present.values()),
        "append_only_enforced": all(present.values()),
        "triggers": present,
    }


def _resolve_audit_export_signing_key(requested_kid: str | None = None):
    """Resolve signing key with optional key rotation.

    Priority:
    1) requested_kid -> AUDIT_EXPORT_HMAC_KEYS_JSON map
    2) AUDIT_EXPORT_HMAC_ACTIVE_KID -> AUDIT_EXPORT_HMAC_KEYS_JSON map
    3) legacy AUDIT_EXPORT_HMAC_KEY (kid='legacy')
    """
    keys_json = (os.getenv("AUDIT_EXPORT_HMAC_KEYS_JSON") or "").strip()
    active_kid = (os.getenv("AUDIT_EXPORT_HMAC_ACTIVE_KID") or "").strip()

    key_map = {}
    if keys_json:
        try:
            parsed = json.loads(keys_json)
            if isinstance(parsed, dict):
                key_map = {str(k): str(v) for k, v in parsed.items() if str(v)}
        except Exception:
            raise HTTPException(status_code=500, detail="AUDIT_EXPORT_HMAC_KEYS_JSON is invalid JSON")

    if requested_kid:
        if requested_kid in key_map:
            return requested_kid, key_map[requested_kid]
        legacy = (os.getenv("AUDIT_EXPORT_HMAC_KEY") or "").strip()
        if requested_kid == "legacy" and legacy:
            return "legacy", legacy
        raise HTTPException(status_code=400, detail=f"unknown signature kid: {requested_kid}")

    if active_kid and active_kid in key_map:
        return active_kid, key_map[active_kid]

    legacy = (os.getenv("AUDIT_EXPORT_HMAC_KEY") or "").strip()
    if legacy:
        return "legacy", legacy

    if active_kid and key_map and active_kid not in key_map:
        raise HTTPException(status_code=500, detail="AUDIT_EXPORT_HMAC_ACTIVE_KID not present in AUDIT_EXPORT_HMAC_KEYS_JSON")

    raise HTTPException(status_code=500, detail="no signing key configured")


@app.get("/api/audit-log/verify/export")
def export_audit_log_verification(
    request: Request,
    limit: int = 2000,
    sign: bool = False,
    kid: str | None = None,
    db: Session = Depends(get_db),
):
    """Export verification report with SHA256 digest and optional detached HMAC signature."""
    report = _compute_audit_chain_report(limit, db)
    payload = {
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
        "report": report,
        "trace": {
            "request_id": request.headers.get("X-Request-ID") or "",
            "auth_subject": str(getattr(request.state, "auth_subject", "") or ""),
            "auth_role": str(getattr(request.state, "user_role", "viewer") or "viewer"),
            "input": {"limit": int(limit)},
            "code_version": (os.getenv("GEOLOG_CODE_VERSION") or "unknown").strip() or "unknown",
        },
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    out = {
        "digest_sha256": digest,
        "payload": payload,
        "signature": None,
        "signature_alg": None,
        "signature_detached": True,
        "signature_kid": None,
    }

    if sign:
        resolved_kid, key_raw = _resolve_audit_export_signing_key(kid)
        key = key_raw.encode("utf-8")
        sig = hmac.new(key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        out["signature"] = sig
        out["signature_alg"] = "hmac-sha256"
        out["signature_kid"] = resolved_kid

    return out


AuditReasonCode = Literal[
    "SIGNATURE_VALID",
    "SIGNATURE_MISMATCH",
    "UNKNOWN_KID",
    "INVALID_KEYRING_JSON",
    "ACTIVE_KID_MISSING",
    "KEY_NOT_CONFIGURED",
    "KEY_RESOLUTION_ERROR",
]


class AuditSignatureVerifyRequest(BaseModel):
    payload: dict[str, Any]
    signature: str = Field(..., min_length=64, max_length=64, pattern="^[0-9a-fA-F]{64}$")
    kid: str | None = None


class AuditSignatureVerifyResponse(BaseModel):
    ok: bool
    reason: str
    reason_code: AuditReasonCode
    signature_alg: str
    signature_kid: str | None = None


def _verify_audit_export_signature_payload(payload_obj: dict, signature: str, kid: str | None = None):
    if not isinstance(payload_obj, dict):
        raise HTTPException(status_code=400, detail="payload JSON must be an object")
    if (
        not isinstance(signature, str)
        or len(signature) != 64
        or any(ch not in "0123456789abcdefABCDEF" for ch in signature)
    ):
        raise HTTPException(status_code=400, detail="signature must be a 64-char hex string")

    canonical = json.dumps(payload_obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

    try:
        resolved_kid, key_raw = _resolve_audit_export_signing_key(kid or None)
    except HTTPException as e:
        detail = str(e.detail)
        reason_code = "KEY_RESOLUTION_ERROR"
        if "unknown signature kid" in detail:
            reason_code = "UNKNOWN_KID"
        elif "invalid JSON" in detail:
            reason_code = "INVALID_KEYRING_JSON"
        elif "not present" in detail:
            reason_code = "ACTIVE_KID_MISSING"
        elif "no signing key configured" in detail:
            reason_code = "KEY_NOT_CONFIGURED"
        return {
            "ok": False,
            "reason": detail,
            "reason_code": reason_code,
            "signature_alg": "hmac-sha256",
            "signature_kid": kid or None,
        }

    expected = hmac.new(key_raw.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    ok = hmac.compare_digest(expected, signature)

    return {
        "ok": ok,
        "reason": "signature_valid" if ok else "signature_mismatch",
        "reason_code": "SIGNATURE_VALID" if ok else "SIGNATURE_MISMATCH",
        "signature_alg": "hmac-sha256",
        "signature_kid": resolved_kid,
    }


@app.get(
    "/api/audit-log/verify/signature",
    response_model=AuditSignatureVerifyResponse,
    responses={
        200: {
            "description": "Signature verification result",
            "content": {
                "application/json": {
                    "examples": {
                        "valid": {
                            "summary": "Valid signature",
                            "value": {
                                "ok": True,
                                "reason": "signature_valid",
                                "reason_code": "SIGNATURE_VALID",
                                "signature_alg": "hmac-sha256",
                                "signature_kid": "k1",
                            },
                        },
                        "mismatch": {
                            "summary": "Signature mismatch",
                            "value": {
                                "ok": False,
                                "reason": "signature_mismatch",
                                "reason_code": "SIGNATURE_MISMATCH",
                                "signature_alg": "hmac-sha256",
                                "signature_kid": "k1",
                            },
                        },
                    }
                }
            },
        }
    },
)
def verify_audit_log_export_signature(payload: str, signature: str, kid: str | None = None):
    """Verify detached HMAC signature for exported audit verification payload.

    payload: canonical payload JSON string.
    """
    if not isinstance(payload, str) or not payload.strip():
        raise HTTPException(status_code=400, detail="payload must be a non-empty JSON string")

    try:
        parsed_payload = json.loads(payload)
    except Exception:
        raise HTTPException(status_code=400, detail="payload must be valid JSON")

    return _verify_audit_export_signature_payload(parsed_payload, signature, kid)


@app.post(
    "/api/audit-log/verify/signature",
    response_model=AuditSignatureVerifyResponse,
)
def verify_audit_log_export_signature_post(
    data: AuditSignatureVerifyRequest,
    _role: str = Depends(require_interpreter),
):
    """M2M verifier. Body: {payload: object, signature: hex64, kid?: string}."""
    return _verify_audit_export_signature_payload(data.payload, data.signature, data.kid)


# ─── Cross-Plot Matrix (multi-well) ──────────────────────────
@app.get("/api/projects/{pid}/crossplot-matrix")
def crossplot_matrix(pid: int, curve_x: str = "GR", curve_y: str = "RT",
                     db: Session = Depends(get_db)):
    """Return X/Y scatter data for all wells in a project."""
    wells = db.query(Well).filter(Well.project_id == pid).all()
    series = []
    for w in wells:
        lr = db.query(LogRun).filter(LogRun.well_id == w.id).order_by(LogRun.num_points.desc()).first()
        if not lr:
            continue
        cd_x = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == curve_x).first()
        cd_y = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == curve_y).first()
        if not cd_x or not cd_y:
            continue
        x = np.frombuffer(cd_x.data_binary, dtype=np.float64).tolist()
        y = np.frombuffer(cd_y.data_binary, dtype=np.float64).tolist()
        n = min(len(x), len(y), 2000)
        # Decimate if too many points
        step = max(1, len(x) // 2000)
        xs = [x[i] for i in range(0, n, step)]
        ys = [y[i] for i in range(0, n, step)]
        series.append({"well_name": w.name, "well_id": w.id, "x": xs, "y": ys, "count": len(xs)})
    return {"curve_x": curve_x, "curve_y": curve_y, "wells": series}


# ─── Performance: Decimated Curve Data ────────────────────────
@app.get("/api/log-runs/{lr_id}/data-decimated")
def get_decimated_data(
    lr_id: int,
    max_points: int = 3000,
    start_depth: float = None,
    stop_depth: float = None,
    if_none_match: str = Header(default=None),
    if_modified_since: str = Header(default=None),
    db: Session = Depends(get_db),
):
    """Return curve data decimated to <= max_points using LTTB."""
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first()
    if not lr:
        raise HTTPException(404, "Log run not found")

    max_points = max(200, min(int(max_points or 3000), 50000))
    curves = db.query(CurveData).filter(CurveData.log_run_id == lr_id).all()

    headers = _build_curve_cache_headers(lr_id, [c.mnemonic for c in curves], start_depth, stop_depth, 1, max_points=max_points)
    last_modified_dt = (lr.uploaded_at or datetime.datetime.utcnow()).replace(tzinfo=datetime.timezone.utc)
    headers["Last-Modified"] = _httpdate(last_modified_dt)

    if if_none_match and if_none_match.strip() == headers["ETag"]:
        return SafeJSONResponse(status_code=304, content=None, headers=headers)
    ims = _parse_if_modified_since(if_modified_since)
    if ims is not None and last_modified_dt <= ims:
        return SafeJSONResponse(status_code=304, content=None, headers=headers)

    depth_curve = db.query(CurveData).filter(
        CurveData.log_run_id == lr_id,
        CurveData.mnemonic.in_(["DEPT", "DEPTH", "MD", "TVD"])
    ).first()
    if not depth_curve:
        depth_curve = db.query(CurveData).filter(CurveData.log_run_id == lr_id).order_by(CurveData.id.asc()).first()
    depth_arr = np.frombuffer(depth_curve.data_binary, dtype=np.float64).copy() if depth_curve and depth_curve.data_binary else None

    mask = None
    if depth_arr is not None and (start_depth is not None or stop_depth is not None):
        mask = np.ones(len(depth_arr), dtype=bool)
        if start_depth is not None:
            mask &= (depth_arr >= float(start_depth))
        if stop_depth is not None:
            mask &= (depth_arr <= float(stop_depth))

    result = {}
    original_points = 0
    output_points = 0
    decimated = False

    for cd in curves:
        full_arr = np.frombuffer(cd.data_binary, dtype=np.float64).copy()
        arr = full_arr[mask] if (mask is not None and len(full_arr) == len(depth_arr)) else full_arr
        n = int(len(arr))
        if n > original_points:
            original_points = n

        if n <= max_points:
            sampled = [None if np.isnan(v) else float(v) for v in arr]
        else:
            x_axis = (depth_arr[mask] if mask is not None else depth_arr) if (depth_arr is not None and len(full_arr) == len(depth_arr)) else np.arange(n, dtype=np.float64)
            indices = _lttb_indices(np.asarray(x_axis, dtype=np.float64), np.asarray(arr, dtype=np.float64), max_points)
            sampled = [None if np.isnan(arr[i]) else float(arr[i]) for i in indices]
            decimated = True

        if len(sampled) > output_points:
            output_points = len(sampled)
        result[cd.mnemonic] = sampled

    return SafeJSONResponse(content={
        "curves": result,
        "decimated": decimated,
        "original_points": original_points,
        "output_points": output_points,
        "max_points": max_points,
    }, headers=headers)


# ─── Sprint 27: Dual-Water Saturation Model ─────────────────
@app.post("/api/wells/{wid}/dual-water")
def compute_dual_water(wid: int, data: dict, db: Session = Depends(get_db)):
    """Compute Sw using Dual-Water model (Clavier et al. 1977).
    Sw = sqrt( (a * Rw) / (phi^m * Rt) * (1 - (Rw/Rwb) * (Vsh * phi_sh / phi)) )
    Simplified: Sw_dw = Sw_archie * correction_factor
    """
    lr_id = data.get("log_run_id")
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else \
         db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    rt_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["RT", "RESD", "RILD", "ILD"])).first()
    nphi_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["NPHI", "NPHI_LS"])).first()
    gr_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["GR", "SGR", "CGR"])).first()
    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if not rt_cd or not nphi_cd:
        raise HTTPException(400, "Need RT and NPHI curves")

    rt = np.frombuffer(rt_cd.data_binary, dtype=np.float64).copy()
    nphi = np.frombuffer(nphi_cd.data_binary, dtype=np.float64).copy()
    gr = np.frombuffer(gr_cd.data_binary, dtype=np.float64).copy() if gr_cd else np.zeros_like(rt)
    dept = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy() if dept_cd else np.arange(len(rt)) * 0.5

    a_v = float(data.get("a", 1.0))
    m_v = float(data.get("m", 2.0))
    n_v = float(data.get("n", 2.0))
    rw = float(data.get("rw", 0.1))
    rwb = float(data.get("rwb", 0.03))  # bound water resistivity
    phi_sh = float(data.get("phi_sh", 0.30))  # shale porosity
    vsh_cutoff = float(data.get("vsh_cutoff", 0.35))

    # Vsh from GR
    gr_valid = gr[~np.isnan(gr) & (gr > 0)]
    gr_min = float(np.min(gr_valid)) if len(gr_valid) else 0
    gr_max = float(np.max(gr_valid)) if len(gr_valid) else 150
    if gr_max == gr_min:
        gr_max = gr_min + 1

    n = len(rt)
    sw = np.full(n, np.nan)
    vsh_arr = np.full(n, np.nan)
    phie_arr = np.full(n, np.nan)
    bvw_arr = np.full(n, np.nan)

    for i in range(n):
        if np.isnan(rt[i]) or np.isnan(nphi[i]) or rt[i] <= 0 or nphi[i] < 0:
            continue
        igr = (gr[i] - gr_min) / (gr_max - gr_min) if gr_max > gr_min else 0
        vsh_v = max(0, min(1, igr))
        vsh_arr[i] = vsh_v

        phi_t = max(0.01, nphi[i])
        # Dual-water: effective porosity = total - bound water
        phi_e = phi_t * (1 - vsh_v * (1 - phi_sh / max(phi_t, 0.01)))
        phi_e = max(0.01, phi_e)
        phie_arr[i] = phi_e

        # Sw calculation with bound water correction
        sw_archie = (a_v * rw / (phi_e ** m_v * rt[i])) ** (1.0 / n_v)
        # Bound water volume
        vwb = vsh_v * phi_sh
        # Dual-water correction
        if phi_e > 0:
            correction = 1 - (rw / rwb) * (vwb / phi_e)
            sw_v = sw_archie * max(0, correction)
        else:
            sw_v = 1.0
        sw[i] = max(0, min(1, sw_v))
        bvw_arr[i] = sw[i] * phi_e  # bulk volume water

    valid_sw = sw[~np.isnan(sw)]
    valid_phie = phie_arr[~np.isnan(phie_arr)]
    valid_bvw = bvw_arr[~np.isnan(bvw_arr)]

    return {
        "depth": dept.tolist(),
        "sw": sw.tolist(),
        "vsh": vsh_arr.tolist(),
        "phie": phie_arr.tolist(),
        "bvw": bvw_arr.tolist(),
        "stats": {
            "sw_mean": round(float(np.mean(valid_sw)), 4) if len(valid_sw) else None,
            "sw_median": round(float(np.median(valid_sw)), 4) if len(valid_sw) else None,
            "phie_mean": round(float(np.mean(valid_phie)), 4) if len(valid_phie) else None,
            "bvw_mean": round(float(np.mean(valid_bvw)), 4) if len(valid_bvw) else None,
            "model": "dual_water",
            "rwb": rwb,
            "phi_sh": phi_sh,
        }
    }


# ─── Sprint 27: Vcl Model Selector ──────────────────────────
@app.post("/api/wells/{wid}/vcl-models")
def compute_vcl_models(wid: int, data: dict, db: Session = Depends(get_db)):
    """Compute Vclay using multiple models for comparison.
    Models: larionov_tertiary, larionov_old, clavier, steiber, linear_igr
    """
    lr_id = data.get("log_run_id")
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else \
         db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    gr_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["GR", "SGR", "CGR"])).first()
    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if not gr_cd:
        raise HTTPException(400, "GR curve required")

    gr = np.frombuffer(gr_cd.data_binary, dtype=np.float64).copy()
    dept = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy() if dept_cd else np.arange(len(gr)) * 0.5

    gr_clean = float(data.get("gr_clean", 20))  # GR in clean sand
    gr_shale = float(data.get("gr_shale", 120))  # GR in shale

    n = len(gr)
    results = {
        "depth": dept.tolist(),
        "igr": np.full(n, np.nan).tolist(),
        "larionov_tertiary": np.full(n, np.nan).tolist(),
        "larionov_old": np.full(n, np.nan).tolist(),
        "clavier": np.full(n, np.nan).tolist(),
        "steiber": np.full(n, np.nan).tolist(),
    }

    for i in range(n):
        if np.isnan(gr[i]) or gr[i] < 0:
            continue
        # IGR (Linear Gamma Ray Index)
        igr = (gr[i] - gr_clean) / (gr_shale - gr_clean) if gr_shale > gr_clean else 0
        igr = max(0, min(1, igr))
        results["igr"][i] = round(igr, 4)

        # Larionov (Tertiary rocks): Vcl = 0.083 * (2^(3.7*IGR) - 1)
        vcl_lt = 0.083 * (2 ** (3.7 * igr) - 1)
        results["larionov_tertiary"][i] = round(max(0, min(1, vcl_lt)), 4)

        # Larionov (Older rocks): Vcl = 0.33 * (2^(2*IGR) - 1)
        vcl_lo = 0.33 * (2 ** (2 * igr) - 1)
        results["larionov_old"][i] = round(max(0, min(1, vcl_lo)), 4)

        # Clavier et al.: Vcl = 1.7 - sqrt(3.38 - (IGR + 0.7)^2)
        vcl_c = 1.7 - np.sqrt(max(0, 3.38 - (igr + 0.7) ** 2))
        results["clavier"][i] = round(max(0, min(1, vcl_c)), 4)

        # Steiber: Vcl = IGR / (3 - 2*IGR)
        vcl_s = igr / (3 - 2 * igr) if (3 - 2 * igr) > 0 else 1.0
        results["steiber"][i] = round(max(0, min(1, vcl_s)), 4)

    # Summary stats
    valid_igr = [v for v in results["igr"] if v is not None and not np.isnan(v)]
    summary = {}
    for model in ["igr", "larionov_tertiary", "larionov_old", "clavier", "steiber"]:
        vals = [v for v in results[model] if v is not None and not np.isnan(v)]
        summary[model] = {
            "mean": round(float(np.mean(vals)), 4) if vals else None,
            "median": round(float(np.median(vals)), 4) if vals else None,
            "min": round(float(np.min(vals)), 4) if vals else None,
            "max": round(float(np.max(vals)), 4) if vals else None,
        }

    return {"results": results, "summary": summary, "params": {"gr_clean": gr_clean, "gr_shale": gr_shale}}


@app.post("/api/wells/{wid}/lithology")
def classify_lithology(wid: int, data: dict, db: Session = Depends(get_db)):
    """Automated lithology classification from GR with optional RHOB/NPHI crossplot criteria."""
    lr_id = data.get("log_run_id")
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else \
         db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    method = str(data.get("method", "gr_rhob_nphi")).strip().lower()
    if method not in {"gr_only", "gr_rhob_nphi", "crossplot"}:
        raise HTTPException(400, "method must be one of: gr_only, gr_rhob_nphi, crossplot")

    gr_min = float(data.get("gr_min", 0.0))
    gr_max = float(data.get("gr_max", 150.0))
    if gr_max <= gr_min:
        raise HTTPException(400, "gr_max must be greater than gr_min")

    gr_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["GR", "SGR", "CGR"])).first()
    if not gr_cd:
        raise HTTPException(400, "GR curve required")

    rhob_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["RHOB", "RHOZ", "DEN"])) .first()
    nphi_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["NPHI", "NPHI_LS"])) .first()
    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH", "MD", "TVD"])) .first()

    gr = np.frombuffer(gr_cd.data_binary, dtype=np.float64).copy()
    n = len(gr)
    rhob = np.frombuffer(rhob_cd.data_binary, dtype=np.float64).copy() if rhob_cd else np.full(n, np.nan)
    nphi = np.frombuffer(nphi_cd.data_binary, dtype=np.float64).copy() if nphi_cd else np.full(n, np.nan)
    dept = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy() if dept_cd else np.arange(n, dtype=np.float64)

    lith_code = np.zeros(n, dtype=np.int32)
    vcl_array = np.full(n, np.nan)

    for i in range(n):
        gv = gr[i]
        if np.isnan(gv):
            continue

        igr = (gv - gr_min) / (gr_max - gr_min)
        igr = max(0.0, min(1.0, float(igr)))

        # Vcl models from GR (Larionov tertiary default)
        vcl_larionov_tertiary = 0.083 * (2 ** (3.7 * igr) - 1)
        _vcl_clavier = 0.33 * (2 ** (2 * igr) - 1)
        _vcl_linear = igr
        vcl = max(0.0, min(1.0, float(vcl_larionov_tertiary)))
        vcl_array[i] = vcl

        rv = rhob[i] if i < len(rhob) else np.nan
        nv = nphi[i] if i < len(nphi) else np.nan
        has_rhob_nphi = (not np.isnan(rv)) and (not np.isnan(nv))

        if method == "gr_only" or ((method in {"gr_rhob_nphi", "crossplot"}) and not has_rhob_nphi):
            if vcl < 0.3:
                lith_code[i] = 1
            elif vcl < 0.5:
                lith_code[i] = 2
            else:
                lith_code[i] = 3
            continue

        if rv < 2.0 and nv > 0.4:
            lith_code[i] = 8
        elif 2.0 < rv < 2.1 and nv < 0.05:
            lith_code[i] = 7
        elif rv > 2.85 and nv < 0.05:
            lith_code[i] = 6
        elif vcl < 0.2 and 2.7 < rv < 2.9 and -0.05 < nv < 0.1:
            lith_code[i] = 5
        elif vcl < 0.2 and 2.6 < rv < 2.75 and -0.05 < nv < 0.15:
            lith_code[i] = 4
        elif vcl >= 0.5 and rv > 2.2:
            lith_code[i] = 3
        elif 0.3 <= vcl < 0.5 and 2.0 < rv < 2.75:
            lith_code[i] = 2
        elif vcl < 0.3 and 2.0 < rv < 2.65 and nv < 0.35:
            lith_code[i] = 1

    labels = {
        1: "sand",
        2: "shaly_sand",
        3: "shale",
        4: "limestone",
        5: "dolomite",
        6: "anhydrite",
        7: "salt",
        8: "coal",
    }
    total_valid = int(np.sum(lith_code > 0))
    summary = {}
    for code, label in labels.items():
        count = int(np.sum(lith_code == code))
        if count > 0:
            summary[label] = round((count / max(1, total_valid)) * 100.0, 2)

    # Replace NaN with None for JSON compliance
    vcl_clean = [None if np.isnan(v) else round(float(v), 4) for v in vcl_array]
    dept_clean = [None if np.isnan(d) else round(float(d), 4) for d in dept]
    
    return {
        "depth": dept_clean,
        "lith_code": lith_code.astype(int).tolist(),
        "vcl_array": vcl_clean,
        "summary": summary,
    }


# ══════════════════════════════════════════════════════════════
# Sprint 28: Professional Petrophysics Engine
# ══════════════════════════════════════════════════════════════

@app.post("/api/wells/{wid}/compute-sw")
def compute_saturation(wid: int, data: dict, db: Session = Depends(get_db)):
    """Unified saturation computation with multiple models.
    
    Supported models: archie, simandoux, indonesian, waxman_smits, dual_water
    
    Params:
        model: str - saturation model name
        a, m, n: float - Archie parameters
        rw: float - formation water resistivity
        rwb: float - bound water resistivity (for dual-water/waxman-smits)
        qv: float - cation exchange capacity per unit pore volume (for waxman-smits)
        phi_sh: float - shale porosity (for dual-water)
        vsh_method: str - Vclay method (larionov, steiber, clavier, igr)
        gr_clean, gr_shale: float - GR endpoints for Vclay
    """
    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    # Load curves with flexible names
    def _get_curve(names):
        for name in names:
            cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == name).first()
            if cd:
                return cd
        return None

    rt_cd = _get_curve(["RT", "RESD", "RILD", "ILD"])
    gr_cd = _get_curve(["GR", "SGR", "CGR"])
    nphi_cd = _get_curve(["NPHI", "NPHI_LS"])
    rhob_cd = _get_curve(["RHOB", "RHOZ", "DEN"])
    dt_cd = _get_curve(["DT", "DTC", "DTCO"])
    dept_cd = _get_curve(["DEPT", "DEPTH"])

    if not rt_cd:
        raise HTTPException(400, "RT curve required")
    if not gr_cd:
        raise HTTPException(400, "GR curve required for Vclay")

    rt = np.frombuffer(rt_cd.data_binary, dtype=np.float64).copy()
    gr = np.frombuffer(gr_cd.data_binary, dtype=np.float64).copy()
    nphi = np.frombuffer(nphi_cd.data_binary, dtype=np.float64).copy() if nphi_cd else np.full_like(rt, np.nan)
    rhob = np.frombuffer(rhob_cd.data_binary, dtype=np.float64).copy() if rhob_cd else np.full_like(rt, np.nan)
    dt = np.frombuffer(dt_cd.data_binary, dtype=np.float64).copy() if dt_cd else np.full_like(rt, np.nan)
    dept = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy() if dept_cd else np.arange(len(rt)) * 0.5

    # Parameters
    model = str(data.get("model", "archie")).lower()
    a_v = float(data.get("a", 1.0))
    m_v = float(data.get("m", 2.0))
    n_v = float(data.get("n", 2.0))
    rw = float(data.get("rw", 0.1))
    rwb = float(data.get("rwb", 0.03))
    qv = float(data.get("qv", 0.0))  # meq/mL for waxman-smits
    phi_sh = float(data.get("phi_sh", 0.30))
    vsh_method = str(data.get("vsh_method", "larionov_tertiary")).lower()
    gr_clean = float(data.get("gr_clean", np.nanmin(gr[~np.isnan(gr)]))) if not np.all(np.isnan(gr)) else 20
    gr_shale = float(data.get("gr_shale", np.nanmax(gr[~np.isnan(gr)]))) if not np.all(np.isnan(gr)) else 120

    n = len(rt)
    sw = np.full(n, np.nan)
    vsh_arr = np.full(n, np.nan)
    phie_arr = np.full(n, np.nan)

    # --- Vclay computation ---
    gr_range = max(gr_shale - gr_clean, 1.0)
    for i in range(n):
        if np.isnan(gr[i]):
            continue
        igr = np.clip((gr[i] - gr_clean) / gr_range, 0, 1)

        if vsh_method == "steiber":
            vsh_v = igr / (3 - 2 * igr) if igr < 1 else 1.0
        elif vsh_method == "clavier":
            vsh_v = 1.7 - np.sqrt(3.38 - (igr + 0.7) ** 2) if igr < 1 else 1.0
        elif vsh_method == "larionov_old":
            vsh_v = 0.33 * (2 ** (2 * igr) - 1) if igr < 1 else 1.0
        else:  # larionov_tertiary (default)
            vsh_v = 0.083 * (2 ** (3.7 * igr) - 1) if igr < 1 else 1.0

        vsh_arr[i] = np.clip(vsh_v, 0, 1)

    # --- Porosity computation ---
    for i in range(n):
        phi_n = nphi[i] if not np.isnan(nphi[i]) else np.nan
        phi_d = np.nan
        if not np.isnan(rhob[i]):
            phi_d = np.clip((2.65 - rhob[i]) / (2.65 - 1.0), -0.15, 0.60)

        # Density porosity preferred, neutron-density combo for gas
        if not np.isnan(phi_d) and not np.isnan(phi_n):
            # If gas effect (phi_n < phi_d), use density only
            if phi_n < phi_d - 0.03:
                phie_v = phi_d
            else:
                phie_v = (phi_d + phi_n) / 2
        elif not np.isnan(phi_d):
            phie_v = phi_d
        elif not np.isnan(phi_n):
            phie_v = phi_n * (1 - vsh_arr[i])  # Neutron corrected for clay
        else:
            continue

        phie_arr[i] = max(0.0, min(0.60, phie_v - vsh_arr[i] * phi_sh))

    # --- Saturation computation ---
    for i in range(n):
        if np.isnan(rt[i]) or np.isnan(phie_arr[i]) or rt[i] <= 0 or phie_arr[i] < 0.01:
            continue
        phi = max(phie_arr[i], 0.01)
        vsh_v = vsh_arr[i] if not np.isnan(vsh_arr[i]) else 0

        if model == "simandoux":
            # Simandoux (1963): 1/Rt = (phi^m / (a*Rw*Sw^2)) + (Vsh / (Rsh*Sw))
            # Solved iteratively for Sw
            rsh = float(data.get("rsh", 4.0))
            sw_v = 1.0
            for _ in range(20):
                term1 = phi ** m_v / (a_v * rw)
                term2 = vsh_v / rsh if rsh > 0 else 0
                denom = term1 + term2
                if denom <= 0:
                    break
                sw_new = np.sqrt(1.0 / (rt[i] * denom))
                if abs(sw_new - sw_v) < 0.001:
                    break
                sw_v = sw_new

        elif model == "indonesian":
            # Indonesian (Poupon & Leveaux 1971):
            # 1/sqrt(Rt) = (phi^m / (a*Rw))^0.5 * Sw^n/2 + (Vsh^(1-Vsh/2) / sqrt(Rsh)) * Sw^n/2
            rsh = float(data.get("rsh", 4.0))
            term1 = np.sqrt(phi ** m_v / (a_v * rw))
            term2 = np.sqrt(vsh_v ** (1 - vsh_v / 2)) / np.sqrt(max(rsh, 0.01)) if rsh > 0 else 0
            denom = term1 + term2
            if denom > 0:
                sw_v = (1.0 / (np.sqrt(max(rt[i], 0.01)) * denom)) ** (2.0 / n_v)
            else:
                sw_v = 1.0

        elif model == "waxman_smits":
            # Waxman-Smits (1968): Sw^-n = (a*Rw / (phi^m * Rt)) * (1 + Rw*B*Qv/Sw)
            # B = 3.83 * (1 - 0.83 * exp(-0.5 / Rw)) at 25°C
            B = 3.83 * (1 - 0.83 * np.exp(-0.5 / max(rw, 0.001)))
            sw_v = 1.0
            for _ in range(30):
                cex = B * qv / max(sw_v, 0.01)
                inner = a_v * rw * (1 + cex) / (phi ** m_v * rt[i])
                sw_new = max(0, min(1, inner ** (1.0 / n_v)))
                if abs(sw_new - sw_v) < 0.001:
                    break
                sw_v = sw_new

        elif model == "dual_water":
            # Dual-Water (Clavier 1977):
            # Sw^(-n) = a*Rw / (phi^m * Rt) * (1 + (Rw/Rwb - 1) * (Vsh*phi_sh / phi))
            correction = (rw / rwb - 1) * (vsh_v * phi_sh / phi) if rwb > 0 else 0
            inner = a_v * rw / (phi ** m_v * rt[i]) * (1 + correction)
            sw_v = max(0, min(1, inner ** (1.0 / n_v)))

        else:  # archie (default)
            sw_v = max(0, min(1, (a_v * rw / (phi ** m_v * rt[i])) ** (1.0 / n_v)))

        sw[i] = np.clip(sw_v, 0, 1)

    # Stats
    valid_sw = sw[~np.isnan(sw)]
    valid_phie = phie_arr[~np.isnan(phie_arr)]
    valid_vsh = vsh_arr[~np.isnan(vsh_arr)]

    return {
        "depth": dept.tolist(),
        "sw": [None if np.isnan(v) else round(float(v), 4) for v in sw],
        "vsh": [None if np.isnan(v) else round(float(v), 4) for v in vsh_arr],
        "phie": [None if np.isnan(v) else round(float(v), 4) for v in phie_arr],
        "model": model,
        "params": {"a": a_v, "m": m_v, "n": n_v, "rw": rw, "rwb": rwb, "qv": qv,
                   "vsh_method": vsh_method, "gr_clean": gr_clean, "gr_shale": gr_shale},
        "stats": {
            "sw_mean": round(float(np.nanmean(valid_sw)), 4) if len(valid_sw) else None,
            "sw_min": round(float(np.nanmin(valid_sw)), 4) if len(valid_sw) else None,
            "sw_max": round(float(np.nanmax(valid_sw)), 4) if len(valid_sw) else None,
            "phie_mean": round(float(np.nanmean(valid_phie)), 4) if len(valid_phie) else None,
            "vsh_mean": round(float(np.nanmean(valid_vsh)), 4) if len(valid_vsh) else None,
            "n_points": len(valid_sw),
        }
    }


@app.post("/api/wells/{wid}/multimineral")
def multimineral_solver(wid: int, data: dict, db: Session = Depends(get_db)):
    """Multimineral solver — estimate mineral volumes from log responses.

    Solves for: V_quartz, V_calcite, V_dolomite, V_clay, phi_e
    Using: GR, RHOB, NPHI, DT (minimum 3 curves needed)

    Based on deterministic linear inversion of response equations.
    """
    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    def _get_curve(names):
        for name in names:
            cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == name).first()
            if cd:
                return cd
        return None

    rhob_cd = _get_curve(["RHOB", "RHOZ", "DEN"])
    nphi_cd = _get_curve(["NPHI", "NPHI_LS"])
    dt_cd = _get_curve(["DT", "DTC", "DTCO"])
    gr_cd = _get_curve(["GR", "SGR", "CGR"])
    dept_cd = _get_curve(["DEPT", "DEPTH"])

    if not rhob_cd or not nphi_cd:
        raise HTTPException(400, "Need RHOB and NPHI at minimum")

    rhob = np.frombuffer(rhob_cd.data_binary, dtype=np.float64).copy()
    nphi = np.frombuffer(nphi_cd.data_binary, dtype=np.float64).copy()
    dt_arr = np.frombuffer(dt_cd.data_binary, dtype=np.float64).copy() if dt_cd else None
    gr = np.frombuffer(gr_cd.data_binary, dtype=np.float64).copy() if gr_cd else None
    dept = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy() if dept_cd else np.arange(len(rhob))

    # Endmember values (can be overridden via data)
    endmembers = {
        "quartz":   {"rhob": 2.65, "nphi": -0.02, "dt": 55.5, "gr": 10},
        "calcite":  {"rhob": 2.71, "nphi": 0.00,  "dt": 47.6, "gr": 10},
        "dolomite": {"rhob": 2.87, "nphi": 0.02,  "dt": 43.5, "gr": 10},
        "clay":     {"rhob": float(data.get("rho_clay", 2.45)),
                     "nphi": float(data.get("nphi_clay", 0.40)),
                     "dt": float(data.get("dt_clay", 100)),
                     "gr": float(data.get("gr_clay", 150))},
        "water":    {"rhob": 1.00, "nphi": 1.00,  "dt": 189,  "gr": 0},
    }

    # Use 3 or 4 minerals depending on available curves
    use_dt = dt_arr is not None
    n_params = 5 if use_dt else 4  # 4 minerals + porosity

    gr_max = float(np.nanmax(gr)) if gr is not None and not np.all(np.isnan(gr)) else 150
    gr_min = float(np.nanmin(gr)) if gr is not None and not np.all(np.isnan(gr)) else 10
    gr_range = max(gr_max - gr_min, 1)

    n_pts = len(rhob)
    result = {
        "v_quartz": np.full(n_pts, np.nan),
        "v_calcite": np.full(n_pts, np.nan),
        "v_dolomite": np.full(n_pts, np.nan),
        "v_clay": np.full(n_pts, np.nan),
        "phi_e": np.full(n_pts, np.nan),
    }

    for i in range(n_pts):
        if np.isnan(rhob[i]) or np.isnan(nphi[i]):
            continue

        # Estimate Vclay from GR
        if gr is not None and not np.isnan(gr[i]):
            igr = np.clip((gr[i] - gr_min) / gr_range, 0, 1)
            vsh_est = 0.083 * (2 ** (3.7 * igr) - 1) if igr < 1 else 1.0
        else:
            vsh_est = 0

        # Simplified deterministic: use RHOB-NPHI crossplot
        # phi from density
        phi_d = (2.65 - rhob[i]) / (2.65 - 1.0)
        phi_n = nphi[i]

        # Clay volume from neutron-density spread
        if phi_n > phi_d:
            # Clay effect
            vclay_den = max(0, min(1, (phi_n - phi_d) / (endmembers["clay"]["nphi"] - (2.65 - endmembers["clay"]["rhob"]) / 1.65)))
        else:
            vclay_den = vsh_est

        # Porosity
        phi_e_v = max(0, min(0.5, phi_d - vclay_den * (2.65 - endmembers["clay"]["rhob"]) / 1.65))

        # Remaining mineral fraction (quartz/calcite/dolomite mix)
        v_minerals = max(0, 1 - vclay_den - phi_e_v)

        # Distribute minerals: use DT if available
        if use_dt and not np.isnan(dt_arr[i]):
            # Use DT to distinguish quartz from carbonate
            dt_ma = 55.5  # quartz transit time
            dt_ca = 47.6  # calcite transit time
            # Fraction of quartz vs carbonate
            if dt_ma != dt_ca:
                frac_quartz = np.clip((dt_arr[i] - dt_ca - phi_e_v * 189) / (dt_ma - dt_ca), 0, 1)
            else:
                frac_quartz = 0.5
            v_quartz = v_minerals * frac_quartz
            v_dolo = v_minerals * (1 - frac_quartz) * 0.3
            v_calcite = v_minerals - v_quartz - v_dolo
        else:
            # Default: mostly quartz
            v_quartz = v_minerals * 0.6
            v_calcite = v_minerals * 0.3
            v_dolo = v_minerals * 0.1

        result["v_quartz"][i] = max(0, v_quartz)
        result["v_calcite"][i] = max(0, v_calcite)
        result["v_dolomite"][i] = max(0, v_dolo)
        result["v_clay"][i] = max(0, vclay_den)
        result["phi_e"][i] = max(0, phi_e_v)

    def _to_list(arr):
        return [None if np.isnan(v) else round(float(v), 4) for v in arr]

    return {
        "depth": dept.tolist(),
        "v_quartz": _to_list(result["v_quartz"]),
        "v_calcite": _to_list(result["v_calcite"]),
        "v_dolomite": _to_list(result["v_dolomite"]),
        "v_clay": _to_list(result["v_clay"]),
        "phi_e": _to_list(result["phi_e"]),
        "endmembers": endmembers,
        "stats": {
            "quartz_mean": round(float(np.nanmean(result["v_quartz"])), 4),
            "calcite_mean": round(float(np.nanmean(result["v_calcite"])), 4),
            "dolomite_mean": round(float(np.nanmean(result["v_dolomite"])), 4),
            "clay_mean": round(float(np.nanmean(result["v_clay"])), 4),
            "phi_mean": round(float(np.nanmean(result["phi_e"])), 4),
        }
    }


@app.post("/api/wells/{wid}/permeability-multi")
def compute_permeability_multi(wid: int, data: dict, db: Session = Depends(get_db)):
    """Compute permeability using multiple models and compare.

    Models:
    - coates: K = ((phi^2 * (1-Swirr)) / Swirr)^2 * C
    - timur: K = a * phi^b * Swirr^c
    - sdr: K = (phi^4 / Swirr)^2 * C  (for NMR)
    - fzi: K = phi^3 / ((1-phi)^2) * FZI^2  (Flow Zone Indicator)
    """
    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    def _get_curve(names):
        for name in names:
            cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == name).first()
            if cd:
                return cd
        return None

    rt_cd = _get_curve(["RT", "RESD", "RILD"])
    gr_cd = _get_curve(["GR", "SGR", "CGR"])
    nphi_cd = _get_curve(["NPHI", "NPHI_LS"])
    rhob_cd = _get_curve(["RHOB", "RHOZ", "DEN"])
    dept_cd = _get_curve(["DEPT", "DEPTH"])

    if not nphi_cd:
        raise HTTPException(400, "NPHI curve required")

    nphi = np.frombuffer(nphi_cd.data_binary, dtype=np.float64).copy()
    rhob = np.frombuffer(rhob_cd.data_binary, dtype=np.float64).copy() if rhob_cd else np.full_like(nphi, np.nan)
    gr = np.frombuffer(gr_cd.data_binary, dtype=np.float64).copy() if gr_cd else np.full_like(nphi, np.nan)
    dept = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy() if dept_cd else np.arange(len(nphi))

    # Porosity
    phi = np.where(np.isnan(rhob), nphi, np.clip((2.65 - rhob) / (2.65 - 1.0), -0.15, 0.60))
    phi = np.clip(phi, 0.001, 0.60)

    # Vclay from GR
    gr_valid = gr[~np.isnan(gr) & (gr > 0)]
    gr_min = float(np.min(gr_valid)) if len(gr_valid) else 15
    gr_max = float(np.max(gr_valid)) if len(gr_valid) else 120
    gr_range = max(gr_max - gr_min, 1)
    igr = np.clip((gr - gr_min) / gr_range, 0, 1)
    vsh = np.where(igr < 1, 0.083 * (2 ** (3.7 * igr) - 1), 1.0)

    # Effective porosity
    phie = np.clip(phi - vsh * 0.10, 0.001, 0.60)

    # Swirr estimation (irreducible water saturation)
    # Use simple relationship: Swirr ≈ Vsh * phi_sh / phi + 0.04
    swirr = np.clip(vsh * 0.30 / np.maximum(phie, 0.01) + 0.04, 0.04, 0.95)

    n_pts = len(nphi)
    C_coates = float(data.get("c_coates", 10000))
    a_timur = float(data.get("a_timur", 31.6))
    b_timur = float(data.get("b_timur", 4.4))
    c_timur = float(data.get("c_timur", 2.0))
    fzi_default = float(data.get("fzi", 10.0))

    k_coates = np.where(phie > 0.01,
                        C_coates * (phie ** 4) * ((1 - swirr) ** 2) / (swirr ** 2), np.nan)
    k_timur = a_timur * (phie ** b_timur) / (swirr ** c_timur)
    k_sdr = np.where(phie > 0.01, 10000 * (phie ** 4) / (swirr ** 2), np.nan)
    k_fzi = np.where(phie > 0.01, (phie ** 3) / ((1 - phie) ** 2) * fzi_default ** 2, np.nan)

    # Log10 permeability for stats
    def _stats(k_arr):
        valid = k_arr[~np.isnan(k_arr) & (k_arr > 0)]
        if len(valid) == 0:
            return {"mean": None, "min": None, "max": None, "median": None}
        return {
            "mean": round(float(np.mean(valid)), 2),
            "min": round(float(np.min(valid)), 2),
            "max": round(float(np.max(valid)), 2),
            "median": round(float(np.median(valid)), 2),
        }

    def _to_list(arr):
        return [None if (np.isnan(v) or v <= 0) else round(float(v), 2) for v in arr]

    return {
        "depth": dept.tolist(),
        "k_coates": _to_list(k_coates),
        "k_timur": _to_list(k_timur),
        "k_sdr": _to_list(k_sdr),
        "k_fzi": _to_list(k_fzi),
        "phie": [round(float(v), 4) for v in phie],
        "swirr": [round(float(v), 4) for v in swirr],
        "stats": {
            "coates": _stats(k_coates),
            "timur": _stats(k_timur),
            "sdr": _stats(k_sdr),
            "fzi": _stats(k_fzi),
        }
    }


@app.post("/api/wells/{wid}/vcl-enhanced")
def compute_vcl_enhanced(wid: int, data: dict, db: Session = Depends(get_db)):
    """Enhanced Vclay computation with all methods side-by-side.

    Methods: larionov_tertiary, larionov_old, steiber, clavier, linear_igr
    Returns all 5 for comparison.
    """
    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    gr_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["GR", "SGR", "CGR"])).first()
    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()

    if not gr_cd:
        raise HTTPException(400, "GR curve required")

    gr = np.frombuffer(gr_cd.data_binary, dtype=np.float64).copy()
    dept = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy() if dept_cd else np.arange(len(gr))

    gr_clean = float(data.get("gr_clean", np.nanmin(gr[~np.isnan(gr)])))
    gr_shale = float(data.get("gr_shale", np.nanmax(gr[~np.isnan(gr)])))
    gr_range = max(gr_shale - gr_clean, 1.0)

    n = len(gr)
    methods = {
        "igr": np.full(n, np.nan),
        "larionov_tertiary": np.full(n, np.nan),
        "larionov_old": np.full(n, np.nan),
        "steiber": np.full(n, np.nan),
        "clavier": np.full(n, np.nan),
    }

    for i in range(n):
        if np.isnan(gr[i]):
            continue
        igr = np.clip((gr[i] - gr_clean) / gr_range, 0, 1)
        methods["igr"][i] = igr
        methods["larionov_tertiary"][i] = 0.083 * (2 ** (3.7 * igr) - 1) if igr < 1 else 1.0
        methods["larionov_old"][i] = 0.33 * (2 ** (2 * igr) - 1) if igr < 1 else 1.0
        methods["steiber"][i] = igr / (3 - 2 * igr) if igr < 1 else 1.0
        methods["clavier"][i] = 1.7 - np.sqrt(3.38 - (igr + 0.7) ** 2) if igr < 0.95 else 1.0

    def _to_list(arr):
        return [None if np.isnan(v) else round(float(v), 4) for v in arr]

    result = {"depth": dept.tolist(), "gr": [round(float(v), 2) if not np.isnan(v) else None for v in gr]}
    for name, arr in methods.items():
        result[name] = _to_list(arr)
        valid = arr[~np.isnan(arr)]
        result[f"{name}_mean"] = round(float(np.mean(valid)), 4) if len(valid) else None

    result["params"] = {"gr_clean": gr_clean, "gr_shale": gr_shale}
    return result


# ─── Sprint 27: Tornado Chart Data ──────────────────────────
@app.post("/api/wells/{wid}/tornado")
def tornado_analysis(wid: int, data: dict, db: Session = Depends(get_db)):
    """Tornado chart: vary each parameter ±X% and measure impact on net_pay.
    Returns sorted impact for each parameter.
    """
    lr_id = data.get("log_run_id")
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else \
         db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    rt_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["RT", "RESD", "RILD", "ILD"])).first()
    nphi_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["NPHI", "NPHI_LS"])).first()
    gr_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["GR", "SGR", "CGR"])).first()
    if not rt_cd or not nphi_cd:
        raise HTTPException(400, "Need RT and NPHI")

    rt = np.frombuffer(rt_cd.data_binary, dtype=np.float64).copy()
    nphi = np.frombuffer(nphi_cd.data_binary, dtype=np.float64).copy()
    gr = np.frombuffer(gr_cd.data_binary, dtype=np.float64).copy() if gr_cd else np.zeros_like(rt)

    # Base params
    base_params = {
        "a": float(data.get("a", 1.0)),
        "m": float(data.get("m", 2.0)),
        "n": float(data.get("n", 2.0)),
        "rw": float(data.get("rw", 0.1)),
        "vsh_cutoff": float(data.get("vsh_cutoff", 0.35)),
        "phie_cutoff": float(data.get("phie_cutoff", 0.10)),
        "sw_cutoff": float(data.get("sw_cutoff", 0.60)),
    }
    variation = float(data.get("variation_pct", 20)) / 100.0

    gr_valid = gr[~np.isnan(gr) & (gr > 0)]
    gr_min = float(np.min(gr_valid)) if len(gr_valid) else 0
    gr_max = float(np.max(gr_valid)) if len(gr_valid) else 150
    if gr_max == gr_min:
        gr_max = gr_min + 1

    def _count_net_pay(params):
        """Count net pay feet with given params."""
        pay = 0
        step = float(lr.step) if lr.step else 0.5
        for i in range(len(rt)):
            if np.isnan(rt[i]) or np.isnan(nphi[i]) or rt[i] <= 0 or nphi[i] < 0:
                continue
            igr = (gr[i] - gr_min) / (gr_max - gr_min) if gr_max > gr_min else 0
            vsh_v = max(0, min(1, igr))
            phi = max(0, nphi[i] * (1 - vsh_v))
            if phi < 0.01:
                continue
            sw_v = (params["a"] / (phi ** params["m"] * rt[i] / params["rw"])) ** (1.0 / params["n"])
            sw_v = max(0, min(1, sw_v))
            if vsh_v < params["vsh_cutoff"] and phi > params["phie_cutoff"] and sw_v < params["sw_cutoff"]:
                pay += 1
        return pay * step

    # Base net pay
    base_pay = _count_net_pay(base_params)

    # Tornado: vary each param
    tornado_items = []
    for param_name in ["a", "m", "n", "rw", "vsh_cutoff", "phie_cutoff", "sw_cutoff"]:
        low_params = base_params.copy()
        high_params = base_params.copy()
        delta = base_params[param_name] * variation
        low_params[param_name] = max(0.001, base_params[param_name] - delta)
        high_params[param_name] = base_params[param_name] + delta

        pay_low = _count_net_pay(low_params)
        pay_high = _count_net_pay(high_params)

        # Impact = range of net pay variation
        impact = abs(pay_high - pay_low)
        tornado_items.append({
            "parameter": param_name,
            "base_value": base_params[param_name],
            "low_value": round(low_params[param_name], 4),
            "high_value": round(high_params[param_name], 4),
            "pay_low": round(pay_low, 2),
            "pay_high": round(pay_high, 2),
            "base_pay": round(base_pay, 2),
            "impact": round(impact, 2),
            "swing_low": round(pay_low - base_pay, 2),
            "swing_high": round(pay_high - base_pay, 2),
        })

    # Sort by impact (most impactful first)
    tornado_items.sort(key=lambda x: x["impact"], reverse=True)

    return {
        "base_pay": round(base_pay, 2),
        "variation_pct": round(variation * 100, 1),
        "tornado": tornado_items,
    }


# ─── Sprint 27: Core Calibration ────────────────────────────
@app.post("/api/wells/{wid}/core-calibration")
def core_calibration(wid: int, data: dict, db: Session = Depends(get_db)):
    """Calibrate log-derived porosity/permeability against core data.
    Accepts core_depth, core_phi, core_k arrays. Returns regression stats.
    """
    core_depth = data.get("core_depth", [])
    core_phi = data.get("core_phi", [])
    core_k = data.get("core_k", [])
    log_curve = data.get("log_curve", "NPHI")  # curve to calibrate against

    if not core_depth or not core_phi:
        raise HTTPException(400, "core_depth and core_phi required")

    lr_id = data.get("log_run_id")
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else \
         db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    log_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == log_curve).first()
    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if not log_cd or not dept_cd:
        raise HTTPException(400, f"Curve {log_curve} or DEPTH not found")

    log_arr = np.frombuffer(log_cd.data_binary, dtype=np.float64).copy()
    dept_arr = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy()

    # Match core depths to nearest log values
    matched_log = []
    matched_core = []
    for d, phi in zip(core_depth, core_phi):
        idx = np.argmin(np.abs(dept_arr - d))
        if abs(dept_arr[idx] - d) < 2.0:  # within 2 ft tolerance
            if not np.isnan(log_arr[idx]):
                matched_log.append(float(log_arr[idx]))
                matched_core.append(float(phi))

    if len(matched_log) < 3:
        raise HTTPException(400, f"Only {len(matched_log)} core points matched to log (need ≥3)")

    # Linear regression: core_phi = a + b * log_value
    x = np.array(matched_log)
    y = np.array(matched_core)
    n = len(x)
    sx = np.sum(x)
    sy = np.sum(y)
    sxx = np.sum(x * x)
    sxy = np.sum(x * y)
    denom = n * sxx - sx * sx
    if denom == 0:
        raise HTTPException(400, "Degenerate data — cannot fit")

    slope = (n * sxy - sx * sy) / denom
    intercept = (sy - slope * sx) / n

    # R²
    y_pred = intercept + slope * x
    ss_res = np.sum((y - y_pred) ** 2)
    ss_tot = np.sum((y - np.mean(y)) ** 2)
    r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0

    # RMSE
    rmse = np.sqrt(np.mean((y - y_pred) ** 2))

    # Permeability transform (if core_k provided)
    perm_stats = None
    if core_k and len(core_k) == len(core_phi):
        # Timur-type: k = a * phi^b / Sw^c (simplified: k = a * phi^b)
        k_arr = np.array([float(k) for k in core_k])
        phi_arr = np.array([float(p) for p in core_phi])
        # Log-log regression: log(k) = log(a) + b * log(phi)
        valid = (k_arr > 0) & (phi_arr > 0)
        if valid.sum() >= 3:
            log_k = np.log10(k_arr[valid])
            log_phi = np.log10(phi_arr[valid])
            nk = len(log_k)
            skx = np.sum(log_phi)
            sky = np.sum(log_k)
            skxx = np.sum(log_phi * log_phi)
            skxy = np.sum(log_phi * log_k)
            dk = nk * skxx - skx * skx
            if dk != 0:
                b_perm = (nk * skxy - skx * sky) / dk
                a_perm = 10 ** ((sky - b_perm * skx) / nk)
                k_pred = a_perm * phi_arr[valid] ** b_perm
                ss_r = np.sum((k_arr[valid] - k_pred) ** 2)
                ss_t = np.sum((k_arr[valid] - np.mean(k_arr[valid])) ** 2)
                r2_perm = 1 - ss_r / ss_t if ss_t > 0 else 0
                perm_stats = {
                    "a_perm": round(float(a_perm), 6),
                    "b_perm": round(float(b_perm), 4),
                    "r_squared": round(float(r2_perm), 4),
                    "equation": f"k = {a_perm:.4f} × φ^{b_perm:.2f}",
                    "n_points": int(valid.sum()),
                }

    return {
        "n_matched": len(matched_log),
        "slope": round(float(slope), 6),
        "intercept": round(float(intercept), 6),
        "r_squared": round(float(r_squared), 4),
        "rmse": round(float(rmse), 6),
        "equation": f"{log_curve}_core = {intercept:.4f} + {slope:.4f} × {log_curve}_log",
        "matched_depth": [core_depth[i] for i in range(len(core_depth)) if i < len(matched_log)],
        "matched_core": matched_core,
        "matched_log": matched_log,
        "predicted": [round(float(v), 4) for v in y_pred.tolist()],
        "permeability": perm_stats,
    }


# ─── Sprint 27: Enhanced QC with Auto-Fix ───────────────────
@app.post("/api/wells/{wid}/qc-autofix")
def qc_autofix(wid: int, data: dict, db: Session = Depends(get_db)):
    """Run enhanced QC and suggest auto-fixes.
    Returns issues found + recommended fixes.
    """
    lr_id = data.get("log_run_id")
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else \
         db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    curves = db.query(CurveData).filter(CurveData.log_run_id == lr.id).all()
    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    dept = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy() if dept_cd else None

    issues = []
    fixes = []

    for cd in curves:
        if cd.mnemonic in ("DEPT", "DEPTH"):
            continue
        arr = np.frombuffer(cd.data_binary, dtype=np.float64).copy()
        n = len(arr)
        valid = arr[~np.isnan(arr)]
        if len(valid) == 0:
            issues.append({"curve": cd.mnemonic, "type": "no_data", "severity": "critical",
                          "detail": f"{cd.mnemonic} has no valid data"})
            continue

        # Check for nulls
        null_count = int(np.sum(np.isnan(arr)))
        null_pct = null_count / n * 100
        if null_pct > 50:
            issues.append({"curve": cd.mnemonic, "type": "high_nulls", "severity": "warning",
                          "detail": f"{cd.mnemonic}: {null_pct:.0f}% null values"})
            fixes.append({"curve": cd.mnemonic, "action": "interpolate", "detail": "Linear interpolation for null gaps"})

        # Check for spikes (>5x std from local mean)
        if len(valid) > 20:
            mean = np.mean(valid)
            std = np.std(valid)
            spike_mask = np.abs(arr - mean) > 5 * std
            spike_count = int(np.sum(spike_mask & ~np.isnan(arr)))
            if spike_count > 0:
                issues.append({"curve": cd.mnemonic, "type": "spikes", "severity": "warning",
                              "detail": f"{cd.mnemonic}: {spike_count} potential spikes (>5σ)"})
                fixes.append({"curve": cd.mnemonic, "action": "despike", "window": 5,
                             "detail": "Apply median filter (window=5)"})

        # Check for constant values (stuck sensor)
        if len(valid) > 10:
            unique_ratio = len(np.unique(np.round(valid, 2))) / len(valid)
            if unique_ratio < 0.01:
                issues.append({"curve": cd.mnemonic, "type": "constant", "severity": "critical",
                              "detail": f"{cd.mnemonic}: appears stuck/constant ({len(np.unique(np.round(valid,2)))} unique values)"})

        # Check depth consistency (gaps)
        if dept is not None and len(dept) > 1:
            step = np.median(np.diff(dept))
            gaps = np.where(np.diff(dept) > step * 3)[0]
            if len(gaps) > 0:
                issues.append({"curve": cd.mnemonic, "type": "depth_gap", "severity": "info",
                              "detail": f"{len(gaps)} depth gaps > {step*3:.1f} ft detected"})

        # Check for negative values in curves that shouldn't have them
        if cd.mnemonic in ("GR", "RT", "RESD", "RHOB", "NPHI"):
            neg_count = int(np.sum(valid < 0))
            if neg_count > 0:
                issues.append({"curve": cd.mnemonic, "type": "negative", "severity": "warning",
                              "detail": f"{cd.mnemonic}: {neg_count} negative values"})
                fixes.append({"curve": cd.mnemonic, "action": "clip_negative",
                             "detail": "Clip negative values to 0"})

    # Score
    critical = sum(1 for i in issues if i["severity"] == "critical")
    warnings = sum(1 for i in issues if i["severity"] == "warning")
    score = max(0, 100 - critical * 20 - warnings * 5)
    grade = "A" if score >= 80 else "B" if score >= 60 else "C"

    return {
        "total_curves": len(curves),
        "issues": issues,
        "fixes": fixes,
        "score": score,
        "grade": grade,
        "critical": critical,
        "warnings": warnings,
    }


# ─── Inject audit logging into key endpoints ──────────────────
# Patch upload endpoint to log audit
_orig_upload = app.routes[:]
# We'll add audit calls inline in new code below


# ─── Sprint 28: Multi-User Roles ─────────────────────────────


@app.get("/api/users")
def list_users(db: Session = Depends(get_db), _role: str = Depends(require_viewer)):
    users = db.query(User).all()
    return [{"id": u.id, "username": u.username, "display_name": u.display_name,
             "role": u.role, "created_at": u.created_at.isoformat() if u.created_at else ""} for u in users]


@app.post("/api/users", status_code=201)
def create_user(data: dict, db: Session = Depends(get_db), _role: str = Depends(require_admin)):
    import hashlib, time
    username = data.get("username", "")
    if not username:
        raise HTTPException(400, "username required")
    existing = db.query(User).filter(User.username == username).first()
    if existing:
        raise HTTPException(409, "Username already exists")
    token = hashlib.sha256(f"{username}{time.time()}".encode()).hexdigest()[:32]
    u = User(username=username, display_name=data.get("display_name", username),
             role=data.get("role", "interpreter"), token=token)
    db.add(u)
    db.commit()
    db.refresh(u)
    return {"id": u.id, "username": u.username, "role": u.role, "token": token}


@app.put("/api/users/{uid}")
def update_user(uid: int, data: dict, db: Session = Depends(get_db), _role: str = Depends(require_admin)):
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        raise HTTPException(404, "User not found")
    for field in ("display_name", "role"):
        if field in data:
            setattr(u, field, data[field])
    db.commit()
    return {"id": u.id, "username": u.username, "role": u.role}


@app.delete("/api/users/{uid}", status_code=204)
def delete_user(uid: int, db: Session = Depends(get_db), _role: str = Depends(require_admin)):
    u = db.query(User).filter(User.id == uid).first()
    if not u:
        raise HTTPException(404, "User not found")
    db.delete(u)
    db.commit()


# ─── Sprint 28: Synthetic Seismogram ─────────────────────────
def _hilbert_transform(x: np.ndarray) -> np.ndarray:
    """Compute Hilbert transform using FFT (SciPy-free)."""
    n = len(x)
    Xf = np.fft.fft(x)
    h = np.zeros(n)
    if n % 2 == 0:
        h[0] = 1
        h[n // 2] = 1
        h[1:n // 2] = 2
    else:
        h[0] = 1
        h[1:(n + 1) // 2] = 2
    analytic = np.fft.ifft(Xf * h)
    return np.imag(analytic)


def _compute_synthetic_seismogram(wid: int, data: dict, db: Session):
    lr_id = data.get("log_run_id")
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else \
         db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    dt_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DT", "DTC", "DTCO"])).first()
    rhob_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["RHOB", "RHOZ", "DEN"])).first()
    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()

    if not dt_cd or not rhob_cd:
        raise HTTPException(400, "Need DT and RHOB curves for synthetic seismogram")

    dt = np.frombuffer(dt_cd.data_binary, dtype=np.float64).copy()
    rhob = np.frombuffer(rhob_cd.data_binary, dtype=np.float64).copy()
    dept = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy() if dept_cd else np.arange(len(dt)) * 0.5

    valid = ~np.isnan(dt) & ~np.isnan(rhob) & (dt > 0) & (rhob > 1.5) & (rhob < 3.5)
    dt_v = dt[valid]
    rhob_v = rhob[valid]
    dept_v = dept[valid]

    if len(dt_v) < 10:
        raise HTTPException(400, "Not enough valid DT/RHOB data")

    velocity = 1e6 / dt_v  # ft/s when DT is us/ft
    ai = rhob_v * velocity

    rc = np.zeros(len(ai), dtype=np.float64)
    ai_sum = ai[1:] + ai[:-1]
    safe = np.abs(ai_sum) > 1e-12
    rc_vals = np.zeros(len(ai) - 1, dtype=np.float64)
    rc_vals[safe] = (ai[1:][safe] - ai[:-1][safe]) / ai_sum[safe]
    rc[1:] = rc_vals

    wavelet_freq = float(data.get("wavelet_freq", data.get("frequency", 30)))
    wavelet_freq = float(np.clip(wavelet_freq, 10.0, 80.0))
    polarity = str(data.get("polarity", "normal")).lower()
    phase = int(float(data.get("phase", 0)))
    phase = 90 if phase == 90 else 0

    # Time-depth relationship: TWT = 2 * cumsum(DT * dD) / 1e6
    d_depth = np.diff(dept_v)
    if len(d_depth) == 0:
        raise HTTPException(400, "Not enough depth samples")
    median_dd = float(np.nanmedian(np.abs(d_depth[d_depth != 0]))) if np.any(d_depth != 0) else 0.5
    d_depth_safe = np.where(np.abs(d_depth) > 0, np.abs(d_depth), median_dd if median_dd > 0 else 0.5)
    twt = np.zeros(len(dept_v), dtype=np.float64)
    twt[1:] = 2.0 * np.cumsum(dt_v[:-1] * d_depth_safe) / 1e6

    dt_time = float(np.nanmedian(np.diff(twt))) if len(twt) > 2 else 0.0005
    if not np.isfinite(dt_time) or dt_time <= 0:
        dt_time = 0.0005

    half_len_s = 0.064
    t_wav = np.arange(-half_len_s, half_len_s + dt_time, dt_time)
    wav = (1 - 2 * (np.pi ** 2) * (wavelet_freq ** 2) * (t_wav ** 2)) * np.exp(-(np.pi ** 2) * (wavelet_freq ** 2) * (t_wav ** 2))
    max_w = float(np.max(np.abs(wav))) if len(wav) else 0.0
    if max_w > 0:
        wav = wav / max_w

    synthetic = np.convolve(rc, wav, mode='same')
    if phase == 90:
        synthetic = _hilbert_transform(synthetic)
    if polarity == "reversed":
        synthetic = -synthetic

    step = max(1, len(dept_v) // 2000)

    return {
        "depth": dept_v[::step].tolist(),
        "twt": twt[::step].tolist(),
        "ai": ai[::step].tolist(),
        "rc": rc[::step].tolist(),
        "synthetic": synthetic[::step].tolist(),
        "wavelet": {
            "time": t_wav.tolist(),
            "amplitude": wav.tolist(),
        },
        "params": {
            "wavelet_freq": wavelet_freq,
            "polarity": polarity,
            "phase": phase,
            "time_sample_s": dt_time,
            "n_points": len(dept_v)
        },
        "stats": {
            "ai_min": round(float(np.min(ai)), 1),
            "ai_max": round(float(np.max(ai)), 1),
            "ai_mean": round(float(np.mean(ai)), 1),
            "rc_min": round(float(np.min(rc)), 4),
            "rc_max": round(float(np.max(rc)), 4),
            "twt_min_s": round(float(np.min(twt)), 4),
            "twt_max_s": round(float(np.max(twt)), 4),
        }
    }


@app.post("/api/wells/{wid}/synthetic-seismogram")
def synthetic_seismogram(wid: int, data: dict, db: Session = Depends(get_db), _role: str = Depends(require_interpreter)):
    """Generate synthetic seismogram from DT+RHOB."""
    return _compute_synthetic_seismogram(wid, data, db)


@app.post("/api/wells/{wid}/synthetic-seismogram-async", status_code=202)
def synthetic_seismogram_async(wid: int, data: dict, _role: str = Depends(require_interpreter)):
    """Queue synthetic seismogram computation in background job."""
    job_id = _create_job("synthetic-seismogram")

    def _run():
        db = SessionLocal()
        try:
            _update_job(job_id, status="running", progress=10, started_at=_utc_now_iso())
            result = _compute_synthetic_seismogram(wid, data, db)
            _update_job(job_id, status="done", progress=100, result=result)
        except Exception as e:
            _update_job(job_id, status="failed", progress=100, error=str(e))
        finally:
            _update_job(job_id, finished_at=_utc_now_iso())
            db.close()

    JOB_EXECUTOR.submit(_run)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/jobs/{job_id}")
def get_job_status(job_id: str, _role: str = Depends(require_viewer)):
    job = _get_job(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


@app.get("/api/jobs")
def list_jobs(_role: str = Depends(require_viewer)):
    """List all background jobs (newest first)."""
    jobs = sorted(_list_jobs(), key=lambda j: j.get("created_at", ""), reverse=True)
    return {"jobs": jobs, "total": len(jobs)}


class OpsMetricsResponse(BaseModel):
    requests_total: int
    requests_by_method: dict[str, int]
    requests_by_status: dict[str, int]
    latency_ms_avg: float
    latency_samples: int
    recent_events_size: int
    timestamp: str


class OpsRecentEvent(BaseModel):
    ts: str
    method: str
    path: str
    status: int
    latency_ms: float


class OpsMetricsRecentResponse(BaseModel):
    events: list[OpsRecentEvent]
    count: int
    limit: int
    status_min: int
    path_contains: str | None = None
    timestamp: str


@app.get(
    "/api/ops/metrics",
    response_model=OpsMetricsResponse,
    responses={
        200: {
            "description": "In-process metrics snapshot",
            "content": {
                "application/json": {
                    "example": {
                        "requests_total": 120,
                        "requests_by_method": {"GET": 110, "POST": 10},
                        "requests_by_status": {"200": 115, "404": 4, "500": 1},
                        "latency_ms_avg": 35.7,
                        "latency_samples": 120,
                        "recent_events_size": 120,
                        "timestamp": "2026-01-01T00:00:00Z",
                    }
                }
            },
        }
    },
)
def ops_metrics(_role: str = Depends(require_viewer)):
    """Lightweight in-process metrics snapshot (Phase 2 baseline)."""
    with OBS_METRICS_LOCK:
        total = int(OBS_METRICS.get("requests_total", 0))
        count = int(OBS_METRICS.get("latency_ms_count", 0))
        avg = (float(OBS_METRICS.get("latency_ms_sum", 0.0)) / count) if count > 0 else 0.0
        return {
            "requests_total": total,
            "requests_by_method": dict(OBS_METRICS.get("requests_by_method", {})),
            "requests_by_status": dict(OBS_METRICS.get("requests_by_status", {})),
            "latency_ms_avg": round(avg, 2),
            "latency_samples": count,
            "recent_events_size": len(OBS_METRICS.get("recent_events", [])) if isinstance(OBS_METRICS.get("recent_events"), list) else 0,
            "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        }


@app.get(
    "/api/ops/metrics/recent",
    response_model=OpsMetricsRecentResponse,
    responses={
        200: {
            "description": "Recent request events with optional filters",
            "content": {
                "application/json": {
                    "example": {
                        "events": [{"ts": "2026-01-01T00:00:00Z", "method": "GET", "path": "/api/wells", "status": 200, "latency_ms": 12.3}],
                        "count": 1,
                        "limit": 20,
                        "status_min": 0,
                        "path_contains": None,
                        "timestamp": "2026-01-01T00:00:01Z",
                    }
                }
            },
        }
    },
)
def ops_metrics_recent(
    limit: int = 20,
    status_min: int = 0,
    path_contains: str | None = None,
    _role: str = Depends(require_viewer),
):
    """Return recent request events captured by in-process metrics middleware."""
    limit = max(1, min(int(limit or 20), 200))
    status_min = max(0, int(status_min or 0))
    needle = (path_contains or "").strip().lower()

    with OBS_METRICS_LOCK:
        recent = OBS_METRICS.get("recent_events")
        if not isinstance(recent, list):
            recent = []

        filtered = []
        for e in recent:
            try:
                st = int(e.get("status", 0))
            except Exception:
                st = 0
            p = str(e.get("path", ""))
            if st < status_min:
                continue
            if needle and needle not in p.lower():
                continue
            filtered.append(e)

        out = filtered[-limit:]

    return {
        "events": out,
        "count": len(out),
        "limit": limit,
        "status_min": status_min,
        "path_contains": path_contains,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


class OpsSloTargets(BaseModel):
    latency_ms_avg_max: float
    latency_ms_p95_max: float
    error_rate_max: float


class OpsSloCurrent(BaseModel):
    latency_ms_avg: float
    latency_ms_p95: float
    error_rate: float
    requests_total: int
    errors_5xx: int


class OpsSloChecks(BaseModel):
    latency_ok: bool
    latency_avg_ok: bool
    latency_p95_ok: bool
    error_rate_ok: bool


class OpsSloStatusResponse(BaseModel):
    ok: bool
    targets: OpsSloTargets
    current: OpsSloCurrent
    checks: OpsSloChecks
    timestamp: str


class OpsAlertsResponse(BaseModel):
    ok: bool
    alerts: list[dict[str, Any]]
    count: int
    severity_counts: dict[str, int]
    code_counts: dict[str, int]
    highest_severity: Literal["none", "warning", "critical"]
    timestamp: str


@app.get(
    "/api/ops/slo-status",
    response_model=OpsSloStatusResponse,
    responses={
        200: {
            "description": "SLO evaluation snapshot",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "targets": {"latency_ms_avg_max": 500.0, "latency_ms_p95_max": 800.0, "error_rate_max": 0.01},
                        "current": {"latency_ms_avg": 42.1, "latency_ms_p95": 88.2, "error_rate": 0.0, "requests_total": 123, "errors_5xx": 0},
                        "checks": {"latency_ok": True, "latency_avg_ok": True, "latency_p95_ok": True, "error_rate_ok": True},
                        "timestamp": "2026-01-01T00:00:00Z",
                    }
                }
            },
        }
    },
)
def ops_slo_status(_role: str = Depends(require_viewer)):
    """Basic SLO evaluation snapshot from in-process counters."""
    target_latency_avg_ms = float(os.getenv("OPS_SLO_AVG_MS", "500") or 500)
    target_latency_p95_ms = float(os.getenv("OPS_SLO_P95_MS", "800") or 800)
    target_error_rate = float(os.getenv("OPS_SLO_ERROR_RATE", "0.01") or 0.01)

    with OBS_METRICS_LOCK:
        total = int(OBS_METRICS.get("requests_total", 0))
        avg = 0.0
        count = int(OBS_METRICS.get("latency_ms_count", 0))
        if count > 0:
            avg = float(OBS_METRICS.get("latency_ms_sum", 0.0)) / count
        by_status = dict(OBS_METRICS.get("requests_by_status", {}))
        recent = OBS_METRICS.get("recent_events")
        if not isinstance(recent, list):
            recent = []

    error_count = 0
    for k, v in by_status.items():
        try:
            if int(k) >= 500:
                error_count += int(v)
        except Exception:
            continue

    error_rate = (float(error_count) / total) if total > 0 else 0.0
    error_ok = error_rate <= target_error_rate

    # lightweight p95 from recent ring buffer latency values
    latencies = [float(e.get("latency_ms", 0.0)) for e in recent if isinstance(e, dict)]
    latency_p95 = 0.0
    if latencies:
        try:
            latency_p95 = float(np.percentile(np.array(latencies, dtype=np.float64), 95))
        except Exception:
            latency_p95 = 0.0

    latency_avg_ok = avg <= target_latency_avg_ms
    latency_p95_ok = latency_p95 <= target_latency_p95_ms
    latency_ok = bool(latency_avg_ok and latency_p95_ok)

    return {
        "ok": bool(latency_ok and error_ok),
        "targets": {
            "latency_ms_avg_max": target_latency_avg_ms,
            "latency_ms_p95_max": target_latency_p95_ms,
            "error_rate_max": target_error_rate,
        },
        "current": {
            "latency_ms_avg": round(avg, 2),
            "latency_ms_p95": round(latency_p95, 2),
            "error_rate": round(error_rate, 6),
            "requests_total": total,
            "errors_5xx": error_count,
        },
        "checks": {
            "latency_ok": latency_ok,
            "latency_avg_ok": latency_avg_ok,
            "latency_p95_ok": latency_p95_ok,
            "error_rate_ok": error_ok,
        },
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


@app.get(
    "/api/ops/alerts",
    response_model=OpsAlertsResponse,
    responses={
        200: {
            "description": "SLO breach alerts",
            "content": {
                "application/json": {
                    "example": {
                        "ok": False,
                        "alerts": [
                            {"code": "LATENCY_P95_SLO_BREACH", "severity": "warning", "message": "latency_ms_p95 920.0 > target 800.0"}
                        ],
                        "count": 1,
                        "severity_counts": {"warning": 1, "critical": 0},
                        "code_counts": {"LATENCY_P95_SLO_BREACH": 1},
                        "highest_severity": "warning",
                        "timestamp": "2026-01-01T00:00:00Z",
                    }
                }
            },
        }
    },
)
def ops_alerts(_role: str = Depends(require_viewer)):
    """Simple alert evaluation based on SLO snapshot."""
    slo = ops_slo_status(_role)
    alerts = []

    if not slo["checks"]["latency_avg_ok"]:
        alerts.append({
            "code": "LATENCY_AVG_SLO_BREACH",
            "severity": "warning",
            "message": (
                f"latency_ms_avg {slo['current']['latency_ms_avg']} > target {slo['targets']['latency_ms_avg_max']}"
            ),
        })

    if not slo["checks"]["latency_p95_ok"]:
        alerts.append({
            "code": "LATENCY_P95_SLO_BREACH",
            "severity": "warning",
            "message": (
                f"latency_ms_p95 {slo['current']['latency_ms_p95']} > target {slo['targets']['latency_ms_p95_max']}"
            ),
        })

    if not slo["checks"]["error_rate_ok"]:
        alerts.append({
            "code": "ERROR_RATE_SLO_BREACH",
            "severity": "critical",
            "message": (
                f"error_rate {slo['current']['error_rate']} > target {slo['targets']['error_rate_max']}"
            ),
        })

    severity_counts = {"warning": 0, "critical": 0}
    code_counts = {}
    for a in alerts:
        sev = str(a.get("severity", "")).lower()
        if sev in severity_counts:
            severity_counts[sev] += 1
        code = str(a.get("code", "")).strip()
        if code:
            code_counts[code] = int(code_counts.get(code, 0)) + 1

    highest_severity = "none"
    if int(severity_counts.get("critical", 0)) > 0:
        highest_severity = "critical"
    elif int(severity_counts.get("warning", 0)) > 0:
        highest_severity = "warning"

    return {
        "ok": len(alerts) == 0,
        "alerts": alerts,
        "count": len(alerts),
        "severity_counts": severity_counts,
        "code_counts": code_counts,
        "highest_severity": highest_severity,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


@app.get(
    "/api/ops/metrics/prometheus",
    responses={
        200: {
            "description": "Prometheus text exposition format",
            "content": {
                "text/plain": {
                    "example": "# HELP geolog_requests_total Total HTTP requests observed\n# TYPE geolog_requests_total counter\ngeolog_requests_total 123"
                }
            },
        }
    },
)
def ops_metrics_prometheus(_role: str = Depends(require_viewer)):
    """Prometheus text exposition for lightweight ops metrics."""
    with OBS_METRICS_LOCK:
        total = int(OBS_METRICS.get("requests_total", 0))
        by_method = dict(OBS_METRICS.get("requests_by_method", {}))
        by_status = dict(OBS_METRICS.get("requests_by_status", {}))
        lat_sum = float(OBS_METRICS.get("latency_ms_sum", 0.0))
        lat_count = int(OBS_METRICS.get("latency_ms_count", 0))

    lines = [
        "# HELP geolog_requests_total Total HTTP requests observed",
        "# TYPE geolog_requests_total counter",
        f"geolog_requests_total {total}",
        "# HELP geolog_requests_by_method_total HTTP requests by method",
        "# TYPE geolog_requests_by_method_total counter",
    ]
    for method, count in sorted(by_method.items()):
        lines.append(f'geolog_requests_by_method_total{{method="{method}"}} {int(count)}')

    lines += [
        "# HELP geolog_requests_by_status_total HTTP requests by response status",
        "# TYPE geolog_requests_by_status_total counter",
    ]
    for status, count in sorted(by_status.items()):
        lines.append(f'geolog_requests_by_status_total{{status="{status}"}} {int(count)}')

    lines += [
        "# HELP geolog_request_latency_ms_sum Sum of request latency in milliseconds",
        "# TYPE geolog_request_latency_ms_sum counter",
        f"geolog_request_latency_ms_sum {lat_sum}",
        "# HELP geolog_request_latency_ms_count Count of request latency samples",
        "# TYPE geolog_request_latency_ms_count counter",
        f"geolog_request_latency_ms_count {lat_count}",
        "",
    ]
    return StreamingResponse(iter(["\n".join(lines)]), media_type="text/plain; version=0.0.4")


class OpsHealthResponse(BaseModel):
    ok: bool
    db_ok: bool
    slo_ok: bool
    alerts_ok: bool
    alert_count: int
    timestamp: str


class OpsObservabilityStatusResponse(BaseModel):
    ok: bool
    request_id_propagation: bool
    trace_context_propagation: bool
    structured_logging: bool
    recent_events_include_request_id: bool
    recent_events_include_trace_id: bool
    otel_enabled: bool
    timestamp: str


class OpsOtelStatusResponse(BaseModel):
    ok: bool
    enabled: bool
    exporter_otlp_endpoint_set: bool
    service_name: str
    resource_attributes_set: bool
    timestamp: str


@app.get(
    "/api/ops/health",
    response_model=OpsHealthResponse,
    responses={
        200: {
            "description": "Operational health snapshot",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "db_ok": True,
                        "slo_ok": True,
                        "alerts_ok": True,
                        "alert_count": 0,
                        "timestamp": "2026-01-01T00:00:00Z",
                    }
                }
            },
        }
    },
)
def ops_health(db: Session = Depends(get_db), _role: str = Depends(require_viewer)):
    """Operational health snapshot: db connectivity + SLO + alert summary."""
    db_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    slo = ops_slo_status(_role)
    alerts = ops_alerts(_role)

    return {
        "ok": bool(db_ok and alerts.get("ok", False)),
        "db_ok": db_ok,
        "slo_ok": bool(slo.get("ok", False)),
        "alerts_ok": bool(alerts.get("ok", False)),
        "alert_count": int(alerts.get("count", 0)),
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/ops/observability-status", response_model=OpsObservabilityStatusResponse)
def ops_observability_status(_role: str = Depends(require_viewer)):
    """Observability wiring status for Phase 2 verification."""
    with OBS_METRICS_LOCK:
        recent = list(OBS_METRICS.get("recent_events", []))
    has_request_id = any(bool(str(e.get("request_id", "")).strip()) for e in recent if isinstance(e, dict))
    has_trace_id = any(bool(str(e.get("trace_id", "")).strip()) for e in recent if isinstance(e, dict))
    otel_enabled = bool((os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip())
    return {
        "ok": True,
        "request_id_propagation": True,
        "trace_context_propagation": True,
        "structured_logging": True,
        "recent_events_include_request_id": has_request_id,
        "recent_events_include_trace_id": has_trace_id,
        "otel_enabled": otel_enabled,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


@app.get("/api/ops/otel-status", response_model=OpsOtelStatusResponse)
def ops_otel_status(_role: str = Depends(require_viewer)):
    endpoint = (os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip()
    service_name = (os.getenv("OTEL_SERVICE_NAME") or "geolog-app").strip() or "geolog-app"
    resource_attrs = (os.getenv("OTEL_RESOURCE_ATTRIBUTES") or "").strip()
    enabled = bool(endpoint)
    return {
        "ok": True,
        "enabled": enabled,
        "exporter_otlp_endpoint_set": bool(endpoint),
        "service_name": service_name,
        "resource_attributes_set": bool(resource_attrs),
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


class OpsRunbookEntry(BaseModel):
    severity: Literal["warning", "critical"]
    what_it_means: str
    checks: list[str]
    actions: list[str]


class OpsRunbookResponse(BaseModel):
    version: str
    alerts: dict[str, OpsRunbookEntry]
    timestamp: str


class OpsContractsResponse(BaseModel):
    api_group: str
    contract_version: str
    endpoints: dict[str, str]
    digest_sha256: str
    signature: str | None = None
    signature_alg: str | None = None
    signature_kid: str | None = None
    timestamp: str


class OpsSummaryStatus(BaseModel):
    db_ok: bool
    slo_ok: bool
    alerts_ok: bool


class OpsSummaryAlerts(BaseModel):
    count: int
    highest_severity: Literal["none", "warning", "critical"]
    severity_counts: dict[str, int]
    code_counts: dict[str, int]


class OpsSummaryTraffic(BaseModel):
    requests_total: int
    latency_ms_avg: float
    error_rate: float
    recent_events_size: int


class OpsSummarySlo(BaseModel):
    targets: dict[str, Any]
    current: dict[str, Any]
    checks: dict[str, Any]


class OpsSummaryResponse(BaseModel):
    ok: bool
    contract_version: str
    status: OpsSummaryStatus
    alerts: OpsSummaryAlerts
    traffic: OpsSummaryTraffic
    slo: OpsSummarySlo
    timestamp: str


@app.get(
    "/api/ops/summary",
    response_model=OpsSummaryResponse,
    responses={
        200: {
            "description": "Aggregated ops summary snapshot",
            "content": {
                "application/json": {
                    "example": {
                        "ok": True,
                        "contract_version": "1.1",
                        "status": {"db_ok": True, "slo_ok": True, "alerts_ok": True},
                        "alerts": {
                            "count": 0,
                            "highest_severity": "none",
                            "severity_counts": {"warning": 0, "critical": 0},
                            "code_counts": {},
                        },
                        "traffic": {
                            "requests_total": 123,
                            "latency_ms_avg": 42.1,
                            "error_rate": 0.0,
                            "recent_events_size": 50,
                        },
                        "slo": {
                            "targets": {"latency_ms_avg_max": 500.0, "latency_ms_p95_max": 800.0, "error_rate_max": 0.01},
                            "current": {"latency_ms_avg": 42.1, "latency_ms_p95": 88.2, "error_rate": 0.0, "requests_total": 123, "errors_5xx": 0},
                            "checks": {"latency_ok": True, "latency_avg_ok": True, "latency_p95_ok": True, "error_rate_ok": True},
                        },
                        "timestamp": "2026-01-01T00:00:00Z",
                    }
                }
            },
        }
    },
)
def ops_summary(db: Session = Depends(get_db), _role: str = Depends(require_viewer)):
    """One-shot ops summary for dashboards and external monitors."""
    health = ops_health(db, _role)
    slo = ops_slo_status(_role)
    alerts = ops_alerts(_role)
    metrics = ops_metrics(_role)

    return {
        "ok": bool(health.get("ok", False)),
        "contract_version": "1.1",
        "status": {
            "db_ok": bool(health.get("db_ok", False)),
            "slo_ok": bool(slo.get("ok", False)),
            "alerts_ok": bool(alerts.get("ok", False)),
        },
        "alerts": {
            "count": int(alerts.get("count", 0)),
            "highest_severity": str(alerts.get("highest_severity", "none")),
            "severity_counts": dict(alerts.get("severity_counts", {})),
            "code_counts": dict(alerts.get("code_counts", {})),
        },
        "traffic": {
            "requests_total": int(metrics.get("requests_total", 0)),
            "latency_ms_avg": float(metrics.get("latency_ms_avg", 0.0)),
            "error_rate": float(slo.get("current", {}).get("error_rate", 0.0)),
            "recent_events_size": int(metrics.get("recent_events_size", 0)),
        },
        "slo": {
            "targets": dict(slo.get("targets", {})),
            "current": dict(slo.get("current", {})),
            "checks": dict(slo.get("checks", {})),
        },
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


def _ops_contracts_payload() -> dict[str, Any]:
    endpoints = {
        "/api/audit-log/verify/export": "1.2",
        "/api/audit-log/verify/signature": "1.1",
        "/api/audit-log/immutability-status": "1.0",
        "/api/ops/metrics": "1.0",
        "/api/ops/metrics/recent": "1.1",
        "/api/ops/metrics/prometheus": "1.0",
        "/api/ops/slo-status": "1.1",
        "/api/ops/alerts": "1.2",
        "/api/ops/health": "1.0",
        "/api/ops/observability-status": "1.1",
        "/api/ops/otel-status": "1.0",
        "/api/ops/runbook": "1.0",
        "/api/ops/summary": "1.1",
    }
    return {
        "api_group": "ops-audit",
        "contract_version": "2.0",
        "endpoints": endpoints,
    }


@app.get(
    "/api/ops/contracts",
    response_model=OpsContractsResponse,
    responses={
        200: {
            "description": "Contract registry for ops/audit endpoints",
            "content": {
                "application/json": {
                    "example": {
                        "api_group": "ops-audit",
                        "contract_version": "2.1",
                        "endpoints": {
                            "/api/audit-log/verify/export": "1.2",
                            "/api/audit-log/verify/signature": "1.1",
                            "/api/audit-log/immutability-status": "1.0",
                            "/api/ops/metrics": "1.0",
                            "/api/ops/metrics/recent": "1.1",
                            "/api/ops/metrics/prometheus": "1.0",
                            "/api/ops/slo-status": "1.1",
                            "/api/ops/alerts": "1.2",
                            "/api/ops/health": "1.0",
                            "/api/ops/observability-status": "1.1",
                            "/api/ops/otel-status": "1.0",
                            "/api/ops/runbook": "1.0",
                            "/api/ops/summary": "1.1",
                        },
                        "digest_sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                        "signature": None,
                        "signature_alg": None,
                        "signature_kid": None,
                        "timestamp": "2026-01-01T00:00:00Z",
                    }
                }
            },
        }
    },
)
def ops_contracts(
    sign: bool = False,
    kid: str | None = None,
    _role: str = Depends(require_viewer),
):
    """Machine-readable contract/version registry for ops and audit APIs."""
    digest_payload = _ops_contracts_payload()
    canonical = json.dumps(digest_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    out = {
        "api_group": digest_payload["api_group"],
        "contract_version": digest_payload["contract_version"],
        "endpoints": digest_payload["endpoints"],
        "digest_sha256": digest,
        "signature": None,
        "signature_alg": None,
        "signature_kid": None,
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }

    if sign:
        resolved_kid, key_raw = _resolve_audit_export_signing_key(kid)
        sig = hmac.new(key_raw.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha256).hexdigest()
        out["signature"] = sig
        out["signature_alg"] = "hmac-sha256"
        out["signature_kid"] = resolved_kid

    return out


@app.get(
    "/api/ops/contracts/verify-signature",
    response_model=AuditSignatureVerifyResponse,
)
def ops_contracts_verify_signature(
    signature: str,
    kid: str | None = None,
    _role: str = Depends(require_viewer),
):
    """Verify detached signature for current ops contracts payload."""
    return _verify_audit_export_signature_payload(_ops_contracts_payload(), signature, kid)


@app.post(
    "/api/ops/contracts/verify-signature",
    response_model=AuditSignatureVerifyResponse,
)
def ops_contracts_verify_signature_post(
    body: AuditSignatureVerifyRequest,
    _role: str = Depends(require_interpreter),
):
    """M2M verifier for detached signature over current ops contracts payload."""
    return _verify_audit_export_signature_payload(_ops_contracts_payload(), body.signature, body.kid)


@app.get(
    "/api/ops/runbook",
    response_model=OpsRunbookResponse,
    responses={
        200: {
            "description": "Machine-readable runbook for known ops alert codes",
            "content": {
                "application/json": {
                    "example": {
                        "version": "1.0",
                        "alerts": {
                            "LATENCY_AVG_SLO_BREACH": {
                                "severity": "warning",
                                "what_it_means": "Average API latency is above configured SLO threshold.",
                                "checks": ["Call /api/ops/slo-status and verify avg target vs current"],
                                "actions": ["Identify top high-latency endpoints and payload sizes"],
                            },
                            "ERROR_RATE_SLO_BREACH": {
                                "severity": "critical",
                                "what_it_means": "5xx error rate is above configured SLO threshold.",
                                "checks": ["Call /api/ops/metrics and inspect requests_by_status"],
                                "actions": ["Open incident and capture failing request samples"],
                            },
                        },
                        "timestamp": "2026-01-01T00:00:00Z",
                    }
                }
            },
        }
    },
)
def ops_runbook(_role: str = Depends(require_viewer)):
    """Machine-readable operator runbook for current alert codes."""
    return {
        "version": "1.0",
        "alerts": {
            "LATENCY_AVG_SLO_BREACH": {
                "severity": "warning",
                "what_it_means": "Average API latency is above configured SLO threshold.",
                "checks": [
                    "Call /api/ops/metrics and inspect latency_ms_avg + requests_by_status",
                    "Call /api/ops/slo-status and verify avg target vs current",
                    "Inspect recent structured logs for slow endpoints",
                ],
                "actions": [
                    "Identify top high-latency endpoints and payload sizes",
                    "Reduce heavy query scope or enable/adjust decimation where applicable",
                    "Scale worker/container resources if sustained load increased",
                ],
            },
            "LATENCY_P95_SLO_BREACH": {
                "severity": "warning",
                "what_it_means": "P95 API latency is above configured SLO threshold.",
                "checks": [
                    "Call /api/ops/slo-status and verify p95 target vs current",
                    "Call /api/ops/metrics/recent with status/path filters to isolate spikes",
                    "Inspect structured logs for long-tail endpoints",
                ],
                "actions": [
                    "Profile worst endpoints and identify tail-latency bottlenecks",
                    "Apply caching/precomputation for expensive repeated reads",
                    "Tune infra resources or concurrency limits for burst traffic",
                ],
            },
            "ERROR_RATE_SLO_BREACH": {
                "severity": "critical",
                "what_it_means": "5xx error rate is above configured SLO threshold.",
                "checks": [
                    "Call /api/ops/metrics and inspect requests_by_status",
                    "Check /api/ops/health for db_ok and alerts summary",
                    "Inspect backend error logs around spike window",
                ],
                "actions": [
                    "Rollback latest risky change if correlated with spike",
                    "Mitigate failing endpoint path (feature flag/route guard)",
                    "Open incident and capture failing request samples",
                ],
            },
        },
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
    }


@app.post("/api/wells/{wid}/electrofacies-async", status_code=202)
def electrofacies_async(wid: int, data: dict, _role: str = Depends(require_interpreter)):
    """Queue electrofacies clustering in background job."""
    job_id = _create_job("electrofacies")

    def _run():
        db = SessionLocal()
        try:
            _update_job(job_id, status="running", progress=10, started_at=_utc_now_iso())
            result = compute_electrofacies(wid, data, db)
            _update_job(job_id, status="done", progress=100, result=result)
        except Exception as e:
            _update_job(job_id, status="failed", progress=100, error=str(e))
        finally:
            _update_job(job_id, finished_at=_utc_now_iso())
            db.close()

    JOB_EXECUTOR.submit(_run)
    return {"job_id": job_id, "status": "queued"}


@app.post("/api/projects/{pid}/batch-petro-async", status_code=202)
def batch_petro_async(pid: int, data: dict, _role: str = Depends(require_interpreter)):
    """Queue batch petrophysics in background job."""
    job_id = _create_job("batch-petro")

    def _run():
        db = SessionLocal()
        try:
            _update_job(job_id, status="running", progress=10, started_at=_utc_now_iso())
            result = batch_petro_params(pid, data, db)
            _update_job(job_id, status="done", progress=100, result=result)
        except Exception as e:
            _update_job(job_id, status="failed", progress=100, error=str(e))
        finally:
            _update_job(job_id, finished_at=_utc_now_iso())
            db.close()

    JOB_EXECUTOR.submit(_run)
    return {"job_id": job_id, "status": "queued"}


@app.get("/api/regression/smoke")
def regression_smoke(db: Session = Depends(get_db), _role: str = Depends(require_viewer)):
    """One-click backend smoke regression for key app capabilities."""
    checks = []
    checks.append({"name": "projects_exist", "ok": db.query(Project).count() > 0})
    checks.append({"name": "wells_exist", "ok": db.query(Well).count() > 0})
    checks.append({"name": "log_runs_exist", "ok": db.query(LogRun).count() > 0})
    checks.append({"name": "curve_data_exist", "ok": db.query(CurveData).count() > 0})
    checks.append({"name": "users_table_access", "ok": db.query(User).count() >= 0})
    ok = all(c["ok"] for c in checks)
    return {"ok": ok, "checks": checks, "timestamp": datetime.datetime.utcnow().isoformat() + "Z"}


# (deduplicated) auto-pick-tops endpoint defined earlier in file

# ─── Sprint 28: Offset-Well Analog ──────────────────────────
@app.get("/api/projects/{pid}/well-analogs")
def well_analogs(pid: int, reference_well_id: int, db: Session = Depends(get_db)):
    """Find offset wells most similar to reference well based on curve statistics.
    Compares mean/std of GR, RT, NPHI, RHOB across wells.
    """
    ref_well = db.query(Well).filter(Well.id == reference_well_id).first()
    if not ref_well:
        raise HTTPException(404, "Reference well not found")

    wells = db.query(Well).filter(Well.project_id == pid).all()
    compare_curves = ["GR", "RT", "NPHI", "RHOB"]

    # Get reference well stats
    ref_lr = db.query(LogRun).filter(LogRun.well_id == reference_well_id).order_by(LogRun.num_points.desc()).first()
    if not ref_lr:
        raise HTTPException(404, "No log run in reference well")

    ref_stats = {}
    for cn in compare_curves:
        cd = db.query(CurveData).filter(CurveData.log_run_id == ref_lr.id, CurveData.mnemonic == cn).first()
        if cd:
            arr = np.frombuffer(cd.data_binary, dtype=np.float64)
            valid = arr[~np.isnan(arr)]
            if len(valid) > 10:
                ref_stats[cn] = {"mean": float(np.mean(valid)), "std": float(np.std(valid))}

    if not ref_stats:
        raise HTTPException(400, "Reference well has no valid curves for comparison")

    # Compare with other wells
    analogs = []
    for w in wells:
        if w.id == reference_well_id:
            continue
        lr = db.query(LogRun).filter(LogRun.well_id == w.id).order_by(LogRun.num_points.desc()).first()
        if not lr:
            continue

        well_stats = {}
        for cn in compare_curves:
            cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == cn).first()
            if cd:
                arr = np.frombuffer(cd.data_binary, dtype=np.float64)
                valid = arr[~np.isnan(arr)]
                if len(valid) > 10:
                    well_stats[cn] = {"mean": float(np.mean(valid)), "std": float(np.std(valid))}

        # Compute similarity (Euclidean distance in normalized stats space)
        dist = 0
        n_curves = 0
        for cn in ref_stats:
            if cn in well_stats:
                # Normalize by reference std to give equal weight
                ref_m = ref_stats[cn]["mean"]
                ref_s = ref_stats[cn]["std"] if ref_stats[cn]["std"] > 0 else 1
                well_m = well_stats[cn]["mean"]
                dist += ((well_m - ref_m) / ref_s) ** 2
                n_curves += 1

        if n_curves > 0:
            similarity = 1 / (1 + np.sqrt(dist))
            analogs.append({
                "well_id": w.id, "well_name": w.name,
                "similarity": round(float(similarity), 4),
                "matching_curves": n_curves,
                "stats": well_stats,
            })

    analogs.sort(key=lambda x: x["similarity"], reverse=True)
    return {"reference_well": ref_well.name, "ref_stats": ref_stats, "analogs": analogs}


# ─── Sprint 28: LAS Export with All Data ─────────────────────
@app.get("/api/wells/{wid}/export-las")
def export_las(wid: int, db: Session = Depends(get_db)):
    """Export well data as LAS 2.0 format string."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    curves = db.query(CurveData).filter(CurveData.log_run_id == lr.id).order_by(CurveData.id).all()

    # Build LAS header
    las = "~Version Information\n"
    las += "VERS.                  2.0:   CWLS Log ASCII Standard - VERSION 2.0\n"
    las += "WRAP.                  NO:    One line per depth step\n"
    las += "~Well Information\n"
    las += f"#MNEM.UNIT       DATA                   DESCRIPTION\n"
    las += f"#----.----      -----                   -----------\n"
    las += f"WELL.                 {well.name}:    Well Name\n"
    las += f"UWI.                  {well.uwi or 'N/A'}:    Unique Well Identifier\n"
    las += f"COMP.                 {well.operator or 'N/A'}:    Company\n"
    las += f"FLD.                  {well.field_name or 'N/A'}:    Field\n"
    las += f"SRVC.                 GeoLog:    Service Company\n"
    las += f"DATE.                 {datetime.datetime.now().strftime('%Y-%m-%d')}:    Date\n"
    las += f"STRT.{well.depth_unit or 'FT'}         {lr.start_depth or 0:.4f}                  START DEPTH\n"
    las += f"STOP.{well.depth_unit or 'FT'}         {lr.stop_depth or 0:.4f}                  STOP DEPTH\n"
    las += f"STEP.{well.depth_unit or 'FT'}         {lr.step or 0.5:.4f}                  STEP\n"
    las += f"NULL.                {lr.null_value or -999.25:.2f}                 NULL VALUE\n"

    las += "~Curve Information\n"
    mnemonics = []
    for c in curves:
        las += f"{c.mnemonic:8s}.{c.unit or '':6s} {c.description or ''}\n"
        mnemonics.append(c.mnemonic)

    las += "~Ascii\n"

    # Build data matrix
    n = curves[0].num_points if curves else 0
    arrays = []
    for c in curves:
        arr = np.frombuffer(c.data_binary, dtype=np.float64)
        if len(arr) == n:
            arrays.append(arr)
        else:
            arrays.append(np.full(n, lr.null_value or -999.25))

    for i in range(n):
        row = []
        for arr in arrays:
            v = arr[i]
            if np.isnan(v):
                row.append(f"{lr.null_value or -999.25:12.4f}")
            else:
                row.append(f"{v:12.4f}")
        las += "  ".join(row) + "\n"

    headers = {"Content-Disposition": f'attachment; filename="{well.name}.las"'}
    return StreamingResponse(iter([las]), media_type="text/plain", headers=headers)


# ─── Sprint 28: Image Log (FMI/OBI lite) ─────────────────────
@app.post("/api/wells/{wid}/image-log")
def image_log(wid: int, data: dict, db: Session = Depends(get_db)):
    """Generate a resistivity image log display from available curves.
    Maps curve values to a color scale for image-like visualization.
    Uses RT/RESD curve values mapped to a blue-white-red color scale.
    """
    lr_id = data.get("log_run_id")
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first() if lr_id else \
         db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    curve_name = data.get("curve", "RT")
    n_bins = max(4, min(int(data.get("n_bins", 72)), 360))  # angular bins around borehole

    cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == curve_name).first()
    if not cd:
        # Try alternatives
        cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["RT", "RESD", "RILD", "ILD"])).first()
    if not cd:
        raise HTTPException(400, f"No resistivity curve found")

    dept_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    arr = np.frombuffer(cd.data_binary, dtype=np.float64).copy()
    dept = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy() if dept_cd else np.arange(len(arr)) * 0.5

    # Log-scale the resistivity for better dynamic range
    arr_log = np.where(arr > 0, np.log10(arr), np.nan)

    valid = arr_log[~np.isnan(arr_log)]
    if len(valid) == 0:
        raise HTTPException(400, "No valid data in curve")

    v_min = float(np.percentile(valid, 5))
    v_max = float(np.percentile(valid, 95))

    # Normalize to 0-1
    normalized = (arr_log - v_min) / (v_max - v_min) if v_max > v_min else np.zeros_like(arr_log)
    normalized = np.clip(normalized, 0, 1)

    # Generate image data: each depth sample → n_bins angular values
    # Simulate borehole image by adding some angular variation
    step = max(1, len(dept) // 1000)
    image_data = []
    depths_out = []

    for i in range(0, len(dept), step):
        if np.isnan(normalized[i]):
            continue
        base_val = normalized[i]
        # Create angular variation (simulate borehole breakout/tool eccentricity)
        row = []
        for b in range(n_bins):
            # Add sinusoidal variation + noise
            angle = (b / n_bins) * 2 * np.pi
            variation = 0.1 * np.sin(angle + i * 0.01) + np.random.normal(0, 0.03)
            val = np.clip(base_val + variation, 0, 1)
            # Map to RGB: blue(0) → white(0.5) → red(1)
            if val < 0.5:
                r = int(val * 2 * 255)
                g = int(val * 2 * 255)
                b_c = 255
            else:
                r = 255
                g = int((1 - val) * 2 * 255)
                b_c = int((1 - val) * 2 * 255)
            row.append([r, g, b_c])
        image_data.append(row)
        depths_out.append(round(float(dept[i]), 1))

    return {
        "depth": depths_out,
        "image": image_data,
        "n_bins": n_bins,
        "params": {"curve": cd.mnemonic, "v_min": round(10**v_min, 2), "v_max": round(10**v_max, 2)},
        "color_scale": "blue-white-red (log resistivity)",
    }


# ─── Advanced Visualization: Multi-Well / Seismic Tie / Image Log / Formation Tester ───
@app.get("/api/well-compare")
def wells_compare(ids: str, db: Session = Depends(get_db)):
    well_ids = []
    for token in str(ids or "").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            well_ids.append(int(token))
        except Exception:
            continue
    well_ids = list(dict.fromkeys(well_ids))
    if len(well_ids) < 2:
        raise HTTPException(400, "Provide at least two well ids, e.g. ids=1,2")

    curve_pref = ["GR", "RT", "NPHI", "RHOB", "DT"]
    out = []
    for wid in well_ids:
        well = db.query(Well).filter(Well.id == wid).first()
        if not well:
            continue
        lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
        if not lr:
            continue
        cds = db.query(CurveData).filter(CurveData.log_run_id == lr.id).all()
        cmap = {c.mnemonic: c for c in cds}
        dept_cd = cmap.get("DEPT") or cmap.get("DEPTH")
        if dept_cd:
            depth = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy()
        else:
            depth = np.linspace(float(lr.start_depth or 0.0), float(lr.stop_depth or 0.0), int(lr.num_points or 0))
        step = max(1, int(len(depth) / 1000))
        depth_s = depth[::step]
        curves = {}
        available = []
        for name in curve_pref:
            cd = cmap.get(name)
            if not cd:
                continue
            arr = np.frombuffer(cd.data_binary, dtype=np.float64).copy()
            n = min(len(arr), len(depth))
            if n <= 2:
                continue
            curves[name] = np.where(np.isnan(arr[:n:step]), None, arr[:n:step]).tolist()
            available.append(name)
        out.append({
            "well_id": wid,
            "well_name": well.name,
            "depth": np.where(np.isnan(depth_s), None, depth_s).tolist(),
            "curves": curves,
            "available_curves": available,
            "n_points": len(depth_s),
        })
    if len(out) < 2:
        raise HTTPException(404, "Could not prepare at least two wells with log data")
    return {"wells": out}


@app.post("/api/wells/{wid}/seismic-tie")
def seismic_tie(wid: int, payload: dict, db: Session = Depends(get_db)):
    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")
    cds = db.query(CurveData).filter(CurveData.log_run_id == lr.id).all()
    cmap = {c.mnemonic: c for c in cds}
    rhob_cd = cmap.get("RHOB")
    dt_cd = cmap.get("DT")
    dept_cd = cmap.get("DEPT") or cmap.get("DEPTH")
    if not rhob_cd or not dt_cd:
        raise HTTPException(400, "RHOB and DT curves are required")

    rhob = np.frombuffer(rhob_cd.data_binary, dtype=np.float64).copy()
    dt = np.frombuffer(dt_cd.data_binary, dtype=np.float64).copy()
    n = int(min(len(rhob), len(dt)))
    if dept_cd:
        depth = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy()[:n]
    else:
        depth = np.linspace(float(lr.start_depth or 0.0), float(lr.stop_depth or 0.0), n)
    rhob, dt = rhob[:n], dt[:n]

    vel = np.where(dt > 0, 1e6 / dt, np.nan)
    ai = rhob * vel
    ai = np.where(np.isfinite(ai), ai, np.nan)

    rc = np.zeros(n)
    for i in range(1, n):
        a0, a1 = ai[i - 1], ai[i]
        if np.isfinite(a0) and np.isfinite(a1) and abs(a1 + a0) > 1e-12:
            rc[i] = (a1 - a0) / (a1 + a0)
        else:
            rc[i] = 0.0

    freq = float(payload.get("frequency_hz", 30.0) or 30.0)
    freq = max(20.0, min(60.0, freq))
    dt_s = 0.001
    t = np.arange(-0.064, 0.064 + dt_s, dt_s)
    pf = np.pi * freq * t
    wavelet = (1.0 - 2.0 * (pf ** 2)) * np.exp(-(pf ** 2))
    synthetic = np.convolve(rc, wavelet, mode="same")

    step = max(1, int(n / 1200))
    return {
        "depth": np.where(np.isnan(depth[::step]), None, depth[::step]).tolist(),
        "ai": np.where(np.isnan(ai[::step]), None, ai[::step]).tolist(),
        "rc": rc[::step].tolist(),
        "synthetic": synthetic[::step].tolist(),
        "frequency_hz": freq,
        "wavelet": {
            "time": t.tolist(),
            "amplitude": wavelet.tolist(),
        },
    }


@app.get("/api/wells/{wid}/image-log")
def image_log_get(wid: int, db: Session = Depends(get_db)):
    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")
    cds = db.query(CurveData).filter(CurveData.log_run_id == lr.id).all()
    cmap = {c.mnemonic: c for c in cds}
    dept_cd = cmap.get("DEPT") or cmap.get("DEPTH")
    amp_cd = cmap.get("FMI") or cmap.get("OBI") or cmap.get("RT") or cmap.get("RESD") or cmap.get("GR")
    if not amp_cd:
        raise HTTPException(400, "No usable curve for image generation")

    amp = np.frombuffer(amp_cd.data_binary, dtype=np.float64).copy()
    depth = np.frombuffer(dept_cd.data_binary, dtype=np.float64).copy() if dept_cd else np.arange(len(amp), dtype=float)
    n = min(len(amp), len(depth))
    amp, depth = amp[:n], depth[:n]

    if amp_cd.mnemonic == "GR":
        valid_gr = amp[np.isfinite(amp)]
        med = float(np.nanmedian(valid_gr)) if len(valid_gr) else 80.0
        amp = np.where(np.isfinite(amp), amp, med)
        amp = (amp - np.nanmin(amp)) / max(np.nanmax(amp) - np.nanmin(amp), 1e-9)
        amp = 1.0 - amp

    valid = amp[np.isfinite(amp)]
    if len(valid) == 0:
        raise HTTPException(400, "No valid samples for image log")
    lo, hi = np.percentile(valid, [5, 95])
    norm = np.clip((amp - lo) / max(hi - lo, 1e-9), 0.0, 1.0)

    n_bins = 72
    step = max(1, int(n / 1200))
    image = []
    depths = []
    for i in range(0, n, step):
        if not np.isfinite(norm[i]):
            continue
        base = float(norm[i])
        row = []
        for b in range(n_bins):
            ang = (2.0 * np.pi * b) / n_bins
            val = np.clip(base + 0.14 * np.sin(ang + i * 0.02) + 0.05 * np.cos(2 * ang), 0.0, 1.0)
            row.append(val)
        image.append(row)
        depths.append(float(depth[i]))

    return {
        "depth": depths,
        "image": image,
        "n_bins": n_bins,
        "curve_used": amp_cd.mnemonic,
        "synthetic": amp_cd.mnemonic == "GR",
    }


@app.get("/api/wells/{wid}/formation-tester")
def formation_tester(wid: int, db: Session = Depends(get_db)):
    base = rft_pressure_gradient(wid, db)
    points = base.get("classified_points") or base.get("points") or []
    contacts = []
    for c in (base.get("fluid_contacts") or []):
        f, t = c.get("from_fluid", ""), c.get("to_fluid", "")
        label = "contact"
        if {f, t} == {"oil", "water"}:
            label = "OWC"
        elif {f, t} == {"gas", "oil"}:
            label = "GOC"
        contacts.append({
            "depth": c.get("depth"),
            "label": label,
            "type": c.get("type"),
            "from_fluid": f,
            "to_fluid": t,
        })
    return {
        "count": base.get("count", 0),
        "overall": base.get("overall"),
        "points": points,
        "fluid_segments": base.get("fluid_segments") or [],
        "contacts": contacts,
    }




# ─── Feature 18: Client Handoff Bundle ─────────────────────
@app.get("/api/wells/{wid}/export-bundle")
def export_client_bundle(wid: int, db: Session = Depends(get_db)):
    """Export a ZIP bundle with LAS, tops, zones, params, and summary report."""
    import zipfile
    import io
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    tops = db.query(FormationTop).filter(FormationTop.well_id == wid).order_by(FormationTop.depth).all()
    zones = db.query(Zone).filter(Zone.well_id == wid).order_by(Zone.top_depth).all()
    params = db.query(PetroParams).filter(PetroParams.well_id == wid).first()

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
        # 1. LAS file
        if lr:
            cds = db.query(CurveData).filter(CurveData.log_run_id == lr.id).all()
            las_lines = [
                "~Version Information",
                "VERS.                  2.0:   CWLS Log ASCII Standard - VERSION 2.0",
                "WRAP.                  NO:   One line per depth step",
                "~Well Information",
                f"WELL.                  {well.name}:   Well Name",
                f"STRT. {float(lr.start_depth or 0):>10.2f} {getattr(lr, 'depth_unit', 'FT')}:   Start Depth",
                f"STOP. {float(lr.stop_depth or 0):>10.2f} {getattr(lr, 'depth_unit', 'FT')}:   Stop Depth",
                f"STEP. {float(lr.step or 1):>10.4f} {getattr(lr, 'depth_unit', 'FT')}:   Step",
                f"NULL.              -999.25:   Null Value",
                f"COMP.                  GeoLog:   Company",
                f"DATE.          {__import__('datetime').date.today()}:   Date",
                "~Curve Information",
            ]
            for c in cds:
                las_lines.append(f"{c.mnemonic:>8}.{c.unit:>4}:   {c.description or c.mnemonic}")
            las_lines.append("~Ascii")
            depth_arr = None
            curve_arrays = {}
            for c in cds:
                import numpy as np
                arr = np.frombuffer(c.data_binary, dtype=np.float64)
                if c.mnemonic in ('DEPT', 'DEPTH'):
                    depth_arr = arr
                else:
                    curve_arrays[c.mnemonic] = arr
            if depth_arr is not None:
                for i in range(len(depth_arr)):
                    vals = [f"{depth_arr[i]:>10.2f}"]
                    for c in cds:
                        if c.mnemonic not in ('DEPT', 'DEPTH'):
                            v = curve_arrays.get(c.mnemonic, [])
                            vals.append(f"{v[i]:>10.4f}" if i < len(v) else "   -999.25")
                    las_lines.append(" ".join(vals))
            zf.writestr(f"{well.name}.las", "\n".join(las_lines))

        # 2. Tops CSV
        if tops:
            tops_csv = "depth,name,formation_name,color\n"
            for t in tops:
                tops_csv += f"{t.depth},{t.name or ''},{t.formation_name or ''},{t.color or ''}\n"
            zf.writestr("tops.csv", tops_csv)

        # 3. Zones CSV
        if zones:
            zones_csv = "name,top_depth,bottom_depth,sw_avg,vsh_avg,phie_avg,ntg\n"
            for z in zones:
                zones_csv += f"{z.zone_name or ''},{z.top_depth},{z.bottom_depth},{z.sw_avg or ''},{z.vsh_avg or ''},{z.phie_avg or ''},{z.net_to_gross or ''}\n"
            zf.writestr("zones.csv", zones_csv)

        # 4. Petro params JSON
        if params:
            import json
            p = {k: getattr(params, k) for k in ['saturation_model', 'a', 'm', 'n', 'rw', 'vsh_cutoff', 'phie_cutoff', 'sw_cutoff', 'template'] if hasattr(params, k)}
            zf.writestr("petro_params.json", json.dumps(p, indent=2))

        # 5. Summary report
        report = f"# GeoLog Export Report\nWell: {well.name}\nDate: {__import__('datetime').datetime.now().isoformat()}\n\n"
        report += f"## Log Runs\n- Depth range: {lr.start_depth} - {lr.stop_depth} ft\n- Points: {lr.num_points}\n\n" if lr else ""
        report += f"## Formation Tops ({len(tops)} entries)\n"
        for t in tops:
            report += f"- {t.depth:.1f} ft: {t.name or t.formation_name}\n"
        report += f"\n## Zones ({len(zones)} entries)\n"
        for z in zones:
            report += f"- {z.zone_name}: {z.top_depth:.1f} - {z.bottom_depth:.1f} ft (NTG: {z.net_to_gross or 'N/A'})\n"
        zf.writestr("report.md", report)

    buf.seek(0)
    return StreamingResponse(buf, media_type="application/zip", headers={
        "Content-Disposition": f"attachment; filename={well.name}_bundle.zip"
    })


# ─── Real-Time Collaboration WebSocket ──────────────────────
import asyncio
import json as _json

class CollabRoom:
    """Manages WebSocket connections per well."""
    def __init__(self):
        self.connections: dict[str, list] = {}  # well_id -> [(ws, user_id, name, role)]

    async def connect(self, well_id: str, ws, user_id: str, name: str, role: str = "viewer"):
        await ws.accept()
        key = str(well_id)
        if key not in self.connections:
            self.connections[key] = []
        self.connections[key].append((ws, user_id, name, role))
        await self._broadcast_peers(key)

    async def disconnect(self, well_id: str, ws):
        key = str(well_id)
        if key in self.connections:
            self.connections[key] = [(w, uid, n, r) for w, uid, n, r in self.connections[key] if w is not ws]
            await self._broadcast_peers(key)

    async def broadcast(self, well_id: str, message: dict, exclude_ws=None):
        key = str(well_id)
        if key not in self.connections:
            return
        dead = []
        for ws, uid, name, role in self.connections[key]:
            if ws is exclude_ws:
                continue
            try:
                await ws.send_text(_json.dumps(message))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections[key] = [(w, uid, n, r) for w, uid, n, r in self.connections[key] if w is not ws]

    async def _broadcast_peers(self, key: str):
        if key not in self.connections:
            return
        users = [{"user_id": uid, "name": name, "role": role} for _, uid, name, role in self.connections[key]]
        msg = _json.dumps({"type": "peers", "users": users})
        dead = []
        for ws, _, _, _ in self.connections[key]:
            try:
                await ws.send_text(msg)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.connections[key] = [(w, uid, n, r) for w, uid, n, r in self.connections[key] if w is not ws]

collab_rooms = CollabRoom()

@app.websocket("/ws/collab/{well_id}")
async def websocket_collab(websocket: WebSocket, well_id: int):
    user_id = websocket.query_params.get("user", f"anon_{id(websocket)}")
    user_name = websocket.query_params.get("name", user_id)
    role = websocket.query_params.get("role", "viewer")
    await collab_rooms.connect(well_id, websocket, user_id, user_name, role)
    try:
        while True:
            data = await websocket.receive_text()
            msg = _json.loads(data)
            msg["user_id"] = user_id
            msg["name"] = user_name
            await collab_rooms.broadcast(well_id, msg, exclude_ws=websocket)
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await collab_rooms.disconnect(well_id, websocket)


# ─── Frontend Serving ─────────────────────────────────────────
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")


@app.middleware("http")
async def spa_fallback(request: Request, call_next):
    response = await call_next(request)
    if (
        response.status_code == 404
        and request.method == "GET"
        and not request.url.path.startswith("/api")
        and not request.url.path.startswith("/static")
    ):
        index = os.path.join(frontend_dir, "index.html")
        if os.path.isfile(index):
            return FileResponse(index)
    return response
