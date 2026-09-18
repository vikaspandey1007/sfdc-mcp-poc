# Presentation outline (for conversion to slides)

Audience: senior client stakeholders, architects, security stakeholders, technology leadership. Style:
executive architecture/consulting — minimal text per slide, evidence over hype. Every slide below tags
its content as **PROVEN** (demonstrated with automated or live evidence in this repo), **DESIGNED**
(built and working, but not yet stress-tested/validated the way "proven" items are), or **FUTURE** (not
implemented — architectural direction only). Never blur these three on a live slide.

---

## Slide 1 — From CRM Chatbot to Governed Revenue Agent

**Executive message**: This isn't a chatbot bolted onto Salesforce — it's an agent whose access to
Salesforce is governed by a protocol boundary, not by trust in the model.

**Recommended visual**: split image — left, a generic "chatbot calls API" icon with a crossed-out lock;
right, this project's logical architecture diagram with the MCP boundary highlighted.

**Content points** (max 4):
- Enterprise agents need real system access to be useful.
- The common shortcut couples the reasoning layer directly to every system it touches.
- This POC uses MCP as the capability boundary instead.
- One business use case, fully working end to end: revenue opportunity prioritisation.

**Evidence/source**: `README.md` "The problem" and "What this project proves".

**Speaker notes**: Open with the problem, not the technology — the audience should feel the pain before
seeing the acronym. MCP gets introduced as the answer, not the headline.

**What NOT to claim**: that this is a general solution to "AI governance" — it's one working pattern,
demonstrated on one use case.

---

## Slide 2 — What We Set Out to Prove

**Executive message**: Three specific, falsifiable hypotheses — not a vague "AI can help with CRM."

**Recommended visual**: three numbered statements, plainly laid out.

**Content points**:
1. An agent can be given governed access to Salesforce without holding its credentials. **[PROVEN]**
2. The same agent can be given a second, custom capability through the same protocol, with no
   special-casing. **[PROVEN]**
3. The agent can orchestrate across both live, combining evidence from each correctly. **[PROVEN]**

**Evidence/source**: `docs/evidence-matrix.md`.

**Speaker notes**: Say plainly that these were hypotheses going in, and that the rest of the deck is the
evidence for or against each — this frames the whole talk as evidence-led, not sales-led.

**What NOT to claim**: that these three prove MCP servers are portable in general, or that any MCP server
would plug in this cleanly. It proves it for these two.

---

## Slide 3 — Architecture at a Glance

**Executive message**: One agent, two independent capability sources, one protocol.

**Recommended visual**: the README's Mermaid architecture diagram, simplified further if needed for a
slide (User → Agent → two MCP boxes → two backend boxes).

**Content points**:
- User → Streamlit demo UI → Agent API → Revenue Agent (Gemini).
- Agent → Salesforce Hosted MCP → real CRM data.
- Agent → Custom Policy MCP → deterministic scoring.

**Evidence/source**: `README.md`'s architecture diagram; `docs/technical-solution-design.md` §9.

**Speaker notes**: Spend real time here — this diagram is what every later slide refers back to. Point
at each box as you name it.

**What NOT to claim**: nothing yet — this is descriptive, not a claim slide.

---

## Slide 4 — Salesforce as the First Enterprise Capability

**Executive message**: Real OAuth, real read-only enforcement, verified independently of the AI layer
before any agent code existed.

**Recommended visual**: OAuth/PKCE sequence diagram (simplified) alongside a "6 tools, 0 write tools"
callout.

**Content points**:
- OAuth 2.0 Authorization Code + PKCE, no client secret. **[PROVEN]**
- `sobject-reads` MCP server: 6 read-only tools, verified via Postman *before* any LLM was involved.
  **[PROVEN]**
- Credentials never reach the model — injected per-call by a token broker. **[PROVEN]**
- Hosted deployment survives a real restart without re-authorizing. **[PROVEN]**

**Evidence/source**: `docs/technical-solution-design.md` §11, §15; Gate 2 (`salesforce/postman-verification.md`).

**Speaker notes**: The Postman-first sequencing is a genuinely strong point — emphasise that the
read-only guarantee was proven with *zero* AI involvement, so it doesn't depend on trusting the model at
all.

**What NOT to claim**: that Salesforce sharing/FLS was independently re-verified beyond the Permission
Set's own deploy+SOQL check — it wasn't audited beyond that.

---

## Slide 5 — Security by Design

**Executive message**: Three layers, and we're explicit about which ones are enforced versus advisory.

**Recommended visual**: the three-layer table from `README.md`'s "Security model", or the trust-boundary
diagram from `docs/technical-solution-design.md` §24.

**Content points**:
- Layer 1 (prompt instructions): behavioural, not enforced. **[DESIGNED — explicitly not a security claim]**
- Layer 2 (MCP capability catalogue): the real enforced boundary — no write tool exists. **[PROVEN]**
- Layer 3 (Salesforce identity/permissions): partially validated — a restricted test identity remains
  deferred. **[PARTIAL — deferred, not silently assumed done]**

**Evidence/source**: `docs/security-model.md`.

**Speaker notes**: This is the slide most likely to get a hard security question — welcome it. Be ready
to say plainly: "the Permission Set is additive, not restrictive, and we haven't yet built a genuinely
restricted test user to close that gap." That candour is a credibility asset here, not a weakness to
hide.

**What NOT to claim**: that the prompt instruction is a security control equivalent to Layer 2 or 3. Never
say "the model won't do X" as a security guarantee — say "there's no tool for it to call."

