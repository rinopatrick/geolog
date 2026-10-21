"""Borehole image assets and manual dip picks."""

from __future__ import annotations

import json
import os
import tempfile
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

try:
    from database import get_db
    from image_logs import extract_dlis_image, fit_dip, png_size, save_png_gray
    from models import DipPick, ImageAsset, LogRun, Well
    from well_state import ARTIFACT_DIR
except ImportError:
    from backend.database import get_db
    from backend.image_logs import extract_dlis_image, fit_dip, png_size, save_png_gray
    from backend.models import DipPick, ImageAsset, LogRun, Well
    from backend.well_state import ARTIFACT_DIR

router = APIRouter(prefix="/api/wells/{wid}/image-assets", tags=["image-logs"])
MAX_BYTES = 50 * 1024 * 1024
ALLOWED = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}

def _well(db: Session, wid: int) -> Well:
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")
    return well

def _asset(db: Session, wid: int, asset_id: int) -> ImageAsset:
    row = db.query(ImageAsset).filter(ImageAsset.id == asset_id, ImageAsset.well_id == wid).first()
    if not row:
        raise HTTPException(404, "Image asset not found")
    return row

def _dip(row: DipPick) -> dict:
    return {
        "id": row.id, "asset_id": row.asset_id, "depth": row.depth,
        "dip_angle": row.dip_angle, "dip_azimuth": row.dip_azimuth,
        "amplitude": row.amplitude, "r2": row.r2, "quality": row.quality,
        "method": row.method, "picked_by": row.picked_by, "approved": bool(row.approved),
        "notes": row.notes or "", "trace": json.loads(row.trace_json or "[]"),
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }

def _asset_dict(row: ImageAsset, include_dips: bool = False) -> dict:
    out = {
        "id": row.id, "well_id": row.well_id, "log_run_id": row.log_run_id,
        "image_type": row.image_type, "source": row.source,
        "width": row.width, "height": row.height,
        "depth_top": row.depth_top, "depth_bottom": row.depth_bottom,
        "azimuth_start": row.azimuth_start, "azimuth_end": row.azimuth_end,
        "borehole_radius": row.borehole_radius, "status": row.status,
        "metadata": json.loads(row.metadata_json or "{}"),
        "dips": len(row.dips or []),
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }
    if include_dips:
        out["dip_rows"] = [_dip(d) for d in sorted(row.dips, key=lambda x: x.depth)]
    return out

def _save_asset(wid: int, data: bytes, suffix: str) -> tuple[str, int, int]:
    ext = suffix.lower()
    if ext not in ALLOWED:
        raise HTTPException(400, "unsupported image extension")
    root = Path(ARTIFACT_DIR).resolve() / "images" / str(wid)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{uuid.uuid4().hex}{ext}"
    path.write_bytes(data)
    width, height = png_size(data)
    return str(path), width, height

@router.get("")
def list_assets(wid: int, db: Session = Depends(get_db)):
    _well(db, wid)
    rows = db.query(ImageAsset).filter(ImageAsset.well_id == wid).order_by(ImageAsset.depth_top).all()
    return [_asset_dict(r) for r in rows]

