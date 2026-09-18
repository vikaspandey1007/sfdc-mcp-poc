# Demo runbook (presenter-facing)

This is for whoever is **driving** the demo, not the audience — it assumes you already know the
architecture and are optimising for a smooth 10–15 minute walkthrough plus graceful recovery if something
glitches live. For the shorter, audience-oriented script (what to actually type/click), see
[`docs/demo-script.md`](demo-script.md); this document is the superset — pre-checks, talk track, and a
failure plan that document doesn't cover.

## Pre-demo checklist

Run through this **before the audience arrives**, ideally 15–30 minutes ahead:

- [ ] `curl https://sfdc-mcp-poc-agent.onrender.com/health` returns `{"status":"ok"}`. If it 502s/is slow,
      the service may be cold-starting (Render free/starter tiers spin down when idle) — hit it once now
      so it's warm before the audience sees it.
- [ ] Open `https://sfdc-mcp-poc-ui.onrender.com` — confirm it shows the **access-code prompt**, not an
      error about missing configuration. Enter `UI_ACCESS_CODE` and confirm the question box appears.
- [ ] Run the positive question once, off-screen, as a warm-up (see "Demo flow" step 3). Confirm it
      returns real data with a populated evidence panel — this is also your Gemini-availability check.
- [ ] Confirm Salesforce OAuth is still valid: the warm-up question succeeding *is* this check (a 503
      citing "Salesforce authorization unavailable" means the stored token needs re-authorization — see
      "Failure plan" below).
- [ ] Confirm token persistence is healthy: if the warm-up question works without you having to
      re-authorize, persistence is fine — no separate check needed.
- [ ] Confirm Policy MCP is available: run the multi-MCP question once, off-screen, as part of the same
      warm-up pass. If it errors, Policy MCP itself won't be the likely cause (it's a same-process local
      subprocess with no external dependency) — suspect Gemini/quota first.
- [ ] Confirm expected Salesforce sample data is present: the warm-up runs above already confirm this
      implicitly (real opportunity names/amounts came back).
- [ ] Browser: close other tabs, clear or hide anything with `DEMO_API_KEY`/`UI_ACCESS_CODE` in visible
      history, set zoom so the evidence panel is legible from the back of the room.
- [ ] Backup evidence ready: have this repo's `docs/developer-guide.md` Gate 3/5/7 sections (or a
      screenshot of their live evidence) open in a second tab, in case you need Plan B.

## Demo flow (10–15 minutes)

### 1. Business problem (60–90 seconds)

**Presenter action**: state the problem in plain terms.
**Expected result**: n/a (framing, not a system interaction).
**Architecture point being demonstrated**: none yet — this is the "why should you care" framing.
**Talk track**: *"Revenue teams need to know which opportunities deserve attention now, and why. That
'why' usually lives in someone's head — a mix of real CRM facts and an informal sense of what matters.
We're going to show you an agent that makes both of those explicit, and combines them live, on real
data."*

### 2. Architecture in 60 seconds

**Presenter action**: show the README's architecture diagram (or draw it on a whiteboard from memory).
**Expected result**: the audience understands there are two independent systems the agent talks to.
**Architecture point being demonstrated**: MCP as a capability boundary — the agent doesn't hold
Salesforce credentials or call its API directly.
**Talk track**: *"This agent never touches Salesforce's API directly, and it doesn't have Salesforce
credentials. It talks to an MCP server — a fixed, inspectable menu of things it's allowed to do. Today
that menu has two entries: a Salesforce menu we didn't write, and a policy-scoring menu we did."*

### 3. Salesforce read scenario

**Presenter action**: type *"Show me Closed Won opportunities worth more than $250K."*
**Expected result**: a real table of records with real Opportunity IDs, amounts, stages; evidence panel
shows `soqlQuery`.
**Architecture point being demonstrated**: the agent is grounded in real data, not generating plausible
numbers — the evidence panel is the audit trail.
**Talk track**: *"That's a real SOQL query, running through Salesforce's own hosted MCP server, against
a real org. Open the evidence panel — that's not decoration, that's proof this isn't a canned response."*

### 4. Mutation refusal / security scenario

**Presenter action**: type *"Update opportunity United Oil Refinery Generators to Closed Lost."*
**Expected result**: a clean refusal, citing the record's real current state for context; evidence panel
shows no mutation-shaped tool call.
**Architecture point being demonstrated**: the security boundary is structural, not the model being
polite — there is no write-capable tool in the catalogue for it to reach for, with or without a prompt
telling it not to.
**Talk track**: *"Notice what's in the evidence panel: at most a read call, never a write. That's not the
model choosing to behave — there is no 'update' tool in this menu at all. Even a jailbroken model has
nothing to invoke."*

