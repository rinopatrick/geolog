"""Core, SCAL, flow-unit and saturation-height router."""

from __future__ import annotations

import csv
import hashlib
import io
import json
from typing import Any

import numpy as np
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

try:
    from database import get_db
    from models import (
        CapillaryPressure,
        Contact,
        CoreDataset,
        CoreMeasurement,
        CorePhoto,
        CorePlug,
        FlowUnit,
        LogRun,
        RelativePerm,
        RockType,
        SaturationHeightModel,
        ThinSection,
        Well,
    )
    from semantics import apply_run_semantics
except ImportError:
    from backend.database import get_db
    from backend.models import (
        CapillaryPressure,
        Contact,
        CoreDataset,
        CoreMeasurement,
        CorePhoto,
        CorePlug,
        FlowUnit,
        LogRun,
        RelativePerm,
        RockType,
        SaturationHeightModel,
        ThinSection,
        Well,
    )
    from backend.semantics import apply_run_semantics

router = APIRouter(prefix="/api/wells/{wid}", tags=["core"])

def _well(db: Session, wid: int) -> Well:
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")
    return well

def _dataset(db: Session, wid: int, dataset_id: int | None = None, create: bool = False) -> CoreDataset | None:
    if dataset_id is not None:
        ds = db.query(CoreDataset).filter(CoreDataset.id == dataset_id, CoreDataset.well_id == wid).first()
        if not ds:
            raise HTTPException(404, "Core dataset not found")
        return ds
    ds = (
        db.query(CoreDataset)
        .filter(CoreDataset.well_id == wid, CoreDataset.status == "draft")
        .order_by(CoreDataset.version.desc())
        .first()
    )
    if ds is None and create:
        latest = (
            db.query(CoreDataset)
            .filter(CoreDataset.well_id == wid)
            .order_by(CoreDataset.version.desc())
            .first()
        )
        ds = CoreDataset(well_id=wid, version=(latest.version + 1) if latest else 1, status="draft", source="api")
        db.add(ds)
        db.flush()
    return ds

def _plug(db: Session, wid: int, plug_id: int) -> CorePlug:
    plug = db.query(CorePlug).filter(CorePlug.id == plug_id, CorePlug.well_id == wid).first()
    if not plug:
        raise HTTPException(404, "Core plug not found")
    return plug

def _draft_guard(ds: CoreDataset | None):
    if ds is not None and ds.status != "draft":
        raise HTTPException(423, "Core dataset is approved and immutable")

def _float(value, key: str, required: bool = False):
    if value is None or value == "":
        if required:
            raise HTTPException(400, f"{key} is required")
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        raise HTTPException(400, f"{key} must be a number")

def _points(value: Any, key: str, width: int) -> list[list[float]]:
    if not isinstance(value, list):
        raise HTTPException(400, f"{key} must be a list")
    out = []
    for i, point in enumerate(value):
        if isinstance(point, dict):
            point = list(point.values())
        if not isinstance(point, (list, tuple)) or len(point) != width:
            raise HTTPException(400, f"{key}[{i}] must have {width} numbers")
        try:
            out.append([float(v) for v in point])
        except (TypeError, ValueError):
            raise HTTPException(400, f"{key}[{i}] must be numeric")
    return out

def _plug_dict(plug: CorePlug) -> dict:
    return {
        "id": plug.id,
        "dataset_id": plug.dataset_id,
        "well_id": plug.well_id,
        "rock_type_id": plug.rock_type_id,
        "plug_name": plug.plug_name,
        "depth_md": plug.depth_md,
        "depth_tvd": plug.depth_tvd,
        "formation": plug.formation or "",
        "lithology": plug.lithology or "",
        "porosity": plug.porosity,
        "perm_air": plug.perm_air,
        "perm_klin": plug.perm_klin,
        "grain_density": plug.grain_density,
        "fluid_saturation": plug.fluid_saturation,
        "plug_type": plug.plug_type or "",
        "source": plug.source or "",
        "notes": plug.notes or "",
        "measurements": len(plug.measurements or []),
        "capillary_pressure": len(plug.capillary_pressure or []),
        "relative_perm": len(plug.relative_perm or []),
        "photos": len(plug.photos or []),
        "thin_sections": len(plug.thin_sections or []),
    }

