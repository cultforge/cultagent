"""Personal-mode cloud panel — tunnel/runtime for bound personal servers."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from cultagent.cloud.client import CloudError
from cultagent.cloud.guild_payloads import split_join_address

if TYPE_CHECKING:
    from cultagent.app import CultAgentApp

logger = logging.getLogger("cultagent.personal")


class PersonalOrchestrator:
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

    def _require_personal_mode(self) -> None:
        identity = self.app.identity_store.load_identity()
        if identity and identity.guild_id:
            raise CloudError(
                "This agent is guild-attached — use guild routes, not personal"
            )

    def _require_bound(self, server_id: str) -> dict[str, Any]:
        binding = self.app.bindings.binding_for_server(server_id)
        if binding is None:
            raise CloudError(
                f"No active binding for personal server {server_id} — bind in launcher"
            )
        if str(binding.get("scope") or "") != "personal":
            raise CloudError(f"Server {server_id} is not a personal binding")
        return binding

    async def _public_join_parts(self) -> tuple[str | None, int | None]:
        net = await self.app.network.status()
        join = net.get("public_join") or net.get("public_endpoint")
        if not join:
            return None, None
        host, port = split_join_address(str(join))
        return (host or None), port

    async def list_bound_servers(self, *, limit: int = 100) -> list[dict[str, Any]]:
        self._require_personal_mode()
        payload = await self.app.cloud_client.list_agent_servers(
            self._token(), limit=limit
        )
        data = self._unwrap(payload)
        if isinstance(data, list):
            return [s if isinstance(s, dict) else {} for s in data]
        return []

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
        self._require_personal_mode()
        binding = self._require_bound(server_id)
        wl = workload_id or binding.get("workload_id")

        if clear_tunnel:
            payload = await self.app.cloud_client.set_personal_server_tunnel(
                self._token(),
                server_id,
                workload_id=str(wl) if wl else None,
                clear_tunnel=True,
                network_mode=network_mode or "direct",
            )
            return {
                "ok": True,
                "server_id": server_id,
                "scope": "personal",
                "clear_tunnel": True,
                "response": self._unwrap(payload),
            }

        address = tunnel_address
        port = tunnel_port
        mode = network_mode
        if not address:
            address, port = await self._public_join_parts()
        if not address:
            raise CloudError(
                "No tunnel_address — run cf-agent playit-start first, or pass --address"
            )
        if mode is None:
            mode = "playit"
        meta = tunnel_meta or {"provider": mode}
        payload = await self.app.cloud_client.set_personal_server_tunnel(
            self._token(),
            server_id,
            workload_id=str(wl) if wl else None,
            tunnel_address=address,
            tunnel_port=port,
            network_mode=mode,
            tunnel_meta=meta,
        )
        return {
            "ok": True,
            "server_id": server_id,
            "scope": "personal",
            "workload_id": wl,
            "tunnel_address": address,
            "tunnel_port": port,
            "network_mode": mode,
            "response": self._unwrap(payload),
        }

    async def upsert_runtime(
        self,
        server_id: str,
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
        include_tunnel: bool = True,
    ) -> dict[str, Any]:
        self._require_personal_mode()
        self._require_bound(server_id)
        address = tunnel_address
        port = tunnel_port
        mode = network_mode
        if include_tunnel and not clear_tunnel and not address:
            address, port = await self._public_join_parts()
            if address and mode is None:
                mode = "playit"
        if clear_tunnel:
            mode = mode or "direct"
        payload = await self.app.cloud_client.upsert_personal_runtime(
            self._token(),
            server_id,
            workload_id=workload_id,
            reported_state=reported_state,
            player_count=player_count,
            max_players=max_players,
            minecraft_version=minecraft_version,
            tps=tps,
            mspt=mspt,
            world=world,
            tunnel_address=address,
            tunnel_port=port,
            network_mode=mode,
            clear_tunnel=clear_tunnel,
        )
        return {
            "ok": True,
            "server_id": server_id,
            "scope": "personal",
            "workload_id": workload_id,
            "response": self._unwrap(payload),
        }
