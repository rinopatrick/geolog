"""Router module integrity.

tests/test_route_inventory.py proves every endpoint still exists. It does not
prove any of them work: a handler can reference a name that is not defined in its
module and still register fine.

That happened while extracting the project routes — the router called
`_create_job` while importing `create_job`, so
POST /api/projects/{pid}/batch-petro-async failed with "name '_create_job' is not
defined". The whole suite stayed green, because no test had ever executed that
handler. This module is the guard for that class of bug.

Two checks:

1. Static: every global name a handler references must be bound at module scope
   or be a builtin. Uses the `symtable` module, so scope analysis is Python's own
   rather than a regex approximation.
2. Dynamic: the extracted routers are actually called, so an import that resolves
   but a body that explodes is still caught.
"""

from __future__ import annotations

import builtins
import pathlib
import symtable
import sys

import pytest

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
ROUTER_DIR = REPO_ROOT / "backend" / "routers"
SHARED_MODULES = [REPO_ROOT / "backend" / "jobs.py", REPO_ROOT / "backend" / "deps.py"]

ALL_MODULES = sorted(ROUTER_DIR.glob("*.py")) + SHARED_MODULES
MODULE_IDS = [p.name for p in ALL_MODULES]

_BUILTINS = set(dir(builtins))

# Module dunders are supplied by the import system, not by the module body:
# __file__, __name__, __doc__, and (on newer Pythons) __conditional_annotations__.
def _is_module_dunder(name: str) -> bool:
    return name.startswith("__") and name.endswith("__")


def _module_scope_names(table: symtable.SymbolTable) -> set[str]:
    """Everything bound at module level, including inside try/except blocks."""
    names = set()
    for symbol in table.get_symbols():
        if symbol.is_assigned() or symbol.is_imported() or symbol.is_namespace():
            names.add(symbol.get_name())
    return names


def _free_globals(table: symtable.SymbolTable) -> set[str]:
    """Names referenced from a nested scope but not bound in it.

    Walks the whole tree so a handler nested inside another function is covered.
    """
    found: set[str] = set()
    for symbol in table.get_symbols():
        if symbol.is_referenced() and symbol.is_global():
            found.add(symbol.get_name())
    for child in table.get_children():
        found |= _free_globals(child)
    return found


@pytest.mark.parametrize("path", ALL_MODULES, ids=MODULE_IDS)
def test_no_unresolved_global_names(path):
    """A handler referencing an undefined name only fails when it is called."""
    source = path.read_text(encoding="utf-8")
    table = symtable.symtable(source, str(path), "exec")

    defined = _module_scope_names(table)
    referenced = _free_globals(table)

    unresolved = sorted(
        n for n in referenced
        if n not in defined and n not in _BUILTINS and not _is_module_dunder(n)
    )
    assert unresolved == [], (
        f"{path.name} references names that are not defined in the module and are "
        f"not builtins: {unresolved}. This raises NameError the first time the "
        f"handler runs."
    )


@pytest.mark.parametrize("path", ALL_MODULES, ids=MODULE_IDS)
def test_module_imports_cleanly(path):
    """A module that cannot be imported would take the whole app down."""
    import importlib

    name = f"backend.{path.parent.name}.{path.stem}" if path.parent.name == "routers" \
        else f"backend.{path.stem}"
    module = importlib.import_module(name)
    assert module is not None


@pytest.mark.parametrize("path", ALL_MODULES, ids=MODULE_IDS)
def test_every_router_declares_a_prefix(path):
    """Routers are mounted with include_router, so they need their own prefix."""
    if path.parent.name != "routers" or path.stem == "__init__":
        pytest.skip("not a router module")
    source = path.read_text(encoding="utf-8")
    assert "APIRouter(" in source, f"{path.name} does not create an APIRouter"
    assert "prefix=" in source, f"{path.name} declares no prefix"


# ─── Dynamic: actually call the extracted routers ───────────────


