# ADR-002: OAuth authentication strategy — token broker (3B), not native ADK OAuth (3A)

**Status:** Accepted
**Date:** 2026-09-16 (Gate 3)

## Context

`docs/gate-0-plan.md` (D2) split Gate 3's Salesforce↔ADK authentication into two branches: 3A, ADK's
native `McpToolset(auth_scheme=..., auth_credential=...)` OAuth 2.0 + PKCE flow, attempted first; 3B, a
hand-built OAuth token broker, built only if 3A fails reproducibly. D2's stated rationale for trying 3A
first was to prove an incompatibility empirically rather than assume one from desk research (brief §8 Gate
0: "do not silently invent glue code if there is a protocol/authentication incompatibility").

## Decision

**3A was attempted and failed reproducibly. 3B (token broker) is now built.**

**Summary**: 3A failed *before* OAuth negotiation with Salesforce even began, because ADK's OAuth2
credential abstraction required a `client_secret`, while the Salesforce ECA is intentionally configured as
a public Authorization Code + PKCE client. **No fake client secret was introduced to bypass the framework
validation.**

## Evidence

Running `adk web` (`google-adk` 2.9.1) against the real `Revenue_Agent_MCP_Client` ECA and asking the
Gate 3 exit-criterion question produced, on the very first turn, before any OAuth consent popup appeared:

```
errorCode: "ValueError"
errorMessage: "Auth Scheme SecuritySchemeType.oauth2 requires both client_id and client_secret in auth_credential.oauth2."
```

Traced to an unconditional check in the installed package
(`.venv/Lib/site-packages/google/adk/auth/auth_handler.py:296-304`), which raises before
`generate_auth_uri()` is ever called — i.e. before ADK attempts to build an authorization URL at all. There
is no constructor flag or alternate code path that allows a public (secret-less) OAuth2 client. Full detail,
including the exact source read and the workaround considered and declined, is in
`docs/troubleshooting.md` ("Branch 3A result: FAIL").

This is **not** the failure shape anticipated by Gate 0's research (`#2168`, `#2615`, `#3331` — all about
the native flow hanging, being ignored, or ordering defects). It's a distinct, more fundamental limitation:
`google-adk` 2.9.1's OAuth2 `AuthHandler` assumes a confidential client (has a secret) unconditionally,
which structurally cannot serve a PKCE-only public client — which is what the Salesforce ECA deliberately
is (`isConsumerSecretOptional=true`, `isSecretRequiredForRefreshToken=false`, no secret configured; Gate 1's
D2 decision explicitly chose this for the native/public client architecture). PKCE's `code_verifier` being a
genuinely modeled field on `OAuth2Auth` doesn't help — the client_secret check gates the flow before any
PKCE-specific logic runs.

**Workaround considered and declined**: passing a fabricated non-empty `client_secret` just to satisfy the
check. Rejected — it contradicts the ECA's actual security design (no real secret exists to send), and
whether Salesforce's token endpoint would accept or reject a request carrying an arbitrary secret value was
genuinely unverified, not a known-good path worth spending the time-box on.

## Consequences

- `auth/token_broker.py` + `auth/token_store.py` are built: a one-time interactive Authorization Code + PKCE
  exchange against the ECA using its already-registered `http://localhost:8765/callback`, tokens persisted
  via OS keyring (Windows Credential Manager), never in `.env` or a plaintext repo file.
- `agent/mcp_config.py` is rewired to use `McpToolset(header_provider=...)` instead of
  `auth_scheme`/`auth_credential`, sourcing a dynamic `Authorization: Bearer` header from the token store so
  a refreshed token is always used without restarting the agent.
- The token broker itself becomes a small custom component needing its own care (token storage, refresh
  failure handling) — accepted as the necessary cost once 3A was shown not to work, not built speculatively
  ahead of that evidence.
- If a future `google-adk` release adds public-client support to its OAuth2 `AuthHandler`, 3A could be
  revisited — this ADR's failure is about the installed library version (2.9.1), not the OAuth 2.0/PKCE
  protocol itself (which Gate 0 already confirmed Salesforce's ECA correctly implements).