### 5. Multi-MCP prioritisation scenario

**Presenter action**: type *"Using our revenue prioritisation policy, which of my high-value open
opportunities should I prioritise and why?"*
**Expected result**: an answer that visibly separates "Salesforce Evidence" from policy scoring per
opportunity, ranked, with real Opportunity names/amounts and real computed scores.
**Architecture point being demonstrated**: two independent MCP servers, one vendor-hosted and one custom,
orchestrated by the agent itself through the same protocol — this is the project's central claim.
**Talk track**: *"Watch the evidence panel fill up with calls to both servers — Salesforce for the facts,
our own Policy MCP for the scoring rules and the score itself. The agent decided to do that; we didn't
script this sequence anywhere in our code."*

### 6. Show evidence/tool trace

**Presenter action**: expand the evidence panel fully on the last answer.
**Expected result**: audience sees the real tool names from both servers in one trace.
**Architecture point being demonstrated**: observability — every claim the agent makes is traceable to a
specific tool call, not an opaque LLM output.
**Talk track**: *"This panel is the whole point. If you don't trust the answer, you don't have to — you
can see exactly what it asked for and what it got back."*

### 7. Explain architecture implication

**Presenter action**: return to the architecture diagram.
**Expected result**: n/a — synthesis moment.
**Architecture point being demonstrated**: this pattern generalises — swapping or adding an MCP server
doesn't require rearchitecting the agent.
**Talk track**: *"The reason this matters beyond one demo: adding a third capability — another system,
another policy — means adding another entry to this menu, not rewriting how the agent thinks."*

### 8. Future evolution

**Presenter action**: show the "Future evolution" diagrams from the README.
**Expected result**: n/a — closing framing.
**Architecture point being demonstrated**: clearly labelled as *future*, not implemented — Demandbase
Capability and Gong Capability as additional governed capabilities (not committed MCP implementations),
other LLM providers as a portability direction.
**Talk track**: *"None of this is built yet — we want to be precise about that. But the architecture we
just showed you doesn't need to change shape to get there."*

## Failure plan

For each, the general rule: **narrate the failure as part of the story, don't panic-recover silently.**
Production LLM/cloud systems fail sometimes; a graceful, explained failure is itself evidence the system
is well-behaved under stress.

| Failure | Likely cause | Recovery |
|---|---|---|
| **Render cold start** — first request hangs/times out | Free/starter-tier service was idle and spun down | This is why the pre-demo checklist warms it up. If it still happens live, narrate it: *"That's a cold start on a free hosting tier — not a demo flaw."* Retry once. |
| **Gemini/API error** — `/ask` returns "temporarily unavailable" | Rate limit or transient outage | Wait a few seconds, retry once, live, as narrative (*"even production LLM APIs have occasional blips — here's a graceful failure instead of a crash"*). If it persists, move to Plan B for that question only. |
| **Expired Salesforce credential** — 503 citing "Salesforce authorization unavailable" | Refresh token revoked/expired outside a normal session | Not fixable mid-demo without a browser OAuth flow (`/oauth/salesforce/authorize`), which is disruptive to run live. Move to Plan B (screenshots/evidence) for the rest of the Salesforce-dependent demo; re-authorize afterward. |
| **Salesforce MCP unavailable** — Salesforce-side outage | Vendor-side, out of your control | Same as above — Plan B, and note it as exactly the kind of external dependency failure the architecture is meant to fail *safely* under (clean 503, not a crash or a silent bypass). |
| **Policy MCP failure** — local subprocess errors | Very unlikely (no external dependency) — most likely a bad deploy | Redeploy `sfdc-mcp-poc-agent` (Policy MCP is a subprocess of that same service). If no time, skip to Plan B for the multi-MCP scenario only; the Salesforce-only scenarios are unaffected since they don't depend on Policy MCP. |
| **Unexpected model wording** — a technically-correct but oddly-phrased answer | Live LLM output varies run to run (documented throughout this repo) | Don't apologise for it at length — briefly note that live model output varies, then move on. The evidence panel is the part that matters, not the exact prose. |
| **Demo UI unavailable** — `sfdc-mcp-poc-ui` itself down | Render-side outage on that specific service | Fall back to `curl`/Postman directly against `sfdc-mcp-poc-agent`'s `/ask` with `X-Demo-Api-Key` — less polished, but proves the same architecture without the UI layer. |

**Plan B, generally**: this repository's `docs/developer-guide.md` (Gate 3, 5, 7 sections) contains
real, already-captured live evidence — actual tool traces and actual answers from prior runs. If live
demo fails mid-scenario, pivot explicitly: *"Let me show you the same scenario from our own evidence
capture, since we don't want to pretend a live failure didn't happen."* Never claim a live success that
didn't occur.
