# Public release readiness audit (Gate 8)

Performed against the full repository and full Git history (`git log --all -p`, `git grep`, `git ls-files`),
not just the current working tree — a redaction in the latest commit does not remove a value from history,
and GitHub shows full history by default. Dated 2026-09-18, against `main` at the point Gate 8 started
(commit range: everything through Gate 7's merge).

## Overall recommendation

**ACTION REQUIRED before this exact Git history is pushed to a public remote.** The current working tree
is clean (see below) and every offline/live test still passes after the redactions this gate made
(106 collected, 101 passed + 5 skipped offline). But real personal and organisational identifiers exist in
several historical commits and would be visible to anyone browsing this repo's history on GitHub, even
though the same values have now been redacted from the current files. **This is not a "PASS" until that
history question is explicitly decided** — see "Finding 1" below for the three real options and why none
of them was chosen unilaterally.

Everything else in this audit is a genuine **PASS**: no working credential, token, or key was ever found
in current files or history; repository hygiene is clean; documentation/gate-numbering consistency issues
found were fixed as part of this gate, not just listed.

## Finding 1 (highest severity) — real personal/org identifiers exist in Git history

**What was found**, confirmed by `git log --all -S "<value>"` (not a guess — each of these is a real
commit that introduced the value):

| Value | Nature | Found in (redacted in current tree, still in history) |
|---|---|---|
| A real personal Gmail address | Personal PII | `salesforce/metadata/.../Revenue_Agent_MCP_Client.eca-meta.xml`'s `contactEmail` field (introduced commit `8f889fe`) |
| A real Salesforce Developer Edition org domain and a real `@epam.com`-suffixed username | Organisational/personal identifier | `salesforce/setup.md`, `salesforce/permissions.md`, `salesforce/postman-verification.md`, `docs/gate-0-plan.md` (introduced across commits `fe2a22e`, `f0419c6`, `6ccbe9a`, and others touching the same lines) |
| The literal string `"EPAM Systems Inc"` (the org's free-text `Organization.Name`) | Organisational affiliation | `docs/gate-0-plan.md` (same commits as above) |
| A real Salesforce org ID and one other org-scoped component ID | Salesforce org identifier | Two `.eca-meta.xml` files under `salesforce/metadata/` |

**None of these are working credentials** — no Consumer Key, access token, refresh token, or encryption
key was ever found (see Finding 2). The org is a free Salesforce Developer Edition trial containing only
this project's own synthetic sample data (fictional companies — see "What's fine to publish" below); the
ECA's Consumer Key was redacted before every commit that touched it, per the discipline already documented
in `salesforce/setup.md`'s own status table. So the practical exploitability of these four items is low —
but a real personal email address and a real employer/org association are still not appropriate for an
indefinitely-public repository, independent of exploitability.

**Remediation applied this gate**: every one of these values was redacted from the *current* working tree
(see the diff for this gate's commit) — replaced with placeholders (`<demo-user-redacted>`,
`REDACTED_ORG_ID`, `demo-contact@example.com`, etc.) and a short comment pointing back to this document.
Going forward, no new commit will reintroduce them as long as future contributors follow the same
`salesforce/postman-verification.md`-established discipline of never pasting real domains/usernames into
docs.

**Remediation NOT applied, and why** — rewriting Git history (`git filter-repo`/BFG, or a fresh squashed
history) to remove these values from every past commit was considered and deliberately **not done**:
it is a destructive, hard-to-reverse operation (rewrites every commit hash on `main`, breaks any existing
clone/fork, and cannot be undone once pushed) that this document's own instructions require explicit
user approval for, not an assumption. **Three real options exist, in order of how much history is
preserved**:

1. **Push as-is, accept the residual exposure.** Lowest effort, but the four items above remain
   permanently visible in this repo's history once public. Reasonable only if the user has already decided
   the exposure is acceptable (the org itself was already used in earlier gates with the user's confirmed
   awareness — see `docs/gate-0-plan.md`'s Open Question 2 — but that confirmation predates the "public
   forever" context Gate 8 introduces, so it should be re-confirmed, not assumed to still apply).
2. **Rewrite history to scrub just these values** (`git filter-repo --replace-text` or equivalent), keeping
   every commit's structure/message/timeline intact. Removes the exposure while preserving the gate-by-gate
   commit history this project has been careful to build as evidence. Destructive to existing clones/forks;
   requires a force-push.
3. **Publish a fresh, single-history export** (e.g. `git init` a new repo, copy the current working tree,
   one commit) to a new public remote, keeping the detailed gate-by-gate history only in a private original.
   Cleanest exposure-wise, but loses the incremental commit history as public evidence of how each gate was
   actually built — a real cost, since several of this project's own docs (e.g. `docs/troubleshooting.md`)
   point back at specific commits as evidence.

**This choice is the user's, not this document's** — it trades off effort, history preservation, and
residual exposure differently, and only the user can weigh which of those three matters most here.

## Finding 2 — secrets/credentials: PASS

Full history scan (`git log --all -p`) for the actual shape of every real secret this project uses, run
twice — once for Gate 6, re-run for Gate 8 after all Gate 7/8 changes:

| Checked for | Result |
|---|---|
| Salesforce access/refresh tokens | None found — only obviously-fake test fixture values (`"legacy-access-token"`, `"OLD-REFRESH-TOKEN-value"`, etc., all inside `tests/`) |
| OAuth authorization codes / PKCE verifier/challenge | None found — same test-fixture pattern |
| Salesforce Consumer Key | Never committed unredacted — `salesforce/metadata/.../ecaGlblOauth-meta.xml`'s `consumerKey` field is `REDACTED_SEE_ENV_SF_ECA_CONSUMER_KEY` in every commit that touched it |
| `GOOGLE_API_KEY` / Gemini keys | None found |
| `DEMO_API_KEY` / `UI_ACCESS_CODE` | None found in any file ever committed. (Two real values *were* accidentally pasted into the chat session during development — flagged immediately in that session and rotated; they were never written to a file, so they don't appear in this scan) |
| `CREDENTIAL_ENCRYPTION_KEY` | None found — `render.yaml` declares it `sync: false` (manual, dashboard-only) and it is never referenced by value anywhere |
| Redis/Render connection strings | None found — wired via `render.yaml`'s `fromService`, never a literal URL |
| Authorization/Bearer header values | None found — the one JWT-*shaped* string in `tests/test_log_redaction.py` is a fixture (`"eyJraWQiOiJhYmMxMjMifQ.some-jwt-shaped-token-value"`), not a real token |
| `.env` files | Never committed — only `.env.example` (placeholders only, verified by reading the actual file content, not assumed from `.gitignore`) |
| Generated credential/token store files | Never committed — `.gitignore` covers `.sf/`, `.sfdx/`, and the local keyring/file fallback paths never live inside the repo directory |
| Screenshots/images | None committed at all (`git ls-files` for `.png`/`.jpg`/`.jpeg`/`.gif`/`.webp` returns nothing) — screenshots exchanged during development stayed in chat, never saved into the repo |

## Finding 3 — client/personal/sensitive information beyond Finding 1

Covered by Finding 1 above; no additional items found. Specifically checked and clear:
- No client name, client data, or client-identifying information anywhere (this project has always used a
  personal Salesforce Developer Edition trial org with synthetic data, never a real client's org or data).
- No local filesystem paths (`C:\Users\...` or `/home/...`) in any tracked file.
- Sample data (`salesforce/sample-data/*.csv`) is entirely fictional company names (Acme Manufacturing,
  Northwind Logistics, Blackwood Financial Services, etc.) — the kind of placeholder business data the
  audit's own instructions call "harmless Developer Edition/sample data," not something requiring redaction.

## Finding 4 — repository hygiene: PASS

- No generated files, caches, IDE files, or test artefacts are tracked (`git ls-files` checked against
  `__pycache__`, `.pyc`, `.pytest_cache`, `.idea`, `.vscode`, `.DS_Store`, `Thumbs.db`, `*.egg-info`,
  session/token-store files, `.adk/` — all absent from tracked files; present-but-untracked locally, which
  is `.gitignore` working as intended).
- One local-only tool config, `.claude/` (Claude Code's own settings — a permissions allowlist, no
  secrets), was untracked but not yet gitignored. **Fixed this gate**: added to `.gitignore`.
- No broken relative markdown links across `docs/*.md` (checked programmatically, all resolve).
- Gate numbering is now fully consistent everywhere (`Gate 0` through `Gate 7`, matching
  `docs/gate-0-plan.md`'s section J) — the one remaining inconsistency (Policy MCP's section header still
  saying "Gate 6" instead of "Gate 7") was caught and fixed during Gate 7 itself, not left for this audit.
- Test-count claims in existing docs were checked against the actual current suite
  (`pytest --collect-only`: 106 tests; `pytest -q`: 101 passed, 5 skipped) — `docs/developer-guide.md`'s
  existing "101 passed, 5 skipped" claim already matched; nothing else in the repo asserts a specific count
  that could go stale.
- No obsolete branch references in documentation — every branch named in a doc (e.g.
  `deployment/gate-4-render`, `feature/gate-5-thin-ui`) refers to a real, already-merged PR, kept as
  historical record, not an instruction to check out a branch that no longer exists.

## What's fine to publish as-is (not a finding, a deliberate non-finding)

- The live `onrender.com` URLs (`sfdc-mcp-poc-agent`, `sfdc-mcp-poc-ui`) are meant to be public — they are
  the actual demo endpoints, gated by `DEMO_API_KEY`/`UI_ACCESS_CODE` respectively, not secrets themselves.
- The GitHub repository URL itself (`github.com/vikaspandey1007/sfdc-mcp-poc`) necessarily contains the
  repo owner's GitHub username — this is how any public GitHub repo is addressed, not extraneous PII.
- The build brief (`CLAUDE_BUILD_BRIEF_SALESFORCE_GEMINI_MCP.md`) and every ADR are safe as-is — reviewed
  specifically for this audit, no identifiers beyond what's covered above.

## Verification commands used (reproducible, not just asserted)

```bash
git grep -niE "epam|pandey|@gmail|creative-narwhal|00Dak00000dgZfd|888ak000002Qfb3" -- .   # working tree, post-redaction: clean
git log --all -S "epamsystemsinc9" --oneline                                                # history: 3 commits, expected
git log --all -p | grep -iE "GOOGLE_API_KEY|CREDENTIAL_ENCRYPTION_KEY|DEMO_API_KEY|Bearer "  # secrets: only fixtures
git ls-files | grep -iE "\.png$|\.jpg$|\.pyc$|__pycache__|\.env$"                             # hygiene: no matches
```
