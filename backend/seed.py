"""Seed database with demo LAS data. Works from any CWD."""
import sys
import os

# Ensure imports work regardless of CWD
_backend_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _backend_dir)

from database import engine, SessionLocal, Base
from models import Project, Well, LogRun, CurveData, FormationTop
from las_parser import LASParser
import numpy as np
import json

Base.metadata.create_all(bind=engine)
db = SessionLocal()

print("🛢️ Seeding GeoLog with demo data...")

# Find demo LAS
demo_paths = [
    os.path.join(_backend_dir, "demo.las"),
    os.path.join(_backend_dir, "..", "data", "hawkins_01.las"),
]
demo_las = next((p for p in demo_paths if os.path.isfile(p)), None)
if not demo_las:
    print("❌ No demo LAS file found")
    sys.exit(1)

las = LASParser.parse_file(demo_las)
fname = os.path.basename(demo_las)

# Create project
proj = Project(name="South Pars Field Demo", field_name="South Pars", operator="ADNOC", country="UAE")
db.add(proj)
db.flush()

# Create well
well = Well(
    project_id=proj.id, name=las.well.well_name or "MELANIE-1", uwi=las.well.uwi or "42-123-45678",
    latitude=25.5, longitude=54.5, elevation=85.0,
    total_depth=las.well.stop, depth_unit="FT", operator=las.well.operator or "ADNOC",
)
db.add(well)
db.flush()

# Create log run
curves_def = [{"mnemonic": c.mnemonic, "unit": c.unit, "description": c.description} for c in las.curves]
lr = LogRun(
    well_id=well.id, run_number=1, filename=fname,
    las_version=las.version, start_depth=las.well.start,
    stop_depth=las.well.stop, step=las.well.step,
    null_value=las.well.null, num_points=len(las.depth),
    curves_json=json.dumps(curves_def),
)
db.add(lr)
db.flush()

# Store curve data
for curve in las.curves:
    arr = las.data.get(curve.mnemonic)
    if arr is not None:
        valid = arr[~np.isnan(arr)]
        cr = CurveData(
            log_run_id=lr.id, mnemonic=curve.mnemonic,
            unit=curve.unit, description=curve.description,
            num_points=len(arr),
            min_value=float(np.min(valid)) if len(valid) else None,
            max_value=float(np.max(valid)) if len(valid) else None,
            data_binary=arr.tobytes(),
        )
        db.add(cr)

# Add formation tops
tops = [
    ("Umm Er Radhuma", las.well.start + 50, "#e74c3c", "Limestone"),
    ("Dammam", las.well.start + 200, "#3498db", "Limestone/Dolomite"),
    ("Asmari", las.well.start + 400, "#2ecc71", "Limestone"),
    ("Pabdeh", las.well.start + 650, "#9b59b6", "Marl"),
    ("Gurpi", las.well.start + 850, "#f39c12", "Shale"),
    ("Mishrif", las.well.start + 1100, "#e67e22", "Limestone"),
]
for name, depth, color, lith in tops:
    db.add(FormationTop(well_id=well.id, formation_name=name, depth=depth, color=color, lithology=lith))

db.commit()
print(f"✅ Done! Project #{proj.id}, Well #{well.id}, Log Run #{lr.id}")
print(f"   {len(las.curves)} curves, {len(las.depth)} data points, {len(tops)} formation tops")
db.close()
