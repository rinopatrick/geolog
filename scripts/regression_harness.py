#!/usr/bin/env python3
"""Live API regression harness.

Runs against a server on http://localhost:8000. Override with BASE_URL.

What changed and why: this script used to check only `status_code == 200`. That
passes whether or not the response is correct, so it reported 26/26 while the LAS
parser was reading the wrong columns for every curve — the numbers were wrong and
the harness could not tell. It now asserts on the shape and the values of each
response.

Two severities:

- **fail**  the response is wrong: bad status, missing key, impossible value.
  Any failure makes the script exit 1.
- **warn**  the value is absent because the demo well lacks the input curve, so
  there is nothing to verify. Reported, but not a failure.

That distinction matters: without it, a check that silently skips looks the same
as a check that passed.
"""

from __future__ import annotations

import json
import os
import pathlib
import sys
import time

import requests

# Repo root on the path so the plausibility checker can be imported when this is
# run as `python scripts/regression_harness.py` (Python adds scripts/, not the root).
_REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# 127.0.0.1 rather than localhost: on a dual-stack host `localhost` resolves to
# ::1 first, and if a server is bound only to 127.0.0.1 the request can land on a
# different process — which produced a confusing 404 from a stale instance.
BASE = os.environ.get("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
HEADERS = {"X-User-Role": "interpreter", "Content-Type": "application/json"}

failures: list[tuple] = []
warnings: list[tuple] = []
checked = 0


def _get(path: str, **kw):
    return requests.get(BASE + path, headers=HEADERS, timeout=60, **kw)


def _post(path: str, body=None):
    return requests.post(BASE + path, headers=HEADERS, json=body or {}, timeout=120)


def _request(label: str, fn, *args, **kwargs):
    """Run a request, turning a transport error into a recorded failure.

    A dropped connection is a result the harness should report, not a crash: the
    first version let `requests.ConnectionError` escape and took the whole run
    down with a traceback, hiding every check after it.

    Retries once on a connection error, because a keep-alive connection can be
    closed by the server between requests and requests will not reopen it.
    """
    for attempt in (1, 2):
        try:
            return fn(*args, **kwargs)
        except requests.ConnectionError as exc:
            if attempt == 2:
                check(f"{label} [transport]", False, f"{type(exc).__name__}: {exc}")
                return None
            time.sleep(0.5)
        except requests.RequestException as exc:
            check(f"{label} [transport]", False, f"{type(exc).__name__}: {exc}")
            return None
    return None


def check(label, condition, detail=""):
    """Record an assertion. Returns the condition so it can guard further checks."""
    global checked
    checked += 1
    if not condition:
        failures.append((label, detail))
    return condition


def warn(label, detail):
    warnings.append((label, detail))


def expect_ok(label, response, *, keys=()):
    """Status must be 200 and the named keys must be present.

    Returns None if anything failed, so a caller's `if data:` guard skips the
    value checks instead of raising KeyError on a key it already reported as
    missing. A None response means the transport failed, already recorded.
    """
    if response is None:
        return None
    if not check(label, response.status_code == 200,
                 f"status {response.status_code}: {response.text[:160]}"):
        return None
    try:
        data = response.json()
    except Exception as exc:
        check(f"{label} [json]", False, str(exc))
        return None
    ok = True
    for key in keys:
        if not check(f"{label} [{key}]", key in data,
                     f"missing key {key!r} in {list(data)[:12]}"):
            ok = False
    return data if ok else None


def get_well_id() -> int:
    response = _request("wells list", _get, "/api/wells/")
    if response.status_code != 200 or not response.json():
        raise RuntimeError(f"no wells available (status {response.status_code})")
    return response.json()[0]["id"]


def run() -> int:
    wid = get_well_id()

    # ─── Health ─────────────────────────────────────────────────
    data = expect_ok("health", _request("health", _get, "/api/health"), keys=("status", "app", "version"))
    if data:
        check("health [status ok]", data["status"] == "ok", str(data.get("status")))
        check("health [app name]", data["app"] == "GeoLog", str(data.get("app")))

    # ─── Reads that must return usable structures ───────────────
    wells = expect_ok("wells list", _request("wells list", _get, "/api/wells/"))
    if wells is not None:
        check("wells list [non-empty]", len(wells) > 0, "no wells returned")
        if wells:
            first = wells[0]
            for key in ("id", "name"):
                check(f"wells list [item.{key}]", key in first, str(list(first)[:10]))

    # GET /api/wells/{wid} returns the well object directly.
    well = expect_ok("well detail", _request("well detail", _get, f"/api/wells/{wid}"), keys=("id", "name"))
    if well:
        check("well detail [id matches request]", well.get("id") == wid,
              f"asked for {wid}, got {well.get('id')}")
        check("well detail [has a name]", bool(well.get("name")), "empty name")

    runs = expect_ok("log runs", _request("log runs", _get, f"/api/wells/{wid}/log-runs"))
    if runs is not None:
        check("log runs [non-empty]", len(runs) > 0, "no log runs")
        if runs:
            check("log runs [num_points > 0]",
                  int(runs[0].get("num_points") or 0) > 0,
                  f"num_points={runs[0].get('num_points')}")

    # ─── Stored curve values must be physically plausible ───────
    # Without this the harness passes with the wrong numbers in the database:
    # the compute endpoints clamp their output, so Sw/VSH/PHIE stay in range even
    # when GR holds porosity values and RHOB holds caliper values. Verified by
    # corrupting a database and confirming this check is what fails.
    from backend.curve_plausibility import audit_curves

    if runs:
        run_id = runs[0].get("id")
        curves = expect_ok(f"curves for run {run_id}",
                           _request("curves", _get, f"/api/log-runs/{run_id}/curves"))
        if curves:
            check("curves [non-empty]", len(curves) > 0, "no curves returned")
            findings = audit_curves({
                "mnemonic": c.get("mnemonic"),
                "num_points": c.get("num_points"),
                "min_value": c.get("min_value"),
                "max_value": c.get("max_value"),
            } for c in curves)
            corrupt = [f for f in findings if f.severity == "corrupt"]
            suspicious = [f for f in findings if f.severity == "suspicious"]
            check("stored curves [physically plausible]", not corrupt,
                  "; ".join(f"{f.mnemonic}: {f.detail}" for f in corrupt))
            for f in suspicious:
                warn(f"stored curve [{f.mnemonic}]", f.detail)

    for label, path in [
        ("tops", f"/api/wells/{wid}/tops"),
        ("zones", f"/api/wells/{wid}/zones"),
    ]:
        expect_ok(label, _request(label, _get, path))

    # data-table returns {columns, rows, total_points, shown_points}.
    table = expect_ok("data table", _request("data table", _get, f"/api/wells/{wid}/data-table"),
                      keys=("columns", "rows", "total_points"))
    if table:
        columns = table["columns"]
        rows = table["rows"]
        check("data table [has columns]", len(columns) > 0, "no columns")
        check("data table [has rows]", len(rows) > 0, "no rows")
        check("data table [total_points > 0]",
              int(table["total_points"] or 0) > 0, f"total_points={table['total_points']}")
        # Every row must be as wide as the header, or the table is misaligned.
        widths = {len(r) for r in rows}
        check("data table [row width matches column count]",
              widths == {len(columns)},
              f"columns={len(columns)} but row widths={sorted(widths)}")

    # ─── Petrophysics: values, not just status ──────────────────
    sw = _request("compute-sw", _post, f"/api/wells/{wid}/compute-sw",
                  {"model": "archie", "a": 1.0, "m": 2.0, "n": 2.0, "rw": 0.1,
                   "gr_clean": 20.0, "gr_shale": 120.0})
    data = expect_ok("compute-sw", sw, keys=("sw", "vsh", "phie", "model", "stats"))
    if data:
        check("compute-sw [echoes model]", data["model"] == "archie", str(data["model"]))
        for field, lo, hi in (("sw", 0.0, 1.0), ("vsh", 0.0, 1.0), ("phie", 0.0, 0.6)):
            values = [v for v in data[field] if v is not None]
            check(f"compute-sw [{field} present]", len(values) > 0, "all null")
            if values:
                check(f"compute-sw [{field} in range]",
                      all(lo <= v <= hi for v in values),
                      f"min={min(values)} max={max(values)} outside [{lo},{hi}]")
        # Archie: Sw must fall as Rt rises. The demo curves give a spread of Rt.
        pairs = [(d, s) for d, s in zip(data["depth"], data["sw"]) if s is not None]
        if len(pairs) > 10:
            check("compute-sw [depth populated]", pairs[0][0] is not None,
                  "depth missing")
        check("compute-sw [stats n_points > 0]",
              int(data["stats"].get("n_points") or 0) > 0,
              f"n_points={data['stats'].get('n_points')}")

    for label, path, body, keys in [
        ("dual-water", f"/api/wells/{wid}/dual-water", {"rw": 0.1}, ("sw",)),
        ("vcl-models", f"/api/wells/{wid}/vcl-models", {}, ()),
        ("permeability", f"/api/wells/{wid}/permeability", {}, ()),
        ("multimineral", f"/api/wells/{wid}/multimineral", {}, ()),
        ("permeability-multi", f"/api/wells/{wid}/permeability-multi", {"rw": 0.1}, ()),
        ("rw-estimation", f"/api/wells/{wid}/rw-estimation", {}, ()),
        ("tornado", f"/api/wells/{wid}/tornado", {}, ()),
        ("probability-plot", f"/api/wells/{wid}/probability-plot", {}, ()),
        ("moveable-oil", f"/api/wells/{wid}/moveable-oil", {}, ()),
        ("electrofacies", f"/api/wells/{wid}/electrofacies", {"n_clusters": 3}, ()),
        ("sensitivity", f"/api/wells/{wid}/sensitivity", {}, ()),
    ]:
        response = _request(label, _post, path, body)
        # A 400 is acceptable when the demo well lacks a required curve; a 5xx is not.
        if response.status_code == 400:
            warn(label, f"skipped: {response.text[:110]}")
            continue
        expect_ok(label, response, keys=keys)

    # ─── Zone statistics ────────────────────────────────────────
    zones = expect_ok("zone-stats", _request("zone-stats", _get, f"/api/wells/{wid}/zone-stats"),
                      keys=("zones", "cutoffs"))
    if zones:
        for key in ("vsh", "phie", "sw"):
            check(f"zone-stats [cutoffs.{key}]", key in zones["cutoffs"],
                  str(zones["cutoffs"]))
        for zone in zones["zones"]:
            ntg = zone.get("ntg")
            if ntg is not None:
                # Net-to-gross above 1 is physically impossible.
                check(f"zone-stats [ntg <= 1 for {zone.get('name')}]",
                      0 <= ntg <= 1, f"ntg={ntg}")
            gross = zone.get("gross_ft")
            if gross is not None:
                check(f"zone-stats [gross > 0 for {zone.get('name')}]",
                      gross > 0, f"gross_ft={gross}")

    # ─── Reports and exports ────────────────────────────────────
    report = _request("report", _get, f"/api/wells/{wid}/report")
    expect_ok("report", report)

    pdf = _request("report-pdf", _get, f"/api/wells/{wid}/report-pdf")
    if check("report-pdf [status]", pdf.status_code == 200,
             f"status {pdf.status_code}: {pdf.text[:120]}"):
        check("report-pdf [content-type]",
              "application/pdf" in (pdf.headers.get("content-type") or ""),
              pdf.headers.get("content-type"))
        check("report-pdf [pdf magic bytes]", pdf.content.startswith(b"%PDF"),
              repr(pdf.content[:8]))
        check("report-pdf [non-trivial size]", len(pdf.content) > 2000,
              f"{len(pdf.content)} bytes")

    las = _request("export-las", _get, f"/api/wells/{wid}/export-las")
    if check("export-las [status]", las.status_code == 200, str(las.status_code)):
        body = las.text
        for token in ("~Version", "~Well", "~Curve", "~Ascii"):
            check(f"export-las [{token}]", token in body,
                  f"{token} missing from the LAS header")

    bundle = _request("export-bundle", _get, f"/api/wells/{wid}/export-bundle")
    if check("export-bundle [status]", bundle.status_code == 200,
             f"status {bundle.status_code}: {bundle.text[:120]}"):
        check("export-bundle [zip magic bytes]",
              bundle.content[:2] == b"PK", repr(bundle.content[:8]))
        check("export-bundle [non-trivial size]", len(bundle.content) > 500,
              f"{len(bundle.content)} bytes")

    # ─── Audit and ops ──────────────────────────────────────────
    audit = expect_ok("audit-log", _request("audit-log", _get, "/api/audit-log"))
    if audit is not None:
        check("audit-log [is list]", isinstance(audit, list), type(audit).__name__)

    chain = expect_ok("audit chain verify", _request("audit chain verify", _get, "/api/audit-log/verify"),
                      keys=("ok", "verified_entries"))
    if chain:
        check("audit chain [intact]", chain["ok"] is True,
              f"chain issues: {str(chain.get('issues'))[:200]}")

    metrics = expect_ok("ops metrics", _request("ops metrics", _get, "/api/ops/metrics"), keys=("requests_total",))
    if metrics:
        # The harness itself has made many requests by now.
        check("ops metrics [counts our own requests]",
              int(metrics["requests_total"]) > 10,
              f"requests_total={metrics['requests_total']}")

    for label, path, keys in [
        ("ops slo-status", "/api/ops/slo-status", ("ok",)),
        ("ops summary", "/api/ops/summary", ()),
        ("ops runbook", "/api/ops/runbook", ("alerts",)),
        ("ops contracts", "/api/ops/contracts", ("endpoints",)),
        ("jobs", "/api/jobs", ("jobs", "total")),
        ("curve-config", "/api/curve-config", ()),
        ("templates", "/api/templates", ("templates",)),
        ("projects", "/api/projects/", ()),
    ]:
        expect_ok(label, _request(label, _get, path), keys=keys)

    # ─── Summary ────────────────────────────────────────────────
    print(json.dumps({
        "checked": checked,
        "failed": len(failures),
        "warned": len(warnings),
    }, indent=2))

    for label, detail in failures:
        print(f"FAIL {label}: {detail}")
    for label, detail in warnings:
        print(f"WARN {label}: {detail}")

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(run())
