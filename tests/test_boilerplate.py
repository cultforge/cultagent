from __future__ import annotations

from pathlib import Path

import pytest

from cultagent.commands import CommandContext, build_default_registry
from cultagent.config import (
    ConfigProfile,
    parse_server_properties,
    render_server_properties,
    structured_view,
)
from cultagent.identity import AgentStatus, IdentityStore, generate_node_id
from cultagent.network import NetworkManager
from cultagent.rbac import LocalAuthorizer, Visibility, VisibilityFilter
from cultagent.settings import AgentConfig, NetworkSection
from cultagent.app import CultAgentApp


def test_generate_node_id_prefix() -> None:
    node_id = generate_node_id()
    assert node_id.startswith("cfnode_")
    assert len(node_id) > len("cfnode_")


def test_identity_store_roundtrip(tmp_path: Path) -> None:
    store = IdentityStore(tmp_path / "identity.json", tmp_path / "credentials.json")
    identity = store.ensure_local_identity(
        display_name="test-node",
        platform="Windows",
        architecture="AMD64",
        agent_version="0.1.0",
        capabilities=["node.status"],
    )
    loaded = store.load_identity()
    assert loaded is not None
    assert loaded.node_id == identity.node_id
    assert loaded.status == AgentStatus.UNREGISTERED
    public = store.export_public()
    assert public["registered"] is False


def test_server_properties_structured() -> None:
    text = "difficulty=hard\nview-distance=12\nunknown-key=1\n"
    props = parse_server_properties(text)
    view = structured_view(props)
    assert view["gameplay"]["difficulty"] == "hard"
    assert view["performance"]["view-distance"] == "12"
    assert view["other"]["unknown-key"] == "1"
    rendered = render_server_properties(props)
    assert "difficulty=hard" in rendered


def test_profile_diff(tmp_path: Path) -> None:
    from cultagent.config import ProfileStore

    store = ProfileStore(tmp_path)
    profile = ConfigProfile(
        name="Event",
        values={"difficulty": "hard", "pvp": "true"},
    )
    store.save(profile)
    diff = store.diff({"difficulty": "easy", "pvp": "true"}, profile)
    assert diff == {"difficulty": {"from": "easy", "to": "hard"}}


def test_visibility_filter() -> None:
    filt = VisibilityFilter(Visibility.INTERNAL)
    payload = {"public": 1, "secret": "nope"}
    out = filt.filter_dict(
        payload,
        {"public": Visibility.PUBLIC, "secret": Visibility.SECRET},
    )
    assert out == {"public": 1}


def test_local_authorizer_resource_scope() -> None:
    auth = LocalAuthorizer()
    auth.grant("mod", "server.restart", "srv_a")
    assert auth.check("mod", "server.restart", "srv_a")
    assert not auth.check("mod", "server.restart", "srv_b")


def test_network_manager_default() -> None:
    mgr = NetworkManager(NetworkSection())
    assert mgr.active_name == "direct"


@pytest.mark.asyncio
async def test_app_bootstrap_and_commands(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CULTAGENT_DATA_DIR", str(tmp_path / "data"))
    config = AgentConfig()
    config.agent.data_dir = str(tmp_path / "data")
    app = CultAgentApp(config)
    app.bootstrap_identity()

    status = await app.dispatch("node.status")
    assert status["ok"] is True
    assert status["data"]["identity"]["node_id"].startswith("cfnode_")

    created = await app.servers.create("Frost Fall #1", minecraft_version="1.20.1", loader="forge")
    listed = await app.dispatch("server.list")
    assert listed["ok"] is True
    assert any(s["server_id"] == created.server_id for s in listed["data"]["servers"])

    # Without jar, start must fail cleanly (no more stub success).
    started = await app.dispatch("server.start", resource_id=created.server_id)
    assert started["ok"] is False


@pytest.mark.asyncio
async def test_unknown_command() -> None:
    registry = build_default_registry()
    result = await registry.dispatch(CommandContext(name="nope.command"))
    assert result.ok is False
    assert result.error == "unknown_command"
