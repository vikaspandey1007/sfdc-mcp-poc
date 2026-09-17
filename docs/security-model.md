# Security model

Seeded early (during Gate 4's PR review) to make one specific distinction explicit, rather than leaving it
implicit across scattered evidence in `docs/developer-guide.md`. This file is a planned Gate 6 ("Security
unhappy paths") deliverable per `docs/gate-0-plan.md`'s section F — what's here now is a focused excerpt,
not the full document that gate will eventually own (threat coverage, the restricted-test-user work, AT-01
through AT-06 in full).

## Two different things are both called "read-only," and they are not the same guarantee

**1. The system prompt's instruction** (`agent/prompts.py`):

```
Do not modify Salesforce data.
```

This is a *behavioral ask* to the LLM. It is words in a prompt. A sufficiently adversarial input (prompt
injection via a malicious Salesforce field value, a jailbreak attempt, a future model that weighs
instructions differently) could in principle cause a model to disregard it. Nothing about this line, by
itself, makes it *impossible* for the agent to attempt a write — it only makes the agent *unlikely* to
try, if it's behaving as instructed.

**2. The enforced MCP capability boundary** (Gate 2's evidence, `salesforce/postman-verification.md`):
the `sobject-reads` Hosted MCP server exposes exactly six tools, and **no create/update/delete tool exists
in the catalogue at all** — confirmed by attempting a `tools/call` for `updateRecord` and getting back
`"Unknown tool"` (JSON-RPC `-32602`), not a permission-denied error caught after an attempt. This is not a
policy the agent chooses to follow; it is an absence of capability at the transport/protocol level. Even a
fully successful prompt-injection attack that convinced the model to *try* to write data would have no
mutation-shaped tool available to call — there is nothing to invoke.

**Why both matter, and why they are not interchangeable:**

- The prompt instruction is necessary but not sufficient — it shapes *ordinary* behavior (e.g., the agent
  proactively explaining *why* it can't help with a write request, rather than silently failing), but a
  security argument built only on it would be "prompt controls behavior," not "permissions enforce
  security" (see the reproducibility/security checklist in this project's own working notes).
- The capability boundary is the actual security guarantee. It is what Gate 2 proved independently of any
  LLM (Postman, zero model involvement) and what Gates 3–4 have since re-confirmed holds through the agent
  layer too, live, in `docs/developer-guide.md`'s evidence for both gates — specifically the observation
  that **no mutation-shaped tool call is ever attempted at all**, not merely that one gets rejected.

**How this shows up in the evidence already gathered** (not new claims, cross-referenced here for
clarity): Gate 2's Postman test proved the capability boundary with zero LLM involvement. Gates 3 and 4's
"Update this opportunity to Closed Won" tests proved the *same* boundary holds when a real model is in the
loop — and in Gate 4's live test specifically, the request logs show only the read-path tool calls that
happened before the model's refusal, confirming the model never even attempted an `updateRecord`-shaped
call, consistent with there being nothing for it to call.

**What this does not yet prove** (deferred to Gate 6, not silently assumed): that the underlying
Salesforce *user's* effective access is itself restricted, independent of the MCP tool catalogue —
`Revenue_Agent_Read_Access` is an additive Permission Set (see Gate 1's caveat in `docs/gate-0-plan.md`),
so a broader Profile could in principle still grant write access at the Salesforce layer even though no
MCP tool exposes it. Gate 6's restricted test user is where that gets built and proven, not this document.
