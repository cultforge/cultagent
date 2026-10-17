"""Build CultForge guild agent payloads (CONTEXT contract).

Caps (server-side):
  presence ≤ 200, stats batch ≤ 100, events batch ≤ 50,
  event payload ≤ 8KB, world meta ≤ 4KB.
"""

from __future__ import annotations

import json
from typing import Any

MAX_PLAYERS = 200
MAX_STATS = 100
MAX_EVENTS = 50
MAX_SCORE_DELTAS = 100
MAX_EVENT_PAYLOAD_BYTES = 8 * 1024
MAX_WORLD_META_BYTES = 4 * 1024


def split_join_address(value: str) -> tuple[str, int | None]:
    """Split ``host``, ``host:port``, or ``[ipv6]:port`` → (host, port|None)."""
    raw = (value or "").strip()
    if not raw:
        return "", None
    if raw.startswith("[") and "]:" in raw:
        host, _, port_s = raw[1:].partition("]:")
        try:
            return host, int(port_s) if port_s else None
        except ValueError:
            return host, None
    # Only treat as host:port when a single colon and numeric port
    # (avoid mangling IPv6 without brackets).
    if raw.count(":") == 1:
        host, _, port_s = raw.partition(":")
        if port_s.isdigit():
            return host, int(port_s)
    return raw, None


def _cap_json(obj: Any, max_bytes: int) -> Any:
    raw = json.dumps(obj, separators=(",", ":"), default=str)
    if len(raw.encode("utf-8")) <= max_bytes:
        return obj
    if isinstance(obj, dict):
        return {"_truncated": True, "keys": list(obj.keys())[:20]}
    return {"_truncated": True}


