"""One-time interactive OAuth 2.0 Authorization Code + PKCE exchange against
the Salesforce ECA, plus proactive refresh -- the Gate 3B fallback, built
only because Branch 3A failed reproducibly (see
docs/decisions/ADR-002-oauth-authentication-strategy.md).

Endpoints, scope, and the "no client_secret, send client_id in body" shape
are copied from Gate 2's proven-working Postman configuration
(salesforce/postman-verification.md), not re-derived.

Run interactively once:
    python -m auth.token_broker

Never logs/prints a token value -- only field names/shapes, matching the
redaction discipline established in Gates 1/2 (AT-06).
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import logging
import secrets
import sys
import time
import urllib.parse
import urllib.request
import webbrowser
from dataclasses import dataclass
from typing import Optional

from agent.config import get_core_settings
from auth.token_store import StoredTokens, load_tokens, save_tokens

logger = logging.getLogger(__name__)

_REDIRECT_URI = "http://localhost:8765/callback"
_SCOPE = "mcp_api refresh_token"
_CALLBACK_HOST = "localhost"
_CALLBACK_PORT = 8765
# Refresh this many seconds before actual expiry, to avoid racing a
# still-in-flight MCP call against a token that expires mid-request.
_REFRESH_SKEW_SECONDS = 60


class _AuthCodeNotReceived(RuntimeError):
    pass


@dataclass
class _CallbackResult:
    code: Optional[str] = None
    state: Optional[str] = None
    error: Optional[str] = None


def _generate_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)  # ~86 chars, within RFC 7636's 43-128 bound
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def _run_callback_server(expected_state: str) -> _CallbackResult:
    """Blocks for exactly one request to the redirect URI, then stops."""
    result = _CallbackResult()

    class _Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature
            pass  # suppress default request logging (could otherwise log the code in the URL)

        def do_GET(self) -> None:  # noqa: N802 - stdlib method name
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            result.code = params.get("code", [None])[0]
            result.state = params.get("state", [None])[0]
            result.error = params.get("error_description", params.get("error", [None]))[0]

            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            if result.error:
                self.wfile.write(b"<html><body>Authorization failed. You can close this window.</body></html>")
            else:
                self.wfile.write(b"<html><body>Authorized. You can close this window.</body></html>")

    server = http.server.HTTPServer((_CALLBACK_HOST, _CALLBACK_PORT), _Handler)
    server.handle_request()  # blocks for exactly one request
    server.server_close()

    if result.error:
        raise _AuthCodeNotReceived(f"Authorization failed: {result.error}")
    if not result.code:
        raise _AuthCodeNotReceived("No authorization code received on callback.")
    if result.state != expected_state:
        raise _AuthCodeNotReceived("State mismatch on callback -- possible CSRF, aborting.")
    return result


def _post_token_request(token_url: str, params: dict[str, str]) -> dict:
    data = urllib.parse.urlencode(params).encode("ascii")
    req = urllib.request.Request(
        token_url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        import json

        return json.loads(resp.read())


def run_interactive_authorization() -> StoredTokens:
    """Performs the one-time interactive Authorization Code + PKCE exchange.

    Opens a browser for the user to log in/consent as the demo Salesforce
    user, catches the redirect locally, exchanges the code for tokens (no
    client_secret -- this is a public/PKCE-only client, see ADR-002), and
    persists the result via auth.token_store.
    """
    sf_my_domain_url, sf_eca_consumer_key, _ = get_core_settings()
    authorize_url = f"{sf_my_domain_url}/services/oauth2/authorize"
    token_url = f"{sf_my_domain_url}/services/oauth2/token"

    code_verifier, code_challenge = _generate_pkce_pair()
    state = secrets.token_urlsafe(16)

    auth_params = {
        "response_type": "code",
        "client_id": sf_eca_consumer_key,
        "redirect_uri": _REDIRECT_URI,
        "scope": _SCOPE,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
        "state": state,
    }
    full_authorize_url = f"{authorize_url}?{urllib.parse.urlencode(auth_params)}"

    logger.info("Opening browser for Salesforce login/consent...")
    webbrowser.open(full_authorize_url)

    callback = _run_callback_server(expected_state=state)
    logger.info("Authorization code received, exchanging for tokens...")

    token_response = _post_token_request(
        token_url,
        {
            "grant_type": "authorization_code",
            "code": callback.code,
            "client_id": sf_eca_consumer_key,
            "redirect_uri": _REDIRECT_URI,
            "code_verifier": code_verifier,
        },
    )

    tokens = StoredTokens(
        access_token=token_response["access_token"],
        refresh_token=token_response["refresh_token"],
        expires_at=time.time() + float(token_response.get("expires_in", 7200)),
        token_type=token_response.get("token_type", "Bearer"),
    )
    save_tokens(tokens)
    logger.info("Tokens saved (fields: access_token, refresh_token, expires_at, token_type; values not logged).")
    return tokens


def refresh_access_token(stored: StoredTokens) -> StoredTokens:
    """Exchanges the stored refresh_token for a new access_token.

    Refresh Token Rotation is enabled on the ECA (salesforce/external-client-app.md),
    so the response's refresh_token replaces the stored one -- the old one is
    invalidated server-side the moment this succeeds.
    """
    sf_my_domain_url, sf_eca_consumer_key, _ = get_core_settings()
    token_url = f"{sf_my_domain_url}/services/oauth2/token"

    token_response = _post_token_request(
        token_url,
        {
            "grant_type": "refresh_token",
            "refresh_token": stored.refresh_token,
            "client_id": sf_eca_consumer_key,
        },
    )

    new_refresh_token = token_response.get("refresh_token", stored.refresh_token)
    tokens = StoredTokens(
        access_token=token_response["access_token"],
        refresh_token=new_refresh_token,
        expires_at=time.time() + float(token_response.get("expires_in", 7200)),
        token_type=token_response.get("token_type", "Bearer"),
    )
    save_tokens(tokens)
    logger.info("Access token refreshed (values not logged).")
    return tokens


def get_valid_access_token() -> str:
    """Returns a currently-valid access token, refreshing proactively if needed.

    Raises RuntimeError with a clear message if no tokens exist yet -- the
    caller (agent/mcp_config.py's header_provider) should surface that
    rather than let a bare KeyError/None propagate.
    """
    stored = load_tokens()
    if stored is None:
        raise RuntimeError(
            "No Salesforce tokens found. Run `python -m auth.token_broker` once "
            "to authorize interactively before starting the agent."
        )
    if stored.expires_at - _REFRESH_SKEW_SECONDS <= time.time():
        stored = refresh_access_token(stored)
    return stored.access_token


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    try:
        run_interactive_authorization()
        print("Authorization complete. Tokens stored.")
    except _AuthCodeNotReceived as exc:
        print(f"Authorization failed: {exc}", file=sys.stderr)
        sys.exit(1)
