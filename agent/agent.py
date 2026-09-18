"""RevenuePrioritisationAgent -- Gate 3 exit-criterion agent, extended in
Gate 7 with a second MCP server.

Model is read from GOOGLE_GENAI_MODEL (config.get_settings()), pinned in
.env rather than chosen dynamically at runtime -- see docs/gate-0-plan.md
and the Gate 3 plan's reproducibility rationale. Building this module's
`root_agent` requires GOOGLE_API_KEY/GOOGLE_GENAI_MODEL to be set (it calls
get_settings(), not get_core_settings()) -- importing agent.mcp_config alone
does not.

Two tools means two independent MCP servers (agent/mcp_config.py) -- the
vendor-hosted Salesforce one and the custom local Policy one (Gate 7). The
agent itself decides which tool(s) a given question needs; nothing in this
module special-cases either server, which is the point being demonstrated
(docs/architecture.md's Gate 7 section, docs/security-model.md).
"""

from __future__ import annotations

from google.adk.agents import Agent

from agent.config import get_settings
from agent.mcp_config import build_policy_mcp_toolset, build_salesforce_mcp_toolset
from agent.prompts import AGENT_INSTRUCTION

_settings = get_settings()

root_agent = Agent(
    name="RevenuePrioritisationAgent",
    model=_settings.google_genai_model,
    instruction=AGENT_INSTRUCTION,
    tools=[build_salesforce_mcp_toolset(), build_policy_mcp_toolset()],
)