def _apply_plug_fields(plug: CorePlug, data: dict):
    for key in ("plug_name", "formation", "lithology", "plug_type", "source", "notes"):
        if key in data and data[key] is not None:
            setattr(plug, key, str(data[key]))
    if "depth_md" in data:
        plug.depth_md = _float(data.get("depth_md"), "depth_md", True)
    for key in ("depth_tvd", "porosity", "perm_air", "perm_klin", "grain_density", "fluid_saturation"):
        if key in data:
            setattr(plug, key, _float(data.get(key), key))
    if "rock_type_id" in data:
        plug.rock_type_id = int(data["rock_type_id"]) if data["rock_type_id"] not in (None, "") else None

@router.get("/core/datasets")
def list_core_datasets(wid: int, db: Session = Depends(get_db)):
    _well(db, wid)
    rows = db.query(CoreDataset).filter(CoreDataset.well_id == wid).order_by(CoreDataset.version.desc()).all()
    return [
        {
            "id": r.id, "version": r.version, "status": r.status, "source": r.source,
            "imported_at": r.imported_at.isoformat() if r.imported_at else "",
            "approved_at": r.approved_at.isoformat() if r.approved_at else "",
            "input_hash": r.input_hash, "plugs": len(r.plugs or []),
        }
        for r in rows
    ]

@router.post("/core/datasets/{dataset_id}/approve")
def approve_core_dataset(wid: int, dataset_id: int, db: Session = Depends(get_db)):
    _well(db, wid)
    ds = _dataset(db, wid, dataset_id)
    ds.status = "approved"
    db.commit()
    return {"status": "ok", "dataset_id": ds.id, "version": ds.version}

@router.get("/core/plugs")
def list_core_plugs(wid: int, dataset_id: int = None, db: Session = Depends(get_db)):
    _well(db, wid)
    q = db.query(CorePlug).filter(CorePlug.well_id == wid)
    if dataset_id is not None:
        q = q.filter(CorePlug.dataset_id == dataset_id)
    return [_plug_dict(p) for p in q.order_by(CorePlug.depth_md.asc()).all()]

@router.post("/core/plugs", status_code=201)
def create_core_plug(wid: int, data: dict, db: Session = Depends(get_db)):
    _well(db, wid)
    ds = _dataset(db, wid, data.get("dataset_id"), create=True)
    _draft_guard(ds)
    plug = CorePlug(
        dataset_id=ds.id,
        well_id=wid,
        plug_name=str(data.get("plug_name") or "").strip(),
        depth_md=0.0,
        depth_tvd=None,
    )
    if not plug.plug_name:
        raise HTTPException(400, "plug_name is required")
    _apply_plug_fields(plug, data)
    if data.get("depth_md") is None:
        raise HTTPException(400, "depth_md is required")
    existing = db.query(CorePlug).filter(
        CorePlug.well_id == wid, CorePlug.plug_name == plug.plug_name, CorePlug.depth_md == plug.depth_md
    ).first()
    if existing:
        raise HTTPException(409, "Core plug already exists at this name/depth")
    db.add(plug)
    db.commit()
    db.refresh(plug)
    return _plug_dict(plug)

@router.get("/core/plugs/{plug_id}")
def get_core_plug(wid: int, plug_id: int, db: Session = Depends(get_db)):
    _well(db, wid)
    plug = _plug(db, wid, plug_id)
    out = _plug_dict(plug)
    out["measurement_rows"] = [
        {"id": m.id, "type": m.measurement_type, "method": m.method, "value": m.value, "unit": m.unit}
        for m in (plug.measurements or [])
    ]
    out["pc_rows"] = [
        {"id": p.id, "test_type": p.test_type, "sigma": p.sigma, "cos_theta": p.cos_theta,
         "points": json.loads(p.points_json or "[]")}
        for p in (plug.capillary_pressure or [])
    ]
    return out

@router.put("/core/plugs/{plug_id}")
def update_core_plug(wid: int, plug_id: int, data: dict, db: Session = Depends(get_db)):
    _well(db, wid)
    plug = _plug(db, wid, plug_id)
    _draft_guard(plug.dataset)
    _apply_plug_fields(plug, data)
    db.commit()
    db.refresh(plug)
    return _plug_dict(plug)

@router.delete("/core/plugs/{plug_id}", status_code=204)
def delete_core_plug(wid: int, plug_id: int, db: Session = Depends(get_db)):
    _well(db, wid)
    plug = _plug(db, wid, plug_id)
    _draft_guard(plug.dataset)
    db.delete(plug)
    db.commit()

