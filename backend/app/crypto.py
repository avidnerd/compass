"""Encryption at rest for provider credentials.

The bridge token and GitHub PAT are read access to a user's Google and GitHub
accounts. Storing them as plaintext in the SQLite file means anyone who can
read that file has that access, so they are sealed with a key derived from
`COMPASS_APP_SECRET` before they ever reach the database.

Values are tagged with a version prefix. Rows written before this existed are
plaintext JSON and still decrypt fine — they are re-sealed the next time they
are saved, so an existing install upgrades itself without a migration.
"""
import base64
import hashlib
import logging

from cryptography.fernet import Fernet, InvalidToken

from .config import settings

logger = logging.getLogger("compass.crypto")

_PREFIX = "v1:"
# Fixed salt: the secret is already high-entropy and per-install, and a stored
# random salt would have to live beside the ciphertext it protects.
_SALT = b"compass.provider-credentials.v1"

_fernet: Fernet | None = None
_warned = False


def available() -> bool:
    return bool(settings.app_secret)


def _cipher() -> Fernet:
    global _fernet
    if _fernet is None:
        key = hashlib.scrypt(settings.app_secret.encode(), salt=_SALT, n=2**14, r=8, p=1, dklen=32)
        _fernet = Fernet(base64.urlsafe_b64encode(key))
    return _fernet


def reset_cache() -> None:
    """Forget the derived key — used when the secret changes under us (tests)."""
    global _fernet
    _fernet = None


def seal(plaintext: str) -> str:
    """Encrypt a credential blob. Returns it unchanged if no secret is set."""
    global _warned
    if not available():
        if not _warned:
            logger.warning("[crypto] COMPASS_APP_SECRET is not set — provider credentials are "
                           "being stored UNENCRYPTED. Set it in .env and re-save them.")
            _warned = True
        return plaintext
    return _PREFIX + _cipher().encrypt(plaintext.encode()).decode()


def unseal(stored: str) -> str:
    """Decrypt a credential blob, tolerating rows written before encryption."""
    if not stored or not stored.startswith(_PREFIX):
        return stored  # legacy plaintext row
    if not available():
        raise RuntimeError("COMPASS_APP_SECRET is required to read stored credentials.")
    try:
        return _cipher().decrypt(stored[len(_PREFIX):].encode()).decode()
    except InvalidToken as exc:
        raise RuntimeError(
            "Stored credentials could not be decrypted — COMPASS_APP_SECRET has changed. "
            "Re-enter the bridge and GitHub tokens in Settings → Connections.") from exc
