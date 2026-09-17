# Developer Guide

A from-scratch, reproducible walkthrough of this lab. If you hand this file to another developer with
access to a fresh Salesforce Developer Edition org, they should be able to follow it top to bottom and end
up in the same state this repo is in.

**This file is a living document.** It's updated as part of every gate's PR, right alongside the code/config
that PR introduces — never left to drift into "what the plan said" versus "what actually happened." If you're
reading this mid-project, the section for the current gate may show a mix of ✅ done and ⬜ pending steps;
that reflects real state, not an error. Deeper rationale for *why* each step exists lives in
[`docs/gate-0-plan.md`](gate-0-plan.md) (architecture/decisions) and the per-topic files under
[`salesforce/`](../salesforce/); this guide is the sequential "do this" version.

---

## Prerequisites

| Tool | Version used in this repo | Check |
|---|---|---|
| Salesforce CLI (`sf`) | 2.82.6 | `sf --version` |
| Python | 3.13 (3.11+ required) | `python --version` |
| Git | any recent | `git --version` |
| GitHub CLI (`gh`), authenticated | any recent | `gh auth status` |
| A Salesforce org | Developer Edition, confirmed Hosted MCP-capable (see Gate 1) | — |

**Windows-specific note:** several `sf` subcommands (`sf data query`, `sf api request rest`, and others that
shell out internally) fail under Git Bash/MSYS on this machine with `'C:\Program' is not recognized...` — a
path-quoting bug unrelated to this project. **Run `sf` CLI commands from PowerShell**, not Git Bash, on
Windows. Project Python scripts (`scripts/*.py`) resolve the `sf` executable via `shutil.which()` internally,
which sidesteps this regardless of which shell launches Python.

---

## Repository bootstrap

```powershell
git clone https://github.com/vikaspandey1007/sfdc-mcp-poc.git
cd sfdc-mcp-poc
```

Workflow: one feature branch per gate, PR back to `main`, reviewed and merged before the next gate starts. No
direct commits to `main`. See `docs/gate-0-plan.md` section J for the full gate sequence.

---

## Gate 0 — Research and plan

No setup steps — this gate produced [`docs/gate-0-plan.md`](gate-0-plan.md) (feasibility verdict,
architecture, decision log). Read it before touching Gate 1; several Gate 1 choices (e.g. why there's one
Permission Set instead of two, why `sobject-reads` and not `sobject-all`) are explained there.

---

## Gate 1 — Salesforce foundation

### 1. Authenticate the `sf` CLI to your org

```powershell
sf org login web --alias devOrg1 --set-default
```

Opens a browser for interactive login. **Caution if you have other Salesforce SSO sessions active in your
default browser** (e.g. a work IdP) — the login can silently authenticate whichever org your browser session
is already logged into rather than the one you intend. Verify afterward:

```powershell
sf org display --target-org devOrg1
sf data query -q "SELECT Name, OrganizationType, IsSandbox FROM Organization" -o devOrg1
```

Confirm `OrganizationType = Developer Edition` and that `Name`/username are the org you meant to use.

### 2. Confirm the org supports Hosted MCP (no confirmed CLI check exists — this is the closest thing to one)

```powershell
sf api request rest /services/data/v67.0/tooling/sobjects/ -o devOrg1 | Select-String "Mcp"
```

If this lists `McpServerDefinition`, `McpServerAccess`, `McpServerToolDefinition`, etc., the Hosted MCP
platform framework is present in the org (this doesn't confirm the *standard* `sobject-reads` server is
active yet — see step 6).

✅ **Done in this repo's org** — see `docs/gate-0-plan.md` Open Question 3 for the full record.

### 3. Deploy the least-privilege Permission Set

```powershell
cd salesforce\metadata
sf project deploy start -d force-app -o devOrg1
```

This deploys `Revenue_Agent_Read_Access` (read-only Account/Opportunity/Task, no create/edit/delete/view-all).
See [`salesforce/permissions.md`](../salesforce/permissions.md) for exactly what it grants and why some fields
(e.g. `Opportunity.CloseDate`) intentionally have no explicit `<fieldPermissions>` entry — required fields
can't take FLS overrides, and Salesforce's own deploy error is the proof (`You cannot deploy to a required
field: ...`), not a guess.

### 4. Assign the Permission Set to yourself (or whichever user will run the demo)

```powershell
sf org assign permset --name Revenue_Agent_Read_Access -o devOrg1
```

Verify independently, don't just trust the assign command's own success message:

```powershell
sf data query -q "SELECT Id, Assignee.Username, PermissionSet.Name FROM PermissionSetAssignment WHERE PermissionSet.Name = 'Revenue_Agent_Read_Access'" -o devOrg1
```

