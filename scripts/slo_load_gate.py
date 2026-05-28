#!/usr/bin/env python3
"""Lightweight Phase-3 performance/SLO gate.

Runs concurrent GET load against selected endpoints, computes p95/error-rate,
and validates `/api/ops/slo-status` contract flags.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed


ROLE_HEADERS = {
    "X-User-Role": "viewer",
}


def _req_json(url: str, timeout: float = 10.0) -> tuple[int, dict]:
    req = urllib.request.Request(url, headers=ROLE_HEADERS, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        payload = resp.read().decode("utf-8", errors="replace")
        data = json.loads(payload) if payload else {}
        return int(resp.status), data


def _req_status_latency(url: str, timeout: float = 10.0) -> tuple[int, float]:
    t0 = time.perf_counter()
    req = urllib.request.Request(url, headers=ROLE_HEADERS, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            _ = resp.read()
            return int(resp.status), (time.perf_counter() - t0) * 1000.0
    except urllib.error.HTTPError as e:
        return int(e.code), (time.perf_counter() - t0) * 1000.0
    except Exception:
        return 599, (time.perf_counter() - t0) * 1000.0


def _percentile(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    if len(values) == 1:
        return float(values[0])
    values = sorted(values)
    k = (len(values) - 1) * (p / 100.0)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(values[int(k)])
    d0 = values[f] * (c - k)
    d1 = values[c] * (k - f)
    return float(d0 + d1)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://127.0.0.1:8000")
    ap.add_argument("--requests", type=int, default=120)
    ap.add_argument("--concurrency", type=int, default=12)
    ap.add_argument("--timeout", type=float, default=10.0)
    ap.add_argument("--p95-max-ms", type=float, default=800.0)
    ap.add_argument("--avg-max-ms", type=float, default=500.0)
    ap.add_argument("--error-rate-max", type=float, default=0.01)
    args = ap.parse_args()

    base = args.base_url.rstrip("/")
    status_url = f"{base}/api/ops/slo-status"
    health_url = f"{base}/api/ops/health"
    alerts_url = f"{base}/api/ops/alerts"
    targets = [status_url, health_url, alerts_url]

    latencies: list[float] = []
    statuses: list[int] = []
    lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as ex:
        futs = []
        for i in range(max(1, args.requests)):
            futs.append(ex.submit(_req_status_latency, targets[i % len(targets)], args.timeout))
        for fut in as_completed(futs):
            code, ms = fut.result()
            with lock:
                statuses.append(code)
                latencies.append(ms)

    total = len(statuses)
    errors = sum(1 for s in statuses if s >= 500 or s == 599)
    err_rate = (errors / total) if total else 1.0
    p95 = _percentile(latencies, 95.0)
    avg = statistics.fmean(latencies) if latencies else 0.0

    _, slo_payload = _req_json(status_url, timeout=args.timeout)
    checks = slo_payload.get("checks", {}) if isinstance(slo_payload, dict) else {}

    gate_ok = (
        p95 <= args.p95_max_ms
        and avg <= args.avg_max_ms
        and err_rate <= args.error_rate_max
        and bool(checks.get("latency_p95_ok", False))
        and bool(checks.get("latency_avg_ok", False))
        and bool(checks.get("error_rate_ok", False))
    )

    out = {
        "ok": bool(gate_ok),
        "measured": {
            "requests": total,
            "errors": errors,
            "error_rate": round(err_rate, 6),
            "latency_ms_avg": round(avg, 2),
            "latency_ms_p95": round(p95, 2),
        },
        "thresholds": {
            "latency_ms_avg_max": args.avg_max_ms,
            "latency_ms_p95_max": args.p95_max_ms,
            "error_rate_max": args.error_rate_max,
        },
        "ops_slo_checks": {
            "latency_avg_ok": bool(checks.get("latency_avg_ok", False)),
            "latency_p95_ok": bool(checks.get("latency_p95_ok", False)),
            "error_rate_ok": bool(checks.get("error_rate_ok", False)),
        },
    }
    print(json.dumps(out, ensure_ascii=False))
    return 0 if gate_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
