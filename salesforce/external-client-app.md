# External Client App (ECA)

**Status: created and configured.** `ExternalClientApplication` and its child settings
(`ExtlClntAppOauthSettings`, `ExtlClntAppOauthConfigurablePolicies`, `ExtlClntAppGlobalOauthSettings`) were
confirmed as valid, retrievable metadata types in this org during Gate 1 investigation (before creation,
`sf project retrieve start -m ExternalClientApplication` succeeded with "Nothing retrieved" rather than a
`RegistryError` — proving the type is supported here, just empty). Deliberately **not** hand-authored blind:
you created it through Setup's guided wizard, and the metadata below was retrieved *from* the org afterward —
it is the actual configuration, not a written intention.

One child type, `ExtlClntAppOauthSecuritySettings`, is **not** in the local `sf` CLI's metadata registry
(`RegistryError: Missing metadata type definition`) even though it's presumably a real server-side type —
this is a gap in the CLI tooling, not the org. Its settings (if any beyond what's captured in the other three
files) aren't independently retrievable right now; nothing in Gate 2's Postman test depends on it.

## What was created

- Name: **Revenue Agent MCP Client** (`Revenue_Agent_MCP_Client`)
- Created: 2026-09-15T17:23:05Z

## Retrieved metadata (source of truth — see the files themselves for full detail)

```
salesforce/metadata/force-app/main/default/
├── externalClientApps/Revenue_Agent_MCP_Client.eca-meta.xml
├── extlClntAppOauthSettings/Revenue_Agent_MCP_Client_oauth.ecaOauth-meta.xml
├── extlClntAppOauthPolicies/Revenue_Agent_MCP_Client_oauthPlcy.ecaOauthPlcy-meta.xml
└── extlClntAppGlobalOauthSets/Revenue_Agent_MCP_Client_glbloauth.ecaGlblOauth-meta.xml
```

Confirmed settings, read directly from the retrieved files (not re-typed from memory of what was clicked):

| Setting | Value | Source field |
|---|---|---|
| OAuth scopes | `RefreshToken, MCP` (i.e. `refresh_token` + `mcp_api` — no broad `api` scope) | `ExtlClntAppOauthSettings.commaSeparatedOauthScopes` |
| PKCE required | `true` | `ExtlClntAppGlobalOauthSettings.isPkceRequired` |
| Named-user JWT access tokens | `true` | `ExtlClntAppGlobalOauthSettings.isNamedUserJwtEnabled` |
| Client Credentials (M2M/service-account) flow | `false` — confirms no service-account path exists, matching Gate 0 research | `ExtlClntAppGlobalOauthSettings.isClientCredentialsFlowEnabled` and the equivalent field in `ExtlClntAppOauthConfigurablePolicies` |
| Secret required for refresh token exchange | `false` | `ExtlClntAppGlobalOauthSettings.isSecretRequiredForRefreshToken` |
| Consumer secret optional | `true` (native/public client, per D2 client-secret guidance) | `ExtlClntAppGlobalOauthSettings.isConsumerSecretOptional` |
| Refresh token rotation | `true` | `ExtlClntAppGlobalOauthSettings.isRefreshTokenRotationEnabled` |
| Refresh token validity | `30` `Days`, policy type `SpecificInactivity` | `ExtlClntAppOauthConfigurablePolicies.refreshTokenValidityPeriod`/`Unit`/`refreshTokenPolicyType` |
| Permitted users | `AdminApprovedPreAuthorized` | `ExtlClntAppOauthConfigurablePolicies.permittedUsersPolicyType` |
| Pre-authorization Permission Set | `Revenue_Agent_Read_Access` | `ExtlClntAppOauthConfigurablePolicies.commaSeparatedPermissionSet` |
| Callback URL(s) | `http://localhost:8765/callback` and `https://oauth.pstmn.io/v1/callback` (both present, confirmed via re-retrieve) | `ExtlClntAppGlobalOauthSettings.callbackUrl` |

**One flag, not yet resolved by a metadata file read alone:** `isCodeCredFlowEnabled = false`. Believed to
refer to a separate certificate-based flow (not the Authorization Code + PKCE flow this lab uses — that's
evidenced instead by `isPkceRequired = true` being set at all), but this isn't asserted with full confidence
from the field name alone. Verify empirically in Gate 2: if Postman's Authorization Code + PKCE flow works
end-to-end, this flag's meaning is settled by behavior, not guessed from a name.

## Redaction (read before touching this metadata again)

`ExtlClntAppGlobalOauthSettings` includes `<consumerKey>` — the org's real Consumer Key (Client ID) was
retrieved in plaintext. For a PKCE public client this isn't a secret in the strict OAuth sense (there's no
client secret to protect; PKCE exists precisely so the client ID can be public), but publishing an org's live
Consumer Key into a shared repo by default is still unnecessary exposure — so **it's redacted in the committed
file** to `REDACTED_SEE_ENV_SF_ECA_CONSUMER_KEY`. The real value lives in the local, gitignored `.env` as
`SF_ECA_CONSUMER_KEY`.

**If you ever re-run `sf project retrieve start -m ExtlClntAppGlobalOauthSettings`, it will re-populate the
real key in your working copy — redact it again before committing.** Do not run a blanket
`sf project deploy start -d force-app` from this directory without checking the diff first: deploying the
redacted placeholder value back to the org could overwrite the real Consumer Key. Treat
`externalClientApps/` and `extlClntApp*/` as **retrieve-only reference/evidence**; only `permissionsets/` is
meant to be deployed routinely.

## Verification performed

```
SELECT Id, DeveloperName, MasterLabel, CreatedDate FROM ExternalClientApplication

ID                  DEVELOPERNAME              MASTERLABEL                CREATEDDATE
0xIak000000ZZXZEA4  Revenue_Agent_MCP_Client   Revenue Agent MCP Client   2026-09-15T17:23:05.000+0000
```

Plus the full metadata retrieval described above, plus a repo-wide grep confirming the real Consumer Key
value appears nowhere in any non-gitignored file (only the redacted placeholder and the gitignored `.env`).

**What's still Gate 2's job, not provable from a metadata file:** whether the live OAuth authorize/token
endpoints actually complete the Authorization Code + PKCE exchange end-to-end. A metadata file proves the
checkboxes are set correctly; it doesn't prove the flow works. That's exactly why Gate 2 (Postman) is
mandatory per the brief, not a formality.

## Callback URL — done

Both `http://localhost:8765/callback` and `https://oauth.pstmn.io/v1/callback` are registered, confirmed by
re-retrieving `ExtlClntAppGlobalOauthSettings` after the change (Salesforce stores multiple callback URLs
newline-separated within the single `<callbackUrl>` element). Gate 2 can use the Postman callback without any
further ECA edits.
