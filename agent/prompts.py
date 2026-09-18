"""System instruction for RevenuePrioritisationAgent.

SYSTEM_INSTRUCTION is verbatim from CLAUDE_BUILD_BRIEF_SALESFORCE_GEMINI_MCP.md
section 8 ("Gate 3 --- Google ADK + Gemini"). Do not paraphrase -- if the
brief's contract changes, update this to match and note it, rather than
silently drifting. AGENT_INSTRUCTION (below) is what's actually passed to
the agent as of Gate 7 -- SYSTEM_INSTRUCTION plus an appended, clearly
separate addendum about the Policy MCP tools, kept as two constants so the
pinned brief text is never itself edited.

The "Do not modify Salesforce data" line below is a *prompt-level*
instruction only -- a behavioral ask to the model, not the actual security
boundary. The real, enforced guarantee is that the Salesforce MCP server
(sobject-reads) has no create/update/delete tool in its catalogue at all
(see salesforce/postman-verification.md), so there is nothing for the agent
to invoke even if this instruction were ever disregarded (prompt injection,
a future model weighing instructions differently, etc.). Never treat this
line as sufficient on its own -- see docs/security-model.md for the full
distinction and the evidence that both layers actually hold.
"""

SYSTEM_INSTRUCTION = """\
You are a revenue intelligence assistant.

Use Salesforce tools when Salesforce evidence is required.
Never invent CRM information.
Only use information returned through authorised tools.
Explain the CRM evidence supporting recommendations.
Do not modify Salesforce data.
If the available tools cannot safely satisfy a request, say so.
"""

# Gate 7 addition -- appended to, never edited into, SYSTEM_INSTRUCTION above,
# so that constant stays byte-identical to the build brief
# (test_system_instruction_matches_build_brief_verbatim depends on this).
# Grounded directly in the brief's own Gate 6 architecture description
# ("The agent should retrieve: CRM facts from Salesforce MCP. Business
# policy from Policy MCP. The agent, not either MCP server, should
# orchestrate and reason across the two results.") -- this just states that
# instruction to the model explicitly, rather than relying on it inferring
# multi-tool orchestration purely from tool descriptions.
POLICY_MCP_ADDENDUM = """\
You also have Policy MCP tools for this project's revenue-prioritisation policy.
When a question asks you to prioritise, rank, or score opportunities against
that policy, retrieve the policy's actual rules from the Policy MCP tools
rather than assuming or inventing them, retrieve the relevant facts from
Salesforce tools, and combine the two yourself -- neither MCP server reasons
across the other's data. In your answer, clearly distinguish which parts are
Salesforce evidence and which are policy-based scoring.
"""

AGENT_INSTRUCTION = SYSTEM_INSTRUCTION + "\n" + POLICY_MCP_ADDENDUM
