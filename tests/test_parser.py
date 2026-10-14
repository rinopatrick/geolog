"""Tests for GeoLog LAS parser and API endpoints."""
import sys, os, io, json, math

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

# Import via the package path. Putting backend/ on sys.path would make the same
# files importable as both 'las_parser' and 'backend.las_parser', giving two
# independent module objects (and two SQLAlchemy registries).
from backend.las_parser import LASParser

# ─── LAS Parser Tests ────────────────────────────────────────────

SAMPLE_LAS = """~Version Information
VERS.                  2.0 :   CWLS LOG ASCII STANDARD -VERSION 2.0
WRAP.                  NO  :   ONE LINE PER DEPTH STEP
~Well Information
STRT.M              100.000 :
STOP.M              103.000 :
STEP.M                1.000 :
NULL.              -999.25  :
COMP.           TEST-COMP  :   COMPANY
WELL.           TEST-WELL  :   WELL
FLD .           TEST-FIELD :   FIELD
~Curve Information
DEPT.M                   :   DEPTH
GR  .GAPI               :   GAMMA RAY
RT  .OHMM               :   RESISTIVITY
NPHI.V/V                :   NEUTRON POROSITY
RHOB.G/C3               :   BULK DENSITY
~ASCII
100.0 50.0 10.0 0.25 2.65
101.0 55.0 12.0 0.22 2.60
102.0 60.0 -999.25 0.20 2.55
103.0 65.0 16.0 -999.25 2.50
"""

ALIAS_LAS = """~Version Information
VERS.                  2.0 :
WRAP.                  NO  :
~Well Information
STRT.FT             5000.0 :
STOP.FT             5003.0 :
STEP.FT                1.0 :
NULL.              -999.25  :
OPER.           ALIAS-OP   :
~Curve Information
DEPTH.FT                  :
CALI.IN                   :
RESD.OHMM                 :
ILD .OHMM                 :
DTP.US/F                  :
~ASCII
5000.0 8.5 20.0 25.0 80.0
5001.0 8.6 22.0 27.0 82.0
5002.0 8.7 24.0 29.0 84.0
5003.0 8.8 26.0 31.0 86.0
"""

# Two ~C mnemonics collapsing to the same canonical name must NOT lose a column:
# ~A data is positional, so dropping one shifts every later curve.
DUP_MNEMONIC_LAS = """~Version Information
VERS.                  2.0 :
WRAP.                  NO  :
~Well Information
STRT.FT             5000.0 :
STOP.FT             5002.0 :
STEP.FT                1.0 :
NULL.              -999.25  :
~Curve Information
DEPT.FT                   :
DEN .G/C3                 :
RHOC.G/C3                 :
GR  .GAPI                 :
DT35.US/F                 :
DT  .US/F                 :
~ASCII
5000.0 2.60 2.58 50.0 80.0 82.0
5001.0 2.55 2.53 55.0 85.0 87.0
5002.0 2.50 2.48 60.0 90.0 92.0
"""

PERCENT_LAS = """~Version Information
VERS.                  2.0 :
WRAP.                  NO  :
~Well Information
STRT.FT             5000.0 :
STOP.FT             5001.0 :
STEP.FT                1.0 :
NULL.              -999.25  :
~Curve Information
DEPT.FT                   :
NPRL.PERC                 :
DPOR.PU                   :
~ASCII
5000.0 40.0 0.25
5001.0 42.0 0.27
"""

# ~C declares 3 curves, ~A rows carry 4 columns.
MISMATCH_LAS = """~Version Information
VERS.                  2.0 :
WRAP.                  NO  :
~Well Information
STRT.FT             5000.0 :
STOP.FT             5001.0 :
STEP.FT                1.0 :
NULL.              -999.25  :
~Curve Information
DEPT.FT                   :
GR  .GAPI                 :
RHOB.G/C3                 :
~ASCII
5000.0 50.0 2.60 9.9
5001.0 55.0 2.55 9.8
"""


