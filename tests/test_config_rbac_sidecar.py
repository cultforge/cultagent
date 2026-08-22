"""Config profiles, RBAC visibility, and Chloe sidecar tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from cultagent.config import (
    ConfigProfile,
    ProfileStore,
    parse_server_properties,
    render_server_properties,
    structured_view,
)
from cultagent.rbac import LocalAuthorizer, Visibility, VisibilityFilter
from cultagent.sidecars import CHLOE_BOT_USER_ID, SidecarStore, ensure_chloe_grants


def test_profile_roundtrip(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles")
    profile = store.save(
        ConfigProfile(
            name="Event Night",
            description="Hard mode event",
            values={"difficulty": "hard", "pvp": "true", "view-distance": "12"},
        )
    )
    assert profile.name == "Event-Night"
    loaded = store.load("Event-Night")
    assert loaded.values["difficulty"] == "hard"
    listed = store.list_profiles()
    assert listed[0]["keys"] == 3


def test_profile_diff_and_apply(tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles")
    profile = ConfigProfile(name="t", values={"difficulty": "hard", "pvp": "true"})
    current = {"difficulty": "easy", "pvp": "true", "motd": "hi"}
    changes = store.diff(current, profile)
    assert "difficulty" in changes
    assert "pvp" not in changes
    merged = store.apply(current, profile, mode="merge")
    assert merged["difficulty"] == "hard"
    assert merged["motd"] == "hi"
    replaced = store.apply(current, profile, mode="replace")
    assert "motd" not in replaced


def test_structured_view() -> None:
    props = parse_server_properties("difficulty=hard\nmotd=Hello\n")
    view = structured_view(props)
    assert view["gameplay"]["difficulty"] == "hard"
    assert view["gameplay"]["motd"] == "Hello"
    assert view["other"] == {}
    assert "difficulty=hard" in render_server_properties(props)


def test_visibility_redacts_secrets() -> None:
    filt = VisibilityFilter(max_level=Visibility.INTERNAL)
    filtered = filt.filter_dict(
        {
            "product": "CultForge Agent",
            "token": "secret-token",
            "port": 25565,
            "password": "nope",
        }
    )
    assert "product" in filtered
    assert "token" not in filtered
    assert "password" not in filtered
    redacted = filt.redact_secrets({"nested": {"agent_token": "abc", "ok": 1}})
    assert redacted["nested"]["agent_token"] == "[redacted]"
    assert redacted["nested"]["ok"] == 1


def test_chloe_role_cannot_stop_server() -> None:
    auth = LocalAuthorizer()
    ensure_chloe_grants(auth)
    assert auth.check(CHLOE_BOT_USER_ID, "server.status", "*")
    assert auth.check(CHLOE_BOT_USER_ID, "server.mods.search", "*")
    assert not auth.check(CHLOE_BOT_USER_ID, "server.stop", "*")
    assert not auth.check(CHLOE_BOT_USER_ID, "playit.secret", "*")
    with pytest.raises(PermissionError):
        auth.require(CHLOE_BOT_USER_ID, "server.stop", "srv1")


def test_sidecar_token_issue_and_verify(tmp_path: Path) -> None:
    store = SidecarStore(tmp_path / "sidecars")
    auth = LocalAuthorizer()
    issued = store.issue("chloe", actor_id=CHLOE_BOT_USER_ID, role="chloe", authorizer=auth)
    assert issued["token"].startswith("cside_")
    clients = store.list_clients()
    assert clients[0]["name"] == "chloe"
    assert "token" not in clients[0]
    verified = store.verify(issued["token"])
    assert verified is not None
    assert verified["actor_id"] == CHLOE_BOT_USER_ID
    assert store.verify("bogus") is None
    store.revoke("chloe")
    assert store.verify(issued["token"]) is None


@pytest.mark.asyncio
async def test_dispatch_sidecar_enforce(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CULTAGENT_DATA_DIR", str(tmp_path / "data"))
    from cultagent.app import create_app

    agent = create_app()
    agent.bootstrap_identity()
    # Without enforce_local, stop is allowed (local/panel path)
    # With enforce_local as Chloe, stop is denied
    denied = await agent.dispatch(
        "server.stop",
        params={"server_id": "x"},
        actor_id=CHLOE_BOT_USER_ID,
        resource_id="x",
        enforce_local=True,
    )
    assert denied["ok"] is False
    assert "forbidden" in str(denied.get("error") or "")

    allowed = await agent.dispatch(
        "node.status",
        actor_id=CHLOE_BOT_USER_ID,
        enforce_local=True,
    )
    assert allowed["ok"] is True
    assert allowed["data"]["product"] == "CultForge Agent"
