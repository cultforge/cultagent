"""Cloud registration + control-plane tests (httpx mocked)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cultagent.app import CultAgentApp
from cultagent.cloud.client import CloudError, CultForgeClient
from cultagent.cloud.registration import apply_registration, normalize_action
from cultagent.identity import AgentStatus
from cultagent.settings import AgentConfig, CloudSection


def test_normalize_action_aliases() -> None:
    assert normalize_action("server.command") == "server.console.execute"
    assert normalize_action("agent.ping") == "node.status"
    assert normalize_action("server.start") == "server.start"


def test_apply_registration(tmp_path: Path) -> None:
    config = AgentConfig()
    config.agent.data_dir = str(tmp_path / "data")
    app = CultAgentApp(config)
    app.bootstrap_identity()
    identity = app.identity_store.load_identity()
    assert identity is not None
    local = identity.node_id

    node = {
        "id": "cfagenode_test123",
        "owner_id": "usr_1",
        "guild_id": "gld_x",
        "name": "Home Box",
        "platform": "Windows",
        "arch": "AMD64",
        "agent_version": "0.1.0",
        "capabilities": ["node.status"],
    }
    apply_registration(
        app.identity_store,
        identity,
        node=node,
        agent_token="cagt_secret_once",
    )
    loaded = app.identity_store.load_identity()
    assert loaded is not None
    assert loaded.cloud_node_id == "cfagenode_test123"
    assert loaded.node_id == "cfagenode_test123"
    assert loaded.local_node_id == local
    assert loaded.guild_id == "gld_x"
    assert loaded.status == AgentStatus.ONLINE
    creds = app.identity_store.load_credentials()
    assert creds.token == "cagt_secret_once"
    public = app.identity_store.export_public()
    assert public["registered"] is True


@pytest.mark.asyncio
async def test_device_login_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = AgentConfig()
    config.agent.data_dir = str(tmp_path / "data")
    app = CultAgentApp(config)
    app.bootstrap_identity()
    identity = app.identity_store.load_identity()
    assert identity is not None

    async def fake_start(**kwargs: Any) -> dict[str, Any]:
        return {
            "status": True,
            "data": {
                "device_code": "device_secret_abc",
                "user_code": "AB12CD34",
                "expires_in": 600,
                "interval": 1,
                "device_id": "adev_1",
            },
        }

    async def fake_capture(**kwargs: Any) -> Any:
        from cultagent.cloud.browser_auth import BrowserAuthResult

        return BrowserAuthResult(token="session.from.browser", provider="google")

    async def fake_approve(user_jwt: str, *, user_code: str, guild_id: str | None = None) -> dict:
        assert user_jwt == "session.from.browser"
        assert user_code == "AB12CD34"
        return {"status": True, "data": {"status": "approved"}}

    async def fake_token(*, device_code: str) -> dict[str, Any]:
        assert device_code == "device_secret_abc"
        return {
            "status": True,
            "data": {
                "state": "approved",
                "node": {
                    "id": "cfagenode_device",
                    "owner_id": "usr_1",
                    "guild_id": "gld_x",
                    "name": "Home",
                    "capabilities": [],
                },
                "agent_token": "cagt_device",
            },
        }

    monkeypatch.setattr(app.cloud_client, "device_start", fake_start)
    monkeypatch.setattr(app.cloud_client, "device_approve", fake_approve)
    monkeypatch.setattr(app.cloud_client, "device_token", fake_token)
    monkeypatch.setattr(
        "cultagent.cloud.browser_auth.capture_oauth_session", fake_capture
    )

    prompts: list[dict[str, Any]] = []
    updated = await app.registration.device_login(
        identity,
        open_browser=False,
        on_prompt=prompts.append,
    )
    assert prompts and prompts[0]["user_code"] == "AB12CD34"
    assert prompts[0]["mode"] == "browser"
    assert updated.cloud_node_id == "cfagenode_device"
    assert app.identity_store.load_credentials().token == "cagt_device"


@pytest.mark.asyncio
async def test_device_login_with_jwt_approve(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AgentConfig()
    config.agent.data_dir = str(tmp_path / "data")
    app = CultAgentApp(config)
    app.bootstrap_identity()
    identity = app.identity_store.load_identity()
    assert identity is not None

    async def fake_start(**kwargs: Any) -> dict[str, Any]:
        return {
            "status": True,
            "data": {
                "device_code": "device_secret_jwt",
                "user_code": "ZZ99YY88",
                "verification_uri": "https://cultforge.com/agent/link",
                "expires_in": 600,
                "interval": 1,
            },
        }

    approved = {"ok": False}

    async def fake_approve(user_jwt: str, *, user_code: str, guild_id: str | None = None) -> dict:
        assert user_jwt == "user.jwt.here"
        assert user_code == "ZZ99YY88"
        assert guild_id == "gld_x"
        approved["ok"] = True
        return {"status": True, "data": {"status": "approved"}}

    async def fake_token(*, device_code: str) -> dict[str, Any]:
        assert approved["ok"]
        return {
            "status": True,
            "data": {
                "state": "approved",
                "node": {"id": "cfagenode_jwt", "owner_id": "usr_1", "capabilities": []},
                "agent_token": "cagt_jwt",
            },
        }

    monkeypatch.setattr(app.cloud_client, "device_start", fake_start)
    monkeypatch.setattr(app.cloud_client, "device_approve", fake_approve)
    monkeypatch.setattr(app.cloud_client, "device_token", fake_token)

    updated = await app.registration.device_login(
        identity,
        approve_jwt="user.jwt.here",
        guild_id="gld_x",
    )
    assert updated.cloud_node_id == "cfagenode_jwt"
    assert app.identity_store.load_credentials().token == "cagt_jwt"


@pytest.mark.asyncio
async def test_claim_pairing_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = AgentConfig()
    config.agent.data_dir = str(tmp_path / "data")
    app = CultAgentApp(config)
    app.bootstrap_identity()
    identity = app.identity_store.load_identity()
    assert identity is not None

    async def fake_claim(**kwargs: Any) -> dict[str, Any]:
        assert kwargs["code"] == "ABCD1234"
        return {
            "status": True,
            "data": {
                "node": {
                    "id": "cfagenode_claimed",
                    "owner_id": "usr_1",
                    "guild_id": None,
                    "name": identity.display_name,
                    "capabilities": identity.capabilities,
                },
                "agent_token": "cagt_claimed",
            },
        }

    monkeypatch.setattr(app.cloud_client, "claim_pairing", fake_claim)
    updated = await app.registration.claim_pairing_code(identity, code="abcd1234")
    assert updated.cloud_node_id == "cfagenode_claimed"
    assert app.identity_store.load_credentials().token == "cagt_claimed"


@pytest.mark.asyncio
async def test_control_plane_tick_executes_command(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AgentConfig()
    config.agent.data_dir = str(tmp_path / "data")
    app = CultAgentApp(config)
    app.bootstrap_identity()
    identity = app.identity_store.load_identity()
    assert identity is not None
    apply_registration(
        app.identity_store,
        identity,
        node={
            "id": "cfagenode_cp",
            "owner_id": "usr_1",
            "name": "n",
            "capabilities": [],
        },
        agent_token="cagt_cp",
    )

    async def fake_heartbeat(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"status": True, "data": {}}

    async def fake_poll(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {
            "status": True,
            "data": {
                "commands": [
                    {
                        "id": "cmd_1",
                        "action": "agent.ping",
                        "payload": {},
                        "actor_user_id": "usr_1",
                    }
                ],
                "desired_workloads": [],
                "poll_interval_seconds": 15,
                "pending_confirms": 0,
            },
        }

    reported: list[dict[str, Any]] = []

    async def fake_result(_token: str, command_id: str, *, success: bool, result: dict | None) -> dict:
        reported.append(
            {"command_id": command_id, "success": success, "result": result}
        )
        return {"status": True}

    async def fake_telemetry(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {"status": True}

    monkeypatch.setattr(app.cloud_client, "heartbeat", fake_heartbeat)
    monkeypatch.setattr(app.cloud_client, "poll", fake_poll)
    monkeypatch.setattr(app.cloud_client, "report_command_result", fake_result)
    monkeypatch.setattr(app.cloud_client, "publish_telemetry", fake_telemetry)

    summary = await app.control_plane.tick()
    assert summary["heartbeat"] is True
    assert summary["commands"] == 1
    assert summary["telemetry"] is True
    assert reported[0]["command_id"] == "cmd_1"
    assert reported[0]["success"] is True
    assert reported[0]["result"]["command"] == "node.status"


@pytest.mark.asyncio
async def test_status_reads_coalesce(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = AgentConfig()
    config.agent.data_dir = str(tmp_path / "data")
    app = CultAgentApp(config)
    app.bootstrap_identity()
    await app.servers.create("AdAstra", server_id="srv_coalesce")

    dispatches: list[str] = []
    orig = app.dispatch

    async def wrapped(command: str, **kwargs: Any) -> dict[str, Any]:
        dispatches.append(command)
        return await orig(command, **kwargs)

    reported: list[str] = []

    async def fake_result(
        _token: str, command_id: str, *, success: bool, result: dict | None
    ) -> dict[str, Any]:
        reported.append(command_id)
        return {"status": True}

    app.dispatch = wrapped  # type: ignore[method-assign]
    monkeypatch.setattr(app.cloud_client, "report_command_result", fake_result)

    payload = {"server_id": "srv_coalesce", "local_server_id": "srv_coalesce"}
    await app.control_plane._execute_command(  # noqa: SLF001
        "cagt_x",
        {"id": "cmd_a", "action": "server.status", "payload": payload},
    )
    await app.control_plane._execute_command(  # noqa: SLF001
        "cagt_x",
        {"id": "cmd_b", "action": "server.status", "payload": payload},
    )
    assert dispatches == ["server.status"]
    assert reported == ["cmd_a", "cmd_b"]


@pytest.mark.asyncio
async def test_429_backs_off_heartbeat(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AgentConfig()
    config.agent.data_dir = str(tmp_path / "data")
    app = CultAgentApp(config)
    app.bootstrap_identity()
    identity = app.identity_store.load_identity()
    assert identity is not None
    apply_registration(
        app.identity_store,
        identity,
        node={
            "id": "cfagenode_cp",
            "owner_id": "usr_1",
            "name": "n",
            "capabilities": [],
        },
        agent_token="cagt_cp",
    )

    heartbeats = 0

    async def boom_heartbeat(*_a: Any, **_k: Any) -> dict[str, Any]:
        nonlocal heartbeats
        heartbeats += 1
        raise CloudError("Too many connection attempts", status_code=429)

    async def fake_poll(*_a: Any, **_k: Any) -> dict[str, Any]:
        return {
            "status": True,
            "data": {
                "commands": [],
                "desired_workloads": [],
                "poll_interval_seconds": 15,
            },
        }

    monkeypatch.setattr(app.cloud_client, "heartbeat", boom_heartbeat)
    monkeypatch.setattr(app.cloud_client, "poll", fake_poll)
    monkeypatch.setattr(app.cloud_client, "publish_telemetry", boom_heartbeat)

    first = await app.control_plane.tick()
    assert first.get("heartbeat") is False
    assert app.control_plane._in_backoff()  # noqa: SLF001
    assert app.control_plane.poll_interval >= 30

    second = await app.control_plane.tick()
    assert second.get("heartbeat") is False
    assert "backoff_seconds" in second
    assert heartbeats == 1


@pytest.mark.asyncio
async def test_client_raises_cloud_error() -> None:
    client = CultForgeClient(CloudSection(api_base="https://example.invalid"))

    class FakeResp:
        status_code = 401
        text = '{"detail":"nope"}'

        def json(self) -> dict[str, str]:
            return {"detail": "nope"}

    class FakeAsyncClient:
        is_closed = False

        def __init__(self, *a: Any, **k: Any) -> None:
            pass

        async def aclose(self) -> None:
            return None

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *a: Any) -> None:
            return None

        async def request(self, *a: Any, **k: Any) -> FakeResp:
            return FakeResp()

    import cultagent.cloud.client as client_mod

    original = client_mod.httpx.AsyncClient
    client_mod.httpx.AsyncClient = FakeAsyncClient  # type: ignore[misc,assignment]
    try:
        with pytest.raises(CloudError) as exc:
            await client.agent_me("cagt_x")
        assert exc.value.status_code == 401
    finally:
        client_mod.httpx.AsyncClient = original  # type: ignore[misc,assignment]


@pytest.mark.asyncio
async def test_guild_client_paths_and_params(monkeypatch: pytest.MonkeyPatch) -> None:
    """Paths/query/body must match CONTEXT + live manifest."""
    client = CultForgeClient(CloudSection(api_base="https://api.example.test"))
    captured: list[dict[str, Any]] = []

    async def fake_request(
        method: str,
        path: str,
        *,
        agent_token: str | None = None,
        user_jwt: str | None = None,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        captured.append(
            {
                "method": method,
                "path": path,
                "json_body": json_body,
                "params": params,
            }
        )
        return {"status": True, "data": {}}

    monkeypatch.setattr(client, "_request", fake_request)

    await client.list_guild_servers("cagt_x", limit=50)
    await client.get_guild_server("cagt_x", "gsrv_1")
    await client.set_guild_server_tunnel(
        "cagt_x",
        "gsrv_1",
        workload_id="awl_1",
        tunnel_address="abc.playit.gg",
        tunnel_port=12345,
        network_mode="playit",
    )
    await client.upsert_guild_runtime(
        "cagt_x",
        workload_id="awl_1",
        state="running",
        player_count=3,
        tunnel_address="abc.playit.gg",
        tunnel_port=12345,
        network_mode="playit",
    )
    await client.list_guild_players("cagt_x", workload_id="awl_1", limit=200)
    await client.replace_guild_players(
        "cagt_x",
        workload_id="awl_1",
        players=[{"name": "Steve", "uuid": "00000000-0000-0000-0000-000000000000"}],
    )
    await client.list_guild_events("cagt_x", limit=50)
    await client.append_guild_events(
        "cagt_x",
        events=[{"event_type": "player.died", "minecraft_name": "Steve"}],
    )
    await client.upsert_guild_stats(
        "cagt_x",
        stats=[{"minecraft_uuid": "00000000-0000-0000-0000-000000000000", "kills": 1}],
    )
    await client.get_agent_commands_schema("cagt_x")

    by_path = {(c["method"], c["path"]): c for c in captured}
    assert by_path[("GET", "/v1/agent/guild/servers")]["params"] == {"limit": 50}
    tunnel = by_path[("POST", "/v1/agent/guild/servers/gsrv_1/tunnel")]
    assert tunnel["json_body"] == {
        "workload_id": "awl_1",
        "tunnel_address": "abc.playit.gg",
        "tunnel_port": 12345,
        "network_mode": "playit",
    }
    runtime = by_path[("POST", "/v1/agent/guild/runtime")]
    assert runtime["json_body"]["workload_id"] == "awl_1"
    assert runtime["json_body"]["tunnel_address"] == "abc.playit.gg"
    assert runtime["json_body"]["tunnel_port"] == 12345
    assert runtime["json_body"]["state"] == "running"
    assert "tunnel_endpoint" not in runtime["json_body"]
    players_post = by_path[("POST", "/v1/agent/guild/players")]
    assert players_post["json_body"]["workload_id"] == "awl_1"
    assert len(players_post["json_body"]["players"]) == 1
    assert by_path[("POST", "/v1/agent/guild/events")]["json_body"]["events"]
    assert by_path[("POST", "/v1/agent/guild/stats")]["json_body"]["stats"]
    assert ("GET", "/v1/agent/commands/schema") in by_path

    with pytest.raises(ValueError, match="workload_id"):
        await client.upsert_guild_runtime("cagt_x", workload_id="")


def test_split_join_address() -> None:
    from cultagent.cloud.guild_payloads import split_join_address

    assert split_join_address("abc.playit.gg:12345") == ("abc.playit.gg", 12345)
    assert split_join_address("tissues-offense.tun.ply.gg") == (
        "tissues-offense.tun.ply.gg",
        None,
    )
    assert split_join_address("[::1]:25565") == ("::1", 25565)
