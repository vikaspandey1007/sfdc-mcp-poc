"""Streamlit thin UI for the Revenue Prioritisation Agent (Gate 5).

Calls server/app.py's `/ask` API over HTTP -- holds no agent/MCP/credential
logic of its own, so that logic lives in exactly one place. This is a
client of the deployed service, same as any other caller.

AGENT_API_URL and DEMO_API_KEY come from this process's environment, never
from anything typed into the UI, and neither is ever rendered on screen --
Gate 5's acceptance criterion is that a non-technical viewer can ask a
question and see the answer and evidence without ever seeing a token or
credential.

Run locally (the presenter sets these in their own shell first):
    export DEMO_API_KEY=...          # PowerShell: $env:DEMO_API_KEY = "..."
    streamlit run app/app.py
"""

from __future__ import annotations

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
