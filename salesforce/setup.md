# Salesforce Setup — Gate 1 Status

Org: Developer Edition, alias `devOrg1`, instance `epamsystemsinc9-dev-ed.develop.my.salesforce.com`,
username `test_vikas_epam_27@epam.com`. Confirmed via `SELECT Name, OrganizationType, IsSandbox FROM
Organization` (see `docs/gate-0-plan.md` Open Question 2 for the full record, including the "EPAM Systems Inc"
org-name caveat).

This file tracks **actual, verified state**, not intent. Each row links to the evidence.

| Component | Status | Evidence |
|---|---|---|
| Org confirmed Developer Edition, Hosted MCP framework present | ✅ Done | `docs/gate-0-plan.md` Open Question 3 — `McpServerDefinition`/`McpServerAccess`/etc. Tooling API objects exist |
| Flex Credit billing exposure | ✅ Checked, not eliminated | `docs/gate-0-plan.md` Open Question 3 — no MCP-related `TenantUsageEntitlement` rows found; not a Salesforce guarantee |
| `sobject-reads` MCP server activated | ⬜ Not yet — manual Setup step | `hosted-mcp.md` |
| Permission Set `Revenue_Agent_Read_Access` deployed + assigned | ✅ Done | `permissions.md` — deploy + assignment + independent SOQL verification |
| External Client App created (OAuth/PKCE/JWT/scopes/pre-auth) | ⬜ Not yet — manual Setup step | `external-client-app.md` |
| Sample Account/Opportunity/Task data seeded | ✅ Done | see "Sample data" below |
| Pre-existing org sample data (United Oil, GenePoint, etc.) | ⚠️ Left in place, by decision | see "Pre-existing data" below |

## Sample data

Source of truth: `sample-data/accounts.csv`, `sample-data/opportunities.csv`. Seeded via
`scripts/seed_data.py` (idempotent — re-running skips records that already exist by Name). Staleness is
derived automatically from real Salesforce behavior, not a fabricated field: `scripts/seed_data.py` creates a
`Task` against each Opportunity (`WhatId`), and Salesforce's own `Opportunity.LastActivityDate` rollup reflects
it — no custom field needed.

**Verified via independent query** (not just the script's own success output):

```
SELECT Name, Amount, StageName, CloseDate FROM Opportunity WHERE Amount > 250000 AND IsClosed = false
ORDER BY Amount DESC
```
returned 11 rows (8 from this lab's seed data spanning 265k-520k, plus 3 pre-existing "United Oil" records)
— confirming both the seed data and the query the demo will actually run both work end-to-end.

```
SELECT Name, LastActivityDate FROM Opportunity ORDER BY Name
```
confirmed the staleness design works exactly as intended: seeded "stale" opportunities show
`LastActivityDate = 2026-08-15` (Task backdated to simulate >14 days of inactivity), seeded "recent" ones show
`2026-09-13` — this is a real Salesforce rollup, not application logic, so it'll behave correctly however the
Hosted MCP server surfaces it.

To re-run (idempotent): `python scripts/seed_data.py --org devOrg1`

## Pre-existing data

This org already contained ~30 Opportunities and their Accounts from Salesforce's standard Developer Edition
sample dataset (United Oil, GenePoint, Edge Communications, Burlington Textiles, Grand Hotels, Express
Logistics, University of AZ, Dickenson Mobile Generators). **Decision: left in place, not deleted or filtered
out.** Rationale: it adds realistic "noise" a real CRM would have, and demonstrates the agent works over real,
unfiltered org data rather than a curated dataset — arguably a better architecture demo than a pristine empty
org. One pre-existing record (`United Oil Plant Standby Generators`, $675k) will legitimately outrank this
lab's seeded data in a raw "highest value open opportunity" sort; the demo script (Gate 4) should account for
this rather than be surprised by it.

## Manual steps still required (Setup UI, cannot be automated from here)

1. Activate the `sobject-reads` Hosted MCP server — see `hosted-mcp.md`.
2. Create the External Client App — see `external-client-app.md`.

Both require interactive Setup UI navigation with dependent picklists/checkboxes I can't drive without a
browser-control tool. Once done, tell me and I'll run the verification queries/metadata retrieval documented
in each file and update this table with real evidence before Gate 1 is considered complete.
