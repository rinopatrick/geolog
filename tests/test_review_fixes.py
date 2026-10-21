"""Regression tests for the issues found in the full-codebase review."""

from __future__ import annotations

import datetime
import hashlib
import json

import jwt
import numpy as np
import pytest
from fastapi.testclient import TestClient

from backend import main as main_mod
from backend.main import SessionLocal, app
from backend.models import Annotation, CurveData, LogRun, User, Well
from backend.validation import canonical_json

client = TestClient(app)
ADMIN = {"X-User-Role": "admin"}
INTERPRETER = {"X-User-Role": "interpreter"}
VIEWER = {"X-User-Role": "viewer"}

def _jwt(role: str, secret: str = "review-secret-1234567890") -> str:
    now = datetime.datetime.now(datetime.timezone.utc)
    return jwt.encode(
        {"sub": f"user-{role}", "role": role, "exp": int((now + datetime.timedelta(hours=1)).timestamp())},
        secret,
        algorithm="HS256",
    )

@pytest.fixture
def jwt_mode():
    old = (main_mod.AUTH_CONFIG.mode, main_mod.AUTH_CONFIG.jwt_secret, main_mod.AUTH_CONFIG.jwt_algorithms)
    main_mod.AUTH_CONFIG.mode = "jwt"
    main_mod.AUTH_CONFIG.jwt_secret = "review-secret-1234567890"
    main_mod.AUTH_CONFIG.jwt_algorithms = ("HS256",)
    try:
        yield
    finally:
        main_mod.AUTH_CONFIG.mode, main_mod.AUTH_CONFIG.jwt_secret, main_mod.AUTH_CONFIG.jwt_algorithms = old

def _first_well_id() -> int:
    from backend.models import Well
    db = SessionLocal()
    try:
        return db.query(Well).order_by(Well.id.asc()).first().id
    finally:
        db.close()

def _first_run_id() -> int:
    db = SessionLocal()
    try:
        return db.query(LogRun).order_by(LogRun.id.asc()).first().id
    finally:
        db.close()

# ─── Auth: public paths, header spoofing, viewer writes ─────────

def test_jwt_mode_allows_login_health_and_static(jwt_mode):
    assert client.get("/api/health").status_code == 200
    assert client.get("/docs").status_code == 200
    assert client.get("/static/index.html").status_code == 200
    # Reaches the handler (unknown user) instead of being rejected by middleware.
    assert client.post("/api/users/token", json={"username": "missing"}).status_code == 401
    # Protected routes still require a token.
    assert client.get("/api/wells").status_code == 401

def test_interpreter_cannot_spoof_admin_header(jwt_mode):
    wid = _first_well_id()
    interp = {"Authorization": f"Bearer {_jwt('interpreter')}"}
    spoofed = {**interp, "X-User-Role": "admin"}
    r = client.post(f"/api/wells/{wid}/unlock", headers=spoofed, json={})
    assert r.status_code == 403, r.text

    admin = {"Authorization": f"Bearer {_jwt('admin')}"}
    r = client.post(f"/api/wells/{wid}/unlock", headers=admin, json={})
    assert r.status_code == 200, r.text

def test_jwt_interpreter_can_lock_template_without_role_header(jwt_mode):
    wid = _first_well_id()
    interp = {"Authorization": f"Bearer {_jwt('interpreter')}"}
    r = client.post(f"/api/wells/{wid}/template-lock", headers=interp, json={})
    assert r.status_code == 200, r.text
    admin = {"Authorization": f"Bearer {_jwt('admin')}"}
    r = client.post(f"/api/wells/{wid}/template-unlock", headers=admin, json={})
    assert r.status_code == 200, r.text

def test_viewer_cannot_write_curve_data():
    lrid = _first_run_id()
    r = client.post(
        f"/api/log-runs/{lrid}/curve-override",
        headers=VIEWER,
        json={"mnemonic": "GR", "start": 1000, "end": 1001, "value": 1},
    )
    assert r.status_code == 403, r.text
    r = client.post(
        f"/api/log-runs/{lrid}/data",
        headers=VIEWER,
        json={"curve_mnemonics": ["GR"]},
    )
    assert r.status_code == 200, r.text

