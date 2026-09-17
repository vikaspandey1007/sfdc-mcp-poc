"""RevenuePrioritisationAgent -- Gate 3 exit-criterion agent.

Model is read from GOOGLE_GENAI_MODEL (config.get_settings()), pinned in
.env rather than chosen dynamically at runtime -- see docs/gate-0-plan.md
and the Gate 3 plan's reproducibility rationale. Building this module's
`root_agent` requires GOOGLE_API_KEY/GOOGLE_GENAI_MODEL to be set (it calls
get_settings(), not get_core_settings()) -- importing agent.mcp_config alone
does not.
"""

from __future__ import annotations

from google.adk.agents import Agent

from agent.config import get_settings
from agent.mcp_config import build_salesforce_mcp_toolset
from agent.prompts import SYSTEM_INSTRUCTION

_settings = get_settings()

root_agent = Agent(
    name="RevenuePrioritisationAgent",
    model=_settings.google_genai_model,
    instruction=SYSTEM_INSTRUCTION,
    tools=[build_salesforce_mcp_toolset()],
)
