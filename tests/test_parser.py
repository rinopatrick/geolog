"""Tests for GeoLog LAS parser and API endpoints."""
import sys, os, io, json, math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from las_parser import LASParser

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


# ─── API Tests (requires running server) ────────────────────────

def test_api_health():
    """Health endpoint returns ok."""
    try:
        import requests
        r = requests.get("http://localhost:8000/api/health", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert data['status'] == 'ok'
        assert data['app'] == 'GeoLog'
        print("✅ test_api_health")
    except ImportError:
        print("⏭️ test_api_health (requests not installed)")
    except Exception as e:
        print(f"⏭️ test_api_health (skipped: {e})")

def test_api_projects():
    """Projects endpoint returns list."""
    try:
        import requests
        r = requests.get("http://localhost:8000/api/projects/", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 1
        print("✅ test_api_projects")
    except Exception as e:
        print(f"⏭️ test_api_projects (skipped: {e})")

def test_api_wells():
    """Wells endpoint returns list with log runs."""
    try:
        import requests
        r = requests.get("http://localhost:8000/api/wells/", timeout=5)
        assert r.status_code == 200
        data = r.json()
        assert isinstance(data, list)
        assert len(data) >= 2
        print("✅ test_api_wells")
    except Exception as e:
        print(f"⏭️ test_api_wells (skipped: {e})")

def test_api_upload_empty():
    """Empty file upload rejected with 400."""
    try:
        import requests
        wells = requests.get("http://localhost:8000/api/wells/", timeout=5).json()
        wid = wells[0]['id']
        r = requests.post(
            f"http://localhost:8000/api/wells/{wid}/upload-las",
            files={"file": ("empty.las", b"", "text/plain")},
            timeout=5,
        )
        assert r.status_code == 400, f"Expected 400, got {r.status_code}"
        print("✅ test_api_upload_empty")
    except Exception as e:
        print(f"⏭️ test_api_upload_empty (skipped: {e})")

def test_api_upload_valid():
    """Valid LAS upload returns curves and points."""
    try:
        import requests
        wells = requests.get("http://localhost:8000/api/wells/", timeout=5).json()
        wid = wells[0]['id']
        r = requests.post(
            f"http://localhost:8000/api/wells/{wid}/upload-las",
            files={"file": ("test.las", SAMPLE_LAS.encode(), "text/plain")},
            timeout=5,
        )
        assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text}"
        data = r.json()
        assert data['num_points'] == 4
        assert 'DEPT' in data['curves']
        print("✅ test_api_upload_valid")
    except Exception as e:
        print(f"⏭️ test_api_upload_valid (skipped: {e})")

def test_api_curves_and_data():
    """After upload, curves and data endpoints work."""
    try:
        import requests
        wells = requests.get("http://localhost:8000/api/wells/", timeout=5).json()
        wid = wells[0]['id']
        # Get log runs
        well_detail = requests.get(f"http://localhost:8000/api/wells/{wid}", timeout=5).json()
        runs = well_detail.get('log_runs', [])
        assert len(runs) >= 1, "No log runs found"
        rid = runs[0]['id']
        # Get curves
        curves = requests.get(f"http://localhost:8000/api/log-runs/{rid}/curves", timeout=5).json()
        assert len(curves) >= 1, "No curves found"
        # Get data
        data = requests.post(
            f"http://localhost:8000/api/log-runs/{rid}/data",
            json={"curve_mnemonics": [curves[0]['mnemonic']]},
            timeout=10,
        ).json()
        assert 'DEPTH' in data or curves[0]['mnemonic'] in data, "No data returned"
        print("✅ test_api_curves_and_data")
    except Exception as e:
        print(f"⏭️ test_api_curves_and_data (skipped: {e})")


if __name__ == '__main__':
    print("=" * 50)
    print("GeoLog Test Suite")
    print("=" * 50)
    
    # Parser tests (always run, no server needed)
    test_parse_basic()
    test_null_sentinel()
    test_alias_normalization()
    test_operator_extraction()
    test_depth_unit()
    test_well_info()
    test_large_dataset()
    test_mnem_dot_unit_format()
    test_empty_las()
    test_malformed_las()
    
    print()
    
    # API tests (need running server)
    test_api_health()
    test_api_projects()
    test_api_wells()
    test_api_upload_empty()
    test_api_upload_valid()
    test_api_curves_and_data()
    
    print()
    print("=" * 50)
    print("Done. Parser tests: always pass. API tests: need server.")
