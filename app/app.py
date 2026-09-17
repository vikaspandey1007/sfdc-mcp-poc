"""Streamlit thin UI for the Revenue Prioritisation Agent (Gate 5).

Calls server/app.py's `/ask` API over HTTP -- holds no agent/MCP/credential
logic of its own, so that logic lives in exactly one place. This is a
client of the deployed service, same as any other caller.

AGENT_API_URL and DEMO_API_KEY come from this process's environment, never
from anything typed into the UI, and neither is ever rendered on screen --
Gate 5's acceptance criterion is that a non-technical viewer can ask a
question and see the answer and evidence without ever seeing a token or
credential.

This app holds DEMO_API_KEY server-side and uses it on behalf of *any*
visitor -- fine when only the presenter can reach it (localhost), but once
this is reachable on a public URL (Render, for demoing without a laptop --
see docs/demo-script.md), it would otherwise be an open, unauthenticated
proxy to the paid Gemini/Salesforce backend for anyone who finds the link.
UI_ACCESS_CODE gates that: a one-time passcode per browser session,
required in every environment (local and hosted alike) rather than only
enforced when "deployed" -- same "fail closed, never treat missing config
as no key required" posture as server/app.py's own DEMO_API_KEY check.

Run locally (the presenter sets these in their own shell first):
    export DEMO_API_KEY=...  UI_ACCESS_CODE=...     # PowerShell: $env:NAME = "..."
    streamlit run app/app.py
"""

from __future__ import annotations

import hmac
import os
from typing import Any

import requests
import streamlit as st

_DEFAULT_AGENT_API_URL = "https://sfdc-mcp-poc-agent.onrender.com"
_REQUEST_TIMEOUT_SECONDS = 90


def agent_api_url() -> str:
    return os.environ.get("AGENT_API_URL", _DEFAULT_AGENT_API_URL).rstrip("/")


def demo_api_key() -> str | None:
    return os.environ.get("DEMO_API_KEY")


def ui_access_code() -> str | None:
    return os.environ.get("UI_ACCESS_CODE")


def ask_agent(question: str) -> dict[str, Any]:
    """Calls the deployed /ask API and returns its parsed JSON body.

    Raises RuntimeError with a message safe to show a viewer (no header
    values, no secrets) on any non-200 response or network failure.
    """
    api_key = demo_api_key()
    if not api_key:
        raise RuntimeError(
            "DEMO_API_KEY is not set in this Streamlit process's environment -- the presenter "
            "needs to set it before running `streamlit run app/app.py`."
        )

    try:
        response = requests.post(
            f"{agent_api_url()}/ask",
            headers={"X-Demo-Api-Key": api_key},
            json={"question": question},
            timeout=_REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        raise RuntimeError(f"Could not reach the agent API ({type(exc).__name__}).") from exc

    if response.status_code != 200:
        body = {}
        if response.headers.get("content-type", "").startswith("application/json"):
            body = response.json()
        detail = body.get("error") or body.get("detail") or f"HTTP {response.status_code}"
        raise RuntimeError(str(detail))

    return response.json()


def render() -> None:
    st.set_page_config(page_title="Revenue Prioritisation Agent", page_icon="\U0001f4ca")
    st.title("Revenue Prioritisation Agent")

    configured_code = ui_access_code()
    if not configured_code:
        st.error(
            "UI_ACCESS_CODE is not configured for this deployment -- refusing to render an "
            "unauthenticated UI that would use DEMO_API_KEY on behalf of any visitor."
        )
        return

    if not st.session_state.get("unlocked"):
        entered_code = st.text_input("Access code", type="password")
        if st.button("Unlock", disabled=not entered_code):
            if hmac.compare_digest(entered_code, configured_code):
                st.session_state["unlocked"] = True
                st.rerun()
            else:
                st.error("Incorrect access code.")
        return

    st.caption(f"Talking to {agent_api_url()}")

    if not demo_api_key():
        st.error(
            "DEMO_API_KEY is not configured for this session. The presenter needs to set it in "
            "the environment before running this app -- it is never entered here."
        )
        return

    question = st.text_input(
        "Ask about Salesforce opportunities",
        placeholder="Show me open opportunities worth more than $250k.",
    )

    if st.button("Ask", disabled=not question.strip()):
        with st.spinner("Asking the agent..."):
            try:
                result = ask_agent(question)
            except RuntimeError as exc:
                st.error(str(exc))
                return

        st.markdown("### Answer")
        st.markdown(result.get("answer") or "_(no answer text returned)_")

        tool_calls = result.get("tool_calls") or []
        with st.expander(f"Evidence / tools used ({len(tool_calls)})"):
            if tool_calls:
                for name in tool_calls:
                    st.markdown(f"- `{name}`")
            else:
                st.markdown("_No tools were called for this question._")


render()
