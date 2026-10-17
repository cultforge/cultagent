"""Live share payload + primary gates."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from cultagent.cloud.guild_payloads import build_live_body
from cultagent.cloud.live_share import (
    LiveSharePublisher,
    build_live_players_from_presence,
    clamp_live_interval,
)
from cultagent.cloud.client import CloudError, CultForgeClient
from cultagent.settings import CloudSection


def test_clamp_live_interval() -> None:
    assert clamp_live_interval(1) == 3.0
    assert clamp_live_interval(5) == 5.0
    assert clamp_live_interval(99) == 10.0


def test_build_live_body_empty_roster() -> None:
    body = build_live_body(
        workload_id="awlk_1",
        guild_server_id="gms_1",
        reported_state="running",
        minecraft_version="1.20.1",
        players=[],
        server_facet={"game_mode": "survival", "cheats": False, "loader": "forge"},
    )
    assert body["player_count"] == 0
    assert body["players"] == []
    assert body["workload_id"] == "awlk_1"
    assert body["guild_server_id"] == "gms_1"
    assert body["server_facet"]["game_mode"] == "survival"
    assert "secret" not in body.get("server_facet", {})


def test_build_live_body_allowlists_session_stats() -> None:
    body = build_live_body(
        workload_id="awlk_1",
        reported_state="running",
        players=[
            {
                "minecraft_name": "Steve",
                "minecraft_uuid": "u-1",
                "session_stats": {
                    "deaths": 2,
                    "playtime_seconds": 90,
                    "score_total": 9999,  # stripped
                },
                "position": {"x": 1.5, "y": 64, "z": -2},
            }
        ],
    )
    player = body["players"][0]
    assert player["session_stats"] == {"deaths": 2, "playtime_seconds": 90}
    assert player["position"]["x"] == 1.5


def test_build_live_players_from_presence() -> None:
    rows = build_live_players_from_presence(
        {
            "players": [
                {
                    "minecraft_name": "Alex",
                    "uuid": "u-2",
                    "joined_at": "2000-01-01T00:00:00Z",
                    "session_stats": {"deaths": 1},
                }
            ]
        }
    )
    assert rows[0]["minecraft_uuid"] == "u-2"
    assert rows[0]["session_stats"]["deaths"] == 1
    assert rows[0]["session_stats"]["playtime_seconds"] > 0


@pytest.mark.asyncio
async def test_post_guild_live_client() -> None:
    client = CultForgeClient(CloudSection())
    calls: list[tuple[str, str, dict[str, Any]]] = []

    async def fake_request(
        method: str,
        path: str,
        *,
        agent_token: str | None = None,
        user_jwt: str | None = None,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        calls.append((method, path, json_body or {}))
        return {"ok": True}

    client._request = fake_request  # type: ignore[method-assign]
    await client.post_guild_live(
        "cagt_x",
        workload_id="awlk_1",
        guild_server_id="gms_1",
        reported_state="running",
        players=[],
    )
    assert calls[0][0] == "POST"
    assert calls[0][1] == "/v1/agent/guild/live"
    assert calls[0][2]["player_count"] == 0


@pytest.mark.asyncio
async def test_live_publisher_skips_non_primary() -> None:
    app = MagicMock()
    app.config.cloud.live_share_interval_seconds = 5
    app.bindings.active_bindings.return_value = [
        {
            "workload_id": "awlk_1",
            "scope": "guild",
            "guild_server_id": "gms_1",
            "local_server_id": "srv_1",
            "is_primary": False,
        }
    ]
    app.bindings.is_primary_binding = MagicMock(return_value=False)
    app.cloud_client.post_guild_live = AsyncMock()
    pub = LiveSharePublisher(app)
    result = await pub.flush("cagt_x")
    assert result["skipped"] >= 1
    assert result["posted"] == 0
    app.cloud_client.post_guild_live.assert_not_called()


@pytest.mark.asyncio
async def test_live_publisher_posts_empty_roster() -> None:
    app = MagicMock()
    app.config.cloud.live_share_interval_seconds = 5
    app.bindings.active_bindings.return_value = [
        {
            "workload_id": "awlk_1",
            "scope": "guild",
            "guild_server_id": "gms_1",
            "local_server_id": "srv_1",
            "is_primary": True,
        }
    ]
    app.bindings.is_primary_binding = MagicMock(return_value=True)
    app.servers.is_process_running = MagicMock(return_value=True)
    rec = MagicMock()
    rec.path = "."
    rec.minecraft_version = "1.20.1"
    rec.loader = "forge"
    rec.build_id = None
    rec.metadata = {}
    app.servers.get = AsyncMock(return_value=rec)
    app.metrics.collect = AsyncMock(return_value={"minecraft": {}})
    app.cloud_client.post_guild_live = AsyncMock(return_value={"ok": True})

    pub = LiveSharePublisher(app)
    result = await pub.flush("cagt_x")
    assert result["posted"] == 1
    kwargs = app.cloud_client.post_guild_live.await_args
    body = kwargs.kwargs.get("body") or {}
    assert body["player_count"] == 0
    assert body["players"] == []


@pytest.mark.asyncio
async def test_live_publisher_403_clear() -> None:
    app = MagicMock()
    app.config.cloud.live_share_interval_seconds = 5
    app.bindings.active_bindings.return_value = [
        {
            "workload_id": "awlk_1",
            "scope": "guild",
            "guild_server_id": "gms_1",
            "local_server_id": "srv_1",
            "is_primary": True,
        }
    ]
    app.bindings.is_primary_binding = MagicMock(return_value=True)
    app.servers.is_process_running = MagicMock(return_value=True)
    rec = MagicMock()
    rec.path = "."
    rec.minecraft_version = "1.20.1"
    rec.loader = "forge"
    rec.build_id = None
    rec.metadata = {}
    app.servers.get = AsyncMock(return_value=rec)
    app.metrics.collect = AsyncMock(return_value={})
    app.cloud_client.post_guild_live = AsyncMock(
        side_effect=CloudError("guild_not_verified", status_code=403)
    )
    pub = LiveSharePublisher(app)
    result = await pub.flush("cagt_x")
    assert result["errors"] == 1
