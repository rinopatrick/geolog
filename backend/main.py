"""GeoLog — Oil & Gas Well Log Viewer."""
from fastapi import FastAPI, Request, UploadFile, File, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy.orm import Session
import numpy as np
import json
import os

try:
    from database import engine, Base, get_db, SessionLocal
    from models import Project, Well, LogRun, CurveData, FormationTop, Annotation
    from las_parser import LASParser, CURVE_TRACKS
except ImportError:
    from backend.database import engine, Base, get_db, SessionLocal
    from backend.models import Project, Well, LogRun, CurveData, FormationTop, Annotation
    from backend.las_parser import LASParser, CURVE_TRACKS

# Create tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="GeoLog", version="2.0.0", description="Oil & Gas Well Log Viewer")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


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


# ─── Curve Metadata ───────────────────────────────────────────
@app.get("/api/curve-config")
def get_curve_config():
    """Return standard curve track configurations."""
    return CURVE_TRACKS


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
