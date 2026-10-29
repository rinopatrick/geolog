"""The backup drill restores both the database and artifact files."""

from __future__ import annotations

import importlib.util
import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _load_drill():
    spec = importlib.util.spec_from_file_location(
        "backup_restore_drill", ROOT / "scripts" / "backup_restore_drill.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_backup_drill_restores_database_and_artifacts(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    db_path = tmp_path / "source.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO items (name) VALUES ('a'), ('b')")
        conn.commit()
    finally:
        conn.close()

    artifacts = tmp_path / "artifacts-src"
    (artifacts / "snapshots").mkdir(parents=True)
    (artifacts / "snapshots" / "one.json").write_text('{"ok": true}', encoding="utf-8")

    drill = _load_drill()
    report = drill.run_drill(db_path, artifacts)
    assert report["ok"] is True, json.dumps(report, indent=2)
    assert report["row_counts"]["match"] is True
    assert report["integrity"]["restore"] is True
    assert report["artifacts"]["ok"] is True
    assert report["artifacts"]["file_count"] == 1
    assert report["hashes"]["backup_restore_match"] is True

    signature_path = Path(report["backup_db"]).parent / "report.signature.json"
    assert signature_path.is_file()
