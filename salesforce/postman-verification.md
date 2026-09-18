# Gate 2: Proving Salesforce Hosted MCP Independently of Gemini (Postman)

**Status: PASS.** All four legs proven with real, captured evidence (not paraphrased) — MCP handshake, tool
discovery, a real Salesforce read, and a rejected write attempt. This is the mandatory gate (brief §8) proving
the Salesforce MCP endpoint works with zero LLM involvement, and it's done before any ADK/Gemini code exists.

## Evidence

### 1. OAuth token + MCP session handshake

Postman's OAuth 2.0 config (section 2/3 below) issued a token; the first MCP call returned:

```
:status         202
mcp-session-id  <uuid, redacted -- value itself isn't evidence, its presence/format is>
```
— "All systems are go!" Session established, a distinct `mcp-session-id` (UUID-shaped, per-session) confirming
a real stateful MCP session over Streamable HTTP, not just a bare HTTP 200. Same redaction logic as the ECA
Consumer Key: the literal value adds no evidentiary weight and isn't needed to prove the claim, so it's not
published even though session IDs are lower-risk than the Consumer Key.

### 2. Tool discovery (`tools/list`)

`sobject-reads` exposes exactly **six tools**, and — this is the load-bearing detail for the security
argument — **every single one carries `"readOnlyHint": true, "destructiveHint": false` in its own MCP
annotations**:

| Tool | Purpose |
|---|---|
| `soqlQuery` | Primary read path — arbitrary SOQL `SELECT` |
| `find` | Cross-object SOSL text search |
| `getRelatedRecords` | Traverse relationships from a known record (e.g. Account → Contacts) |
| `listRecentSobjectRecords` | Recently viewed records by object type |
| `getUserInfo` | Current user identity/role/preferences |
| `getObjectSchema` | Object/field metadata for query construction |

No create/update/delete tool is present in the catalogue at all — this isn't an access-control decision made
per-call, it's an absence of capability at the server's tool-definition level, and the tools self-declare that
fact in their own annotations rather than it being an inference from what's missing.

### 3. Real read: `soqlQuery` against seeded data

Query for open opportunities over $250k returned `"totalSize": 11` — **exactly matching** the count found by
running the identical SOQL directly against the org during Gate 1 verification (8 seeded + 3 pre-existing
"United Oil"-family records; see `setup.md` "Pre-existing data"). Sample records returned, matching seeded
values exactly:

```json
{
  "totalSize": 11,
  "done": true,
  "records": [
    {
      "Id": "006ak00000INiEZAA1",
      "Name": "United Oil Plant Standby Generators",
      "Amount": 675000.0,
      "StageName": "Needs Analysis",
      "CloseDate": "2025-10-17",
      "Account": { "Name": "United Oil & Gas Corp." }
    },
    {
      "Id": "006ak00000aqGS9AAM",
      "Name": "Blackwood - Core Banking Migration",
      "Amount": 520000.0,
      "StageName": "Negotiation/Review",
      "CloseDate": "2026-10-05",
      "LastActivityDate": "2026-08-15",
      "Account": { "Name": "Blackwood Financial Services" }
    }
  ]
}
```
(truncated to two representative rows — full response has 11; `Blackwood - Core Banking Migration` is this
lab's seeded data, `United Oil Plant Standby Generators` is the pre-existing Dev Edition sample record,
exactly as predicted in Gate 1's "Pre-existing data" note.)

This is the evidence that CRUD/FLS/sharing enforcement and real org data actually flow through MCP correctly
— not just that the endpoint responds, but that it responds with the *right* data.

### 4. Rejected write: proves the security claim precisely

Attempted `tools/call` with `name: "updateRecord"` against a real Opportunity (setting `StageName` to
`"Closed Won"` — the exact unhappy-path scenario from brief §3):

```json
{
  "jsonrpc": "2.0", "id": 4, "method": "tools/call",
  "params": {
    "name": "updateRecord",
    "arguments": {
      "sobject-name": "Opportunity",
      "id": "006000000000000AAA",
      "fields": { "StageName": "Closed Won" }
    }
  }
}
```

Response:
```json
{
  "jsonrpc": "2.0", "id": 4,
  "error": {
    "code": -32602,
    "message": "Unknown tool: invalid_tool_name",
    "data": "Tool not found: updateRecord"
  }
}
```

**Why this is the strong version of the claim, not the weak one:** the request never reached a
permission-check at all — there's no `updateRecord` tool to even attempt calling (consistent with #2's
tool-list annotations). This proves *"a valid OAuth token does not grant the capability to perform arbitrary
Salesforce operations — the MCP server exposes a defined, read-only tool catalogue, full stop,"* rather than
the weaker *"a write tool exists but Salesforce blocked it at the data layer."* Both would be valid security
outcomes, but this is the one that actually happened, and it's a stronger design-time guarantee than a
runtime permission check would have been.

