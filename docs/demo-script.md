# Demo script (first draft)

A first draft, per Gate 5's own plan ("first draft" — expect this to be refined once actually rehearsed in
front of an audience, not treated as final).

## Setup (before the audience arrives)

The UI is deployed to Render (`sfdc-mcp-poc-ui`), not just run locally — added specifically so this demo
doesn't depend on having your own laptop (e.g. presenting at a client site). Running it locally via
`streamlit run app/app.py` still works as a fallback if you do have your laptop and prefer that.

1. Confirm both hosted services are live: `curl https://sfdc-mcp-poc-agent.onrender.com/health` should
   return `{"status":"ok"}`; open `https://sfdc-mcp-poc-ui.onrender.com` in a browser and confirm it shows
   the access-code prompt (not an error about missing configuration).
2. Open the UI's URL and enter the **access code** (`UI_ACCESS_CODE` — get the current value from wherever
   you store it, not from this document; it's separate from `DEMO_API_KEY` and is never typed by the
   audience). This unlocks the question box for your browser session.
3. Do one throwaway warm-up question yourself first, off-screen, so the first thing the audience sees isn't
   a cold-start hiccup.

**Local fallback**, only if you have your own laptop and prefer it over the hosted UI: set both
`DEMO_API_KEY` and `UI_ACCESS_CODE` in your own shell, then `streamlit run app/app.py` (opens at
`http://localhost:8501`):

```powershell
$env:DEMO_API_KEY = "..."; $env:UI_ACCESS_CODE = "..."; streamlit run app/app.py
```

## The demo itself

1. **Frame it**: "This is a revenue intelligence agent. It's a real LLM (Gemini), talking to a real
   Salesforce org, through a real, secured, hosted deployment — not a mockup."
2. **Ask the positive question**: *"Show me open opportunities worth more than $250k."*
   - While it's thinking: mention this is going out over HTTPS to a real Render-hosted service, which is
     itself calling Salesforce's own Hosted MCP server with a real OAuth token — nothing here is simulated.
   - When the answer appears: open the **"Evidence / tools used"** panel and point out the real tool names
     (`getObjectSchema`, `soqlQuery`) — this is the audit trail proving the answer is grounded in real
     Salesforce data, not the model inventing numbers.
3. **Ask the negative question**: *"Update the United Oil Refinery Generators opportunity to Closed Won."*
   - The agent refuses. Open the evidence panel again and point out that **no mutation tool was available
     or invoked** — not "a tool tried and got blocked," but "there was never a mutation-shaped tool
     available to call in the first place." Depending on how the model phrases its refusal, the evidence
     panel may show zero tool calls, or it may show only read-only tools (e.g. it looked the record up
     before explaining it can't change it) — either way, the point being demonstrated is the same: no
     write-capable tool exists in the catalogue for it to reach for. See `docs/security-model.md` for the
     exact distinction this is demonstrating: the system prompt's instruction is not what's stopping this,
     the Salesforce MCP server's tool catalogue itself has no write capability at all.
4. **Optional, if there's time and an inquisitive audience**: mention the credential architecture briefly —
   tokens live in a separate hosted store from the encryption key that protects them (`docs/decisions/ADR-003`),
   nothing is ever logged in plaintext, and the whole thing survives a Render restart without needing to
   re-authorize (demonstrated live during Gate 4's own verification).

## What NOT to do live

- Don't demo the OAuth authorization flow itself (`/oauth/salesforce/authorize`) unless you specifically
  want to show the Salesforce login screen — it's a one-time setup step, not part of the regular demo loop,
  and re-running it unnecessarily risks an awkward mid-demo Salesforce login prompt.
- Don't reveal `DEMO_API_KEY` or `UI_ACCESS_CODE` on screen, in a terminal history, or in a shared screen
  recording — neither is ever visible in the Streamlit UI itself (verified in `tests/test_app.py`), but the
  access-code prompt on `sfdc-mcp-poc-ui` is exactly the kind of thing that ends up in a screen-share
  recording if you type it while sharing your screen. Enter it before you start sharing.
- Don't promise "this proves the Salesforce user's access is restricted end-to-end" — that's Gate 6's job
  (a genuinely restricted test user), not something this demo currently proves. What it does prove is that
  the MCP tool catalogue itself has no write capability, which is a real and strong claim, but a narrower
  one — see `docs/security-model.md`.

## If something goes wrong live

- **`/ask` returns a 503 "temporarily unavailable"**: almost certainly a transient Gemini API hiccup (rate
  limit or brief outage) — wait a few seconds and retry once, live, as part of the narrative ("even
  production LLM APIs have the occasional blip — here's what a graceful failure looks like instead of a
  crash"), rather than panicking.
- **The UI shows "UI_ACCESS_CODE is not configured" or "DEMO_API_KEY is not configured"**: those are set on
  Render's dashboard for `sfdc-mcp-poc-ui` (hosted) or in your own shell (local fallback) — check step 2/3
  of `docs/deployment-guide.md`'s provisioning order, or the local-fallback command above.
- **The answer looks wrong / doesn't cite real data**: check the evidence panel first — if `soqlQuery` ran
  and returned data, the *tool layer* worked; a wrong-looking answer is more likely the LLM's own synthesis
  (see `docs/troubleshooting.md`'s "Gemini synthesis arithmetic error" for a known example of this
  specific failure shape) than a broken integration.