@router.post("/core/plugs/{plug_id}/measurements", status_code=201)
def add_core_measurement(wid: int, plug_id: int, data: dict, db: Session = Depends(get_db)):
    _well(db, wid)
    plug = _plug(db, wid, plug_id)
    _draft_guard(plug.dataset)
    row = CoreMeasurement(
        plug_id=plug.id,
        measurement_type=str(data.get("measurement_type") or "").strip(),
        method=str(data.get("method") or ""),
        value=_float(data.get("value"), "value", True),
        unit=str(data.get("unit") or ""),
        quality=str(data.get("quality") or ""),
        lab=str(data.get("lab") or ""),
        sample_date=str(data.get("sample_date") or ""),
    )
    if not row.measurement_type:
        raise HTTPException(400, "measurement_type is required")
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "plug_id": row.plug_id, "type": row.measurement_type, "value": row.value}

@router.post("/core/plugs/{plug_id}/capillary-pressure", status_code=201)
def add_capillary_pressure(wid: int, plug_id: int, data: dict, db: Session = Depends(get_db)):
    _well(db, wid)
    plug = _plug(db, wid, plug_id)
    _draft_guard(plug.dataset)
    points = _points(data.get("points"), "points", 2)
    if len(points) < 2:
        raise HTTPException(400, "at least two Pc/Sw points are required")
    row = CapillaryPressure(
        plug_id=plug.id,
        test_type=str(data.get("test_type") or "drainage"),
        sigma=float(data.get("sigma", 72.0) or 72.0),
        cos_theta=float(data.get("cos_theta", 1.0) or 1.0),
        points_json=json.dumps(points),
        quality=str(data.get("quality") or ""),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "plug_id": row.plug_id, "points": len(points)}

@router.post("/core/plugs/{plug_id}/relative-perm", status_code=201)
def add_relative_perm(wid: int, plug_id: int, data: dict, db: Session = Depends(get_db)):
    _well(db, wid)
    plug = _plug(db, wid, plug_id)
    _draft_guard(plug.dataset)
    points = _points(data.get("points"), "points", 3)
    row = RelativePerm(
        plug_id=plug.id,
        points_json=json.dumps(points),
        method=str(data.get("method") or ""),
        quality=str(data.get("quality") or ""),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "plug_id": row.plug_id, "points": len(points)}

@router.post("/core/plugs/{plug_id}/photos", status_code=201)
def add_core_photo(wid: int, plug_id: int, data: dict, db: Session = Depends(get_db)):
    _well(db, wid)
    plug = _plug(db, wid, plug_id)
    _draft_guard(plug.dataset)
    path = str(data.get("file_path") or "").strip()
    if not path:
        raise HTTPException(400, "file_path is required")
    row = CorePhoto(
        plug_id=plug.id, file_path=path, caption=str(data.get("caption") or ""),
        scale=str(data.get("scale") or ""), orientation=str(data.get("orientation") or ""),
        checksum=str(data.get("checksum") or ""),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "plug_id": row.plug_id, "file_path": row.file_path}

@router.post("/core/plugs/{plug_id}/thin-sections", status_code=201)
def add_thin_section(wid: int, plug_id: int, data: dict, db: Session = Depends(get_db)):
    _well(db, wid)
    plug = _plug(db, wid, plug_id)
    _draft_guard(plug.dataset)
    path = str(data.get("file_path") or "").strip()
    if not path:
        raise HTTPException(400, "file_path is required")
    row = ThinSection(
        plug_id=plug.id, file_path=path, caption=str(data.get("caption") or ""),
        description=str(data.get("description") or ""), checksum=str(data.get("checksum") or ""),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "plug_id": row.plug_id, "file_path": row.file_path}