@router.post("", status_code=201)
async def upload_asset(
    wid: int,
    file: UploadFile = File(...),
    depth_top: float = Form(...),
    depth_bottom: float = Form(...),
    image_type: str = Form("manual"),
    source: str = Form(""),
    azimuth_start: float = Form(0.0),
    azimuth_end: float = Form(360.0),
    borehole_radius: float | None = Form(None),
    log_run_id: int | None = Form(None),
    db: Session = Depends(get_db),
):
    _well(db, wid)
    if depth_bottom <= depth_top:
        raise HTTPException(400, "depth_bottom must be greater than depth_top")
    if log_run_id is not None:
        lr = db.query(LogRun).filter(LogRun.id == log_run_id, LogRun.well_id == wid).first()
        if not lr:
            raise HTTPException(404, "Log run not found")
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty image")
    if len(content) > MAX_BYTES:
        raise HTTPException(413, "Image exceeds 50 MB")
    path, width, height = _save_asset(wid, content, Path(file.filename or "image.png").suffix or ".png")
    row = ImageAsset(
        well_id=wid, log_run_id=log_run_id, image_type=image_type, source=source,
        file_path=path, width=width, height=height, depth_top=depth_top,
        depth_bottom=depth_bottom, azimuth_start=azimuth_start, azimuth_end=azimuth_end,
        borehole_radius=borehole_radius, status="draft", metadata_json="{}",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _asset_dict(row)

@router.post("/import-dlis", status_code=201)
async def import_dlis(
    wid: int,
    file: UploadFile = File(...),
    channel: str = Form(...),
    depth_channel: str = Form("DEPT"),
    image_type: str = Form("dlis"),
    borehole_radius: float | None = Form(None),
    depth_top: float | None = Form(None),
    depth_bottom: float | None = Form(None),
    db: Session = Depends(get_db),
):
    _well(db, wid)
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty DLIS")
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".dlis")
    try:
        tmp.write(content)
        tmp.close()
        try:
            extracted = extract_dlis_image(tmp.name, channel, depth_channel)
        except Exception as exc:
            raise HTTPException(400, f"DLIS image extraction failed: {exc}")
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
    depth = extracted["depth"]
    top = float(depth_top if depth_top is not None else np_min(depth))
    bottom = float(depth_bottom if depth_bottom is not None else np_max(depth))
    if bottom <= top:
        raise HTTPException(400, "depth_bottom must be greater than depth_top")
    root = Path(ARTIFACT_DIR).resolve() / "images" / str(wid)
    path = root / f"{uuid.uuid4().hex}.png"
    width, height = save_png_gray(extracted["image"], path)
    meta = {"channel": channel, "depth_channel": depth_channel, "frame": extracted["frame"]}
    row = ImageAsset(
        well_id=wid, image_type=image_type, source=Path(file.filename or "").name,
        file_path=str(path), width=width, height=height, depth_top=top,
        depth_bottom=bottom, azimuth_start=0.0, azimuth_end=360.0,
        borehole_radius=borehole_radius, status="draft", metadata_json=json.dumps(meta),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _asset_dict(row)

def np_min(values):
    values = [float(v) for v in values if v == v]
    return min(values) if values else 0.0

def np_max(values):
    values = [float(v) for v in values if v == v]
    return max(values) if values else 0.0

@router.get("/{asset_id}")
def get_asset(wid: int, asset_id: int, db: Session = Depends(get_db)):
    _well(db, wid)
    return _asset_dict(_asset(db, wid, asset_id), include_dips=True)

@router.get("/{asset_id}/file")
def get_asset_file(wid: int, asset_id: int, db: Session = Depends(get_db)):
    _well(db, wid)
    row = _asset(db, wid, asset_id)
    path = Path(row.file_path).resolve()
    root = Path(ARTIFACT_DIR).resolve()
    if root not in path.parents or not path.exists():
        raise HTTPException(404, "Image file not found")
    return FileResponse(str(path))

@router.put("/{asset_id}")
def update_asset(wid: int, asset_id: int, data: dict, db: Session = Depends(get_db)):
    _well(db, wid)
    row = _asset(db, wid, asset_id)
    if "image_type" in data:
        row.image_type = str(data.get("image_type") or row.image_type)
    if "source" in data:
        row.source = str(data.get("source") or "")
    if "status" in data and data.get("status") in {"draft", "approved"}:
        row.status = data["status"]
    if "depth_top" in data:
        row.depth_top = float(data["depth_top"])
    if "depth_bottom" in data:
        row.depth_bottom = float(data["depth_bottom"])
    if row.depth_bottom <= row.depth_top:
        raise HTTPException(400, "depth_bottom must be greater than depth_top")
    if "borehole_radius" in data:
        value = data.get("borehole_radius")
        row.borehole_radius = float(value) if value not in (None, "") else None
    if "azimuth_start" in data:
        row.azimuth_start = float(data["azimuth_start"])
    if "azimuth_end" in data:
        row.azimuth_end = float(data["azimuth_end"])
    db.commit()
    db.refresh(row)
    return _asset_dict(row)

@router.delete("/{asset_id}", status_code=204)
def delete_asset(wid: int, asset_id: int, db: Session = Depends(get_db)):
    _well(db, wid)
    row = _asset(db, wid, asset_id)
    path = Path(row.file_path)
    db.delete(row)
    db.commit()
    try:
        path.unlink()
    except OSError:
        pass

@router.get("/{asset_id}/dips")
def list_dips(wid: int, asset_id: int, db: Session = Depends(get_db)):
    _well(db, wid)
    row = _asset(db, wid, asset_id)
    return [_dip(d) for d in sorted(row.dips, key=lambda x: x.depth)]

@router.post("/{asset_id}/dips", status_code=201)
def create_dip(wid: int, asset_id: int, data: dict, db: Session = Depends(get_db)):
    _well(db, wid)
    asset = _asset(db, wid, asset_id)
    trace = data.get("trace")
    if trace is not None:
        radius = float(data.get("borehole_radius") or asset.borehole_radius or 0.0)
        try:
            fit = fit_dip(trace, radius, float(asset.azimuth_start or 0.0))
        except (TypeError, ValueError) as exc:
            raise HTTPException(400, str(exc))
        method = "manual_trace"
        trace_json = json.dumps(trace)
    else:
        try:
            depth = float(data["depth"])
            dip_angle = float(data["dip_angle"])
            dip_azimuth = float(data["dip_azimuth"])
        except (KeyError, TypeError, ValueError):
            raise HTTPException(400, "trace or depth/dip_angle/dip_azimuth are required")
        if not (0.0 <= dip_angle <= 90.0) or not (0.0 <= dip_azimuth < 360.0):
            raise HTTPException(400, "dip_angle must be 0-90 and dip_azimuth 0-360")
        fit = {"depth": depth, "dip_angle": dip_angle, "dip_azimuth": dip_azimuth,
               "amplitude": None, "r2": None}
        method = "manual"
        trace_json = "[]"
    quality = str(data.get("quality") or ("" if fit.get("r2") is None else
                  ("good" if float(fit["r2"]) >= 0.8 else "review")))
    row = DipPick(
        asset_id=asset.id, depth=float(fit["depth"]), dip_angle=float(fit["dip_angle"]),
        dip_azimuth=float(fit["dip_azimuth"]), amplitude=fit.get("amplitude"),
        r2=fit.get("r2"), quality=quality, method=method,
        picked_by=str(data.get("picked_by") or ""), notes=str(data.get("notes") or ""),
        trace_json=trace_json,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _dip(row)

@router.post("/{asset_id}/dips/{dip_id}/approve")
def approve_dip(wid: int, asset_id: int, dip_id: int, db: Session = Depends(get_db)):
    _well(db, wid)
    asset = _asset(db, wid, asset_id)
    row = db.query(DipPick).filter(DipPick.id == dip_id, DipPick.asset_id == asset.id).first()
    if not row:
        raise HTTPException(404, "Dip pick not found")
    row.approved = True
    db.commit()
    return {"status": "ok", "id": row.id}

@router.delete("/{asset_id}/dips/{dip_id}", status_code=204)
def delete_dip(wid: int, asset_id: int, dip_id: int, db: Session = Depends(get_db)):
    _well(db, wid)
    asset = _asset(db, wid, asset_id)
    row = db.query(DipPick).filter(DipPick.id == dip_id, DipPick.asset_id == asset.id).first()
    if not row:
        raise HTTPException(404, "Dip pick not found")
    db.delete(row)
    db.commit()
