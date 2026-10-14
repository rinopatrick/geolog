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

    from backend.main import LogRun, SessionLocal, app

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

    from backend.main import Project, SessionLocal, Well, app

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