@router.post("/core/import")
async def import_core_csv(
    wid: int,
    file: UploadFile = File(...),
    dry_run: bool = False,
    update: bool = False,
    db: Session = Depends(get_db),
):
    _well(db, wid)
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")
    text = content.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    rows = list(reader)
    if not rows:
        raise HTTPException(400, "CSV has no data rows")

    ds = None if dry_run else _dataset(db, wid, create=True)
    imported = 0
    conflicts = []
    errors = []
    for line_no, raw in enumerate(rows, start=2):
        row = {(k or "").strip().lower(): v for k, v in raw.items()}
        name = str(row.get("plug_name") or row.get("plug") or "").strip()
        depth = _float(row.get("depth_md") or row.get("depth"), "depth_md")
        if not name or depth is None:
            errors.append({"line": line_no, "error": "plug_name and depth_md are required"})
            continue
        existing = db.query(CorePlug).filter(
            CorePlug.well_id == wid, CorePlug.plug_name == name, CorePlug.depth_md == depth
        ).first()
        if existing and not update:
            conflicts.append({"line": line_no, "plug_name": name, "depth_md": depth, "action": "skipped"})
            continue
        if dry_run:
            imported += 1
            continue
        _draft_guard(ds)
        plug = existing or CorePlug(dataset_id=ds.id, well_id=wid, plug_name=name, depth_md=depth)
        if not existing:
            db.add(plug)
        _apply_plug_fields(plug, {
            "plug_name": name, "depth_md": depth,
            "depth_tvd": row.get("depth_tvd"),
            "formation": row.get("formation"), "lithology": row.get("lithology"),
            "porosity": row.get("porosity"), "perm_air": row.get("perm_air"),
            "perm_klin": row.get("perm_klin"), "grain_density": row.get("grain_density"),
            "fluid_saturation": row.get("fluid_saturation"),
            "plug_type": row.get("plug_type"), "source": row.get("source"), "notes": row.get("notes"),
        })
        imported += 1

    if dry_run:
        db.rollback()
        return {"dry_run": True, "rows": len(rows), "would_import": imported,
                "conflicts": conflicts, "errors": errors}
    ds.input_hash = hashlib.sha256(content).hexdigest()
    db.commit()
    return {"dry_run": False, "dataset_id": ds.id, "version": ds.version, "imported": imported,
            "conflicts": conflicts, "errors": errors}

@router.get("/core/rock-types")
def list_rock_types(wid: int, db: Session = Depends(get_db)):
    _well(db, wid)
    return [
        {"id": r.id, "name": r.name, "color": r.color, "description": r.description}
        for r in db.query(RockType).filter(RockType.well_id == wid).all()
    ]

@router.post("/core/rock-types", status_code=201)
def create_rock_type(wid: int, data: dict, db: Session = Depends(get_db)):
    _well(db, wid)
    name = str(data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    row = RockType(well_id=wid, name=name, color=str(data.get("color") or "#58a6ff"),
                   description=str(data.get("description") or ""))
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "name": row.name, "color": row.color}

@router.get("/core/contacts")
def list_contacts(wid: int, db: Session = Depends(get_db)):
    _well(db, wid)
    return [
        {"id": c.id, "zone_id": c.zone_id, "type": c.contact_type, "depth": c.depth,
         "source": c.source, "confidence": c.confidence}
        for c in db.query(Contact).filter(Contact.well_id == wid).order_by(Contact.depth).all()
    ]

@router.post("/core/contacts", status_code=201)
def create_contact(wid: int, data: dict, db: Session = Depends(get_db)):
    _well(db, wid)
    ctype = str(data.get("contact_type") or data.get("type") or "FWL").upper()
    if ctype not in {"FWL", "OWC", "GOC"}:
        raise HTTPException(400, "contact_type must be FWL, OWC or GOC")
    row = Contact(well_id=wid, zone_id=data.get("zone_id"), contact_type=ctype,
                  depth=_float(data.get("depth"), "depth", True),
                  source=str(data.get("source") or ""), confidence=str(data.get("confidence") or ""))
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "type": row.contact_type, "depth": row.depth}

@router.delete("/core/contacts/{contact_id}", status_code=204)
def delete_contact(wid: int, contact_id: int, db: Session = Depends(get_db)):
    _well(db, wid)
    row = db.query(Contact).filter(Contact.id == contact_id, Contact.well_id == wid).first()
    if not row:
        raise HTTPException(404, "Contact not found")
    db.delete(row)
    db.commit()

@router.get("/core/flow-units")
def list_flow_units(wid: int, db: Session = Depends(get_db)):
    _well(db, wid)
    return [
        {"id": u.id, "version": u.version, "cluster_index": u.cluster_index,
         "fzi_min": u.fzi_min, "fzi_max": u.fzi_max, "stats": json.loads(u.stats_json or "{}")}
        for u in db.query(FlowUnit).filter(FlowUnit.well_id == wid).order_by(FlowUnit.version.desc(), FlowUnit.cluster_index).all()
    ]

