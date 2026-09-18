"""Offline unit tests for policy_mcp/policy.py (deterministic scoring logic)
and a real-stdio-transport smoke test of policy_mcp/server.py itself.

Covers:
  AT-07-01: Policy MCP starts and exposes the expected tool catalogue.
  AT-07-02: Policy scoring is deterministic for known inputs.
  AT-07-03: Invalid/missing inputs fail safely and do not produce fabricated
            scores.
  AT-07-08: no Salesforce/Gemini credentials anywhere in this module or the
            module under test (nothing here even imports agent/auth code).

Nothing here touches Salesforce, Gemini, or the network -- policy_mcp has
no dependency on either, by design (see policy_mcp/policy.py's docstring).
The server-catalogue test does spawn a real subprocess over stdio (the
actual transport agent/mcp_config.py uses), not a mock, since AT-07-01 is
specifically about the *server* starting and advertising tools, which a
call directly into policy.py's Python functions wouldn't prove.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from policy_mcp.policy import (
    InvalidOpportunityFactsError,
    get_policy_rules,
    score_opportunity,
)

# -- AT-07-02: deterministic scoring for known inputs --


def test_score_is_deterministic_across_repeated_calls() -> None:
    kwargs = dict(amount=300_000, stage="Proposal/Price Quote", days_since_activity=20, is_strategic_account=True)
    first = score_opportunity(**kwargs)
    second = score_opportunity(**kwargs)
    assert first.to_dict() == second.to_dict()


def test_all_five_rules_apply_when_every_condition_is_met() -> None:
    result = score_opportunity(
        amount=300_000,
        stage="Negotiation/Review",
        days_since_activity=20,
        is_strategic_account=True,
        close_date="2026-10-15",
        as_of_date="2026-10-01",
    )
    assert result.score == 10
    assert result.max_possible_score == 10
    assert all(f.applied for f in result.factors)


def test_no_rules_apply_for_a_low_priority_opportunity() -> None:
    result = score_opportunity(
        amount=50_000,
        stage="Qualification",
        days_since_activity=2,
        is_strategic_account=False,
    )
    assert result.score == 0
    assert not any(f.applied for f in result.factors)
    assert "no prioritisation rules matched" in result.explanation


def test_amount_rule_uses_strict_greater_than() -> None:
    exactly_at_threshold = score_opportunity(
        amount=250_000, stage="Qualification", days_since_activity=0, is_strategic_account=False
    )
    just_over_threshold = score_opportunity(
        amount=250_000.01, stage="Qualification", days_since_activity=0, is_strategic_account=False
    )
    assert exactly_at_threshold.score == 0
    assert just_over_threshold.score == 3


def test_close_date_rule_only_applies_within_the_window() -> None:
    within_window = score_opportunity(
        amount=0, stage="Qualification", days_since_activity=0, is_strategic_account=False,
        close_date="2026-01-20", as_of_date="2026-01-01",
    )
    outside_window = score_opportunity(
        amount=0, stage="Qualification", days_since_activity=0, is_strategic_account=False,
        close_date="2026-03-01", as_of_date="2026-01-01",
    )
    already_passed = score_opportunity(
        amount=0, stage="Qualification", days_since_activity=0, is_strategic_account=False,
        close_date="2025-12-01", as_of_date="2026-01-01",
    )
    assert within_window.score == 2
    assert outside_window.score == 0
    assert already_passed.score == 0


def test_stage_rule_is_case_insensitive() -> None:
    result = score_opportunity(
        amount=0, stage="PROPOSAL/PRICE QUOTE", days_since_activity=0, is_strategic_account=False
    )
    assert result.score == 1


def test_get_policy_rules_matches_the_scoring_function() -> None:
    """Pins that the human-readable catalogue (what an agent/human would cite
    to explain a score) doesn't silently drift from what score_opportunity
    actually computes -- same five rules, same points, same order."""
    rules = get_policy_rules()
    rule_points = {r["rule"]: r["points"] for r in rules["rules"]}
    assert rule_points == {
        "amount_over_threshold": 3,
        "close_date_within_window": 2,
        "strategic_account": 2,
        "stale_activity": 2,
        "priority_stage": 1,
    }
    assert rules["max_possible_score"] == 10 == sum(rule_points.values())


# -- AT-07-03: invalid/missing inputs fail safely, no fabricated score --


@pytest.mark.parametrize(
    "bad_kwargs",
    [
        dict(amount=-1, stage="Qualification", days_since_activity=0, is_strategic_account=False),
        dict(amount="a lot", stage="Qualification", days_since_activity=0, is_strategic_account=False),
        dict(amount=0, stage="", days_since_activity=0, is_strategic_account=False),
        dict(amount=0, stage="   ", days_since_activity=0, is_strategic_account=False),
        dict(amount=0, stage=42, days_since_activity=0, is_strategic_account=False),
        dict(amount=0, stage="Qualification", days_since_activity=-5, is_strategic_account=False),
        dict(amount=0, stage="Qualification", days_since_activity=1.5, is_strategic_account=False),
        dict(amount=0, stage="Qualification", days_since_activity=0, is_strategic_account="yes"),
        dict(amount=0, stage="Qualification", days_since_activity=0, is_strategic_account=False, close_date="not-a-date"),
    ],
)
def test_invalid_inputs_raise_rather_than_produce_a_score(bad_kwargs: dict) -> None:
    with pytest.raises(InvalidOpportunityFactsError):
        score_opportunity(**bad_kwargs)


# -- AT-07-01: the server itself starts and exposes the expected catalogue --


def test_server_starts_over_real_stdio_and_exposes_expected_tools() -> None:
    """Spawns the actual server as a subprocess over stdio -- the same
    transport agent/mcp_config.py uses -- rather than calling FastMCP's
    Python object directly, since the thing AT-07-01 is proving is that the
    *process* starts and speaks MCP correctly, not just that the underlying
    functions work."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def _run() -> set[str]:
        params = StdioServerParameters(command=sys.executable, args=["-m", "policy_mcp.server"])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                return {tool.name for tool in tools.tools}

    tool_names = asyncio.run(_run())
    assert tool_names == {"score_opportunity", "get_scoring_policy"}