def test_log_run_routes_respond():
    """Exercise the extracted log-run handlers against seeded demo data."""
    from fastapi.testclient import TestClient

    from backend.main import SessionLocal, app
    from backend.models import LogRun

    client = TestClient(app)
    headers = {"X-User-Role": "interpreter"}

    db = SessionLocal()
    try:
        run = db.query(LogRun).order_by(LogRun.id.asc()).first()
        assert run is not None, "conftest should have seeded a log run"
        run_id = run.id
        other = db.query(LogRun).order_by(LogRun.id.desc()).first()
        other_id = other.id
    finally:
        db.close()

    calls = [
        ("GET", f"/api/log-runs/{run_id}/curves", None),
        ("POST", f"/api/log-runs/{run_id}/data",
         {"curve_mnemonics": ["GR"], "start_depth": 5000.0, "stop_depth": 5010.0}),
        ("GET", f"/api/log-runs/{run_id}/data-decimated", None),
        ("GET", f"/api/log-runs/{run_id}/depth-shift", None),
        ("POST", f"/api/log-runs/{run_id}/depth-shift", {"shift": 0.5, "stretch": 1.0}),
        ("POST", f"/api/log-runs/{run_id}/filter",
         {"mnemonic": "GR", "filter_type": "median", "window": 5}),
        ("POST", f"/api/log-runs/{run_id}/curve-edit",
         {"mnemonic": "GR", "edits": [{"index": 0, "value": 55.0}]}),
        ("POST", f"/api/log-runs/{run_id}/curve-override",
         {"mnemonic": "GR", "start": 5000.0, "end": 5010.0, "value": 42.0}),
        ("POST", f"/api/log-runs/{run_id}/shoulder-bed-correction",
         {"mnemonic": "GR", "method": "linear"}),
        ("POST", "/api/log-runs/diff",
         {"log_run_a_id": run_id, "log_run_b_id": other_id}),
    ]

    for method, path, body in calls:
        if method == "GET":
            response = client.get(path, headers=headers)
        else:
            response = client.post(path, json=body, headers=headers)
        assert response.status_code < 500, f"{method} {path} -> {response.status_code} {response.text[:200]}"


def test_project_routes_respond():
    """Exercise the extracted project handlers against seeded demo data."""
    from fastapi.testclient import TestClient

    from backend.main import SessionLocal, app
    from backend.models import Project, Well

    client = TestClient(app)
    headers = {"X-User-Role": "interpreter"}

    db = SessionLocal()
    try:
        project = db.query(Project).order_by(Project.id.asc()).first()
        assert project is not None, "conftest should have seeded a project"
        pid = project.id
        wid = db.query(Well).order_by(Well.id.asc()).first().id
    finally:
        db.close()

    calls = [
        ("GET", f"/api/projects/{pid}/well-comparison", None),
        ("GET", f"/api/projects/{pid}/strip-log-data", None),
        ("GET", f"/api/projects/{pid}/cross-section", None),
        ("GET", f"/api/projects/{pid}/tops-export", None),
        ("GET", f"/api/projects/{pid}/formation-matrix", None),
        ("GET", f"/api/projects/{pid}/summary", None),
        ("GET", f"/api/projects/{pid}/well-locations", None),
        ("GET", f"/api/projects/{pid}/crossplot-matrix", None),
    ]

    for method, path, body in calls:
        response = client.get(path, headers=headers)
        assert response.status_code < 500, f"{method} {path} -> {response.status_code} {response.text[:200]}"

    # well-analogs requires a reference well.
    response = client.get(
        f"/api/projects/{pid}/well-analogs",
        params={"reference_well_id": wid}, headers=headers,
    )
    assert response.status_code < 500, response.text[:200]


def test_ops_and_audit_routes_respond():
    """Exercise the extracted ops/audit handlers.

    Most of these had never been executed by any test, so a broken response model
    would only show up in production. The gate endpoint was in exactly that state.
    """
    from fastapi.testclient import TestClient

    from backend.main import app

    client = TestClient(app)
    viewer = {"X-User-Role": "viewer"}
    interpreter = {"X-User-Role": "interpreter"}

    read_paths = [
        "/api/ops/metrics",
        "/api/ops/metrics/recent",
        "/api/ops/metrics/prometheus",
        "/api/ops/slo-status",
        "/api/ops/alerts",
        "/api/ops/alert-rules",
        "/api/ops/health",
        "/api/ops/observability-status",
        "/api/ops/otel-status",
        "/api/ops/evidence-status",
        "/api/ops/security-posture-status",
        "/api/ops/security-evidence-status",
        "/api/ops/summary",
        "/api/ops/contracts",
        "/api/ops/runbook",
        "/api/ops/security-evidence/freshness",
        "/api/ops/security-evidence/gate",
        "/api/audit-log",
        "/api/audit-log/verify",
        "/api/audit-log/immutability-status",
        "/api/audit-log/verify/export",
    ]
    for path in read_paths:
        response = client.get(path, headers=viewer)
        assert response.status_code < 500, (
            f"GET {path} -> {response.status_code} {response.text[:200]}"
        )

    # gate/check always returns 200 by contract, and needs interpreter.
    assert client.post("/api/ops/security-evidence/gate/check", headers=interpreter).status_code == 200

    # gate/enforce is documented to return 503 when the gate fails, which is the
    # case with no attested evidence.
    assert client.get("/api/ops/security-evidence/gate/enforce", headers=viewer).status_code == 503

    # A viewer must not be able to assert the gate.
    assert client.post("/api/ops/security-evidence/gate/assert", headers=viewer).status_code == 403


