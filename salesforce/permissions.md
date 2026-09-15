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
