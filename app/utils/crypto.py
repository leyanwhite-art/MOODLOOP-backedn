"""Fernet-based at-rest encryption for sensitive reflection text.

Fernet tokens are urlsafe base64 by construction, which satisfies the
"store as base64" wording in the spec while providing real confidentiality
and authentication (AES-128-CBC + HMAC-SHA256). The key lives in .env as
REFLECTION_ENC_KEY and is never returned by any API.
"""

from cryptography.fernet import Fernet, InvalidToken

from app.config import settings


class DecryptionError(Exception):
    """Raised when a stored ciphertext cannot be decrypted with the current key."""


def _cipher() -> Fernet:
    # Constructed per-call so a rotated key takes effect on next request without
    # holding a stale Fernet instance. Cheap — Fernet() just wraps the key.
    return Fernet(settings.REFLECTION_ENC_KEY.encode("utf-8"))


def encrypt_text(plaintext: str | None) -> str | None:
    if plaintext is None:
        return None
    token = _cipher().encrypt(plaintext.encode("utf-8"))
    return token.decode("utf-8")


def decrypt_text(token: str | None) -> str | None:
    if token is None:
        return None
    try:
        return _cipher().decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken as exc:
        raise DecryptionError(
            "Stored reflection text could not be decrypted with the configured key. "
            "Either REFLECTION_ENC_KEY changed without re-encryption or the row was tampered with."
        ) from exc


def looks_like_fernet_token(value: str) -> bool:
    """Heuristic — Fernet tokens start with 'gAAAAA' (version byte + IV/timestamp prefix)."""
    return isinstance(value, str) and value.startswith("gAAAAA")
