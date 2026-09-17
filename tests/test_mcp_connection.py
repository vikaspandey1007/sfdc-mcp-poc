"""Unit tests for agent/mcp_config.py -- Branch 3B (token-broker) wiring.

Asserted against google-adk 2.9.1's actually-installed McpToolset attributes,
inspected directly (`vars(instance)` on this installed version) rather than
assumed from docs -- see docs/troubleshooting.md "Installed API vs.
researched API". McpToolset has no public getters for connection_params /
header_provider / auth_scheme / auth_credential, only the private attributes
it stores them under (_connection_params, _header_provider, _auth_scheme,
_auth_credential, tool_filter).

Fully offline: constructing McpToolset does not open an MCP session (it
lazy-connects on first tool call), so nothing here touches the network or
requires real Salesforce/Gemini credentials.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent import mcp_config

_FIXTURES = Path(__file__).parent / "fixtures"
_TEST_MCP_SERVER_URL = "https://api.salesforce.com/platform/mcp/v1/platform/sobject-reads"


@pytest.fixture(autouse=True)
def _core_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pins the three core Salesforce vars for every test in this module,
    overriding whatever real .env values agent.config's module-level
    load_dotenv() already put into os.environ on first import."""
    monkeypatch.setenv("SF_MY_DOMAIN_URL", "https://test.my.salesforce.com")
    monkeypatch.setenv("SF_ECA_CONSUMER_KEY", "test-consumer-key")
    monkeypatch.setenv("SF_MCP_SERVER_URL", _TEST_MCP_SERVER_URL)


def test_toolset_points_at_configured_mcp_server_url() -> None:
    toolset = mcp_config.build_salesforce_mcp_toolset()
    assert toolset._connection_params.url == _TEST_MCP_SERVER_URL


def test_toolset_uses_header_provider_not_native_oauth() -> None:
    """Branch 3B regression guard: auth_scheme/auth_credential are Branch
    3A's mechanism, which failed reproducibly (docs/troubleshooting.md
    "Branch 3A result: FAIL") because google-adk 2.9.1's OAuth2 AuthHandler
    unconditionally requires a client_secret that this public/PKCE-only ECA
    doesn't have. If either is ever set again on this toolset, 3A's wiring
    has crept back in without the ADR being revisited."""
    toolset = mcp_config.build_salesforce_mcp_toolset()
    assert toolset._auth_scheme is None
    assert toolset._auth_credential is None
    assert toolset._header_provider is mcp_config._header_provider


def test_header_provider_returns_bearer_token_from_token_broker(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mcp_config, "get_valid_access_token", lambda: "unit-test-token-value")
    headers = mcp_config._header_provider(None)  # ReadonlyContext is unused by this provider
    assert headers == {"Authorization": "Bearer unit-test-token-value"}


def test_no_client_side_tool_filter_configured() -> None:
    """The read-only guarantee is structural at the MCP server's tool
    catalogue level (Gate 2 evidence: sobject-reads exposes exactly six
    tools, all self-annotated readOnlyHint=true/destructiveHint=false, with
    no create/update/delete tool defined at all -- see
    salesforce/postman-verification.md, "Evidence" #2 and #4). mcp_config.py
    deliberately adds no client-side tool_filter on top of that; this test
    pins that decision so it isn't silently changed to paper over a
    server-side regression instead of catching it."""
    toolset = mcp_config.build_salesforce_mcp_toolset()
    assert toolset.tool_filter is None


def test_build_toolset_missing_core_var_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SF_MCP_SERVER_URL", raising=False)
    with pytest.raises(RuntimeError, match="SF_MCP_SERVER_URL"):
        mcp_config.build_salesforce_mcp_toolset()


def test_build_toolset_does_not_require_gemini_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """agent/config.py's get_core_settings() is deliberately Gemini-free so
    this toolset can be built (and tested) before a Gemini key exists."""
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_GENAI_MODEL", raising=False)
    mcp_config.build_salesforce_mcp_toolset()  # must not raise


def test_sobject_reads_tool_catalogue_fixture_has_no_mutating_tools() -> None:
    """Regression guard pinned from Gate 2's captured tool-discovery evidence.
    This does not re-verify the live server -- that's the opt-in integration
    suite's job -- it pins the already-proven catalogue shape so any future
    change to this fixture is a deliberate, reviewed edit, not silent drift."""
    catalogue = json.loads((_FIXTURES / "sobject_reads_tools_list.json").read_text())
    tool_names = {tool["name"] for tool in catalogue["tools"]}
    assert tool_names == {
        "soqlQuery",
        "find",
        "getRelatedRecords",
        "listRecentSobjectRecords",
        "getUserInfo",
        "getObjectSchema",
    }
    for tool in catalogue["tools"]:
        assert tool["annotations"]["readOnlyHint"] is True
        assert tool["annotations"]["destructiveHint"] is False

    mutating_verbs = ("create", "update", "delete", "upsert", "merge")
    assert not any(verb in name.lower() for name in tool_names for verb in mutating_verbs)