@router.post("/core/flow-units/cluster")
def cluster_flow_units(wid: int, data: dict, db: Session = Depends(get_db)):
    _well(db, wid)
    k = max(2, min(int(data.get("k", 3) or 3), 10))
    plugs = db.query(CorePlug).filter(CorePlug.well_id == wid).all()
    values = []
    for p in plugs:
        phi = float(p.porosity) if p.porosity else None
        perm = float(p.perm_air) if p.perm_air else None
        if not phi or not perm or phi <= 0 or phi >= 1 or perm <= 0:
            continue
        fzi = 0.0314 * np.sqrt(perm / phi) / (phi / (1.0 - phi))
        if np.isfinite(fzi) and fzi > 0:
            values.append((p, fzi))
    if len(values) < k:
        raise HTTPException(400, f"need at least {k} plugs with positive porosity and perm_air")
    values.sort(key=lambda item: item[1])
    groups = [(0, len(values))]
    while len(groups) < k:
        best = None
        for gi, (a, b) in enumerate(groups):
            if b - a < 2:
                continue
            for i in range(a + 1, b):
                gap = np.log(values[i][1]) - np.log(values[i - 1][1])
                if best is None or gap > best[0]:
                    best = (gap, gi, i)
        if best is None:
            break
        _, gi, split = best
        a, b = groups[gi]
        groups[gi:gi + 1] = [(a, split), (split, b)]

    latest = db.query(FlowUnit).filter(FlowUnit.well_id == wid).order_by(FlowUnit.version.desc()).first()
    version = (latest.version + 1) if latest else 1
    created = []
    for idx, (a, b) in enumerate(groups):
        chunk = [item[1] for item in values[a:b]]
        row = FlowUnit(
            well_id=wid, version=version, cluster_index=idx,
            fzi_min=float(min(chunk)), fzi_max=float(max(chunk)),
            stats_json=json.dumps({"count": len(chunk), "mean": float(np.mean(chunk)),
                                   "median": float(np.median(chunk))}),
        )
        db.add(row)
        created.append({"cluster_index": idx, "count": len(chunk),
                        "fzi_min": row.fzi_min, "fzi_max": row.fzi_max})
    db.commit()
    return {"version": version, "k": len(groups), "clusters": created}

def _model_params(row: SaturationHeightModel) -> dict:
    return json.loads(row.parameters_json or "{}")

