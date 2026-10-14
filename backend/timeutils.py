"""UTC clock helpers.

`datetime.datetime.utcnow()` is deprecated (scheduled for removal) and emitted 39
DeprecationWarnings per test run, which buried the warnings that mattered. Its
replacement, `now(timezone.utc)`, returns an *aware* datetime, so a naive
substitution would change both the type and the serialised string — several
response payloads are covered by tests that pin the exact format.

These helpers keep the existing behaviour: naive UTC, same output.
"""

from __future__ import annotations

import datetime


def utcnow() -> datetime.datetime:
    """Naive UTC now. Drop-in replacement for `datetime.datetime.utcnow()`."""
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def utc_now_iso() -> str:
    """ISO-8601 UTC with a trailing Z, e.g. `2026-01-01T00:00:00.123456Z`.

    Matches `utcnow().isoformat() + "Z"` exactly.
    """
    return utcnow().isoformat() + "Z"


def utc_today_str() -> str:
    """`YYYY-MM-DD` in UTC."""
    return utcnow().strftime("%Y-%m-%d")
