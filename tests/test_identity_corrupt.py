"""Corrupt / empty identity files must not crash the CLI."""

from __future__ import annotations

from pathlib import Path

from cultagent.identity import IdentityStore


def test_empty_identity_file_returns_none(tmp_path: Path) -> None:
    ident = tmp_path / "identity.json"
    creds = tmp_path / "credentials.json"
    ident.write_text("", encoding="utf-8")
    store = IdentityStore(ident, creds)
    assert store.load_identity() is None
    # Quarantined aside
    assert not ident.is_file()
    assert any(tmp_path.glob("identity.json.corrupt-empty-*"))


def test_whitespace_identity_file_returns_none(tmp_path: Path) -> None:
    ident = tmp_path / "identity.json"
    creds = tmp_path / "credentials.json"
    ident.write_text("   \n", encoding="utf-8")
    store = IdentityStore(ident, creds)
    assert store.load_identity() is None


def test_corrupt_json_identity_file_returns_none(tmp_path: Path) -> None:
    ident = tmp_path / "identity.json"
    creds = tmp_path / "credentials.json"
    ident.write_text("{not json", encoding="utf-8")
    store = IdentityStore(ident, creds)
    assert store.load_identity() is None


def test_ensure_local_identity_recovers_from_empty(tmp_path: Path) -> None:
    ident = tmp_path / "identity.json"
    creds = tmp_path / "credentials.json"
    ident.write_text("", encoding="utf-8")
    store = IdentityStore(ident, creds)
    identity = store.ensure_local_identity(
        display_name="test",
        platform="linux",
        architecture="x86_64",
        agent_version="0.2.3",
    )
    assert identity.node_id.startswith("cfnode_")
    assert store.load_identity() is not None


def test_empty_credentials_returns_empty(tmp_path: Path) -> None:
    ident = tmp_path / "identity.json"
    creds = tmp_path / "credentials.json"
    creds.write_text("", encoding="utf-8")
    store = IdentityStore(ident, creds)
    loaded = store.load_credentials()
    assert loaded.has_credentials is False
