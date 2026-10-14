"""Version consistency.

There were two hardcoded "2.0.0" strings (the FastAPI app version and the health
payload) and no git tags at all, so nothing tied a release to the code it
described. backend/version.py is now the single source, and this keeps it in step
with the git tag.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app
from backend.version import __version__

REPO_ROOT = Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^\d+\.\d+\.\d+$")


def test_version_is_semver():
    assert SEMVER.match(__version__), f"not a semver string: {__version__!r}"


def test_version_is_zero_major_while_pre_production():
    """0.x signals an unstable API; README calls this pre-production."""
    major = int(__version__.split(".")[0])
    assert major == 0, (
        f"version {__version__} claims a stable major release, but the README "
        "documents this as an engineering sample"
    )


def test_fastapi_app_version_matches_the_module():
    assert app.version == __version__


def test_health_endpoint_reports_the_module_version():
    client = TestClient(app)
    body = client.get("/api/health").json()
    assert body["version"] == __version__


def test_no_stale_hardcoded_version_strings():
    """Guard against a version literal being reintroduced next to the constant."""
    source = (REPO_ROOT / "backend" / "main.py").read_text(encoding="utf-8")
    # LAS file versions are legitimately "2.0" and unrelated to the app version.
    occurrences = [
        line for line in source.splitlines()
        if "2.0.0" in line and "las_version" not in line
    ]
    assert occurrences == [], (
        f"hardcoded app version string(s) in backend/main.py: {occurrences}"
    )


def test_git_tag_matches_the_module_version():
    """Skip when the checkout has no tags (shallow clone, tarball)."""
    proc = subprocess.run(
        ["git", "describe", "--tags", "--exact-match"],
        cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=30,
    )
    if proc.returncode != 0:
        pytest.skip("HEAD is not an exact tag, so there is nothing to compare")

    tag = proc.stdout.strip()
    assert tag == f"v{__version__}", (
        f"HEAD is tagged {tag} but backend/version.py says {__version__}"
    )


def test_changelog_has_an_entry_for_the_current_version():
    changelog = REPO_ROOT / "CHANGELOG.md"
    assert changelog.exists(), "CHANGELOG.md is missing"
    text = changelog.read_text(encoding="utf-8")
    assert f"## [{__version__}]" in text, (
        f"CHANGELOG.md has no section for {__version__}"
    )
