"""Secret hashing for locally managed user credentials.

PBKDF2-HMAC-SHA256 from the standard library keeps the deployment dependency
surface unchanged. The encoded form carries its own algorithm, iteration count
and salt so the cost can be raised later without breaking existing rows.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets

ALGORITHM = "pbkdf2_sha256"
DEFAULT_ITERATIONS = 240_000
SALT_BYTES = 16


def _iterations() -> int:
    try:
        value = int(os.getenv("GEOLOG_PBKDF2_ITERATIONS", str(DEFAULT_ITERATIONS)) or DEFAULT_ITERATIONS)
    except ValueError:
        return DEFAULT_ITERATIONS
    return value if value >= 50_000 else DEFAULT_ITERATIONS


def hash_secret(secret: str, iterations: int | None = None) -> str:
    if not isinstance(secret, str) or not secret:
        raise ValueError("secret must be a non-empty string")
    rounds = _iterations() if iterations is None else iterations
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, rounds)
    return "$".join(
        (
            ALGORITHM,
            str(rounds),
            base64.b64encode(salt).decode("ascii"),
            base64.b64encode(digest).decode("ascii"),
        )
    )


def is_hash(value: str | None) -> bool:
    return bool(value) and str(value).startswith(ALGORITHM + "$")


def verify_secret(secret: str, encoded: str | None) -> bool:
    if not secret or not encoded or not is_hash(encoded):
        return False
    try:
        algorithm, rounds_raw, salt_raw, digest_raw = str(encoded).split("$", 3)
        if algorithm != ALGORITHM:
            return False
        rounds = int(rounds_raw)
        salt = base64.b64decode(salt_raw.encode("ascii"), validate=True)
        expected = base64.b64decode(digest_raw.encode("ascii"), validate=True)
    except (ValueError, TypeError):
        return False
    actual = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, rounds)
    return hmac.compare_digest(actual, expected)


def needs_rehash(encoded: str | None) -> bool:
    if not is_hash(encoded):
        return True
    try:
        rounds = int(str(encoded).split("$", 2)[1])
    except (IndexError, ValueError):
        return True
    return rounds < _iterations()
