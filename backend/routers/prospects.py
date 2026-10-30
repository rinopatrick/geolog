"""Prospect volumetrics and risking."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

try:
    from acl import require_project_access
    from database import get_db
    from models import Project, Prospect, ProspectPortfolio, SeismicLine, SeismicSurface
    from portfolio import build_portfolio
    from volumetrics import calculate_prospect
    from cell_maps import cell_posterior_maps
    from allocation import allocate_production
except ImportError:
    from backend.acl import require_project_access
    from backend.database import get_db
    from backend.models import Project, Prospect, ProspectPortfolio, SeismicLine, SeismicSurface
    from backend.portfolio import build_portfolio
    from backend.volumetrics import calculate_prospect
    from backend.cell_maps import cell_posterior_maps
    from backend.allocation import allocate_production

router = APIRouter(prefix="/api", tags=["prospects"])


def _serialized(row: Prospect, include_result: bool = True) -> dict:
    payload = {
        "id": row.id,
        "project_id": row.project_id,
        "line_id": row.line_id,
        "surface_id": row.surface_id,
        "base_surface_id": row.base_surface_id,
        "name": row.name,
        "fluid_type": row.fluid_type or "oil",
        "contact_depth_m": row.contact_depth_m,
        "grv_m3": row.grv_m3,
        "area_m2": row.area_m2,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }
    if include_result:
        try:
            payload["result"] = json.loads(row.result_json or "{}")
        except json.JSONDecodeError:
            payload["result"] = {}
    return payload


def _portfolio_serialized(row: ProspectPortfolio) -> dict:
    try:
        inputs = json.loads(row.inputs_json or "{}")
    except json.JSONDecodeError:
        inputs = {}
    try:
        result = json.loads(row.result_json or "{}")
    except json.JSONDecodeError:
        result = {}
    return {
        "id": row.id,
        "project_id": row.project_id,
        "name": row.name,
        "inputs": inputs,
        "result": result,
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


@router.post("/projects/{pid}/prospect-portfolios", status_code=201)
def create_prospect_portfolio(pid: int, data: dict, request: Request, db: Session = Depends(get_db)):
    if not db.query(Project.id).filter(Project.id == pid).first():
        raise HTTPException(404, "Project not found")
    require_project_access(db, request, pid, write=True)
    name = str(data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    query = db.query(Prospect).filter(Prospect.project_id == pid)
    ids = data.get("prospect_ids")
    if ids:
        try:
            query = query.filter(Prospect.id.in_([int(value) for value in ids]))
        except (TypeError, ValueError):
            raise HTTPException(400, "prospect_ids must be integers")
    rows = query.order_by(Prospect.id.asc()).all()
    if not rows:
        raise HTTPException(400, "no prospects selected")
    payloads = []
    for row in rows:
        try:
            result = json.loads(row.result_json or "{}")
        except json.JSONDecodeError:
            result = {}
        payloads.append({
            "id": row.id,
            "name": row.name,
            "fluid_type": row.fluid_type or "oil",
            "result": result,
        })
    try:
        result = build_portfolio(
            payloads,
            price_per_boe=data.get("price_per_boe", 60.0),
            opex_per_boe=data.get("opex_per_boe", 10.0),
            capex=data.get("capex", 0.0),
            dry_hole_cost=data.get("dry_hole_cost", 0.0),
            correlation=data.get("correlation", 0.0),
            risk_correlation=data.get("risk_correlation", 0.0),
            correlation_matrix=data.get("correlation_matrix"),
            risk_correlation_matrix=data.get("risk_correlation_matrix"),
            capex_timing=data.get("capex_timing", "success"),
            iterations=data.get("iterations", 2000),
            seed=data.get("seed"),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc))
    item = ProspectPortfolio(
        project_id=pid,
        name=name,
        inputs_json=json.dumps(result["inputs"]),
        result_json=json.dumps(result),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _portfolio_serialized(item)


@router.get("/projects/{pid}/prospect-portfolios")
def list_prospect_portfolios(pid: int, request: Request, db: Session = Depends(get_db)):
    if not db.query(Project.id).filter(Project.id == pid).first():
        raise HTTPException(404, "Project not found")
    require_project_access(db, request, pid)
    rows = (
        db.query(ProspectPortfolio)
        .filter(ProspectPortfolio.project_id == pid)
        .order_by(ProspectPortfolio.id.desc())
        .all()
    )
    return [_portfolio_serialized(row) for row in rows]


@router.get("/projects/{pid}/prospect-portfolios/{portfolio_id}")
def get_prospect_portfolio(pid: int, portfolio_id: int, request: Request, db: Session = Depends(get_db)):
    if not db.query(Project.id).filter(Project.id == pid).first():
        raise HTTPException(404, "Project not found")
    require_project_access(db, request, pid)
    item = (
        db.query(ProspectPortfolio)
        .filter(ProspectPortfolio.id == portfolio_id, ProspectPortfolio.project_id == pid)
        .first()
    )
    if not item:
        raise HTTPException(404, "Portfolio not found")
    return _portfolio_serialized(item)


@router.get("/projects/{pid}/prospect-portfolios/{portfolio_id}/export.csv")
def export_prospect_portfolio(pid: int, portfolio_id: int, request: Request, db: Session = Depends(get_db)):
    if not db.query(Project.id).filter(Project.id == pid).first():
        raise HTTPException(404, "Project not found")
    require_project_access(db, request, pid)
    item = (
        db.query(ProspectPortfolio)
        .filter(ProspectPortfolio.id == portfolio_id, ProspectPortfolio.project_id == pid)
        .first()
    )
    if not item:
        raise HTTPException(404, "Portfolio not found")
    payload = _portfolio_serialized(item)
    lines = ["rank,name,fluid_type,chance,boe_p90,boe_p50,boe_p10,net_revenue,emv"]
    for prospect in payload["result"].get("prospects", []):
        lines.append(",".join(str(prospect.get(key, "")) for key in (
            "rank", "name", "fluid_type", "chance", "boe_p90", "boe_p50", "boe_p10", "net_revenue", "emv"
        )))
    return Response(
        "\n".join(lines),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="portfolio_{item.id}.csv"'},
    )


@router.delete("/projects/{pid}/prospect-portfolios/{portfolio_id}", status_code=204)
def delete_prospect_portfolio(pid: int, portfolio_id: int, request: Request, db: Session = Depends(get_db)):
    if not db.query(Project.id).filter(Project.id == pid).first():
        raise HTTPException(404, "Project not found")
    require_project_access(db, request, pid, write=True)
    item = (
        db.query(ProspectPortfolio)
        .filter(ProspectPortfolio.id == portfolio_id, ProspectPortfolio.project_id == pid)
        .first()
    )
    if not item:
        raise HTTPException(404, "Portfolio not found")
    db.delete(item)
    db.commit()


@router.get("/projects/{pid}/prospects")
def list_prospects(pid: int, request: Request, db: Session = Depends(get_db)):
    if not db.query(Project.id).filter(Project.id == pid).first():
        raise HTTPException(404, "Project not found")
    require_project_access(db, request, pid)
    rows = (
        db.query(Prospect)
        .filter(Prospect.project_id == pid)
        .order_by(Prospect.id.desc())
        .all()
    )
    return [_serialized(row, include_result=False) for row in rows]


@router.post("/projects/{pid}/prospects", status_code=201)
def create_prospect(pid: int, data: dict, request: Request, db: Session = Depends(get_db)):
    if not db.query(Project.id).filter(Project.id == pid).first():
        raise HTTPException(404, "Project not found")
    require_project_access(db, request, pid, write=True)
    name = str(data.get("name") or "").strip()
    if not name:
        raise HTTPException(400, "name is required")
    try:
        surface_id = int(data.get("surface_id"))
    except (TypeError, ValueError):
        raise HTTPException(400, "surface_id is required")
    surface = (
        db.query(SeismicSurface)
        .join(SeismicLine, SeismicLine.id == SeismicSurface.line_id)
        .filter(SeismicSurface.id == surface_id, SeismicLine.project_id == pid)
        .first()
    )
    if not surface:
        raise HTTPException(404, "Surface not found in this project")
    if not surface.velocity_model_id or not surface.depth_grid_json or surface.depth_grid_json == "[]":
        raise HTTPException(400, "surface must be depth-converted first")
    if not surface.inline_spacing_m or not surface.crossline_spacing_m:
        raise HTTPException(400, "surface needs inline/crossline spacing")
    base_surface = None
    if data.get("base_surface_id") is not None:
        try:
            base_id = int(data["base_surface_id"])
        except (TypeError, ValueError):
            raise HTTPException(400, "base_surface_id must be an integer")
        base_surface = (
            db.query(SeismicSurface)
            .filter(SeismicSurface.id == base_id, SeismicSurface.line_id == surface.line_id)
            .first()
        )
        if not base_surface:
            raise HTTPException(404, "Base surface not found on this line")
        if not base_surface.depth_grid_json or base_surface.depth_grid_json == "[]":
            raise HTTPException(400, "base surface must be depth-converted first")
    try:
        contact = float(data.get("contact_depth_m"))
    except (TypeError, ValueError):
        raise HTTPException(400, "contact_depth_m is required")
    try:
        result = calculate_prospect(
            depth_grid=json.loads(surface.depth_grid_json),
            contact_depth_m=contact,
            inline_spacing_m=surface.inline_spacing_m,
            crossline_spacing_m=surface.crossline_spacing_m,
            inlines=json.loads(surface.inlines_json or "[]"),
            crosslines=json.loads(surface.crosslines_json or "[]"),
            base_depth_grid=json.loads(base_surface.depth_grid_json) if base_surface else None,
            porosity=data.get("porosity", 0.2),
            water_saturation=data.get("water_saturation", 0.3),
            recovery_factor=data.get("recovery_factor", 0.35),
            net_to_gross=data.get("net_to_gross", 1.0),
            bo=data.get("bo", 1.2),
            risk=data.get("risk", 1.0),
            risks=data.get("risks"),
            iterations=data.get("iterations", 1000),
            seed=data.get("seed"),
            fluid_type=data.get("fluid_type", "oil"),
            bg=data.get("bg", 0.005),
            condensate_yield=data.get("condensate_yield", 30.0),
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(400, str(exc))
    item = Prospect(
        project_id=pid,
        line_id=surface.line_id,
        surface_id=surface.id,
        base_surface_id=base_surface.id if base_surface else None,
        name=name,
        fluid_type=result["fluid_type"],
        contact_depth_m=contact,
        grv_m3=result["grv"]["grv_m3"],
        area_m2=result["grv"]["area_m2"],
        result_json=json.dumps(result),
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _serialized(item)


@router.get("/projects/{pid}/prospects/{prospect_id}")
def get_prospect(pid: int, prospect_id: int, request: Request, db: Session = Depends(get_db)):
    if not db.query(Project.id).filter(Project.id == pid).first():
        raise HTTPException(404, "Project not found")
    require_project_access(db, request, pid)
    item = (
        db.query(Prospect)
        .filter(Prospect.id == prospect_id, Prospect.project_id == pid)
        .first()
    )
    if not item:
        raise HTTPException(404, "Prospect not found")
    return _serialized(item)


@router.delete("/projects/{pid}/prospects/{prospect_id}", status_code=204)
def delete_prospect(pid: int, prospect_id: int, request: Request, db: Session = Depends(get_db)):
    if not db.query(Project.id).filter(Project.id == pid).first():
        raise HTTPException(404, "Project not found")
    require_project_access(db, request, pid, write=True)
    item = (
        db.query(Prospect)
        .filter(Prospect.id == prospect_id, Prospect.project_id == pid)
        .first()
    )
    if not item:
        raise HTTPException(404, "Prospect not found")
    db.delete(item)
    db.commit()
    return Response(status_code=204)

@router.post("/projects/{pid}/prospect-maps", status_code=200)
def prospect_maps(pid: int, data: dict, request: Request, db: Session = Depends(get_db)):
    """Per-cell P10/P50/P90 hydrocarbon column + probability for a surface."""
    if not db.query(Project.id).filter(Project.id == pid).first():
        raise HTTPException(404, "Project not found")
    require_project_access(db, request, pid)
    try:
        surface_id = int(data.get("surface_id"))
    except (TypeError, ValueError):
        raise HTTPException(400, "surface_id is required")
    surface = (
        db.query(SeismicSurface)
        .join(SeismicLine, SeismicLine.id == SeismicSurface.line_id)
        .filter(SeismicSurface.id == surface_id, SeismicLine.project_id == pid)
        .first()
    )
    if not surface:
        raise HTTPException(404, "Surface not found in this project")
    if not surface.depth_grid_json or surface.depth_grid_json == "[]":
        raise HTTPException(400, "surface must be depth-converted first")
    if not surface.inline_spacing_m or not surface.crossline_spacing_m:
        raise HTTPException(400, "surface needs inline/crossline spacing")
    base_surface = None
    if data.get("base_surface_id") is not None:
        try:
            base_id = int(data["base_surface_id"])
        except (TypeError, ValueError):
            raise HTTPException(400, "base_surface_id must be an integer")
        base_surface = (
            db.query(SeismicSurface)
            .filter(SeismicSurface.id == base_id, SeismicSurface.line_id == surface.line_id)
            .first()
        )
        if not base_surface:
            raise HTTPException(404, "Base surface not found on this line")
        if not base_surface.depth_grid_json or base_surface.depth_grid_json == "[]":
            raise HTTPException(400, "base surface must be depth-converted first")
    try:
        contact = float(data.get("contact_depth_m"))
    except (TypeError, ValueError):
        raise HTTPException(400, "contact_depth_m is required")
    iterations = data.get("iterations", 1000)
    try:
        iterations = int(iterations)
    except (TypeError, ValueError):
        raise HTTPException(400, "iterations must be an integer")
    seed = data.get("seed")
    if seed is not None:
        try:
            seed = int(seed)
        except (TypeError, ValueError):
            raise HTTPException(400, "seed must be an integer")
    try:
        maps = cell_posterior_maps(
            depth_grid=json.loads(surface.depth_grid_json),
            contact_depth_m=contact,
            inline_spacing_m=surface.inline_spacing_m,
            crossline_spacing_m=surface.crossline_spacing_m,
            porosity=data.get("porosity", 0.2),
            water_saturation=data.get("water_saturation", 0.3),
            net_to_gross=data.get("net_to_gross", 1.0),
            base_depth_grid=json.loads(base_surface.depth_grid_json) if base_surface else None,
            iterations=iterations,
            seed=seed,
        )
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        raise HTTPException(400, str(exc))
    return {
        "surface_id": surface.id,
        "base_surface_id": base_surface.id if base_surface else None,
        "inlines": json.loads(surface.inlines_json or "[]"),
        "crosslines": json.loads(surface.crosslines_json or "[]"),
        **maps,
    }

@router.post("/projects/{pid}/production-allocation", status_code=200)
def production_allocation(pid: int, data: dict, request: Request, db: Session = Depends(get_db)):
    """Split a total rate across compartments by kh transmissibility."""
    if not db.query(Project.id).filter(Project.id == pid).first():
        raise HTTPException(404, "Project not found")
    require_project_access(db, request, pid)
    try:
        total = float(data.get("total_rate_bpd"))
    except (TypeError, ValueError):
        raise HTTPException(400, "total_rate_bpd is required")
    compartments = data.get("compartments")
    if not isinstance(compartments, list) or not compartments:
        raise HTTPException(400, "compartments must be a non-empty list")
    seed = data.get("seed")
    if seed is not None:
        try:
            seed = int(seed)
        except (TypeError, ValueError):
            raise HTTPException(400, "seed must be an integer")
    # Optional: pull kh from a stored surface's compartments by key.
    surface_id = data.get("surface_id")
    if surface_id is not None:
        try:
            surface_id = int(surface_id)
        except (TypeError, ValueError):
            raise HTTPException(400, "surface_id must be an integer")
        surface = (
            db.query(SeismicSurface)
            .join(SeismicLine, SeismicLine.id == SeismicSurface.line_id)
            .filter(SeismicSurface.id == surface_id, SeismicLine.project_id == pid)
            .first()
        )
        if not surface:
            raise HTTPException(404, "Surface not found in this project")
        if not surface.compartments_json or surface.compartments_json == "{}":
            raise HTTPException(400, "surface has no compartments; build them first")
    try:
        result = allocate_production(total, compartments, seed=seed)
    except (TypeError, ValueError) as exc:
        raise HTTPException(400, str(exc))
    return result
