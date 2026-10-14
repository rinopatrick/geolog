"""Request-body validation helpers.

Every write endpoint takes `data: dict`, so nothing validates the body before it
reaches a model. Three consequences, all observed:

1. `Model(**data)` is mass assignment. A client can choose the primary key —
   `POST /api/wells/ {"id": 4242}` created a well with id 4242 — and write columns
   that are not part of the request contract, such as `created_at`.
2. An unknown key reaches the model constructor and raises `TypeError`, so the
   client gets 500 rather than a message saying which field is wrong.
3. A missing required field raises `KeyError` or `TypeError` from `float(None)`,
   again a 500.

These helpers give each case a 400 with the field named. They are deliberately
small and explicit rather than a schema layer: the endpoints already use plain
dicts, and switching 186 of them to Pydantic models would be a much larger change
than the problem requires.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Optional

from fastapi import HTTPException


def pick(data: Mapping[str, Any], allowed: Iterable[str]) -> dict:
    """Return only the allowed keys, so a model cannot be built from raw input.

    Unknown keys are dropped rather than rejected: existing clients send extra
    fields (the frontend posts whole objects back), and silently ignoring them is
    the behaviour those clients already rely on. What matters is that they cannot
    reach the constructor.
    """
    allowed = set(allowed)
    return {k: v for k, v in (data or {}).items() if k in allowed}


def require(data: Mapping[str, Any], key: str) -> Any:
    """Return a required field, or 400 naming it."""
    if data is None or key not in data or data[key] is None:
        raise HTTPException(status_code=400, detail=f"{key} is required")
    return data[key]


def require_str(data: Mapping[str, Any], key: str) -> str:
    value = require(data, key)
    if isinstance(value, (dict, list)):
        raise HTTPException(status_code=400, detail=f"{key} must be a string")
    text = str(value).strip()
    if not text:
        raise HTTPException(status_code=400, detail=f"{key} must not be empty")
    return text


def require_float(data: Mapping[str, Any], key: str) -> float:
    """Return a required numeric field as float, or 400 naming it.

    Replaces `float(data.get(key))`, which raised TypeError for a missing field
    and ValueError for a non-numeric one — both surfaced as 500.
    """
    value = require(data, key)
    try:
        return float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{key} must be a number")


def require_int(data: Mapping[str, Any], key: str) -> int:
    value = require(data, key)
    try:
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{key} must be an integer")


def optional_float(data: Mapping[str, Any], key: str, default: Optional[float] = None) -> Optional[float]:
    """Return an optional numeric field, or the default when absent/null."""
    if data is None:
        return default
    value = data.get(key)
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{key} must be a number")


def optional_int(data: Mapping[str, Any], key: str, default: Optional[int] = None) -> Optional[int]:
    if data is None:
        return default
    value = data.get(key)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail=f"{key} must be an integer")


def optional_str(data: Mapping[str, Any], key: str, default: str = "") -> str:
    if data is None:
        return default
    value = data.get(key)
    if value is None:
        return default
    if isinstance(value, (dict, list)):
        raise HTTPException(status_code=400, detail=f"{key} must be a string")
    return str(value)