✅ **Done in this repo's org.**

### 5. Seed sample data

```powershell
cd <repo root>
python scripts\verify_environment.py --org devOrg1   # sanity check first
python scripts\seed_data.py --org devOrg1
```

Creates 8 Accounts / 12 Opportunities / 12 Tasks from
[`salesforce/sample-data/accounts.csv`](../salesforce/sample-data/accounts.csv) and
[`opportunities.csv`](../salesforce/sample-data/opportunities.csv). Idempotent — safe to re-run; it skips
records that already exist by Name. Staleness is a real `Opportunity.LastActivityDate` rollup off backdated
Task records, not a fabricated field.

**Note:** a fresh Developer Edition org typically ships with its own standard sample dataset (United Oil,
GenePoint, Edge Communications, etc.) — this repo's org already had one. We deliberately left it in place
(see [`salesforce/setup.md`](../salesforce/setup.md) "Pre-existing data") rather than deleting it; if your org
has the same, expect it to show up alongside this lab's seeded Opportunities in any un-filtered query.

Verify:

```powershell
sf data query -q "SELECT Name, Amount, StageName, CloseDate FROM Opportunity WHERE Amount > 250000 AND IsClosed = false ORDER BY Amount DESC" -o devOrg1
```

✅ **Done in this repo's org.**

### 6. Activate the `sobject-reads` Hosted MCP server — manual, Setup UI only

