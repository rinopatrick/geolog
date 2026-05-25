"""Unit Normalization + Alias Resolution router for GeoLog."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
import numpy as np
import math
import json

try:
    from database import get_db
    from models import Well, LogRun, CurveData, CurveAlias
except ImportError:
    from backend.database import get_db
    from backend.models import Well, LogRun, CurveData, CurveAlias

router = APIRouter(prefix="/api", tags=["units"])


# ── Conversion Rules ──────────────────────────────────────────
UNIT_CONVERSIONS = {
    "resistivity": {
        "from": "ohm.m", "to": "ohm-ft", "factor": 3.28084,
        "mnemonics": ["RT", "RILD", "RILM", "RMED", "RXO", "RES", "AHT90", "AT90", "RLA1"],
    },
    "resistivity_inv": {
        "from": "ohm-ft", "to": "ohm.m", "factor": 1/3.28084,
        "mnemonics": [],
    },
    "sonic": {
        "from": "us/ft", "to": "us/m", "factor": 3.28084,
        "mnemonics": ["DT", "DTC", "AC", "SONIC", "DTS"],
    },
    "sonic_inv": {
        "from": "us/m", "to": "us/ft", "factor": 1/3.28084,
        "mnemonics": [],
    },
    "density": {
        "from": "g/cc", "to": "kg/m3", "factor": 1000,
        "mnemonics": ["RHOB", "ZDEN", "DEN", "BULK", "RHOZ"],
    },
    "density_inv": {
        "from": "kg/m3", "to": "g/cc", "factor": 0.001,
        "mnemonics": [],
    },
    "depth_ft_to_m": {
        "from": "ft", "to": "m", "factor": 0.3048,
        "mnemonics": ["DEPT", "DEPTH"],
    },
    "depth_m_to_ft": {
        "from": "m", "to": "ft", "factor": 1/0.3048,
        "mnemonics": [],
    },
    "porosity_pct": {
        "from": "v/v", "to": "%", "factor": 100,
        "mnemonics": ["PHIE", "PHID", "PHIN", "PHI_E", "NPHI", "NPOR"],
    },
    "porosity_frac": {
        "from": "%", "to": "v/v", "factor": 0.01,
        "mnemonics": [],
    },
}

# ── Canonical Alias Map ───────────────────────────────────────
CANONICAL_ALIASES = {
    "GR": ["GAMMA", "GR_API", "HCGR", "CGR", "SGR", "GRC", "GR1", "GR2"],
    "RT": ["RILD", "RILM", "RMED", "RES", "AHT90", "AT90", "RLA1", "RT_HRLT"],
    "RHOB": ["ZDEN", "DEN", "BULK", "RHOZ", "RHOB_CAL"],
    "NPHI": ["NPOR", "NEUTRON", "TNPH", "NPHI_LIM"],
    "DT": ["DTC", "AC", "SONIC", "DTS", "DTCO", "DTSM"],
    "CALI": ["CAL", "C1", "C2", "HCAL", "LCAL"],
    "SP": ["SPONT", "SSP"],
    "PEF": ["PE", "PEFZ"],
}


def _sanitize(v):
    if v is None:
        return None
    if isinstance(v, (np.floating, float)):
        fv = float(v)
        return None if (math.isnan(fv) or math.isinf(fv)) else fv
    if isinstance(v, (np.integer, int)):
        return int(v)
    return v


@router.get("/unit-conversions")
def list_unit_conversions():
    """Return all available conversion rules."""
    rules = []
    for key, conv in UNIT_CONVERSIONS.items():
        if key.endswith("_inv"):
            continue
        rules.append({
            "id": key,
            "from_unit": conv["from"],
            "to_unit": conv["to"],
            "factor": conv["factor"],
            "mnemonics": conv["mnemonics"],
        })
    return {"conversions": rules, "canonical_aliases": CANONICAL_ALIASES}


@router.get("/wells/{wid}/unit-map")
def get_unit_map(wid: int, db: Session = Depends(get_db)):
    """Return current unit mapping per curve for the latest log run."""
    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run found")

    curves = json.loads(lr.curves_json) if lr.curves_json else []
    unit_map = []
    for c in curves:
        mn = c.get("mnemonic", "")
        unit = c.get("unit", "")
        # Detect category and possible conversions
        category = "unknown"
        possible_conversions = []
        for key, conv in UNIT_CONVERSIONS.items():
            if key.endswith("_inv"):
                continue
            if mn.upper() in conv["mnemonics"] or any(mn.upper().startswith(alias) for alias in conv["mnemonics"]):
                category = key
                possible_conversions.append({
                    "to_unit": conv["to"],
                    "factor": conv["factor"],
                })

        # Check if canonical alias exists
        canonical = mn.upper()
        for canon, aliases in CANONICAL_ALIASES.items():
            if mn.upper() == canon or mn.upper() in aliases:
                canonical = canon
                break

        unit_map.append({
            "mnemonic": mn,
            "unit": unit,
            "canonical": canonical,
            "category": category,
            "possible_conversions": possible_conversions,
        })

    return {"well_id": wid, "log_run_id": lr.id, "curves": unit_map}


@router.post("/wells/{wid}/normalize-units")
def normalize_units(wid: int, data: dict, db: Session = Depends(get_db)):
    """Auto-detect and normalize curve units to standard SI/field conventions."""
    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run found")

    target_system = data.get("target", "field")  # 'field' or 'si'
    conversion_log = []

    curves = json.loads(lr.curves_json) if lr.curves_json else []
    for c in curves:
        mn = c.get("mnemonic", "")
        unit = (c.get("unit", "") or "").lower().strip()
        mn_upper = mn.upper()

        # Detect needed conversions
        conversion = None
        for key, conv in UNIT_CONVERSIONS.items():
            if key.endswith("_inv"):
                continue
            if mn_upper not in conv["mnemonics"]:
                continue
            from_u = conv["from"].lower()
            to_u = conv["to"].lower()
            # Check if current unit matches source
            if unit in [from_u, from_u.replace(".", "").replace("/", ""), conv["from"]]:
                continue  # already in correct unit
            # Check if needs conversion
            if unit in [to_u, to_u.replace(".", "").replace("/", ""), conv["to"]]:
                conversion = conv  # needs reverse conversion
                break
            # Auto-detect: if unit is empty but mnemonic is known, flag it
            if not unit:
                conversion_log.append({
                    "mnemonic": mn,
                    "detected_unit": "(empty)",
                    "action": "skipped — unit unknown, cannot auto-convert",
                })
                continue

        if conversion:
            conversion_log.append({
                "mnemonic": mn,
                "from_unit": conversion["from"],
                "to_unit": conversion["to"],
                "factor": conversion["factor"],
                "action": "conversion available",
            })

    return {
        "well_id": wid,
        "log_run_id": lr.id,
        "target_system": target_system,
        "conversions": conversion_log,
        "note": "Unit normalization metadata returned. Apply conversions on curve data as needed.",
    }


@router.post("/wells/{wid}/resolve-aliases")
def resolve_aliases(wid: int, data: dict, db: Session = Depends(get_db)):
    """Resolve vendor mnemonics to canonical names."""
    lr = db.query(LogRun).filter(LogRun.well_id == wid).order_by(LogRun.id.desc()).first()
    if not lr:
        raise HTTPException(404, "No log run found")

    curves = json.loads(lr.curves_json) if lr.curves_json else []
    auto = data.get("auto", True)  # auto-save aliases

    resolved = []
    alias_map = {}
    for c in curves:
        mn = c.get("mnemonic", "")
        mn_upper = mn.upper()
        canonical = mn_upper
        for canon, aliases in CANONICAL_ALIASES.items():
            if mn_upper == canon or mn_upper in [a.upper() for a in aliases]:
                canonical = canon
                break
        resolved.append({
            "original": mn,
            "canonical": canonical,
            "is_alias": canonical != mn_upper,
        })
        if canonical != mn_upper:
            alias_map[mn] = canonical

    if auto and alias_map:
        # Save to CurveAlias table
        for orig, canon in alias_map.items():
            existing = db.query(CurveAlias).filter(
                CurveAlias.well_id == wid,
                CurveAlias.original_mnemonic == orig,
            ).first()
            if not existing:
                db.add(CurveAlias(
                    well_id=wid,
                    original_mnemonic=orig,
                    alias_mnemonic=canon,
                ))
        db.commit()

    return {
        "well_id": wid,
        "resolved": resolved,
        "alias_count": len(alias_map),
        "auto_saved": auto,
    }
