"""GeoLog — Oil & Gas Well Log Viewer."""
import logging
import traceback
from fastapi import FastAPI, Request, UploadFile, File, Depends, HTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
import numpy as np
import json
import os
import datetime
import csv
import io

try:
    from database import engine, Base, get_db, SessionLocal
    from models import Project, Well, LogRun, CurveData, FormationTop, Annotation, Zone, CorrelationMarker, CorrelationProfile, PetroParams, LogRunDepthShift, CurveAlias, DeviationSurvey, AuditLog
    from las_parser import LASParser, CURVE_TRACKS
except ImportError:
    from backend.database import engine, Base, get_db, SessionLocal
    from backend.models import Project, Well, LogRun, CurveData, FormationTop, Annotation, Zone, CorrelationMarker, CorrelationProfile, PetroParams, LogRunDepthShift, CurveAlias, DeviationSurvey, AuditLog
    from backend.las_parser import LASParser, CURVE_TRACKS

# Create tables
# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("geolog")

Base.metadata.create_all(bind=engine)

app = FastAPI(title="GeoLog", version="2.0.0", description="Oil & Gas Well Log Viewer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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
            return JSONResponse(
                status_code=500,
                content={"detail": "Internal server error", "error": str(e)},
            )

app.add_middleware(ErrorLoggingMiddleware)


# ─── Auto-seed demo data on first startup ───────────────────
@app.on_event("startup")
def _auto_seed():
    """Seed demo data if database is empty."""
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
def get_curve_data(lr_id: int, req: dict, db: Session = Depends(get_db)):
    """Get curve data for specified mnemonics."""
    mnemonics = req.get("curve_mnemonics", [])
    start = req.get("start_depth")
    stop = req.get("stop_depth")
    step = req.get("step", 1)

    if not mnemonics:
        raise HTTPException(400, "No curves requested")

    lr = db.query(LogRun).filter(LogRun.id == lr_id).first()
    if not lr:
        raise HTTPException(404, "Log run not found")

    # Get depth curve with fallback candidates, then first curve in run
    depth_curve = db.query(CurveData).filter(
        CurveData.log_run_id == lr_id,
        CurveData.mnemonic.in_(["DEPT", "DEPTH", "MD", "TVD"])
    ).first()
    if not depth_curve:
        depth_curve = db.query(CurveData).filter(CurveData.log_run_id == lr_id).order_by(CurveData.id.asc()).first()

    # Build unified depth mask ONCE
    depth_arr = None
    if depth_curve and depth_curve.data_binary:
        depth_arr = np.frombuffer(depth_curve.data_binary, dtype=np.float64).copy()
        mask = np.ones(len(depth_arr), dtype=bool)
        if start is not None:
            mask &= (depth_arr >= start)
        if stop is not None:
            mask &= (depth_arr <= stop)

    curves = db.query(CurveData).filter(
        CurveData.log_run_id == lr_id,
        CurveData.mnemonic.in_(mnemonics)
    ).all()

    result = {}
    for c in curves:
        arr = np.frombuffer(c.data_binary, dtype=np.float64).copy()
        if depth_arr is not None and len(arr) == len(depth_arr):
            arr = arr[mask]
        if step > 1:
            arr = arr[::step]
        result[c.mnemonic] = [
            None if np.isnan(v) else round(float(v), 4)
            for v in arr
        ]

    # Also return depth (same mask + decimation)
    if depth_arr is not None:
        d = depth_arr[mask] if mask is not None else depth_arr
        if step > 1:
            d = d[::step]
        result["DEPTH"] = [round(float(v), 2) for v in d]

    return result


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


# ─── Curve Metadata ───────────────────────────────────────────
@app.get("/api/curve-config")
def get_curve_config():
    """Return standard curve track configurations."""
    return CURVE_TRACKS



# ─── Petrophysics Parameters Persistence ──────────────────────
@app.get("/api/wells/{wid}/petro-params")
def get_petro_params(wid: int, db: Session = Depends(get_db)):
    pp = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    if not pp:
        return {"well_id": wid, "saturation_model": "archie", "a": 1.0, "m": 2.0, "n": 2.0, "rw": 0.1,
                "vsh_cutoff": 0.35, "phie_cutoff": 0.10, "sw_cutoff": 0.60, "template": "custom"}
    return {c.name: getattr(pp, c.name) for c in PetroParams.__table__.columns}


@app.post("/api/wells/{wid}/petro-params")
def save_petro_params(wid: int, data: dict, db: Session = Depends(get_db)):
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
    return {"status": "ok"}


# ─── Sensitivity Analysis (Monte Carlo) ───────────────────────
@app.post("/api/wells/{wid}/sensitivity")
def sensitivity_analysis(wid: int, data: dict, db: Session = Depends(get_db)):
    """Run sensitivity: vary params to get P10/P50/P90 for net_pay."""
    import random
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

    base_a = float(data.get("a", 1.0))
    base_m = float(data.get("m", 2.0))
    base_n = float(data.get("n", 2.0))
    base_rw = float(data.get("rw", 0.1))
    vsh_cut = float(data.get("vsh_cutoff", 0.35))
    phie_cut = float(data.get("phie_cutoff", 0.10))
    sw_cut = float(data.get("sw_cutoff", 0.60))
    n_iter = min(int(data.get("iterations", 500)), 2000)
    pct = float(data.get("variation_pct", 30)) / 100.0
    model = data.get("saturation_model", "archie")
    start_depth = data.get("start_depth")
    stop_depth = data.get("stop_depth")

    gr_valid = gr[~np.isnan(gr) & (gr > 0)]
    gr_min = float(np.min(gr_valid)) if len(gr_valid) else 0
    gr_max = float(np.max(gr_valid)) if len(gr_valid) else 150
    if gr_max == gr_min:
        gr_max = gr_min + 1

    step = float(lr.step) if lr.step else abs(float(rt[1] - rt[0])) if len(rt) > 1 else 0.5
    if step == 0:
        step = 0.5

    # Apply depth filter if provided
    depth_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    depth_arr = np.frombuffer(depth_cd.data_binary, dtype=np.float64).copy() if depth_cd else None
    depth_mask = np.ones(len(rt), dtype=bool)
    if depth_arr is not None and (start_depth is not None or stop_depth is not None):
        if start_depth is not None:
            depth_mask &= (depth_arr >= float(start_depth))
        if stop_depth is not None:
            depth_mask &= (depth_arr <= float(stop_depth))

    net_pays = []
    for _ in range(n_iter):
        a_v = base_a * (1 + random.uniform(-pct, pct))
        m_v = base_m * (1 + random.uniform(-pct, pct))
        n_v = base_n * (1 + random.uniform(-pct, pct))
        rw_v = base_rw * (1 + random.uniform(-pct, pct))
        pay = 0
        for i in range(len(rt)):
            if not depth_mask[i]:
                continue
            if np.isnan(rt[i]) or np.isnan(nphi[i]) or rt[i] <= 0 or nphi[i] <= -1:
                continue
            igr = (gr[i] - gr_min) / (gr_max - gr_min) if not np.isnan(gr[i]) else 0
            vsh_v = max(0, min(1, igr))
            phi = max(0, nphi[i] * (1 - vsh_v))
            if phi < 0.01:
                continue
            if model == "simandoux":
                inner = (a_v * rw_v) / (phi ** m_v * rt[i]) - vsh_v * rw_v / (0.4 * phi)
                sw_v = np.sqrt(max(0, inner))
            elif model == "indonesian":
                denom = np.sqrt(phi ** m_v / (a_v * rw_v)) + np.sqrt(vsh_v) / np.sqrt(max(rt[i], 0.01))
                sw_v = 1.0 / (np.sqrt(max(rt[i], 0.01)) * denom) if denom > 0 else 1.0
            else:
                sw_v = (a_v / (phi ** m_v * rt[i] / rw_v)) ** (1.0 / n_v)
            sw_v = max(0, min(1, sw_v))
            if vsh_v < vsh_cut and phi > phie_cut and sw_v < sw_cut:
                pay += 1
        net_pays.append(pay * step)

    net_pays.sort()
    p10 = net_pays[int(len(net_pays) * 0.1)] if net_pays else 0
    p50 = net_pays[int(len(net_pays) * 0.5)] if net_pays else 0
    p90 = net_pays[int(len(net_pays) * 0.9)] if net_pays else 0

    return {
        "iterations": n_iter,
        "variation_pct": round(pct * 100, 1),
        "p10_net_pay": round(float(p10), 2),
        "p50_net_pay": round(float(p50), 2),
        "p90_net_pay": round(float(p90), 2),
        "mean_net_pay": round(float(np.mean(net_pays)), 2) if net_pays else 0,
        "std_net_pay": round(float(np.std(net_pays)), 2) if net_pays else 0,
        "histogram_bins": [round(float(x), 1) for x in np.histogram_bin_edges(net_pays, bins=20).tolist()],
        "histogram_counts": np.histogram(net_pays, bins=20)[0].tolist(),
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
    np.random.seed(42)
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


# ─── Formation Top Auto-Pick ──────────────────────────────────
@app.post("/api/wells/{wid}/auto-pick-tops")
def auto_pick_tops(wid: int, data: dict, db: Session = Depends(get_db)):
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
    id = Column(Integer, primary_key=True, index=True)
    well_id = Column(Integer, ForeignKey("wells.id"), nullable=False)
    md = Column(Float, nullable=False)
    inc = Column(Float, nullable=False)
    azi = Column(Float, nullable=False)
    tvd = Column(Float, nullable=True)
    northing = Column(Float, nullable=True)
    easting = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    well = relationship("Well")


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

    # Normalize: positive = above reference, negative = below
    normalized_depth = depth - ref_depth

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
    """Compute permeability from PHIE using Timur, Coates, or SDR model."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    method = str(data.get("method", "timur")).lower()
    phie_curve = data.get("phie_curve", "PHIE")
    vsh_curve = data.get("vsh_curve", "VSH")
    grain_density = float(data.get("grain_density", 2.65))

    phie_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == phie_curve).first()
    depth_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()

    # Fallback: if PHIE not found, compute from RHOB
    if not phie_cd:
        rho_curve = data.get("rhob_curve", "RHOB")
        rho_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == rho_curve).first()
        if rho_cd:
            rho_arr = np.frombuffer(rho_cd.data_binary, dtype=np.float64).copy()
            rho_ma = grain_density
            rho_f = 1.0
            phie_arr = np.clip((rho_ma - rho_arr) / (rho_ma - rho_f), 1e-6, 0.6)
            phie_arr[np.isnan(rho_arr)] = np.nan
            phie = phie_arr
        else:
            raise HTTPException(404, f"Curve {phie_curve} not found and no RHOB for fallback")
    if not depth_cd:
        raise HTTPException(404, "Depth curve not found")

    vsh_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == vsh_curve).first()
    phie = np.frombuffer(phie_cd.data_binary, dtype=np.float64).copy() if phie_cd else phie  # phie set by RHOB fallback above
    depth = np.frombuffer(depth_cd.data_binary, dtype=np.float64).copy()
    vsh = np.frombuffer(vsh_cd.data_binary, dtype=np.float64).copy() if vsh_cd else np.full_like(phie, np.nan)

    pp = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    sw_cutoff = float(pp.sw_cutoff) if pp and pp.sw_cutoff is not None else 0.6
    sw_irr = max(0.05, min(0.95, sw_cutoff))

    phie_clip = np.clip(phie, 1e-6, 0.6)
    # BVW approximation using PHIE and Sw_irr cutoff proxy
    bvw = np.clip(phie_clip * sw_irr, 1e-6, None)
    a = float(pp.a) if pp and pp.a is not None else 4.0

    k = np.full_like(phie_clip, np.nan)
    valid = ~np.isnan(phie_clip) & (phie_clip > 0)

    if method == "timur":
        k[valid] = (10 ** 4) * (phie_clip[valid] ** 2.25) / (sw_irr ** 2)
    elif method == "coates":
        ratio = (phie_clip[valid] ** 2) * ((1 - sw_irr) / sw_irr)
        k[valid] = (ratio ** 2) * (10 ** 4)
    elif method == "sdr":
        k[valid] = a * (phie_clip[valid] ** 4) * ((1.0 / bvw[valid]) ** 2)
    else:
        raise HTTPException(400, "method must be one of: timur, coates, sdr")

    # Mild density scaling hook for professional workflows (kept bounded)
    dens_scale = max(0.8, min(1.2, grain_density / 2.65))
    k[valid] = k[valid] * dens_scale

    k_valid = k[~np.isnan(k)]
    step = max(1, len(depth) // 500)
    idx = list(range(0, len(depth), step))

    return {
        "curve_name": f"K_{method.upper()}",
        "points": int(len(k_valid)),
        "values": [round(float(k[i]), 3) if not np.isnan(k[i]) else None for i in idx],
        "depths": [round(float(depth[i]), 3) for i in idx],
        "method": method,
        "stats": {
            "min": round(float(np.min(k_valid)), 3) if len(k_valid) else None,
            "max": round(float(np.max(k_valid)), 3) if len(k_valid) else None,
            "mean": round(float(np.mean(k_valid)), 3) if len(k_valid) else None,
            "median": round(float(np.median(k_valid)), 3) if len(k_valid) else None,
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
    rxo_curve = data.get("rxo_curve", "RXO")
    phie_curve = data.get("phie_curve", "PHIE")

    rt_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == rt_curve).first()
    rxo_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == rxo_curve).first()
    phie_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == phie_curve).first()
    depth_cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic.in_(["DEPT", "DEPTH"])).first()
    if not rt_cd or not rxo_cd or not phie_cd or not depth_cd:
        raise HTTPException(404, "Required curves not found")

    rt = np.frombuffer(rt_cd.data_binary, dtype=np.float64).copy()
    rxo = np.frombuffer(rxo_cd.data_binary, dtype=np.float64).copy()
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
        raise HTTPException(404, "No deviation survey")

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


@app.get("/api/wells/{wid}/zone-stats")
def zone_stats(wid: int, db: Session = Depends(get_db)):
    """Compute petrophysics statistics per persisted zone for the latest log run."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")

    zones = (
        db.query(Zone)
        .filter(Zone.well_id == wid)
        .order_by(Zone.sort_order.asc(), Zone.id.asc())
        .all()
    )
    if not zones:
        return {
            "zones": [],
            "cutoffs": {"vsh": 0.35, "phie": 0.10, "sw": 0.60},
        }

    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")

    depth_cd = db.query(CurveData).filter(
        CurveData.log_run_id == lr.id,
        CurveData.mnemonic.in_(["DEPT", "DEPTH", "MD", "TVD"]),
    ).first()
    if not depth_cd:
        raise HTTPException(404, "Depth curve not found")

    depth = np.frombuffer(depth_cd.data_binary, dtype=np.float64).copy()

    curve_map = {}
    for mnem in ["PHIE", "SW", "VSH", "K"]:
        cd = db.query(CurveData).filter(CurveData.log_run_id == lr.id, CurveData.mnemonic == mnem).first()
        if cd:
            arr = np.frombuffer(cd.data_binary, dtype=np.float64).copy()
            if len(arr) == len(depth):
                curve_map[mnem] = arr

    pp = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    vsh_cut = float(pp.vsh_cutoff) if pp and pp.vsh_cutoff is not None else 0.35
    phie_cut = float(pp.phie_cutoff) if pp and pp.phie_cutoff is not None else 0.10
    sw_cut = float(pp.sw_cutoff) if pp and pp.sw_cutoff is not None else 0.60

    def _safe_stat(vals: np.ndarray, fn):
        valid = vals[~np.isnan(vals)]
        if len(valid) == 0:
            return None
        return round(float(fn(valid)), 6)

    out_zones = []
    for z in zones:
        if z.top_depth is None or z.bottom_depth is None:
            continue
        top = float(z.top_depth)
        bottom = float(z.bottom_depth)
        if bottom <= top:
            continue

        zone_mask = (~np.isnan(depth)) & (depth >= top) & (depth <= bottom)
        points = int(np.count_nonzero(zone_mask))
        if points == 0:
            continue

        d_zone = depth[zone_mask]
        if len(d_zone) > 1:
            d_step = np.diff(d_zone)
            d_step = d_step[np.isfinite(d_step)]
            md_step = float(np.median(np.abs(d_step))) if len(d_step) else 0.0
        else:
            md_step = 0.0

        zone_item = {
            "name": z.name,
            "top_depth": round(top, 6),
            "bottom_depth": round(bottom, 6),
            "gross_ft": round(bottom - top, 6),
            "net_pay_ft": 0.0,
            "ntg": 0.0,
            "points": points,
        }

        for mnem in ["PHIE", "SW", "VSH", "K"]:
            vals = curve_map.get(mnem)
            if vals is None:
                zone_item[f"avg_{mnem.lower()}"] = None
                zone_item[f"min_{mnem.lower()}"] = None
                zone_item[f"max_{mnem.lower()}"] = None
                zone_item[f"std_{mnem.lower()}"] = None
                continue
            zvals = vals[zone_mask]
            zone_item[f"avg_{mnem.lower()}"] = _safe_stat(zvals, np.mean)
            zone_item[f"min_{mnem.lower()}"] = _safe_stat(zvals, np.min)
            zone_item[f"max_{mnem.lower()}"] = _safe_stat(zvals, np.max)
            zone_item[f"std_{mnem.lower()}"] = _safe_stat(zvals, np.std)

        phie_vals = curve_map.get("PHIE")
        sw_vals = curve_map.get("SW")
        vsh_vals = curve_map.get("VSH")
        if phie_vals is not None and sw_vals is not None and vsh_vals is not None and md_step > 0:
            phie_z = phie_vals[zone_mask]
            sw_z = sw_vals[zone_mask]
            vsh_z = vsh_vals[zone_mask]
            pay_mask = (
                (~np.isnan(phie_z))
                & (~np.isnan(sw_z))
                & (~np.isnan(vsh_z))
                & (vsh_z < vsh_cut)
                & (phie_z > phie_cut)
                & (sw_z < sw_cut)
            )
            net_pay_ft = float(np.count_nonzero(pay_mask)) * md_step
            gross_ft = float(zone_item["gross_ft"])
            zone_item["net_pay_ft"] = round(net_pay_ft, 6)
            zone_item["ntg"] = round((net_pay_ft / gross_ft), 6) if gross_ft > 0 else 0.0

        out_zones.append(zone_item)

    return {
        "zones": out_zones,
        "cutoffs": {"vsh": vsh_cut, "phie": phie_cut, "sw": sw_cut},
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
def get_decimated_data(lr_id: int, max_points: int = 3000, db: Session = Depends(get_db)):
    """Return curve data decimated to max_points for performance."""
    lr = db.query(LogRun).filter(LogRun.id == lr_id).first()
    if not lr:
        raise HTTPException(404, "Log run not found")
    curves = db.query(CurveData).filter(CurveData.log_run_id == lr_id).all()
    result = {}
    for cd in curves:
        arr = np.frombuffer(cd.data_binary, dtype=np.float64)
        n = len(arr)
        if n <= max_points:
            result[cd.mnemonic] = arr.tolist()
        else:
            step = max(1, n // max_points)
            result[cd.mnemonic] = [float(arr[i]) for i in range(0, n, step)]
    return {"curves": result, "decimated": len(arr) > max_points, "original_points": len(arr)}


# ─── Inject audit logging into key endpoints ──────────────────
# Patch upload endpoint to log audit
_orig_upload = app.routes[:]
# We'll add audit calls inline in new code below


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
