"""LocalCredentialStore -- development-only CredentialStore backed by the OS
keyring (Windows Credential Manager on this machine).

Refactored from the original auth/token_store.py (Gate 3B) into the
CredentialStore interface (Gate 4 Step 1). Preserves every security property
established during Gate 3's post-merge security review
(docs/troubleshooting.md "Security review findings"), with one deliberate
hardening on top:

- The token pair itself: OS keyring first; a Fernet-encrypted file outside
  the repo tree as fallback, since a real Salesforce JWT access_token +
  refresh_token pair can exceed Windows Credential Manager's ~2560-byte
  blob limit (see docs/troubleshooting.md "Windows Credential Manager blob
  size limit"). This fallback is expected and fine -- it's ciphertext only.
- The Fernet key that protects that fallback file: OS keyring ONLY. Unlike
  the original implementation's fallback-of-a-fallback, this refactor does
  NOT degrade to writing the key beside its own ciphertext if keyring is
  entirely unavailable -- it raises instead (see `_fallback_key`). Gate 4's
  own spec calls this out explicitly: this store "must NOT silently fall
  back to colocated key + encrypted file." A logged warning followed by a
  weaker security posture is still a silent failure in the sense that
  matters here (the process keeps running in a degraded state); raising is
  the honest failure mode for what is explicitly a development-only store
  that should never be relied on in a hosted context anyway.

Never logs/prints a token value -- see docs/gate-0-plan.md AT-06.
"""

from __future__ import annotations

import json
import logging
import stat
from dataclasses import asdict
from pathlib import Path
from typing import Optional

import keyring
from cryptography.fernet import Fernet

from auth.credential_store import CredentialStore, StoredTokens

logger = logging.getLogger(__name__)

_SERVICE_NAME = "sfdc-mcp-poc-token-broker"
_KEYRING_USERNAME = "revenue-agent-mcp-client"
_FALLBACK_KEY_KEYRING_USERNAME = "revenue-agent-mcp-client-fallback-key"

# Fallback location -- deliberately outside the repo tree. Local/dev only:
# never used on Render, where the filesystem is not durable and must not
# hold credentials at all (see auth/credential_store.py's on-Render guard).
_FALLBACK_DIR = Path.home() / ".sfdc-mcp-poc"
_FALLBACK_TOKEN_FILE = _FALLBACK_DIR / "token_store.enc"
_LEGACY_FALLBACK_KEY_FILE = _FALLBACK_DIR / "token_key.bin"


class LocalCredentialStore(CredentialStore):
    """Development-only. Do not use in a hosted/container environment --
    OS keyring is not a meaningful concept there, and this store's
    filesystem fallback would violate Gate 4's "never persist to the
    Render filesystem" principle."""

    def load(self) -> Optional[StoredTokens]:
        try:
            payload = keyring.get_password(_SERVICE_NAME, _KEYRING_USERNAME)
            if payload:
                return StoredTokens(**json.loads(payload))
            return self._load_fallback()
        except Exception as exc:
            logger.warning("Keyring read failed (%s), reading encrypted file fallback.", type(exc).__name__)
            return self._load_fallback()

    def save(self, tokens: StoredTokens) -> None:
        payload = json.dumps(asdict(tokens))
        try:
            keyring.set_password(_SERVICE_NAME, _KEYRING_USERNAME, payload)
            logger.info("Tokens saved to OS keyring.")
        except Exception as exc:
            logger.warning("Keyring write failed (%s), falling back to encrypted file.", type(exc).__name__)
            self._save_fallback(tokens)

    def clear(self) -> None:
        try:
            keyring.delete_password(_SERVICE_NAME, _KEYRING_USERNAME)
        except Exception:
            pass  # never wrote there (fallback path), or already absent -- both fine to ignore
        _FALLBACK_TOKEN_FILE.unlink(missing_ok=True)

    # -- fallback file for the token pair itself (ciphertext only) --

    def _save_fallback(self, tokens: StoredTokens) -> None:
        fernet = Fernet(self._fallback_key())
        payload = json.dumps(asdict(tokens)).encode("utf-8")
        _FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
        _FALLBACK_TOKEN_FILE.write_bytes(fernet.encrypt(payload))
        try:
            _FALLBACK_TOKEN_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)  # 0o600, best-effort on Windows
        except OSError:
            pass

    def _load_fallback(self) -> Optional[StoredTokens]:
        if not _FALLBACK_TOKEN_FILE.exists():
            return None
        fernet = Fernet(self._fallback_key())
        payload = fernet.decrypt(_FALLBACK_TOKEN_FILE.read_bytes())
        return StoredTokens(**json.loads(payload))

    # -- the fallback file's own encryption key: keyring only, never disk --

    def _fallback_key(self) -> bytes:
        """Returns the Fernet key for the fallback token file, from OS
        keyring. Migrates a legacy file-based key (from before this
        refactor) into keyring on first use, so an already-encrypted token
        file doesn't get orphaned, then deletes the file copy.

        Deliberately does NOT catch a keyring failure here -- if keyring is
        unavailable outright, this raises and propagates up through
        save()/load()'s own except blocks (which only catch the *primary*
        keyring call for the token pair itself) rather than degrading to a
        colocated key+ciphertext scheme. See this module's docstring.
        """
        existing = keyring.get_password(_SERVICE_NAME, _FALLBACK_KEY_KEYRING_USERNAME)
        if existing:
            return existing.encode("ascii")

        if _LEGACY_FALLBACK_KEY_FILE.exists():
            key = _LEGACY_FALLBACK_KEY_FILE.read_bytes()
            logger.info("Migrating fallback encryption key from file to OS keyring.")
        else:
            key = Fernet.generate_key()

        keyring.set_password(_SERVICE_NAME, _FALLBACK_KEY_KEYRING_USERNAME, key.decode("ascii"))
        _LEGACY_FALLBACK_KEY_FILE.unlink(missing_ok=True)  # migrated -- don't leave a second copy on disk
        return key
