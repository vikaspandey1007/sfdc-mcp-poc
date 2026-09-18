"""Gate 7's core acceptance evidence: a single live question that makes the
agent orchestrate across BOTH MCP servers -- the vendor-hosted Salesforce
one and the custom local Policy one -- through the MCP protocol alone,
with the LLM itself deciding to call both, not Python application code
faking the orchestration.

Covers:
  AT-07-05: a live multi-MCP question causes the agent to use both
            Salesforce MCP and Policy MCP.
  AT-07-06: the final response combines Salesforce facts with Policy MCP
            output -- checked by capturing the actual opportunity
            identifiers Salesforce returned and the actual scores Policy
            MCP computed *in this run*, then requiring the final answer to
            quote at least one of each. A generic keyword check (does the
            text contain "opportunity" and "score" somewhere) would pass
            even if the model paraphrased or invented detail instead of
            citing the real retrieved facts -- this is deliberately
            language-fragile in the other direction: it fails unless the
            answer demonstrably used the real data, not just talked about
            the right topics.
  AT-07-07: no Salesforce mutation capability has been introduced (checked
            here at the live-catalogue level, same allowlist-not-blocklist
            method as test_integration_live.py and test_guardrails.py).

Opt-in, same as the other live suites (hits the real org and Gemini):
    pytest --run-integration tests/test_multi_mcp_live.py
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.integration

_FIXTURES = Path(__file__).parent / "fixtures"

_SALESFORCE_TOOL_NAMES = {
    tool["name"]
    for tool in json.loads((_FIXTURES / "sobject_reads_tools_list.json").read_text())["tools"]
}
_POLICY_TOOL_NAMES = {
    tool["name"]
    for tool in json.loads((_FIXTURES / "policy_mcp_tools_list.json").read_text())["tools"]
}
_MUTATING_VERBS = ("create", "update", "delete", "upsert", "merge", "execute")


def _parsed_tool_payload(function_response: Any) -> Any:
    """MCP tool responses carry `structuredContent` (already-parsed) when the
    tool declares one -- Salesforce's soqlQuery does; Policy MCP's plain-dict
    return does not, but always has the same JSON as text in `content[0]`.
    Falls back to parsing that text so either shape works."""
    response = function_response.response or {}
    structured = response.get("structuredContent")
    if structured is not None:
        return structured
    content = response.get("content") or []
    if content and content[0].get("type") == "text":
        try:
            return json.loads(content[0]["text"])
        except (json.JSONDecodeError, TypeError):
            return None
    return None


def _real_opportunity_identifiers_from_salesforce_responses(events) -> set[str]:
    """Every real Opportunity Name/Id actually returned by a soqlQuery call
    in this run -- not assumed from fixture/sample data, since which
    opportunities come back depends on the live org's current state."""
    identifiers: set[str] = set()
    for event in events:
        for response in event.get_function_responses():
            if response.name != "soqlQuery":
                continue
            payload = _parsed_tool_payload(response)
            if not isinstance(payload, dict):
                continue
            for record in payload.get("records", []):
                if not isinstance(record, dict):
                    continue
                if record.get("Name"):
                    identifiers.add(str(record["Name"]))
                if record.get("Id"):
                    identifiers.add(str(record["Id"]))
    return identifiers


def _real_score_strings_from_policy_responses(events) -> set[str]:
    """Every real `score/max_possible_score` pair actually computed by a
    score_opportunity call in this run, as a regex tolerant of the model's
    own formatting variance (e.g. "8/10" vs "10 / 10", both observed live)."""
    score_patterns: set[str] = set()
    for event in events:
        for response in event.get_function_responses():
            if response.name != "score_opportunity":
                continue
            payload = _parsed_tool_payload(response)
            if not isinstance(payload, dict) or "score" not in payload:
                continue
            score = payload["score"]
            max_score = payload.get("max_possible_score")
            score_patterns.add(rf"{score}\s*/\s*{max_score}")
    return score_patterns


