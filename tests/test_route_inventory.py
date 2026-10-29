"""Route inventory.

Splitting a 9.6k-line module into routers is a mechanical refactor, and the
easiest way to get it wrong is to silently drop or rename an endpoint. This pins
the whole public surface, taken from the OpenAPI schema (which sees routes
contributed by sub-routers; `app.routes` does not).

If an endpoint is added or removed on purpose, update EXPECTED_ROUTES in the same
commit so the change shows up in review.
"""

from __future__ import annotations

import warnings

EXPECTED_ROUTES = [
    "DELETE /api/annotations/{aid}",
    "DELETE /api/completion/{cid}",
    "DELETE /api/log-runs/{lr_id}",
    "DELETE /api/log-runs/{lr_id}/depth-control-points",
    "DELETE /api/projects/{pid}",
    "DELETE /api/projects/{pid}/members/{subject}",
    "DELETE /api/tops/{tid}",
    "DELETE /api/users/{uid}",
    "DELETE /api/wells/{wid}",
    "DELETE /api/wells/{wid}/core/contacts/{contact_id}",
    "DELETE /api/wells/{wid}/core/plugs/{plug_id}",
    "DELETE /api/wells/{wid}/image-assets/{asset_id}",
    "DELETE /api/wells/{wid}/image-assets/{asset_id}/dips/{dip_id}",
    "DELETE /api/wells/{wid}/members/{subject}",
    "GET /api/audit-log",
    "GET /api/audit-log/immutability-status",
    "GET /api/audit-log/verify",
    "GET /api/audit-log/verify/export",
    "GET /api/audit-log/verify/signature",
    "GET /api/correlation-markers",
    "GET /api/correlation-profile",
    "GET /api/correlation/cross-section",
    "GET /api/correlation/tie-lines",
    "GET /api/curve-config",
    "GET /api/health",
    "GET /api/interop/config",
    "GET /api/jobs",
    "GET /api/jobs/{job_id}",
    "GET /api/log-runs/{lr_id}/curves",
    "GET /api/log-runs/{lr_id}/data-decimated",
    "GET /api/log-runs/{lr_id}/depth-control-points",
    "GET /api/log-runs/{lr_id}/depth-shift",
    "GET /api/ops/alert-rules",
    "GET /api/ops/alerts",
    "GET /api/ops/contracts",
    "GET /api/ops/contracts/verify-signature",
    "GET /api/ops/evidence-status",
    "GET /api/ops/health",
    "GET /api/ops/metrics",
    "GET /api/ops/metrics/prometheus",
    "GET /api/ops/metrics/recent",
    "GET /api/ops/observability-status",
    "GET /api/ops/otel-status",
    "GET /api/ops/runbook",
    "GET /api/ops/security-evidence-status",
    "GET /api/ops/security-evidence/attest/latest",
    "GET /api/ops/security-evidence/freshness",
    "GET /api/ops/security-evidence/gate",
    "GET /api/ops/security-evidence/gate/enforce",
    "GET /api/ops/security-evidence/manifest",
    "GET /api/ops/security-evidence/manifest/verify-signature",
    "GET /api/ops/security-posture-status",
    "GET /api/ops/slo-status",
    "GET /api/ops/summary",
    "GET /api/projects/",
    "GET /api/projects/{pid}/cross-section",
    "GET /api/projects/{pid}/crossplot-matrix",
    "GET /api/projects/{pid}/formation-matrix",
    "GET /api/projects/{pid}/members",
    "GET /api/projects/{pid}/strip-log-data",
    "GET /api/projects/{pid}/summary",
    "GET /api/projects/{pid}/tops-export",
    "GET /api/projects/{pid}/well-analogs",
    "GET /api/projects/{pid}/well-comparison",
    "GET /api/projects/{pid}/well-locations",
    "GET /api/regression/smoke",
    "GET /api/templates",
    "GET /api/templates/{name}",
    "GET /api/unit-conversions",
    "GET /api/users",
    "GET /api/version",
    "GET /api/well-compare",
    "GET /api/wells/",
    "GET /api/wells/{wid}",
    "GET /api/wells/{wid}/advanced-qc",
    "GET /api/wells/{wid}/advanced-qc/env-flags",
    "GET /api/wells/{wid}/advanced-qc/missing-intervals",
    "GET /api/wells/{wid}/advanced-qc/spikes",
    "GET /api/wells/{wid}/aliases",
    "GET /api/wells/{wid}/annotations",
    "GET /api/wells/{wid}/completion",
    "GET /api/wells/{wid}/core/contacts",
    "GET /api/wells/{wid}/core/datasets",
    "GET /api/wells/{wid}/core/flow-units",
    "GET /api/wells/{wid}/core/plugs",
    "GET /api/wells/{wid}/core/plugs/{plug_id}",
    "GET /api/wells/{wid}/core/plugs/{plug_id}/depth-matches",
    "GET /api/wells/{wid}/core/rock-types",
    "GET /api/wells/{wid}/core/saturation-height/models",
    "GET /api/wells/{wid}/data-table",
    "GET /api/wells/{wid}/delivery-bundle",
    "GET /api/wells/{wid}/dst",
    "GET /api/wells/{wid}/export-bundle",
    "GET /api/wells/{wid}/export-las",
    "GET /api/wells/{wid}/export-package",
    "GET /api/wells/{wid}/formation-tester",
    "GET /api/wells/{wid}/geomechanics/models",
    "GET /api/wells/{wid}/geomechanics/models/{model_id}",
    "GET /api/wells/{wid}/geomechanics/report",
    "GET /api/wells/{wid}/geomechanics/runs",
    "GET /api/wells/{wid}/image-assets",
    "GET /api/wells/{wid}/image-assets/{asset_id}",
    "GET /api/wells/{wid}/image-assets/{asset_id}/dips",
    "GET /api/wells/{wid}/image-assets/{asset_id}/file",
    "GET /api/wells/{wid}/image-log",
    "GET /api/wells/{wid}/lock-status",
    "GET /api/wells/{wid}/log-runs",
    "GET /api/wells/{wid}/members",
    "GET /api/wells/{wid}/nmr/inversions",
    "GET /api/wells/{wid}/nmr/inversions/{inversion_id}",
    "GET /api/wells/{wid}/nmr/inversions/{inversion_id}/distribution",
    "GET /api/wells/{wid}/petro-params",
    "GET /api/wells/{wid}/production",
    "GET /api/wells/{wid}/production/decline-curve",
    "GET /api/wells/{wid}/report",
    "GET /api/wells/{wid}/report-pdf",
    "GET /api/wells/{wid}/rft",
    "GET /api/wells/{wid}/rft/pressure-gradient",
    "GET /api/wells/{wid}/snapshots",
    "GET /api/wells/{wid}/snapshots/{base_id}/diff/{target_id}",
    "GET /api/wells/{wid}/snapshots/{snapshot_id}",
    "GET /api/wells/{wid}/template-comparison",
    "GET /api/wells/{wid}/template-lock-status",
    "GET /api/wells/{wid}/tops",
    "GET /api/wells/{wid}/tops-petrel",
    "GET /api/wells/{wid}/trajectory",
    "GET /api/wells/{wid}/unit-map",
    "GET /api/wells/{wid}/zonation-report",
    "GET /api/wells/{wid}/zone-report",
    "GET /api/wells/{wid}/zone-report/csv",
    "GET /api/wells/{wid}/zone-report/pdf",
    "GET /api/wells/{wid}/zone-stats",
    "GET /api/wells/{wid}/zones",
    "POST /api/audit-log/verify/signature",
    "POST /api/correlation-markers",
    "POST /api/correlation-profile",
    "POST /api/correlation/auto-correlate",
    "POST /api/interop/osdu/pull",
    "POST /api/interop/osdu/pull-logs",
    "POST /api/interop/osdu/push/wells/{wid}",
    "POST /api/interop/osdu/test",
    "POST /api/interop/witsml/pull",
    "POST /api/interop/witsml/test",
    "POST /api/log-runs/diff",
    "POST /api/log-runs/{lr_id}/curve-edit",
    "POST /api/log-runs/{lr_id}/curve-override",
    "POST /api/log-runs/{lr_id}/data",
    "POST /api/log-runs/{lr_id}/depth-shift",
    "POST /api/log-runs/{lr_id}/filter",
    "POST /api/log-runs/{lr_id}/shoulder-bed-correction",
    "POST /api/ops/contracts/verify-signature",
    "POST /api/ops/security-evidence/attest",
    "POST /api/ops/security-evidence/gate/assert",
    "POST /api/ops/security-evidence/gate/check",
    "POST /api/ops/security-evidence/manifest/verify-signature",
    "POST /api/projects/",
    "POST /api/projects/{pid}/batch-petro",
    "POST /api/projects/{pid}/batch-petro-async",
    "POST /api/projects/{pid}/members",
    "POST /api/users",
    "POST /api/users/refresh",
    "POST /api/users/revoke",
    "POST /api/users/token",
    "POST /api/users/{uid}/rotate-token",
    "POST /api/wells/",
    "POST /api/wells/{wid}/aliases",
    "POST /api/wells/{wid}/annotations",
    "POST /api/wells/{wid}/apply-template",
    "POST /api/wells/{wid}/auto-pick-tops",
    "POST /api/wells/{wid}/auto-zone",
    "POST /api/wells/{wid}/auto-zone-from-tops",
    "POST /api/wells/{wid}/buckles",
    "POST /api/wells/{wid}/bulk-upload",
    "POST /api/wells/{wid}/completion",
    "POST /api/wells/{wid}/completion/upload-csv",
    "POST /api/wells/{wid}/compute-sw",
    "POST /api/wells/{wid}/core-calibration",
    "POST /api/wells/{wid}/core/contacts",
    "POST /api/wells/{wid}/core/datasets/{dataset_id}/approve",
    "POST /api/wells/{wid}/core/depth-matches/{match_id}/apply",
    "POST /api/wells/{wid}/core/flow-units/cluster",
    "POST /api/wells/{wid}/core/import",
    "POST /api/wells/{wid}/core/plugs",
    "POST /api/wells/{wid}/core/plugs/{plug_id}/capillary-pressure",
    "POST /api/wells/{wid}/core/plugs/{plug_id}/depth-match",
    "POST /api/wells/{wid}/core/plugs/{plug_id}/measurements",
    "POST /api/wells/{wid}/core/plugs/{plug_id}/photos",
    "POST /api/wells/{wid}/core/plugs/{plug_id}/photos/upload",
    "POST /api/wells/{wid}/core/plugs/{plug_id}/relative-perm",
    "POST /api/wells/{wid}/core/plugs/{plug_id}/thin-sections",
    "POST /api/wells/{wid}/core/plugs/{plug_id}/thin-sections/upload",
    "POST /api/wells/{wid}/core/rock-types",
    "POST /api/wells/{wid}/core/saturation-height/apply",
    "POST /api/wells/{wid}/core/saturation-height/fit",
    "POST /api/wells/{wid}/core/saturation-height/models/{model_id}/approve",
    "POST /api/wells/{wid}/curve-calc",
    "POST /api/wells/{wid}/depth-match",
    "POST /api/wells/{wid}/dip-plot",
    "POST /api/wells/{wid}/dst",
    "POST /api/wells/{wid}/dual-water",
    "POST /api/wells/{wid}/electrofacies",
    "POST /api/wells/{wid}/electrofacies-async",
    "POST /api/wells/{wid}/geomechanics/breakout-calibration",
    "POST /api/wells/{wid}/geomechanics/compute",
    "POST /api/wells/{wid}/geomechanics/models",
    "POST /api/wells/{wid}/geomechanics/models/{model_id}/approve",
    "POST /api/wells/{wid}/hingle",
    "POST /api/wells/{wid}/image-assets",
    "POST /api/wells/{wid}/image-assets/import-dlis",
    "POST /api/wells/{wid}/image-assets/{asset_id}/dips",
    "POST /api/wells/{wid}/image-assets/{asset_id}/dips/{dip_id}/approve",
    "POST /api/wells/{wid}/image-log",
    "POST /api/wells/{wid}/lithology",
    "POST /api/wells/{wid}/members",
    "POST /api/wells/{wid}/moveable-oil",
    "POST /api/wells/{wid}/multimineral",
    "POST /api/wells/{wid}/nmr/interpret",
    "POST /api/wells/{wid}/nmr/invert-async",
    "POST /api/wells/{wid}/normalize-units",
    "POST /api/wells/{wid}/permeability",
    "POST /api/wells/{wid}/permeability-multi",
    "POST /api/wells/{wid}/petro-params",
    "POST /api/wells/{wid}/probability-plot",
    "POST /api/wells/{wid}/production",
    "POST /api/wells/{wid}/production/economics",
    "POST /api/wells/{wid}/production/upload-csv",
    "POST /api/wells/{wid}/qc-autofix",
    "POST /api/wells/{wid}/resolve-aliases",
    "POST /api/wells/{wid}/rft",
    "POST /api/wells/{wid}/rft/upload-csv",
    "POST /api/wells/{wid}/rw-estimation",
    "POST /api/wells/{wid}/save-picks",
    "POST /api/wells/{wid}/seismic-tie",
    "POST /api/wells/{wid}/sensitivity",
    "POST /api/wells/{wid}/snapshots",
    "POST /api/wells/{wid}/snapshots/{snapshot_id}/approve",
    "POST /api/wells/{wid}/source-rock",
    "POST /api/wells/{wid}/splice",
    "POST /api/wells/{wid}/strat-normalize",
    "POST /api/wells/{wid}/synthetic-seismogram",
    "POST /api/wells/{wid}/synthetic-seismogram-async",
    "POST /api/wells/{wid}/template-lock",
    "POST /api/wells/{wid}/template-preview",
    "POST /api/wells/{wid}/template-unlock",
    "POST /api/wells/{wid}/tops",
    "POST /api/wells/{wid}/tops-import",
    "POST /api/wells/{wid}/tornado",
    "POST /api/wells/{wid}/trajectory",
    "POST /api/wells/{wid}/unlock",
    "POST /api/wells/{wid}/upload-csv",
    "POST /api/wells/{wid}/upload-dlis",
    "POST /api/wells/{wid}/upload-las",
    "POST /api/wells/{wid}/upload-lis",
    "POST /api/wells/{wid}/vcl-enhanced",
    "POST /api/wells/{wid}/vcl-models",
    "POST /api/wells/{wid}/zones",
    "PUT /api/log-runs/{lr_id}/depth-control-points",
    "PUT /api/tops/{tid}",
    "PUT /api/users/{uid}",
    "PUT /api/wells/{wid}",
    "PUT /api/wells/{wid}/core/plugs/{plug_id}",
    "PUT /api/wells/{wid}/geomechanics/models/{model_id}",
    "PUT /api/wells/{wid}/image-assets/{asset_id}",
]


