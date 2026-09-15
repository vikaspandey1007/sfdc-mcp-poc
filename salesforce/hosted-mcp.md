# Hosted MCP Server Activation

**Status as of this writing: not yet activated.** This document is the exact procedure to follow, and the
exact verification to run afterward. Activation happens through Setup UI only — no CLI/API path was found in
Gate 0 research, and Gate 1's own investigation confirmed the Tooling API objects for *custom* MCP servers
(`McpServerDefinition`) exist but return nothing relevant to toggling the *standard* `sobject-reads` server, and
no `CatalogedApi` metadata type is registered in the local `sf` CLI (`RegistryError` on retrieve) even though
the org's own `describeMetadata` lists it — so this remains a manual, UI-only step for now.

## Steps (perform in the org, logged in as `test_vikas_epam_27@epam.com`)

1. Setup → Quick Find → type **"MCP Servers"** → open **MCP Servers** (listed under API Catalog).
   - If it doesn't appear, try Quick Find → **"Agentforce Vibes"** instead (the Developer Edition activation
     path per Salesforce's April 2026 announcement) and report back what you see — this would mean the
     feature hasn't propagated to this org the way Gate 0's Tooling API check implied.
2. Find **`sobject-reads`** ("SObject Reads") in the server list.
3. Toggle it **Active**. Do **not** activate `sobject-all` or any mutation/delete server — this lab is
   read-only by design (see `docs/gate-0-plan.md` D1/D6).
4. Allow up to ~2 minutes for activation to take effect (documented propagation delay).

## Verification (run after you've done the above — tell me and I'll run this)

There's no confirmed API to read the standard server's active/inactive state directly (see the status note
above), so verification is a combination of:
- Visual confirmation in Setup that the toggle shows **Active**.
- Attempting a live Postman call against the server in Gate 2, which will fail cleanly if the server isn't
  actually active — this is the hard, protocol-level proof, not just a UI checkbox reading.

If you find an API-visible signal of activation state while you're in there (e.g., anything on the MCP Servers
page that looks queryable), let me know and I'll fold it into this doc and re-check via Tooling API.
