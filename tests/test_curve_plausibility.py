"""Physical plausibility checks used to find stored wells corrupted by the old
positional LAS parsing bug.

The fixtures double as the regression case: the current parser must produce no
'corrupt' findings on them, because the old parser shifted their columns.
"""

from __future__ import annotations

import glob
import pathlib
import sys

import numpy as np
import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Package imports only — see tests/test_import_hygiene.py for why.
from backend.curve_plausibility import (  # noqa: E402
    MIN_POINTS_FOR_CHECK,
    PLAUSIBLE_RANGES,
    audit_curves,
    check_curve,
    check_resistivity_ordering,
)
from backend.las_parser import LASParser  # noqa: E402


# ─── Single-curve range checks ──────────────────────────────────


def test_flags_gr_that_is_actually_a_porosity_curve():
    """The old bug left GR holding DPOR values (max 1.585)."""
    finding = check_curve("GR", 1695, 0.01, 1.585)
    assert finding is not None
    assert finding.severity == "corrupt"
    assert "below the plausible floor" in finding.detail


def test_flags_rhob_that_is_actually_a_caliper_curve():
    """The old bug left RHOB holding DCAL values (min 6.9 inches)."""
    finding = check_curve("RHOB", 1695, 6.9, 12.4)
    assert finding is not None
    assert finding.severity == "corrupt"
    assert "above the plausible ceiling" in finding.detail


def test_flags_dt_that_is_actually_a_resistivity_curve():
    finding = check_curve("DT", 1000, 0.02, 5.326)
    assert finding is not None
    assert finding.severity == "corrupt"


@pytest.mark.parametrize("mnemonic,lo,hi", [
    ("GR", 15.0, 120.0),
    ("RHOB", 2.1, 2.7),
    ("DT", 55.0, 90.0),
    ("NPHI", 0.12, 0.38),
    ("RILD", 0.5, 300.0),
    ("PE", 1.8, 6.0),
])
def test_real_values_pass(mnemonic, lo, hi):
    assert check_curve(mnemonic, 5000, lo, hi) is None


def test_short_curves_are_not_judged():
    assert check_curve("GR", MIN_POINTS_FOR_CHECK - 1, 0.01, 1.5) is None


def test_constant_curves_are_not_judged():
    """An all-null or all-zero curve carries no information."""
    assert check_curve("GR", 5000, 0.0, 0.0) is None


def test_missing_bounds_are_not_judged():
    assert check_curve("GR", 5000, None, 100.0) is None
    assert check_curve("GR", 5000, 1.0, None) is None


def test_unknown_mnemonic_is_not_judged():
    assert check_curve("ZZTOP", 5000, -1e9, -1e8) is None


# ─── Cross-curve ordering ───────────────────────────────────────


def test_flags_resistivity_column_swap():
    """The old bug left RILM holding sonic transit time and RILD sonic porosity."""
    findings = check_resistivity_ordering({"RILD": (0.5, 239.0), "RILM": (0.5, 797.0)})
    assert len(findings) == 1
    assert findings[0].severity == "suspicious"
    assert findings[0].mnemonic == "RILM"


def test_normal_resistivity_ordering_passes():
    findings = check_resistivity_ordering({
        "RILD": (0.5, 300.0), "RILM": (0.5, 250.0), "RXO": (0.5, 100.0),
    })
    assert findings == []


def test_ordering_ignores_missing_curves():
    assert check_resistivity_ordering({"RILD": (0.5, 300.0)}) == []


def test_ordering_tolerates_small_inversion():
    """Invasion is not always present; a small inversion is not evidence."""
    assert check_resistivity_ordering({"RILD": (0.5, 200.0), "RILM": (0.5, 210.0)}) == []


# ─── Integration over the real fixtures ─────────────────────────


FIXTURES = sorted(glob.glob(str(REPO_ROOT / "test_data" / "*.las")))


def _stored_ranges(path: str) -> list[dict]:
    """Mirror what upload_las() persists: NaN-filtered min/max per curve."""
    las = LASParser.parse_file(path)
    out = []
    for curve in las.curves:
        arr = las.data.get(curve.mnemonic)
        if arr is None or not len(arr):
            continue
        valid = arr[~np.isnan(arr)]
        if not len(valid):
            continue
        out.append({
            "mnemonic": curve.mnemonic,
            "num_points": len(arr),
            "min_value": float(np.min(valid)),
            "max_value": float(np.max(valid)),
        })
    return out


def test_fixtures_exist():
    assert len(FIXTURES) >= 3, "expected the KGS regression fixtures"


@pytest.mark.parametrize("path", FIXTURES, ids=lambda p: pathlib.Path(p).stem[:40])
def test_current_parser_produces_plausible_values(path):
    """Regression: the fixed parser must not shift any fixture's columns."""
    findings = audit_curves(_stored_ranges(path))
    corrupt = [f for f in findings if f.severity == "corrupt"]
    assert corrupt == [], (
        f"{pathlib.Path(path).name} produced impossible values: "
        f"{[(f.mnemonic, f.detail) for f in corrupt]}"
    )


def test_ranges_table_covers_the_curves_the_parser_can_emit():
    """Every canonical mnemonic the app computes or displays should be checkable."""
    for mnemonic in ("GR", "RHOB", "NPHI", "DT", "PE", "RILD", "RILM", "RXO",
                     "DPOR", "SPOR", "VSH", "PHIE", "SW"):
        assert mnemonic in PLAUSIBLE_RANGES


def test_all_ranges_are_ordered():
    for mnemonic, (lo, hi) in PLAUSIBLE_RANGES.items():
        assert lo < hi, f"{mnemonic} has an inverted range ({lo}, {hi})"