def test_collab_websocket_requires_token(jwt_mode, make_well):
    from starlette.websockets import WebSocketDisconnect

    wid = make_well("WS", {"DEPT": [1000.0, 1001.0], "GR": [10.0, 11.0]})
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect(f"/ws/collab/{wid}?user=anonymous") as ws:
            ws.receive_json()

    token = _jwt("viewer")
    with client.websocket_connect(f"/ws/collab/{wid}?user=u1&token={token}") as ws:
        msg = ws.receive_json()
        assert msg["type"] == "peers"

# ─── Curve dtype / depth ────────────────────────────────────────

def test_curve_readers_use_float64(make_well):
    wid = make_well("DTYPE", {
        "DEPT": np.arange(1000.0, 1010.0),
        "GR": np.arange(10.0),
    })
    db = SessionLocal()
    try:
        from backend.routers.correlation import _load_curve
        from backend.routers.qc import _curve_array
        from backend.routers.zonation import _extract_curve

        lr = db.query(LogRun).filter(LogRun.well_id == wid).first()
        cd = db.query(CurveData).filter_by(log_run_id=lr.id, mnemonic="GR").first()
        assert np.allclose(_curve_array(cd, 10), np.arange(10.0))
        _, depth, values, _ = _load_curve(db, wid, "GR")
        assert np.allclose(depth, np.arange(1000.0, 1010.0))
        assert np.allclose(values, np.arange(10.0))
        arr, _ = _extract_curve(db, lr.id, ["GR"])
        assert np.allclose(arr, np.arange(10.0))
    finally:
        db.close()

def test_advanced_qc_reports_real_values():
    from backend.routers.qc import _curve_array

    class Row:
        data_binary = np.array([1.5, 2.5, np.nan], dtype=np.float64).tobytes()

    arr = _curve_array(Row(), 3)
    assert arr.dtype == np.float64
    assert np.allclose(arr, [1.5, 2.5, np.nan], equal_nan=True)

# ─── Deletion cleanup and lock/snapshot state ───────────────────

def test_delete_well_removes_children_and_state():
    r = client.post("/api/wells/", json={"project_id": 1, "name": "CLEANUP-WELL"}, headers=ADMIN)
    assert r.status_code == 201, r.text
    wid = r.json()["id"]
    try:
        assert client.post(f"/api/wells/{wid}/annotations", json={"depth": 1000, "text": "secret"}, headers=INTERPRETER).status_code == 201
        assert client.post(f"/api/wells/{wid}/production", json={"date": "2020-01-01", "oil_rate": 5}, headers=INTERPRETER).status_code == 201
        assert client.post(f"/api/wells/{wid}/petro-params", json={"a": 9.9}, headers=INTERPRETER).status_code == 200
        partner = next(w["id"] for w in client.get("/api/wells").json() if w["id"] != wid)
        assert client.post(
            "/api/correlation-profile",
            json={"well_a_id": wid, "well_b_id": partner, "depth_shift": 5},
            headers=INTERPRETER,
        ).status_code == 201
        snap = client.post(f"/api/wells/{wid}/snapshots", json={"label": "x"}, headers=INTERPRETER).json()
        assert client.post(f"/api/wells/{wid}/snapshots/{snap['snapshot_id']}/approve", json={}, headers=INTERPRETER).status_code == 200

        assert client.delete(f"/api/wells/{wid}", headers=ADMIN).status_code == 204

        new = client.post("/api/wells/", json={"project_id": 1, "name": "AFTER-CLEANUP"}, headers=ADMIN)
        assert new.status_code == 201, new.text
        new_id = new.json()["id"]
        try:
            assert client.get(f"/api/wells/{new_id}/annotations").json() == []
            assert client.get(f"/api/wells/{new_id}/production").json() == []
            assert client.get(f"/api/wells/{new_id}/petro-params").json()["a"] == 1.0
            assert client.get(f"/api/wells/{new_id}/lock-status").json().get("locked") is False
            assert client.get(f"/api/wells/{new_id}/snapshots").json()["count"] == 0
            profile = client.get(f"/api/correlation-profile?well_a_id={new_id}&well_b_id={partner}").json()
            assert profile["depth_shift"] == 0.0
        finally:
            client.delete(f"/api/wells/{new_id}", headers=ADMIN)
    finally:
        client.delete(f"/api/wells/{wid}", headers=ADMIN)

