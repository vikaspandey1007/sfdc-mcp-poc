# Demo script (first draft)

A first draft, per Gate 5's own plan ("first draft" — expect this to be refined once actually rehearsed in
front of an audience, not treated as final).

## Setup (before the audience arrives)

1. Confirm the hosted service is live: `curl https://sfdc-mcp-poc-agent.onrender.com/health` should return
   `{"status":"ok"}`.
2. Set `DEMO_API_KEY` in your own shell (never typed into the UI) — get the current value from wherever you
   store it, not from this document:
   ```powershell
   $env:DEMO_API_KEY = "..."
   ```
3. Run the thin UI: `streamlit run app/app.py` — opens at `http://localhost:8501`.
4. Do one throwaway warm-up question yourself first, off-screen, so the first thing the audience sees isn't
   a cold-start hiccup.

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
   - The agent refuses. Open the evidence panel again and point out **zero tool calls** — not "a tool
     tried and got blocked," but "there was never a mutation-shaped tool available to call in the first
     place." See `docs/security-model.md` for the exact distinction this is demonstrating: the system
     prompt's instruction is not what's stopping this, the Salesforce MCP server's tool catalogue itself
     has no write capability at all.
4. **Optional, if there's time and an inquisitive audience**: mention the credential architecture briefly —
   tokens live in a separate hosted store from the encryption key that protects them (`docs/decisions/ADR-003`),
   nothing is ever logged in plaintext, and the whole thing survives a Render restart without needing to
   re-authorize (demonstrated live during Gate 4's own verification).

## What NOT to do live

- Don't demo the OAuth authorization flow itself (`/oauth/salesforce/authorize`) unless you specifically
  want to show the Salesforce login screen — it's a one-time setup step, not part of the regular demo loop,
  and re-running it unnecessarily risks an awkward mid-demo Salesforce login prompt.
- Don't reveal `DEMO_API_KEY` on screen, in a terminal history, or in a shared screen recording — it's set
  in your own shell's environment, never visible in the Streamlit UI itself (verified in
  `tests/test_app.py`).
- Don't promise "this proves the Salesforce user's access is restricted end-to-end" — that's Gate 6's job
  (a genuinely restricted test user), not something this demo currently proves. What it does prove is that
  the MCP tool catalogue itself has no write capability, which is a real and strong claim, but a narrower
  one — see `docs/security-model.md`.

## If something goes wrong live

- **`/ask` returns a 503 "temporarily unavailable"**: almost certainly a transient Gemini API hiccup (rate
  limit or brief outage) — wait a few seconds and retry once, live, as part of the narrative ("even
  production LLM APIs have the occasional blip — here's what a graceful failure looks like instead of a
  crash"), rather than panicking.
- **The UI shows "DEMO_API_KEY is not configured"**: you forgot step 2 above — set it and restart
  `streamlit run app/app.py`.
- **The answer looks wrong / doesn't cite real data**: check the evidence panel first — if `soqlQuery` ran
  and returned data, the *tool layer* worked; a wrong-looking answer is more likely the LLM's own synthesis
  (see `docs/troubleshooting.md`'s "Gemini synthesis arithmetic error" for a known example of this
  specific failure shape) than a broken integration.
