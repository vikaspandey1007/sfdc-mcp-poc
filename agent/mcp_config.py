"""McpToolset wiring for the Salesforce Hosted MCP (sobject-reads) server.

Branch 3B: header_provider-based dynamic Bearer auth via the auth/
token broker, NOT ADK's native auth_scheme/auth_credential. Branch 3A
(native OAuth) was attempted first and failed reproducibly -- google-adk
2.9.1's OAuth2 AuthHandler unconditionally requires a client_secret, which
this ECA (a genuine public/PKCE-only client) does not have. Full evidence:
docs/troubleshooting.md ("Branch 3A result: FAIL"),
docs/decisions/ADR-002-oauth-authentication-strategy.md.

Auth/credential/connection types match google-adk 2.9.1's actually installed
signatures (inspected via `inspect.signature`, not assumed from docs) -- see
docs/troubleshooting.md "Installed API vs. researched API".
"""

from __future__ import annotations

from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.mcp_tool.mcp_session_manager import StreamableHTTPConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset

from agent.config import get_core_settings
from auth.token_broker import get_valid_access_token


def _header_provider(_context: ReadonlyContext) -> dict[str, str]:
    """Called before each MCP session -- always returns a currently-valid token.

    get_valid_access_token() refreshes proactively if the stored access token
    is near expiry, so a long-running agent process keeps working without a
    restart (the reason header_provider was chosen over a static header).
    """
    return {"Authorization": f"Bearer {get_valid_access_token()}"}


def build_salesforce_mcp_toolset() -> McpToolset:
    """Builds the McpToolset for sobject-reads, Branch 3B (token-broker auth).

    Does not require GOOGLE_API_KEY -- only the Salesforce-side env vars
    (get_core_settings), so this can be constructed and inspected before a
    Gemini key exists. Does require that `python -m auth.token_broker` has
    already been run once interactively -- get_valid_access_token() raises a
    clear error otherwise, surfaced the first time the agent actually calls
    a tool.
    """
    _, _, sf_mcp_server_url = get_core_settings()
    return McpToolset(
        connection_params=StreamableHTTPConnectionParams(url=sf_mcp_server_url),
        header_provider=_header_provider,
    )
