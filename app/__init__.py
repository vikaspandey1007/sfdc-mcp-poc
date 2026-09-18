"""Gate 5 thin UI -- a Streamlit client for server/app.py's /ask API.

Not run via `adk web` or invoked in-process: this is a separate, thin
client over HTTP, exactly like any other caller of the deployed service.
Keeps agent-invocation logic in exactly one place (server/app.py).
"""
