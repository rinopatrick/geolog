"""1.0 hardening: stale GEOLOG env fails fast, upgrade doc exists, Postgres limits documented."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_stale_geolog_env_fails_fast(monkeypatch):
    """Stale GEOLOG_ prefix vars must abort startup with a clear message."""
    from backend import main

    monkeypatch.setenv("GEOLOG_DB_PATH", "/tmp/stale.db")
    try:
        main._enforce_rename_policy()
    except RuntimeError as exc:
        assert "GEOLOG_" in str(exc)
        assert "BORELIA_" in str(exc)
    else:
        raise AssertionError("stale GEOLOG_ env must fail fast")


def test_clean_env_passes_rename_policy(monkeypatch):
    """Without stale vars the rename policy must not raise."""
    from backend import main

    for key in list(os.environ):
        if key.startswith("GEOLOG_"):
            monkeypatch.delenv(key, raising=False)
    main._enforce_rename_policy()


def test_upgrade_guide_covers_three_lines():
    """Operator upgrade guide must name env, DB file, and compose volume."""
    doc = ROOT / "docs" / "UPGRADE_1_0.md"
    assert doc.is_file(), "docs/UPGRADE_1_0.md must exist"
    text = doc.read_text(encoding="utf-8")
    assert "BORELIA_" in text
    assert "borelia.db" in text
    assert "borelia-data" in text


def test_postgres_doc_states_offline_copy_and_stamp():
    """Postgres doc must state offline copy and alembic stamp head."""
    text = (ROOT / "docs" / "POSTGRES.md").read_text(encoding="utf-8")
    assert "offline" in text.lower()
    assert "alembic stamp head" in text

def test_panel_inventory_artifact_exists():
    """Panel inventory must record nav/dispatch parity for the 1.0 UI bound."""
    doc = ROOT / "docs" / "PANEL_INVENTORY_1_0.md"
    assert doc.is_file(), "docs/PANEL_INVENTORY_1_0.md must exist"
    text = doc.read_text(encoding="utf-8")
    assert "46" in text
    assert "No orphan" in text or "no orphan" in text.lower()

def test_js_rendered_result_panels_have_empty_guidance():
    """Every JS-filled result div must show guidance before first run."""
    import re
    html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    bare = []
    for m in re.finditer(r'<div id="([A-Za-z]+Results)"([^>]*)>', html):
        attrs = m.group(2)
        if "empty-state" not in attrs and "data-empty" not in attrs:
            bare.append(m.group(1))
    assert bare == [], f"result divs without empty guidance: {bare}"
