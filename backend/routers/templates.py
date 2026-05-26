"""Template Workflow router for GeoLog."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import math
import json
import os

try:
    from database import get_db
    from models import Well, LogRun, PetroParams
except ImportError:
    from backend.database import get_db
    from backend.models import Well, LogRun, PetroParams

router = APIRouter(prefix="/api", tags=["templates"])
LOCK_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "artifacts", "locks.json")


def _template_locked(wid: int) -> bool:
    if not os.path.exists(LOCK_FILE):
        return False
    try:
        with open(LOCK_FILE, "r", encoding="utf-8") as f:
            locks = json.load(f)
        row = locks.get(str(wid), {}) if isinstance(locks, dict) else {}
        tlock = row.get("template_lock") if isinstance(row, dict) else None
        return bool(isinstance(tlock, dict) and tlock.get("locked"))
    except Exception:
        return False

# ── Template Database ─────────────────────────────────────────
TEMPLATE_DB = [
    {
        "name": "Sandstone Standard",
        "description": "Balanced clean-sand default for conventional clastics.",
        "reservoir_type": "clastic",
        "params": {"saturation_model": "archie", "a": 1.0, "m": 2.0, "n": 2.0, "rw": 0.08},
        "recommended_cutoffs": {"vsh_cutoff": 0.4, "phie_cutoff": 0.1, "sw_cutoff": 0.6},
        "suggested_rw": 0.08,
        "log_track_layout": ["GR", "RT", "NPHI", "RHOB", "DT", "VSH", "PHIE", "SW"],
    },
    {
        "name": "Carbonate",
        "description": "Conservative carbonate interpretation with tighter shale screening.",
        "reservoir_type": "carbonate",
        "params": {"saturation_model": "archie", "a": 1.0, "m": 2.0, "n": 2.0, "rw": 0.05},
        "recommended_cutoffs": {"vsh_cutoff": 0.3, "phie_cutoff": 0.05, "sw_cutoff": 0.5},
        "suggested_rw": 0.05,
        "log_track_layout": ["GR", "PEF", "RHOB", "NPHI", "RT", "PHIE", "SW"],
    },
    {
        "name": "Shale Gas",
        "description": "Lower-porosity unconventional shale gas workflow baseline.",
        "reservoir_type": "unconventional",
        "params": {"saturation_model": "simandoux", "a": 1.0, "m": 1.8, "n": 1.8, "rw": 0.12},
        "recommended_cutoffs": {"vsh_cutoff": 0.6, "phie_cutoff": 0.02, "sw_cutoff": 0.4},
        "suggested_rw": 0.12,
        "log_track_layout": ["GR", "RT", "RHOB", "NPHI", "DT", "TOC_PROXY", "SW"],
    },
    {
        "name": "Deepwater Turbidite",
        "description": "Deepwater clastic setting tuned for variable lamination and pay continuity.",
        "reservoir_type": "clastic",
        "params": {"saturation_model": "archie", "a": 0.8, "m": 2.2, "n": 2.2, "rw": 0.09},
        "recommended_cutoffs": {"vsh_cutoff": 0.35, "phie_cutoff": 0.08, "sw_cutoff": 0.65},
        "suggested_rw": 0.09,
        "log_track_layout": ["GR", "RT", "NPHI", "RHOB", "DT", "VSH", "PHIE", "SW"],
    },
    {
        "name": "Tight Gas Sand",
        "description": "Tight-gas sand screening with stricter porosity and water saturation limits.",
        "reservoir_type": "unconventional",
        "params": {"saturation_model": "archie", "a": 1.0, "m": 2.5, "n": 2.0, "rw": 0.07},
        "recommended_cutoffs": {"vsh_cutoff": 0.25, "phie_cutoff": 0.03, "sw_cutoff": 0.45},
        "suggested_rw": 0.07,
        "log_track_layout": ["GR", "RT", "NPHI", "RHOB", "DT", "PHIE", "SW"],
    },
    {
        "name": "Shaly Sand",
        "description": "Simandoux-based workflow for shaly sandstone reservoirs with moderate clay content.",
        "reservoir_type": "clastic",
        "params": {"saturation_model": "simandoux", "a": 1.0, "m": 1.8, "n": 2.0, "rw": 0.10},
        "recommended_cutoffs": {"vsh_cutoff": 0.45, "phie_cutoff": 0.08, "sw_cutoff": 0.55},
        "suggested_rw": 0.10,
        "log_track_layout": ["GR", "RT", "NPHI", "RHOB", "DT", "VSH", "PHIE", "SW"],
    },
]


def _sanitize(v):
    if v is None:
        return None
    if isinstance(v, float):
        return None if (math.isnan(v) or math.isinf(v)) else v
    return v


@router.get("/templates")
def list_templates():
    """Return all available templates."""
    return {"templates": TEMPLATE_DB}


@router.get("/templates/{name}")
def get_template(name: str):
    """Return a single template by name."""
    for t in TEMPLATE_DB:
        if t["name"].lower() == name.lower().replace("-", " ").replace("_", " "):
            return t
    raise HTTPException(404, f"Template '{name}' not found")


@router.post("/wells/{wid}/apply-template")
def apply_template(wid: int, data: dict, db: Session = Depends(get_db)):
    """Apply a template to a well — update PetroParams."""
    well = db.query(Well).filter(Well.id == wid).first()
    if not well:
        raise HTTPException(404, "Well not found")
    if _template_locked(wid):
        raise HTTPException(423, "Template is locked; unlock required before edits")

    template_name = data.get("template_name") or data.get("name") or ""
    template = None
    for t in TEMPLATE_DB:
        if t["name"].lower() == template_name.lower():
            template = t
            break
    if not template:
        raise HTTPException(400, f"Template '{template_name}' not found")

    params = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    if not params:
        params = PetroParams(well_id=wid)
        db.add(params)

    # Apply template parameters
    tp = template["params"]
    tc = template["recommended_cutoffs"]
    params.saturation_model = tp.get("saturation_model", params.saturation_model)
    params.a = float(tp.get("a", params.a))
    params.m = float(tp.get("m", params.m))
    params.n = float(tp.get("n", params.n))
    params.rw = float(tp.get("rw", params.rw))
    params.vsh_cutoff = float(tc.get("vsh_cutoff", params.vsh_cutoff))
    params.phie_cutoff = float(tc.get("phie_cutoff", params.phie_cutoff))
    params.sw_cutoff = float(tc.get("sw_cutoff", params.sw_cutoff))
    params.template = template["name"]
    db.commit()

    return {
        "status": "ok",
        "applied_template": template["name"],
        "params": {
            "saturation_model": params.saturation_model,
            "a": params.a, "m": params.m, "n": params.n, "rw": params.rw,
            "vsh_cutoff": params.vsh_cutoff, "phie_cutoff": params.phie_cutoff, "sw_cutoff": params.sw_cutoff,
        },
        "log_track_layout": template.get("log_track_layout", []),
    }


@router.post("/wells/{wid}/template-preview")
def template_preview(wid: int, data: dict, db: Session = Depends(get_db)):
    """Preview what a template would change without applying."""
    template_name = data.get("template_name") or ""
    template = None
    for t in TEMPLATE_DB:
        if t["name"].lower() == template_name.lower():
            template = t
            break
    if not template:
        raise HTTPException(400, f"Template '{template_name}' not found")

    params = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    current = {}
    if params:
        current = {
            "saturation_model": params.saturation_model,
            "a": params.a, "m": params.m, "n": params.n, "rw": params.rw,
            "vsh_cutoff": params.vsh_cutoff, "phie_cutoff": params.phie_cutoff,
            "sw_cutoff": params.sw_cutoff, "template": params.template,
        }

    # Build diff
    tp = template["params"]
    tc = template["recommended_cutoffs"]
    proposed = {
        "saturation_model": tp.get("saturation_model", "archie"),
        "a": tp["a"], "m": tp["m"], "n": tp["n"], "rw": tp["rw"],
        "vsh_cutoff": tc["vsh_cutoff"], "phie_cutoff": tc["phie_cutoff"],
        "sw_cutoff": tc["sw_cutoff"], "template": template["name"],
    }

    changes = []
    for key, new_val in proposed.items():
        old_val = current.get(key)
        if old_val != new_val:
            changes.append({"param": key, "current": old_val, "proposed": new_val})

    return {
        "template": template["name"],
        "current": current,
        "proposed": proposed,
        "changes": changes,
        "description": template["description"],
        "log_track_layout": template.get("log_track_layout", []),
    }


@router.get("/wells/{wid}/template-comparison")
def template_comparison(wid: int, db: Session = Depends(get_db)):
    """Compare current well params against all templates."""
    params = db.query(PetroParams).filter(PetroParams.well_id == wid).first()
    if not params:
        return {"well_id": wid, "current": None, "comparisons": [], "note": "No petrophysical parameters saved for this well."}

    current = {
        "saturation_model": params.saturation_model,
        "a": params.a, "m": params.m, "n": params.n, "rw": params.rw,
        "vsh_cutoff": params.vsh_cutoff, "phie_cutoff": params.phie_cutoff,
        "sw_cutoff": params.sw_cutoff, "template": params.template,
    }

    comparisons = []
    for t in TEMPLATE_DB:
        tp = t["params"]
        tc = t["recommended_cutoffs"]
        proposed = {
            "saturation_model": tp.get("saturation_model"),
            "a": tp["a"], "m": tp["m"], "n": tp["n"], "rw": tp["rw"],
            "vsh_cutoff": tc["vsh_cutoff"], "phie_cutoff": tc["phie_cutoff"],
            "sw_cutoff": tc["sw_cutoff"],
        }
        diffs = sum(1 for k, v in proposed.items() if current.get(k) != v)
        comparisons.append({
            "name": t["name"],
            "description": t["description"],
            "reservoir_type": t.get("reservoir_type", ""),
            "param_diffs": diffs,
            "is_current": t["name"].lower() == (params.template or "").lower(),
        })

    comparisons.sort(key=lambda x: x["param_diffs"])
    return {"well_id": wid, "current": current, "comparisons": comparisons}
