"""Default command handlers."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cultagent.config import parse_server_properties, render_server_properties, structured_view
from cultagent.guild.servers_view import guild_server_build_id
from cultagent.servers.install import jar_present

logger = logging.getLogger("cultagent.commands")

if TYPE_CHECKING:
    from cultagent.commands import CommandContext, CommandRegistry


def _server_id(ctx: CommandContext) -> str:
    raw = (
        ctx.params.get("local_server_id")
        or ctx.resource_id
        or ctx.params.get("server_id")
        or ctx.params.get("resource_id")
    )
    if not raw:
        raise ValueError("server_id required")
    requested = str(raw).strip()
    app = ctx.app
    if app is not None:
        known = app.servers.resolve_local_id(requested)
        if known:
            return known
        mapped = app.bindings.local_server_id_for(requested)
        if mapped:
            known = app.servers.resolve_local_id(mapped)
            return known or mapped
    return requested


async def node_status(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    return ctx.app.public_status()


async def node_metrics(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    return await ctx.app.metrics.collect()


async def server_list(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    servers = await ctx.app.servers.list_servers()
    return {"servers": [s.model_dump() for s in servers]}


def _chambered_build_id(ctx: CommandContext, record: Any) -> str | None:
    """Build id from the local record, then the bound cloud server row."""
    assert ctx.app is not None
    if record.build_id:
        return str(record.build_id)
    meta = record.metadata or {}
    for key in ("build_id", "guild_build_id", "published_build_id"):
        val = meta.get(key)
        if val:
            return str(val)
    cloud_id = str(
        meta.get("cloud_server_id")
        or meta.get("guild_server_id")
        or meta.get("personal_server_id")
        or record.server_id
    )
    for row in ctx.app.bindings.servers:
        rid = str(row.get("id") or row.get("server_id") or "")
        if rid == cloud_id:
            return guild_server_build_id(row)
    return None


async def server_status(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    status = await ctx.app.servers.status(_server_id(ctx))
    return status.model_dump()


async def server_start(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    server_id = _server_id(ctx)
    accept_eula = bool(ctx.params.get("accept_eula", False))
    record = await ctx.app.servers.get(server_id)
    if record is not None and not jar_present(record):
        bid = _chambered_build_id(ctx, record)
        if bid:
            logger.info(
                "Start: no jar on %s — installing build %s first",
                server_id,
                bid,
            )
            await ctx.app.builds.install_to_server(
                bid, server_id, accept_eula=True
            )
            accept_eula = True
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=server_id,
        operation="server.start",
    )
    return await ctx.app.servers.start(server_id, accept_eula=accept_eula)


async def server_stop(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    server_id = _server_id(ctx)
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=server_id,
        operation="server.stop",
    )
    return await ctx.app.servers.stop(server_id)


async def server_restart(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    server_id = _server_id(ctx)
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=server_id,
        operation="server.restart",
    )
    return await ctx.app.servers.restart(server_id)


async def server_console_read(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    limit = int(ctx.params.get("limit", 200))
    after_seq = int(ctx.params.get("after_seq", 0))
    return await ctx.app.servers.console_read(
        _server_id(ctx),
        limit=limit,
        after_seq=after_seq,
    )


async def server_console_execute(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    server_id = _server_id(ctx)
    command = ctx.params.get("command") or ctx.params.get("line")
    if not command:
        raise ValueError("command required")
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=server_id,
        operation="server.console.execute",
        extra={"command": str(command)[:200]},
    )
    return await ctx.app.servers.console_execute(server_id, str(command))


def _player_target(ctx: CommandContext) -> str:
    name = (
        ctx.params.get("minecraft_name")
        or ctx.params.get("player")
        or ctx.params.get("name")
        or ctx.params.get("user_id")
        or ctx.params.get("username")
    )
    if not name or not str(name).strip():
        raise ValueError("minecraft_name (or player/user_id) required")
    # Minecraft names: alphanumeric + underscore, ≤16 — reject injection
    text = str(name).strip()
    if not re.fullmatch(r"[A-Za-z0-9_]{1,16}", text):
        raise ValueError(f"invalid player name: {text!r}")
    return text


async def server_player_kick(ctx: CommandContext) -> dict[str, Any]:
    """Kick a player via console: ``kick <name> [reason]``."""
    assert ctx.app is not None
    server_id = _server_id(ctx)
    player = _player_target(ctx)
    reason = str(ctx.params.get("reason") or "").strip()
    # Strip control chars from reason; keep it as a single console arg
    reason = re.sub(r"[\r\n\x00]", " ", reason)[:120]
    line = f"kick {player}"
    if reason:
        line = f"kick {player} {reason}"
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=server_id,
        operation="server.player.kick",
        extra={"player": player, "reason": reason or None},
    )
    result = await ctx.app.servers.console_execute(server_id, line)
    return {"ok": True, "action": "kick", "player": player, "console": result}


async def server_player_ban(ctx: CommandContext) -> dict[str, Any]:
    """Ban a player via console: ``ban <name> [reason]`` (high-risk)."""
    assert ctx.app is not None
    server_id = _server_id(ctx)
    player = _player_target(ctx)
    reason = str(ctx.params.get("reason") or "").strip()
    reason = re.sub(r"[\r\n\x00]", " ", reason)[:120]
    line = f"ban {player}"
    if reason:
        line = f"ban {player} {reason}"
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=server_id,
        operation="server.player.ban",
        extra={"player": player, "reason": reason or None},
    )
    result = await ctx.app.servers.console_execute(server_id, line)
    return {"ok": True, "action": "ban", "player": player, "console": result}


async def server_config_read(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    server_id = _server_id(ctx)
    record = await ctx.app.servers.get(server_id)
    if record is None:
        raise KeyError(f"unknown server: {server_id}")
    props_path = Path(record.path) / "server.properties"
    if not props_path.is_file():
        return {"server_id": server_id, "properties": {}, "structured": {}}
    text = props_path.read_text(encoding="utf-8")
    props = parse_server_properties(text)
    return {
        "server_id": server_id,
        "properties": props,
        "structured": structured_view(props),
        "raw": text,
    }


async def server_config_update(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    from cultagent.config.live_apply import apply_config_to_running

    server_id = _server_id(ctx)
    updates = ctx.params.get("values") or ctx.params.get("properties")
    if not isinstance(updates, dict) or not updates:
        raise ValueError("values object required")
    record = await ctx.app.servers.get(server_id)
    if record is None:
        raise KeyError(f"unknown server: {server_id}")
    props_path = Path(record.path) / "server.properties"
    current = (
        parse_server_properties(props_path.read_text(encoding="utf-8"))
        if props_path.is_file()
        else {}
    )
    clean = {str(k): str(v) for k, v in updates.items()}
    merged = {**current, **clean}
    props_path.write_text(render_server_properties(merged), encoding="utf-8")
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=server_id,
        operation="server.config.update",
        extra={"keys": list(clean.keys())},
    )
    auto_restart = bool(ctx.params.get("auto_restart", True))
    live = await apply_config_to_running(
        ctx.app, server_id, clean, auto_restart=auto_restart
    )
    return {"server_id": server_id, "properties": merged, "live": live, **{k: live[k] for k in ("message", "restarted", "needs_restart", "applied_keys") if k in live}}


async def server_backup_create(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    server_id = _server_id(ctx)
    record = await ctx.app.servers.get(server_id)
    if record is None:
        raise KeyError(f"unknown server: {server_id}")
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=server_id,
        operation="server.backup.create",
    )
    return ctx.app.backups.create_backup(Path(record.path), server_id)


async def server_backup_restore(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    server_id = _server_id(ctx)
    backup_path = ctx.params.get("backup_path")
    if not backup_path:
        raise ValueError("backup_path required")
    confirm = bool(ctx.params.get("confirm", False))
    record = await ctx.app.servers.get(server_id)
    if record is None:
        raise KeyError(f"unknown server: {server_id}")
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=server_id,
        operation="server.backup.restore",
        extra={"confirm": confirm},
    )
    return ctx.app.backups.restore_backup(
        Path(str(backup_path)),
        Path(record.path),
        confirm=confirm,
    )


async def builds_list(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    limit = int(ctx.params.get("limit", 50))
    has_search = any(ctx.params.get(k) for k in ("q", "keywords", "loader", "minecraft_version"))
    if has_search:
        builds = await ctx.app.builds.search_builds(
            q=ctx.params.get("q"),
            keywords=ctx.params.get("keywords"),
            loader=ctx.params.get("loader"),
            minecraft_version=ctx.params.get("minecraft_version"),
            limit=limit,
            offset=int(ctx.params.get("offset", 0)),
        )
    else:
        builds = await ctx.app.builds.list_builds(limit=limit)
    return {"builds": builds, "count": len(builds)}


async def builds_manifest(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    build_id = ctx.params.get("build_id")
    if not build_id:
        raise ValueError("build_id required")
    manifest = await ctx.app.builds.get_manifest(str(build_id))
    check = await ctx.app.content.validate_cloud_manifest(manifest)
    # Attach compatibility for Rich CLI; keep file list intact.
    out = dict(manifest)
    out["compatibility"] = check
    return out


async def builds_provision(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    build_id = ctx.params.get("build_id")
    if not build_id:
        raise ValueError("build_id required")
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=str(build_id),
        operation="builds.provision",
    )
    existing_server = ctx.params.get("server_id") or ctx.params.get("local_server_id")
    if existing_server:
        return await ctx.app.builds.install_to_server(
            str(build_id),
            str(existing_server),
            include_optional=bool(ctx.params.get("include_optional", False)),
            install_platform=ctx.params.get("install_platform", True) is not False,
            force_platform=bool(ctx.params.get("force_platform", False)),
            accept_eula=ctx.params.get("accept_eula", True) is not False,
            loader_version=ctx.params.get("loader_version"),
        )
    return await ctx.app.builds.provision(
        str(build_id),
        create_local_server=bool(ctx.params.get("create_local_server", True)),
        install=bool(ctx.params.get("install", True)),
        desired_state=str(ctx.params.get("desired_state") or "stopped"),
        display_name=ctx.params.get("display_name"),
        include_optional=bool(ctx.params.get("include_optional", False)),
        network_mode=str(ctx.params.get("network_mode") or "direct"),
    )


async def builds_install(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    build_id = ctx.params.get("build_id")
    server_id = _server_id(ctx)
    if not build_id:
        raise ValueError("build_id required")
    return await ctx.app.builds.install_to_server(
        str(build_id),
        server_id,
        include_optional=bool(ctx.params.get("include_optional", False)),
        install_platform=ctx.params.get("install_platform", True) is not False,
        force_platform=bool(ctx.params.get("force_platform", False)),
        accept_eula=ctx.params.get("accept_eula", True) is not False,
        loader_version=ctx.params.get("loader_version"),
        resolve_deps=bool(ctx.params.get("resolve_deps", False)),
    )


async def server_refresh(ctx: CommandContext) -> dict[str, Any]:
    """Re-sync chambered build: install missing, prune extras, dedupe deps."""
    assert ctx.app is not None
    from cultagent.content.refresh import refresh_server_from_manifest

    server_id = _server_id(ctx)
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=server_id,
        operation="server.refresh",
    )
    return await refresh_server_from_manifest(
        app=ctx.app,
        server_id=server_id,
        build_id=str(ctx.params["build_id"]) if ctx.params.get("build_id") else None,
        include_optional=bool(ctx.params.get("include_optional", False)),
        prune=ctx.params.get("prune", True) is not False,
        resolve_deps=bool(ctx.params.get("resolve_deps", False)),
        install_platform=bool(ctx.params.get("install_platform", False)),
    )


async def builds_search(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    builds = await ctx.app.builds.search_builds(
        q=ctx.params.get("q"),
        keywords=ctx.params.get("keywords"),
        loader=ctx.params.get("loader"),
        minecraft_version=ctx.params.get("minecraft_version"),
        limit=int(ctx.params.get("limit", 50)),
        offset=int(ctx.params.get("offset", 0)),
    )
    return {"builds": builds, "count": len(builds)}


async def agent_bindings_list(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    token = ctx.app.identity_store.load_credentials().token
    if not token:
        raise ValueError("Agent not registered")
    identity = ctx.app.identity_store.load_identity()
    await ctx.app.bindings.refresh(
        ctx.app.cloud_client, token, identity=identity
    )
    return {
        "mode": ctx.app.bindings.mode,
        "bindings": ctx.app.bindings.active_bindings(),
        "servers": ctx.app.bindings.servers,
    }


async def agent_servers_list(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    from cultagent.cloud.bindings import agent_mode

    limit = int(ctx.params.get("limit", 100))
    identity = ctx.app.identity_store.load_identity()
    mode = agent_mode(identity)
    if mode == "personal":
        servers = await ctx.app.personal.list_bound_servers(limit=limit)
    else:
        servers = await ctx.app.guild.list_servers(limit=limit)
    return {"servers": servers, "count": len(servers), "mode": mode}


async def personal_servers_tunnel(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    server_id = ctx.params.get("server_id") or ctx.params.get("id")
    if not server_id:
        raise ValueError("server_id required (upsrv_…)")
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=str(server_id),
        operation="personal.servers.tunnel",
    )
    join = ctx.params.get("join") or ctx.params.get("endpoint")
    address = ctx.params.get("tunnel_address") or ctx.params.get("address")
    port = ctx.params.get("tunnel_port") or ctx.params.get("port")
    if join and not address:
        from cultagent.cloud.guild_payloads import split_join_address

        address, parsed_port = split_join_address(str(join))
        if port is None:
            port = parsed_port
    return await ctx.app.personal.report_tunnel(
        str(server_id),
        workload_id=ctx.params.get("workload_id"),
        tunnel_address=str(address) if address else None,
        tunnel_port=int(port) if port is not None else None,
        network_mode=ctx.params.get("network_mode"),
        clear_tunnel=bool(ctx.params.get("clear_tunnel") or ctx.params.get("clear")),
    )


async def personal_runtime_upsert(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    server_id = ctx.params.get("server_id") or ctx.params.get("id")
    workload_id = ctx.params.get("workload_id")
    if not server_id:
        raise ValueError("server_id required (upsrv_…)")
    if not workload_id:
        raise ValueError("workload_id required")
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=str(server_id),
        operation="personal.runtime.upsert",
    )
    return await ctx.app.personal.upsert_runtime(
        str(server_id),
        workload_id=str(workload_id),
        reported_state=ctx.params.get("reported_state") or ctx.params.get("state"),
        player_count=int(ctx.params["player_count"]) if ctx.params.get("player_count") is not None else None,
        max_players=int(ctx.params["max_players"]) if ctx.params.get("max_players") is not None else None,
        minecraft_version=ctx.params.get("minecraft_version"),
        tps=float(ctx.params["tps"]) if ctx.params.get("tps") is not None else None,
        mspt=float(ctx.params["mspt"]) if ctx.params.get("mspt") is not None else None,
        world=ctx.params.get("world") if isinstance(ctx.params.get("world"), dict) else None,
        include_tunnel=ctx.params.get("include_tunnel", True) is not False,
        clear_tunnel=bool(ctx.params.get("clear_tunnel") or ctx.params.get("clear")),
    )


async def guild_servers_list(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    limit = int(ctx.params.get("limit", 50))
    servers = await ctx.app.guild.list_servers(limit=limit)
    from cultagent.guild.servers_view import guild_server_label

    return {
        "servers": servers,
        "count": len(servers),
        "options": [guild_server_label(s) for s in servers],
    }


async def guild_servers_get(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    server_id = ctx.params.get("server_id") or ctx.params.get("id")
    if not server_id:
        raise ValueError("server_id required")
    server = await ctx.app.guild.get_server(str(server_id))
    return {"server": server}


async def server_clone(ctx: CommandContext) -> dict[str, Any]:
    """Clone a guild catalog server into a local CultAgent server dir."""
    assert ctx.app is not None
    guild_server_id = (
        ctx.params.get("guild_server_id")
        or ctx.params.get("server_id")
        or ctx.params.get("id")
    )
    if not guild_server_id:
        raise ValueError("guild_server_id required (or pass ? to list)")
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=str(guild_server_id),
        operation="server.clone",
    )
    port = ctx.params.get("port")
    return await ctx.app.guild.clone_server(
        str(guild_server_id),
        local_name=ctx.params.get("name"),
        download=ctx.params.get("download", True) is not False,
        accept_eula=ctx.params.get("accept_eula", True) is not False,
        port=int(port) if port is not None else None,
    )


async def server_remove(ctx: CommandContext) -> dict[str, Any]:
    """Remove a local server from the catalog (and optionally its files)."""
    assert ctx.app is not None
    server_id = _server_id(ctx)
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=server_id,
        operation="server.remove",
    )
    return await ctx.app.servers.remove(
        server_id,
        delete_files=ctx.params.get("delete_files", True) is not False,
        force_stop=ctx.params.get("force_stop", True) is not False,
    )


async def servers_tunnel(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    server_id = ctx.params.get("server_id") or ctx.params.get("id")
    if not server_id:
        raise ValueError("server_id required")
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=str(server_id),
        operation="servers.tunnel",
    )
    join = ctx.params.get("join") or ctx.params.get("endpoint")
    address = ctx.params.get("tunnel_address") or ctx.params.get("address")
    port = ctx.params.get("tunnel_port") or ctx.params.get("port")
    if join and not address:
        from cultagent.cloud.guild_payloads import split_join_address

        address, parsed_port = split_join_address(str(join))
        if port is None:
            port = parsed_port
    binding = ctx.app.bindings.binding_for_server(str(server_id))
    if binding and str(binding.get("scope") or "") == "personal":
        return await ctx.app.personal.report_tunnel(
            str(server_id),
            workload_id=ctx.params.get("workload_id") or binding.get("workload_id"),
            tunnel_address=str(address) if address else None,
            tunnel_port=int(port) if port is not None else None,
            network_mode=ctx.params.get("network_mode"),
            clear_tunnel=bool(ctx.params.get("clear_tunnel") or ctx.params.get("clear")),
        )
    return await ctx.app.guild.report_tunnel(
        str(server_id),
        workload_id=ctx.params.get("workload_id"),
        tunnel_address=str(address) if address else None,
        tunnel_port=int(port) if port is not None else None,
        network_mode=ctx.params.get("network_mode"),
        clear_tunnel=bool(ctx.params.get("clear_tunnel") or ctx.params.get("clear")),
    )


async def runtime_upsert(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    workload_id = ctx.params.get("workload_id")
    if not workload_id:
        raise ValueError("workload_id required")
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=str(workload_id),
        operation="runtime.upsert",
    )
    join = ctx.params.get("join") or ctx.params.get("endpoint")
    address = ctx.params.get("tunnel_address") or ctx.params.get("address")
    port = ctx.params.get("tunnel_port") or ctx.params.get("port")
    if join and not address:
        from cultagent.cloud.guild_payloads import split_join_address

        address, parsed_port = split_join_address(str(join))
        if port is None:
            port = parsed_port
    return await ctx.app.guild.upsert_runtime(
        workload_id=str(workload_id),
        state=ctx.params.get("state") or ctx.params.get("reported_state"),
        player_count=(
            int(ctx.params["player_count"])
            if ctx.params.get("player_count") is not None
            else None
        ),
        tunnel_address=str(address) if address else None,
        tunnel_port=int(port) if port is not None else None,
        network_mode=ctx.params.get("network_mode"),
        clear_tunnel=bool(ctx.params.get("clear_tunnel")),
        guild_server_id=ctx.params.get("guild_server_id") or ctx.params.get("server_id"),
        local_server_id=ctx.params.get("local_server_id"),
        include_tunnel=ctx.params.get("include_tunnel", True) is not False,
    )


async def guild_commands_schema(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    schema = await ctx.app.guild.commands_schema()
    return {"schema": schema}


async def server_mods_list(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    server_id = _server_id(ctx)
    record = await ctx.app.servers.get(server_id)
    if record is None:
        raise KeyError(f"unknown server: {server_id}")
    mods = await ctx.app.content.list_installed_mods(record.path)
    return {"server_id": server_id, "mods": mods}


async def server_mods_install(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    server_id = _server_id(ctx)
    project_id = ctx.params.get("project_id") or ctx.params.get("slug")
    if not project_id:
        raise ValueError("project_id (or slug) required")
    record = await ctx.app.servers.get(server_id)
    if record is None:
        raise KeyError(f"unknown server: {server_id}")
    loader = str(ctx.params.get("loader") or record.loader or "fabric")
    if loader == "vanilla":
        loader = "fabric"
    game_version = str(
        ctx.params.get("game_version") or record.minecraft_version or ""
    )
    if not game_version:
        raise ValueError("game_version required (or set minecraft_version on server)")
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=server_id,
        operation="server.mods.install",
        extra={"project_id": str(project_id)},
    )
    result = await ctx.app.content.install_mod(
        record.path,
        project_id=str(project_id),
        version_id=str(ctx.params["version_id"]) if ctx.params.get("version_id") else None,
        loader=loader,
        game_version=game_version,
        install_deps=ctx.params.get("install_deps", True) is not False
        and ctx.params.get("deps", True) is not False,
    )
    return {"server_id": server_id, **result}


async def server_mods_remove(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    server_id = _server_id(ctx)
    filename = ctx.params.get("filename") or ctx.params.get("name")
    if not filename:
        raise ValueError("filename required")
    record = await ctx.app.servers.get(server_id)
    if record is None:
        raise KeyError(f"unknown server: {server_id}")
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=server_id,
        operation="server.mods.remove",
        extra={"filename": str(filename)},
    )
    result = await ctx.app.content.remove_mod(record.path, str(filename))
    return {"server_id": server_id, **result}


async def server_mods_update(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    server_id = _server_id(ctx)
    filename = ctx.params.get("filename") or ctx.params.get("name")
    project_id = ctx.params.get("project_id") or ctx.params.get("slug")
    record = await ctx.app.servers.get(server_id)
    if record is None:
        raise KeyError(f"unknown server: {server_id}")
    loader = str(ctx.params.get("loader") or record.loader or "fabric")
    if loader == "vanilla":
        loader = "fabric"
    game_version = str(
        ctx.params.get("game_version") or record.minecraft_version or ""
    )
    if not game_version:
        raise ValueError("game_version required")
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=server_id,
        operation="server.mods.update",
        extra={"filename": filename, "project_id": project_id},
    )
    result = await ctx.app.content.update_mod(
        record.path,
        filename=str(filename) if filename else None,
        project_id=str(project_id) if project_id else None,
        loader=loader,
        game_version=game_version,
        install_deps=ctx.params.get("install_deps", True) is not False
        and ctx.params.get("deps", True) is not False,
    )
    return {"server_id": server_id, **result}


async def server_mods_resolve(ctx: CommandContext) -> dict[str, Any]:
    """Fill missing required Modrinth deps for jars already in mods/."""
    assert ctx.app is not None
    server_id = _server_id(ctx)
    record = await ctx.app.servers.get(server_id)
    if record is None:
        raise KeyError(f"unknown server: {server_id}")
    loader = str(ctx.params.get("loader") or record.loader or "forge")
    if loader == "vanilla":
        loader = "forge"
    game_version = str(
        ctx.params.get("game_version") or record.minecraft_version or ""
    )
    if not game_version:
        raise ValueError("game_version required (or set minecraft_version on server)")
    disable_client = ctx.params.get("disable_client_only", True) is not False
    source = str(ctx.params.get("source") or "auto")
    crash_path = ctx.params.get("crash_path") or ctx.params.get("log")
    also_scan = bool(ctx.params.get("full") or ctx.params.get("also_scan_jars"))
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=server_id,
        operation="server.mods.resolve",
        extra={"loader": loader, "game_version": game_version, "source": source},
    )
    result = await ctx.app.content.resolve_mod_dependencies(
        record.path,
        loader=loader,
        game_version=game_version,
        disable_client_only=disable_client,
        source=source,
        crash_path=str(crash_path) if crash_path else None,
        also_scan_jars=also_scan,
    )
    return {"server_id": server_id, **result}


async def server_mods_search(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    query = str(ctx.params.get("query") or ctx.params.get("q") or "").strip()
    if not query:
        raise ValueError("query required")
    data = await ctx.app.content.modrinth.search(
        query,
        limit=int(ctx.params.get("limit") or 20),
        offset=int(ctx.params.get("offset") or 0),
        project_type=str(ctx.params["project_type"]) if ctx.params.get("project_type") else "mod",
        loader=str(ctx.params["loader"]) if ctx.params.get("loader") else None,
        game_version=str(ctx.params["game_version"]) if ctx.params.get("game_version") else None,
    )
    return {"query": query, "hits": data.get("hits") or [], "total_hits": data.get("total_hits")}


async def server_mods_project(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    project_id = ctx.params.get("project_id") or ctx.params.get("slug")
    if not project_id:
        raise ValueError("project_id or slug required")
    project = await ctx.app.content.modrinth.project(str(project_id))
    return {"project": project}


async def server_mods_versions(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    project_id = ctx.params.get("project_id") or ctx.params.get("slug")
    if not project_id:
        raise ValueError("project_id or slug required")
    loader = str(ctx.params.get("loader") or "fabric")
    game_version = str(ctx.params.get("game_version") or "")
    if not game_version:
        raise ValueError("game_version required")
    versions = await ctx.app.content.modrinth.version_files(
        str(project_id), loader=loader, game_version=game_version
    )
    return {
        "project_id": project_id,
        "loader": loader,
        "game_version": game_version,
        "versions": versions,
    }


async def network_status(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    return await ctx.app.network.status()


async def network_restart(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=ctx.resource_id,
        operation="network.restart",
    )
    return await ctx.app.network.restart()


async def network_use(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    provider = str(ctx.params.get("provider") or "")
    config_params = {
        k: v
        for k, v in ctx.params.items()
        if k not in ("provider",) and v is not None
    }
    if not provider and not config_params:
        raise ValueError("provider required (direct|playit)")
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        operation="network.use",
        extra={"provider": provider} if provider else {},
    )
    if provider:
        ctx.app.network.use(provider)
    if config_params:
        await ctx.app.network.configure(config_params)
    return await ctx.app.network.status()


async def network_configure(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        operation="network.configure",
    )
    return await ctx.app.network.configure(dict(ctx.params))


async def playit_setup(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    await ctx.app.audit.record(actor_id=ctx.actor_id, operation="playit.setup")
    timeout = ctx.params.get("exchange_timeout")
    return await ctx.app.network.setup_playit(
        force=bool(ctx.params.get("force")),
        open_browser=ctx.params.get("open_browser", True) is not False,
        wait_exchange=ctx.params.get("wait_exchange", True) is not False,
        exchange_timeout=float(timeout) if timeout is not None else 300,
    )


async def playit_claim_wait(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    await ctx.app.audit.record(actor_id=ctx.actor_id, operation="playit.claim.wait")
    timeout = ctx.params.get("timeout", 300)
    return await ctx.app.network.wait_playit_claim(
        ctx.params.get("claim_code") or ctx.params.get("code"),
        timeout=float(timeout),
    )


async def playit_reset(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    await ctx.app.audit.record(actor_id=ctx.actor_id, operation="playit.reset")
    return await ctx.app.network.reset_playit()


async def playit_install(ctx: CommandContext) -> dict[str, Any]:
    """Deprecated alias — prefer playit.setup (download only, no browser)."""
    assert ctx.app is not None
    await ctx.app.audit.record(actor_id=ctx.actor_id, operation="playit.install")
    return await ctx.app.network.install_playit(force=bool(ctx.params.get("force")))


async def playit_start(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    await ctx.app.audit.record(actor_id=ctx.actor_id, operation="playit.start")
    result = await ctx.app.network.start_playit()
    if ctx.params.get("ensure_tunnel", True) is not False:
        try:
            tunnel = await ctx.app.network.ensure_playit_tunnel()
            result["tunnel"] = tunnel
        except Exception as exc:  # noqa: BLE001
            result["tunnel_error"] = str(exc)
    return result


async def playit_tunnel_ensure(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    await ctx.app.audit.record(actor_id=ctx.actor_id, operation="playit.tunnel.ensure")
    return await ctx.app.network.ensure_playit_tunnel()


async def playit_stop(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    await ctx.app.audit.record(actor_id=ctx.actor_id, operation="playit.stop")
    return await ctx.app.network.stop_playit()


async def playit_secret(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    secret = ctx.params.get("secret")
    if not secret:
        raise ValueError("secret required")
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        operation="playit.secret",
        result="ok",
    )
    return ctx.app.network.set_secret(str(secret))


async def playit_logs(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    limit = int(ctx.params.get("limit") or 80)
    return ctx.app.network.playit_logs(limit=limit)


async def _props_for_server(ctx: CommandContext, server_id: str) -> tuple[Any, dict[str, str], Path]:
    assert ctx.app is not None
    record = await ctx.app.servers.get(server_id)
    if record is None:
        raise KeyError(f"unknown server: {server_id}")
    props_path = Path(record.path) / "server.properties"
    current = (
        parse_server_properties(props_path.read_text(encoding="utf-8"))
        if props_path.is_file()
        else {}
    )
    return record, current, props_path


async def config_profile_list(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    name = ctx.params.get("name") or ctx.params.get("profile")
    if name:
        profile = ctx.app.profiles.load(str(name))
        return {"profile": profile.model_dump()}
    return {"profiles": ctx.app.profiles.list_profiles()}


async def config_profile_show(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    name = ctx.params.get("name") or ctx.params.get("profile")
    if not name:
        raise ValueError("name required")
    profile = ctx.app.profiles.load(str(name))
    return {"profile": profile.model_dump()}


async def config_profile_save(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    from cultagent.config import ConfigProfile

    name = ctx.params.get("name") or ctx.params.get("profile")
    values = ctx.params.get("values") or {}
    if not name:
        raise ValueError("name required")
    if not isinstance(values, dict):
        raise ValueError("values object required")
    profile = ConfigProfile(
        name=str(name),
        description=str(ctx.params.get("description") or ""),
        values={str(k): str(v) for k, v in values.items()},
        tags=list(ctx.params.get("tags") or []),
    )
    saved = ctx.app.profiles.save(profile)
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        operation="config.profile.save",
        extra={"name": saved.name, "keys": len(saved.values)},
    )
    return {"profile": saved.model_dump()}


async def config_profile_delete(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    name = ctx.params.get("name") or ctx.params.get("profile")
    if not name:
        raise ValueError("name required")
    ctx.app.profiles.delete(str(name))
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        operation="config.profile.delete",
        extra={"name": str(name)},
    )
    return {"ok": True, "deleted": str(name)}


async def config_profile_capture(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    name = ctx.params.get("name") or ctx.params.get("profile")
    if not name:
        raise ValueError("name required")
    server_id = _server_id(ctx)
    _, current, _ = await _props_for_server(ctx, server_id)
    profile = ctx.app.profiles.capture(
        str(name),
        current,
        description=str(ctx.params.get("description") or f"Captured from {server_id}"),
    )
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=server_id,
        operation="config.profile.capture",
        extra={"name": profile.name, "keys": len(profile.values)},
    )
    return {"profile": profile.model_dump(), "server_id": server_id}


async def config_profile_diff(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    name = ctx.params.get("name") or ctx.params.get("profile")
    if not name:
        raise ValueError("name required")
    server_id = _server_id(ctx)
    _, current, _ = await _props_for_server(ctx, server_id)
    profile = ctx.app.profiles.load(str(name))
    changes = ctx.app.profiles.diff(current, profile)
    return {
        "server_id": server_id,
        "profile": profile.name,
        "changes": changes,
        "change_count": len(changes),
    }


async def config_profile_apply(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    name = ctx.params.get("name") or ctx.params.get("profile")
    if not name:
        raise ValueError("name required")
    server_id = _server_id(ctx)
    dry_run = bool(ctx.params.get("dry_run", False))
    confirm = bool(ctx.params.get("confirm", False))
    mode = str(ctx.params.get("mode") or "merge")
    if mode not in {"merge", "replace"}:
        raise ValueError("mode must be merge or replace")
    _, current, props_path = await _props_for_server(ctx, server_id)
    profile = ctx.app.profiles.load(str(name))
    changes = ctx.app.profiles.diff(current, profile)
    if dry_run or not confirm:
        return {
            "server_id": server_id,
            "profile": profile.name,
            "dry_run": True,
            "mode": mode,
            "changes": changes,
            "change_count": len(changes),
            "applied": False,
            "note": "Pass confirm=true to write (or dry_run=true explicitly).",
        }
    merged = ctx.app.profiles.apply(current, profile, mode=mode)
    props_path.write_text(render_server_properties(merged), encoding="utf-8")
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        resource_id=server_id,
        operation="config.profile.apply",
        extra={"name": profile.name, "mode": mode, "changes": len(changes)},
    )
    return {
        "server_id": server_id,
        "profile": profile.name,
        "mode": mode,
        "changes": changes,
        "change_count": len(changes),
        "applied": True,
        "properties": merged,
    }


async def sidecar_list(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    return {"clients": ctx.app.sidecars.list_clients()}


async def sidecar_issue(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    from cultagent.sidecars import CHLOE_BOT_USER_ID

    name = str(ctx.params.get("name") or "chloe").strip().lower()
    role = str(ctx.params.get("role") or "chloe")
    actor_id = str(ctx.params.get("actor_id") or CHLOE_BOT_USER_ID)
    issued = ctx.app.sidecars.issue(
        name,
        actor_id=actor_id,
        role=role,
        authorizer=ctx.app.authorizer,
    )
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        operation="sidecar.issue",
        extra={"name": name, "role": role, "actor_id": actor_id},
    )
    return issued


async def sidecar_revoke(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    name = ctx.params.get("name")
    if not name:
        raise ValueError("name required")
    result = ctx.app.sidecars.revoke(str(name))
    await ctx.app.audit.record(
        actor_id=ctx.actor_id,
        operation="sidecar.revoke",
        extra={"name": str(name)},
    )
    return result


async def node_doctor(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    import platform
    import shutil

    from cultagent.servers.java import detect_java

    checks: list[dict[str, Any]] = []
    ok = True

    def add(name: str, passed: bool, detail: str, *, required: bool = True) -> None:
        nonlocal ok
        if required and not passed:
            ok = False
        checks.append(
            {
                "name": name,
                "ok": passed,
                "detail": detail,
                "required": required,
            }
        )

    bind = ctx.app.config.local.bind_host
    add(
        "loopback_bind",
        bind in {"127.0.0.1", "localhost", "::1"},
        f"bind_host={bind} (panel should stay loopback)",
    )
    java = detect_java(ctx.app.config.servers.java_path or None, min_major=17)
    any_java = detect_java(ctx.app.config.servers.java_path or None) if java is None else java
    add(
        "java",
        java is not None,
        (
            f"{java.path} ({java.version})"
            if java
            else (
                f"need Java 17+; found {any_java.path} ({any_java.version})"
                if any_java
                else "not found — install Temurin 17 or 21"
            )
        ),
    )
    identity = ctx.app.identity_store.load_identity()
    creds = ctx.app.identity_store.load_credentials()
    add(
        "identity",
        identity is not None,
        f"status={getattr(identity, 'status', None)}",
    )
    add(
        "credentials",
        bool(creds and creds.has_credentials),
        "agent token present" if creds and creds.has_credentials else "not logged in",
        required=False,
    )
    data_dir = ctx.app.paths.root
    add("data_dir", data_dir.is_dir(), str(data_dir))
    add("profiles_dir", ctx.app.paths.profiles_dir.is_dir(), str(ctx.app.paths.profiles_dir))
    playit_bin = ctx.app.network.playit.binary_path()
    profile = None
    try:
        from cultagent.network.playit import platform_profile

        profile = platform_profile()
    except Exception:  # noqa: BLE001
        profile = None
    add(
        "playit_binary",
        playit_bin is not None and playit_bin.is_file(),
        str(playit_bin)
        if playit_bin
        else (
            f"not installed — {'; '.join((profile or {}).get('install_methods') or ['see playit.gg/support/'])}"
        ),
        required=False,
    )
    if profile:
        add(
            "playit_platform",
            True,
            f"{profile.get('platform')} managed_download={profile.get('managed_download')}",
            required=False,
        )
    which = shutil.which("cf-agent")
    add(
        "cf_agent_on_path",
        which is not None,
        which or "use .venv Scripts/cf-agent",
        required=False,
    )
    add("platform", True, f"{platform.system()} {platform.machine()}")
    return {
        "ok": ok,
        "checks": checks,
        "version": ctx.app.public_status().get("version"),
        "product": "CultForge Agent",
    }


async def node_update_check(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    from cultagent.updates import check_for_update

    return await check_for_update()


async def node_update_apply(ctx: CommandContext) -> dict[str, Any]:
    assert ctx.app is not None
    from cultagent.updates import apply_update

    await ctx.app.audit.record(actor_id=ctx.actor_id, operation="node.update.apply")
    return await apply_update(
        force=bool(ctx.params.get("force", False)),
        restart=ctx.params.get("restart", True) is not False,
    )


def register_all(registry: CommandRegistry) -> None:
    registry.register("node.status", node_status)
    registry.register("node.metrics", node_metrics)
    registry.register("node.doctor", node_doctor)
    registry.register("node.update.check", node_update_check)
    registry.register("node.update.apply", node_update_apply)
    registry.register("server.list", server_list)
    registry.register("server.status", server_status)
    registry.register("server.start", server_start)
    registry.register("server.stop", server_stop)
    registry.register("server.restart", server_restart)
    registry.register("server.refresh", server_refresh)
    registry.register("server.console.read", server_console_read)
    registry.register("server.console.execute", server_console_execute)
    registry.register("server.player.kick", server_player_kick)
    registry.register("server.player.ban", server_player_ban)
    registry.register("server.config.read", server_config_read)
    registry.register("server.config.update", server_config_update)
    registry.register("server.backup.create", server_backup_create)
    registry.register("server.backup.restore", server_backup_restore)
    registry.register("server.mods.list", server_mods_list)
    registry.register("server.mods.install", server_mods_install)
    registry.register("server.mods.remove", server_mods_remove)
    registry.register("server.mods.update", server_mods_update)
    registry.register("server.mods.resolve", server_mods_resolve)
    registry.register("server.mods.search", server_mods_search)
    registry.register("server.mods.project", server_mods_project)
    registry.register("server.mods.versions", server_mods_versions)
    registry.register("builds.list", builds_list)
    registry.register("builds.manifest", builds_manifest)
    registry.register("builds.provision", builds_provision)
    registry.register("server.clone", server_clone)
    registry.register("server.remove", server_remove)
    registry.register("agent.bindings.list", agent_bindings_list)
    registry.register("agent.servers.list", agent_servers_list)
    registry.register("guild.servers.get", guild_servers_get)
    registry.register("servers.tunnel", servers_tunnel)
    registry.register("runtime.upsert", runtime_upsert)
    registry.register("network.status", network_status)
    registry.register("network.restart", network_restart)
    registry.register("network.use", network_use)
    registry.register("playit.setup", playit_setup)
    registry.register("playit.claim.wait", playit_claim_wait)
    registry.register("playit.reset", playit_reset)
    registry.register("playit.start", playit_start)
    registry.register("playit.stop", playit_stop)
    registry.register("playit.secret", playit_secret)
    registry.register("playit.logs", playit_logs)
    registry.register("config.profile.list", config_profile_list)
    registry.register("config.profile.save", config_profile_save)
    registry.register("config.profile.delete", config_profile_delete)
    registry.register("config.profile.capture", config_profile_capture)
    registry.register("config.profile.apply", config_profile_apply)
    registry.register("sidecar.list", sidecar_list)
    registry.register("sidecar.issue", sidecar_issue)
    registry.register("sidecar.revoke", sidecar_revoke)
