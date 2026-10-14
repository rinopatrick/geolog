"""Project-level router for GeoLog.

Covers project CRUD and the cross-well views: comparison, cross-section, strip
log, formation matrix, tops export, summary, locations, crossplot matrix,
well analogs and batch petrophysics. Extracted from backend/main.py.
"""

from __future__ import annotations

import csv
import io

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

try:
    from database import SessionLocal, get_db
    from deps import require_interpreter
    from jobs import (
        JOB_EXECUTOR,
        create_job as _create_job,
        update_job as _update_job,
        utc_now_iso as _utc_now_iso,
    )
    from models import (
        CurveData,
        FormationTop,
        LogRun,
        PetroParams,
        Project,
        Well,
        Zone,
    )
except ImportError:
    from backend.database import SessionLocal, get_db
    from backend.deps import require_interpreter
    from backend.jobs import (
        JOB_EXECUTOR,
        create_job as _create_job,
        update_job as _update_job,
        utc_now_iso as _utc_now_iso,
    )
    from backend.models import (
        CurveData,
        FormationTop,
        LogRun,
        PetroParams,
        Project,
        Well,
        Zone,
    )

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("/")
def list_projects(db: Session = Depends(get_db)):
    projects = db.query(Project).all()
    result = []
    for p in projects:
        d = {c.name: getattr(p, c.name) for c in Project.__table__.columns}
        d["well_count"] = len(p.wells)
        result.append(d)
    return result


@router.post("/", status_code=201)
def create_project(data: dict, db: Session = Depends(get_db)):
    p = Project(**data)
    db.add(p)
    db.commit()
    db.refresh(p)
    return {c.name: getattr(p, c.name) for c in Project.__table__.columns}


@router.delete("/{pid}", status_code=204)
def delete_project(pid: int, db: Session = Depends(get_db)):
    p = db.query(Project).filter(Project.id == pid).first()
    if not p:
        raise HTTPException(404, "Project not found")
    db.delete(p)
    db.commit()


@router.get("/{pid}/well-comparison")
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


@router.get("/{pid}/strip-log-data")
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


@router.get("/{pid}/cross-section")
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


@router.get("/{pid}/tops-export")
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


@router.get("/{pid}/formation-matrix")
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


@router.post("/{pid}/batch-petro")
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


@router.get("/{pid}/summary")
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


@router.get("/{pid}/well-locations")
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


@router.get("/{pid}/crossplot-matrix")
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


@router.post("/{pid}/batch-petro-async", status_code=202)
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


@router.get("/{pid}/well-analogs")
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

