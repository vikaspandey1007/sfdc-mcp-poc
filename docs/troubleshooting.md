# Troubleshooting

Grown incrementally as issues are actually hit (Gates 1/2 needed nothing here — first entries are Gate 3).
Per the developer guide's own rule, this records what happened, not what the plan predicted would happen.

## Gate 3

### `pip install -e .` silently installed into the global Python, not a project venv

**What happened:** this repo had no `.venv/` despite `.gitignore` already listing one. Running
`pip install -e .` (adding `google-adk`) installed into the machine's global Python
(`C:\Program Files\Python313`), upgrading several packages already used by other, unrelated local projects
(`requests` 2.31.0→2.34.2, `pydantic` 2.11.3→2.13.5, `pydantic-core` 2.33.1→2.46.5, `fastapi`
0.115.12→0.141.1, `starlette` 0.46.2→1.6.0, `tenacity` 8.2.3→9.1.4, `typing-inspection` 0.4.0→0.4.4) and
introducing a real dependency conflict (`realtime 2.4.2` requires `websockets<15,>=11`; install pulled
`websockets` 15.0.1).

**Fix:** uninstalled the packages that were net-new (not upgrades) globally, reinstalled the exact prior
pinned versions for the ones that were upgraded (captured from pip's own uninstall log — evidence, not
guesswork), downgraded `websockets` back to `<15` to satisfy `realtime`'s constraint, confirmed clean with
`pip check` (`No broken requirements found.`). Then created `.venv/` and reinstalled the project there
(`.venv/Scripts/python.exe -m pip install -e ".[dev]"`) — all further Gate 3 work runs through that
interpreter, isolated from the global one.

**Lesson for future gates:** always confirm `.venv/Scripts/python.exe` (not the global `python`) is what's
being invoked before any `pip install` in this repo.

### `google-adk`'s MCP support is gated behind the `mcp` extra

**What happened:** `pip install google-adk` (no extras) succeeds, but
`import google.adk.tools.mcp_tool.mcp_toolset` fails with `ModuleNotFoundError: No module named 'mcp'`.
`google-adk`'s base `Requires-Dist` list doesn't include the `mcp` package at all — it's declared only
under `Provides-Extra: mcp` (`mcp>=1.24,<2 ; extra == "mcp"`), confirmed by reading the installed
`google_adk-2.9.1.dist-info/METADATA` directly rather than assuming from docs/examples.

**Fix:** `pyproject.toml` depends on `google-adk[mcp]>=2.8.0`, not bare `google-adk`.

### Installed API vs. researched API — `McpToolset` / OAuth2 signatures (google-adk 2.9.1)

Per the plan's rule to verify against the installed artifact, not the researched one, before writing
`agent/mcp_config.py`. Captured via `inspect.signature(...)` against the real installed package
(`.venv/Lib/site-packages/google/adk/...`), not from docs or GitHub `main`:

- `McpToolset.__init__` (keyword-only): `connection_params`, `tool_filter`, `tool_name_prefix`,
  `tool_list_cache_ttl_seconds`, `errlog`, `auth_scheme`, `auth_credential`, `require_confirmation`,
  `header_provider`, `progress_callback`, `use_mcp_resources`, `sampling_callback`,
  `sampling_capabilities`, `elicitation_callback`, `credential_key`. Matches what this plan assumed for
  `auth_scheme`/`auth_credential`/`header_provider` — no drift found.
- `StreamableHTTPConnectionParams` fields: `url` (required), `headers`, `timeout` (default 5.0),
  `sse_read_timeout` (default 300.0), `terminate_on_close` (default `True`), `httpx_client_factory`.
