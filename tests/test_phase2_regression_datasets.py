"""Phase 2 regression-dataset evidence tests.

Ensures at least 3 realistic LAS datasets are present, parseable, and — most
importantly — that every parsed curve reads the column it claims to. Counting
curves alone passes while columns are silently shifted.
"""

from __future__ import annotations

import json
import math
import os
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "backend"))

from las_parser import FRACTION_CURVES, LASParser, PERCENT_UNITS  # noqa: E402


MANIFEST_PATH = REPO_ROOT / "test_data" / "regression_datasets_phase2.json"


def _manifest():
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def _raw_row(path: Path, delimiter: str, index: int) -> list[str]:
    """First `index`-th ~A row, split the same way the parser splits it."""
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    start = next(i for i, l in enumerate(lines) if l.strip().upper().startswith("~A"))
    rows = [l.strip() for l in lines[start + 1 :] if l.strip() and not l.strip().startswith("#")]
    sep = delimiter if delimiter else None
    return rows[index].split(sep)


def test_phase2_regression_manifest_has_min_three_datasets():
    assert MANIFEST_PATH.exists(), "Missing regression dataset manifest"
    datasets = _manifest().get("datasets", [])
    assert isinstance(datasets, list)
    assert len(datasets) >= 3, "Phase 2 requires >=3 realistic regression datasets"


def test_phase2_regression_datasets_exist_and_are_nontrivial():
    for ds in _manifest()["datasets"]:
        path = REPO_ROOT / ds["path"]
        assert path.exists(), f"Dataset not found: {ds['path']}"
        assert path.suffix.lower() == ".las"
        assert path.stat().st_size > 100_000, f"Dataset too small to be realistic: {ds['path']}"


def test_phase2_regression_datasets_parse_with_expected_shape():
    for ds in _manifest()["datasets"]:
        parsed = LASParser.parse_file(str(REPO_ROOT / ds["path"]))

        assert len(parsed.depth) >= int(ds["expected_min_depth_points"]), (
            f"Depth points too low for {ds['id']}: {len(parsed.depth)}"
        )
        assert len(parsed.curves) >= int(ds["expected_min_curves"]), (
            f"Curve count too low for {ds['id']}: {len(parsed.curves)}"
        )

        assert "DEPT" in parsed.data, f"Missing DEPT curve data in {ds['id']}"
        assert len(parsed.data["DEPT"]) == len(parsed.depth)
        assert parsed.warnings == [], f"Parse warnings for {ds['id']}: {parsed.warnings}"


@pytest.mark.parametrize("ds", _manifest()["datasets"], ids=lambda d: d["id"])
def test_regression_dataset_columns_are_not_shifted(ds):
    """Every curve must read the ~A column matching its ~C position.

    This is the assertion that catches alias collisions dropping a ~C entry and
    shifting all later curves into the wrong column.
    """
    path = REPO_ROOT / ds["path"]
    index = int(ds["golden_index"])
    raw = _raw_row(path, ds.get("delimiter") or "", index)
    parsed = LASParser.parse_file(str(path))

    assert len(raw) == len(parsed.curves), (
        f"{ds['id']}: ~A row has {len(raw)} columns but {len(parsed.curves)} curves were parsed"
    )

    for position, curve in enumerate(parsed.curves):
        expected = float(raw[position])
        got = float(parsed.data[curve.mnemonic][index])
        if expected == parsed.well.null:
            assert math.isnan(got), (
                f"{ds['id']}: {curve.mnemonic} should be null (NaN), got {got}"
            )
            continue
        if (curve.unit or "").strip().upper() in PERCENT_UNITS and curve.mnemonic in FRACTION_CURVES:
            expected /= 100.0
        assert got == pytest.approx(expected, rel=1e-9, abs=1e-9), (
            f"{ds['id']}: {curve.mnemonic} read column {position} as {got}, file says {expected}"
        )


@pytest.mark.parametrize("ds", _manifest()["datasets"], ids=lambda d: d["id"])
def test_regression_dataset_golden_values(ds):
    """Spot-check values transcribed from the raw file, independent of the parser."""
    parsed = LASParser.parse_file(str(REPO_ROOT / ds["path"]))
    index = int(ds["golden_index"])
    for mnemonic, expected in ds["golden"].items():
        assert mnemonic in parsed.data, f"{ds['id']}: missing curve {mnemonic}"
        assert float(parsed.data[mnemonic][index]) == pytest.approx(expected, rel=1e-4), (
            f"{ds['id']}: {mnemonic}[{index}] = {parsed.data[mnemonic][index]}, expected {expected}"
        )