@pytest.fixture
def runner():
    from google.adk.runners import InMemoryRunner

    from agent.agent import root_agent

    return InMemoryRunner(agent=root_agent)


def test_prioritisation_question_uses_both_mcp_servers_and_combines_their_output(runner) -> None:
    agent = runner.agent
    captured_catalogue: dict[str, set[str]] = {}
    original_callback = agent.before_model_callback

    def _capture_advertised_tools(callback_context, llm_request):
        captured_catalogue["names"] = set(llm_request.tools_dict.keys())
        return None

    agent.before_model_callback = _capture_advertised_tools
    try:
        events = asyncio.run(
            runner.run_debug(
                "Using our revenue prioritisation policy, which of my high-value open "
                "opportunities should I prioritise and why?",
                session_id="gate7-multi-mcp-prioritisation",
                quiet=True,
            )
        )
    finally:
        agent.before_model_callback = original_callback

    # AT-07-07: the live catalogue is still exactly the known-safe union of
    # both servers' tools -- neither has grown a mutation-shaped capability.
    assert "names" in captured_catalogue, "before_model_callback never fired -- no model call was made"
    assert captured_catalogue["names"] == _SALESFORCE_TOOL_NAMES | _POLICY_TOOL_NAMES, (
        f"Live combined MCP catalogue {captured_catalogue['names']} no longer matches the approved "
        f"allowlist {_SALESFORCE_TOOL_NAMES | _POLICY_TOOL_NAMES} -- a capability was added or removed."
    )
    assert not any(
        verb in name.lower() for name in captured_catalogue["names"] for verb in _MUTATING_VERBS
    ), f"A mutation-shaped tool name appeared in the live catalogue: {captured_catalogue['names']}"

    tool_calls = [call.name for event in events for call in event.get_function_calls()]

    # AT-07-05: the agent itself chose to call into both servers for this
    # question -- not asserted by construction, this is the actual trace.
    salesforce_calls = [name for name in tool_calls if name in _SALESFORCE_TOOL_NAMES]
    policy_calls = [name for name in tool_calls if name in _POLICY_TOOL_NAMES]
    assert salesforce_calls, f"Expected at least one Salesforce MCP tool call, got: {tool_calls}"
    assert policy_calls, f"Expected at least one Policy MCP tool call, got: {tool_calls}"
    assert set(tool_calls) <= (_SALESFORCE_TOOL_NAMES | _POLICY_TOOL_NAMES), (
        f"Agent called a tool outside the approved allowlist: {tool_calls}"
    )

    final_text = "".join(
        part.text or ""
        for event in events
        if event.is_final_response() and event.content and event.content.parts
        for part in event.content.parts
    )
    assert final_text.strip(), "Expected a synthesized final answer"

    # AT-07-06: the answer must actually contain concrete, real values from
    # BOTH tool results, not just language that sounds like it combined
    # them. Generic keyword checks ("opportunity", "score") would pass even
    # if the model paraphrased or invented detail instead of citing the
    # actual retrieved facts -- this instead captures the real identifiers
    # Salesforce returned and the real scores Policy MCP computed *in this
    # run*, then requires the answer to quote at least one of each.
    real_opportunity_identifiers = _real_opportunity_identifiers_from_salesforce_responses(events)
    real_score_patterns = _real_score_strings_from_policy_responses(events)
    assert real_opportunity_identifiers, "No soqlQuery response in this run contained a Name/Id to check against"
    assert real_score_patterns, "No score_opportunity response in this run contained a score to check against"

    assert any(identifier in final_text for identifier in real_opportunity_identifiers), (
        f"Final answer cites none of the actual opportunity identifiers Salesforce returned "
        f"({real_opportunity_identifiers}): {final_text!r}"
    )
    assert any(re.search(pattern, final_text) for pattern in real_score_patterns), (
        f"Final answer cites none of the actual scores Policy MCP computed ({real_score_patterns}): {final_text!r}"
    )
