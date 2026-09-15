# External Client App (ECA)

**Status as of this writing: not yet created.** ECA creation is a guided Setup wizard with dependent
picklists and security-sensitive checkboxes (PKCE, JWT access tokens, pre-authorization policy) — Gate 0
research found `ExternalClientApplication` and its child settings (`ExtlClntAppOauthSettings`,
`ExtlClntAppOauthConfigurablePolicies`, `ExtlClntAppOauthSecuritySettings`, etc.) **are** valid, retrievable
metadata types in this org (confirmed: `sf project retrieve start -m ExternalClientApplication` succeeds with
"Nothing retrieved" rather than a `RegistryError`). Deliberately **not** hand-authoring this XML blind, though
— getting OAuth/PKCE/JWT security settings wrong from an unverified guess is a worse failure mode than one
extra manual step. Instead: you create it through Setup (validated, guided UI), and I retrieve the resulting
metadata afterward via the same command — so the real configuration becomes the source-controlled artifact,
not a hand-written guess.

## Steps (perform in the org, logged in as `test_vikas_epam_27@epam.com`)

1. Setup → Quick Find → **"external client"** → **External Client App Manager** → **New External Client App**.
2. Basic Information:
   - Name: `Revenue Agent MCP Client` (or similar — record the exact name you use, I'll need it for retrieval)
   - Distribution State: leave as Local (this is a lab, not a distributed package)
3. API (OAuth) section — enable OAuth, then set:
   - **OAuth Scopes**: add exactly two — **"Access MCP servers" (`mcp_api`)** and **"Perform requests at any
     time" (`refresh_token`)**. Do not add the broad "Manage user data via APIs" (`api`) scope — that's exactly
     the over-broad access this lab is designed to avoid (brief §5/§6 least privilege).
   - **Callback URL**: leave a placeholder for now (e.g. `http://localhost:8765/callback`) — Gate 2 will add
     Postman's `https://oauth.pstmn.io/v1/callback`, and Gate 3 will add whatever ADK's native flow needs, once
     we know which (see Gate 3A/3B in `docs/gate-0-plan.md`). Multiple callback URLs can be registered on one
     ECA.
   - **PKCE**: enable "Require Proof Key for Code Exchange (PKCE)".
   - **Client secret**: leave the "web server flow requires secret" style option **off** — this lab's clients
     (Postman initially, then ADK, possibly a token broker) are all native/public clients, not a web server
     with guaranteed secure server-side secret storage (see `docs/gate-0-plan.md` section C step 5 for why this
     is environment-dependent, not an MCP-wide rule).
4. Security settings: enable **"Issue JSON Web Token (JWT)-based access tokens for named users"**; leave other
   token-shape options off.
5. Policies → App Policies → **Permitted Users**: set to **"Admin approved users are pre-authorized"**, and
   attach the **`Revenue_Agent_Read_Access`** Permission Set (already deployed — see `permissions.md`) as the
   required pre-authorization set.
6. Refresh Token Policy: set validity to **≤30 days**, enable **Refresh Token Rotation**.
7. Save. Allow up to **30 minutes** for the ECA to fully propagate before it's usable by a client (documented
   Salesforce behavior — don't be alarmed if Gate 2's Postman test fails immediately after saving).

## Verification (run after you've created it — tell me and I'll run this)

Once created, I'll run, and paste real output (not paraphrase) into this file:

```powershell
# Confirm it exists and see its consumer key (safe to view — not a secret by itself, but never commit it)
sf data query -q "SELECT Id, DeveloperName, MasterLabel FROM ExternalClientApplication" -o devOrg1

# Pull the real configuration into source control as the actual artifact of record
cd salesforce\metadata
sf project retrieve start -m ExternalClientApplication -o devOrg1
```

The retrieved XML under `salesforce/metadata/force-app/main/default/externalClientApps/` (plus its OAuth
settings sub-metadata) becomes the checked-in record of what was **actually** configured — this is the
evidence artifact for Gate 1 review, not a hand-written approximation of what the settings *should* be.

**What still won't be provable from a file diff alone:** the consumer secret (if any exists) and the live
OAuth authorize/token endpoints only get proven working in Gate 2 (Postman) — a metadata file can show the
scopes/PKCE/JWT checkboxes are set correctly, but "does this actually authenticate" is Gate 2's job by design
(brief §8 Gate 2 is the mandatory "prove MCP independently" gate).
