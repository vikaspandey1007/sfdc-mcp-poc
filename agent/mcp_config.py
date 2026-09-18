"""McpToolset wiring for this agent's two MCP servers.

1. Salesforce Hosted MCP (sobject-reads) -- Branch 3B: header_provider-based
   dynamic Bearer auth via the auth/ token broker, NOT ADK's native
   auth_scheme/auth_credential. Branch 3A (native OAuth) was attempted first
   and failed reproducibly -- google-adk 2.9.1's OAuth2 AuthHandler
   unconditionally requires a client_secret, which this ECA (a genuine
   public/PKCE-only client) does not have. Full evidence:
   docs/troubleshooting.md ("Branch 3A result: FAIL"),
   docs/decisions/ADR-002-oauth-authentication-strategy.md.
2. Custom Policy MCP (policy_mcp/server.py, Gate 7) -- a local subprocess
   over stdio, no auth at all (see docs/decisions/ADR-004-policy-mcp-design.md
   for why stdio, why local, why no database).

Both are wired as ordinary McpToolset instances -- the agent (agent/agent.py)
talks to each the same way, through the MCP protocol, regardless of which
one is vendor-hosted and which one is ours. That equivalence is Gate 7's
actual point, not just "a second server exists."

Auth/credential/connection types match google-adk 2.9.1's actually installed
signatures (inspected via `inspect.signature`, not assumed from docs) -- see
docs/troubleshooting.md "Installed API vs. researched API".
"""

from __future__ import annotations

import sys

from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.tools.mcp_tool.mcp_session_manager import (
    StdioConnectionParams,
    StreamableHTTPConnectionParams,
)
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from mcp import StdioServerParameters

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


def build_policy_mcp_toolset() -> McpToolset:
    """Builds the McpToolset for the custom Policy MCP server (Gate 7).

    Spawns `python -m policy_mcp.server` as a stdio subprocess -- `sys.executable`
    so the exact same interpreter/venv running the agent runs the server, not
    whatever "python" happens to resolve to on PATH. No Salesforce or Gemini
    env vars are required to build this toolset, matching
    build_salesforce_mcp_toolset()'s own "constructible before other config
    exists" property.
    """
    return McpToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                command=sys.executable,
                args=["-m", "policy_mcp.server"],
            ),
        ),
    )
