"""Unit tests for server/log_redaction.py.

Pairs a positive case (a benign message passes through unchanged) with
negative cases (each redaction path actually catches the pattern it claims
to) -- per this project's standing rule not to trust a redaction claim
without a test that proves it actually fires.
"""

from __future__ import annotations

import logging

import pytest

from server.log_redaction import log_exception_redacted, redact


def test_benign_text_passes_through_unchanged() -> None:
    text = "Failed to create MCP session: Client error '401 Unauthorized' for url 'https://api.salesforce.com/x'"
    assert redact(text) == text


def test_redacts_configured_secret_env_var_value(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "SECRET-GOOGLE-KEY-abc123")
    text = "some error mentioning SECRET-GOOGLE-KEY-abc123 in its message"
    redacted = redact(text)
    assert "SECRET-GOOGLE-KEY-abc123" not in redacted
    assert "[REDACTED:GOOGLE_API_KEY]" in redacted


def test_redacts_all_configured_secret_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SF_ECA_CONSUMER_KEY", "secret-consumer-key")
    monkeypatch.setenv("DEMO_API_KEY", "secret-demo-key")
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", "secret-encryption-key")
    text = "leak: secret-consumer-key and secret-demo-key and secret-encryption-key"
    redacted = redact(text)
    assert "secret-consumer-key" not in redacted
    assert "secret-demo-key" not in redacted
    assert "secret-encryption-key" not in redacted


def test_redacts_bearer_token_pattern() -> None:
    text = "Authorization: Bearer eyJraWQiOiJhYmMxMjMifQ.some-jwt-shaped-token-value"
    redacted = redact(text)
    assert "eyJraWQiOiJhYmMxMjMifQ" not in redacted
    assert "Bearer [REDACTED]" in redacted


@pytest.mark.parametrize("param_name", ["key", "api_key", "access_token", "refresh_token", "client_secret", "code"])
def test_redacts_credential_shaped_query_params(param_name: str) -> None:
    text = f"GET https://example.com/endpoint?{param_name}=super-secret-value-123&other=fine"
    redacted = redact(text)
    assert "super-secret-value-123" not in redacted
    assert "other=fine" in redacted  # only the credential-shaped param is touched


def test_log_exception_redacted_never_leaks_a_secret_in_the_traceback(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The core regression this module exists for: an exception whose own
    message embeds a live secret must not leak that secret into the logs,
    even though log_exception_redacted logs the full traceback."""
    monkeypatch.setenv("GOOGLE_API_KEY", "SECRET-GOOGLE-KEY-xyz789")
    logger = logging.getLogger("test-log-redaction")

    try:
        raise RuntimeError(
            "simulated third-party error embedding a secret: "
            "https://generativelanguage.googleapis.com/v1/models?key=SECRET-GOOGLE-KEY-xyz789"
        )
    except RuntimeError as exc:
        with caplog.at_level(logging.ERROR):
            log_exception_redacted(logger, "Unexpected error", exc)

    assert "SECRET-GOOGLE-KEY-xyz789" not in caplog.text
    assert "RuntimeError" in caplog.text  # still useful for diagnosis
    assert "Unexpected error" in caplog.text