No CLI/metadata path was found for this specific toggle (see `salesforce/hosted-mcp.md` for what was actually
tried and why it doesn't work yet). In the org, logged in as the intended user:

1. Setup → Quick Find → **"MCP Servers"** (under API Catalog). If not present, try Quick Find →
   **"Agentforce Vibes"** instead (Developer Edition activation path).
2. Find **`sobject-reads`** ("SObject Reads") and toggle it **Active**.
3. Wait up to ~2 minutes for activation to take effect.

Do **not** activate `sobject-all` or any mutation/delete server — this lab is read-only by design.

Verify (this turned out to be checkable via API after all — a correction to Gate 0's assumption that no such
check existed):

```powershell
sf data query -q "SELECT DeveloperName, MasterLabel, Active FROM McpServerAccess" -o devOrg1 -t
```

✅ **Done in this repo's org** — `Active = true` for `sobject-reads`. Full detail in
[`salesforce/hosted-mcp.md`](../salesforce/hosted-mcp.md).

### 7. Create the External Client App (ECA) — manual, Setup UI only

Full field-by-field detail, including exact scope names and why client secret/PKCE/JWT are set the way they
are, is in [`salesforce/external-client-app.md`](../salesforce/external-client-app.md). Summary:

1. Setup → Quick Find → **"external client"** → External Client App Manager → New External Client App.
2. OAuth scopes: **"Access MCP servers" (`mcp_api`)** + **"Perform requests at any time" (`refresh_token`)**
   only — not the broad `api` scope.
3. Enable PKCE. Leave client secret off (native/public client, not a secure web server).
4. Enable JWT-based access tokens for named users.
5. Permitted Users → "Admin approved users are pre-authorized", attach `Revenue_Agent_Read_Access` as the
   pre-authorization Permission Set.
6. Refresh token validity ≤30 days, enable rotation.
7. Save, wait up to 30 minutes for propagation.

Once created, pull the real configuration into source control instead of trusting what was clicked:

```powershell
cd salesforce\metadata
sf project retrieve start -m ExternalClientApplication -o devOrg1
sf project retrieve start -m ExtlClntAppOauthSettings -m ExtlClntAppOauthConfigurablePolicies -m ExtlClntAppGlobalOauthSettings -o devOrg1
```

**Redact the Consumer Key before committing** — `ExtlClntAppGlobalOauthSettings` retrieves the real
`<consumerKey>` in plaintext. Replace its value with `REDACTED_SEE_ENV_SF_ECA_CONSUMER_KEY` and keep the real
value only in the local, gitignored `.env`. Full rationale in `external-client-app.md` "Redaction".

✅ **Done in this repo's org** — created, retrieved, verified, redacted. Both callback URLs
(`http://localhost:8765/callback` and `https://oauth.pstmn.io/v1/callback`) are registered, confirmed via
re-retrieve. Full detail in [`salesforce/external-client-app.md`](../salesforce/external-client-app.md).

**Gate 1 is complete.** Every exit criterion (server active, ECA config, metadata retrieved, no secrets,
environment re-verified) has independent verification — see
[`salesforce/setup.md`](../salesforce/setup.md) for the full status table.

---

## Gate 2 — Prove MCP independently of Gemini (Postman)

**Status: PASS.** Full configuration reference and captured evidence (real request/response JSON, not
paraphrased) in [`salesforce/postman-verification.md`](../salesforce/postman-verification.md). Summary:

- MCP session handshake succeeded (`202`, distinct `mcp-session-id`).
- `tools/list` returned exactly six tools, all self-annotated `readOnlyHint: true` — no mutation tool exists
  in the catalogue.
- `soqlQuery` returned real data matching Gate 1's independently-verified SOQL results exactly
  (`totalSize: 11`).
- An attempted `updateRecord` call was rejected as an **unknown tool** (JSON-RPC `-32602`), not as a
  permission-denied write — proving the stronger security claim: the capability doesn't exist for this
  client, it isn't merely blocked at call time.
- Resolved Gate 1's open question about `isCodeCredFlowEnabled = false`: it does not block the Authorization
  Code + PKCE flow, settled empirically rather than guessed.

## Gate 3 — Google ADK + Gemini

**Status: PASS.** Branch 3A (native ADK OAuth) was attempted first per plan and failed reproducibly; Branch
3B (a hand-built OAuth token broker) was built and proven end-to-end against the real org and real Gemini
API. Full decision record: [`docs/decisions/ADR-002-oauth-authentication-strategy.md`](decisions/ADR-002-oauth-authentication-strategy.md).
Full incident-level detail: [`docs/troubleshooting.md`](troubleshooting.md) (Gate 3 section).

- **3A result — FAIL, before any OAuth popup appeared.** `google-adk` 2.9.1's OAuth2 `AuthHandler`
  unconditionally requires a `client_secret`, but the Salesforce ECA is a deliberate public/PKCE-only client
  with no secret. No fake client secret was introduced to bypass the check. Root cause traced to the
  installed package's source, not assumed from docs.
- **3B built and proven working**: `auth/token_broker.py` performs a real Authorization Code + PKCE exchange
  against the ECA; `auth/token_store.py` persists tokens via OS keyring, falling back to a Fernet-encrypted
  file outside the repo tree when Windows Credential Manager's blob-size limit rejects a real Salesforce
  token pair (hit and fixed this session — see troubleshooting.md). `agent/mcp_config.py` wires
  `McpToolset(header_provider=...)` to source a dynamic `Authorization: Bearer` header from the broker.
- **New setup step found, not in Gate 0's original plan**: `adk web`'s default OAuth redirect URI
  (`http://localhost:8000/dev-ui`) had to be registered on the ECA before 3A could even be attempted — see
  `salesforce/external-client-app.md`'s Callback URL section (now three URLs, one per gate/branch).
- **All five Gate 3 verification criteria demonstrated, reproduced across two fresh `adk web` sessions plus
  an automated integration test** (`pytest --run-integration tests/test_integration_live.py`, which passed
  against the live org and live Gemini API):
  1. Connectivity — `McpToolset` discovers `sobject-reads`' six tools.
  2. Identity — the token broker's real PKCE exchange succeeds; Windows Credential Manager fallback verified
     with real tokens.
  3. Intelligence — *"Show me open opportunities worth more than $250k"* correctly triggers
     `getObjectSchema` then `soqlQuery` with `IsClosed = false`, citing real Opportunity records.
  4. Security — *"Update this opportunity to Closed Won"* is refused with no mutation-shaped tool call ever
     attempted, in every session tested.
  5. Observability — both paths visible in the Trace tab; repo-wide grep confirms no token/secret value
     appears in any committed file.
- **Model pinned**: `GOOGLE_GENAI_MODEL` in `.env` (checked live against the Gemini `ListModels` API, not
  guessed from search results, which returned unreliable SEO content for model names this session).
  `gemini-3.8-flash` hit two reproducible 503s at the answer-synthesis step; switching to `gemini-3.6-flash`
  (same live-verified list, also non-preview/non-`-latest`) succeeded immediately and reproducibly. Not
  enough data points to blame the specific model version for the 503s, but the switch unblocked progress.
- **Known caveat, not a Gate 3 blocker**: Gemini's own prose summary of a tool result can contain arithmetic
  errors even when the underlying data/tool calls are correct (see troubleshooting.md, "Gemini synthesis
  arithmetic error") — consumers should verify a stated total against the accompanying table, not trust the
  narrative summary standalone.
- Test suite: `tests/test_mcp_connection.py`, `tests/test_agent.py`, `tests/test_token_broker.py` (16 unit
  tests, fully offline, pinned against the installed `google-adk` 2.9.1 API); `tests/test_integration_live.py`
  (2 tests, opt-in via `--run-integration`, hits the real org/Gemini).

## Gate 4 — Secure hosted runtime on Render

**Status: PASS.** Inserted after Gate 3 per a dedicated brief given directly for this gate (not the original
`docs/gate-0-plan.md` sequence — see that file's renumbering note in section F). Deploys the proven Gate 3
implementation to Render as a secure, repeatable hosted POC. Full decision record:
[`docs/decisions/ADR-003-hosted-credential-persistence.md`](decisions/ADR-003-hosted-credential-persistence.md).
Full incident-level detail: [`docs/troubleshooting.md`](troubleshooting.md) (Gate 4 section). Deployment
recipe: [`docs/deployment-guide.md`](deployment-guide.md).

- **`CredentialStore` abstraction** (`auth/credential_store.py`): `LocalCredentialStore` (OS keyring,
  refactored from Gate 3B's `token_store.py`, hardened to raise instead of silently falling back to a
  colocated key+ciphertext scheme) and `HostedCredentialStore` (Render Key Value), selected via a factory
  that refuses to silently default to the dev-only Local store when running on Render.
- **Hosted persistence**: Render Key Value, paid tier, Journal + Snapshot persistence — chosen over Render
  Disks (disqualified: filesystem-based), PostgreSQL (viable but heavier than one blob needs), and an
  external secrets manager (disproportionate infra for a POC). The encryption key lives in a Render
  environment variable, never colocated with the ciphertext it protects.
- **Hosted OAuth**: `auth/token_broker.py`'s redirect_uri is now a parameter, not a hardcoded local
  constant; `server/oauth.py` adds `/oauth/salesforce/authorize` + `/callback`, using the same Key Value
  instance (short TTL, single-use) to bridge the two-request PKCE handshake statelessly. Local callback
  flow unchanged. Fourth ECA callback URL registered (a real typo — `onerender.com` vs `onrender.com` — was
  caught by diffing the retrieved metadata against the live service URL before it could break the flow).
- **Production-shaped entry point** (`server/app.py`), not `adk web`: `GET /health` (unauthenticated,
  reveals nothing); `POST /ask` (authenticated via `X-Demo-Api-Key` — the smallest secure surface, agreed
  before building it) runs one question and returns the synthesized answer + tool-call trace; fails fast at
  startup on missing config; a live Gemini quota error initially fell through to a raw 500 (fixed with a
  catch-all handler, now a clean 503 for anything unanticipated); dev docs (`/docs`, `/redoc`) disabled.
- **All eight Gate 4 exit criteria demonstrated live against the real deployed service**
  (`https://sfdc-mcp-poc-agent.onrender.com`), not just offline tests:
  1. Running on Render over HTTPS — confirmed (`curl`'d directly).
  2. Hosted OAuth + PKCE works — real token exchange completed, logged server-side.
  3. Credentials survive restart — a manual restart was triggered, then a real `/ask` call succeeded
     afterward using the token obtained *before* the restart, with no re-authorization in between.
  4. Real Salesforce MCP read succeeds — real tool calls, real data, synthesized answer.
  5. Mutation attempt impossible — clean refusal, no mutation-shaped tool call ever attempted (confirmed
     from the live request logs, not just the response text).
  6. No credentials in Git/filesystem/logs — repo-wide grep clean; logs show metadata only.
  7. Deployment reproducible from documentation — the person who ran it followed
     `docs/deployment-guide.md` and `render.yaml` directly, no undocumented steps.
  8. Existing Gate 1–3 tests still pass — full offline suite green throughout.
- Test suite: `tests/test_credential_store.py`, `tests/test_local_credential_store.py`,
  `tests/test_hosted_credential_store.py`, `tests/test_server_app.py`, `tests/test_server_oauth.py` — all
  offline, fully mocked (fake keyring, fake Redis), no live dependency.
- **Not yet done**: a live test of AT-05 (deliberately revoking the Salesforce grant to prove the failure
  path) — verified at unit level (mocked `RuntimeError`/`ConnectionError`/`HTTPError` → clean 503) but not
  yet reproduced against a real revoked credential, since doing so would interrupt the now-working demo
  deployment. Flagged here rather than silently assumed equivalent to a live test.

## Gate 5 — Thin UI

_Renumbered from the original Gate 4 (see `docs/gate-0-plan.md`'s renumbering note). Not started yet._

## Gate 6 — Security unhappy paths

_Renumbered from the original Gate 5. Not started yet._

## Gate 7 — Policy MCP server

_Renumbered from the original Gate 6. Not started yet._

---

## Keeping this guide current

Every gate's PR must update this file before merge: mark completed steps ✅ with a one-line pointer to the
evidence (a query result, a command's output, a file), fill in the next gate's section with what was *actually*
done (not the plan's prediction of what would be done), and flag any deviation from `docs/gate-0-plan.md`
inline rather than silently diverging from it. A PR that changes setup/config/steps without updating this file
is incomplete.
