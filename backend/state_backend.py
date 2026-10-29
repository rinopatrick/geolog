"""Database-backed shared state for multi-instance deployments.

Set ``GEOLOG_STATE_BACKEND=database`` to move rate-limit counters, metric
snapshots and job records from per-host files into the primary database. With
PostgreSQL this makes them shared across app instances; with SQLite it keeps the
same single-host constraint but preserves the existing behavior.

The file backend remains the default so upgrades do not silently change where
state lives.
"""

from __future__ import annotations

import json
import os
import time
from typing import Any

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

try:
    from database import engine
    from deps import sanitize_json
except ImportError:
    from backend.database import engine
    from backend.deps import sanitize_json


def enabled() -> bool:
    return (os.getenv("GEOLOG_STATE_BACKEND") or "file").strip().lower() in {
        "database",
        "db",
        "postgres",
        "postgresql",
    }


def _json(value: Any, default: Any) -> str:
    return json.dumps(sanitize_json(value), separators=(",", ":"), ensure_ascii=False)


def _loads(raw: str | None, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


# ─── Rate limits ──────────────────────────────────────────────

def bucket_increment(key: str, window_seconds: int) -> tuple[int, float]:
    now = time.time()
    reset_at = now + window_seconds
    with engine.begin() as conn:
        row = conn.execute(
            text(
                """
                INSERT INTO shared_rate_buckets (key, count, reset_at)
                VALUES (:key, 1, :reset_at)
                ON CONFLICT (key) DO UPDATE SET
                    count = CASE
                        WHEN shared_rate_buckets.reset_at <= :now THEN 1
                        ELSE shared_rate_buckets.count + 1
                    END,
                    reset_at = CASE
                        WHEN shared_rate_buckets.reset_at <= :now THEN :reset_at
                        ELSE shared_rate_buckets.reset_at
                    END
                RETURNING count, reset_at
                """
            ),
            {"key": key, "reset_at": reset_at, "now": now},
        ).first()
    return int(row[0]), float(row[1])


def hit(key: str, limit: int, window_seconds: int) -> int:
    count, reset_at = bucket_increment(key, window_seconds)
    if count > limit:
        return max(1, int(reset_at - time.time()))
    return 0


def locked_for(key: str) -> int:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT until FROM shared_rate_locks WHERE key = :key"),
            {"key": key},
        ).first()
    if not row:
        return 0
    return max(0, int(float(row[0]) - time.time()))


def record_failure(key: str, limit: int, window_seconds: int, lockout_seconds: int) -> int:
    count, _ = bucket_increment(key, window_seconds)
    if count < limit:
        return 0
    until = time.time() + lockout_seconds
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO shared_rate_locks (key, until, failures)
                VALUES (:key, :until, :failures)
                ON CONFLICT (key) DO UPDATE SET
                    until = EXCLUDED.until,
                    failures = EXCLUDED.failures
                """
            ),
            {"key": key, "until": until, "failures": count},
        )
    return lockout_seconds


def clear_failures(key: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM shared_rate_buckets WHERE key = :key"), {"key": key})
        conn.execute(text("DELETE FROM shared_rate_locks WHERE key = :key"), {"key": key})


def reset_rate_limits() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM shared_rate_buckets"))
        conn.execute(text("DELETE FROM shared_rate_locks"))


# ─── Metrics ──────────────────────────────────────────────────

def flush_metrics(worker_id: str, payload: dict[str, Any]) -> None:
    raw = _json(payload, {})
    now = time.time()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO shared_metric_workers (worker_id, payload, updated_at)
                VALUES (:worker_id, :payload, :updated_at)
                ON CONFLICT (worker_id) DO UPDATE SET
                    payload = EXCLUDED.payload,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {"worker_id": worker_id, "payload": raw, "updated_at": now},
        )


def load_metrics() -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT payload FROM shared_metric_workers ORDER BY worker_id")
        ).all()
    result = []
    for row in rows:
        data = _loads(row[0], {})
        if isinstance(data, dict):
            result.append(data)
    return result


def reset_metrics() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM shared_metric_workers"))


# ─── Well state (locks, snapshots, templates) ─────────────────

def load_well_state(key: str, default: Any = None) -> Any:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT payload FROM shared_well_state WHERE key = :key"),
            {"key": key},
        ).first()
    return _loads(row[0], default) if row else default


def save_well_state(key: str, payload: Any) -> None:
    now = time.time()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO shared_well_state (key, payload, version, updated_at)
                VALUES (:key, :payload, 0, :updated_at)
                ON CONFLICT (key) DO UPDATE SET
                    payload = EXCLUDED.payload,
                    version = shared_well_state.version + 1,
                    updated_at = EXCLUDED.updated_at
                """
            ),
            {"key": key, "payload": _json(payload, None), "updated_at": now},
        )


def mutate_well_state(key: str, fn, default: Any = None, retries: int = 5) -> Any:
    """Optimistic read-modify-write, safe across instances without a FILE lock."""
    for _ in range(retries):
        with engine.begin() as conn:
            row = conn.execute(
                text("SELECT payload, version FROM shared_well_state WHERE key = :key"),
                {"key": key},
            ).first()
            if row is None:
                payload = default
                result = fn(payload)
                try:
                    conn.execute(
                        text(
                            """
                            INSERT INTO shared_well_state (key, payload, version, updated_at)
                            VALUES (:key, :payload, 0, :updated_at)
                            """
                        ),
                        {"key": key, "payload": _json(payload, None), "updated_at": time.time()},
                    )
                    return result
                except IntegrityError:
                    pass
            else:
                payload = _loads(row[0], default)
                result = fn(payload)
                updated = conn.execute(
                    text(
                        """
                        UPDATE shared_well_state
                        SET payload = :payload, version = version + 1, updated_at = :updated_at
                        WHERE key = :key AND version = :version
                        """
                    ),
                    {
                        "key": key,
                        "payload": _json(payload, None),
                        "updated_at": time.time(),
                        "version": int(row[1]),
                    },
                )
                if updated.rowcount == 1:
                    return result
        time.sleep(0.01)
    raise RuntimeError(f"could not update shared state {key!r} after {retries} retries")


