"""UTC clock helpers.

`datetime.datetime.utcnow()` is deprecated and emitted 39 warnings per test run.
Its replacement returns an aware datetime, which would change both the type and
the serialised string, so the substitution has to preserve the old behaviour.
"""

from __future__ import annotations

import datetime
import re

from backend.timeutils import utc_today_str, utc_now_iso, utcnow


def test_utcnow_is_naive_utc():
    """Must stay naive, matching what utcnow() returned."""
    now = utcnow()
    assert isinstance(now, datetime.datetime)
    assert now.tzinfo is None, "aware datetimes would change stored values"
    # Within a minute of the real UTC time.
    delta = abs((now - datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)).total_seconds())
    assert delta < 60, f"not UTC now (off by {delta}s)"


def test_utc_now_iso_matches_the_previous_format():
    """`utcnow().isoformat() + "Z"` — trailing Z, no offset."""
    value = utc_now_iso()
    assert value.endswith("Z"), value
    assert "+00:00" not in value, "aware isoformat would carry an offset"
    # Parseable as ISO-8601 once the Z is restored to +00:00.
    parsed = datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    assert parsed.tzinfo is not None


def test_utc_now_iso_shape():
    assert re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$", utc_now_iso())


def test_utc_today_str_shape():
    assert re.match(r"^\d{4}-\d{2}-\d{2}$", utc_today_str())


def test_utcnow_is_monotonic():
    first = utcnow()
    second = utcnow()
    assert second >= first


def test_no_utcnow_calls_remain_in_the_codebase():
    """Guard against the deprecated call creeping back in."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "backend"
    offenders = []
    for path in root.rglob("*.py"):
        if "migrations" in str(path):
            continue
        # timeutils.py is the module that documents this migration, so its
        # docstring names the deprecated call.
        if path.name == "timeutils.py":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        if "datetime.datetime.utcnow" in text:
            offenders.append(str(path.relative_to(root.parent)))
    assert offenders == [], (
        f"datetime.datetime.utcnow() is deprecated; use timeutils.utcnow: {offenders}"
    )
