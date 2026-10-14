"""Seed the database with the South Pars demo scenario.

Run as a script::

    python -m backend.seed

Notes on what changed and why:

- Schema is created by ``ensure_schema()``, not ``Base.metadata.create_all()``.
  create_all() adds missing *tables* but never missing *columns*, so on an
  existing database this used to leave the schema silently stale.
- Imports are package-relative. The previous version inserted ``backend/`` on
  ``sys.path``, which makes the same modules importable under two names and gives
  the models a different SQLAlchemy ``Base`` than ``backend.database`` exposes.
- Output is ASCII. Emoji raised UnicodeEncodeError under the Windows console
  codepage (cp1252) and aborted the run.
- Everything runs inside ``main()`` rather than at import, so this module can be
  imported and tested.

The data here is a different scenario from ``seed_demo_data()`` in main.py: that
one builds two offset wells for correlation, this one a single South Pars well
with a full stratigraphic column.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np

from backend.database import SessionLocal
from backend.las_parser import LASParser
from backend.models import CurveData, FormationTop, LogRun, Project, Well
from backend.schema import ensure_schema

PROJECT_NAME = "South Pars Field Demo"

# Relative to this file, so it works from any working directory without
# touching sys.path.
_HERE = os.path.dirname(os.path.abspath(__file__))
DEMO_LAS_CANDIDATES = (
    os.path.join(_HERE, "demo.las"),
    os.path.join(_HERE, "..", "data", "hawkins_01.las"),
)

# (name, depth offset from the top of the logged interval, colour, lithology)
STRATIGRAPHY = (
    ("Umm Er Radhuma", 50, "#e74c3c", "Limestone"),
    ("Dammam", 200, "#3498db", "Limestone/Dolomite"),
    ("Asmari", 400, "#2ecc71", "Limestone"),
    ("Pabdeh", 650, "#9b59b6", "Marl"),
    ("Gurpi", 850, "#f39c12", "Shale"),
    ("Mishrif", 1100, "#e67e22", "Limestone"),
)


def find_demo_las() -> str | None:
    return next((p for p in DEMO_LAS_CANDIDATES if os.path.isfile(p)), None)


def seed(session=None) -> dict:
    """Create the demo project and well. Returns a summary dict.

    Raises FileNotFoundError if no demo LAS file is present. Existing rows are
    left alone: seeding twice does not create a second copy.
    """
    demo_las = find_demo_las()
    if not demo_las:
        raise FileNotFoundError(
            f"no demo LAS found; looked in {list(DEMO_LAS_CANDIDATES)}"
        )

    owns_session = session is None
    db = session if session is not None else SessionLocal()
    try:
        existing = db.query(Project).filter(Project.name == PROJECT_NAME).first()
        if existing is not None:
            return {
                "created": False,
                "reason": "already seeded",
                "project_id": existing.id,
            }

        las = LASParser.parse_file(demo_las)
        fname = os.path.basename(demo_las)

        project = Project(
            name=PROJECT_NAME, field_name="South Pars",
            operator="ADNOC", country="UAE",
        )
        db.add(project)
        db.flush()

        well = Well(
            project_id=project.id,
            name=las.well.well_name or "MELANIE-1",
            uwi=las.well.uwi or "42-123-45678",
            latitude=25.5, longitude=54.5, elevation=85.0,
            total_depth=las.well.stop, depth_unit="FT",
            operator=las.well.operator or "ADNOC",
        )
        db.add(well)
        db.flush()

        curves_def = [
            {"mnemonic": c.mnemonic, "unit": c.unit, "description": c.description}
            for c in las.curves
        ]
        log_run = LogRun(
            well_id=well.id, run_number=1, filename=fname,
            las_version=las.version,
            start_depth=las.well.start, stop_depth=las.well.stop,
            step=las.well.step, null_value=las.well.null,
            num_points=len(las.depth), curves_json=json.dumps(curves_def),
        )
        db.add(log_run)
        db.flush()

        for curve in las.curves:
            arr = las.data.get(curve.mnemonic)
            if arr is None:
                continue
            valid = arr[~np.isnan(arr)]
            db.add(CurveData(
                log_run_id=log_run.id, mnemonic=curve.mnemonic,
                unit=curve.unit, description=curve.description,
                num_points=len(arr),
                min_value=float(np.min(valid)) if len(valid) else None,
                max_value=float(np.max(valid)) if len(valid) else None,
                data_binary=arr.tobytes(),
            ))

        for name, offset, color, lithology in STRATIGRAPHY:
            db.add(FormationTop(
                well_id=well.id, formation_name=name,
                depth=las.well.start + offset, color=color, lithology=lithology,
            ))

        db.commit()
        return {
            "created": True,
            "project_id": project.id,
            "well_id": well.id,
            "log_run_id": log_run.id,
            "curves": len(las.curves),
            "points": len(las.depth),
            "tops": len(STRATIGRAPHY),
        }
    except Exception:
        db.rollback()
        raise
    finally:
        if owns_session:
            db.close()


def main() -> int:
    print("Seeding GeoLog with demo data...")
    ensure_schema()

    db = SessionLocal()
    try:
        result = seed(db)
    finally:
        db.close()

    if not result.get("created"):
        print(f"Nothing to do: {result.get('reason')}")
        return 0

    print(
        f"Done. Project #{result['project_id']}, Well #{result['well_id']}, "
        f"Log Run #{result['log_run_id']}"
    )
    print(
        f"  {result['curves']} curves, {result['points']} data points, "
        f"{result['tops']} formation tops"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
