# ADR-003: Hosted credential persistence — Render Key Value, not Disks/Postgres/external secrets manager

**Status:** Accepted
**Date:** 2026-09-17 (Gate 4)

## Context

Gate 4 deploys the proven Gate 3 implementation to Render. Its Step 1 requires refactoring token
persistence behind an explicit `CredentialStore` interface (`auth/credential_store.py`) with two
implementations: `LocalCredentialStore` (development, OS keyring — already existed as Gate 3B's
`auth/token_store.py`, refactored in place) and a new hosted backend appropriate for Render. Gate 4's own
plan is explicit that the hosted persistence technology must not be selected until options have been
researched and compared, with architectural approval required before implementation.

Gate 4's stated architectural principles constrain the option space directly:

- Application containers must be stateless; OAuth tokens/encryption keys must never be persisted to the
  Render filesystem (principles 2–3).
- Static secrets and dynamic OAuth credentials must be treated differently (principle 5).
- Prefer configuration and managed platform capabilities over custom infrastructure; do not introduce
  infrastructure unnecessary for the POC (principles 9–10); Step 2 explicitly lists "unnecessary databases"
  among things to avoid.

## Decision

**Render Key Value (a managed Redis-compatible instance), paid tier, configured for Journal + Snapshot
persistence.** The Fernet encryption key is a Render environment variable (`CREDENTIAL_ENCRYPTION_KEY`,
static, set once), never colocated with the ciphertext, which lives in Key Value under a single key
(`sfdc-mcp-poc:salesforce-tokens`).

## Options considered

| Option | Security | Persistence | Render compatibility | Operational complexity | Cost | Portability |
|---|---|---|---|---|---|---|
| **Render Disks** | N/A — disqualified | Survives restarts, but is a mounted filesystem volume | Native, but single-instance only, blocks zero-downtime deploys | Low | Included | Low — filesystem-shaped, hard to move off Render |
| **Render Key Value (paid, Journal+Snapshot)** — chosen | Ciphertext only; TLS in transit; encryption key kept in a separate env var, never in Key Value | Free tier: none, data lost on restart (disqualifying). Paid tier: disk-backed by default in this mode, survives restarts | Native managed add-on; internal URL for a same-region web service | Low — `redis-py` GET/SET/DEL, no schema/migrations | ~$10/mo minimum, no viable free tier | Contained entirely inside `HostedCredentialStore`; swappable without touching business logic |
| **Render PostgreSQL (paid, Basic-256mb)** | Ciphertext only; TLS in transit; AES-256 at rest; encryption key in a separate env var | Free tier: 30-day auto-expiration (disqualifying for anything long-running). Paid tier: durable by default, point-in-time recovery included | Native managed add-on | Low–medium — one-table schema/migration, otherwise simple | ~$6/mo minimum — cheapest paid durable option | Same containment as Key Value |
| **External secrets manager** (AWS/GCP Secret Manager, HashiCorp Vault, Doppler) | Strongest secret-specific tooling (rotation, audit, fine-grained IAM) | Yes, by design | Not native — called over the network from the Render service | Highest — new account, IAM/auth setup, another dependency to keep available | Varies; adds a second billing relationship | Good in theory, but adds a second platform dependency alongside Render itself |

Render's own environment variables / Secret Files were also considered for the *dynamic* token pair and
ruled out regardless of which option above won: Render's docs describe environment variable and secret
file changes as deploy-time only (each change triggers a new deploy), with no documented API for the
running application to update them at runtime — unworkable for a value that refreshes roughly every two
hours. They remain the correct store for the *static* `CREDENTIAL_ENCRYPTION_KEY`, per principle 5.

**Disqualified outright:** Render Disks — explicitly ruled out by principle 3 (never persist credentials to
the Render filesystem) regardless of its other properties, and it also blocks zero-downtime deploys and
multi-instance scaling.

**Runner-up:** Render PostgreSQL. Cheaper ($6/mo vs. $10/mo) and has a stronger default durability guarantee
than Key Value (no persistence-mode footgun to configure correctly), but provisions a full relational
database to store what is, in this app, a single small blob — a mismatch Gate 4 Step 2 calls out directly
("avoid... unnecessary databases"). Key Value's GET/SET/DEL model is a closer match to the actual shape of
this data (one key, one encrypted value) and needs no schema or migration.

**Rejected:** an external secrets manager. Best-in-class secret-management features, but adds a second
cloud platform dependency, a new account/billing relationship, and real setup complexity (IAM, cross-cloud
network calls) that's disproportionate to a POC storing one token pair — contrary to principles 9–10.

## Consequences

- New dependency: `redis>=5.0.0` (`pyproject.toml`).
- New required environment variables when `CREDENTIAL_STORE_BACKEND=hosted`: `REDIS_URL` (the Key Value
  instance's Internal Connection URL) and `CREDENTIAL_ENCRYPTION_KEY` (generated once via
  `Fernet.generate_key()`, set as a Render secret environment variable, never committed).
- Deployment prerequisite (Gate 4 Step 5, not yet done): provision a **paid** Render Key Value instance
  configured for **Journal + Snapshot** persistence — the free tier and the "Off"/cache-only persistence
  modes are both disqualifying and must not be used for this instance.
- `auth/credential_store.py`'s factory refuses to default to `LocalCredentialStore` when running on Render
  (detected via `RENDER=true`) unless `CREDENTIAL_STORE_BACKEND` is explicitly set — see
  `docs/troubleshooting.md` if this guard needs revisiting.
- If a future gate needs richer secret-management features (rotation policies, audit trails, multi-tenant
  scoping) that Key Value can't reasonably provide, this ADR's choice should be revisited — nothing here
  claims Key Value is the right answer forever, only that it's the right-sized answer for this POC's single
  token pair today.