def test_delete_project_removes_child_well_data():
    p = client.post("/api/projects/", json={"name": "CLEANUP-PROJECT"}, headers=ADMIN)
    assert p.status_code == 201, p.text
    pid = p.json()["id"]
    w = client.post("/api/wells/", json={"project_id": pid, "name": "CHILD"}, headers=ADMIN)
    assert w.status_code == 201, w.text
    wid = w.json()["id"]
    assert client.post(f"/api/wells/{wid}/annotations", json={"depth": 1, "text": "x"}, headers=INTERPRETER).status_code == 201

    assert client.delete(f"/api/projects/{pid}", headers=ADMIN).status_code == 204

    db = SessionLocal()
    try:
        assert db.query(Well).filter(Well.id == wid).first() is None
        assert db.query(Annotation).filter(Annotation.well_id == wid).count() == 0
    finally:
        db.close()

def test_create_well_rejects_missing_project():
    r = client.post("/api/wells/", json={"project_id": 999999, "name": "ORPHAN"}, headers=ADMIN)
    assert r.status_code == 400, r.text

# ─── Auto-zone without scipy ───────────────────────────────────

def test_auto_zone_from_tops_without_scipy(make_well):
    n = 500
    t = np.arange(n)
    wid = make_well("AUTOZONE", {
        "DEPT": 1000.0 + t,
        "GR": 50.0 + 40.0 * np.sin(t / 20.0),
    })
    r = client.post(f"/api/wells/{wid}/auto-zone-from-tops", headers=INTERPRETER)
    assert r.status_code == 200, r.text
    assert r.json()["zones_created"] >= 1

# ─── Validation: 400 not 500 ────────────────────────────────────

@pytest.mark.parametrize("path,body", [
    ("petro-params", {"a": "abc"}),
    ("zones", {"zones": [{"top": "abc", "bottom": 2}]}),
    ("save-picks", {"picks": [{"formation_name": "X", "depth": "abc"}]}),
    ("production", {"date": "2020-01-01", "oil_rate": "abc"}),
    ("aliases", {"aliases": [{}]}),
    ("trajectory", {"points": [{"md": 100}]}),
    ("template-preview", {"template_name": 123}),
])
def test_bad_input_returns_400(path, body):
    wid = _first_well_id()
    r = client.post(f"/api/wells/{wid}/{path}", json=body, headers=INTERPRETER)
    assert r.status_code == 400, f"{path}: {r.status_code} {r.text[:200]}"

def test_bad_depth_shift_returns_400():
    lrid = _first_run_id()
    r = client.post(f"/api/log-runs/{lrid}/depth-shift", json={"shift": "abc"}, headers=INTERPRETER)
    assert r.status_code == 400, r.text

# ─── Calibration labels ────────────────────────────────────────

