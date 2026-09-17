"""Env/config loading and validation for the Gate 3 agent.

Fails fast and specifically -- naming exactly which variable is missing --
rather than letting a downstream ADK/MCP stack trace stand in for a config
error. Core Gate 3 vars (Salesforce side) are always required; Gemini vars
are required only once an agent is actually constructed (get_settings() is
the single point where that happens), so importing this module or building
agent/mcp_config.py alone doesn't require GOOGLE_API_KEY to be set yet.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

_CORE_VARS = ("SF_MY_DOMAIN_URL", "SF_ECA_CONSUMER_KEY", "SF_MCP_SERVER_URL")
_GEMINI_VARS = ("GOOGLE_API_KEY", "GOOGLE_GENAI_MODEL")


@dataclass(frozen=True)
class Settings:
    sf_my_domain_url: str
    sf_eca_consumer_key: str
    sf_mcp_server_url: str
    google_api_key: str
    google_genai_model: str


def _require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing required environment variable: {name}. "
            f"Copy .env.example to .env and fill it in, or export it directly."
        )
    return value


def get_core_settings() -> tuple[str, str, str]:
    """Loads only the Salesforce-side vars -- no Gemini key required.

    Use this from agent/mcp_config.py so the MCP toolset can be built/tested
    before GOOGLE_API_KEY exists.
    """
    return tuple(_require(name) for name in _CORE_VARS)  # type: ignore[return-value]


def get_settings() -> Settings:
    """Loads full settings including Gemini vars -- call only when actually
    constructing the agent (agent/agent.py), not at import time elsewhere.
    """
    sf_my_domain_url, sf_eca_consumer_key, sf_mcp_server_url = get_core_settings()
    google_api_key, google_genai_model = (_require(name) for name in _GEMINI_VARS)
    return Settings(
        sf_my_domain_url=sf_my_domain_url,
        sf_eca_consumer_key=sf_eca_consumer_key,
        sf_mcp_server_url=sf_mcp_server_url,
        google_api_key=google_api_key,
        google_genai_model=google_genai_model,
    )
