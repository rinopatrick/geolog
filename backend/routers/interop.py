"""WITSML / OSDU interoperability endpoints (read-first)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

try:
    from database import get_db
    import interop
    from models import Well
except ImportError:
    from backend.database import get_db
    from backend import interop
    from backend.models import Well

router = APIRouter(prefix="/api/interop", tags=["interop"])

def _config_summary() -> dict:
    try:
        w = interop.witsml_config()
        witsml = {"configured": True, "url": w["url"], "version": "1.4.1.1",
                  "auth": "token" if w["token"] else ("basic" if w["user"] else "none"),
                  "verify_tls": w["verify_tls"]}
    except RuntimeError:
        witsml = {"configured": False, "version": "1.4.1.1"}
    try:
        o = interop.osdu_config()
        osdu = {"configured": True, "url": o["url"], "partition": o["partition"],
                "auth": bool(o["token"]), "path": o["wellbores_path"]}
    except RuntimeError:
        osdu = {"configured": False}
    return {"witsml": witsml, "osdu": osdu}

@router.get("/config")
def config():
    return _config_summary()

@router.post("/witsml/test")
def witsml_test():
    try:
        return interop.witsml_test()
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"WITSML connection failed: {exc}")

@router.post("/witsml/pull")
def witsml_pull(
    project_id: int = Query(...),
    object_type: str = Query("well"),
    name: str = Query(""),
    well_id: int | None = Query(None),
    import_curves: bool = Query(True),
    db: Session = Depends(get_db),
):
    kind = (object_type or "well").lower()
    if kind not in {"well", "log", "both"}:
        raise HTTPException(400, "object_type must be well, log or both")
    report = {"witsml_version": "1.4.1.1", "wells": [], "logs": []}
    try:
        if kind in {"well", "both"}:
            xml = interop.witsml_query("well", name)
            for payload in interop.parse_witsml_wells(xml):
                well, created = interop.upsert_well(db, project_id, payload, "witsml")
                report["wells"].append({"id": well.id, "name": well.name,
                                        "created": created, "uwi": well.uwi})
            db.commit()
        if kind in {"log", "both"}:
            xml = interop.witsml_query("log", name)
            logs = interop.parse_witsml_logs(xml)
            by_name = {w["name"]: w["id"] for w in report["wells"]}
            for log in logs:
                if well_id is not None:
                    well = db.query(Well).filter(Well.id == well_id).first()
                else:
                    wid = by_name.get(log.get("well_name") or "")
                    if wid is None and name:
                        found = db.query(Well).filter(Well.name == name).first()
                        wid = found.id if found else None
                    well = db.query(Well).filter(Well.id == wid).first() if wid else None
                if well is None:
                    report["logs"].append({"name": log["name"], "status": "well_not_found"})
                    continue
                report["logs"].extend(interop.import_witsml_logs(db, well, [log], import_curves))
            db.commit()
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(502, str(exc))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))
    return report

@router.post("/osdu/test")
def osdu_test():
    try:
        return interop.osdu_test()
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"OSDU connection failed: {exc}")

@router.post("/osdu/pull")
def osdu_pull(project_id: int = Query(...), limit: int = Query(100),
              db: Session = Depends(get_db)):
    try:
        return interop.osdu_pull_wells(db, project_id, limit)
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(502, str(exc))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))



@router.post("/osdu/pull-logs")
def osdu_pull_logs(well_id: int = Query(...), wellbore_id: str | None = Query(None),
                   limit: int = Query(100), db: Session = Depends(get_db)):
    well = db.query(Well).filter(Well.id == well_id).first()
    if not well:
        raise HTTPException(404, "Well not found")
    ident = (wellbore_id or well.uwi or "").strip()
    if not ident:
        raise HTTPException(400, "wellbore_id is required when the well has no UWI")
    try:
        return interop.osdu_pull_logs(db, well, ident, limit)
    except RuntimeError as exc:
        db.rollback()
        raise HTTPException(502, str(exc))
    except ValueError as exc:
        db.rollback()
        raise HTTPException(400, str(exc))

@router.post("/osdu/push/wells/{wid}")
def osdu_push_well(wid: int, db: Session = Depends(get_db)):
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")
    try:
        return interop.osdu_push_well(db, well)
    except RuntimeError as exc:
        raise HTTPException(400, str(exc))
    except Exception as exc:
        raise HTTPException(502, f"OSDU push failed: {exc}")
