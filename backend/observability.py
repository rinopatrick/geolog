"""In-process request metrics.

The metrics middleware in main.py writes here and the /api/ops routes read here,
so the state has to live somewhere both can import without a cycle.

In-process and in-memory, like the job registry: counters reset on restart and are
not shared between workers. Adequate for the single-process deployment this app
targets.

shortcut: in-memory metrics, single process only. Upgrade to a real metrics
backend (Prometheus client library, or OTLP) if the app runs with more than one
worker — /api/ops/metrics/prometheus currently exposes only what this process saw.
"""

from __future__ import annotations

import datetime
from threading import Lock
from typing import Any
try:
    from timeutils import utcnow
except ImportError:
    from backend.timeutils import utcnow

OBS_METRICS_LOCK = Lock()
OBS_METRICS: dict[str, Any] = {
    "requests_total": 0,
    "requests_by_method": {},
    "requests_by_status": {},
    "latency_ms_sum": 0.0,
    "latency_ms_count": 0,
    "recent_events": [],
}

# How many request events to retain for /api/ops/metrics/recent.
RECENT_EVENT_LIMIT = 200


def record_request(
    method: str,
    path: str,
    status: int,
    elapsed_ms: float,
    request_id: str = "",
    trace_id: str = "",
) -> None:
    """Record one completed request. Called by the metrics middleware."""
    with OBS_METRICS_LOCK:
        OBS_METRICS["requests_total"] += 1
        OBS_METRICS["latency_ms_sum"] += elapsed_ms
        OBS_METRICS["latency_ms_count"] += 1

        by_method = OBS_METRICS["requests_by_method"]
        by_status = OBS_METRICS["requests_by_status"]
        by_method[method] = int(by_method.get(method, 0)) + 1
        by_status[str(status)] = int(by_status.get(str(status), 0)) + 1

        recent = OBS_METRICS.get("recent_events")
        if isinstance(recent, list):
            recent.append({
                "ts": utcnow().isoformat() + "Z",
                "request_id": request_id,
                "trace_id": trace_id,
                "method": method,
                "path": path,
                "status": int(status),
                "latency_ms": round(elapsed_ms, 2),
            })
            if len(recent) > RECENT_EVENT_LIMIT:
                del recent[:-RECENT_EVENT_LIMIT]
