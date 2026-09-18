# ADR-004: Policy MCP — local stdio transport, plain-Python config, no database

**Status:** Accepted
**Date:** 2026-09-18 (Gate 7)

## Context

Gate 7 adds a second MCP server — a custom "Policy MCP" implementing deterministic
revenue-prioritisation scoring — to prove the agent orchestrates across a vendor-hosted MCP server
(Salesforce) and an application-owned one through the same protocol, not that it is coupled to
Salesforce's specific implementation. The gate's own brief is explicit about what this must *not*
become: no PostgreSQL or other database, no Redis/Render Key Value for policy storage, no new cloud
dependency, no generic database/SQL/filesystem MCP, no rules-engine product. Persistence is explicitly
out of scope for this gate.

Three separate decisions were needed: how the server is transported, how its rules are stored, and how
many/which tools it exposes.

## Decision

**Transport: stdio**, via `StdioConnectionParams`/`StdioServerParameters` (google-adk's own MCP
support, already used for the Salesforce toolset's `StreamableHTTPConnectionParams` sibling). The
server runs as a subprocess (`python -m policy_mcp.server`) spawned by
`agent/mcp_config.py:build_policy_mcp_toolset()`, one per agent process, communicating over stdin/stdout.

**Configuration: plain Python** (`policy_mcp/policy.py`'s module-level constants and a pure
`score_opportunity()` function), not a YAML/JSON rules file, not a database table, not a rules-engine
product.

**Tools: exactly two** — `score_opportunity` (score one opportunity's already-retrieved facts) and
`get_scoring_policy` (return the rule catalogue itself, for explainability). Both are narrow, named
business capabilities; neither is a generic "run this code"/"query this"/"call this URL" capability.

## Options considered — transport

| Option | Fit for this gate | Why |
|---|---|---|
| **stdio** — chosen | Best fit | No network port to open or secure, no URL to manage, no auth to design — the server only ever needs to be reachable by the one agent process that spawns it. Matches the brief's own suggestion ("stdio or local Streamable HTTP... no OAuth needed, it's a local trusted server"). |
| Streamable HTTP (local) | Rejected for now | Works, and is what Salesforce's own server uses, but requires picking a port, binding an address, and answering "what else on this machine can reach it" — real questions with no real payoff at this gate's scope, since nothing here needs a second client or a network hop. Revisit if Policy MCP is ever hosted independently (see "Future evolution" below). |
| SSE | Rejected | The MCP spec itself deprecates SSE in favour of Streamable HTTP for anything that does need an HTTP transport; no reason to pick a deprecated transport for a new server. |

## Options considered — configuration storage

| Option | Fit for this gate | Why |
|---|---|---|
| **Plain Python module** — chosen | Best fit | Typed, imported directly, checked by the same test suite as the rest of the app, zero parsing failure modes, zero new dependency. The brief itself allows "JSON/YAML/Python configuration where appropriate" — Python is the appropriate choice when there's no operator persona editing this file by hand without touching code, which is true here: the rules are part of the application's behaviour, reviewed and tested the same way as any other logic change. |
| YAML/JSON rules file | Rejected for now | Would add a parsing step and a new failure mode (malformed file) for no real benefit at this scale (five rules, five constants) — worth revisiting only if a non-engineer needs to edit policy weights without a code review, which isn't a stated requirement here. |
| Database table | Explicitly disqualified | The gate's own constraints rule this out directly — no PostgreSQL, no Redis/Key Value "for policy storage." Even setting that aside, five fixed constants don't need a schema, migrations, or a persistence layer of any kind. |
| Rules-engine product (e.g. a Drools-style engine) | Explicitly disqualified | Explicitly listed as out of scope. Also disproportionate: this gate's entire rule set is five `if` conditions, not a rules graph needing a dedicated engine. |

## Options considered — tool granularity

| Option | Fit for this gate | Why |
|---|---|---|
| **Two narrow tools** (`score_opportunity`, `get_scoring_policy`) — chosen | Best fit | Each is a specific business capability with a fixed, typed signature. Together they let the agent both compute a score and explain *why* (by citing the actual rule catalogue), satisfying the brief's exit criterion without inventing functionality beyond it. |
| One tool only (`score_opportunity`) | Rejected | Would leave the agent's explanation of a score referencing rules it never actually retrieved — closer to the model paraphrasing a policy from its own training data than citing this project's actual, current rule set. `get_scoring_policy` exists specifically so the agent has something real to cite. |
| A generic `run_policy_query(code: str)` / SQL-like capability | Explicitly disqualified | Exactly the "arbitrary code execution... generic HTTP capabilities" this gate's security section rules out. Narrow, named tools are themselves a security property (Layer 2 of the defence-in-depth model — see `docs/security-model.md`'s Gate 7 section), not just a design preference. |

## Consequences

- No new runtime dependency: `mcp`'s `FastMCP` server helper is already installed transitively via
  `google-adk[mcp]` (confirmed via `pip show`/import, not assumed).
- `policy_mcp/` has zero imports from `agent/` or `auth/`, and zero references to any Salesforce or
  Gemini credential env var names — verified by a dedicated static test
  (`tests/test_policy.py::test_policy_mcp_source_has_no_salesforce_or_gemini_credential_material`,
  AT-07-08), not just an absence of a reason to add them.
- `agent/prompts.py` gained an appended addendum (`POLICY_MCP_ADDENDUM`) telling the model these tools
  exist and that it — not either MCP server — must combine their output; the original brief-verbatim
  `SYSTEM_INSTRUCTION` constant is untouched (still pinned byte-for-byte to the build brief).
- **"Local MCP" is a deployment choice for this POC, not the architectural pattern being proven.** The
  pattern is: *vendor MCP + custom MCP + agent orchestration through a common MCP protocol.* Swapping
  this server's transport from stdio to a hosted Streamable HTTP endpoint later would change exactly one
  function (`build_policy_mcp_toolset()`) and nothing about how the agent uses it — see
  `docs/architecture.md`'s Gate 7 section for the fuller architectural statement, and "Future evolution"
  below.

## Future evolution (not built now, kept possible)

- If Policy MCP ever needs to be shared across multiple agent processes, or needs its rules editable
  without a deploy, it would move to a hosted Streamable HTTP transport with its rules in a small config
  store — at that point this ADR's transport/storage choices should be revisited, not silently assumed
  to still hold.
- Demandbase/Gong-style third-party MCP servers (explicitly out of scope for this gate, per the brief's
  own "future-state architecture to preserve") would plug into the same agent orchestration pattern this
  gate proves, each as its own independent trust domain requiring its own delta security assessment —
  approving this gate does not pre-approve any future server.