def _parse(s):
    return LASParser.parse_string(s)

def test_parse_basic():
    """Basic parsing: depth, curves, null handling."""
    p = _parse(SAMPLE_LAS)
    assert len(p.depth) == 4, f"Expected 4 depth points, got {len(p.depth)}"
    assert p.depth[0] == 100.0
    assert p.depth[-1] == 103.0
    assert len(p.curves) == 5  # DEPT, GR, RT, NPHI, RHOB
    print("✅ test_parse_basic")

def test_null_sentinel():
    """Null sentinel -999.25 should become NaN."""
    p = _parse(SAMPLE_LAS)
    assert math.isnan(p.data['RT'][2]), f"Expected NaN at RT[2], got {p.data['RT'][2]}"
    assert math.isnan(p.data['NPHI'][3]), f"Expected NaN at NPHI[3], got {p.data['NPHI'][3]}"
    assert not any(math.isnan(v) for v in p.data['GR']), "GR should have no NaN"
    print("✅ test_null_sentinel")

def test_alias_normalization():
    """Alias normalization: DEPTH→DEPT, CALI→CAL, RESD→RT, ILD→RILD, DTP→DT."""
    p = _parse(ALIAS_LAS)
    mnemonics = [c.mnemonic for c in p.curves]
    assert 'DEPT' in mnemonics, f"DEPT not found in {mnemonics}"
    assert 'CAL' in mnemonics, f"CAL not found in {mnemonics}"
    assert 'RT' in mnemonics, f"RT not found in {mnemonics}"
    assert 'RILD' in mnemonics, f"RILD not found in {mnemonics}"
    assert 'DT' in mnemonics, f"DT not found in {mnemonics}"
    print("✅ test_alias_normalization")

def test_operator_extraction():
    """Operator from OPER field."""
    p = _parse(ALIAS_LAS)
    assert p.well.operator == 'ALIAS-OP', f"Expected ALIAS-OP, got {p.well.operator}"
    print("✅ test_operator_extraction")

def test_depth_unit():
    """Depth unit extraction from curve definition."""
    p_ft = _parse(ALIAS_LAS)
    p_m = _parse(SAMPLE_LAS)
    ft_depth = next(c for c in p_ft.curves if c.mnemonic == 'DEPT')
    m_depth = next(c for c in p_m.curves if c.mnemonic == 'DEPT')
    assert ft_depth.unit == 'FT', f"Expected FT, got {ft_depth.unit}"
    assert m_depth.unit == 'M', f"Expected M, got {m_depth.unit}"
    print("✅ test_depth_unit")

def test_well_info():
    """Well info extraction."""
    p = _parse(SAMPLE_LAS)
    assert p.well.well_name == 'TEST-WELL', f"Expected TEST-WELL, got {p.well.well_name}"
    assert p.well.field == 'TEST-FIELD', f"Expected TEST-FIELD, got {p.well.field}"
    # OPER maps to operator; COMP maps to service_company in LAS spec
    p2 = _parse(ALIAS_LAS)
    assert p2.well.operator == 'ALIAS-OP', f"Expected ALIAS-OP, got {p2.well.operator}"
    print("✅ test_well_info")

def test_large_dataset():
    """Parser handles large dataset without crash."""
    lines = [
        "~Version Information", "VERS. 2.0 :", "WRAP. NO :",
        "~Well Information", "STRT.FT 0 :", "STOP.FT 9999 :", "STEP.FT 1 :",
        "NULL. -999.25 :", "WELL. LARGE :",
        "~Curve Information", "DEPT.FT :", "GR.GAPI :", "RT.OHMM :",
        "~ASCII",
    ]
    for i in range(10000):
        lines.append(f"{float(i)} {50.0 + i*0.01} {10.0 + i*0.001}")
    las_str = "\n".join(lines)
    p = _parse(las_str)
    assert len(p.depth) == 10000, f"Expected 10000, got {len(p.depth)}"
    assert len(p.data['GR']) == 10000
    print("✅ test_large_dataset")