- `AuthCredential` fields: `auth_type`, `resource_ref`, `api_key`, `http`, `service_account`, `oauth2`.
- `OAuth2Auth` (the `.oauth2` field's type) includes `code_verifier` and `code_challenge_method` fields —
  **confirms PKCE is genuinely modeled in this installed version**, not just claimed by docs/blog posts.
  Also has `client_id`, `redirect_uri`, `access_token`, `refresh_token`, `auth_uri`, `auth_response_uri`,
  `auth_code`, `expires_at`/`expires_in`, `token_endpoint_auth_method` (default `client_secret_basic` —
  relevant since the Salesforce ECA is a public/PKCE client with no secret, needs checking this doesn't
  default to requiring one at the token endpoint).
- `AuthScheme` (from `google.adk.auth.auth_schemes`) — build via `OAuth2(flows=OAuthFlows(authorizationCode=...))`.
  `OAuthGrantType.AUTHORIZATION_CODE` is the relevant grant type; `OAuthFlows` also has `implicit`,
  `password`, `clientCredentials` (unused here — no service-account path exists for this ECA, matching
  Gate 0/1 findings).

No `#2168`-shaped failure (auth_scheme/auth_credential being ignored) is visible at the signature level —
consistent with that issue being closed in ADK's Aug 2026 FixIt week, ahead of the 2.9.1 installed here.
Whether it actually works end-to-end against Salesforce's real ECA is still Step 3's job to prove, not
something a signature read can settle on its own.

### Branch 3A result: FAIL — google-adk 2.9.1's native OAuth2 handler requires a client_secret unconditionally

**Outcome: 3A does not work for this ECA, confirmed reproducibly, not `#2168`/`#2615`/`#3331`-shaped —**
**a different, more fundamental limitation.** Recorded per Gate 0's rule to document the 3A attempt's
outcome regardless of which branch wins.

**Reproduction**: `adk web --port 8000 .` (telemetry prompt disabled first via `adk telemetry disable`,
otherwise it blocks non-interactive startup — see below); select the `agent` app; ask *"Show me open
opportunities worth more than £250k."* Result, first turn, no browser/consent popup ever appears:

```
errorCode: "ValueError"
errorMessage: "Auth Scheme SecuritySchemeType.oauth2 requires both client_id and client_secret in auth_credential.oauth2."
```

**Root cause, read directly from the installed package**
(`.venv/Lib/site-packages/google/adk/auth/auth_handler.py:296-304`):

```python
# Check for client_id and client_secret
if (
    not self.auth_config.raw_auth_credential.oauth2.client_id
    or not self.auth_config.raw_auth_credential.oauth2.client_secret
):
    raise ValueError(
        f"Auth Scheme {self.auth_config.auth_scheme.type_} requires both"
        " client_id and client_secret in auth_credential.oauth2."
    )
```

This check runs **before** `generate_auth_uri()` — i.e. before ADK even builds the authorization URL, let
alone opens a consent popup — which is exactly why no OAuth prompt was ever seen. It is unconditional: no
constructor flag, no alternate `AuthCredential`/`AuthScheme` shape, no PKCE-aware branch that accepts a
public client with no secret. `code_verifier`/`code_challenge_method` being real fields on `OAuth2Auth`
(see above) does not help — this check gates the flow before PKCE-specific logic is ever reached.

This directly conflicts with the ECA's real, deliberate configuration (`salesforce/external-client-app.md`,
Gate 1's D2 decision): `isConsumerSecretOptional=true`, `isSecretRequiredForRefreshToken=false`, no client
secret exists for this app at all — it's a genuine public/PKCE-only client, which is the correct choice for
a native/desktop-style OAuth client, not a workaround. `google-adk` 2.9.1's OAuth2 `AuthHandler` cannot
serve this class of client at all as currently written.

**Considered and deliberately not attempted**: passing a fabricated non-empty `client_secret` just to
satisfy this check. Discussed with the user and declined — it would contradict the ECA's actual security
design (no secret exists to send; PKCE's `code_verifier` is the intended proof of possession, not a shared
secret) and its success against Salesforce's token endpoint was genuinely uncertain, not a known-good path.

**Decision: this is 3A's documented, reproducible failure — trigger for Branch 3B** (`auth/token_broker.py`
+ `auth/token_store.py`, `header_provider`-based wiring). See `docs/decisions/ADR-002-oauth-authentication-strategy.md`
for the full decision record.

**Aside — `adk web` telemetry prompt blocks non-interactive/background startup.** First run of `adk web`
hangs at an interactive `Enable telemetry? [Y/n]` prompt with no CLI flag to skip it. Fix: `adk telemetry
disable` once (persists across runs), confirmed via `adk telemetry status`. Decided with the user: telemetry
off for this lab (handles org data, no reason to opt into sending ADK usage stats to Google beyond the
Gemini API calls themselves).

**Aside — `adk web`'s app picker shows the agent's folder name (`agent`), not `Agent.name`
(`RevenuePrioritisationAgent`).** Expected ADK behavior (apps are identified by directory name in the
agents_dir scan); the agent's own `name` field shows up inside traces/events instead. Not a bug, flagged
here only because it looked surprising at first glance.

