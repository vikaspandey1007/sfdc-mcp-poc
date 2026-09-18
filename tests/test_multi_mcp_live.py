"""Gate 7's core acceptance evidence: a single live question that makes the
agent orchestrate across BOTH MCP servers -- the vendor-hosted Salesforce
one and the custom local Policy one -- through the MCP protocol alone,
with the LLM itself deciding to call both, not Python application code
faking the orchestration.

Covers:
  AT-07-05: a live multi-MCP question causes the agent to use both
            Salesforce MCP and Policy MCP.
  AT-07-06: the final response combines Salesforce facts with Policy MCP
            output.
  AT-07-07: no Salesforce mutation capability has been introduced (checked
            here at the live-catalogue level, same allowlist-not-blocklist
            method as test_integration_live.py and test_guardrails.py).

Opt-in, same as the other live suites (hits the real org and Gemini):
    pytest --run-integration tests/test_multi_mcp_live.py
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

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

    # AT-07-06: the answer must actually show its work from both sources --
    # real opportunity/account language (Salesforce evidence) alongside
    # scoring/policy language (Policy MCP output), not just one or the other.
    lowered = final_text.lower()
    crm_evidence_language = ("opportunity", "account", "amount", "stage")
    policy_evidence_language = ("score", "polic", "prioriti")
    assert any(word in lowered for word in crm_evidence_language), (
        f"Final answer doesn't appear to cite Salesforce/CRM evidence: {final_text!r}"
    )
    assert any(word in lowered for word in policy_evidence_language), (
        f"Final answer doesn't appear to cite policy scoring: {final_text!r}"
    )