def test_mnem_dot_unit_format():
    """MNEM.UNIT format parsing."""
    p = _parse(SAMPLE_LAS)
    gr_curve = next(c for c in p.curves if c.mnemonic == 'GR')
    assert gr_curve.unit == 'GAPI', f"Expected GAPI, got {gr_curve.unit}"
    rt_curve = next(c for c in p.curves if c.mnemonic == 'RT')
    assert rt_curve.unit == 'OHMM', f"Expected OHMM, got {rt_curve.unit}"
    print("✅ test_mnem_dot_unit_format")

def test_duplicate_canonical_mnemonics_keep_columns_aligned():
    """Alias collisions must not drop columns and shift every later curve."""
    p = _parse(DUP_MNEMONIC_LAS)

    assert [c.mnemonic for c in p.curves] == ['DEPT', 'RHOB', 'RHOC', 'GR', 'DT', 'DT_2'], \
        f"Column count changed: {[c.mnemonic for c in p.curves]}"

    # Each curve must still read its own column.
    assert p.data['RHOB'][0] == 2.60
    assert p.data['RHOC'][0] == 2.58
    assert p.data['GR'][0] == 50.0
    assert p.data['DT'][0] == 80.0
    assert p.data['DT_2'][0] == 82.0
    assert p.warnings == []
    print("✅ test_duplicate_canonical_mnemonics_keep_columns_aligned")


def test_percent_unit_porosity_normalized_to_fraction():
    """PERC porosity curves become fractions; PU curves are left alone."""
    p = _parse(PERCENT_LAS)
    assert p.data['NPHI'][0] == 0.40, f"Expected 0.40, got {p.data['NPHI'][0]}"
    assert p.data['DPOR'][0] == 0.25, f"PU must not be rescaled, got {p.data['DPOR'][0]}"
    print("✅ test_percent_unit_porosity_normalized_to_fraction")


def test_column_count_mismatch_is_reported():
    """A ~C/~A disagreement must surface as a warning, not silent truncation."""
    p = _parse(MISMATCH_LAS)
    assert len(p.curves) == 3
    assert any('columns' in w for w in p.warnings), f"No warning raised: {p.warnings}"
    assert p.to_dict()['warnings'] == p.warnings
    print("✅ test_column_count_mismatch_is_reported")


def test_empty_las():
    """Empty string should not crash."""
    try:
        p = _parse("")
        # Should either return empty or raise — should NOT crash
        print("✅ test_empty_las (returned empty)")
    except Exception:
        print("✅ test_empty_las (raised gracefully)")

def test_malformed_las():
    """Malformed input should not crash."""
    try:
        p = _parse("NOT A LAS FILE\nJUST RANDOM TEXT\n12345")
        print("✅ test_malformed_las (returned)")
    except Exception:
        print("✅ test_malformed_las (raised gracefully)")


# ─── API tests ──────────────────────────────────────────────────
#
# These used to call `requests` against http://localhost:8000 and wrap every
# assertion in `try/except Exception: print("skipped")`. With no server running
# they reported as passing without checking anything, so they could never fail.
# They now drive the app through TestClient, which needs no server and cannot
# silently skip.

from fastapi.testclient import TestClient

from backend.main import SessionLocal, app
from backend.models import Well

client = TestClient(app)
HEADERS = {"X-User-Role": "interpreter"}


def _first_well_id() -> int:
    db = SessionLocal()
    try:
        well = db.query(Well).order_by(Well.id.asc()).first()
        assert well is not None, "conftest should have seeded a well"
        return well.id
    finally:
        db.close()


