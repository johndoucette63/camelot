"""Tests for app.security — Fernet encryption helpers (feature 016, T030).

Covers the symmetric-encryption wrapper used to protect the HA long-lived
access token at rest:

* encrypt/decrypt round-trip
* mask_token output shape
* TokenDecryptionError when the ciphertext was produced under a different key
* Settings() refuses to construct when ADVISOR_ENCRYPTION_KEY is missing

The module-level fixture key in conftest.py ensures every test file can
import app.config cleanly; these tests exercise the security surface in
isolation without going through the poller or the routers.
"""
from __future__ import annotations

import base64
import os

import pytest

from app import security
from app.security import TokenDecryptionError, decrypt_token, encrypt_token, mask_token


# ── (a) round-trip ─────────────────────────────────────────────────────


def test_encrypt_decrypt_round_trip():
    plaintext = "llat_01234567890abcdefWXYZ"
    ciphertext = encrypt_token(plaintext)

    assert isinstance(ciphertext, bytes)
    assert plaintext.encode("utf-8") not in ciphertext  # ciphertext is not plain

    restored = decrypt_token(ciphertext)
    assert restored == plaintext


# ── (b) mask_token output shape ────────────────────────────────────────


def test_mask_token_shape():
    # A typical long-lived access token ending in "WXYZ" masks to "…WXYZ".
    assert mask_token("llat_0123456789abcdefWXYZ") == "\u2026WXYZ"

    # Empty input stays empty so callers don't need to branch.
    assert mask_token("") == ""

    # Short input (< 4 chars) falls back to the whole string after the ellipsis
    # so we never accidentally return the literal token unmasked.
    assert mask_token("abc") == "\u2026abc"


# ── (c) wrong-key decrypt → TokenDecryptionError ───────────────────────


def test_decrypt_wrong_key_raises(monkeypatch):
    # Encrypt under the default (conftest-provided) key.
    ciphertext = encrypt_token("secret-value")

    # Now swap in an entirely different valid Fernet key and attempt decrypt.
    other_key = base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")

    class _SecretLike:
        def __init__(self, v: str) -> None:
            self._v = v

        def get_secret_value(self) -> str:
            return self._v

    monkeypatch.setattr(
        security.settings, "advisor_encryption_key", _SecretLike(other_key)
    )

    with pytest.raises(TokenDecryptionError):
        decrypt_token(ciphertext)


# ── (d) startup refuses to construct Settings with missing key ─────────


def test_startup_failure_on_missing_key(monkeypatch):
    """Settings() must reject an empty ADVISOR_ENCRYPTION_KEY loudly.

    Re-instantiate Settings with the env var cleared to simulate a fresh
    process that never had the key.
    """
    from pydantic import ValidationError

    from app.config import Settings

    # pydantic-settings reads from the environment at construction time.
    monkeypatch.delenv("ADVISOR_ENCRYPTION_KEY", raising=False)

    # pydantic's field_validator wraps ValueError into a ValidationError when
    # constructing BaseSettings. Either is acceptable at startup — we just
    # need a loud, non-silent failure (Constitution V).
    with pytest.raises((ValidationError, ValueError)):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_startup_failure_on_malformed_key(monkeypatch):
    """A non-base64 / wrong-length key must also fail loudly."""
    from pydantic import ValidationError

    from app.config import Settings

    monkeypatch.setenv("ADVISOR_ENCRYPTION_KEY", "not-a-valid-base64-fernet-key")
    with pytest.raises((ValidationError, ValueError)):
        Settings(_env_file=None)  # type: ignore[call-arg]