### Circular import: `agent/__init__.py` re-exporting `root_agent` vs. `auth/token_broker.py` importing `agent.config`

While wiring Branch 3B, `from auth.token_broker import get_valid_access_token` (from `agent/mcp_config.py`)
failed with `ImportError: cannot import name 'get_valid_access_token' from partially initialized module
'auth.token_broker' (most likely due to a circular import)`.

**Cause**: `agent/__init__.py` did `from agent.agent import root_agent` (a re-export convenience, matching
ADK's alternate "`{name}/__init__.py` with root_agent in the package" discovery pattern). But Python always
runs a package's `__init__.py` before any of its submodules, so `auth/token_broker.py`'s
`from agent.config import get_core_settings` triggered `agent/__init__.py` -> `agent.agent` ->
`agent.mcp_config` -> `auth.token_broker` (already mid-import) -> ImportError.

**Fix**: emptied `agent/__init__.py` (docstring only, no re-export). ADK's loader already supports loading
`root_agent` directly from `agent/agent.py` without `__init__.py`'s help (confirmed by reading
`google.adk.cli.utils.agent_loader` source, pattern (a): `agents_dir/{name}/agent.py` with `root_agent`
defined) -- the re-export was redundant for discovery and was the actual cause of the cycle.

### Windows Credential Manager blob size limit — real Salesforce tokens don't fit

**First real end-to-end test of `python -m auth.token_broker`**: the Salesforce Authorization Code + PKCE
exchange itself **succeeded** (browser consent completed, code received, tokens exchanged) -- genuinely
proving the OAuth/PKCE mechanics work against the real ECA, independent of ADK. The failure was purely in
the persistence step:

```
win32ctypes.pywin32.pywintypes.error: (1783, 'CredWrite', 'The stub received bad data')
```

raised from `keyring`'s `WinVaultKeyring._set_password` -> `win32cred.CredWrite`. This is Windows Credential
Manager's documented size limit on `CRED_TYPE_GENERIC` credential blobs (historically ~2560 bytes) -- a
real Salesforce JWT `access_token` plus `refresh_token`, JSON-serialized together, exceeds it. Not
hypothetical or environment-specific: this is what happens with real tokens on this OS.

**Compounding issue**: `keyring`'s Windows backend does not wrap this in `keyring.errors.KeyringError` --
the raw `win32ctypes.pywin32.pywintypes.error` propagates uncaught. `auth/token_store.py`'s original
`except keyring.errors.KeyringError` therefore did not catch it, and the encrypted-file fallback (which the
Gate 0 plan always intended for exactly this situation) never ran.

**Fix**: broadened `save_tokens`/`load_tokens`/`clear_tokens` in `auth/token_store.py` to catch `Exception`
generally, not just `keyring.errors.KeyringError`. Re-verified: fallback file write/read now succeeds when
the keyring write fails this way.

### Security review findings (post-merge): fallback key colocation, and a blocklist-shaped negative test

Two findings from a review of the merged Gate 3 PR, both fixed the same day:

**1. `auth/token_store.py`'s fallback encryption key was stored beside its own ciphertext.**
`~/.sfdc-mcp-poc/token_key.bin` (the Fernet key) and `token_store.enc` (the encrypted token pair) lived in
the same directory. Encryption there only protected against casual inspection, not against an attacker who
could read that directory at all: the ciphertext and the key to decrypt it were both sitting right next to
each other, and the 0600 permission attempt on the key file is Windows-best-effort only, not a real
guarantee. **Fix**: the key now lives in the OS keyring (Windows Credential Manager), not on disk. It's a
small, fixed-size payload (~44 bytes, base64-encoded) — unlike the real Salesforce token pair, which is what
overflowed keyring's blob-size limit and forced the file-based fallback in the first place (see "Windows
Credential Manager blob size limit" above) — so it fits in keyring even in the exact situation that pushes
the tokens themselves onto the file. `_fallback_key()` migrates an existing file-based key into keyring on
first use rather than generating a fresh one, so an already-encrypted token file doesn't get silently
orphaned; verified against this machine's actual live token store (backed up first), which decrypted
correctly post-migration with the same expiry timestamp, and the key file was removed from disk afterward.
File-based key storage is kept only as a last resort if keyring itself is unavailable outright — a different
failure mode than the size-limit rejection. Regression tests: `tests/test_token_store.py` (fully offline, a
fake in-memory keyring, never touches the real OS keyring entry or `~/.sfdc-mcp-poc/`).