**Caveat carried forward (unchanged from Gate 1 review):** this proves the *MCP server's* capability surface
is read-only. It does not by itself prove the underlying Salesforce *user's* effective access is restricted —
that's still Gate 5's job (genuinely restricted test user), per the additive-Permission-Set caveat in
`permissions.md`.

## Configuration reference (to reproduce)

### 1. Create a new Postman request

Any request will do to host the OAuth config — Postman's OAuth 2.0 token flow lives in the **Authorization**
tab of a request, independent of the request's own method/URL (you'll point the request itself at the MCP
endpoint in step 3, but the token flow itself is configured first).

### 2. Authorization tab → OAuth 2.0

These values come directly from this repo's verified Gate 1 state (`salesforce/external-client-app.md`,
`.env`), not generic documentation:

| Field | Value |
|---|---|
| Grant Type | **Authorization Code (With PKCE)** |
| Callback URL | `https://oauth.pstmn.io/v1/callback` (already registered on the ECA — confirmed in Gate 1) |
| Auth URL | `<SF_MY_DOMAIN_URL>/services/oauth2/authorize` |
| Access Token URL | `<SF_MY_DOMAIN_URL>/services/oauth2/token` |
| Client ID | your local `.env`'s `SF_ECA_CONSUMER_KEY` value (copy it from there, not from this file) |
| Client Secret | leave **blank** — confirmed `isConsumerSecretOptional = true`, no secret required for this public/PKCE client |
| Scope | `mcp_api refresh_token` |
| Client Authentication | **Send client credentials in body** (there's no secret to send as a Basic Auth header) |
| Code Challenge Method | **SHA-256** (Postman generates the verifier/challenge automatically for this grant type) |

`<SF_MY_DOMAIN_URL>` is your `.env`'s `SF_MY_DOMAIN_URL` (real value redacted for public release here —
see `docs/public-release-readiness.md`).

### 3. Get New Access Token

Click **Get New Access Token** — opens a browser/popup to log in as the demo org's user and consent.
**Never paste the actual token value into chat or a doc** — only the token response's field names/shape
are useful for documentation.

Confirmed working: `isCodeCredFlowEnabled = false` (flagged as unresolved in `external-client-app.md`) does
**not** block the Authorization Code + PKCE flow — the token issuance succeeded, settling that open question
by behavior rather than by guessing at the field's meaning, exactly as planned.

### 4. Configure the request itself: tool discovery

Once a token is issued, set the request:
- Method: `POST`
- URL: your `.env`'s `SF_MCP_SERVER_URL` (`https://api.salesforce.com/platform/mcp/v1/platform/sobject-reads`)
- Headers: `Content-Type: application/json`
- Auth: inherit from the OAuth 2.0 config above (Postman does this automatically if you used the same
  request's Authorization tab)
- Body (raw JSON) — MCP's JSON-RPC `tools/list` call:
```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "method": "tools/list"
}
```

Send it. Actual response: the six read-only tools listed in "Evidence" #2 above.

### 5. A real read

Call `soqlQuery` with a query for open opportunities over $250k. Actual result: "Evidence" #3 above.

### 6. Unhappy path — attempted write

Call `tools/call` with `name: "updateRecord"` (or any mutation-shaped tool name). Actual result: "Evidence" #4
above — rejected as an unknown tool, not attempted-then-blocked.

**FLS-level access-denied scenario (deferred to Gate 5, not attempted here):** attempting to read a field
excluded from `Revenue_Agent_Read_Access`'s FLS grants would test a *different* enforcement layer (field
visibility within an allowed read, not tool-catalogue absence) and is more meaningful once Gate 5's genuinely
restricted test user exists — testing it against the current admin-ish user risks a false negative (the field
might be visible for reasons unrelated to this Permission Set, per the additive-permissions caveat).