@router.post("/core/saturation-height/fit")
def fit_saturation_height(wid: int, data: dict, db: Session = Depends(get_db)):
    _well(db, wid)
    model_type = str(data.get("model_type") or "j_function").lower()
    if model_type != "j_function":
        raise HTTPException(400, "only j_function is implemented")
    rock_type_id = data.get("rock_type_id")
    q = (
        db.query(CapillaryPressure)
        .join(CorePlug, CapillaryPressure.plug_id == CorePlug.id)
        .filter(CorePlug.well_id == wid)
    )
    if rock_type_id is not None:
        q = q.filter(CorePlug.rock_type_id == int(rock_type_id))
    rows = q.all()
    if not rows:
        raise HTTPException(400, "no capillary-pressure data for this selection")
    xs, ys = [], []
    for row in rows:
        plug = db.query(CorePlug).filter(CorePlug.id == row.plug_id).first()
        if not plug or not plug.porosity or not plug.perm_air or plug.porosity <= 0 or plug.perm_air <= 0:
            continue
        sigma = float(row.sigma or 72.0)
        cos_theta = float(row.cos_theta or 1.0)
        for point in json.loads(row.points_json or "[]"):
            try:
                pc, sw = float(point[0]), float(point[1])
            except (TypeError, ValueError, IndexError):
                continue
            if pc <= 0 or sw <= 0 or sw >= 1:
                continue
            j = (pc * np.sqrt(plug.perm_air / plug.porosity)) / max(sigma * cos_theta, 1e-9)
            if j > 0:
                xs.append(np.log10(j))
                ys.append(np.log10(sw))
    if len(xs) < 3:
        raise HTTPException(400, "not enough valid Pc/Sw points")
    slope, intercept = np.polyfit(np.array(xs), np.array(ys), 1)
    predicted = slope * np.array(xs) + intercept
    ss_res = float(np.sum((np.array(ys) - predicted) ** 2))
    ss_tot = float(np.sum((np.array(ys) - np.mean(ys)) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    params = {"a": float(10 ** intercept), "b": float(slope)}
    latest = db.query(SaturationHeightModel).filter(SaturationHeightModel.well_id == wid).order_by(SaturationHeightModel.version.desc()).first()
    version = (latest.version + 1) if latest else 1
    payload = {"model_type": model_type, "rock_type_id": rock_type_id, "params": params, "n": len(xs)}
    row = SaturationHeightModel(
        well_id=wid, rock_type_id=int(rock_type_id) if rock_type_id is not None else None,
        model_type=model_type, version=version, status="draft",
        parameters_json=json.dumps(params), r2=float(r2), residual=float(ss_res),
        input_hash=hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest(),
        contact_id=data.get("contact_id"), created_by="api",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "model_type": model_type, "version": version, "parameters": params,
            "r2": row.r2, "residual": row.residual, "points": len(xs)}

@router.get("/core/saturation-height/models")
def list_saturation_height_models(wid: int, db: Session = Depends(get_db)):
    _well(db, wid)
    rows = db.query(SaturationHeightModel).filter(SaturationHeightModel.well_id == wid).order_by(SaturationHeightModel.version.desc()).all()
    return [
        {"id": r.id, "model_type": r.model_type, "version": r.version, "status": r.status,
         "parameters": _model_params(r), "r2": r.r2, "residual": r.residual,
         "contact_id": r.contact_id}
        for r in rows
    ]

@router.post("/core/saturation-height/models/{model_id}/approve")
def approve_saturation_height(wid: int, model_id: int, db: Session = Depends(get_db)):
    _well(db, wid)
    row = db.query(SaturationHeightModel).filter(
        SaturationHeightModel.id == model_id, SaturationHeightModel.well_id == wid
    ).first()
    if not row:
        raise HTTPException(404, "Saturation-height model not found")
    row.status = "approved"
    db.commit()
    return {"status": "ok", "id": row.id}

@router.post("/core/saturation-height/apply")
def apply_saturation_height(wid: int, data: dict, db: Session = Depends(get_db)):
    _well(db, wid)
    model = db.query(SaturationHeightModel).filter(
        SaturationHeightModel.id == data.get("model_id"), SaturationHeightModel.well_id == wid
    ).first()
    if not model:
        raise HTTPException(404, "Saturation-height model not found")
    contact = db.query(Contact).filter(Contact.id == model.contact_id).first() if model.contact_id else None
    if contact is None:
        contact = db.query(Contact).filter(Contact.well_id == wid).order_by(Contact.depth.desc()).first()
    if contact is None:
        raise HTTPException(400, "a contact/FWL is required")
    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.num_points.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run")
    sem = apply_run_semantics(db, lr, as_arrays=True)
    depth = np.asarray(sem["depth"], dtype=np.float64)
    by_name = {}
    for meta in sem["metadata"]["aliases"]:
        arr = sem["curves"].get(meta["name"])
        if arr is not None:
            by_name[str(meta["name"]).upper()] = arr
            by_name[str(meta["raw"]).upper()] = arr
    phie = by_name.get("PHIE")
    if phie is None:
        phie = by_name.get("PHIT")
    perm = by_name.get("PERM")
    if perm is None:
        perm = by_name.get("K")
    if phie is None or perm is None:
        raise HTTPException(400, "PHIE/PHIT and PERM curves are required")
    n = min(len(depth), len(phie), len(perm))
    depth, phie, perm = depth[:n], np.asarray(phie[:n], dtype=float), np.asarray(perm[:n], dtype=float)
    params = _model_params(model)
    height = np.maximum(float(contact.depth) - depth, 0.0)
    pc = height * float(data.get("water_gradient", 0.433) or 0.433)
    sigma_cos = 72.0
    with np.errstate(divide="ignore", invalid="ignore"):
        j = (pc * np.sqrt(np.clip(perm, 1e-12, None) / np.clip(phie, 1e-6, 1.0))) / sigma_cos
        sw = float(params.get("a", 1.0)) * np.power(np.clip(j, 1e-12, None), float(params.get("b", 1.0)))
    sw = np.clip(sw, 0.0, 1.0)
    return {
        "model_id": model.id, "contact_id": contact.id, "contact_depth": contact.depth,
        "depth": [round(float(v), 4) for v in depth],
        "sw": [None if not np.isfinite(v) else round(float(v), 6) for v in sw],
        "params": params,
    }