def test_core_calibration_reports_only_matched_depths(make_well):
    wid = make_well("CAL", {
        "DEPT": np.array([1000.0, 1001.0, 1002.0, 1003.0, 1004.0]),
        "NPHI": np.array([0.1, 0.2, 0.3, 0.4, 0.5]),
    })
    r = client.post(
        f"/api/wells/{wid}/core-calibration",
        headers=INTERPRETER,
        json={
            "core_depth": [1000.0, 1001.0, 5000.0, 1002.0],
            "core_phi": [0.11, 0.21, 0.99, 0.31],
            "log_curve": "NPHI",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["matched_depth"] == [1000.0, 1001.0, 1002.0]

# ─── Bulk upload ───────────────────────────────────────────────

def test_bulk_upload_accepts_multipart(make_well):
    wid = make_well("BULK", {"DEPT": [1000.0, 1001.0], "GR": [10.0, 11.0]})
    content = open("data/public_sample.las", "rb").read()
    files = [
        ("files", ("a.las", content, "text/plain")),
        ("files", ("b.las", content, "text/plain")),
    ]
    r = client.post(f"/api/wells/{wid}/bulk-upload", files=files, headers=INTERPRETER)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["uploaded"] == 2, data
    assert all(item["status"] == "ok" for item in data["results"]), data

def test_metrics_refresh_reads_another_workers_file(tmp_path, monkeypatch):
    from backend import observability

    path = tmp_path / "metrics.json"
    monkeypatch.setattr(observability, "METRICS_FILE", str(path))
    path.write_text(json.dumps({"requests_total": 7, "latency_ms_count": 0, "recent_events": []}), encoding="utf-8")
    observability.OBS_METRICS.clear()
    observability.refresh_metrics()
    assert observability.OBS_METRICS["requests_total"] == 7

def test_filter_and_splice_still_compute(make_well):
    wid = make_well("PERF", {
        "DEPT": np.array([1000.0, 1001.0, 1002.0, 1003.0, 1004.0]),
        "GR": np.array([1.0, 2.0, 3.0, 4.0, 5.0]),
    })
    db = SessionLocal()
    try:
        lr1 = db.query(LogRun).filter(LogRun.well_id == wid).first()
        lr2 = LogRun(
            well_id=wid, run_number=2, filename="second.las",
            start_depth=1000.0, stop_depth=1004.0, step=1.0, num_points=5,
        )
        db.add(lr2)
        db.flush()
        db.add(CurveData(log_run_id=lr2.id, mnemonic="DEPT", num_points=5,
                         data_binary=np.array([1000.0, 1001.0, 1002.0, 1003.0, 1004.0]).tobytes()))
        db.add(CurveData(log_run_id=lr2.id, mnemonic="GR", num_points=5,
                         data_binary=np.array([10.0, 20.0, 30.0, 40.0, 50.0]).tobytes()))
        db.commit()
        lr1_id, lr2_id = lr1.id, lr2.id
    finally:
        db.close()

    r = client.post(
        f"/api/log-runs/{lr1_id}/filter",
        headers=INTERPRETER,
        json={"mnemonic": "GR", "filter": "smooth", "window": 3},
    )
    assert r.status_code == 200, r.text
    db = SessionLocal()
    try:
        filtered = db.query(CurveData).filter_by(log_run_id=lr1_id, mnemonic="GR_S3").first()
        assert filtered is not None
        values = np.frombuffer(filtered.data_binary, dtype=np.float64)
        assert np.allclose(values, [1.0 + 1.0 / 3.0, 2.0, 3.0, 4.0, 5.0 - 1.0 / 3.0])
    finally:
        db.close()

    r = client.post(
        f"/api/wells/{wid}/splice",
        headers=INTERPRETER,
        json={
            "source_runs": [lr1_id, lr2_id],
            "intervals": [{"start": 1001.0, "end": 1003.0, "source_lr_id": lr2_id}],
            "mnemonic": "GR",
        },
    )
    assert r.status_code == 200, r.text
    new_run = r.json()["log_run_id"]
    db = SessionLocal()
    try:
        spliced = db.query(CurveData).filter_by(log_run_id=new_run, mnemonic="GR").first()
        values = np.frombuffer(spliced.data_binary, dtype=np.float64)
        assert np.allclose(values, [1.0, 20.0, 30.0, 40.0, 5.0])
    finally:
        db.close()

def test_dlis_fallback_reports_a_warning():
    from backend.dlis_lis_parser import parse_dlis_content

    tokens = []
    for i in range(10):
        tokens.extend([str(1000.0 + i), str(40.0 + i), str(2.5)])
    parsed = parse_dlis_content(("HEADER " + " ".join(tokens)).encode("latin1"), "x.dlis")
    assert parsed.warnings, "fallback parser must tell the caller the curves are heuristic"

# ─── Ops evidence / numpy compatibility ────────────────────────

def test_attestation_rejects_unknown_algorithm():
    report = {"drill": "ok"}
    sha = hashlib.sha256(canonical_json(report).encode()).hexdigest()
    r = client.post(
        "/api/ops/security-evidence/attest",
        headers=INTERPRETER,
        json={
            "report": report,
            "signature": {
                "report_sha256": sha,
                "signature_alg": "none",
                "signature": "0" * 64,
            },
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["reason_code"] == "UNSUPPORTED_ALG", r.text

def test_eur_works_on_current_numpy():
    from backend.routers.wells import _compute_eur
    eur = _compute_eur({"model": "exponential", "qi": 100.0, "d": 0.001}, days_to_limit=100.0)
    assert eur is not None and eur > 0

# ─── Token issuance ────────────────────────────────────────────

def test_user_token_generation_is_random(monkeypatch):
    monkeypatch.setenv("AUTH_JWT_SECRET", "review-secret-1234567890")
    names = ["random_user_a", "random_user_b"]
    tokens = []
    try:
        for name in names:
            r = client.post("/api/users", json={"username": name, "role": "viewer"}, headers=ADMIN)
            assert r.status_code in (201, 409), r.text
            if r.status_code == 201:
                tokens.append(r.json()["token"])
        if len(tokens) == 2:
            assert tokens[0] != tokens[1]
            assert len(tokens[0]) >= 32
    finally:
        db = SessionLocal()
        try:
            for name in names:
                db.query(User).filter(User.username == name).delete()
            db.commit()
        finally:
            db.close()