def test_api_health():
    """Health endpoint reports the running version."""
    from backend.version import __version__

    response = client.get("/api/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["app"] == "GeoLog"
    assert body["version"] == __version__


def test_api_projects():
    """Projects endpoint returns a list."""
    response = client.get("/api/projects/", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "id" in data[0]


def test_api_wells():
    """Wells endpoint returns wells with log run counts."""
    response = client.get("/api/wells/", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) >= 1
    assert "log_run_count" in data[0]


def test_api_upload_empty():
    """An empty file is rejected."""
    wid = _first_well_id()
    response = client.post(
        f"/api/wells/{wid}/upload-las",
        files={"file": ("empty.las", b"", "text/plain")},
        headers=HEADERS,
    )
    assert response.status_code == 400, response.text[:200]


def test_api_upload_valid():
    """A valid LAS upload reports the curves and point count it stored."""
    wid = _first_well_id()
    response = client.post(
        f"/api/wells/{wid}/upload-las",
        files={"file": ("parser-test.las", SAMPLE_LAS.encode(), "text/plain")},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text[:300]
    data = response.json()
    assert data["num_points"] == 4
    assert "DEPT" in data["curves"]


def test_api_upload_las_values_round_trip():
    """The uploaded values must come back unchanged, not just present.

    This is the check that would have caught the positional column bug: the
    parser could return a curve under the right name holding another curve's
    numbers, and a status-only check would pass.
    """
    wid = _first_well_id()
    upload = client.post(
        f"/api/wells/{wid}/upload-las",
        files={"file": ("roundtrip.las", SAMPLE_LAS.encode(), "text/plain")},
        headers=HEADERS,
    )
    assert upload.status_code == 200, upload.text[:300]
    log_run_id = upload.json()["log_run_id"]

    response = client.post(
        f"/api/log-runs/{log_run_id}/data",
        json={"curve_mnemonics": ["GR", "RT", "NPHI", "RHOB"]},
        headers=HEADERS,
    )
    assert response.status_code == 200, response.text[:300]
    data = response.json()

    # Values from SAMPLE_LAS above, transcribed by hand.
    assert data["GR"][:2] == [50.0, 55.0], data["GR"][:4]
    assert data["RT"][:2] == [10.0, 12.0], data["RT"][:4]
    assert data["NPHI"][:2] == [0.25, 0.22], data["NPHI"][:4]
    assert data["RHOB"][:2] == [2.65, 2.60], data["RHOB"][:4]
    # -999.25 is the file's NULL, so it must arrive as null, not as a number.
    assert data["RT"][2] is None, f"null sentinel not converted: {data['RT'][2]}"
    assert data["NPHI"][3] is None, f"null sentinel not converted: {data['NPHI'][3]}"


def test_api_curves_and_data():
    """Curve listing and data retrieval work for an uploaded run."""
    wid = _first_well_id()
    upload = client.post(
        f"/api/wells/{wid}/upload-las",
        files={"file": ("curves.las", SAMPLE_LAS.encode(), "text/plain")},
        headers=HEADERS,
    )
    assert upload.status_code == 200, upload.text[:300]
    log_run_id = upload.json()["log_run_id"]

    curves = client.get(f"/api/log-runs/{log_run_id}/curves", headers=HEADERS)
    assert curves.status_code == 200
    curve_list = curves.json()
    assert len(curve_list) >= 1
    mnemonic = curve_list[0]["mnemonic"]
    assert mnemonic, "curve has no mnemonic"

    data = client.post(
        f"/api/log-runs/{log_run_id}/data",
        json={"curve_mnemonics": [mnemonic]},
        headers=HEADERS,
    )
    assert data.status_code == 200
    body = data.json()
    assert mnemonic in body or "DEPTH" in body, sorted(body)[:10]


def test_api_upload_unknown_well_is_404():
    response = client.post(
        "/api/wells/999999/upload-las",
        files={"file": ("x.las", SAMPLE_LAS.encode(), "text/plain")},
        headers=HEADERS,
    )
    assert response.status_code == 404
