"""Cross-worker rate limits and login lockout.

State is a JSON file under GEOLOG_ARTIFACT_DIR, protected by the same advisory
file lock used by the other file-backed state. That is sufficient for the
single-host deployment this project supports; a multi-host deployment should
move the same interface to Redis or the primary database.
"""

from __future__ import annotations

import json
import os
import time
from threading import Lock
from typing import Any

try:
    from filelock import interprocess_lock
except ImportError:
    from backend.filelock import interprocess_lock

try:
    from well_state import ARTIFACT_DIR
except ImportError:
    from backend.well_state import ARTIFACT_DIR

RATE_LIMIT_FILE = os.path.join(ARTIFACT_DIR, "rate_limits.json")
_RATE_LIMIT_LOCK = Lock()
_MAX_KEYS = 5000


def _env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)) or default)
    except ValueError:
        return default
    return value if value > 0 else default


def auth_ip_limit() -> int:
    return _env_int("GEOLOG_AUTH_IP_LIMIT", 30)


def auth_ip_window_seconds() -> int:
    return _env_int("GEOLOG_AUTH_IP_WINDOW_SECONDS", 300)


def auth_failure_limit() -> int:
    return _env_int("GEOLOG_AUTH_FAILURE_LIMIT", 5)


def auth_failure_window_seconds() -> int:
    return _env_int("GEOLOG_AUTH_FAILURE_WINDOW_SECONDS", 900)


def auth_lockout_seconds() -> int:
    return _env_int("GEOLOG_AUTH_LOCKOUT_SECONDS", 900)


def _db_enabled() -> bool:
    try:
        from state_backend import enabled
    except ImportError:
        from backend.state_backend import enabled
    return enabled()


def _now() -> float:
    return time.time()


def _load() -> dict[str, Any]:
    if not os.path.exists(RATE_LIMIT_FILE):
        return {"buckets": {}, "locks": {}}
    try:
        with open(RATE_LIMIT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError("not a dict")
        data.setdefault("buckets", {})
        data.setdefault("locks", {})
        return data
    except Exception:
        return {"buckets": {}, "locks": {}}


def _save(data: dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(RATE_LIMIT_FILE), exist_ok=True)
    tmp = RATE_LIMIT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, separators=(",", ":"))
    os.replace(tmp, RATE_LIMIT_FILE)


def _prune(data: dict[str, Any], now: float) -> None:
    buckets = data.get("buckets", {})
    locks = data.get("locks", {})
    for key in [k for k, v in buckets.items() if float(v.get("reset_at", 0)) <= now]:
        buckets.pop(key, None)
    for key in [k for k, v in locks.items() if float(v.get("until", 0)) <= now]:
        locks.pop(key, None)
    # Bound the file if a caller sprays distinct usernames/IPs.
    if len(buckets) + len(locks) > _MAX_KEYS:
        keep = sorted(
            list(buckets.items()) + list(locks.items()),
            key=lambda kv: float(kv[1].get("reset_at", kv[1].get("until", 0))),
            reverse=True,
        )[:_MAX_KEYS]
        data["buckets"] = {k: v for k, v in keep if k in buckets}
        data["locks"] = {k: v for k, v in keep if k in locks}


def _mutate(fn):
    with _RATE_LIMIT_LOCK, interprocess_lock(RATE_LIMIT_FILE):
        now = _now()
        data = _load()
        _prune(data, now)
        result = fn(data, now)
        _save(data)
        return result


def hit(key: str, limit: int, window_seconds: int) -> int:
    """Count one attempt. Return 0 when allowed, else seconds until retry."""
    if _db_enabled():
        try:
            from state_backend import hit as db_hit
        except ImportError:
            from backend.state_backend import hit as db_hit
        return db_hit(key, limit, window_seconds)

    def _apply(data: dict[str, Any], now: float) -> int:
        bucket = data["buckets"].get(key)
        if not bucket or float(bucket.get("reset_at", 0)) <= now:
            bucket = {"count": 0, "reset_at": now + window_seconds}
            data["buckets"][key] = bucket
        bucket["count"] = int(bucket.get("count", 0)) + 1
        if bucket["count"] > limit:
            return max(1, int(float(bucket["reset_at"]) - now))
        return 0

    return _mutate(_apply)


def locked_for(key: str) -> int:
    if _db_enabled():
        try:
            from state_backend import locked_for as db_locked_for
        except ImportError:
            from backend.state_backend import locked_for as db_locked_for
        return db_locked_for(key)

    def _apply(data: dict[str, Any], now: float) -> int:
        lock = data["locks"].get(key)
        if not lock:
            return 0
        return max(0, int(float(lock.get("until", 0)) - now))

    return _mutate(_apply)


def record_failure(key: str, limit: int, window_seconds: int, lockout_seconds: int) -> int:
    """Record a failed credential attempt; lock the key at the threshold."""
    if _db_enabled():
        try:
            from state_backend import record_failure as db_record_failure
        except ImportError:
            from backend.state_backend import record_failure as db_record_failure
        return db_record_failure(key, limit, window_seconds, lockout_seconds)

    def _apply(data: dict[str, Any], now: float) -> int:
        bucket = data["buckets"].get(key)
        if not bucket or float(bucket.get("reset_at", 0)) <= now:
            bucket = {"count": 0, "reset_at": now + window_seconds}
            data["buckets"][key] = bucket
        bucket["count"] = int(bucket.get("count", 0)) + 1
        if bucket["count"] >= limit:
            until = now + lockout_seconds
            data["locks"][key] = {"until": until, "failures": bucket["count"]}
            return lockout_seconds
        return 0

    return _mutate(_apply)


def clear_failures(key: str) -> None:
    if _db_enabled():
        try:
            from state_backend import clear_failures as db_clear_failures
        except ImportError:
            from backend.state_backend import clear_failures as db_clear_failures
        db_clear_failures(key)
        return

    def _apply(data: dict[str, Any], now: float) -> None:
        data["buckets"].pop(key, None)
        data["locks"].pop(key, None)

    _mutate(_apply)


def login_ip_key(ip: str) -> str:
    return f"login-ip:{ip}"


def login_user_key(username: str) -> str:
    return f"login-user:{username.strip().lower()}"


def check_login_allowed(ip: str, username: str) -> int:
    """Return 0 when a login may proceed, else seconds until retry."""
    remaining = locked_for(login_user_key(username))
    if remaining:
        return remaining
    return hit(login_ip_key(ip), auth_ip_limit(), auth_ip_window_seconds())


def record_login_failure(ip: str, username: str) -> int:
    # The IP bucket above already counts every attempt. This bucket counts only
    # failures and drives the account lockout.
    return record_failure(
        login_user_key(username),
        auth_failure_limit(),
        auth_failure_window_seconds(),
        auth_lockout_seconds(),
    )


def clear_login_failures(username: str) -> None:
    clear_failures(login_user_key(username))


def reset_rate_limits() -> None:
    """Test helper: drop all state."""
    if _db_enabled():
        try:
            from state_backend import reset_rate_limits as db_reset
        except ImportError:
            from backend.state_backend import reset_rate_limits as db_reset
        db_reset()
        return
    with _RATE_LIMIT_LOCK:
        try:
            os.remove(RATE_LIMIT_FILE)
        except FileNotFoundError:
            pass
