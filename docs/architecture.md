# Architecture

This file starts as a Gate 7 deliverable (the multi-MCP orchestration pattern this gate exists to
prove) rather than the full consolidated architecture pass `docs/gate-0-plan.md` section J defers to
"final documentation" — that broader pass (covering Gates 1–6 too) is still pending and should not be
assumed done because this file exists.

## The pattern Gate 7 proves

```
User
  |
  v
Revenue Agent (Google ADK + Gemini)
  |
  +---- Salesforce Hosted MCP  (vendor-provided, hosted, OAuth-protected)
  |        |
  |        +---- CRM facts (opportunities, accounts, ...)
  |
  +---- Custom Policy MCP      (application-owned, local, no auth)
           |
           +---- deterministic business policy/scoring
```

**The architectural pattern is: vendor MCP + custom MCP + agent orchestration through a common MCP
protocol.** The agent (`agent/agent.py`) holds two `McpToolset` instances (`agent/mcp_config.py`) and
talks to both exactly the same way — through MCP's `tools/list` and `tools/call`. Nothing in the agent
code special-cases which server is "the real one" and which is "ours." That equivalence, not merely
"a second server exists," is what Gate 7's acceptance evidence demonstrates (see this file's evidence
section and `docs/developer-guide.md`'s Gate 7 section for the live run).

**"Local MCP" (stdio transport, no database, no separate deployment) is an implementation/deployment
choice for this POC, not the architectural pattern itself.** The pattern holds regardless of transport:
whether Policy MCP is a local stdio subprocess (today) or a hosted Streamable HTTP service behind its
own auth (a plausible future step, see `docs/decisions/ADR-004-policy-mcp-design.md`'s "Future
evolution"), the agent still reaches it as one more MCP server alongside Salesforce's. Swapping the
transport changes one function
(`agent/mcp_config.py:build_policy_mcp_toolset()`); it does not change how the agent decides to use it.

This is also the shape the brief's own "future-state architecture to preserve" describes scaling to:

```
Revenue Intelligence Agent
   |
   +-- Demandbase MCP   -> intent / account intelligence
   +-- Salesforce MCP   -> CRM / opportunity context
   `-- Gong MCP         -> conversation intelligence
```

Each additional MCP server is its own independent security/data trust domain requiring its own delta
assessment (identity, tools, data, actions) — approving Gate 7's Policy MCP does not pre-approve any
future server, the same rule the brief states for Salesforce not pre-approving Demandbase/Gong.

## Policy MCP's responsibility (and what it deliberately does not own)

Policy MCP owns exactly one thing: deterministic scoring of already-known opportunity facts against a
fixed, committed rule set (`policy_mcp/policy.py`; rules themselves reproduced from
`CLAUDE_BUILD_BRIEF_SALESFORCE_GEMINI_MCP.md` section 8's example policy). It does not fetch Salesforce
data, does not hold Salesforce or Gemini credentials, and does not decide *when* to combine its output
with CRM facts — that orchestration is the agent's job, not either MCP server's (see
`docs/security-model.md`'s Gate 7 section for why this separation is itself part of the security model,
not just a tidiness preference). Full design rationale — why stdio, why plain Python config, why no
database, why exactly two tools — is in `docs/decisions/ADR-004-policy-mcp-design.md`.

## Tool catalogue

| Server | Tool | Purpose |
|---|---|---|
| Salesforce Hosted MCP (`sobject-reads`) | `soqlQuery`, `find`, `getRelatedRecords`, `listRecentSobjectRecords`, `getUserInfo`, `getObjectSchema` | Read-only CRM access (Gate 2 evidence: no create/update/delete tool exists in this catalogue at all) |
| Policy MCP (`policy_mcp/server.py`) | `score_opportunity` | Deterministic score + contributing factors + explanation for one opportunity's facts |
| Policy MCP | `get_scoring_policy` | Returns the fixed rule catalogue itself, for explainability |

## Multi-MCP sequence (the acceptance scenario)

Question: *"Using our revenue prioritisation policy, which of my high-value open opportunities should I
prioritise and why?"*

```
User question
   |
   v
Revenue Agent (Gemini decides tool calls, not application code)
   |
   +--> Salesforce MCP: soqlQuery -- retrieve open opportunities + facts
   |
   +--> Policy MCP: get_scoring_policy -- retrieve the actual rules
   |
   +--> Policy MCP: score_opportunity (per candidate) -- score each one
   |
   v
Agent synthesises answer: CRM evidence (Salesforce) + policy reasoning (Policy MCP),
distinguishing which is which (agent/prompts.py's POLICY_MCP_ADDENDUM)
```

The important property is not the exact call sequence above (Gemini's own tool-selection legitimately
varies run to run, same caveat as every other live test in this repo) — it's that **both** servers were
used and the final answer visibly draws on both, which is exactly what
`tests/test_multi_mcp_live.py` asserts against the real agent, not a scripted mock.

## Acceptance evidence

Live evidence (not just unit tests) is recorded in `docs/developer-guide.md`'s Gate 7 section once run —
see that section for the actual trace/transcript. Automated coverage: `tests/test_policy.py` (AT-07-01
through AT-07-03, AT-07-08 — offline plus one real-stdio-subprocess smoke test),
`tests/test_multi_mcp_live.py` (AT-07-05 through AT-07-07, live, opt-in via `--run-integration`),
`tests/test_integration_live.py`/`tests/test_guardrails.py` (AT-07-04 — existing Salesforce coverage,
re-verified unaffected by the second toolset).

## Known limitations

- Policy MCP's rules are fixed at deploy time (plain Python, committed with the app) — there is no
  runtime API to change scoring weights without a code change and redeploy. Deliberate for this gate's
  scope (see ADR-004); would need revisiting if a non-engineer ever needs to tune weights directly.
- The "strategic account" and "days since activity" facts are supplied by the *agent* as arguments to
  `score_opportunity` — Policy MCP trusts whatever it's given and does not independently verify these
  against Salesforce. This is correct separation of concerns (Policy MCP shouldn't duplicate Salesforce
  data — see ADR-004), but it does mean a scoring result is only as good as the facts the agent actually
  retrieved and passed in; nothing in Policy MCP itself catches the agent passing a *wrong* fact for a
  real field (only a *malformed* one — AT-07-03 covers shape/type validity, not truthfulness).
- Only one business capability is implemented (opportunity scoring). The brief's example policy is used
  verbatim; no additional policy capabilities were added beyond it, per the instruction not to
  manufacture functionality merely to create more tools.

## Future evolution

See `docs/decisions/ADR-004-policy-mcp-design.md`'s "Future evolution" section — hosting Policy MCP
independently, and the Demandbase/Gong future-state architecture the brief describes but this gate does
not implement.
