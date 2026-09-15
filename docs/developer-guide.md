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

⬜ **Pending in this repo's org** — full detail in [`salesforce/hosted-mcp.md`](../salesforce/hosted-mcp.md).
Verification of this step is indirect (visual Setup confirmation + a working Gate 2 Postman call), since no
confirmed API exposes the standard server's active/inactive state.

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
```

⬜ **Pending in this repo's org** — full detail in
[`salesforce/external-client-app.md`](../salesforce/external-client-app.md).

---

## Gate 2 — Prove MCP independently of Gemini (Postman)

_Not started yet. This section will be filled in with the exact Postman configuration and captured evidence
once Gate 1 is complete and merged._

## Gate 3 — Google ADK + Gemini

_Not started yet. Will document whichever of 3A (native OAuth) or 3B (token broker fallback) actually ends up
working, per `docs/gate-0-plan.md` section F — not both, whichever is real._

## Gate 4 — Thin UI

_Not started yet._

## Gate 5 — Security unhappy paths

_Not started yet._

## Gate 6 — Policy MCP server

_Not started yet._

---

## Keeping this guide current

Every gate's PR must update this file before merge: mark completed steps ✅ with a one-line pointer to the
evidence (a query result, a command's output, a file), fill in the next gate's section with what was *actually*
done (not the plan's prediction of what would be done), and flag any deviation from `docs/gate-0-plan.md`
inline rather than silently diverging from it. A PR that changes setup/config/steps without updating this file
is incomplete.
