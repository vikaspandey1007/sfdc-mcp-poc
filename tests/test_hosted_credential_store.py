"""Unit tests for auth/hosted_credential_store.py.

Security context: this store's whole design point is that the ciphertext
(in Key Value) and the encryption key (a Render env var) live in different
places -- see the module's own docstring. These tests use a fully
in-memory fake Redis client (never a real network connection) and assert
both the functional round-trip AND that what actually lands in the fake
store is genuinely ciphertext, not the plaintext token pair.
"""

from __future__ import annotations

import pytest
import redis
from cryptography.fernet import Fernet

from auth import hosted_credential_store
from auth.credential_store import StoredTokens
from auth.hosted_credential_store import HostedCredentialStore


class _FakeRedisClient:
    """In-memory stand-in for redis.Redis's get/set/delete/ping."""

    def __init__(self, ping_should_fail: bool = False) -> None:
        self._store: dict[str, str] = {}
        self._ping_should_fail = ping_should_fail

    def ping(self) -> bool:
        if self._ping_should_fail:
            raise redis.ConnectionError("fake connection failure")
        return True

    def get(self, name: str) -> str | None:
        return self._store.get(name)

    def set(self, name: str, value: str, **_kwargs: object) -> bool:
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
def _base_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REDIS_URL", "redis://fake-host:6379/0")
    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))


def _patch_client(monkeypatch: pytest.MonkeyPatch, client: _FakeRedisClient) -> None:
    monkeypatch.setattr(hosted_credential_store.redis.Redis, "from_url", staticmethod(lambda url, **kw: client))


def test_missing_redis_url_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        HostedCredentialStore()


def test_missing_encryption_key_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CREDENTIAL_ENCRYPTION_KEY", raising=False)
    with pytest.raises(RuntimeError, match="CREDENTIAL_ENCRYPTION_KEY"):
        HostedCredentialStore()


def test_unreachable_redis_raises_clear_error_at_construction(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, _FakeRedisClient(ping_should_fail=True))
    with pytest.raises(RuntimeError, match="Could not reach the hosted Key Value store"):
        HostedCredentialStore()


def test_load_returns_none_when_nothing_stored(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, _FakeRedisClient())
    store = HostedCredentialStore()
    assert store.load() is None


def test_save_then_load_round_trip(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, _FakeRedisClient())
    store = HostedCredentialStore()

    tokens = StoredTokens(
        access_token="hosted-test-access-token",
        refresh_token="hosted-test-refresh-token",
        expires_at=1234567890.0,
    )
    store.save(tokens)
    loaded = store.load()

    assert loaded == tokens


def test_clear_removes_stored_tokens(monkeypatch: pytest.MonkeyPatch) -> None:
    _patch_client(monkeypatch, _FakeRedisClient())
    store = HostedCredentialStore()

    store.save(StoredTokens(access_token="a", refresh_token="b", expires_at=0.0))
    assert store.load() is not None

    store.clear()
    assert store.load() is None


def test_value_stored_in_redis_is_ciphertext_not_the_plaintext_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole point of this store is that Key Value never sees a
    plaintext token value -- verify what actually lands in the fake store,
    not just that round-tripping through this class works."""
    client = _FakeRedisClient()
    _patch_client(monkeypatch, client)
    store = HostedCredentialStore()

    secret_access_token = "SECRET-ACCESS-TOKEN-value"
    store.save(StoredTokens(access_token=secret_access_token, refresh_token="r", expires_at=0.0))

    raw_stored_value = client._store[hosted_credential_store._REDIS_KEY]
    assert secret_access_token not in raw_stored_value


def test_two_instances_with_different_keys_cannot_read_each_others_ciphertext(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Confirms the encryption key is actually load-bearing (not a no-op) --
    a second store built with a different CREDENTIAL_ENCRYPTION_KEY must
    not be able to decrypt what the first one wrote."""
    client = _FakeRedisClient()
    _patch_client(monkeypatch, client)

    store_one = HostedCredentialStore()
    store_one.save(StoredTokens(access_token="a", refresh_token="b", expires_at=0.0))

    monkeypatch.setenv("CREDENTIAL_ENCRYPTION_KEY", Fernet.generate_key().decode("ascii"))
    store_two = HostedCredentialStore()

    with pytest.raises(Exception):  # cryptography.fernet.InvalidToken
        store_two.load()
