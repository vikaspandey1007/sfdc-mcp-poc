"""Persists Salesforce OAuth tokens for the Gate 3B token broker.

Primary: OS keyring (Windows Credential Manager on this machine). Fallback:
a Fernet-encrypted file, stored entirely outside the repo tree (under the
user's home directory), never in .env or any file git could pick up.

In practice, on this machine, the fallback is the path actually used: a
real Salesforce JWT access_token + refresh_token pair exceeds Windows
Credential Manager's ~2560-byte generic-credential blob limit (WinError
1783), and keyring's Windows backend lets that error propagate raw rather
than wrapping it -- so save/load/clear here catch Exception broadly, not
just keyring.errors.KeyringError. See docs/troubleshooting.md "Windows
Credential Manager blob size limit".

The fallback file's own Fernet key is stored in the OS keyring, not beside
the ciphertext on disk (see `_fallback_key`) -- the key is small enough to
fit within keyring's blob limit even though the token pair itself isn't, so
this doesn't hit the same size problem. Colocating a key with its own
ciphertext would mean anyone who can read the fallback directory gets both,
which defeats most of the point of encrypting it; this keeps the two in
different stores with different access-control models instead.

Redaction-safe: no function here ever logs/prints a token value. Callers
must not either -- see docs/gate-0-plan.md AT-06.
"""

from __future__ import annotations

import json
import logging
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Optional

import keyring
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)

_SERVICE_NAME = "sfdc-mcp-poc-token-broker"
_KEYRING_USERNAME = "revenue-agent-mcp-client"
_FALLBACK_KEY_KEYRING_USERNAME = "revenue-agent-mcp-client-fallback-key"

# Fallback location -- deliberately outside the repo tree.
_FALLBACK_DIR = Path.home() / ".sfdc-mcp-poc"
_FALLBACK_TOKEN_FILE = _FALLBACK_DIR / "token_store.enc"
_FALLBACK_KEY_FILE = _FALLBACK_DIR / "token_key.bin"


@dataclass(frozen=True)
class StoredTokens:
    access_token: str
    refresh_token: str
    expires_at: float  # unix timestamp
    token_type: str = "Bearer"


def _fallback_key() -> bytes:
    """Returns the Fernet key used to encrypt/decrypt the fallback token file.

    Stored in the OS keyring, deliberately not beside the encrypted file on
    disk -- see the module docstring for why colocating a key with its own
    ciphertext defeats most of the point of encrypting it. The key is a
    small, fixed-size payload (~44 bytes, base64-encoded), unlike the real
    Salesforce token pair that overflows Windows Credential Manager's
    blob-size limit, so it fits in keyring even in the exact situation that
    forces the token pair itself onto this file-based fallback.

    Migrates an existing file-based key (from before this fix, or from a
    prior run where keyring was genuinely unavailable) into keyring on first
    use, so an already-encrypted token file on disk stays decryptable --
    generating a fresh key here instead would silently orphan it.
    """
    try:
        existing = keyring.get_password(_SERVICE_NAME, _FALLBACK_KEY_KEYRING_USERNAME)
        if existing:
            return existing.encode("ascii")

        if _FALLBACK_KEY_FILE.exists():
            key = _FALLBACK_KEY_FILE.read_bytes()
            logger.info("Migrating fallback encryption key from file to OS keyring.")
        else:
            key = Fernet.generate_key()

        keyring.set_password(_SERVICE_NAME, _FALLBACK_KEY_KEYRING_USERNAME, key.decode("ascii"))
        _FALLBACK_KEY_FILE.unlink(missing_ok=True)  # migrated -- don't leave a second copy on disk
        return key
    except Exception as exc:
        logger.warning(
            "Keyring unavailable for the fallback encryption key (%s) -- falling back to storing "
            "the key beside the encrypted file on disk, which weakens protection to "
            "file-permission-only (0600, best-effort on Windows).",
            type(exc).__name__,
        )
        return _file_fallback_key()


def _file_fallback_key() -> bytes:
    """Last-resort key storage, colocated with the ciphertext on disk --
    used only when the OS keyring is unavailable outright, not merely
    rejecting an oversized payload (see `_fallback_key`'s docstring)."""
    _FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
    if not _FALLBACK_KEY_FILE.exists():
        key = Fernet.generate_key()
        _FALLBACK_KEY_FILE.write_bytes(key)
        try:
            _FALLBACK_KEY_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600, best-effort on Windows
        except OSError:
            pass
        return key
    return _FALLBACK_KEY_FILE.read_bytes()


def _save_fallback(tokens: StoredTokens) -> None:
    fernet = Fernet(_fallback_key())
    payload = json.dumps(asdict(tokens)).encode("utf-8")
    _FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
    _FALLBACK_TOKEN_FILE.write_bytes(fernet.encrypt(payload))
    try:
        _FALLBACK_TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def _load_fallback() -> Optional[StoredTokens]:
    if not _FALLBACK_TOKEN_FILE.exists():
        return None
    fernet = Fernet(_fallback_key())
    payload = fernet.decrypt(_FALLBACK_TOKEN_FILE.read_bytes())
    return StoredTokens(**json.loads(payload))


def _clear_fallback() -> None:
    _FALLBACK_TOKEN_FILE.unlink(missing_ok=True)


def save_tokens(tokens: StoredTokens) -> None:
    """Persists tokens -- keyring first, falls back to encrypted file on keyring error.

    Catches Exception broadly, not just keyring.errors.KeyringError: on
    Windows, keyring's WinVaultKeyring lets raw pywin32/win32ctypes errors
    propagate uncaught instead of wrapping them (confirmed empirically --
    see docs/troubleshooting.md "Windows Credential Manager blob size
    limit"). A real Salesforce JWT access_token + refresh_token pair
    exceeds Windows Credential Manager's ~2560-byte generic-credential blob
    limit (WinError 1783, "The stub received bad data"), so this fallback
    path is not just a theoretical contingency -- it's the path actually
    used on this OS for real tokens.
    """
    payload = json.dumps(asdict(tokens))
    try:
        keyring.set_password(_SERVICE_NAME, _KEYRING_USERNAME, payload)
        logger.info("Tokens saved to OS keyring.")
    except Exception as exc:
        logger.warning("Keyring write failed (%s), falling back to encrypted file.", type(exc).__name__)
        _save_fallback(tokens)


def load_tokens() -> Optional[StoredTokens]:
    """Loads tokens -- keyring first, falls back to encrypted file on keyring error."""
    try:
        payload = keyring.get_password(_SERVICE_NAME, _KEYRING_USERNAME)
        if payload:
            return StoredTokens(**json.loads(payload))
        # Nothing in keyring -- check the fallback in case a previous run used it.
        return _load_fallback()
    except Exception as exc:
        logger.warning("Keyring read failed (%s), reading encrypted file fallback.", type(exc).__name__)
        return _load_fallback()


def clear_tokens() -> None:
    """Removes stored tokens from both keyring and the fallback file, if present."""
    try:
        keyring.delete_password(_SERVICE_NAME, _KEYRING_USERNAME)
    except Exception:
        pass  # never wrote there (fallback path), or already absent -- both fine to ignore
    _clear_fallback()
