"""Unit tests for agent/agent.py and agent/prompts.py.

agent.agent builds root_agent at import time -- it calls
agent.config.get_settings(), which requires GOOGLE_API_KEY and
GOOGLE_GENAI_MODEL (see agent/agent.py's own docstring). Tests that need a
freshly-constructed root_agent explicitly `importlib.reload` the module
under a controlled env, so results don't depend on whatever happens to
already be in the real .env at test time.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

from agent.prompts import SYSTEM_INSTRUCTION

_BUILD_BRIEF = Path(__file__).parent.parent / "CLAUDE_BUILD_BRIEF_SALESFORCE_GEMINI_MCP.md"
_TEST_MCP_SERVER_URL = "https://api.salesforce.com/platform/mcp/v1/platform/sobject-reads"


@pytest.fixture(autouse=True)
def _full_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SF_MY_DOMAIN_URL", "https://test.my.salesforce.com")
    monkeypatch.setenv("SF_ECA_CONSUMER_KEY", "test-consumer-key")
    monkeypatch.setenv("SF_MCP_SERVER_URL", _TEST_MCP_SERVER_URL)
    monkeypatch.setenv("GOOGLE_API_KEY", "test-google-api-key")
    monkeypatch.setenv("GOOGLE_GENAI_MODEL", "test-pinned-model-id")


def test_system_instruction_matches_build_brief_verbatim() -> None:
    """Extracts Gate 3's fenced behavioural-contract block directly from the
    build brief and compares it against agent/prompts.py, so this fails
    loudly the moment either one drifts from the other -- per prompts.py's
    own "do not paraphrase" rule."""
    brief_text = _BUILD_BRIEF.read_text(encoding="utf-8")
    match = re.search(r"Initial behavioural contract:\s*``` text\n(.*?)```", brief_text, re.DOTALL)
    assert match, "Could not locate Gate 3's behavioural contract block in the build brief"
    assert match.group(1) == SYSTEM_INSTRUCTION


def test_root_agent_uses_pinned_model_from_env() -> None:
    import agent.agent as agent_module
    from agent.config import get_settings

    importlib.reload(agent_module)
    assert agent_module.root_agent.model == get_settings().google_genai_model
    assert agent_module.root_agent.model == "test-pinned-model-id"


def test_root_agent_identity_and_instruction() -> None:
    import agent.agent as agent_module

    importlib.reload(agent_module)
    assert agent_module.root_agent.name == "RevenuePrioritisationAgent"
    assert agent_module.root_agent.instruction == SYSTEM_INSTRUCTION


def test_agent_module_requires_gemini_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    import agent.agent as agent_module

    with pytest.raises(RuntimeError, match="GOOGLE_API_KEY"):
        importlib.reload(agent_module)
