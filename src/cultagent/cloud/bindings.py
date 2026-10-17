"""Agent binding cache — maps workloads ↔ cloud servers (guild or personal)."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from cultagent.cloud.client import CloudError, CultForgeClient
from cultagent.identity import AgentIdentity

logger = logging.getLogger("cultagent.cloud.bindings")


def agent_mode(identity: AgentIdentity | None) -> str:
    """Return ``guild`` or ``personal`` from stored node scope."""
    if identity is None or not identity.guild_id:
        return "personal"
    return "guild"


@dataclass
class BindingCache:
    """In-memory view refreshed from GET /v1/agent/bindings + /v1/agent/servers."""

    bindings: list[dict[str, Any]] = field(default_factory=list)
    servers: list[dict[str, Any]] = field(default_factory=list)
    mode: str = "personal"
    refreshed_at: float | None = None
    node_id: str | None = None

    def _unwrap_list(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        data = payload.get("data")
        if isinstance(data, list):
            return [x for x in data if isinstance(x, dict)]
        if isinstance(data, dict):
            for key in ("bindings", "servers", "items", "results"):
                items = data.get(key)
                if isinstance(items, list):
                    return [x for x in items if isinstance(x, dict)]
        if isinstance(payload.get("bindings"), list):
            return [x for x in payload["bindings"] if isinstance(x, dict)]
        return []

    def _unwrap_servers(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        data = payload.get("data")
        if isinstance(data, list):
            out: list[dict[str, Any]] = []
            for item in data:
                if not isinstance(item, dict):
                    continue
                if "server" in item and isinstance(item["server"], dict):
                    row = dict(item["server"])
                    if "binding" in item and isinstance(item["binding"], dict):
                        row["_binding"] = item["binding"]
                    out.append(row)
                else:
                    out.append(item)
            return out
        if isinstance(data, dict):
            for key in ("servers", "items", "results"):
                items = data.get(key)
                if isinstance(items, list):
                    return self._unwrap_servers({"data": items})
        return []

    def _binding_belongs_here(self, binding: dict[str, Any]) -> bool:
        """Drop bindings clearly owned by another agent node (API mix-ups)."""
        if not self.node_id:
            return True
        foreign = (
            binding.get("node_id")
            or binding.get("agent_id")
            or binding.get("anode_id")
            or binding.get("agent_node_id")
        )
        if not foreign:
            return True
        return str(foreign) == str(self.node_id)

    async def refresh(
        self,
        client: CultForgeClient,
        token: str,
        *,
        identity: AgentIdentity | None = None,
    ) -> dict[str, Any]:
        import time

        self.mode = agent_mode(identity)
        if identity is not None:
            self.node_id = identity.cloud_node_id or identity.node_id
        summary: dict[str, Any] = {"mode": self.mode, "bindings": 0, "servers": 0}
        try:
            bind_payload = await client.list_bindings(token)
            raw = self._unwrap_list(bind_payload)
            self.bindings = [b for b in raw if self._binding_belongs_here(b)]
            dropped = len(raw) - len(self.bindings)
            summary["bindings"] = len(self.bindings)
            if dropped:
                summary["bindings_foreign_dropped"] = dropped
                logger.warning(
                    "Dropped %s binding(s) belonging to another node (kept %s)",
                    dropped,
                    len(self.bindings),
                )
        except CloudError as exc:
            logger.debug("bindings refresh skipped: %s", exc)
            summary["bindings_error"] = str(exc)
        try:
            srv_payload = await client.list_agent_servers(token)
            self.servers = self._unwrap_servers(srv_payload)
            summary["servers"] = len(self.servers)
        except CloudError as exc:
            logger.debug("agent servers refresh skipped: %s", exc)
            summary["servers_error"] = str(exc)
        self.refreshed_at = time.time()
        return summary

    def active_bindings(self) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for b in self.bindings:
            if b.get("revoked_at"):
                continue
            if not self._binding_belongs_here(b):
                continue
            out.append(b)
        return out

    def binding_for_workload(self, workload_id: str) -> dict[str, Any] | None:
        wl = str(workload_id)
        for b in self.active_bindings():
            if str(b.get("workload_id") or "") == wl:
                return b
        return None

    def binding_for_server(self, server_id: str) -> dict[str, Any] | None:
        sid = str(server_id)
        for b in self.active_bindings():
            if str(b.get("guild_server_id") or "") == sid:
                return b
            if str(b.get("personal_server_id") or "") == sid:
                return b
        return None

    def is_bound(self, server_id: str) -> bool:
        return self.binding_for_server(server_id) is not None

    def local_server_id_for(self, server_id: str) -> str | None:
        """Map a cloud guild/personal id (or local id) to the agent's local_server_id."""
        sid = str(server_id or "").strip()
        if not sid:
            return None
        for b in self.active_bindings():
            local = str(b.get("local_server_id") or b.get("resource_id") or "").strip()
            clouds = {
                str(b.get("guild_server_id") or "").strip(),
                str(b.get("personal_server_id") or "").strip(),
                str(b.get("server_id") or "").strip(),
            }
            clouds.discard("")
            if sid == local or sid in clouds:
                return local or sid
        return None

    def cloud_server_id(self, binding: dict[str, Any]) -> str | None:
        scope = str(binding.get("scope") or "")
        if scope == "personal":
            val = binding.get("personal_server_id")
            return str(val) if val else None
        val = binding.get("guild_server_id")
        return str(val) if val else None

    @staticmethod
    def is_primary_binding(binding: dict[str, Any]) -> bool:
        """True when this binding is the primary host for the cloud server.

        API marks ``is_primary`` (or legacy ``primary``). If the field is absent,
        treat as primary so older API responses keep working until all nodes
        advertise the flag.
        """
        if "is_primary" in binding:
            return bool(binding.get("is_primary"))
        if "primary" in binding:
            return bool(binding.get("primary"))
        return True

    @staticmethod
    def is_stats_eligible(binding: dict[str, Any]) -> bool:
        """Competitive ingest gate from binding / nested server row.

        Missing ``stats_eligible`` defaults to True for primary guild bindings
        (API still enforces verified-guild). Explicit False blocks agent emit.
        """
        if "stats_eligible" in binding:
            return bool(binding.get("stats_eligible"))
        server = binding.get("server")
        if isinstance(server, dict) and "stats_eligible" in server:
            return bool(server.get("stats_eligible"))
        return True

    def primary_bindings(self) -> list[dict[str, Any]]:
        return [b for b in self.active_bindings() if self.is_primary_binding(b)]

    def stats_eligible_bindings(self) -> list[dict[str, Any]]:
        """Primary guild bindings that may feed competitive score batches."""
        out: list[dict[str, Any]] = []
        for b in self.primary_bindings():
            if str(b.get("scope") or self.mode) == "personal":
                continue
            if not self.is_stats_eligible(b):
                continue
            out.append(b)
        return out

    def primary_binding_for_server(self, server_id: str) -> dict[str, Any] | None:
        sid = str(server_id)
        for b in self.primary_bindings():
            if str(b.get("guild_server_id") or "") == sid:
                return b
            if str(b.get("personal_server_id") or "") == sid:
                return b
            if str(b.get("server_id") or "") == sid:
                return b
        return None
