"""CultForge HTTPS API client (api.cultforge.com agent control plane)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from cultagent.settings import CloudSection

logger = logging.getLogger("cultagent.cloud")


class CloudError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class CultForgeClient:
    """Outbound HTTPS client for CultForge agent routes."""

    def __init__(self, cloud: CloudSection, timeout: float = 30.0) -> None:
        self.cloud = cloud
        self._timeout = timeout
        self._http: httpx.AsyncClient | None = None

    @property
    def api_base(self) -> str:
        return self.cloud.api_base.rstrip("/")

    def _headers(self, *, agent_token: str | None = None, user_jwt: str | None = None) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "CultForge-Agent/0.1 (cf-agent)",
        }
        if agent_token:
            headers["Authorization"] = f"Bearer {agent_token}"
        elif user_jwt:
            headers["Authorization"] = f"Bearer {user_jwt}"
        return headers

    def _http_client(self) -> httpx.AsyncClient:
        client = self._http
        if client is None or getattr(client, "is_closed", False):
            self._http = httpx.AsyncClient(
                timeout=self._timeout,
                limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
            )
            client = self._http
        return client

    async def aclose(self) -> None:
        client = self._http
        self._http = None
        if client is not None:
            closer = getattr(client, "aclose", None)
            if closer is not None:
                await closer()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        agent_token: str | None = None,
        user_jwt: str | None = None,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.api_base}{path}"
        query: dict[str, Any] | None = None
        if params:
            query = {k: v for k, v in params.items() if v is not None}
        response = await self._http_client().request(
            method,
            url,
            headers=self._headers(agent_token=agent_token, user_jwt=user_jwt),
            json=json_body,
            params=query or None,
        )
        try:
            payload = response.json()
        except ValueError:
            payload = {"raw": response.text}
        if response.status_code >= 400:
            detail = payload.get("detail") if isinstance(payload, dict) else payload
            raise CloudError(
                f"{method} {path} failed ({response.status_code}): {detail}",
                status_code=response.status_code,
                body=payload,
            )
        if isinstance(payload, dict):
            return payload
        return {"data": payload}

    async def health(self) -> dict[str, Any]:
        results: dict[str, Any] = {}
        for name, base in (
            ("auth", self.cloud.auth_base),
            ("api", self.cloud.api_base),
            ("invite", self.cloud.invite_base),
            ("guilds", self.cloud.guilds_base),
        ):
            try:
                async with httpx.AsyncClient(timeout=self._timeout) as client:
                    response = await client.get(base.rstrip("/") + "/")
                results[name] = {
                    "ok": response.status_code < 500,
                    "status_code": response.status_code,
                    "base": base,
                }
            except httpx.HTTPError as exc:
                results[name] = {"ok": False, "error": str(exc), "base": base}
        return results

    # --- User JWT (launcher / optional direct register) ---

    async def register_with_user_jwt(
        self,
        user_jwt: str,
        *,
        name: str,
        guild_id: str | None = None,
        platform: str | None = None,
        arch: str | None = None,
        agent_version: str | None = None,
        capabilities: list[Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "name": name,
            "capabilities": capabilities or [],
        }
        if guild_id:
            body["guild_id"] = guild_id
        if platform:
            body["platform"] = platform
        if arch:
            body["arch"] = arch
        if agent_version:
            body["agent_version"] = agent_version
        return await self._request(
            "POST",
            "/v1/agents/register",
            user_jwt=user_jwt,
            json_body=body,
        )

    # --- Pairing claim (preferred on-box) ---

    async def claim_pairing(
        self,
        *,
        code: str,
        name: str,
        platform: str | None = None,
        arch: str | None = None,
        agent_version: str | None = None,
        capabilities: list[Any] | None = None,
        local_node_id: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "code": code.strip().upper(),
            "name": name,
            "capabilities": capabilities or [],
        }
        if platform:
            body["platform"] = platform
        if arch:
            body["arch"] = arch
        if agent_version:
            body["agent_version"] = agent_version
        if local_node_id:
            body["local_node_id"] = local_node_id
        return await self._request("POST", "/v1/agents/claim", json_body=body)

    async def device_start(
        self,
        *,
        name: str,
        platform: str | None = None,
        arch: str | None = None,
        agent_version: str | None = None,
        capabilities: list[Any] | None = None,
        local_node_id: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "name": name,
            "capabilities": capabilities or [],
        }
        if platform:
            body["platform"] = platform
        if arch:
            body["arch"] = arch
        if agent_version:
            body["agent_version"] = agent_version
        if local_node_id:
            body["local_node_id"] = local_node_id
        return await self._request("POST", "/v1/agents/device/start", json_body=body)

    async def device_token(self, *, device_code: str) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/agents/device/token",
            json_body={"device_code": device_code},
        )

    async def device_approve(
        self,
        user_jwt: str,
        *,
        user_code: str,
        guild_id: str | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"user_code": user_code.strip().upper()}
        if guild_id:
            body["guild_id"] = guild_id
        return await self._request(
            "POST",
            "/v1/agents/device/approve",
            user_jwt=user_jwt,
            json_body=body,
        )

    # --- Agent bearer (cagt_…) ---

    async def agent_me(self, agent_token: str) -> dict[str, Any]:
        return await self._request("GET", "/v1/agent/me", agent_token=agent_token)

    async def heartbeat(
        self,
        agent_token: str,
        *,
        status: str = "online",
        agent_version: str | None = None,
        platform: str | None = None,
        arch: str | None = None,
        capabilities: list[Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {"status": status}
        if agent_version:
            body["agent_version"] = agent_version
        if platform:
            body["platform"] = platform
        if arch:
            body["arch"] = arch
        if capabilities is not None:
            body["capabilities"] = capabilities
        return await self._request(
            "POST",
            "/v1/agent/heartbeat",
            agent_token=agent_token,
            json_body=body,
        )

    async def poll(self, agent_token: str) -> dict[str, Any]:
        return await self._request("GET", "/v1/agent/poll", agent_token=agent_token)

    async def report_command_result(
        self,
        agent_token: str,
        command_id: str,
        *,
        success: bool,
        result: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            f"/v1/agent/commands/{command_id}/result",
            agent_token=agent_token,
            json_body={"success": success, "result": result},
        )

    async def publish_telemetry(
        self,
        agent_token: str,
        *,
        metrics: dict[str, Any],
        workload_id: str | None = None,
        schema_version: int = 1,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "metrics": metrics,
            "schema_version": schema_version,
        }
        if workload_id:
            body["workload_id"] = workload_id
        return await self._request(
            "POST",
            "/v1/agent/telemetry",
            agent_token=agent_token,
            json_body=body,
        )

    async def report_workloads(
        self,
        agent_token: str,
        reports: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/agent/workloads/report",
            agent_token=agent_token,
            json_body={"reports": reports},
        )

    # --- Guild builds (Option A: workload + install manifest) ---

    async def list_guild_builds(
        self, agent_token: str, *, limit: int = 50
    ) -> dict[str, Any]:
        # Manifest: GET /v1/agent/guild/builds?limit (1–100, default 50)
        return await self._request(
            "GET",
            "/v1/agent/guild/builds",
            agent_token=agent_token,
            params={"limit": max(1, min(int(limit), 100))},
        )

    async def get_guild_build_manifest(
        self, agent_token: str, build_id: str
    ) -> dict[str, Any]:
        return await self._request(
            "GET",
            f"/v1/agent/guild/builds/{build_id}/manifest",
            agent_token=agent_token,
        )

    async def provision_from_build(
        self,
        agent_token: str,
        build_id: str,
        *,
        desired_state: str = "stopped",
        display_name: str | None = None,
        local_server_id: str | None = None,
        network_mode: str = "direct",
        network_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "desired_state": desired_state,
            "network_mode": network_mode,
        }
        if display_name:
            body["display_name"] = display_name
        if local_server_id:
            body["local_server_id"] = local_server_id
        if network_meta:
            body["network_meta"] = network_meta
        return await self._request(
            "POST",
            f"/v1/agent/guild/builds/{build_id}/provision",
            agent_token=agent_token,
            json_body=body,
        )

    # --- Guild servers / runtime / presence / events / stats ---
    # Contract: CONTEXT (tunnel_address/port, effective join, caps).
    # Manifest lists path/query; POST bodies match server models (not OpenAPI).

    async def list_guild_servers(
        self, agent_token: str, *, limit: int = 50
    ) -> dict[str, Any]:
        """GET /v1/agent/guild/servers?limit — includes effective_* address fields."""
        return await self._request(
            "GET",
            "/v1/agent/guild/servers",
            agent_token=agent_token,
            params={"limit": max(1, min(int(limit), 100))},
        )

    async def get_guild_server(
        self, agent_token: str, server_id: str
    ) -> dict[str, Any]:
        """GET /v1/agent/guild/servers/{server_id} — configured vs effective join."""
        return await self._request(
            "GET",
            f"/v1/agent/guild/servers/{server_id}",
            agent_token=agent_token,
        )

    async def set_guild_server_tunnel(
        self,
        agent_token: str,
        server_id: str,
        *,
        workload_id: str | None = None,
        tunnel_address: str | None = None,
        tunnel_port: int | None = None,
        network_mode: str | None = None,
        clear_tunnel: bool = False,
        tunnel_meta: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST /v1/agent/guild/servers/{server_id}/tunnel.

        Body::
            workload_id, tunnel_address, tunnel_port, network_mode,
            clear_tunnel?, tunnel_meta?
        """
        from cultagent.cloud.guild_payloads import build_tunnel_body

        payload = body if body is not None else build_tunnel_body(
            workload_id=workload_id,
            tunnel_address=tunnel_address,
            tunnel_port=tunnel_port,
            network_mode=network_mode,
            clear_tunnel=clear_tunnel,
            tunnel_meta=tunnel_meta,
        )
        return await self._request(
            "POST",
            f"/v1/agent/guild/servers/{server_id}/tunnel",
            agent_token=agent_token,
            json_body=payload,
        )

    async def upsert_guild_runtime(
        self,
        agent_token: str,
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
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST /v1/agent/guild/runtime — snapshot (+ optional tunnel fold-in)."""
        from cultagent.cloud.guild_payloads import build_runtime_body

        payload = body if body is not None else build_runtime_body(
            workload_id=workload_id,
            state=state,
            player_count=player_count,
            tps=tps,
            mspt=mspt,
            world=world,
            tunnel_address=tunnel_address,
            tunnel_port=tunnel_port,
            network_mode=network_mode,
            clear_tunnel=clear_tunnel,
            guild_server_id=guild_server_id,
            local_server_id=local_server_id,
        )
        return await self._request(
            "POST",
            "/v1/agent/guild/runtime",
            agent_token=agent_token,
            json_body=payload,
        )

    async def list_guild_players(
        self,
        agent_token: str,
        *,
        workload_id: str | None = None,
        limit: int = 200,
    ) -> dict[str, Any]:
        """GET /v1/agent/guild/players?workload_id&limit (1–200, default 200)."""
        return await self._request(
            "GET",
            "/v1/agent/guild/players",
            agent_token=agent_token,
            params={
                "workload_id": workload_id,
                "limit": max(1, min(int(limit), 200)),
            },
        )

    async def replace_guild_players(
        self,
        agent_token: str,
        *,
        workload_id: str,
        players: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """POST /v1/agent/guild/players — replace-all roster (≤200)."""
        from cultagent.cloud.guild_payloads import build_players_body

        return await self._request(
            "POST",
            "/v1/agent/guild/players",
            agent_token=agent_token,
            json_body=build_players_body(workload_id=workload_id, players=players),
        )

    async def list_guild_events(
        self,
        agent_token: str,
        *,
        workload_id: str | None = None,
        limit: int = 50,
    ) -> dict[str, Any]:
        """GET /v1/agent/guild/events?workload_id&limit (1–200, default 50)."""
        return await self._request(
            "GET",
            "/v1/agent/guild/events",
            agent_token=agent_token,
            params={
                "workload_id": workload_id,
                "limit": max(1, min(int(limit), 200)),
            },
        )

    async def append_guild_events(
        self,
        agent_token: str,
        *,
        events: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """POST /v1/agent/guild/events — append batch (≤50)."""
        from cultagent.cloud.guild_payloads import build_events_body

        return await self._request(
            "POST",
            "/v1/agent/guild/events",
            agent_token=agent_token,
            json_body=build_events_body(events=events),
        )

    async def upsert_guild_stats(
        self,
        agent_token: str,
        *,
        stats: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """POST /v1/agent/guild/stats — batch upsert by minecraft_uuid (≤100)."""
        from cultagent.cloud.guild_payloads import build_stats_body

        return await self._request(
            "POST",
            "/v1/agent/guild/stats",
            agent_token=agent_token,
            json_body=build_stats_body(stats=stats),
        )

    async def post_guild_live(
        self,
        agent_token: str,
        *,
        body: dict[str, Any] | None = None,
        workload_id: str | None = None,
        guild_server_id: str | None = None,
        reported_state: str = "running",
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
        """POST /v1/agent/guild/live — Aternos-style live share (agent token only)."""
        from cultagent.cloud.guild_payloads import build_live_body

        payload = body if body is not None else build_live_body(
            workload_id=str(workload_id or ""),
            guild_server_id=guild_server_id,
            reported_state=reported_state,
            minecraft_version=minecraft_version,
            player_count=player_count,
            max_players=max_players,
            tps=tps,
            mspt=mspt,
            world=world,
            server_facet=server_facet,
            players=players,
            events=events,
        )
        return await self._request(
            "POST",
            "/v1/agent/guild/live",
            agent_token=agent_token,
            json_body=payload,
        )

    async def post_personal_live(
        self,
        agent_token: str,
        server_id: str,
        *,
        body: dict[str, Any] | None = None,
        workload_id: str | None = None,
        reported_state: str = "running",
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
        """POST /v1/agent/personal/servers/{server_id}/live."""
        from cultagent.cloud.guild_payloads import build_live_body

        payload = body if body is not None else build_live_body(
            workload_id=str(workload_id or ""),
            personal_server_id=str(server_id),
            reported_state=reported_state,
            minecraft_version=minecraft_version,
            player_count=player_count,
            max_players=max_players,
            tps=tps,
            mspt=mspt,
            world=world,
            server_facet=server_facet,
            players=players,
            events=events,
        )
        return await self._request(
            "POST",
            f"/v1/agent/personal/servers/{server_id}/live",
            agent_token=agent_token,
            json_body=payload,
        )

    async def post_score_batch(
        self,
        agent_token: str,
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
    ) -> dict[str, Any]:
        """POST /v1/agent/score/batch — competitive raw deltas (API owns formula)."""
        from cultagent.cloud.guild_payloads import build_score_batch_body

        return await self._request(
            "POST",
            "/v1/agent/score/batch",
            agent_token=agent_token,
            json_body=build_score_batch_body(
                agent_node_id=agent_node_id,
                players=players,
                deltas=deltas,
                batch_id=batch_id,
                batch_seq=batch_seq,
                session_fingerprint=session_fingerprint,
                observed_at=observed_at,
                guild_server_id=guild_server_id,
                personal_server_id=personal_server_id,
                guild_id=guild_id,
                workload_id=workload_id,
                binding_id=binding_id,
                local_server_id=local_server_id,
                server_facet=server_facet or facet,
                agent_version=agent_version,
            ),
        )

    async def get_agent_commands_schema(
        self, agent_token: str
    ) -> dict[str, Any]:
        """GET /v1/agent/commands/schema — merged CultAgentCommandProfile for this node."""
        return await self._request(
            "GET",
            "/v1/agent/commands/schema",
            agent_token=agent_token,
        )

    # --- Bindings & bound servers (r4s5t6u7v8w9) ---

    async def list_bindings(self, agent_token: str) -> dict[str, Any]:
        """GET /v1/agent/bindings — active server bindings for this node."""
        return await self._request(
            "GET",
            "/v1/agent/bindings",
            agent_token=agent_token,
        )

    async def list_agent_servers(
        self, agent_token: str, *, limit: int = 100
    ) -> dict[str, Any]:
        """GET /v1/agent/servers — bound servers with effective join addresses."""
        return await self._request(
            "GET",
            "/v1/agent/servers",
            agent_token=agent_token,
            params={"limit": max(1, min(int(limit), 200))},
        )

    # --- Unified build catalog (prefer over guild-only paths) ---

    async def search_builds(
        self,
        agent_token: str,
        *,
        q: str | None = None,
        keywords: str | None = None,
        loader: str | None = None,
        minecraft_version: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> dict[str, Any]:
        """GET /v1/agent/builds/search — public catalog + guild builds when attached."""
        return await self._request(
            "GET",
            "/v1/agent/builds/search",
            agent_token=agent_token,
            params={
                "q": q,
                "keywords": keywords,
                "loader": loader,
                "minecraft_version": minecraft_version,
                "limit": max(1, min(int(limit), 100)),
                "offset": max(0, int(offset)),
            },
        )

    async def get_build_manifest(
        self, agent_token: str, build_id: str
    ) -> dict[str, Any]:
        """GET /v1/agent/builds/{build_id}/manifest — guild or user build."""
        return await self._request(
            "GET",
            f"/v1/agent/builds/{build_id}/manifest",
            agent_token=agent_token,
        )

    async def provision_build(
        self,
        agent_token: str,
        build_id: str,
        *,
        desired_state: str = "stopped",
        display_name: str | None = None,
        local_server_id: str | None = None,
        network_mode: str = "direct",
        network_meta: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST /v1/agent/builds/{build_id}/provision — unified catalog provision."""
        body: dict[str, Any] = {
            "desired_state": desired_state,
            "network_mode": network_mode,
        }
        if display_name:
            body["display_name"] = display_name
        if local_server_id:
            body["local_server_id"] = local_server_id
        if network_meta:
            safe = {
                k: v
                for k, v in network_meta.items()
                if k.lower()
                not in {"secret", "secret_key", "token", "agent_key", "password"}
            }
            if safe:
                body["network_meta"] = safe
        return await self._request(
            "POST",
            f"/v1/agent/builds/{build_id}/provision",
            agent_token=agent_token,
            json_body=body,
        )

    # --- Personal server panel (personal agents only) ---

    async def set_personal_server_tunnel(
        self,
        agent_token: str,
        server_id: str,
        *,
        workload_id: str | None = None,
        tunnel_address: str | None = None,
        tunnel_port: int | None = None,
        network_mode: str | None = None,
        clear_tunnel: bool = False,
        tunnel_meta: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST /v1/agent/personal/servers/{server_id}/tunnel."""
        from cultagent.cloud.guild_payloads import build_tunnel_body

        payload = body if body is not None else build_tunnel_body(
            workload_id=workload_id,
            tunnel_address=tunnel_address,
            tunnel_port=tunnel_port,
            network_mode=network_mode,
            clear_tunnel=clear_tunnel,
            tunnel_meta=tunnel_meta,
        )
        return await self._request(
            "POST",
            f"/v1/agent/personal/servers/{server_id}/tunnel",
            agent_token=agent_token,
            json_body=payload,
        )

    async def upsert_personal_runtime(
        self,
        agent_token: str,
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
        raw_public: dict[str, Any] | None = None,
        server_facet: dict[str, Any] | None = None,
        body: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """POST /v1/agent/personal/servers/{server_id}/runtime."""
        from cultagent.cloud.guild_payloads import build_personal_runtime_body

        payload = body if body is not None else build_personal_runtime_body(
            workload_id=workload_id,
            reported_state=reported_state,
            player_count=player_count,
            max_players=max_players,
            minecraft_version=minecraft_version,
            tps=tps,
            mspt=mspt,
            world=world,
            tunnel_address=tunnel_address,
            tunnel_port=tunnel_port,
            network_mode=network_mode,
            clear_tunnel=clear_tunnel,
            raw_public=raw_public,
            server_facet=server_facet,
        )
        return await self._request(
            "POST",
            f"/v1/agent/personal/servers/{server_id}/runtime",
            agent_token=agent_token,
            json_body=payload,
        )
