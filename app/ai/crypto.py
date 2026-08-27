"""Encrypts provider API keys at rest. A user's AI settings row stores only the encrypted
ciphertext -- the raw key is decrypted in memory just long enough to build a provider adapter
and is never logged, returned from an API response, or persisted anywhere else."""

from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken


def _fernet(secret: str) -> Fernet:
    # Fernet requires a 32-byte urlsafe-base64 key; derives one deterministically from
    # whatever secret this deployment already has configured (see Settings.ai_encryption_key)
    # rather than requiring a brand-new secret to be provisioned.
    digest = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(plaintext: str, secret: str) -> str:
    return _fernet(secret).encrypt(plaintext.encode()).decode()


def decrypt_secret(ciphertext: str, secret: str) -> str | None:
    """Returns None (instead of raising) on a key that can't be decrypted with the current
    secret -- e.g. the deployment's secret was rotated -- so a caller can degrade to "not
    configured" rather than crashing a run."""
    try:
        return _fernet(secret).decrypt(ciphertext.encode()).decode()
    except InvalidToken:
        return None
