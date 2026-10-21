"""GeoLog — Oil & Gas Well Log Viewer."""
import hashlib
import json
import logging
import os
import time
import traceback
import uuid

import numpy as np
from fastapi import (
    Depends,
    FastAPI,
    HTTPException,
    Request,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from starlette.middleware.base import BaseHTTPMiddleware

try:
    from timeutils import utcnow
except ImportError:
    from backend.timeutils import utcnow

try:
    from audit import append_audit_entry
    from deps import (
        SafeJSONResponse,
        require_role,
        require_viewer,
    )
    from validation import pick_typed
    from jobs import (
        get_job as _get_job,
        list_jobs as _list_jobs,
    )
    from observability import record_request
    from schema import ensure_schema
    from version import __version__
    from well_state import get_well_lock as _get_well_lock
    from routers.audit import router as audit_router
    from routers.correlation import router as corr_router
    from routers.log_runs import router as log_runs_router
    from routers.nmr import router as nmr_router
    from routers.ops import router as ops_router
    from routers.projects import router as projects_router
    from routers.qc import router as qc_router
    from routers.reports import router as reports_router
    from routers.templates import router as templates_router
    from routers.units import router as units_router
    from routers.users import router as users_router
    from routers.wells import router as wells_router
    from routers.zonation import router as zonation_router
except ImportError:
    from backend.audit import append_audit_entry
    from backend.deps import (
        SafeJSONResponse,
        require_role,
        require_viewer,
    )
    from backend.validation import pick_typed
    from backend.jobs import (
        get_job as _get_job,
        list_jobs as _list_jobs,
    )
    from backend.observability import record_request
    from backend.schema import ensure_schema
    from backend.version import __version__
    from backend.well_state import get_well_lock as _get_well_lock
    from backend.routers.audit import router as audit_router
    from backend.routers.correlation import router as corr_router
    from backend.routers.log_runs import router as log_runs_router
    from backend.routers.nmr import router as nmr_router
    from backend.routers.ops import router as ops_router
    from backend.routers.projects import router as projects_router
    from backend.routers.qc import router as qc_router
    from backend.routers.reports import router as reports_router
    from backend.routers.templates import router as templates_router
    from backend.routers.units import router as units_router
    from backend.routers.users import router as users_router
    from backend.routers.wells import router as wells_router
    from backend.routers.zonation import router as zonation_router




try:
    from database import SessionLocal, get_db
    from las_parser import CURVE_TRACKS, LASParser
    from models import (
        Annotation,
        CompletionData,
        CorrelationMarker,
        CorrelationProfile,
        CurveData,
        FormationTop,
        LogRun,
        Project,
        User,
        Well,
    )
    from security import (
        ROLE_RANK,
        AuthConfig,
        current_env,
        resolve_auth_context,
        role_from_request,
    )
except ImportError:
    from backend.database import SessionLocal, get_db
    from backend.las_parser import CURVE_TRACKS, LASParser
    from backend.models import (
        Annotation,
        CompletionData,
        CorrelationMarker,
        CorrelationProfile,
        CurveData,
        FormationTop,
        LogRun,
        Project,
        User,
        Well,
    )
    from backend.security import (
        ROLE_RANK,
        AuthConfig,
        current_env,
        resolve_auth_context,
        role_from_request,
    )

# Create tables
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("geolog")



# Schema is owned by Alembic. See backend/schema.py for why the previous
# create_all() + _ensure_* helper combination could not be trusted.
ensure_schema()











app = FastAPI(
    title="GeoLog",
    description="Oil & Gas Well Log Viewer",
    version=__version__,
    docs_url="/docs",
    redoc_url="/redoc",
    default_response_class=SafeJSONResponse,
)


@app.exception_handler(RequestValidationError)
async def _request_validation_error_handler(request: Request, exc: RequestValidationError):
    """Return a JSON-safe 422.

    FastAPI's default handler echoes the offending input, and Starlette serialises
    responses with `allow_nan=False`. A client sending `{"x": Infinity}` therefore
    turned a 422 into a 500, on every endpoint with a Pydantic body model.
    """
    return SafeJSONResponse(status_code=422, content={"detail": exc.errors()})


app.include_router(qc_router)
app.include_router(corr_router)
app.include_router(zonation_router)
app.include_router(units_router)
app.include_router(templates_router)
app.include_router(reports_router)
app.include_router(users_router)
app.include_router(log_runs_router)
app.include_router(nmr_router)
app.include_router(projects_router)
app.include_router(audit_router)
app.include_router(ops_router)
app.include_router(wells_router)






AUTH_CONFIG = AuthConfig.from_env()
if AUTH_CONFIG.mode == "header":
    logger.warning(
        "AUTH_MODE=header (trusted client header, GEOLOG_ENV=%s). "
        "Use AUTH_MODE=jwt for any shared or public deployment.",
        current_env(),
    )


# Kept as an alias: existing call sites in this module use the private name.
_require_role = require_role

# CORS is opt-in. The bundled frontend is served from this same origin, so it
# needs none. A wildcard origin combined with credentials would let any site a
# logged-in user visits read the whole database.
_cors_origins = [o.strip() for o in (os.getenv("GEOLOG_CORS_ORIGINS") or "").split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
app.add_middleware(GZipMiddleware, minimum_size=1000)










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


# Paths that must work before a caller has a token: login, health checks, docs,
# and the bundled SPA/static assets. Everything else under /api still requires
# auth in jwt mode.
PUBLIC_PATHS = frozenset({
    "/api/health",
    "/api/users/token",
    "/docs",
    "/docs/oauth2-redirect",
    "/redoc",
    "/openapi.json",
    "/favicon.ico",
})

def _is_public_request(request: Request) -> bool:
    path = request.url.path
    if request.method == "OPTIONS":
        return True
    if path in PUBLIC_PATHS or path.startswith("/static/"):
        return True
    # The SPA shell and its non-API assets carry no data by themselves.
    return request.method in {"GET", "HEAD"} and not path.startswith("/api/")

class AuthContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if _is_public_request(request):
            return await call_next(request)
        try:
            auth_ctx = resolve_auth_context(request, AUTH_CONFIG)
        except HTTPException as e:
            return SafeJSONResponse(status_code=e.status_code, content={"detail": e.detail})
        request.state.user_role = auth_ctx.role
        request.state.auth_subject = auth_ctx.subject
        request.state.auth_source = auth_ctx.source
        request.state.auth_claims = auth_ctx.claims
        return await call_next(request)


def _https_required() -> bool:
    return (os.getenv("GEOLOG_REQUIRE_HTTPS", "false") or "false").strip().lower() in {"1", "true", "yes", "on"}

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Optional HTTPS redirect plus baseline response hardening headers."""

    async def dispatch(self, request: Request, call_next):
        if (
            _https_required()
            and request.url.scheme != "https"
            and request.method not in {"OPTIONS"}
            and request.url.path != "/api/health"
        ):
            return RedirectResponse(str(request.url.replace(scheme="https")), status_code=308)

        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        if request.url.scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response

class RequestMetricsMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start = time.perf_counter()
        response = await call_next(request)
        elapsed_ms = (time.perf_counter() - start) * 1000.0
        method = request.method.upper()
        status = str(getattr(response, "status_code", 0))

        # Counters live in backend/observability.py: the /api/ops routes read the
        # same state, so it cannot live in this module.
        record_request(
            method=method,
            path=request.url.path,
            status=int(status) if status.isdigit() else 0,
            elapsed_ms=elapsed_ms,
            request_id=str(getattr(request.state, "request_id", "") or ""),
            trace_id=str(getattr(request.state, "trace_id", "") or ""),
        )

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

            # Only the two POST query endpoints are viewer-safe. The old
            # "/api/log-runs/" prefix also matched curve writes (filter,
            # curve-override, curve-edit, depth-shift).
            viewer_safe_post = path.startswith("/api/log-runs/") and path.endswith(
                ("/data", "/data-decimated")
            )

            # Admin-only paths (structural/destructive)
            admin_exact_post = {"/api/projects/", "/api/wells/"}
            admin_prefixes = ("/api/users",)

            required = "interpreter"
            if path in admin_exact_post and method == "POST":
                required = "admin"
            elif path == "/api/users/token":
                required = "viewer"
            elif any(path.startswith(p) for p in admin_prefixes):
                required = "admin"
            elif method == "DELETE":
                required = "admin"
            elif method == "POST" and viewer_safe_post:
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
            # Shared with log_audit(), so the two writers cannot compute the
            # chain differently. The read-previous-hash and insert happen under
            # a lock inside append_audit_entry.
            append_audit_entry(
                db,
                action=f"write:{method.lower()}",
                entity_type="api",
                well_id=well_id,
                project_id=project_id,
                details=path,
                request_id=request_id,
                subject=subject,
                role=role,
                method=method,
                path=path,
                status_code=int(response.status_code),
                payload_hash=payload_hash,
            )
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
app.add_middleware(SecurityHeadersMiddleware)


def _enforce_secrets_source_policy() -> None:
    """Fail fast in non-dev environments when secrets source is not configured."""
    env = (os.getenv("GEOLOG_ENV") or os.getenv("ENV") or "dev").strip().lower()
    secrets_source = (os.getenv("GEOLOG_SECRETS_SOURCE") or "").strip()
    strict = (os.getenv("GEOLOG_ENFORCE_SECRETS_SOURCE", "true") or "true").strip().lower() in {"1", "true", "yes", "on"}
    if not strict:
        return
    if env in {"dev", "local", "test"}:
        return
    if not secrets_source:
        raise RuntimeError("GEOLOG_SECRETS_SOURCE is required for non-dev environments")


@app.on_event("startup")
def _startup_security_guards():
    _enforce_secrets_source_policy()


# ─── Demo seed (startup + tests) ────────────────────────────
def seed_demo_data(db: Session = None) -> bool:
    """Seed demo data when the database is empty. Returns True if it seeded.

    Output is ASCII-only on purpose: this runs during startup and the Windows
    console codepage (cp1252) cannot encode emoji, which aborted startup.
    """
    owns_session = db is None
    db = db if db is not None else SessionLocal()
    try:
        if db.query(Project).count() > 0:
            return False  # Already seeded

        # Find demo LAS file (try multiple paths for Docker compat)
        _here = os.path.dirname(os.path.abspath(__file__))
        demo_paths = [
            os.path.join(_here, "demo.las"),
            os.path.join(_here, "..", "data", "hawkins_01.las"),
            os.path.join(_here, "data", "hawkins_01.las"),
        ]
        demo_las = next((p for p in demo_paths if os.path.isfile(p)), None)
        if not demo_las:
            print("[seed] no demo LAS found, skipping")
            return False

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
        print(
            f"[seed] Auto-seeded: {w1.name} ({nc1} curves, {np1} pts), "
            f"{w2.name} ({nc2} curves, {np2} pts), {nt1} tops each"
        )
        return True
    except Exception as e:
        db.rollback()
        print(f"[seed] Auto-seed failed: {e}")
        return False
    finally:
        if owns_session:
            db.close()


@app.on_event("startup")
def _auto_seed():
    """Seed demo data if database is empty. Gate behind GEOLOG_ENABLE_DEMO_SEED=true."""
    if os.environ.get("GEOLOG_ENABLE_DEMO_SEED", "false").lower() != "true":
        return
    seed_demo_data()


# ─── Health ───────────────────────────────────────────────────
@app.get("/api/health")
def health():
    return {"status": "ok", "app": "GeoLog", "version": __version__}


# ─── Projects ─────────────────────────────────────────────────




# ─── Wells ────────────────────────────────────────────────────







# ─── LAS Upload ───────────────────────────────────────────────










# ─── Delete Log Run ─────────────────────────────────────────────


# ─── Log Run Diff (LAS comparison) ─────────────────────────────


# ─── Curve Data ───────────────────────────────────────────────








# ─── Formation Tops ───────────────────────────────────────────


@app.delete("/api/tops/{tid}", status_code=204)
def delete_top(tid: int, db: Session = Depends(get_db)):
    t = db.query(FormationTop).filter(FormationTop.id == tid).first()
    if not t:
        raise HTTPException(404, "Formation top not found")
    db.delete(t)
    db.commit()


# ─── Zones (persisted) ─────────────────────────────────────────




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
    # Validate every marker before touching the database. The delete below runs
    # in the same transaction, so a bad marker would have rolled back — but
    # validating first means the client gets a 400 naming the field instead of a
    # 500, and no partially-applied replacement can ever be committed.
    prepared = []
    for index, m in enumerate(markers):
        try:
            a_depth = float(m.get("aDepth"))
            b_depth = float(m.get("bDepth"))
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail=f"markers[{index}] requires numeric aDepth and bDepth",
            )
        prepared.append((a_depth, b_depth, str(m.get("label", ""))))

    db.query(CorrelationMarker).filter(
        ((CorrelationMarker.well_a_id == well_a_id) & (CorrelationMarker.well_b_id == well_b_id)) |
        ((CorrelationMarker.well_a_id == well_b_id) & (CorrelationMarker.well_b_id == well_a_id))
    ).delete()
    for a_depth, b_depth, label in prepared:
        db.add(CorrelationMarker(
            well_a_id=well_a_id,
            well_b_id=well_b_id,
            a_depth=a_depth,
            b_depth=b_depth,
            label=label,
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
    # Was a bare setattr loop: {"depth": "abc"} reached the FLOAT column and
    # {"depth": null} hit its NOT NULL constraint, both surfacing as 500.
    for field, value in pick_typed(
        data,
        strings=("formation_name", "color", "lithology", "notes", "depth_unit"),
        floats=("depth", "top_depth", "base_depth"),
        nullable=("top_depth", "base_depth"),
    ).items():
        setattr(t, field, value)
    db.commit()
    db.refresh(t)
    return {c.name: getattr(t, c.name) for c in FormationTop.__table__.columns}


# ─── Bulk Export ─────────────────────────────────────────────




















































# ─── Curve Metadata ───────────────────────────────────────────
@app.get("/api/curve-config")
def get_curve_config():
    """Return standard curve track configurations."""
    return CURVE_TRACKS



# GET /api/templates is served by backend/routers/templates.py. A second handler
# used to be registered here and was silently shadowed by the router's.




# ─── Petrophysics Parameters Persistence ──────────────────────






# ─── Sensitivity Analysis (Monte Carlo) ───────────────────────


# ─── Well Comparison (multi-well stats) ───────────────────────



# ─── Bulk LAS Upload ──────────────────────────────────────────


# ─── Depth Shift per Log Run ──────────────────────────────────





# ─── Annotations CRUD ────────────────────────────────────────




@app.delete("/api/annotations/{aid}")
def delete_annotation(aid: int, db: Session = Depends(get_db)):
    ann = db.query(Annotation).filter(Annotation.id == aid).first()
    if not ann:
        raise HTTPException(404, "Annotation not found")
    db.delete(ann)
    db.commit()
    return {"status": "ok"}


# ─── DST / RFT Pressure Data ──────────────────────────────────














@app.delete("/api/completion/{cid}")
def delete_completion_component(cid: int, db: Session = Depends(get_db)):
    row = db.query(CompletionData).filter(CompletionData.id == cid).first()
    if not row:
        raise HTTPException(404, "Completion component not found")
    db.delete(row)
    db.commit()
    return {"status": "ok"}








# ─── Production Data ──────────────────────────────────────────
















# ─── Curve Alias/Mnemonic Remap ──────────────────────────────





# ─── Curve Splice/Merge ──────────────────────────────────────


# ─── Log Run List (for overlay/splice selection) ─────────────


# ─── Print-Ready Report ──────────────────────────────────────



# ─── Electrofacies / Rock Typing ──────────────────────────────


# ─── Despike / Smooth ────────────────────────────────────────


# ─── Depth Match (Auto Cross-Correlation) ────────────────────


# ─── Curve Override ──────────────────────────────────────────




# ─── Multi-well Strip Log Data ────────────────────────────────




# ─── Formation Top Auto-Pick ──────────────────────────────────


# ─── Save Auto-Picked Tops ───────────────────────────────────


# ─── CSV Data Import ──────────────────────────────────────────


# ─── Well Trajectory / Deviation Survey ──────────────────────






# ─── Stratigraphic Normalization ─────────────────────────────


# ─── Sprint 21: Professional Petrophysics / Plotting ─────────








# ─── Sprint 22: Buckles / Hingle / Curve Calculator ───────────






















# ─── Helper: Audit Log ────────────────────────────────────────


# ─── Audit Trail ──────────────────────────────────────────────
























# ─── Cross-Plot Matrix (multi-well) ──────────────────────────


# ─── Performance: Decimated Curve Data ────────────────────────


# ─── Sprint 27: Dual-Water Saturation Model ─────────────────


# ─── Sprint 27: Vcl Model Selector ──────────────────────────




# ══════════════════════════════════════════════════════════════
# Sprint 28: Professional Petrophysics Engine
# ══════════════════════════════════════════════════════════════









# ─── Sprint 27: Tornado Chart Data ──────────────────────────


# ─── Sprint 27: Core Calibration ────────────────────────────


# ─── Sprint 27: Enhanced QC with Auto-Fix ───────────────────


# ─── Inject audit logging into key endpoints ──────────────────
# Patch upload endpoint to log audit


# ─── Sprint 28: Multi-User Roles ─────────────────────────────
# /api/users routes moved to backend/routers/users.py


# ─── Sprint 28: Synthetic Seismogram ─────────────────────────








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
    return {"ok": ok, "checks": checks, "timestamp": utcnow().isoformat() + "Z"}


# (deduplicated) auto-pick-tops endpoint defined earlier in file

# ─── Sprint 28: Offset-Well Analog ──────────────────────────


# ─── Sprint 28: LAS Export with All Data ─────────────────────


# ─── Sprint 28: Image Log (FMI/OBI lite) ─────────────────────


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










# ─── Feature 18: Client Handoff Bundle ─────────────────────


# ─── Real-Time Collaboration WebSocket ──────────────────────
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
    auth_header = websocket.headers.get("authorization") or ""
    token = websocket.query_params.get("token") or (
        auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else ""
    )
    if AUTH_CONFIG.mode == "jwt":
        if not token:
            await websocket.close(code=1008)
            return
        class _AuthRequest:
            headers = {"Authorization": f"Bearer {token}"}
        try:
            auth_ctx = resolve_auth_context(_AuthRequest(), AUTH_CONFIG)
        except HTTPException:
            await websocket.close(code=1008)
            return
        role = auth_ctx.role
        user_id = auth_ctx.subject or websocket.query_params.get("user", f"anon_{id(websocket)}")
    else:
        role = (websocket.headers.get(AUTH_CONFIG.header_role_name)
                or websocket.query_params.get("role") or "viewer").lower()
        role = role if role in ROLE_RANK else "viewer"
        user_id = websocket.query_params.get("user", f"anon_{id(websocket)}")
    user_name = websocket.query_params.get("name", user_id)
    await collab_rooms.connect(well_id, websocket, user_id, user_name, role)
    try:
        while True:
            data = await websocket.receive_text()
            msg = _json.loads(data)
            if not isinstance(msg, dict):
                continue
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
