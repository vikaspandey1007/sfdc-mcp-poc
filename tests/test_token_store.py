"""Unit tests for auth/token_store.py -- specifically the fallback
encryption key's storage location.

Security context: the fallback path (Fernet-encrypted file on disk) exists
because a real Salesforce token pair overflows Windows Credential Manager's
blob-size limit (see docs/troubleshooting.md "Windows Credential Manager
blob size limit"). But the *key* used to encrypt that file must not be
stored beside it -- an attacker who can read the fallback directory would
then have both the ciphertext and the key to decrypt it, which defeats most
of the point of encrypting it at all. These tests pin that the key lives in
the OS keyring instead (verified small enough to fit there even though the
token pair isn't), with file-based key storage only as a last resort when
keyring is truly unavailable, and that an already-encrypted file from
before this fix still decrypts correctly after migration.

Uses a fully in-memory fake keyring and a tmp_path-scoped fallback
directory throughout -- never touches the real OS keyring entry or the
real ~/.sfdc-mcp-poc/ directory that holds this machine's actual live
Salesforce tokens.
"""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from auth import token_store


class _FakeKeyring:
    """In-memory stand-in for the `keyring` module's two functions this
    file uses, keyed the same way (service, username) -> password."""

    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str) -> str | None:
        return self._store.get((service, username))

    def set_password(self, service: str, username: str, password: str) -> None:
        self._store[(service, username)] = password

    def delete_password(self, service: str, username: str) -> None:
        del self._store[(service, username)]


class _AlwaysFailingKeyring:
    """Simulates keyring being unavailable outright (not the size-limit
    case -- every call raises, matching e.g. no backend being configured)."""

    def get_password(self, service: str, username: str) -> str | None:
        raise RuntimeError("no keyring backend available")

    def set_password(self, service: str, username: str, password: str) -> None:
        raise RuntimeError("no keyring backend available")

    def delete_password(self, service: str, username: str) -> None:
        raise RuntimeError("no keyring backend available")


@pytest.fixture(autouse=True)
def _isolated_fallback_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Points the fallback file paths at a throwaway tmp_path directory for
    every test in this module, so nothing here ever touches the real
    ~/.sfdc-mcp-poc/ directory."""
    fallback_dir = tmp_path / "sfdc-mcp-poc"
    monkeypatch.setattr(token_store, "_FALLBACK_DIR", fallback_dir)
    monkeypatch.setattr(token_store, "_FALLBACK_TOKEN_FILE", fallback_dir / "token_store.enc")
    monkeypatch.setattr(token_store, "_FALLBACK_KEY_FILE", fallback_dir / "token_key.bin")
    return fallback_dir


def test_fallback_key_lives_in_keyring_not_beside_ciphertext_on_disk(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(token_store, "keyring", _FakeKeyring())

    key = token_store._fallback_key()

    assert key  # a real key was returned
    assert not token_store._FALLBACK_KEY_FILE.exists(), (
        "The encryption key must not be written to disk when keyring is available -- "
        "colocating it with the ciphertext file defeats the point of encrypting it."
    )


def test_fallback_key_is_stable_across_calls(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(token_store, "keyring", _FakeKeyring())

    first = token_store._fallback_key()
    second = token_store._fallback_key()
    assert first == second


def test_save_and_load_fallback_round_trip_with_keyring_backed_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(token_store, "keyring", _FakeKeyring())

    tokens = token_store.StoredTokens(
        access_token="unit-test-access-token",
        refresh_token="unit-test-refresh-token",
        expires_at=1234567890.0,
    )
    token_store._save_fallback(tokens)
    loaded = token_store._load_fallback()

    assert loaded == tokens
    assert not token_store._FALLBACK_KEY_FILE.exists()


def test_legacy_file_based_key_is_migrated_into_keyring_not_orphaned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Simulates a token store created before this fix (key file colocated
    with the ciphertext). The fix must migrate that existing key into
    keyring -- not generate a fresh one -- or the already-encrypted file
    becomes permanently undecryptable."""
    fake_keyring = _FakeKeyring()
    monkeypatch.setattr(token_store, "keyring", fake_keyring)

    # Simulate the pre-fix state: encrypt tokens with a key stored only on disk.
    legacy_key = Fernet.generate_key()
    token_store._FALLBACK_DIR.mkdir(parents=True, exist_ok=True)
    token_store._FALLBACK_KEY_FILE.write_bytes(legacy_key)
    tokens = token_store.StoredTokens(
        access_token="legacy-access-token",
        refresh_token="legacy-refresh-token",
        expires_at=1234567890.0,
    )
    payload = Fernet(legacy_key).encrypt(json.dumps(dataclasses.asdict(tokens)).encode("utf-8"))
    token_store._FALLBACK_TOKEN_FILE.write_bytes(payload)

    loaded = token_store._load_fallback()

    assert loaded == tokens, "Migration must preserve the ability to decrypt the existing file"
    assert not token_store._FALLBACK_KEY_FILE.exists(), "The legacy key file should be removed after migrating"
    assert fake_keyring.get_password(
        token_store._SERVICE_NAME, token_store._FALLBACK_KEY_KEYRING_USERNAME
    ) == legacy_key.decode("ascii"), "The migrated key in keyring must be the original key, not a new one"


def test_fallback_key_falls_back_to_file_when_keyring_is_unavailable_outright(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Keyring being unavailable (no backend at all) is a different failure
    mode from the documented size-limit rejection -- this is the deliberate
    last resort, not the default, and it must still work so the broker
    doesn't simply break on a machine with no keyring backend configured."""
    monkeypatch.setattr(token_store, "keyring", _AlwaysFailingKeyring())

    key = token_store._fallback_key()

    assert token_store._FALLBACK_KEY_FILE.exists()
    assert token_store._FALLBACK_KEY_FILE.read_bytes() == key

    # Reusing it on a second call must return the same key, not regenerate one.
    second = token_store._fallback_key()
    assert second == key