def test_gate_response_model_accepts_every_reason_code_it_emits():
    """Regression: the gate's response model declared codes the handler never returns.

    attest_reason_code was typed as ATTEST_VALID | ATTEST_INVALID | ATTEST_ERROR,
    but _attest_security_evidence_payload returns MISSING_REPORT when nothing has
    been attested — the normal state of a fresh deployment. FastAPI then failed
    response validation and the endpoint raised 500.
    """
    import re

    source = (REPO_ROOT / "backend" / "routers" / "ops.py").read_text(encoding="utf-8")

    handler = source[source.index("def _attest_security_evidence_payload"):]
    handler = handler[: handler.index("\ndef ")]
    emitted = set(re.findall(r'"reason_code":\s*"([A-Z_]+)"', handler))
    assert emitted, "could not find any reason codes in the attestation handler"

    declared = set(re.findall(r'"([A-Z_]+)"', re.search(
        r"OpsEvidenceAttestReasonCode = Literal\[[^\]]*\]", source
    ).group(0)))
    assert emitted <= declared, (
        f"the handler emits codes the Literal does not declare: {sorted(emitted - declared)}"
    )

    # And the gate response must reference that alias, not a narrower literal.
    gate_model = source[source.index("class OpsSecurityEvidenceGateResponse"):]
    gate_model = gate_model[: gate_model.index("\nclass ")]
    assert "attest_reason_code: OpsEvidenceAttestReasonCode" in gate_model, (
        "the gate response narrowed attest_reason_code to a literal that does not "
        "cover the handler's outputs"
    )


def test_metrics_middleware_and_ops_routes_share_state():
    """The counters moved to backend/observability.py; the wiring must still work."""
    from fastapi.testclient import TestClient

    from backend.main import app
    from backend.observability import OBS_METRICS

    client = TestClient(app)
    headers = {"X-User-Role": "viewer"}

    before = OBS_METRICS["requests_total"]
    client.get("/api/ops/health", headers=headers)
    client.get("/api/ops/health", headers=headers)
    after = OBS_METRICS["requests_total"]

    assert after > before, "requests are not reaching the shared counters"

    reported = client.get("/api/ops/metrics", headers=headers).json()
    assert reported["requests_total"] >= after, (
        "the ops route is reading a different counter object than the middleware writes"
    )


def test_audit_router_reuses_the_shared_signing_helpers():
    """Both routers verify signatures through backend/audit.py, not their own copy."""
    from backend.audit import (
        resolve_audit_export_signing_key,
        verify_audit_export_signature_payload,
    )
    from backend.routers import audit as audit_router_module
    from backend.routers import ops as ops_router_module

    assert audit_router_module.verify_audit_export_signature_payload is verify_audit_export_signature_payload
    assert ops_router_module.verify_audit_export_signature_payload is verify_audit_export_signature_payload
    assert ops_router_module.resolve_audit_export_signing_key is resolve_audit_export_signing_key


