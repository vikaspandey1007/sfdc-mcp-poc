"""Unit tests for auth/credential_store.py's get_credential_store() factory.

Gate 4 Step 1 hardening: this factory must never silently select the
development-only LocalCredentialStore when running on Render, and must fail
clearly (not silently) if a hosted backend is requested before it exists.
"""

from __future__ import annotations

import pytest

from auth.credential_store import get_credential_store
from auth.local_credential_store import LocalCredentialStore


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CREDENTIAL_STORE_BACKEND", raising=False)
    monkeypatch.delenv("RENDER", raising=False)


def test_defaults_to_local_off_render() -> None:
    store = get_credential_store()
    assert isinstance(store, LocalCredentialStore)


def test_explicit_local_backend_works(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CREDENTIAL_STORE_BACKEND", "local")
    store = get_credential_store()
    assert isinstance(store, LocalCredentialStore)


def test_refuses_to_default_to_local_on_render(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RENDER", "true")
    with pytest.raises(RuntimeError, match="CREDENTIAL_STORE_BACKEND is not set"):
        get_credential_store()


def test_explicit_local_backend_on_render_is_allowed_since_it_is_not_silent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The guard exists to prevent an unnoticed default, not to forbid every
    possible (mis)configuration -- an operator who explicitly sets
    CREDENTIAL_STORE_BACKEND=local on Render has made a deliberate choice,
    even if a questionable one, and isn't the failure mode this guards
    against."""
    monkeypatch.setenv("RENDER", "true")
    monkeypatch.setenv("CREDENTIAL_STORE_BACKEND", "local")
    store = get_credential_store()
    assert isinstance(store, LocalCredentialStore)


def test_hosted_backend_requires_its_own_env_vars(monkeypatch: pytest.MonkeyPatch) -> None:
    """Doesn't stub out HostedCredentialStore's own dependencies -- this is
    checking that the factory actually routes to it (and that constructing
    it without REDIS_URL/CREDENTIAL_ENCRYPTION_KEY fails clearly), not
    re-testing HostedCredentialStore's internals (see
    tests/test_hosted_credential_store.py for those)."""
    monkeypatch.setenv("CREDENTIAL_STORE_BACKEND", "hosted")
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("CREDENTIAL_ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        get_credential_store()


def test_unknown_backend_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CREDENTIAL_STORE_BACKEND", "bogus")
    with pytest.raises(RuntimeError, match="Unknown CREDENTIAL_STORE_BACKEND"):
        get_credential_store()
