"""Unit tests for auth/token_broker.py -- Branch 3B's interactive PKCE
exchange and refresh.

Per the Gate 3 plan's Step 5 requirement, the load-bearing assertion in this
file is that no token value ever appears in logs (redaction discipline,
docs/gate-0-plan.md AT-06). Network/browser calls are stubbed; the callback
server's own state-mismatch (CSRF) guard is exercised against a real local
socket, since that's the actual security-relevant logic this module owns,
and it's fast and fully offline (no external network).
"""

from __future__ import annotations

import base64
import hashlib
import logging
import threading
import time
import urllib.request

import pytest

from auth import token_broker
from auth.token_store import StoredTokens


@pytest.fixture(autouse=True)
def _core_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SF_MY_DOMAIN_URL", "https://test.my.salesforce.com")
    monkeypatch.setenv("SF_ECA_CONSUMER_KEY", "test-consumer-key")
    monkeypatch.setenv(
        "SF_MCP_SERVER_URL", "https://api.salesforce.com/platform/mcp/v1/platform/sobject-reads"
    )


def test_pkce_pair_challenge_matches_verifier() -> None:
    verifier, challenge = token_broker._generate_pkce_pair()
    assert 43 <= len(verifier) <= 128  # RFC 7636 bound on code_verifier length
    expected_challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .rstrip(b"=")
        .decode("ascii")
    )
    assert challenge == expected_challenge
    assert "=" not in challenge  # PKCE requires unpadded base64url


def test_callback_server_extracts_code_on_matching_state(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(token_broker, "_CALLBACK_PORT", 18765)

    def fire_callback() -> None:
        time.sleep(0.2)
        urllib.request.urlopen(
            "http://localhost:18765/callback?code=test-auth-code&state=expected-state", timeout=5
        )

    thread = threading.Thread(target=fire_callback)
    thread.start()
    result = token_broker._run_callback_server(expected_state="expected-state")
    thread.join()

    assert result.code == "test-auth-code"
    assert result.state == "expected-state"

    # The handler's log_message override suppresses the default request log
    # (which would otherwise print the code-bearing URL to stderr).
    captured = capsys.readouterr()
    assert "test-auth-code" not in captured.err


def test_callback_server_rejects_state_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(token_broker, "_CALLBACK_PORT", 18766)

    def fire_callback() -> None:
        time.sleep(0.2)
        urllib.request.urlopen(
            "http://localhost:18766/callback?code=test-auth-code&state=wrong-state", timeout=5
        )

    thread = threading.Thread(target=fire_callback)
    thread.start()
    with pytest.raises(token_broker._AuthCodeNotReceived, match="State mismatch"):
        token_broker._run_callback_server(expected_state="expected-state")
    thread.join()


def test_run_interactive_authorization_never_logs_token_values(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    secret_access_token = "SECRET-ACCESS-TOKEN-abc123xyz"
    secret_refresh_token = "SECRET-REFRESH-TOKEN-def456uvw"
    secret_auth_code = "SECRET-AUTH-CODE-ghi789"

    class _NoOpBrowser:
        @staticmethod
        def open(url: str) -> bool:
            return True

    monkeypatch.setattr(token_broker, "webbrowser", _NoOpBrowser)
    monkeypatch.setattr(
        token_broker,
        "_run_callback_server",
        lambda expected_state: token_broker._CallbackResult(code=secret_auth_code, state=expected_state),
    )
    monkeypatch.setattr(
        token_broker,
        "_post_token_request",
        lambda token_url, params: {
            "access_token": secret_access_token,
            "refresh_token": secret_refresh_token,
            "expires_in": 7200,
            "token_type": "Bearer",
        },
    )
    monkeypatch.setattr(token_broker, "save_tokens", lambda tokens: None)

    with caplog.at_level(logging.DEBUG):
        result = token_broker.run_interactive_authorization()

    assert result.access_token == secret_access_token  # the real value is returned to the caller...
    assert secret_access_token not in caplog.text  # ...but never written to logs
    assert secret_refresh_token not in caplog.text
    assert secret_auth_code not in caplog.text


def test_refresh_access_token_never_logs_token_values(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    old_refresh_token = "OLD-REFRESH-TOKEN-value"
    new_access_token = "NEW-ACCESS-TOKEN-value"
    new_refresh_token = "NEW-REFRESH-TOKEN-value"

    monkeypatch.setattr(
        token_broker,
        "_post_token_request",
        lambda token_url, params: {
            "access_token": new_access_token,
            "refresh_token": new_refresh_token,
            "expires_in": 7200,
            "token_type": "Bearer",
        },
    )
    monkeypatch.setattr(token_broker, "save_tokens", lambda tokens: None)

    stored = StoredTokens(access_token="old-access-token", refresh_token=old_refresh_token, expires_at=0.0)

    with caplog.at_level(logging.DEBUG):
        result = token_broker.refresh_access_token(stored)

    assert result.access_token == new_access_token
    assert new_access_token not in caplog.text
    assert new_refresh_token not in caplog.text
    assert old_refresh_token not in caplog.text