def test_well_export_bundle_is_a_valid_zip(make_well):
    """Regression: the bundle referenced model fields that do not exist.

    export_client_bundle built tops.csv from t.name (the model has
    formation_name) and zones.csv from z.zone_name / z.sw_avg / z.net_to_gross
    (Zone stores name, top_depth, bottom_depth, color only), so every call raised
    AttributeError and returned 500. It had never worked.
    """
    import io
    import zipfile

    from fastapi.testclient import TestClient

    from backend.main import SessionLocal, app
    from backend.models import FormationTop, Well, Zone

    client = TestClient(app)
    headers = {"X-User-Role": "interpreter"}

    n = 60
    wid = make_well("bundle-well", {
        "DEPT": [1000.0 + i for i in range(n)],
        "GR": [50.0 + i for i in range(n)],
        "RHOB": [2.4] * n,
        "NPI": [0.25] * n,
    })

    # Give it a top and a zone so both CSV branches execute.
    db = SessionLocal()
    try:
        db.add(FormationTop(well_id=wid, formation_name="Test Fm", depth=1010.0,
                            color="#ff0000", lithology="Sandstone"))
        db.add(Zone(well_id=wid, name="Zone A", top_depth=1000.0, bottom_depth=1030.0))
        db.commit()
    finally:
        db.close()

    response = client.get(f"/api/wells/{wid}/export-bundle", headers=headers)
    assert response.status_code == 200, response.text[:200]

    archive = zipfile.ZipFile(io.BytesIO(response.content))
    names = archive.namelist()
    assert any(n.endswith(".las") for n in names), names
    assert "tops.csv" in names
    assert "zones.csv" in names
    assert "report.md" in names

    tops_csv = archive.read("tops.csv").decode()
    assert tops_csv.splitlines()[0] == "depth,formation_name,color,lithology"
    assert "Test Fm" in tops_csv

    zones_csv = archive.read("zones.csv").decode()
    assert zones_csv.splitlines()[0] == "name,top_depth,bottom_depth,color"
    assert "Zone A" in zones_csv

    report = archive.read("report.md").decode()
    assert "Test Fm" in report
    assert "Zone A" in report


def test_async_job_producers_complete(make_well):
    """The job registry moved modules; every producer must still work.

    This is the check that would have caught the _create_job NameError.

    Uses a well created for this test rather than a seeded one: an earlier test
    approves a snapshot on the first seeded well, which locks it, and a write
    endpoint then correctly returns 423. Depending on another test's leftover
    lock state is not a property of this code.
    """
    import time

    import numpy as np
    from fastapi.testclient import TestClient

    from backend.main import Project, SessionLocal, app

    client = TestClient(app)
    headers = {"X-User-Role": "interpreter"}

    # Enough points for the seismogram/electrofacies maths to have something to
    # work with, and the curves each producer looks for.
    n = 200
    depth = [5000.0 + i * 0.5 for i in range(n)]
    rng = np.random.default_rng(11)
    curves = {
        "DEPT": depth,
        "GR": list(np.clip(60 + rng.normal(0, 12, n), 5, 150)),
        "NPHI": list(np.clip(0.28 + rng.normal(0, 0.03, n), 0.02, 0.5)),
        "RHOB": list(np.clip(2.35 + rng.normal(0, 0.04, n), 1.9, 2.9)),
        "DT": list(np.clip(75 + rng.normal(0, 5, n), 45, 140)),
        "RT": list(np.clip(15 + rng.normal(0, 3, n), 0.5, 500)),
    }
    wid = make_well("job-producer-well", curves)

    db = SessionLocal()
    try:
        pid = db.query(Project).order_by(Project.id.asc()).first().id
    finally:
        db.close()

    producers = [
        (f"/api/projects/{pid}/batch-petro-async",
         {"params": {"a": 1.0, "m": 2.0, "n": 2.0, "rw": 0.1}}),
        (f"/api/wells/{wid}/synthetic-seismogram-async", {}),
        (f"/api/wells/{wid}/electrofacies-async", {"n_clusters": 3}),
    ]

    for path, body in producers:
        response = client.post(path, json=body, headers=headers)
        assert response.status_code in (200, 202), (
            f"POST {path} -> {response.status_code} {response.text[:200]}"
        )
        job_id = response.json().get("job_id")
        assert job_id, f"POST {path} returned no job_id"

        # Poll briefly: the jobs are submitted to a 2-worker pool.
        status = None
        for _ in range(40):
            time.sleep(0.1)
            status = client.get(f"/api/jobs/{job_id}", headers=headers).json()
            if status.get("status") in ("done", "failed"):
                break
        assert status is not None
        assert status.get("status") == "done", (
            f"{path} job ended as {status.get('status')}: {status.get('error')}"
        )

    listing = client.get("/api/jobs", headers=headers).json()
    assert listing["total"] >= len(producers)
    assert len(listing["jobs"]) == listing["total"]
