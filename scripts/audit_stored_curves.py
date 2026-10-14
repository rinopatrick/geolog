#!/usr/bin/env python3
"""Report stored wells whose curve values are physically impossible.

The LAS parser used to drop a ~C definition when two vendor mnemonics mapped to
the same canonical name, shifting every later curve into its neighbour's column.
The raw upload is not retained, so those wells must be re-uploaded. This finds
them.

Usage:
  python scripts/audit_stored_curves.py
  python scripts/audit_stored_curves.py --json
  python scripts/audit_stored_curves.py --db backend/geolog.db

Exit codes: 0 = nothing found, 1 = at least one corrupt curve found.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from backend.curve_plausibility import audit_curves  # noqa: E402


def collect(db_path: str | None) -> list[dict]:
    if db_path:
        os.environ["GEOLOG_DB_PATH"] = db_path

    from backend.database import SessionLocal
    from backend.models import CurveData, LogRun, Well

    db = SessionLocal()
    try:
        report = []
        wells = db.query(Well).order_by(Well.id.asc()).all()
        for well in wells:
            runs = db.query(LogRun).filter(LogRun.well_id == well.id).all()
            for run in runs:
                curves = db.query(CurveData).filter(CurveData.log_run_id == run.id).all()
                findings = audit_curves(
                    {
                        "mnemonic": c.mnemonic,
                        "num_points": c.num_points,
                        "min_value": c.min_value,
                        "max_value": c.max_value,
                    }
                    for c in curves
                )
                if findings:
                    report.append({
                        "well_id": well.id,
                        "well": well.name,
                        "log_run_id": run.id,
                        "filename": run.filename,
                        "findings": [f.as_dict() for f in findings],
                    })
        return report
    finally:
        db.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", default=None, help="SQLite path (default: app default)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    args = parser.parse_args()

    report = collect(args.db)

    if args.json:
        print(json.dumps({"affected": report, "count": len(report)}, indent=2))
    elif not report:
        print("No physically impossible curve values found.")
    else:
        print(f"{len(report)} log run(s) contain curves whose values cannot belong to them.\n")
        for entry in report:
            print(f"  {entry['well']} (well {entry['well_id']}, run {entry['log_run_id']})")
            print(f"    file: {entry['filename']}")
            for f in entry["findings"]:
                print(f"      [{f['severity']:10s}] {f['mnemonic']}: {f['detail']}")
            print()
        print("The raw upload is not retained, so these must be re-uploaded from the")
        print("original LAS files. Re-uploading with the current parser is safe.")

    return 1 if any(
        f["severity"] == "corrupt" for e in report for f in e["findings"]
    ) else 0


if __name__ == "__main__":
    raise SystemExit(main())