def delete_well_state(key: str) -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM shared_well_state WHERE key = :key"), {"key": key})


def reset_well_state() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM shared_well_state"))


# ─── Jobs ─────────────────────────────────────────────────────

_JOB_FIELDS = {
    "status", "progress", "error", "attempts", "worker_id",
    "started_at", "started_epoch", "finished_at", "finished_epoch",
}


def _job_row(row) -> dict[str, Any]:
    data = dict(row)
    data["payload"] = _loads(data.get("payload"), {})
    data["result"] = _loads(data.get("result"), None)
    for key in ("created_epoch", "started_epoch", "finished_epoch"):
        data.pop(key, None)
    return data


def create_job(job_id: str, job_type: str, payload: dict[str, Any], created_at: str) -> None:
    now = time.time()
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO shared_jobs
                    (id, type, payload, status, progress, result, error, attempts,
                     worker_id, created_at, created_epoch, started_at, started_epoch,
                     finished_at, finished_epoch)
                VALUES
                    (:id, :type, :payload, 'queued', 0, NULL, NULL, 0,
                     NULL, :created_at, :now, NULL, NULL, NULL, NULL)
                """
            ),
            {
                "id": job_id,
                "type": job_type,
                "payload": _json(payload, {}),
                "created_at": created_at,
                "now": now,
            },
        )


def update_job(job_id: str, **fields) -> None:
    assignments = []
    params: dict[str, Any] = {"id": job_id}
    for key, value in fields.items():
        if key not in _JOB_FIELDS:
            continue
        if key == "progress":
            value = int(value or 0)
        if key == "attempts":
            value = int(value or 0)
        assignments.append(f"{key} = :{key}")
        params[key] = value
    if "status" in fields:
        assignments.append("status = :status")
        params["status"] = str(fields.get("status") or "queued")
    if "finished_at" in fields and "finished_epoch" not in fields:
        assignments.append("finished_epoch = :finished_epoch")
        params["finished_epoch"] = time.time()
    if "started_at" in fields and "started_epoch" not in fields:
        assignments.append("started_epoch = :started_epoch")
        params["started_epoch"] = time.time()
    if not assignments:
        return
    with engine.begin() as conn:
        conn.execute(
            text(f"UPDATE shared_jobs SET {', '.join(assignments)} WHERE id = :id"),
            params,
        )


def update_job_result(job_id: str, result: Any) -> None:
    with engine.begin() as conn:
        conn.execute(
            text("UPDATE shared_jobs SET result = :result WHERE id = :id"),
            {"id": job_id, "result": _json(result, None)},
        )


def get_job(job_id: str) -> dict[str, Any] | None:
    with engine.connect() as conn:
        row = conn.execute(
            text("SELECT * FROM shared_jobs WHERE id = :id"), {"id": job_id}
        ).mappings().first()
    return _job_row(row) if row else None


def list_jobs() -> list[dict[str, Any]]:
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT * FROM shared_jobs")).mappings().all()
    return [_job_row(row) for row in rows]


def claim_job(job_id: str, worker_id: str, stale_seconds: int) -> dict[str, Any] | None:
    now = time.time()
    cutoff = now - stale_seconds
    with engine.begin() as conn:
        updated = conn.execute(
            text(
                """
                UPDATE shared_jobs
                SET status = 'running',
                    worker_id = :worker_id,
                    attempts = attempts + 1,
                    progress = 0,
                    error = NULL,
                    started_at = :started_at,
                    started_epoch = :now,
                    finished_at = NULL,
                    finished_epoch = NULL
                WHERE id = :id
                  AND (
                    status IN ('queued', 'retrying')
                    OR (status = 'running' AND (started_epoch IS NULL OR started_epoch < :cutoff))
                  )
                """
            ),
            {
                "id": job_id,
                "worker_id": worker_id,
                "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now)),
                "now": now,
                "cutoff": cutoff,
            },
        )
        if updated.rowcount != 1:
            return None
        row = conn.execute(
            text("SELECT * FROM shared_jobs WHERE id = :id"), {"id": job_id}
        ).mappings().first()
    return _job_row(row) if row else None


def requeue_job(job_id: str) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                UPDATE shared_jobs
                SET status = 'queued', worker_id = NULL, started_at = NULL,
                    started_epoch = NULL, finished_at = NULL, finished_epoch = NULL
                WHERE id = :id
                """
            ),
            {"id": job_id},
        )


def recoverable_job_ids(stale_seconds: int) -> list[str]:
    cutoff = time.time() - stale_seconds
    with engine.connect() as conn:
        rows = conn.execute(
            text(
                """
                SELECT id FROM shared_jobs
                WHERE status = 'queued'
                   OR (status = 'running' AND (started_epoch IS NULL OR started_epoch < :cutoff))
                ORDER BY created_epoch
                """
            ),
            {"cutoff": cutoff},
        ).all()
    return [str(row[0]) for row in rows]


def reset_jobs() -> None:
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM shared_jobs"))
