# Permissions

## Permission Set: `Revenue_Agent_Read_Access`

Source: [`salesforce/metadata/force-app/main/default/permissionsets/Revenue_Agent_Read_Access.permissionset-meta.xml`](metadata/force-app/main/default/permissionsets/Revenue_Agent_Read_Access.permissionset-meta.xml)

Grants:
- **Read** on `Account`, `Opportunity`, `Task` — no Create/Edit/Delete on any object, no "View All"/"Modify All".
- Explicit field-level read on `Account.Rating`, `Account.Industry`, `Opportunity.Amount` (the non-required
  fields the agent needs). Required fields (`Opportunity.StageName`, `Opportunity.CloseDate`, `Name` on both
  objects) don't take explicit `<fieldPermissions>` entries — Salesforce doesn't allow FLS overrides on fields
  that are always required/visible once object-level Read is granted; the first deploy attempt failed with
  exactly this error (`You cannot deploy to a required field: Opportunity.CloseDate`), which is direct
  evidence this constraint is real, not assumed.

**Dual purpose (deliberate simplification from the Gate 0 plan):** this single Permission Set both shapes data
access (least privilege, read-only) *and* serves as the ECA's pre-authorization gate (see
`external-client-app.md`) — only users holding it can complete the OAuth grant for the Hosted MCP client. The
Gate 0 plan originally proposed a second, separate "MCP Client User" Permission Set purely for the
pre-authorization gate. With exactly one demo user in this lab, a second Permission Set would be pure
ceremony with no security benefit — same net permissions, one more moving part to keep in sync. Flagging this
explicitly per the brief's rule to update the plan rather than silently deviate from it.

**Enterprise note (reviewer feedback, recorded for any future hardening pass — not acted on in this PoC):**
in a production pattern, business-data access and client/application pre-authorization should normally be
separate Permission Sets, because their lifecycle and ownership differ — data-access grants are typically
owned by a data/security team and change with role, while an ECA's pre-authorization list is an
integration-owner concern and changes with which *applications* are trusted, independent of what any given
user can see in the UI. Collapsing them works here specifically because this lab has exactly one user and one
client; it would not scale cleanly to multiple users or multiple client applications sharing the same
Hosted MCP server, since revoking one application's access would require touching a Permission Set that also
controls data visibility, and vice versa. If this pattern is ever taken past a single-user lab, split it back
into two Permission Sets along that ownership boundary.

**Caveat (reviewer feedback, tracked for Gate 5 — not a Gate 1 blocker):** Permission Sets are **additive**,
not restrictive. Assigning `Revenue_Agent_Read_Access` does not make the OAuth user's *effective* Salesforce
access read-only if their Profile or any other assigned Permission Set already grants broader CRUD/FLS —
Salesforce unions all granted permissions, it never narrows them. In this Gate 1 design, the actual
least-privilege enforcement comes from a stronger, independent mechanism: only the `sobject-reads` MCP server
is active, and no mutation-capable server is active at all (see `hosted-mcp.md`), so there's no write path
through MCP regardless of the underlying user's broader Salesforce permissions. That's sufficient to prove
this lab's architecture, but it means this repo cannot yet claim "Salesforce authorization proves least
privilege end-to-end" — that requires a user whose effective access is genuinely restricted, not merely a
Permission Set that was never exercised against broader access. See `docs/gate-0-plan.md` Gate 5 for the plan
to create that user and re-prove the boundary properly.

### Evidence: actually deployed and assigned (not just written)

Deployed via `sf project deploy start -d force-app -o devOrg1` from `salesforce/metadata/`:

```
status                   : Succeeded
success                  : True
numberComponentsDeployed : 1
numberComponentErrors    : 0
```

Assigned to the demo user via `sf org assign permset --name Revenue_Agent_Read_Access -o devOrg1`:

```
successes : {@{name=test_vikas_epam_27@epam.com; value=Revenue_Agent_Read_Access}}
failures  : {}
```

Verified independently via SOQL (`PermissionSetAssignment`, not just the assign command's own success message):

```
SELECT Id, Assignee.Username, PermissionSet.Name, PermissionSet.Label
FROM PermissionSetAssignment
WHERE PermissionSet.Name = 'Revenue_Agent_Read_Access'

ID                  ASSIGNEE.USERNAME             PERMISSIONSET.NAME          PERMISSIONSET.LABEL
0Paak000014BkfpCAC  test_vikas_epam_27@epam.com   Revenue_Agent_Read_Access   Revenue Agent Read Access
```

## Re-deploying / re-assigning

```powershell
cd salesforce\metadata
sf project deploy start -d force-app -o devOrg1
sf org assign permset --name Revenue_Agent_Read_Access -o devOrg1
```

Idempotent: re-running the assign command against a user who already holds the Permission Set is a no-op
(Salesforce returns success without creating a duplicate assignment).
