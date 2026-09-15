# Hosted MCP Server Activation

**Status: `sobject-reads` is active, confirmed via API — not just a Setup UI screenshot.**

Gate 0 research found no confirmed CLI/API check for a standard server's active/inactive state. Gate 1
investigation found one anyway: the Tooling API object `McpServerAccess` (distinct from `McpServerDefinition`,
which is for custom servers) has `Active` and `DeveloperName`/`MasterLabel` fields, and directly reflects the
Setup UI toggle state for standard servers.

## Steps performed (Setup UI, no CLI/metadata path exists for this toggle)

1. Setup → Quick Find → **"MCP Servers"** (under API Catalog).
2. Found **`sobject-reads`** ("SObject Reads") and toggled it **Active**.
3. Waited for activation to take effect.

## Verification (real query output, not a description of intent)

```
SELECT Id, DeveloperName, MasterLabel, Active, McpServerId FROM McpServerAccess

ID                   DEVELOPERNAME             MASTERLABEL      ACTIVE  MCPSERVERID
1fzak000006XC29AAG   platform_sobject_reads    sobject-reads    true    null
```

`Active = true`, confirming the server is live. `DeveloperName = platform_sobject_reads` also matches the
endpoint path structure discovered independently in `.env`
(`https://api.salesforce.com/platform/mcp/v1/platform/sobject-reads` — note the `platform/` segment before the
server name, which isn't obvious from Salesforce's own docs and wasn't predicted in Gate 0 research; recording
it here since it's needed verbatim for Gate 2's Postman configuration and Gate 3's `SF_MCP_SERVER_URL`).

Only `sobject-reads` was activated — `sobject-all` and any mutation/delete server remain untouched, consistent
with the read-only design (D1/D6 in `docs/gate-0-plan.md`).

## What this does and doesn't prove

`Active = true` proves the org-side toggle is on. It does **not** prove the endpoint actually answers MCP
protocol calls (tool discovery, reads) correctly for an authenticated client — that's Gate 2's job (Postman),
by design, same as the ECA's OAuth settings.
