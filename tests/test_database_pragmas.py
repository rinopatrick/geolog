"""SQLite concurrency pragmas are applied to every connection."""

from __future__ import annotations

from backend.database import engine


def test_sqlite_uses_wal_and_busy_timeout():
    with engine.connect() as conn:
        assert str(conn.exec_driver_sql("PRAGMA journal_mode").scalar()).lower() == "wal"
        assert int(conn.exec_driver_sql("PRAGMA busy_timeout").scalar()) >= 15000
