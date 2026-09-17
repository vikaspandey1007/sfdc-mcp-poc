"""Unit tests for server/app.py -- the hosted runtime entry point (Gate 4
Step 4).

Never calls real Gemini/Salesforce: Runner.run_async is monkeypatched to a
fake async generator yielding duck-typed Event-like objects (only the
attributes server/app.py actually reads: get_function_calls(),
is_final_response(), content.parts[].text). Auth-gating, health, and the
graceful-credential-failure path are all exercised without any network
call.
"""

from __future__ import annotations

from typing import AsyncIterator

import pytest
from fastapi.testclient import TestClient

import server.app as server_app


class _FakeFunctionCall:
    def __init__(self, name: str) -> None:
        self.name = name


class _FakeContent:
    def __init__(self, text: str) -> None:
        self.parts = [type("P", (), {"text": text})()]


class _FakeEvent:
    def __init__(self, function_calls: tuple[str, ...] = (), final_text: str | None = None) -> None:
        self._function_calls = [_FakeFunctionCall(name) for name in function_calls]
        self._final_text = final_text
        self.content = _FakeContent(final_text) if final_text is not None else None

    def get_function_calls(self) -> list[_FakeFunctionCall]:
        return self._function_calls

    def is_final_response(self) -> bool:
        return self._final_text is not None


@pytest.fixture(autouse=True)
def _demo_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEMO_API_KEY", "unit-test-demo-key")


@pytest.fixture
def client() -> TestClient:
    with TestClient(server_app.app) as test_client:
        yield test_client


def test_health_is_unauthenticated_and_reveals_nothing_sensitive(client: TestClient) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_ask_without_api_key_header_is_rejected(client: TestClient) -> None:
    response = client.post("/ask", json={"question": "hi"})
    assert response.status_code == 401


def test_ask_with_wrong_api_key_is_rejected(client: TestClient) -> None:
    response = client.post("/ask", json={"question": "hi"}, headers={"X-Demo-Api-Key": "wrong-key"})
    assert response.status_code == 401


def test_ask_fails_closed_when_demo_api_key_not_configured(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    monkeypatch.delenv("DEMO_API_KEY", raising=False)
    response = client.post("/ask", json={"question": "hi"}, headers={"X-Demo-Api-Key": "anything"})
    assert response.status_code == 500


def test_ask_with_correct_key_returns_synthesized_answer_and_tool_calls(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    async def fake_run_async(self, *, user_id: str, session_id: str, **kwargs) -> AsyncIterator[_FakeEvent]:
        yield _FakeEvent(function_calls=("getObjectSchema",))
        yield _FakeEvent(function_calls=("soqlQuery",))
        yield _FakeEvent(final_text="Here are the opportunities.")

    monkeypatch.setattr(server_app.Runner, "run_async", fake_run_async)

    response = client.post(
        "/ask",
        json={"question": "Show me open opportunities worth more than $250k."},
        headers={"X-Demo-Api-Key": "unit-test-demo-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["answer"] == "Here are the opportunities."
    assert body["tool_calls"] == ["getObjectSchema", "soqlQuery"]


@pytest.mark.parametrize("exception_type", [RuntimeError, ConnectionError, TimeoutError])
def test_ask_returns_503_not_a_raw_error_when_salesforce_auth_is_unavailable(
    monkeypatch: pytest.MonkeyPatch, client: TestClient, exception_type: type[Exception]
) -> None:
    async def failing_run_async(self, *, user_id: str, session_id: str, **kwargs) -> AsyncIterator[_FakeEvent]:
        raise exception_type("simulated Salesforce authorization failure")
        yield  # pragma: no cover -- unreachable, makes this a generator function

    monkeypatch.setattr(server_app.Runner, "run_async", failing_run_async)

    response = client.post(
        "/ask", json={"question": "hi"}, headers={"X-Demo-Api-Key": "unit-test-demo-key"}
    )

    assert response.status_code == 503
    assert "Salesforce authorization" in response.json()["error"]


def test_ask_returns_503_not_a_raw_500_for_unanticipated_errors(
    monkeypatch: pytest.MonkeyPatch, client: TestClient
) -> None:
    """Regression test: a live deployment hit Gemini's free-tier daily quota
    (google.adk's ResourceExhaustedError, a 429) mid-request, which fell
    through the Salesforce-specific except clause and surfaced as a raw,
    unhelpful plain-text 500 with no JSON body. Any exception type must now
    get a clean JSON 503, not just the ones this file anticipated."""

    async def failing_run_async(self, *, user_id: str, session_id: str, **kwargs) -> AsyncIterator[_FakeEvent]:
        raise ValueError("simulated unanticipated failure, e.g. an LLM provider quota error")
        yield  # pragma: no cover -- unreachable, makes this a generator function

    monkeypatch.setattr(server_app.Runner, "run_async", failing_run_async)

    response = client.post(
        "/ask", json={"question": "hi"}, headers={"X-Demo-Api-Key": "unit-test-demo-key"}
    )

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/json")
    assert "temporarily unavailable" in response.json()["error"]


def test_docs_and_openapi_are_disabled_in_the_hosted_runtime(client: TestClient) -> None:
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert client.get(path).status_code == 404
