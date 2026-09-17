"""HostedCredentialStore -- Render-appropriate CredentialStore backed by a
managed Key Value (Redis-compatible) instance.

Chosen after a researched comparison presented for Gate 4 Step 1 (Render
Disks: rejected outright, filesystem-based, and Gate 4's own principle 3
forbids persisting credentials to the Render filesystem; Render PostgreSQL:
a viable, slightly cheaper alternative, but a full relational database is
more infrastructure than storing one small blob needs, and Gate 4 Step 2
explicitly lists "unnecessary databases" as something to avoid; an external
secrets manager (AWS/GCP/Vault/Doppler): strongest secret-specific tooling,
but adds a second cloud platform dependency disproportionate to a POC).
Render Key Value was approved as the hosted persistence technology.

Render Key Value's free tier has NO persistence at all (data lost on
restart) -- this store requires a paid instance provisioned with
Journal + Snapshot persistence. That's a deployment/provisioning decision,
not something this code can enforce; see the deployment docs once written.

Static vs. dynamic secrets (Gate 4 principle 5): the Fernet encryption key
is a static secret and lives in a Render environment variable
(CREDENTIAL_ENCRYPTION_KEY), set once via the dashboard/render.yaml, never
committed. The token pair is dynamic (refreshed every ~2 hours) and lives
as an encrypted blob in Key Value. The two are never colocated -- an
attacker who can read the Key Value instance's contents does not also get
the key to decrypt them, and vice versa for an attacker who can read the
environment configuration. Same principle as LocalCredentialStore's fix
for the file-fallback key (docs/troubleshooting.md "Security review
findings"), applied to the hosted backend from the start rather than
retrofitted.

Never logs/prints a token value -- see docs/gate-0-plan.md AT-06.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import asdict
from typing import Optional

import redis
from cryptography.fernet import Fernet

from auth.credential_store import CredentialStore, StoredTokens

logger = logging.getLogger(__name__)

_REDIS_KEY = "sfdc-mcp-poc:salesforce-tokens"
_REDIS_URL_ENV_VAR = "REDIS_URL"
_ENCRYPTION_KEY_ENV_VAR = "CREDENTIAL_ENCRYPTION_KEY"


class HostedCredentialStore(CredentialStore):
    """Render-appropriate CredentialStore: ciphertext in a managed Key Value
    instance, encryption key in a Render environment variable -- never
    colocated. See this module's docstring for why Key Value was chosen.

    Fails fast at construction (missing config, unreachable Key Value
    instance) rather than surfacing a confusing error on first real use --
    Gate 4's "fail fast when required configuration is missing" principle.
    """

    def __init__(self) -> None:
        redis_url = os.environ.get(_REDIS_URL_ENV_VAR)
        if not redis_url:
            raise RuntimeError(
                f"Missing required environment variable: {_REDIS_URL_ENV_VAR}. Set it to the "
                "Render Key Value instance's Internal Connection URL (Render dashboard -> "
                "Key Value instance -> Connect)."
            )
        encryption_key = os.environ.get(_ENCRYPTION_KEY_ENV_VAR)
        if not encryption_key:
            raise RuntimeError(
                f"Missing required environment variable: {_ENCRYPTION_KEY_ENV_VAR}. Generate one "
                'with `python -c "from cryptography.fernet import Fernet; '
                'print(Fernet.generate_key().decode())"` and set it as a Render secret environment '
                "variable -- never commit it, never store it in Key Value beside the ciphertext it "
                "protects."
            )

        self._fernet = Fernet(encryption_key.encode("ascii"))
        self._client = redis.Redis.from_url(redis_url, decode_responses=True)
        try:
            self._client.ping()
        except redis.RedisError as exc:
            raise RuntimeError(
                f"Could not reach the hosted Key Value store at startup ({type(exc).__name__}: {exc}). "
                f"Check {_REDIS_URL_ENV_VAR} points at a running, reachable Render Key Value instance."
            ) from exc

    def load(self) -> Optional[StoredTokens]:
        ciphertext = self._client.get(_REDIS_KEY)
        if not ciphertext:
            return None
        payload = self._fernet.decrypt(ciphertext.encode("ascii"))
        return StoredTokens(**json.loads(payload))

    def save(self, tokens: StoredTokens) -> None:
        payload = json.dumps(asdict(tokens)).encode("utf-8")
        ciphertext = self._fernet.encrypt(payload)
        self._client.set(_REDIS_KEY, ciphertext.decode("ascii"))
        logger.info("Tokens saved to hosted Key Value store.")

    def clear(self) -> None:
        self._client.delete(_REDIS_KEY)