def test_server_tool_call_over_stdio_rejects_invalid_input_as_an_mcp_error() -> None:
    """AT-07-03 at the transport level: a bad call must come back as an MCP
    tool error (isError=True), never a 200-shaped fabricated score."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client

    async def _run() -> bool:
        params = StdioServerParameters(command=sys.executable, args=["-m", "policy_mcp.server"])
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(
                    "score_opportunity",
                    {"amount": -1, "stage": "Qualification", "days_since_activity": 0, "is_strategic_account": False},
                )
                return result.isError

    assert asyncio.run(_run()) is True


# -- AT-07-08: no Salesforce/Gemini credentials anywhere in policy_mcp/ --


def test_policy_mcp_source_has_no_salesforce_or_gemini_credential_material() -> None:
    """Static check, not just "we didn't happen to use one": scans every
    policy_mcp/*.py source file for the actual env var names and import
    paths those credentials would show up under if this module ever grew a
    dependency on Salesforce or Gemini. This module has no business
    importing agent.* or auth.* at all -- score_opportunity/get_scoring_policy
    take facts as arguments; they never fetch anything themselves."""
    forbidden_tokens = (
        "SF_MY_DOMAIN_URL", "SF_ECA_CONSUMER_KEY", "SF_MCP_SERVER_URL",
        "GOOGLE_API_KEY", "GOOGLE_GENAI_MODEL", "DEMO_API_KEY",
        "CREDENTIAL_ENCRYPTION_KEY", "Authorization", "Bearer",
        "import agent", "from agent", "import auth", "from auth",
    )
    policy_mcp_dir = Path(__file__).parent.parent / "policy_mcp"
    for source_file in policy_mcp_dir.glob("*.py"):
        text = source_file.read_text(encoding="utf-8")
        for token in forbidden_tokens:
            assert token not in text, f"{source_file.name} unexpectedly contains {token!r}"
