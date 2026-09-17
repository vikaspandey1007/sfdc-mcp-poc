# Gate 4 deployment guide — Render

Written so a second developer could recreate this deployment from the repository plus this document,
without anything held only on the original author's laptop (Gate 4 Step 5). Nothing here is evidence of a
completed deployment — this is the recipe; `docs/troubleshooting.md` and the Gate 4 PR carry the actual
run-through evidence once performed.

## What gets provisioned

Per `docs/decisions/ADR-003-hosted-credential-persistence.md` and Gate 4 Step 2's "minimum Render
components" instruction, exactly two Render services, declared in `render.yaml`:

1. **`sfdc-mcp-poc-agent`** (Web Service) — runs `server/app.py`, the production-shaped entry point. Not
   `adk web`: that bundles a development UI, which Gate 4 says not to expose publicly.
2. **`sfdc-mcp-poc-tokens`** (Key Value) — the only additional infrastructure. Holds the encrypted
   Salesforce token pair; must be a **paid** plan with `persistenceMode: journal-snapshot` (the free tier
   has no persistence at all — see ADR-003).

No database, no additional microservices, no Kubernetes — deliberately, per Gate 4's own principles.

## Environment configuration

| Variable | Where it comes from | Static or dynamic | Notes |
|---|---|---|---|
| `CREDENTIAL_STORE_BACKEND` | `render.yaml` literal (`hosted`) | Static | Fixed by design; the factory in `auth/credential_store.py` also refuses to silently default to the local dev store when `RENDER=true` |
| `GOOGLE_GENAI_MODEL` | `render.yaml` literal | Static | Pinned after checking Gemini's `ListModels` API live — do not re-choose dynamically (see `docs/gate-0-plan.md`'s reproducibility rationale) |
| `OAUTH_REDIRECT_URI` | `render.yaml` literal, derived from the service's own `onrender.com` hostname | Static (per deployment) | Must exactly match what's registered on the Salesforce ECA (manual step below) |
| `GOOGLE_API_KEY` | Render Dashboard, set manually after first apply (`sync: false`) | Static secret | Never committed |
| `SF_MY_DOMAIN_URL` | Render Dashboard, manual | Static, per-org | Never committed |
| `SF_ECA_CONSUMER_KEY` | Render Dashboard, manual | Static, per-org | Never committed |
| `SF_MCP_SERVER_URL` | Render Dashboard, manual | Static | Never committed |
| `DEMO_API_KEY` | Render Dashboard, manual, generated once | Static secret | Shared secret for `POST /ask` (`X-Demo-Api-Key` header). Generate: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `CREDENTIAL_ENCRYPTION_KEY` | Render Dashboard, manual, generated once | Static secret | Fernet key protecting the token ciphertext in Key Value — **never** store this anywhere near the Key Value instance itself (ADR-003, Gate 4 principle 5) |
| `REDIS_URL` | Auto-wired via `fromService` in `render.yaml` | N/A — not manual | The Key Value instance's internal connection string |

No value from this table is ever printed by this app — `GET /health` (`server/app.py`) deliberately returns
only `{"status": "ok"}` (Step 6 AT-09), and every module handling a secret logs field names/shapes at most,
never values (Gate 0's AT-06, carried through every gate).

## Provisioning order

1. **Apply the Blueprint** (`render.yaml`) via the Render Dashboard ("New" → "Blueprint", point it at this
   repo). This creates both services but the web service will fail its first deploy — that's expected, it
   fails fast on missing configuration (`server/app.py`'s startup validation), not silently.
2. **Set the manual secrets** (Dashboard → `sfdc-mcp-poc-agent` → Environment): `GOOGLE_API_KEY`,
   `SF_MY_DOMAIN_URL`, `SF_ECA_CONSUMER_KEY`, `SF_MCP_SERVER_URL`, `DEMO_API_KEY`, `CREDENTIAL_ENCRYPTION_KEY`
   (generation commands in `render.yaml`'s comments). Redeploy.
3. **Confirm the Key Value instance's plan and persistence mode** in the Dashboard — `render.yaml`'s `plan`
   value is a placeholder; make sure whatever's actually selected is a paid plan with Journal + Snapshot
   persistence, not the free/no-persistence default.
4. **Register the hosted callback URL on the Salesforce ECA** (Gate 4 Step 3, manual, mirrors how the
   previous two callback URLs were added in Gates 2/3 — see `salesforce/external-client-app.md`): Setup →
   External Client Apps → `Revenue_Agent_MCP_Client` → add `OAUTH_REDIRECT_URI`'s value (e.g.
   `https://sfdc-mcp-poc-agent.onrender.com/oauth/salesforce/callback`) as an additional callback URL,
   newline-separated alongside the existing three. Re-retrieve `ExtlClntAppGlobalOauthSettings`, redact the
   Consumer Key again, commit. **Do not remove the existing local/Postman callback URLs.**
5. **Authorize the hosted service once, interactively, as a human**: visit
   `https://sfdc-mcp-poc-agent.onrender.com/oauth/salesforce/authorize` in a browser, log in/consent as the
   demo Salesforce user. This is the hosted equivalent of running `python -m auth.token_broker` locally —
   same PKCE mechanics (`auth/token_broker.py`'s `build_authorization_request`/`exchange_code_for_tokens`),
   different transport (`server/oauth.py`'s routes, backed by the Key Value instance for the short-lived
   state/verifier handshake, not a local throwaway HTTP server).
6. **Verify**: `GET /health` returns `{"status": "ok"}`; `POST /ask` with the correct `X-Demo-Api-Key`
   header and a real question returns a synthesized answer citing real Salesforce data (Step 7).

## Re-authorizing later

Salesforce's refresh token is rotated automatically on each use (`salesforce/external-client-app.md`) and
`auth/token_broker.get_valid_access_token()` refreshes proactively — no manual action needed under normal
operation. If the refresh token is ever revoked or expires outright, `POST /ask` returns a `503` with a
message pointing back at `/oauth/salesforce/authorize` (Step 4's "graceful handling of expired/revoked
Salesforce credentials", AT-05) — re-run step 5 above.

## What this guide does not cover yet

Gate 4 Step 6 (automated security acceptance tests, AT-01–AT-10) and Step 7 (functional acceptance,
Trace-tab-equivalent evidence from the hosted environment) are separate, not-yet-performed passes — this
document is the provisioning recipe, not the evidence that a real deployment was run through it.
