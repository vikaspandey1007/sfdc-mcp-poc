# Gate 2: Proving Salesforce Hosted MCP Independently of Gemini (Postman)

**Status: not started.** This is the mandatory gate (brief §8) proving the Salesforce MCP endpoint works with
zero LLM involvement, before any ADK/Gemini code is written.

## 1. Create a new Postman request

Any request will do to host the OAuth config — Postman's OAuth 2.0 token flow lives in the **Authorization**
tab of a request, independent of the request's own method/URL (you'll point the request itself at the MCP
endpoint in step 3, but the token flow itself is configured first).

## 2. Authorization tab → OAuth 2.0

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

`<SF_MY_DOMAIN_URL>` is your `.env`'s `SF_MY_DOMAIN_URL`
(`https://epamsystemsinc9-dev-ed.develop.my.salesforce.com`).

## 3. Get New Access Token

Click **Get New Access Token**. This should open a browser/popup for you to log in as
`test_vikas_epam_27@epam.com` and consent. On success, Postman shows the issued access token (and refresh
token). **Don't paste the actual token value back to me in chat** — screenshots/text of the token response
structure (field names, expiry) are useful for documentation; the value itself isn't needed for verification
and shouldn't be pasted somewhere it might get logged or copied into a doc by mistake.

**If this fails**, capture the *exact* error (Postman shows it inline) — this is exactly the kind of evidence
Gate 0's decision log (D2) said to capture if the flow doesn't work cleanly, and it directly informs whether
`isCodeCredFlowEnabled = false` (flagged as unresolved in `external-client-app.md`) turns out to matter.

## 4. Configure the request itself: tool discovery

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

Send it. A successful response lists the tools `sobject-reads` exposes (expect something like a SOQL/query
tool for Account and Opportunity).

## 5. A real read

Using one of the discovered tools, issue a read against seeded data — e.g. query Opportunities over $250k
(the exact tool name/shape comes from step 4's response, so this step's request body can't be written until
that's known).

## 6. Access-denied scenario (optional but valuable)

If practical: attempt to read a field excluded from `Revenue_Agent_Read_Access`'s FLS grants (see
`permissions.md`) and confirm Salesforce denies it rather than the MCP layer silently filtering it — this is
the evidence for AT-04 later, captured early.

## What to send back

For each of steps 3-6: the actual (sanitized — no token values) request/response, or the exact error if it
failed. This becomes the evidence recorded in this file and in `docs/troubleshooting.md` if anything needed
debugging.
