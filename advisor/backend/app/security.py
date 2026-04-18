"""Symmetric encryption helpers for HA access token storage (feature 016).

The encryption key comes from the ADVISOR_ENCRYPTION_KEY env var, validated
at startup in app.config. The key is a Fernet key (32 URL-safe base64 bytes).
"""
from __future__ import annotations

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class TokenDecryptionError(Exception):
    """Raised when a stored HA access token cannot be decrypted.

    Signals key rotation, corruption, or a ciphertext produced under a
    different key. Callers should map this to an operator-visible error so
    the admin can re-paste the token in Settings -> Home Assistant.
    """


def _fernet() -> Fernet:
    return Fernet(settings.advisor_encryption_key.get_secret_value().encode("ascii"))


def encrypt_token(plaintext: str) -> bytes:
    """Encrypt a long-lived access token for storage in the DB."""
    return _fernet().encrypt(plaintext.encode("utf-8"))


def decrypt_token(ciphertext: bytes) -> str:
    """Decrypt a stored ciphertext. Raises TokenDecryptionError on failure."""
    try:
        return _fernet().decrypt(ciphertext).decode("utf-8")
    except InvalidToken as e:
        raise TokenDecryptionError(
            "HA access token could not be decrypted. The encryption key "
            "may have been rotated; re-save the HA connection in Settings."
        ) from e


def mask_token(plaintext: str) -> str:
    """Redacted read-back for the UI.

    Shows an ellipsis plus the last 4 characters. Returns empty string for
    empty input so callers don't need to branch.
    """
    if not plaintext:
        return ""
    suffix = plaintext[-4:] if len(plaintext) >= 4 else plaintext
    return f"\u2026{suffix}"