def build_tunnel_body(
    *,
    workload_id: str | None = None,
    tunnel_address: str | None = None,
    tunnel_port: int | None = None,
    network_mode: str | None = None,
    clear_tunnel: bool = False,
    tunnel_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST /v1/agent/guild/servers/{server_id}/tunnel body."""
    body: dict[str, Any] = {}
    if workload_id:
        body["workload_id"] = str(workload_id)
    if clear_tunnel:
        body["clear_tunnel"] = True
        body["network_mode"] = network_mode or "direct"
        return body
    if tunnel_address:
        body["tunnel_address"] = str(tunnel_address)
    if tunnel_port is not None:
        body["tunnel_port"] = int(tunnel_port)
    if network_mode:
        body["network_mode"] = str(network_mode)
    elif tunnel_address:
        body["network_mode"] = "playit"
    if tunnel_meta:
        # Never include secrets
        safe = {
            k: v
            for k, v in tunnel_meta.items()
            if k.lower() not in {"secret", "secret_key", "token", "agent_key", "password"}
        }
        if safe:
            body["tunnel_meta"] = safe
    return body


def build_runtime_body(
    *,
    workload_id: str,
    state: str | None = None,
    player_count: int | None = None,
    tps: float | None = None,
    mspt: float | None = None,
    world: dict[str, Any] | None = None,
    tunnel_address: str | None = None,
    tunnel_port: int | None = None,
    network_mode: str | None = None,
    clear_tunnel: bool = False,
    guild_server_id: str | None = None,
    local_server_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST /v1/agent/guild/runtime — snapshot (+ optional tunnel fold-in)."""
    if not workload_id or not str(workload_id).strip():
        raise ValueError("workload_id required")
    body: dict[str, Any] = {"workload_id": str(workload_id).strip()}
    if state is not None:
        body["state"] = str(state)
    if player_count is not None:
        body["player_count"] = int(player_count)
    if tps is not None:
        body["tps"] = float(tps)
    if mspt is not None:
        body["mspt"] = float(mspt)
    if world is not None:
        body["world"] = _cap_json(world, MAX_WORLD_META_BYTES)
    if guild_server_id:
        body["guild_server_id"] = str(guild_server_id)
    if local_server_id:
        body["local_server_id"] = str(local_server_id)
    # Optional tunnel fold-in (same fields as dedicated tunnel route)
    if clear_tunnel:
        body["clear_tunnel"] = True
        body["network_mode"] = network_mode or "direct"
    else:
        if tunnel_address:
            body["tunnel_address"] = str(tunnel_address)
        if tunnel_port is not None:
            body["tunnel_port"] = int(tunnel_port)
        if network_mode:
            body["network_mode"] = str(network_mode)
        elif tunnel_address:
            body["network_mode"] = "playit"
    if extra:
        for k, v in extra.items():
            if k not in body and v is not None:
                body[k] = v
    return body


def build_players_body(
    *,
    workload_id: str,
    players: list[dict[str, Any]],
) -> dict[str, Any]:
    """POST /v1/agent/guild/players — replace-all roster (≤200)."""
    if not workload_id or not str(workload_id).strip():
        raise ValueError("workload_id required")
    capped = list(players)[:MAX_PLAYERS]
    return {
        "workload_id": str(workload_id).strip(),
        "players": capped,
    }


def build_stats_body(*, stats: list[dict[str, Any]]) -> dict[str, Any]:
    """POST /v1/agent/guild/stats — batch upsert by minecraft_uuid (≤100)."""
    return {"stats": list(stats)[:MAX_STATS]}


def normalize_server_facet(facet: dict[str, Any] | None) -> dict[str, Any]:
    """Canonical ``server_facet`` for runtime + score batches."""
    if not facet:
        return {}
    out: dict[str, Any] = {}
    mapping = {
        "game_mode": "game_mode",
        "cheats": "cheats",
        "difficulty": "difficulty",
        "minecraft_version": "minecraft_version",
        "loader": "loader",
        "pack_id": "pack_id",
        "pack": "pack_id",  # legacy alias
    }
    for src, dest in mapping.items():
        if src in facet and facet[src] is not None and dest not in out:
            out[dest] = facet[src]
    return out


def build_score_batch_body(
    *,
    agent_node_id: str,
    batch_id: str,
    batch_seq: int,
    session_fingerprint: str,
    observed_at: str,
    players: list[dict[str, Any]] | None = None,
    deltas: list[dict[str, Any]] | None = None,
    guild_server_id: str | None = None,
    personal_server_id: str | None = None,
    guild_id: str | None = None,
    workload_id: str | None = None,
    binding_id: str | None = None,
    local_server_id: str | None = None,
    server_facet: dict[str, Any] | None = None,
    facet: dict[str, Any] | None = None,
    agent_version: str | None = None,
    schema_version: int = 1,
) -> dict[str, Any]:
    """POST /v1/agent/score/batch — raw competitive deltas (API owns formula).

    Prefer ``players[].delta`` (contract sketch). Legacy flat ``deltas`` are
    accepted and aggregated into players when ``players`` is omitted.
    """
    from cultagent.cloud.scoring import aggregate_deltas_to_players

    facet_norm = normalize_server_facet(server_facet or facet)
    player_rows = list(players) if players is not None else aggregate_deltas_to_players(
        list(deltas or [])
    )
    player_rows = player_rows[:MAX_SCORE_DELTAS]

    binding: dict[str, Any] = {}
    if guild_id:
        binding["guild_id"] = str(guild_id)
    if guild_server_id:
        binding["guild_server_id"] = str(guild_server_id)
    if personal_server_id:
        binding["personal_server_id"] = str(personal_server_id)
    if binding_id:
        binding["binding_id"] = str(binding_id)
    if local_server_id:
        binding["local_server_id"] = str(local_server_id)

    integrity: dict[str, Any] = {
        "batch_id": str(batch_id),
        "batch_seq": int(batch_seq),
        "observed_at": str(observed_at),
        "session_fingerprint": str(session_fingerprint),
    }
    if agent_version:
        integrity["agent_version"] = str(agent_version)

    body: dict[str, Any] = {
        "schema_version": int(schema_version),
        "agent_node_id": str(agent_node_id),
        "integrity": integrity,
        "server_facet": facet_norm,
        "players": player_rows,
    }
    if workload_id:
        body["workload_id"] = str(workload_id)
    if binding:
        body["binding"] = binding
    # Flat aliases for older API readers
    if guild_server_id:
        body["guild_server_id"] = str(guild_server_id)
    if personal_server_id:
        body["personal_server_id"] = str(personal_server_id)
    return body


def build_events_body(*, events: list[dict[str, Any]]) -> dict[str, Any]:
    """POST /v1/agent/guild/events — append-only batch (≤50, payload ≤8KB)."""
    out: list[dict[str, Any]] = []
    for ev in list(events)[:MAX_EVENTS]:
        if not isinstance(ev, dict):
            continue
        item = dict(ev)
        if "payload" in item:
            item["payload"] = _cap_json(item["payload"], MAX_EVENT_PAYLOAD_BYTES)
        out.append(item)
    return {"events": out}


# R.md §4 session_stats allowlist — never invent competitive score totals here.
LIVE_SESSION_STAT_KEYS = frozenset(
    {
        "blocks_mined",
        "blocks_placed",
        "distance_m",
        "deaths",
        "kills_mobs",
        "kills_players",
        "playtime_seconds",
        "xp_gained",
        "items_crafted",
    }
)


def _normalize_live_player(row: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(row, dict):
        return None
    name = str(row.get("minecraft_name") or row.get("name") or "").strip()
    uuid_val = str(row.get("minecraft_uuid") or row.get("uuid") or "").strip()
    if not name and not uuid_val:
        return None
    out: dict[str, Any] = {}
    if name:
        out["minecraft_name"] = name
    if uuid_val:
        out["minecraft_uuid"] = uuid_val
    for key in (
        "ping_ms",
        "gamemode",
        "dimension",
        "health",
        "food",
    ):
        if row.get(key) is not None:
            out[key] = row[key]
    pos = row.get("position")
    if isinstance(pos, dict):
        clean_pos: dict[str, Any] = {}
        for axis in ("x", "y", "z", "yaw", "pitch"):
            if pos.get(axis) is not None:
                try:
                    clean_pos[axis] = float(pos[axis])
                except (TypeError, ValueError):
                    pass
        if clean_pos:
            out["position"] = clean_pos
    stats = row.get("session_stats")
    if isinstance(stats, dict):
        clean_stats = {
            k: int(stats[k])
            for k in LIVE_SESSION_STAT_KEYS
            if k in stats and stats[k] is not None
        }
        if clean_stats:
            out["session_stats"] = clean_stats
    return out


def build_live_body(
    *,
    workload_id: str,
    reported_state: str,
    guild_server_id: str | None = None,
    personal_server_id: str | None = None,
    minecraft_version: str | None = None,
    player_count: int | None = None,
    max_players: int | None = None,
    tps: float | None = None,
    mspt: float | None = None,
    world: dict[str, Any] | None = None,
    server_facet: dict[str, Any] | None = None,
    players: list[dict[str, Any]] | None = None,
    events: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """POST /v1/agent/guild/live or personal …/live — Aternos-style snapshot.

    Competitive score totals belong on score/batch, not here.
    """
    if not workload_id or not str(workload_id).strip():
        raise ValueError("workload_id required")
    body: dict[str, Any] = {
        "workload_id": str(workload_id).strip(),
        "reported_state": str(reported_state or "unknown"),
        "server_facet": normalize_server_facet(server_facet),
    }
    if guild_server_id:
        body["guild_server_id"] = str(guild_server_id)
    if personal_server_id:
        body["personal_server_id"] = str(personal_server_id)
    if minecraft_version:
        body["minecraft_version"] = str(minecraft_version)
    if player_count is not None:
        body["player_count"] = int(player_count)
    elif players is not None:
        body["player_count"] = len(players)
    else:
        body["player_count"] = 0
    if max_players is not None:
        body["max_players"] = int(max_players)
    if tps is not None:
        body["tps"] = float(tps)
    if mspt is not None:
        body["mspt"] = float(mspt)
    if world is not None:
        body["world"] = _cap_json(world, MAX_WORLD_META_BYTES)

    live_players: list[dict[str, Any]] = []
    for row in list(players or [])[:MAX_PLAYERS]:
        normalized = _normalize_live_player(row)
        if normalized:
            live_players.append(normalized)
    body["players"] = live_players

    live_events: list[dict[str, Any]] = []
    for ev in list(events or [])[:MAX_EVENTS]:
        if not isinstance(ev, dict):
            continue
        item = dict(ev)
        if "payload" in item:
            item["payload"] = _cap_json(item["payload"], MAX_EVENT_PAYLOAD_BYTES)
        live_events.append(item)
    if live_events:
        body["events"] = live_events
    return body


def build_personal_runtime_body(
    *,
    workload_id: str,
    reported_state: str | None = None,
    player_count: int | None = None,
    max_players: int | None = None,
    minecraft_version: str | None = None,
    tps: float | None = None,
    mspt: float | None = None,
    world: dict[str, Any] | None = None,
    tunnel_address: str | None = None,
    tunnel_port: int | None = None,
    network_mode: str | None = None,
    clear_tunnel: bool = False,
    raw_public: dict[str, Any] | None = None,
    server_facet: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """POST /v1/agent/personal/servers/{server_id}/runtime body."""
    if not workload_id or not str(workload_id).strip():
        raise ValueError("workload_id required")
    body: dict[str, Any] = {"workload_id": str(workload_id).strip()}
    if reported_state is not None:
        body["reported_state"] = str(reported_state)
    if player_count is not None:
        body["player_count"] = int(player_count)
    if max_players is not None:
        body["max_players"] = int(max_players)
    if minecraft_version:
        body["minecraft_version"] = str(minecraft_version)
    if tps is not None:
        body["tps"] = float(tps)
    if mspt is not None:
        body["mspt"] = float(mspt)
    if world is not None:
        body["world"] = _cap_json(world, MAX_WORLD_META_BYTES)
    if raw_public:
        body["raw_public"] = _cap_json(raw_public, MAX_EVENT_PAYLOAD_BYTES)
    body["server_facet"] = normalize_server_facet(server_facet)
    if clear_tunnel:
        body["clear_tunnel"] = True
        body["network_mode"] = network_mode or "direct"
    else:
        if tunnel_address:
            body["tunnel_address"] = str(tunnel_address)
        if tunnel_port is not None:
            body["tunnel_port"] = int(tunnel_port)
        if network_mode:
            body["network_mode"] = str(network_mode)
        elif tunnel_address:
            body["network_mode"] = "playit"
    return body
