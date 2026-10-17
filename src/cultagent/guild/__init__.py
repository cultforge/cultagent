"""Guild cloud surfaces — servers, tunnel override, runtime (CONTEXT contract)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from cultagent.cloud.client import CloudError
from cultagent.cloud.guild_payloads import split_join_address
from cultagent.guild.servers_view import (
    extract_clone_spec,
    guild_server_build_id,
    guild_server_id,
    guild_server_label,
    summarize_chambered_build,
)

if TYPE_CHECKING:
    from cultagent.app import CultAgentApp

logger = logging.getLogger("cultagent.guild")


class GuildOrchestrator:
    """Agent-side guild HTTP: servers, tunnel override, runtime, presence, events."""

    def __init__(self, app: CultAgentApp) -> None:
        self.app = app

    def _token(self) -> str:
        token = self.app.identity_store.load_credentials().token
        if not token:
            raise CloudError("Agent not registered — run cf-agent login first")
        return token

    def _unwrap(self, payload: dict[str, Any]) -> Any:
        data = payload.get("data")
        return data if data is not None else payload

    async def _public_join_parts(self) -> tuple[str | None, int | None]:
        net = await self.app.network.status()
        join = net.get("public_join") or net.get("public_endpoint")
        if not join:
            return None, None
        host, port = split_join_address(str(join))
        return (host or None), port

    async def list_servers(self, *, limit: int = 50) -> list[dict[str, Any]]:
        payload = await self.app.cloud_client.list_guild_servers(
            self._token(), limit=limit
        )
        data = self._unwrap(payload)
        if isinstance(data, list):
            return [s if isinstance(s, dict) else {} for s in data]
        if isinstance(data, dict):
            for key in ("servers", "items", "results"):
                items = data.get(key)
                if isinstance(items, list):
                    return [s if isinstance(s, dict) else {} for s in items]
        return []

    async def get_server(self, server_id: str) -> dict[str, Any]:
        payload = await self.app.cloud_client.get_guild_server(
            self._token(), server_id
        )
        data = self._unwrap(payload)
        if not isinstance(data, dict):
            raise CloudError("Invalid guild server response")
        return data

    async def resolve_server(self, server_id: str) -> dict[str, Any]:
        """Fetch one guild server; fall back to list match if get fails."""
        try:
            return await self.get_server(server_id)
        except CloudError:
            for row in await self.list_servers(limit=100):
                if guild_server_id(row) == server_id:
                    return row
            raise

    async def clone_server(
        self,
        guild_server_id: str,
        *,
        local_name: str | None = None,
        download: bool = True,
        accept_eula: bool = True,
        port: int | None = None,
    ) -> dict[str, Any]:
        """Create a local server dir from a guild catalog server (load the magazine).

        When the guild row has ``build_id``, loader/MC come from that build (and its
        install manifest). Files are not installed here — that is ``cf-agent build``
        (shoot / chamber → install).
        """
        remote = await self.resolve_server(guild_server_id)
        bid = guild_server_build_id(remote)
        build_row: dict[str, Any] | None = None
        manifest: dict[str, Any] | None = None
        if bid:
            try:
                build_row = await self.app.builds.find_build(bid)
            except CloudError as exc:
                logger.warning("clone: could not list builds for %s: %s", bid, exc)
            try:
                manifest = await self.app.builds.get_manifest(bid)
            except CloudError as exc:
                logger.warning("clone: could not fetch manifest for %s: %s", bid, exc)

        spec = extract_clone_spec(remote, build=build_row, manifest=manifest)
        if not spec["guild_server_id"]:
            raise CloudError("Guild server payload missing id")
        name = local_name or str(spec["name"])
        loader = str(spec["loader"] or "vanilla")
        version = spec.get("minecraft_version")
        local_port = int(port if port is not None else spec["port"])
        # Chambered build: do not jar-download on clone — `cf-agent build` installs.
        # Bare clone (no build): optional jar download when MC version is known.
        chambered = bool(bid)
        do_download = bool(download and version and not chambered)

        record = await self.app.servers.create(
            name,
            minecraft_version=str(version) if version else None,
            loader=loader,
            port=local_port,
            accept_eula=accept_eula,
            download_jar=do_download,
            server_id=str(spec["guild_server_id"]),
        )
        chamber = None
        if bid:
            chamber = summarize_chambered_build(
                build_id=bid, build=build_row, manifest=manifest
            )
            record.build_id = bid
            # Prefer chamber loader/mc on the record (build is source of truth).
            if chamber.get("loader"):
                record.loader = str(chamber["loader"])
            if chamber.get("minecraft_version"):
                record.minecraft_version = str(chamber["minecraft_version"])

        record.metadata = {
            **(record.metadata or {}),
            "scope": "guild",
            "guild_server_id": spec["guild_server_id"],
            "cloned_from": "guild",
            "configured_address": spec.get("configured_address"),
            "configured_port": spec.get("configured_port"),
            "effective_address": spec.get("effective_address"),
            "effective_port": spec.get("effective_port"),
            "address_source": spec.get("address_source"),
            "tunnel_address": spec.get("tunnel_address"),
            "tunnel_port": spec.get("tunnel_port"),
            "join": spec.get("join"),
            "build_id": bid,
            "build_name": (chamber or {}).get("name") or spec.get("build_name"),
            "chambered": chambered,
        }
        await self.app.servers.update_record(record)

        next_hint = (
            f"cf-agent build {record.server_id}"
            if chambered
            else "cf-agent server-install"
        )
        return {
            "ok": True,
            "cloned": True,
            "chambered": chambered,
            "guild_server_id": spec["guild_server_id"],
            "local_server_id": record.server_id,
            "name": record.name,
            "loader": record.loader,
            "minecraft_version": record.minecraft_version,
            "port": record.port,
            "path": record.path,
            "join": spec.get("join"),
            "downloaded": do_download,
            "build_id": bid,
            "build": chamber,
            "next": next_hint,
            "label": guild_server_label(
                remote,
                builds_by_id={bid: build_row} if bid and build_row else None,
            ),
        }

    def _require_primary_for_tunnel(self, server_id: str) -> dict[str, Any] | None:
        """Return binding if this node is primary; skip (no API call) otherwise."""
        binding = self.app.bindings.binding_for_server(server_id)
        if binding is None:
            # No binding cache hit — let API decide (legacy / first sync)
            return None
        if not self.app.bindings.is_primary_binding(binding):
            raise CloudError(
                "skip tunnel: this agent is not the primary binding for "
                f"{server_id} (avoids 403 standby spam)",
                status_code=403,
            )
        return binding

    async def report_tunnel(
        self,
        server_id: str,
        *,
        workload_id: str | None = None,
        tunnel_address: str | None = None,
        tunnel_port: int | None = None,
        network_mode: str | None = None,
        clear_tunnel: bool = False,
        tunnel_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST tunnel override — body uses tunnel_address / tunnel_port (not endpoint URL)."""
        try:
            binding = self._require_primary_for_tunnel(server_id)
        except CloudError as exc:
            if exc.status_code == 403 and "not the primary" in str(exc):
                logger.info("%s", exc)
                return {
                    "ok": True,
                    "skipped": True,
                    "reason": "not_primary",
                    "server_id": server_id,
                }
            raise
        address = tunnel_address
        port = tunnel_port
        mode = network_mode
        if binding and not workload_id:
            workload_id = binding.get("workload_id")

        if clear_tunnel:
            payload = await self.app.cloud_client.set_guild_server_tunnel(
                self._token(),
                server_id,
                workload_id=workload_id,
                clear_tunnel=True,
                network_mode=mode or "direct",
            )
            return {
                "ok": True,
                "server_id": server_id,
                "clear_tunnel": True,
                "response": self._unwrap(payload),
            }

        if not address:
            address, port = await self._public_join_parts()
        if not address:
            raise CloudError(
                "No tunnel_address — run cf-agent playit-start first, "
                "or pass --address / --join"
            )
        if mode is None:
            mode = "playit"
        meta = tunnel_meta or {"provider": mode}
        payload = await self.app.cloud_client.set_guild_server_tunnel(
            self._token(),
            server_id,
            workload_id=workload_id,
            tunnel_address=address,
            tunnel_port=port,
            network_mode=mode,
            tunnel_meta=meta,
        )
        return {
            "ok": True,
            "server_id": server_id,
            "workload_id": workload_id,
            "tunnel_address": address,
            "tunnel_port": port,
            "network_mode": mode,
            "response": self._unwrap(payload),
        }

    async def upsert_runtime(
        self,
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
        include_tunnel: bool = True,
    ) -> dict[str, Any]:
        address = tunnel_address
        port = tunnel_port
        mode = network_mode
        if include_tunnel and not clear_tunnel and not address:
            address, port = await self._public_join_parts()
            if address and mode is None:
                mode = "playit"
        if clear_tunnel:
            mode = mode or "direct"
        payload = await self.app.cloud_client.upsert_guild_runtime(
            self._token(),
            workload_id=workload_id,
            state=state,
            player_count=player_count,
            tps=tps,
            mspt=mspt,
            world=world,
            tunnel_address=address,
            tunnel_port=port,
            network_mode=mode,
            clear_tunnel=clear_tunnel,
            guild_server_id=guild_server_id,
            local_server_id=local_server_id,
        )
        return {
            "ok": True,
            "workload_id": workload_id,
            "tunnel_address": address,
            "tunnel_port": port,
            "response": self._unwrap(payload),
        }

    async def replace_players(
        self, *, workload_id: str, players: list[dict[str, Any]]
    ) -> dict[str, Any]:
        payload = await self.app.cloud_client.replace_guild_players(
            self._token(), workload_id=workload_id, players=players
        )
        return {"ok": True, "response": self._unwrap(payload)}

    async def append_events(self, *, events: list[dict[str, Any]]) -> dict[str, Any]:
        payload = await self.app.cloud_client.append_guild_events(
            self._token(), events=events
        )
        return {"ok": True, "response": self._unwrap(payload)}

    async def upsert_stats(self, *, stats: list[dict[str, Any]]) -> dict[str, Any]:
        payload = await self.app.cloud_client.upsert_guild_stats(
            self._token(), stats=stats
        )
        return {"ok": True, "response": self._unwrap(payload)}

    async def commands_schema(self) -> dict[str, Any]:
        payload = await self.app.cloud_client.get_agent_commands_schema(self._token())
        data = self._unwrap(payload)
        return data if isinstance(data, dict) else {"raw": data}
