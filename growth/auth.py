"""Passcode hashing and verification for profile sign-in.

Uses PBKDF2-HMAC-SHA256 from the standard library — no external dependencies.
Stored format:

    pbkdf2_sha256$<iterations>$<base64-salt>$<base64-hash>

A single self-describing string per profile means the iteration count can be
raised in the future without invalidating older records.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets

ALGO = "pbkdf2_sha256"
ITERATIONS = 200_000
SALT_BYTES = 16
DIGEST_BYTES = 32  # sha256 output size

MIN_PASSCODE_LENGTH = 6


class InvalidPasscode(ValueError):
    """Raised when the passcode does not meet minimum length / format rules."""


def validate_passcode(passcode: str) -> None:
    if not isinstance(passcode, str):
        raise InvalidPasscode("Passcode must be a string.")
    if len(passcode) < MIN_PASSCODE_LENGTH:
        raise InvalidPasscode(
            f"Passcode must be at least {MIN_PASSCODE_LENGTH} characters."
        )


def hash_passcode(passcode: str) -> str:
    validate_passcode(passcode)
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", passcode.encode("utf-8"), salt, ITERATIONS, dklen=DIGEST_BYTES)
    return f"{ALGO}${ITERATIONS}${base64.b64encode(salt).decode()}${base64.b64encode(digest).decode()}"


def verify_passcode(passcode: str, stored: str) -> bool:
    """Constant-time check of `passcode` against a stored hash string."""
    try:
        algo, iter_str, salt_b64, hash_b64 = stored.split("$")
    except ValueError:
        return False
    if algo != ALGO:
        return False
    try:
        iterations = int(iter_str)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
    except (ValueError, TypeError):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", passcode.encode("utf-8"), salt, iterations, dklen=len(expected))
    return hmac.compare_digest(digest, expected)
