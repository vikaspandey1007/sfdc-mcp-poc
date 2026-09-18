"""Custom Policy MCP server (Gate 7).

Built on the official `mcp` Python SDK's FastMCP helper (transitively
installed via google-adk[mcp] -- see pyproject.toml), the same SDK
Salesforce's own Hosted MCP server is built on, per the vendor-neutral MCP
boundary this project's architecture requires: the agent talks to this
server the exact same way it talks to Salesforce's, through the MCP
protocol, not through a Python import or a shared function call.

Transport: stdio. This is a fully local, trusted, single-process server
(spawned as a subprocess by agent/mcp_config.py, one per agent process) --
there is no network boundary to secure and no OAuth to perform, so stdio is
the simplest transport that fits, not Streamable HTTP (which would need a
port, a URL, and answering "who else can reach it"), and not SSE (deprecated
in favour of Streamable HTTP for anything that does need HTTP). "Local
stdio" is a POC deployment choice, not the architectural pattern -- see
docs/architecture.md's Gate 7 section for why swapping this server for a
hosted one later would not change how the agent uses it.

No Salesforce credentials, OAuth tokens, or Gemini credentials exist in
this module or anywhere under policy_mcp/ (AT-07-08) -- every tool here
takes already-retrieved facts as plain arguments and returns a computed
result; nothing here calls out to Salesforce, Gemini, or any network at
all. Only two tools are exposed (score_opportunity, get_scoring_policy),
deliberately narrow rather than a generic "run this code"/"query this"
capability -- see policy_mcp/policy.py's own docstring for the scoring
rules and docs/security-model.md's Gate 7 section for why that narrowness
is itself a security property, not just a design preference.

Run directly for manual smoke-testing:
    python -m policy_mcp.server
Normally spawned automatically by agent/mcp_config.py's
build_policy_mcp_toolset(), not run manually.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from policy_mcp.policy import get_policy_rules as _get_policy_rules
from policy_mcp.policy import score_opportunity as _score_opportunity

mcp = FastMCP(name="policy-mcp")


@mcp.tool()
def score_opportunity(
    amount: float,
    stage: str,
    days_since_activity: int,
    is_strategic_account: bool,
    close_date: str | None = None,
) -> dict:
    """Scores one Salesforce opportunity against this project's deterministic
    revenue-prioritisation policy (see get_scoring_policy for the rules
    themselves). Every argument is a fact about the opportunity that the
    caller must already have retrieved elsewhere (e.g. from Salesforce MCP)
    -- this tool does not look anything up itself.

    Args:
        amount: The opportunity's Amount field, in USD.
        stage: The opportunity's StageName field (e.g. "Proposal/Price Quote").
        days_since_activity: Days since the opportunity's last meaningful activity.
        is_strategic_account: Whether the related account is a strategic account.
        close_date: The opportunity's CloseDate, as an ISO date string (YYYY-MM-DD),
            if known.

    Returns:
        A dict with `score` (integer points earned), `max_possible_score`,
        `factors` (which rules applied and why), and a human-readable
        `explanation` string.

    Raises invalid-argument errors (surfaced as an MCP tool error, never a
    fabricated score) for negative amounts, negative days_since_activity, an
    empty stage, or a close_date that isn't a valid ISO date.
    """
    result = _score_opportunity(
        amount=amount,
        stage=stage,
        days_since_activity=days_since_activity,
        is_strategic_account=is_strategic_account,
        close_date=close_date,
    )
    return result.to_dict()


@mcp.tool()
def get_scoring_policy() -> dict:
    """Returns this project's deterministic revenue-prioritisation policy
    itself -- the exact rules and point values score_opportunity applies --
    so a caller can explain *why* a score came out the way it did, rather
    than treating score_opportunity as a black box.

    Returns:
        A dict with `source` (where this policy comes from), `max_possible_score`,
        and `rules` (a list of {rule, points, description}).
    """
    return _get_policy_rules()


if __name__ == "__main__":
    mcp.run(transport="stdio")
