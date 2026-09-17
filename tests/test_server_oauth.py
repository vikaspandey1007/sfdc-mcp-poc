"""Unit tests for server/oauth.py -- the hosted OAuth callback routes
(Gate 4 Step 3).

Uses a fully in-memory fake Redis client (same pattern as
tests/test_hosted_credential_store.py) for the transient state/code_verifier
store, and stubs auth.token_broker.exchange_code_for_tokens so no real
network call happens. Tests the router in isolation, not the full
server/app.py (see tests/test_server_app.py for that).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import server.oauth as oauth_module


class _FakeRedisClient:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, name: str) -> str | None:
        return self._store.get(name)

    def set(self, name: str, value: str, ex: int | None = None) -> bool:
        self._store[name] = value
        return True

    def delete(self, *names: str) -> int:
        count = 0
        for name in names:
            if name in self._store:
                del self._store[name]
                count += 1
        return count


@pytest.fixture(autouse=True)
def _configured_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://fake-host:6379/0")
    monkeypatch.setenv("OAUTH_REDIRECT_URI", "https://my-service.onrender.com/oauth/salesforce/callback")


@pytest.fixture
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> _FakeRedisClient:
    client = _FakeRedisClient()
    monkeypatch.setattr(oauth_module, "_redis_client", lambda: client)
    return client


@pytest.fixture
def test_client() -> TestClient:
    app = FastAPI()
    app.include_router(oauth_module.router)
    return TestClient(app)


def test_authorize_requires_oauth_redirect_uri(
    monkeypatch: pytest.MonkeyPatch, test_client: TestClient, fake_redis: _FakeRedisClient
) -> None:
    monkeypatch.delenv("OAUTH_REDIRECT_URI", raising=False)
    response = test_client.get("/oauth/salesforce/authorize", follow_redirects=False)
    assert response.status_code == 500
    assert "OAUTH_REDIRECT_URI" in response.json()["detail"]


def test_authorize_stashes_code_verifier_and_redirects_to_salesforce(
    test_client: TestClient, fake_redis: _FakeRedisClient
) -> None:
    response = test_client.get("/oauth/salesforce/authorize", follow_redirects=False)

    assert response.status_code in (302, 307)
    location = response.headers["location"]
    assert location.startswith("https://")
    assert "code_challenge_method=S256" in location
    assert len(fake_redis._store) == 1  # exactly one pending state was stashed


def test_callback_rejects_missing_code_or_state(test_client: TestClient, fake_redis: _FakeRedisClient) -> None:
    response = test_client.get("/oauth/salesforce/callback", params={"state": "some-state"})
    assert response.status_code == 400


def test_callback_rejects_salesforce_error_param(test_client: TestClient, fake_redis: _FakeRedisClient) -> None:
    response = test_client.get(
        "/oauth/salesforce/callback",
        params={"error": "access_denied", "error_description": "user cancelled"},
    )
    assert response.status_code == 400
    assert "user cancelled" in response.json()["detail"]


def test_callback_rejects_unknown_or_expired_state(
    test_client: TestClient, fake_redis: _FakeRedisClient
) -> None:
    response = test_client.get(
        "/oauth/salesforce/callback", params={"code": "some-code", "state": "never-issued-state"}
    )
    assert response.status_code == 400
    assert "expired" in response.json()["detail"].lower()


def test_callback_success_exchanges_code_and_consumes_state_single_use(
    monkeypatch: pytest.MonkeyPatch, test_client: TestClient, fake_redis: _FakeRedisClient
) -> None:
    captured: dict[str, str] = {}

    def fake_exchange(*, code: str, code_verifier: str, redirect_uri: str):
        captured.update(code=code, code_verifier=code_verifier, redirect_uri=redirect_uri)

    monkeypatch.setattr(oauth_module, "exchange_code_for_tokens", fake_exchange)
    fake_redis.set("sfdc-mcp-poc:oauth-pending-state:abc123", "the-real-code-verifier")

    response = test_client.get(
        "/oauth/salesforce/callback", params={"code": "the-auth-code", "state": "abc123"}
    )

    assert response.status_code == 200
    assert captured == {
        "code": "the-auth-code",
        "code_verifier": "the-real-code-verifier",
        "redirect_uri": "https://my-service.onrender.com/oauth/salesforce/callback",
    }
    # Single-use: a second callback with the same state must be rejected.
    replay = test_client.get(
        "/oauth/salesforce/callback", params={"code": "the-auth-code", "state": "abc123"}
    )
    assert replay.status_code == 400


def test_authorize_then_callback_round_trip_with_real_state_and_verifier(
    monkeypatch: pytest.MonkeyPatch, test_client: TestClient, fake_redis: _FakeRedisClient
) -> None:
    """End-to-end within this module: the state issued by /authorize is
    exactly what /callback needs to look up the matching code_verifier --
    no hardcoded fixture values standing in for the real handshake."""
    captured: dict[str, str] = {}
    monkeypatch.setattr(
        oauth_module,
        "exchange_code_for_tokens",
        lambda **kwargs: captured.update(kwargs),
    )

    authorize_response = test_client.get("/oauth/salesforce/authorize", follow_redirects=False)
    location = authorize_response.headers["location"]
    query = location.split("?", 1)[1]
    params = dict(pair.split("=", 1) for pair in query.split("&"))
    import urllib.parse

    issued_state = urllib.parse.unquote(params["state"])

    callback_response = test_client.get(
        "/oauth/salesforce/callback", params={"code": "real-flow-auth-code", "state": issued_state}
    )

    assert callback_response.status_code == 200
    assert captured["code"] == "real-flow-auth-code"
    assert captured["code_verifier"]  # the real verifier round-tripped through Redis correctly
