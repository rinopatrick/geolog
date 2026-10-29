"""Multi-worker safe request metrics without a per-request global lock.

The previous implementation read, mutated and rewrote one `metrics.json` under
an inter-process file lock for every request. That serialised the entire server
behind disk I/O. Each worker now keeps counters in memory and periodically
flushes its own file; readers aggregate the per-worker files. No request takes
an inter-process lock.
"""

from __future__ import annotations

import atexit
import glob
import json
import os
import threading
import time
from typing import Any

try:
    from timeutils import utcnow
    from well_state import ARTIFACT_DIR
except ImportError:
    from backend.timeutils import utcnow
    from backend.well_state import ARTIFACT_DIR

OBS_METRICS_LOCK = threading.Lock()
METRICS_FILE = os.path.join(ARTIFACT_DIR, "metrics.json")

_START_TOKEN = f"{os.getpid()}-{int(time.time() * 1000)}"
_LOCAL_METRICS: dict[str, Any] = {
    "requests_total": 0,
    "requests_by_method": {},
    "requests_by_status": {},
    "latency_ms_sum": 0.0,
    "latency_ms_count": 0,
    "recent_events": [],
}
OBS_METRICS: dict[str, Any] = {
    "requests_total": 0,
    "requests_by_method": {},
    "requests_by_status": {},
    "latency_ms_sum": 0.0,
    "latency_ms_count": 0,
    "recent_events": [],
}

RECENT_EVENT_LIMIT = 200
_MAX_EVENT_FILES = 200


def _empty_metrics() -> dict[str, Any]:
    return {
        "requests_total": 0,
        "requests_by_method": {},
        "requests_by_status": {},
        "latency_ms_sum": 0.0,
        "latency_ms_count": 0,
        "recent_events": [],
    }


def _worker_path() -> str:
    directory = os.path.dirname(os.path.abspath(METRICS_FILE))
    return os.path.join(directory, f"metrics-{_START_TOKEN}.json")


def _read_file(path: str) -> dict[str, Any] | None:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        return None
    return None


def _save_json(path: str, data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp.{os.getpid()}.{threading.get_ident()}"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    os.replace(tmp, path)


def flush_metrics() -> None:
    """Persist this worker's counters. Cheap enough to call from ops routes."""
    with OBS_METRICS_LOCK:
        snapshot = {
            "requests_total": int(_LOCAL_METRICS.get("requests_total", 0)),
            "requests_by_method": dict(_LOCAL_METRICS.get("requests_by_method", {})),
            "requests_by_status": dict(_LOCAL_METRICS.get("requests_by_status", {})),
            "latency_ms_sum": float(_LOCAL_METRICS.get("latency_ms_sum", 0.0)),
            "latency_ms_count": int(_LOCAL_METRICS.get("latency_ms_count", 0)),
            "recent_events": list(_LOCAL_METRICS.get("recent_events", [])),
        }
    _save_json(_worker_path(), snapshot)


def _merge_into(target: dict[str, Any], source: dict[str, Any]) -> None:
    target["requests_total"] = int(target.get("requests_total", 0)) + int(source.get("requests_total", 0))
    target["latency_ms_sum"] = float(target.get("latency_ms_sum", 0.0)) + float(source.get("latency_ms_sum", 0.0))
    target["latency_ms_count"] = int(target.get("latency_ms_count", 0)) + int(source.get("latency_ms_count", 0))
    for field in ("requests_by_method", "requests_by_status"):
        bucket = target.setdefault(field, {})
        for key, value in (source.get(field) or {}).items():
            bucket[str(key)] = int(bucket.get(str(key), 0)) + int(value)
    events = source.get("recent_events")
    if isinstance(events, list):
        target.setdefault("recent_events", []).extend(events)


def _aggregate() -> dict[str, Any]:
    flush_metrics()
    aggregate = _empty_metrics()
    directory = os.path.dirname(os.path.abspath(METRICS_FILE))
    files = sorted(glob.glob(os.path.join(directory, "metrics-*.json")), key=os.path.getmtime)
    if len(files) > _MAX_EVENT_FILES:
        for stale in files[: len(files) - _MAX_EVENT_FILES]:
            try:
                os.remove(stale)
            except OSError:
                pass
        files = files[-_MAX_EVENT_FILES:]
    legacy = METRICS_FILE if os.path.exists(METRICS_FILE) else None
    if legacy:
        files.append(legacy)
    for path in files:
        data = _read_file(path)
        if data:
            _merge_into(aggregate, data)
    events = aggregate.get("recent_events", [])
    if isinstance(events, list):
        events.sort(key=lambda e: str(e.get("ts", "")))
        aggregate["recent_events"] = events[-RECENT_EVENT_LIMIT:]
    return aggregate


def _load_metrics() -> dict[str, Any]:
    """Read the aggregated state. Kept for compatibility with ops/tests."""
    return _aggregate()


def refresh_metrics() -> None:
    """Reload shared counters so a worker sees requests handled by peers."""
    data = _aggregate()
    with OBS_METRICS_LOCK:
        OBS_METRICS.clear()
        OBS_METRICS.update(data)


def current_metrics() -> dict[str, Any]:
    return _aggregate()


def record_request(
    method: str,
    path: str,
    status: int,
    elapsed_ms: float,
    request_id: str = "",
    trace_id: str = "",
) -> None:
    """Record one completed request in this worker's in-memory counters."""
    with OBS_METRICS_LOCK:
        _LOCAL_METRICS["requests_total"] = int(_LOCAL_METRICS.get("requests_total", 0)) + 1
        _LOCAL_METRICS["latency_ms_sum"] = float(_LOCAL_METRICS.get("latency_ms_sum", 0.0)) + elapsed_ms
        _LOCAL_METRICS["latency_ms_count"] = int(_LOCAL_METRICS.get("latency_ms_count", 0)) + 1
        by_method = _LOCAL_METRICS.setdefault("requests_by_method", {})
        by_status = _LOCAL_METRICS.setdefault("requests_by_status", {})
        by_method[method] = int(by_method.get(method, 0)) + 1
        by_status[str(status)] = int(by_status.get(str(status), 0)) + 1
        recent = _LOCAL_METRICS.setdefault("recent_events", [])
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


def _flush_loop() -> None:
    try:
        interval = float(os.getenv("GEOLOG_METRICS_FLUSH_SECONDS", "5") or 5)
    except ValueError:
        interval = 5.0
    interval = max(1.0, interval)
    while True:
        time.sleep(interval)
        try:
            flush_metrics()
        except Exception:
            pass


atexit.register(flush_metrics)
threading.Thread(target=_flush_loop, name="geolog-metrics-flush", daemon=True).start()
