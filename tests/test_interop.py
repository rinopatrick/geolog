"""WITSML/OSDU parsing and pull/push endpoints with mocked transports."""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend import interop
from backend.main import SessionLocal, app
from backend.models import Project, Well

client = TestClient(app)
I = {"X-User-Role": "interpreter"}

WELL_XML = """<wells xmlns="http://www.witsml.org/schemas/1series" version="1.4.1.1">
<well><name>W1</name><uwi>U1</uwi><operator>Op</operator><field>F</field>
<latitude>60.1</latitude><longitude>5.2</longitude><totalDepth>2000</totalDepth></well></wells>"""

LOG_XML = """<logs xmlns="http://www.witsml.org/schemas/1series" version="1.4.1.1">
<log><name>L1</name><wellName>W1</wellName><startIndex>1000</startIndex><endIndex>1002</endIndex>
<logCurveInfo><mnemonic>DEPT</mnemonic><unit>ft</unit></logCurveInfo>
<logCurveInfo><mnemonic>GR</mnemonic><unit>gAPI</unit></logCurveInfo>
<logData><data>1000 10
1001 20
1002 30</data></logData></log></logs>"""

def _project_id():
    db = SessionLocal()
    try:
        return db.query(Project.id).order_by(Project.id.asc()).first()[0]
    finally:
        db.close()

def test_parsers():
    wells = interop.parse_witsml_wells(WELL_XML)
    assert wells[0]["name"] == "W1" and wells[0]["uwi"] == "U1"
    logs = interop.parse_witsml_logs(LOG_XML)
    assert logs[0]["well_name"] == "W1"
    assert [c["mnemonic"] for c in logs[0]["curves"]] == ["DEPT", "GR"]
    assert logs[0]["rows"][-1] == [1002.0, 30.0]

def test_witsml_pull_and_osdu_push(monkeypatch, make_well):
    pid = _project_id()
    monkeypatch.setattr(interop, "witsml_query",
                        lambda kind, name="": WELL_XML if kind == "well" else LOG_XML)
    r = client.post(f"/api/interop/witsml/pull?project_id={pid}&object_type=both", headers=I)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["wells"][0]["name"] == "W1"
    assert body["logs"][0]["status"] == "imported"
    assert body["logs"][0]["points"] == 3

    db = SessionLocal()
    try:
        well = db.query(Well).filter(Well.name == "W1").first()
        assert well.uwi == "U1"
        wid = well.id
    finally:
        db.close()

    monkeypatch.setenv("GEOLOG_OSDU_URL", "https://osdu.example")
    monkeypatch.setenv("GEOLOG_OSDU_PARTITION", "p1")
    seen = {}
    def fake_osdu(cfg, method, path, body=None):
        seen["method"], seen["path"] = method, path
        return 200, {"id": "osdu-1"}
    monkeypatch.setattr(interop, "osdu_request", fake_osdu)
    push = client.post(f"/api/interop/osdu/push/wells/{wid}", headers=I)
    assert push.status_code == 200, push.text
    assert push.json()["ok"] is True
    assert seen == {"method": "POST", "path": "/api/wellbore/v1/wellbores"}

def test_osdu_pull(monkeypatch):
    pid = _project_id()
    monkeypatch.setenv("GEOLOG_OSDU_URL", "https://osdu.example")
    monkeypatch.setattr(interop, "osdu_request", lambda cfg, method, path, body=None: (
        200, {"results": [{"data": {"WellName": "OSDU-1", "UWI": "OSDU-U1"}}]}
    ))
    r = client.post(f"/api/interop/osdu/pull?project_id={pid}", headers=I)
    assert r.status_code == 200, r.text
    assert r.json()["created"] >= 1