---

## Slide 6 — Breaking the Single-Platform Boundary

**Executive message**: The same agent, unmodified in its core logic, now talks to a second, custom
capability through the identical protocol.

**Recommended visual**: side-by-side comparison — Salesforce MCP's tool list vs. Policy MCP's tool list,
both under one "Agent" box.

**Content points**:
- Custom Policy MCP built with the official MCP SDK. **[PROVEN]**
- Deterministic scoring — plain, tested Python, not an LLM guess. **[PROVEN]**
- No database, no rules-engine product — five rules, committed as code. **[DESIGNED, deliberate scope choice]**
- Local stdio transport today — a deployment choice, not the architectural pattern. **[DESIGNED]**

**Evidence/source**: `docs/decisions/ADR-004-policy-mcp-design.md`; `docs/technical-solution-design.md` §18.

**Speaker notes**: Pre-empt the "why not a database/rules engine" question directly on this slide — it
was a deliberate, documented choice for this scope, not an oversight.

**What NOT to claim**: that Policy MCP's current local-stdio deployment is required by the architecture —
it isn't; it's the simplest fit for this POC's scope (see next section for the distinction).

---

## Slide 7 — Multi-MCP Use Case

**Executive message**: One real question, live, that only makes sense if both capabilities are actually
being used together.

**Recommended visual**: the multi-MCP sequence diagram (`docs/technical-solution-design.md` §19),
annotated with the real captured trace (getUserInfo → get_scoring_policy → soqlQuery ×3 →
score_opportunity ×12).

**Content points**:
- Real question: *"Using our revenue prioritisation policy, which of my high-value open opportunities
  should I prioritise and why?"* **[PROVEN, live]**
- Agent decided every tool call itself — nothing scripted in application code. **[PROVEN]**
- Final answer explicitly separates Salesforce evidence from policy scoring. **[PROVEN]**
- Verified against real captured values (real Opportunity names/scores appear in the answer), not just
  keyword matching. **[PROVEN]**

**Evidence/source**: `tests/test_multi_mcp_live.py`; `docs/developer-guide.md` Gate 7 section.

**Speaker notes**: This is the centrepiece slide. If you only have time to go deep on one thing live in
the room, make it this scenario (see `docs/demo-runbook.md` step 5).

**What NOT to claim**: that this exact tool-call sequence repeats identically every time — Gemini's tool
selection varies run to run; what's guaranteed is that both servers get used and both show up in the
answer, not the precise order.

---

## Slide 8 — What the POC Actually Proved

**Executive message**: A concise, evidence-only summary — no aspirational language.

**Recommended visual**: the evidence-matrix table (or a condensed excerpt of it), status column visible.

**Content points**:
- Governed, credential-free agent access to a real enterprise system. **[PROVEN]**
- A custom capability integrated through the same protocol, zero special-casing. **[PROVEN]**
- Multi-MCP orchestration with live, value-level verification. **[PROVEN]**
- Restart-durable hosted deployment. **[PROVEN]**
- A named, honest list of what's deferred (restricted test identity, live revocation test). **[DEFERRED, explicit]**

**Evidence/source**: `docs/evidence-matrix.md` in full.

**Speaker notes**: Read this slide almost verbatim from the evidence matrix — the point of this slide is
that nothing on it is a marketing statement, every line has a test or a live run behind it.

**What NOT to claim**: anything not on the evidence matrix. If a stakeholder asks about something this
slide doesn't cover, say so directly rather than improvising an answer.

---

## Slide 9 — From POC to Enterprise Architecture

**Executive message**: What actually has to change before this becomes a production system — stated
plainly, not glossed over.

**Recommended visual**: a simple two-column "POC today / needed for production" list.

**Content points**:
- Enterprise SSO/identity, replacing the shared-secret demo auth. **[FUTURE]**
- The two deferred security items, actually closed out. **[FUTURE]**
- Horizontal scaling / HA design beyond a single Render instance. **[FUTURE]**
- Structured monitoring/alerting, secret rotation policy, formal data governance. **[FUTURE]**

**Evidence/source**: `docs/technical-solution-design.md` §29 ("Productionisation considerations").

**Speaker notes**: Lead this slide yourself rather than waiting for the audience to ask "so is this
production-ready?" — answering it before it's asked is the stronger position.

**What NOT to claim**: that any of this is scheduled or committed — it's a list of what production would
require, not a roadmap with dates.

---

## Slide 10 — Evolution

**Executive message**: The pattern this POC proved is designed to extend — but extension is not yet
attempted.

**Recommended visual**: the README's two "Future evolution" diagrams (additional MCP servers;
model-provider portability), both clearly watermarked FUTURE.

**Content points**:
- Additional enterprise capabilities as more MCP servers (Demandbase, Gong, others). **[FUTURE]**
- Each new server is its own trust domain — approving these two never pre-approves a third. **[DESIGNED, stated principle]**
- Model-provider portability (Claude, OpenAI, others) as an architectural direction. **[FUTURE — not tested]**

**Evidence/source**: `README.md` "Future evolution"; the original build brief's §9 future-state section.

**Speaker notes**: Close on ambition, but keep the FUTURE label visible and say it out loud: *"We want to
be precise that none of this is built — it's the direction the architecture makes feasible."*

**What NOT to claim**: that provider portability has been tested, attempted, or is low-risk to build —
it is genuinely unproven, and the deck should not imply otherwise.
