"""Phase 2 regression-dataset evidence tests.

Ensures at least 3 realistic LAS datasets are present and parseable.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from las_parser import LASParser  # noqa: E402


MANIFEST_PATH = REPO_ROOT / "test_data" / "regression_datasets_phase2.json"


def test_phase2_regression_manifest_has_min_three_datasets():
    assert MANIFEST_PATH.exists(), "Missing regression dataset manifest"
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    datasets = data.get("datasets", [])
    assert isinstance(datasets, list)
    assert len(datasets) >= 3, "Phase 2 requires >=3 realistic regression datasets"


def test_phase2_regression_datasets_exist_and_are_nontrivial():
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for ds in data["datasets"]:
        path = REPO_ROOT / ds["path"]
        assert path.exists(), f"Dataset not found: {ds['path']}"
        assert path.suffix.lower() == ".las"
        assert path.stat().st_size > 100_000, f"Dataset too small to be realistic: {ds['path']}"


def test_phase2_regression_datasets_parse_with_expected_shape():
    data = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    for ds in data["datasets"]:
        path = REPO_ROOT / ds["path"]
        parsed = LASParser.parse_file(str(path))

        assert len(parsed.depth) >= int(ds["expected_min_depth_points"]), (
            f"Depth points too low for {ds['id']}: {len(parsed.depth)}"
        )
        assert len(parsed.curves) >= int(ds["expected_min_curves"]), (
            f"Curve count too low for {ds['id']}: {len(parsed.curves)}"
        )

        assert "DEPT" in parsed.data, f"Missing DEPT curve data in {ds['id']}"
        assert len(parsed.data["DEPT"]) == len(parsed.depth)
