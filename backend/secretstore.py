"""Read secrets from the environment or from a mounted file.

Docker/Kubernetes secret managers usually mount a file and expose its path as
``<NAME>_FILE``. This helper keeps that convention in one place:

    AUTH_JWT_SECRET_FILE=/run/secrets/auth_jwt_secret

falls back to ``AUTH_JWT_SECRET`` when no file is configured. Values are stripped
so a newline at the end of a mounted secret does not become part of the key.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

def read_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    path = (os.getenv(f"{name}_FILE") or "").strip()
    if path:
        try:
            return Path(path).read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise RuntimeError(f"cannot read {name}_FILE ({path}): {exc}") from exc

    value = os.getenv(name)
    if value is None:
        return default
    return value.strip()
