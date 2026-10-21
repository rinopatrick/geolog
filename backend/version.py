"""Single source of truth for the application version.

Keep this in step with the git tag: ``v0.7.0`` <-> ``__version__ = "0.7.0"``.
tests/test_version.py enforces that, so a release cannot ship a tag and a code
version that disagree.

The project is pre-production; see README's production-readiness section for what
that means. Version 0.x signals that the API is not yet stable.
"""

from __future__ import annotations

__version__ = "0.7.0"

# Short label for the release line, used in the UI and the health payload.
__release_name__ = "workbench"
