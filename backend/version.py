"""Single source of truth for the application version.

Keep this in step with the git tag: ``v0.27.0`` <-> ``__version__ = "0.27.0"``.
tests/test_version.py enforces that, so a release cannot ship a tag and a code
version that disagree.

The project is pre-production; see README's production-readiness section for what
that means. Version 0.x signals that the API is not yet stable.
"""

from __future__ import annotations

__version__ = "0.27.0"

# Public API generation. The `/api` prefix is v0 until a breaking change needs
# a new prefix; clients can branch on the X-API-Version response header.
__api_version__ = "v0"

# Short label for the release line, used in the UI and the health payload.
__release_name__ = "migration"
