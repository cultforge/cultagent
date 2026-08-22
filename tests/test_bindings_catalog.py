"""Tests for agent bindings cache and unified build client paths."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cultagent.app import CultAgentApp
from cultagent.cloud.bindings import BindingCache, agent_mode
from cultagent.cloud.client import CultForgeClient
from cultagent.identity import AgentIdentity, AgentStatus
from cultagent.settings import AgentConfig, CloudSection


def test_agent_mode_personal_vs_guild() -> None:
    personal = AgentIdentity(node_id="anode_1", guild_id=None)
    guild = AgentIdentity(node_id="anode_2", guild_id="gld_x")
    assert agent_mode(personal) == "personal"
    assert agent_mode(guild) == "guild"


@pytest.mark.asyncio
async def test_binding_cache_refresh_and_lookup() -> None:
    cache = BindingCache()

    async def fake_bindings(token: str) -> dict[str, Any]:
        assert token == "cagt_test"
        return {
            "data": [
                {
                    "id": "cagb_1",
                    "scope": "guild",
                    "guild_server_id": "srv_a",
                    "workload_id": "awlk_1",
                    "revoked_at": None,
                }
            ]
        }

    async def fake_servers(token: str, *, limit: int = 100) -> dict[str, Any]:
        return {
            "data": [
                {
                    "binding": {"id": "cagb_1", "scope": "guild"},
                    "server": {
                        "id": "srv_a",
                        "effective_address": "play.example.com",
                        "effective_port": 25565,
                    },
                }
            ]
        }

    client = CultForgeClient(CloudSection())
    client.list_bindings = fake_bindings  # type: ignore[method-assign]
    client.list_agent_servers = fake_servers  # type: ignore[method-assign]

    identity = AgentIdentity(node_id="anode_1", guild_id="gld_x", status=AgentStatus.ONLINE)
    summary = await cache.refresh(client, "cagt_test", identity=identity)
    assert summary["mode"] == "guild"
    assert summary["bindings"] == 1
    assert summary["servers"] == 1

    binding = cache.binding_for_workload("awlk_1")
    assert binding is not None
    assert binding["guild_server_id"] == "srv_a"
    assert cache.is_bound("srv_a")


@pytest.mark.asyncio
async def test_builds_search_fallback_to_guild(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = AgentConfig()
    config.agent.data_dir = str(tmp_path / "data")
    app = CultAgentApp(config)
    app.bootstrap_identity()

    calls: list[str] = []

    async def fake_search(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append("search")
        raise Exception("use CloudError")  # noqa: TRY002

    async def fake_guild_list(token: str, *, limit: int = 50) -> dict[str, Any]:
        calls.append("guild")
        return {"data": [{"id": "bld_1", "name": "Guild Pack"}]}

    from cultagent.cloud.client import CloudError

    async def fake_search_err(*args: Any, **kwargs: Any) -> dict[str, Any]:
        calls.append("search")
        raise CloudError("not found", status_code=404)

    app.cloud_client.search_builds = fake_search_err  # type: ignore[method-assign]
    app.cloud_client.list_guild_builds = fake_guild_list  # type: ignore[method-assign]

    # Patch token
    from cultagent.identity import AgentCredentials

    app.identity_store.save_credentials(AgentCredentials(agent_token="cagt_x"))

    builds = await app.builds.list_builds(limit=10)
    assert calls == ["search", "guild"]
    assert builds[0]["id"] == "bld_1"


@pytest.mark.asyncio
async def test_ensure_bound_creates_local_using_cloud_id(tmp_path: Path) -> None:
    config = AgentConfig()
    config.agent.data_dir = str(tmp_path / "data")
    app = CultAgentApp(config)
    app.bootstrap_identity()
    app.bindings.mode = "guild"
    app.bindings.bindings = [
        {
            "id": "cagb_1",
            "scope": "guild",
            "guild_server_id": "srv_1hAMv7Fw",
            "workload_id": "awlk_1",
            "revoked_at": None,
        }
    ]
    app.bindings.servers = [{"id": "srv_1hAMv7Fw", "name": "AdAstra"}]

    first = await app.control_plane._ensure_bound_locals()  # noqa: SLF001
    assert first["created"] == ["srv_1hAMv7Fw"]
    record = await app.servers.get("srv_1hAMv7Fw")
    assert record is not None
    assert record.name == "AdAstra"
    assert record.metadata.get("guild_server_id") == "srv_1hAMv7Fw"

    second = await app.control_plane._ensure_bound_locals()  # noqa: SLF001
    assert second["created"] == []
    assert "srv_1hAMv7Fw" in second["already"]

    status = await app.dispatch("server.status", resource_id="srv_1hAMv7Fw")
    assert status["ok"] is True
    assert status["data"]["server_id"] == "srv_1hAMv7Fw"
    assert status["data"]["state"] in {"stopped", "unknown"}


@pytest.mark.asyncio
async def test_ensure_bound_copies_build_id(tmp_path: Path) -> None:
    config = AgentConfig()
    config.agent.data_dir = str(tmp_path / "data")
    app = CultAgentApp(config)
    app.bootstrap_identity()
    app.bindings.mode = "guild"
    app.bindings.bindings = [
        {
            "id": "cagb_1",
            "scope": "guild",
            "guild_server_id": "srv_1hAMv7Fw",
            "workload_id": "awlk_1",
            "revoked_at": None,
        }
    ]
    app.bindings.servers = [
        {
            "id": "srv_1hAMv7Fw",
            "name": "AdAstra",
            "build_id": "bld_pack",
            "loader": "neoforge",
            "minecraft_version": "1.21.1",
        }
    ]

    await app.control_plane._ensure_bound_locals()  # noqa: SLF001
    record = await app.servers.get("srv_1hAMv7Fw")
    assert record is not None
    assert record.build_id == "bld_pack"
    assert record.loader == "neoforge"
    assert record.minecraft_version == "1.21.1"
    assert record.metadata.get("build_id") == "bld_pack"

    # Second pass still syncs if the cloud row gains a build later
    app.bindings.servers[0]["build_id"] = "bld_pack2"
    await app.control_plane._ensure_bound_locals()  # noqa: SLF001
    record = await app.servers.get("srv_1hAMv7Fw")
    assert record is not None
    assert record.build_id == "bld_pack2"


@pytest.mark.asyncio
async def test_start_installs_missing_jar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AgentConfig()
    config.agent.data_dir = str(tmp_path / "data")
    app = CultAgentApp(config)
    app.bootstrap_identity()
    record = await app.servers.create("AdAstra", server_id="srv_1hAMv7Fw")
    record.build_id = "bld_pack"
    await app.servers.update_record(record)

    installed: list[str] = []

    async def fake_install(build_id: str, server_id: str, **kwargs: Any) -> dict[str, Any]:
        installed.append(build_id)
        assert server_id == "srv_1hAMv7Fw"
        return {"ok": True, "build_id": build_id}

    started: list[dict[str, Any]] = []

    async def fake_start(server_id: str, *, accept_eula: bool = False) -> dict[str, Any]:
        started.append({"server_id": server_id, "accept_eula": accept_eula})
        return {"server_id": server_id, "state": "starting"}

    monkeypatch.setattr(
        "cultagent.commands.handlers.jar_present", lambda _record: False
    )
    app.builds.install_to_server = fake_install  # type: ignore[method-assign]
    app.servers.start = fake_start  # type: ignore[method-assign]

    result = await app.dispatch(
        "server.start",
        resource_id="srv_1hAMv7Fw",
        params={"accept_eula": True},
    )
    assert result["ok"] is True
    assert installed == ["bld_pack"]
    assert started == [{"server_id": "srv_1hAMv7Fw", "accept_eula": True}]
