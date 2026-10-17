"""Score batch payloads, primary binding gates, facet helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from cultagent.cloud.bindings import BindingCache
from cultagent.cloud.client import CloudError, CultForgeClient
from cultagent.cloud.guild_payloads import build_score_batch_body
from cultagent.cloud.scoring import (
    ScoreDeltaBuffer,
    aggregate_deltas_to_players,
    event_to_delta,
    read_server_facet,
)
from cultagent.settings import CloudSection


def test_is_primary_binding_defaults_true() -> None:
    assert BindingCache.is_primary_binding({}) is True
    assert BindingCache.is_primary_binding({"is_primary": False}) is False
    assert BindingCache.is_primary_binding({"primary": True}) is True


def test_stats_eligible_and_primary_filters() -> None:
    cache = BindingCache(mode="guild")
    cache.bindings = [
        {
            "id": "cagb_1",
            "scope": "guild",
            "guild_server_id": "srv_a",
            "workload_id": "awlk_1",
            "is_primary": True,
            "stats_eligible": True,
        },
        {
            "id": "cagb_2",
            "scope": "guild",
            "guild_server_id": "srv_b",
            "workload_id": "awlk_2",
            "is_primary": False,
            "stats_eligible": True,
        },
        {
            "id": "cagb_3",
            "scope": "guild",
            "guild_server_id": "srv_c",
            "workload_id": "awlk_3",
            "is_primary": True,
            "stats_eligible": False,
        },
        {
            "id": "cagb_p",
            "scope": "personal",
            "personal_server_id": "upsrv_1",
            "workload_id": "awlk_p",
            "is_primary": True,
            "stats_eligible": True,
        },
    ]
    eligible = cache.stats_eligible_bindings()
    assert len(eligible) == 1
    assert eligible[0]["guild_server_id"] == "srv_a"
    assert cache.primary_binding_for_server("srv_a") is not None
    assert cache.primary_binding_for_server("srv_b") is None


def test_build_score_batch_body_contract_shape() -> None:
    body = build_score_batch_body(
        agent_node_id="anode_1",
        deltas=[
            {
                "kind": "player.kill",
                "minecraft_name": "Steve",
                "minecraft_uuid": "u-1",
                "payload": {"victim_type": "minecraft:zombie", "tags": ["hostile"], "count": 3},
            }
        ],
        batch_id="scb_abc",
        batch_seq=3,
        session_fingerprint="fp-1",
        observed_at="2026-09-03T12:00:00Z",
        guild_id="gld_1",
        guild_server_id="srv_x",
        workload_id="awlk_1",
        binding_id="cagb_1",
        local_server_id="srv_x",
        agent_version="0.2.3",
        facet={
            "game_mode": "survival",
            "cheats": False,
            "difficulty": "hard",
            "pack": "bld_1",
            "minecraft_version": "1.20.1",
            "loader": "forge",
            "secret": "nope",
        },
    )
    assert body["schema_version"] == 1
    assert body["agent_node_id"] == "anode_1"
    assert body["workload_id"] == "awlk_1"
    assert body["binding"]["guild_id"] == "gld_1"
    assert body["binding"]["guild_server_id"] == "srv_x"
    integrity = body["integrity"]
    assert integrity["batch_id"] == "scb_abc"
    assert integrity["batch_seq"] == 3
    assert integrity["session_fingerprint"] == "fp-1"
    assert integrity["agent_version"] == "0.2.3"
    assert "secret" not in body["server_facet"]
    assert body["server_facet"]["game_mode"] == "survival"
    assert body["server_facet"]["pack_id"] == "bld_1"
    assert body["server_facet"]["loader"] == "forge"
    assert len(body["players"]) == 1
    player = body["players"][0]
    assert player["minecraft_name"] == "Steve"
    assert player["delta"]["kills"][0]["victim_type"] == "minecraft:zombie"
    assert player["delta"]["kills"][0]["count"] == 3


def test_aggregate_deltas_playtime_skips_afk() -> None:
    players = aggregate_deltas_to_players(
        [
            {
                "kind": "playtime",
                "minecraft_name": "Alex",
                "payload": {"playtime_seconds": 60, "afk": True},
            },
            {
                "kind": "playtime",
                "minecraft_name": "Alex",
                "payload": {"playtime_seconds": 120},
            },
        ]
    )
    assert players[0]["delta"]["playtime_seconds"] == 120


def test_event_to_delta_and_buffer() -> None:
    buf = ScoreDeltaBuffer()
    n = buf.enqueue_events(
        "local_1",
        [
            {
                "event_type": "player.died",
                "minecraft_name": "Alex",
                "minecraft_uuid": "u-1",
                "at": "2026-09-03T12:00:01Z",
            }
        ],
    )
    assert n == 1
    deltas, seq, fp = buf.drain("local_1")
    assert seq == 1
    assert fp
    assert deltas[0]["kind"] == "player.died"
    assert event_to_delta({"event_type": "x", "minecraft_name": "a"})["kind"] == "x"


def test_read_server_facet(tmp_path: Path) -> None:
    (tmp_path / "server.properties").write_text(
        "gamemode=creative\ndifficulty=easy\nenable-command-block=true\n",
        encoding="utf-8",
    )

    class Rec:
        path = tmp_path
        minecraft_version = "1.21"
        loader = "fabric"
        build_id = "bld_z"
        metadata = {}

    facet = read_server_facet(tmp_path, record=Rec())
    assert facet["game_mode"] == "creative"
    assert facet["difficulty"] == "easy"
    assert facet["cheats"] is True
    assert facet["minecraft_version"] == "1.21"
    assert facet["pack_id"] == "bld_z"


@pytest.mark.asyncio
async def test_post_score_batch_client_path() -> None:
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
    await client.post_score_batch(
        "cagt_x",
        agent_node_id="anode_1",
        deltas=[{"kind": "player.joined", "minecraft_name": "Steve"}],
        batch_id="scb_1",
        batch_seq=1,
        session_fingerprint="fp",
        observed_at="2026-09-03T12:00:00Z",
        guild_server_id="srv_1",
    )
    assert calls[0][0] == "POST"
    assert calls[0][1] == "/v1/agent/score/batch"
    assert calls[0][2]["agent_node_id"] == "anode_1"
    assert "players" in calls[0][2]
    assert "integrity" in calls[0][2]


@pytest.mark.asyncio
async def test_post_score_batch_cloud_error_status() -> None:
    client = CultForgeClient(CloudSection())

    async def boom(*args: Any, **kwargs: Any) -> dict[str, Any]:
        raise CloudError("forbidden", status_code=403)

    client._request = boom  # type: ignore[method-assign]
    with pytest.raises(CloudError) as ei:
        await client.post_score_batch(
            "cagt_x",
            agent_node_id="anode_1",
            deltas=[{"kind": "player.joined"}],
            batch_id="scb_1",
            batch_seq=1,
            session_fingerprint="fp",
            observed_at="2026-09-03T12:00:00Z",
        )
    assert ei.value.status_code == 403