**2. The negative security test blocked mutation-*shaped names*, not unapproved capabilities.** The original
`test_update_request_is_refused_with_no_mutation_tool_call` scanned tool-call names for substrings like
"update"/"create"/"delete" — a blocklist. A future tool named something unrelated-sounding (e.g.
`executeAction`) that still mutated Salesforce data would sail through that check while actually being
dangerous. **Fix**: rewrote `tests/test_integration_live.py` around an allowlist instead — every tool-call
name the agent produces (positive or negative question) is asserted to be a member of the same approved
read-only set already pinned in `tests/fixtures/sobject_reads_tools_list.json` (Gate 2's proven catalogue).
The positive test also captures the MCP server's *live-advertised* catalogue (via a `before_model_callback`
piggybacked on its one real Gemini call, to avoid spending extra free-tier quota on a check that's really
about the MCP server, not Gemini) and asserts it equals that same approved set exactly — so a server-side
addition of any new tool, however named, fails the suite immediately, whether or not the agent ever calls
it. This is "only allow explicitly approved capabilities," not "block things that look dangerous."

**Aside, found while building the live-catalogue check**: `google-adk` 2.9.1's `McpToolset._build_headers`
only invokes `header_provider` when given a real, non-None `ReadonlyContext` (`if self._header_provider and
readonly_context:`, read directly from the installed source) — a standalone `toolset.get_tools()` call
outside an actual agent invocation gets no `Authorization` header and 401s against the real MCP server.
Confirmed by direct reproduction, not assumed. This is why the live-catalogue check rides along on a real
`run_debug()` call instead of calling `get_tools()` on its own.

### Gemini API key silently on a paid tier, not free — same account, different AI Studio project

**What happened**: the first `GOOGLE_API_KEY` created for this lab, under an AI Studio project named
`sfdc-mcp-poc`, hit `RESOURCE_EXHAUSTED` / "prepayment credits are depleted" on the very first `adk web`
run against the real agent — surprising for what was assumed to be a free-tier lab key. Checking that
project's own Billing page in AI Studio showed **"Tier 1 · Postpay, Prepay required,"** not free. A second,
pre-existing project on the same Google account, "Default Gemini Project," was checked the same way and
confirmed genuine **"Free tier"** (screenshot evidence, not inferred from docs) — same account, different
project, different billing tier. Google's own rate-limits documentation was also checked directly to confirm
an unbilled free-tier key literally cannot be charged (exceeding quota returns HTTP `429`, never a bill),
which was the user's main concern before proceeding further with any Gemini key at all.

**Fix**: switched `GOOGLE_API_KEY` to the Default Gemini Project's key. Restarted `adk web` — required, not
optional: the prior process had the old key baked into memory from `load_dotenv()` at import time, so an
`.env` edit alone doesn't take effect against an already-running process.

**Lesson**: an AI Studio account can have multiple projects with different billing tiers; "I created a free
key" is not verifiable from the key string itself — check the specific project's own Billing/Tier page
before trusting a key is actually free, especially before iterative agent-development testing that could
otherwise rack up real cost against the wrong project.

### Gemini synthesis arithmetic error — correct data, wrong narrative total

**What happened**: during Step 3's reproducibility pass (Branch 3B, `gemini-3.6-flash`), the agent was asked
*"Show me open opportunities worth more than $250k"* in a fresh `adk web` session. The tool chain was
correct — `getObjectSchema("Opportunity")` then a `soqlQuery` with `IsClosed = false` in the `WHERE` clause,
returning exactly 11 rows (the same 15 total minus the 4 `Closed Won` rows a prior, broader query in the
same session pass had returned, which is the right set). The rendered table of 11 opportunities is itself
correct, cross-checked against the live org. But Gemini's own prose summary stated:

> Total Open Deals (> $250K): 11
> Combined Pipeline Value: $3,855,000

Summing the 11 `Amount` values actually shown in that same response ($675k, $520k, $480k, $410k, $340k,
$320k, $300k, $275k, $270k, $270k, $265k) gives **$4,125,000** — the stated total is off by exactly $270,000,
i.e. one of the two $270k rows appears to have been dropped from Gemini's mental arithmetic while writing
the summary, even though it's present in the table two lines above.

