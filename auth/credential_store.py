"""Abstraction over where Salesforce OAuth tokens are persisted.

Introduced for Gate 4 so the rest of the auth/agent code (auth/token_broker.py,
agent/mcp_config.py) depends only on this interface, not on which concrete
backend is active. Two backends exist:

- LocalCredentialStore (auth/local_credential_store.py) -- development only,
  OS keyring.
- HostedCredentialStore (auth/hosted_credential_store.py) -- Render, backed
  by a managed Key Value instance. Selected after a researched comparison
  against Render Disks, Render PostgreSQL, and an external secrets manager
  (see auth/hosted_credential_store.py's module docstring for the outcome).

StoredTokens lives here (not in either backend module) since it's the shared
value type both read and write, not something either backend owns.
"""

from __future__ import annotations

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class StoredTokens:
    access_token: str
    refresh_token: str
    expires_at: float  # unix timestamp
    token_type: str = "Bearer"


class CredentialStore(ABC):
    """Persists/retrieves the Salesforce OAuth token pair.

    Implementations must never log or print a token value (see
    docs/gate-0-plan.md AT-06) and must never store an encryption key beside
    the ciphertext it protects -- see docs/troubleshooting.md "Security
    review findings" for why that matters and what it looks like when done
    wrong.
    """

    @abstractmethod
    def load(self) -> Optional[StoredTokens]:
        """Returns the stored tokens, or None if nothing has been stored yet."""

    @abstractmethod
    def save(self, tokens: StoredTokens) -> None:
        """Persists tokens, replacing whatever was stored before."""

    @abstractmethod
    def clear(self) -> None:
        """Removes any stored tokens. Safe to call when nothing is stored."""


def get_credential_store() -> CredentialStore:
    """Selects the active CredentialStore backend.

    CREDENTIAL_STORE_BACKEND=local (default off Render) -- OS keyring,
    development only.
    CREDENTIAL_STORE_BACKEND=hosted -- Render Key Value-backed persistence
    (auth/hosted_credential_store.py). Required (and enforced below) when
    running on Render.

    Refuses to default to Local at all when running on Render (detected via
    the RENDER env var Render sets on every service) even if
    CREDENTIAL_STORE_BACKEND wasn't set -- Local's OS-keyring dependency is
    not a meaningful concept in a container, and silently limping along on
    it there would violate the "never persist to the Render filesystem"
    principle the moment its own file-fallback path ever triggered.
    """
    backend = os.environ.get("CREDENTIAL_STORE_BACKEND", "").strip().lower()
    on_render = os.environ.get("RENDER", "").strip().lower() == "true"

    if not backend:
        if on_render:
            raise RuntimeError(
                "Running on Render (RENDER=true) but CREDENTIAL_STORE_BACKEND is not set. "
                "Set CREDENTIAL_STORE_BACKEND=hosted explicitly -- refusing to default to the "
                "development-only local store in a hosted environment."
            )
        backend = "local"

    if backend == "local":
        from auth.local_credential_store import LocalCredentialStore

        return LocalCredentialStore()
    if backend == "hosted":
        from auth.hosted_credential_store import HostedCredentialStore

        return HostedCredentialStore()
    raise RuntimeError(f"Unknown CREDENTIAL_STORE_BACKEND={backend!r} -- expected 'local' or 'hosted'.")