def _current_routes() -> list[str]:
    from backend.main import app

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        spec = app.openapi()

    found = set()
    for path, operations in spec["paths"].items():
        for method in operations:
            if method in ("head", "options", "parameters"):
                continue
            found.add(f"{method.upper()} {path}")
    return sorted(found)


def test_route_inventory_is_unchanged():
    actual = _current_routes()
    missing = sorted(set(EXPECTED_ROUTES) - set(actual))
    added = sorted(set(actual) - set(EXPECTED_ROUTES))
    assert not missing, f"endpoints disappeared: {missing}"
    assert not added, f"unexpected new endpoints: {added}"
    assert actual == EXPECTED_ROUTES


# ─── Duplicate route registration ───────────────────────────────
#
# Starlette matches the FIRST route registered for a path, so a second handler for
# the same method+path is dead code — it registers, appears in the OpenAPI schema,
# and never runs. Two have been found this way:
#
#   GET  /api/templates                      main.py vs routers/templates.py
#   POST /api/wells/{wid}/apply-template     routers/wells.py vs routers/templates.py
#
# The second was subtle: the dead copy had been fixed while the live one still
# failed, so a fix appeared not to work. Both were also fixed with different
# template lists and different lock files, so which one answered depended on
# registration order.


def _all_routes() -> dict[tuple[str, str], list[tuple[str, str]]]:
    """Every (method, path) with the handlers claiming it, across all modules."""
    import importlib
    import pathlib

    import backend.routers as routers_pkg
    from backend.main import app

    found: dict[tuple[str, str], list[tuple[str, str]]] = {}

    def add(method: str, path: str, handler: str, source: str):
        if method in ("HEAD", "OPTIONS"):
            return
        found.setdefault((method, path), []).append((handler, source))

    for route in app.routes:
        path = getattr(route, "path", "")
        methods = getattr(route, "methods", None)
        if methods and path.startswith("/api"):
            for method in methods:
                add(method, path, getattr(route, "name", "?"), "main.py")

    for file in sorted(pathlib.Path(routers_pkg.__file__).parent.glob("*.py")):
        if file.stem == "__init__":
            continue
        module = importlib.import_module(f"backend.routers.{file.stem}")
        router = getattr(module, "router", None)
        if router is None:
            continue
        for route in router.routes:
            methods = getattr(route, "methods", None)
            if not methods:
                continue
            for method in methods:
                # route.path is already prefix-qualified.
                add(method, getattr(route, "path", ""), getattr(route, "name", "?"), file.stem)

    return found


def test_no_duplicate_route_registrations():
    duplicates = {
        key: handlers
        for key, handlers in _all_routes().items()
        if len(handlers) > 1
    }
    assert duplicates == {}, (
        "more than one handler is registered for the same method and path; the "
        f"later one is dead code: {duplicates}"
    )


def test_the_expansion_actually_finds_the_routers():
    """Guards the check above: if it saw nothing, it would pass vacuously."""
    routes = _all_routes()
    assert len(routes) >= 180, f"only found {len(routes)} routes"
    sources = {source for handlers in routes.values() for _, source in handlers}
    for expected in ("main.py", "wells", "ops", "audit", "log_runs", "projects", "templates"):
        assert expected in sources, f"{expected} contributed no routes"


def test_apply_template_is_served_by_the_templates_router():
    """The duplicate resolution kept routers/templates.py's handler."""
    from backend.routers import templates, wells

    template_paths = {r.path for r in templates.router.routes}
    well_paths = {r.path for r in wells.router.routes}
    assert "/api/wells/{wid}/apply-template" in template_paths
    assert "/api/wells/{wid}/apply-template" not in well_paths