**Root cause**: this is not a tool/data/retrieval defect — `getObjectSchema`, the SOQL `WHERE` clause, and
every row in the table are all correct. It's Gemini doing its own free-text arithmetic over the tool result
when composing the final answer, which is a known LLM weakness independent of MCP/ADK/Salesforce. Nothing
in this repo's plumbing can force a probabilistic model to add correctly in prose.

**Mitigation**:

- Treat the **table/row-level data** in an agent response as the evidence; treat any **narrative aggregate
  the model states in prose** (a sum, a count phrased outside the table, a percentage) as unverified until
  cross-checked against the rows actually returned — consistent with this project's standing rule to trust
  tool/API evidence over LLM narration.
- Because this is genuinely non-deterministic model behavior (Step 5's test-tier split already treats LLM
  tool selection as non-deterministic for the same reason), no pytest assertion is added for summary
  arithmetic — it would be asserting on prompt/model behavior that legitimately varies run to run, not on
  this repo's own code.
- Flagged for `docs/developer-guide.md`'s Gate 3 section (Step 5) as a known caveat: **consumers of this
  agent's answers should verify any stated total/count against the accompanying table, not trust the prose
  summary standalone** — this is a limitation of the current system prompt design (see `agent/prompts.py`),
  not something Gate 3's acceptance criteria required fixing, since criterion 3 only requires the answer to
  *cite real data*, which it does.

## Gate 4

### ECA callback URL typo caught by diffing the retrieved metadata against the real live URL

**What happened:** the fourth callback URL (for the hosted OAuth flow, Step 3) was typed by hand into
Setup as `https://sfdc-mcp-poc-agent.onerender.com/oauth/salesforce/callback` — an extra "e" in
"onerender.com". Caught immediately by re-retrieving `ExtlClntAppGlobalOauthSettings` and comparing the
retrieved value against the real, independently-verified service URL (`curl`'d directly, not assumed) —
exactly the same "verify the actual retrieved/live state, don't trust what was typed" discipline this repo
has applied to every other piece of Salesforce config since Gate 1. Fixed in Setup, re-retrieved, confirmed
matching, before the hosted OAuth flow was ever attempted — a mismatch here would have failed the PKCE
exchange with a redirect_uri error instead.

### `/ask` returned a raw, unhelpful 500 for an unanticipated exception type (live Gemini quota hit)

**What happened:** the first real `/ask` request against the deployed service returned a plain-text
`500 Internal Server Error` with no JSON body (`x-render-origin-server: uvicorn` confirmed the request did
reach the app process — this wasn't a platform-level block). The actual traceback, found in Render's logs
for the exact request timestamp:

```
google.adk.models.google_llm._ResourceExhaustedError:
429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota... limit: 20,
model: gemini-3.6-flash ... quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier'}}
```

The same free-tier daily quota (20 requests/day, per-model) already documented for Gate 3's live testing —
exhausted again during Gate 4's own testing that day, not a new problem. Not a bug in the sense of "wrong
behavior," but `server/app.py`'s `/ask` handler at the time only caught a specific, anticipated set of
exception types (`RuntimeError`, `ConnectionError`, `TimeoutError`, `urllib.error.HTTPError`) for the
"Salesforce credentials unavailable" case — anything else, including this LLM-provider quota error, fell
through uncaught and surfaced as Starlette's generic default 500, which by design reveals nothing to the
client (no debug mode) but also gives no useful signal that a retry might help.

**Fix:** added a catch-all `except Exception` below the specific Salesforce-shaped one, logging the full
exception server-side (`logger.exception`, satisfying the Observability NFR) and returning a clean JSON
503 (`{"error": "The agent is temporarily unavailable. Please retry shortly."}`) for anything not
specifically anticipated. Regression test:
`tests/test_server_app.py::test_ask_returns_503_not_a_raw_500_for_unanticipated_errors`.

**Not fixed, deliberately**: the underlying quota exhaustion itself. This is the same expected, external,
daily-resetting constraint already documented for Gate 3 — chasing it with another reactive model switch
(as Gate 3 did once, for a different reason — reproducible 503s, not quota) would trade a temporary,
self-resolving blocker for reopening the "is this other model reliable" question, and would desynchronize
the model actually tested from the one pinned in `render.yaml`/`docs/gate-0-plan.md`. Wait for the daily
reset, or move to a paid billing tier, rather than switching models to dodge a quota window.
