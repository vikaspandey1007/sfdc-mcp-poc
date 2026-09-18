# Architecture evidence matrix

The source of truth for what this project has actually demonstrated. Every claim made in `README.md`,
`docs/technical-solution-design.md`, or `docs/presentation-outline.md` should trace back to a row here —
if a document ever claims something this matrix doesn't support, trust this matrix and fix the other
document, not the reverse.

Status legend: **PROVEN** (automated test and/or live evidence exists and passes), **PARTIAL** (some
evidence exists, but a stated gap remains), **DEFERRED** (deliberately not done, recorded as an open
item, not silently skipped), **FUTURE** (not implemented — architectural direction only).

| Claim | Implementation | Automated test | Live evidence | ADR/Documentation | Status |
|---|---|---|---|---|---|
| Salesforce MCP connectivity | `agent/mcp_config.py:build_salesforce_mcp_toolset()` | `tests/test_mcp_connection.py` | Gate 2 (Postman), Gate 3 (agent) | `salesforce/postman-verification.md` | **PROVEN** |
| OAuth 2.0 Authorization Code + PKCE | `auth/token_broker.py` | `tests/test_token_broker.py` | Interactive local + hosted authorization runs (Gates 3, 4) | ADR-002 | **PROVEN** |
| Read-only Salesforce capability (structural, not just policy) | No create/update/delete tool in `sobject-reads` catalogue | `tests/test_mcp_connection.py::test_sobject_reads_tool_catalogue_fixture_has_no_mutating_tools`, `tests/test_integration_live.py`, `tests/test_guardrails.py` | Gate 2 Postman `tools/call updateRecord` → "Unknown tool"; live mutation-refusal tests | `docs/security-model.md` | **PROVEN** |
| Least-privilege Salesforce Permission Set (additive) | `Revenue_Agent_Read_Access` | N/A (Salesforce-side, no unit test) | Deployed + independently verified via SOQL | `salesforce/permissions.md` | **PROVEN** (as additive access; see next row for the residual gap) |
| Salesforce identity/permissions genuinely restrictive end-to-end | A second, restricted test identity | None | None | `docs/security-model.md` Gate 6 section | **DEFERRED** |
| Credential persistence (local) | `auth/local_credential_store.py`, OS keyring | `tests/test_local_credential_store.py` | Gate 3B local runs | — | **PROVEN** |
| Credential persistence (hosted) | `auth/hosted_credential_store.py`, Render Key Value, Fernet | `tests/test_hosted_credential_store.py` | Gate 4 restart-survival test | ADR-003 | **PROVEN** |
| Hosted runtime on Render | `server/app.py`, `render.yaml` | `tests/test_server_app.py` | Live `GET /health`, live `/ask` against real Salesforce+Gemini | `docs/deployment-guide.md` | **PROVEN** |
| Live credential-revocation failure handling | 503 on `RuntimeError`/`ConnectionError`/`TimeoutError` | `tests/test_server_app.py` (mocked) | None — deliberately not run against the working demo's real credentials | `docs/security-model.md` Gate 6 section | **PARTIAL** (offline proven, live deferred) |
| Demo UI | `app/app.py`, Streamlit | `tests/test_app.py` | Local + hosted (`sfdc-mcp-poc-ui`) runs, both positive and negative questions | `docs/demo-script.md` | **PROVEN** |
| UI access-code gate + lockout | `hmac.compare_digest`, per-session lockout after 5 attempts | `tests/test_app.py` | — | — | **PROVEN** |
| Mutation refusal (single-record) | Agent + MCP catalogue | `tests/test_integration_live.py::test_update_request_only_uses_approved_tools_if_any` | Live, hosted UI and local | `docs/demo-script.md` | **PROVEN** |
| Mutation refusal (bulk phrasing) | Same mechanism | `tests/test_guardrails.py::test_bulk_mutation_prompt_is_refused_via_allowlist` | Live | `docs/security-model.md` Gate 6 | **PROVEN** |
| No invented data for a nonexistent record | Agent behaviour, checked against real tool output | `tests/test_guardrails.py::test_nonexistent_opportunity_is_not_invented` | Live | `docs/security-model.md` Gate 6 | **PROVEN** (one observed flake, retried clean — see `docs/troubleshooting.md`) |
| Custom Policy MCP server | `policy_mcp/server.py` | `tests/test_policy.py` (real stdio subprocess) | Live tool-call trace (Gate 7) | ADR-004 | **PROVEN** |
| Deterministic policy scoring | `policy_mcp/policy.py` | `tests/test_policy.py` (18 tests) | Live scores cited in real answers | ADR-004 | **PROVEN** |
| Invalid Policy MCP input fails safely | `InvalidOpportunityFactsError` → MCP `isError: true` | `tests/test_policy.py` | Manual real-stdio verification during Gate 7 | ADR-004 | **PROVEN** |
| Multi-MCP orchestration (both servers used) | `agent/agent.py` two-toolset wiring | `tests/test_multi_mcp_live.py` | Live, two independent runs | `docs/architecture.md` | **PROVEN** |
| Multi-MCP answer combines real values from both servers | Same | `tests/test_multi_mcp_live.py` (captures real Opportunity identifiers + real scores, asserts the answer quotes at least one of each) | Live | `docs/developer-guide.md` Gate 7 | **PROVEN** |
| No mutation capability introduced by Policy MCP | Two narrow, typed tools only | `tests/test_multi_mcp_live.py` (catalogue equality check) | Live | `docs/security-model.md` Gate 7 | **PROVEN** |
| Secret protection — no credential in logs | `server/log_redaction.py` | `tests/test_log_redaction.py` | — | `docs/security-model.md` | **PROVEN** |
| Secret protection — no credential in Git history/working tree | Redaction discipline throughout | Full-history `git log -p` scan | — | `docs/public-release-readiness.md` | **PROVEN** (secrets); real PII/org identifiers found and remediated in current tree, history question still open — see that document's Finding 1 |
| Policy MCP holds no Salesforce/Gemini credentials | No `agent.*`/`auth.*` imports, no secret env var names | `tests/test_policy.py::test_policy_mcp_source_has_no_salesforce_or_gemini_credential_material` | — | ADR-004 | **PROVEN** |
| Existing Salesforce-only capability unaffected by adding Policy MCP | Same agent, two toolsets | Full offline suite (101 passed, 5 skipped) unchanged in pass/fail shape after Gate 7 | Live | `docs/developer-guide.md` Gate 7 | **PROVEN** |
| MCP protocol vendor-neutrality / general portability | N/A | N/A | N/A | `docs/architecture.md` | **FUTURE** — this project proves it for exactly two servers, not portability in general |
| LLM provider portability (non-Gemini) | N/A | N/A | N/A | `README.md` "Known limitations" | **FUTURE** — not attempted |
| Demandbase Capability / Gong Capability | N/A | N/A | N/A | `README.md` "Future evolution" | **FUTURE** — not implemented; no MCP (or other) implementation for either has been built, evaluated, or approved |
