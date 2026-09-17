"""Hosted OAuth callback routes for the Salesforce Authorization Code + PKCE
flow (Gate 4 Step 3).

Local development keeps using auth.token_broker's own throwaway HTTP server
(`python -m auth.token_broker`) -- these routes exist only for the hosted
(Render) flow, where the redirect must land on the deployed service's own
public HTTPS URL, not localhost. Gate 4 Step 3 explicitly says not to remove
the local callback, only to add this one alongside it.

auth.token_broker.build_authorization_request()/exchange_code_for_tokens()
are the same environment-agnostic functions the local CLI flow uses --
nothing about the PKCE mechanics is duplicated here, only the HTTP plumbing
around it.

The state/code_verifier pair build_authorization_request() returns is
inherently short-lived and single-use, but /authorize and /callback are two
separate HTTP requests (the user's browser round-trips to Salesforce in
between), so something has to hold that pair between them. Rather than an
in-memory dict -- which would silently break the moment this service ever
ran more than one instance, and sits awkwardly next to "application
containers must be stateless" -- it's stored in the same Redis Key Value
instance already provisioned for token persistence (ADR-003), under a
different key namespace, with a short TTL so an abandoned flow self-cleans.

OAUTH_REDIRECT_URI must be set explicitly for these routes (no
request-derived fallback): Salesforce's token endpoint requires the
redirect_uri sent during the code exchange to exactly match the one used to
start the flow, and deriving it from request headers behind Render's proxy
would depend on X-Forwarded-Proto being correctly honored -- one more thing
that could silently go wrong. A fixed, explicitly-configured value is also
what Step 3 assumes when it says this URL "must be registered as an
additional Salesforce ECA callback URL": a known string, not something
computed per-request.

Never logs/prints a token, code, or state value -- see docs/gate-0-plan.md
AT-06.
"""

from __future__ import annotations

import logging
import os

import redis
from fastapi import APIRouter, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from auth.token_broker import build_authorization_request, exchange_code_for_tokens

logger = logging.getLogger(__name__)

router = APIRouter()

_PENDING_STATE_PREFIX = "sfdc-mcp-poc:oauth-pending-state:"
# Generous enough for a human to complete a Salesforce login, short enough
# that an abandoned flow doesn't linger in Redis indefinitely.
_PENDING_STATE_TTL_SECONDS = 600


def _redis_client() -> redis.Redis:
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        raise HTTPException(status_code=500, detail="REDIS_URL is not configured.")
    return redis.Redis.from_url(redis_url, decode_responses=True)


def _configured_redirect_uri() -> str:
    redirect_uri = os.environ.get("OAUTH_REDIRECT_URI")
    if not redirect_uri:
        raise HTTPException(
            status_code=500,
            detail="OAUTH_REDIRECT_URI is not configured. Set it to this service's registered "
            "callback URL, e.g. https://<service>.onrender.com/oauth/salesforce/callback.",
        )
    return redirect_uri


@router.get("/oauth/salesforce/authorize")
def start_authorization() -> RedirectResponse:
    """Starts the hosted PKCE flow: issues a fresh state/code_verifier pair,
    stashes the verifier in Redis keyed by state (TTL-bound), and redirects
    the browser to Salesforce's own login/consent page."""
    redirect_uri = _configured_redirect_uri()
    auth_request = build_authorization_request(redirect_uri)

    client = _redis_client()
    client.set(
        f"{_PENDING_STATE_PREFIX}{auth_request.state}",
        auth_request.code_verifier,
        ex=_PENDING_STATE_TTL_SECONDS,
    )
    logger.info("Started hosted OAuth authorization flow (state issued, values not logged).")
    return RedirectResponse(auth_request.url)


@router.get("/oauth/salesforce/callback")
def handle_callback(
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
    error_description: str | None = None,
) -> HTMLResponse:
    """Receives Salesforce's redirect, validates state (rejecting anything
    we didn't just issue -- the CSRF guard), and exchanges the code for
    tokens via the same exchange_code_for_tokens() the local flow uses."""
    if error:
        logger.warning("Salesforce authorization failed: %s", error)
        raise HTTPException(status_code=400, detail=f"Authorization failed: {error_description or error}")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Missing code or state on callback.")

    client = _redis_client()
    state_key = f"{_PENDING_STATE_PREFIX}{state}"
    code_verifier = client.get(state_key)
    if not code_verifier:
        # Expired, already used, or never issued by us -- reject rather than guess why.
        raise HTTPException(status_code=400, detail="Unknown or expired authorization state.")
    client.delete(state_key)  # single-use: consume before the token exchange, not after

    exchange_code_for_tokens(code=code, code_verifier=code_verifier, redirect_uri=_configured_redirect_uri())
    logger.info("Hosted OAuth authorization complete (values not logged).")
    return HTMLResponse("<html><body>Authorized. You can close this window.</body></html>")
