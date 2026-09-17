"""Gate 4 Step 4 -- the production-shaped entry point deployed to Render.

Deliberately not `adk web`: that bundles a development UI, which Gate 4's
own spec says not to expose publicly without a deliberate, secured reason.
This is a small, purpose-built FastAPI app exposing exactly two routes
(plus the hosted OAuth callback routes from server/oauth.py):

- GET  /health        unauthenticated, reveals no configuration (AT-09).
- POST /ask           authenticated (X-Demo-Api-Key), runs one question
                       through the agent and returns the synthesized answer
                       plus the tool-call trace, as JSON -- no HTML, no
                       browser UI. The smallest surface that can still
                       produce Step 7's acceptance evidence.

Startup fails fast (Gate 4 principle: "fail fast when required
configuration is missing") if core/Gemini env vars or the credential store
backend aren't valid -- see `_validate_startup_configuration`. Expired or
revoked Salesforce credentials during a request are caught and turned into
a clear 503, not a raw stack trace (Step 4's "graceful handling" + AT-05).

Run locally (rarely needed -- local dev normally uses `adk web` instead):
    uvicorn server.app:app --host 0.0.0.0 --port 8000

Render's start command (see render.yaml):
    uvicorn server.app:app --host 0.0.0.0 --port $PORT
No --reload anywhere in this file or in render.yaml -- no debug mode in the
hosted runtime.
"""

from __future__ import annotations

import hmac
import logging
import os
import urllib.error
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel

from agent.agent import root_agent
from agent.config import get_settings
from auth.credential_store import get_credential_store
from server.oauth import router as oauth_router

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger(__name__)

_DEMO_API_KEY_ENV_VAR = "DEMO_API_KEY"
_APP_NAME = "sfdc-mcp-poc"


def _validate_startup_configuration() -> None:
    """Fails fast if this process cannot possibly serve a real request.

    get_settings() validates every core + Gemini env var (agent/config.py).
    get_credential_store() validates and connects the active backend --
    for HostedCredentialStore that includes a live ping to Key Value, so a
    misconfigured REDIS_URL/CREDENTIAL_ENCRYPTION_KEY fails at startup, not
    on the first real request.
    """
    get_settings()
    get_credential_store()
    logger.info("Startup configuration validated (core + Gemini env vars, credential store reachable).")


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    _validate_startup_configuration()
    yield


app = FastAPI(
    title="Revenue Prioritisation Agent",
    debug=False,
    lifespan=_lifespan,
    # No auto-generated interactive docs in the hosted runtime -- same
    # "don't expose dev tooling publicly" reasoning as not running `adk web`.
    docs_url=None,
    redoc_url=None,
    openapi_url=None,
)
app.include_router(oauth_router)


@app.get("/health")
def health() -> dict[str, str]:
    """Unauthenticated. Deliberately returns nothing beyond a bare status --
    no env var names, no config values, no version/dependency details that
    could help an attacker (AT-09)."""
    return {"status": "ok"}


def _require_demo_api_key(x_demo_api_key: str | None = Header(default=None)) -> None:
    configured_key = os.environ.get(_DEMO_API_KEY_ENV_VAR)
    if not configured_key:
        # Missing server-side config is our bug, not a client auth failure --
        # fail closed (never treat "no key configured" as "no key required").
        raise HTTPException(status_code=500, detail=f"{_DEMO_API_KEY_ENV_VAR} is not configured.")
    if not x_demo_api_key or not hmac.compare_digest(x_demo_api_key, configured_key):
        raise HTTPException(status_code=401, detail="Missing or invalid X-Demo-Api-Key header.")


class AskRequest(BaseModel):
    question: str


class AskResponse(BaseModel):
    answer: str
    tool_calls: list[str]


@app.post("/ask", dependencies=[Depends(_require_demo_api_key)])
async def ask(payload: AskRequest) -> AskResponse:
    """Runs one question through the agent in a fresh, throwaway session --
    each request gets its own session_service/session, nothing persists
    between requests (this process holds no per-user state; the only
    durable state is Salesforce's own tokens, in the credential store)."""
    session_service = InMemorySessionService()
    session = await session_service.create_session(app_name=_APP_NAME, user_id="demo-user")
    runner = Runner(app_name=_APP_NAME, agent=root_agent, session_service=session_service)

    tool_call_names: list[str] = []
    answer_parts: list[str] = []
    try:
        async for event in runner.run_async(
            user_id="demo-user",
            session_id=session.id,
            new_message=types.UserContent(parts=[types.Part(text=payload.question)]),
        ):
            tool_call_names.extend(call.name for call in event.get_function_calls())
            if event.is_final_response() and event.content and event.content.parts:
                answer_parts.extend(part.text or "" for part in event.content.parts)
    except (RuntimeError, ConnectionError, TimeoutError, urllib.error.HTTPError) as exc:
        # RuntimeError: no tokens stored yet, or the credential store itself
        # is misconfigured. ConnectionError: MCP session creation failed,
        # the shape a revoked/expired Salesforce session takes (confirmed
        # empirically -- see docs/troubleshooting.md). HTTPError: Salesforce
        # rejected a refresh_token outright (revoked). All three mean the
        # Salesforce side of this integration needs re-authorization, not a
        # bug in this request -- surfaced as 503, not a raw 500/stack trace.
        logger.warning("Salesforce authorization unavailable during /ask (%s: %s)", type(exc).__name__, exc)
        return JSONResponse(
            status_code=503,
            content={
                "error": "Salesforce authorization is currently unavailable. Re-authorize via "
                "/oauth/salesforce/authorize, then retry."
            },
        )

    return AskResponse(answer="".join(answer_parts), tool_calls=tool_call_names)
