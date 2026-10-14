"""Multi-worker safe request metrics and event tracking.

State is backed by file-based persistence under ARTIFACT_DIR/metrics.json,
allowing multiple server worker processes to share and accumulate request totals,
latencies, and status distributions.
"""

from __future__ import annotations

import datetime
import json
import os
from threading import Lock
from typing import Any

try:
    from timeutils import utcnow
except ImportError:
    from backend.timeutils import utcnow

try:
    from well_state import ARTIFACT_DIR
except ImportError:
    from backend.well_state import ARTIFACT_DIR


OBS_METRICS_LOCK = Lock()
METRICS_FILE = os.path.join(ARTIFACT_DIR, "metrics.json")
OBS_METRICS: dict[str, Any] = {
    "requests_total": 0,
    "requests_by_method": {},
    "requests_by_status": {},
    "latency_ms_sum": 0.0,
    "latency_ms_count": 0,
    "recent_events": [],
}

RECENT_EVENT_LIMIT = 200


def _load_metrics() -> dict[str, Any]:
    if not os.path.exists(METRICS_FILE):
        return {
            "requests_total": 0,
            "requests_by_method": {},
            "requests_by_status": {},
            "latency_ms_sum": 0.0,
            "latency_ms_count": 0,
            "recent_events": [],
        }
    try:
        with open(METRICS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {
        "requests_total": 0,
        "requests_by_method": {},
        "requests_by_status": {},
        "latency_ms_sum": 0.0,
        "latency_ms_count": 0,
        "recent_events": [],
    }


def _save_metrics(data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(METRICS_FILE), exist_ok=True)
    tmp_path = METRICS_FILE + ".tmp"
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp_path, METRICS_FILE)


def record_request(
    method: str,
    path: str,
    status: int,
    elapsed_ms: float,
    request_id: str = "",
    trace_id: str = "",
) -> None:
    """Record one completed request and persist state across worker processes."""
    with OBS_METRICS_LOCK:
        metrics = _load_metrics()
        metrics["requests_total"] = int(metrics.get("requests_total", 0)) + 1
        metrics["latency_ms_sum"] = float(metrics.get("latency_ms_sum", 0.0)) + elapsed_ms
        metrics["latency_ms_count"] = int(metrics.get("latency_ms_count", 0)) + 1

        by_method = metrics.setdefault("requests_by_method", {})
        by_status = metrics.setdefault("requests_by_status", {})
        by_method[method] = int(by_method.get(method, 0)) + 1
        by_status[str(status)] = int(by_status.get(str(status), 0)) + 1

        recent = metrics.setdefault("recent_events", [])
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

        _save_metrics(metrics)
        OBS_METRICS.clear()
        OBS_METRICS.update(metrics)
