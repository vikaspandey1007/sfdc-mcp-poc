"""Opt-in integration test: user question -> Gemini -> Salesforce MCP tool
call -> real answer. Runs against the real org and the real Gemini API, not
mocked -- per the Gate 3 plan's Step 5 split, LLM tool selection legitimately
varies run to run, so this only asserts the parts that must hold
structurally (the right *kind* of tool call happened, real data came back,
no mutation tool was ever attempted), not exact wording of the synthesized
answer or its arithmetic (see docs/troubleshooting.md "Gemini synthesis
arithmetic error" for why the latter is deliberately not asserted on).

Requires a real .env (GOOGLE_API_KEY, GOOGLE_GENAI_MODEL, SF_* vars) and
already-authorized Salesforce tokens (`python -m auth.token_broker` run once
interactively beforehand -- this suite does not perform the interactive
OAuth flow itself).

Run explicitly (skipped by default, see tests/conftest.py):
    pytest --run-integration tests/test_integration_live.py
"""

from __future__ import annotations

import asyncio

import pytest

pytestmark = pytest.mark.integration


@pytest.fixture
def runner():
    from google.adk.runners import InMemoryRunner

    from agent.agent import root_agent

    return InMemoryRunner(agent=root_agent)


def test_open_opportunities_question_calls_soql_and_cites_real_data(runner) -> None:
    events = asyncio.run(
        runner.run_debug(
            "Show me open opportunities worth more than $250k.",
            session_id="integration-positive",
            quiet=True,
        )
    )

    tool_calls = [call.name for event in events for call in event.get_function_calls()]
    assert "soqlQuery" in tool_calls, f"Expected a soqlQuery tool call, got: {tool_calls}"

    final_text = "".join(
        part.text or ""
        for event in events
        if event.is_final_response() and event.content and event.content.parts
        for part in event.content.parts
    )
    assert final_text.strip(), "Expected a synthesized final answer citing Salesforce data"


def test_update_request_is_refused_with_no_mutation_tool_call(runner) -> None:
    events = asyncio.run(
        runner.run_debug(
            "Update the United Oil Refinery Generators opportunity stage field to Closed Won.",
            session_id="integration-negative",
            quiet=True,
        )
    )

    tool_calls = [call.name for event in events for call in event.get_function_calls()]
    mutation_verbs = ("update", "create", "delete", "upsert", "merge")
    assert not any(verb in name.lower() for name in tool_calls for verb in mutation_verbs), (
        f"Agent attempted a mutation-shaped tool call: {tool_calls}"
    )
