"""Shared constants for CultAgent."""

from __future__ import annotations

PRODUCT_NAME = "CultForge Agent"
SHORT_NAME = "CultAgent"
CLI_NAME = "cf-agent"
NODE_ID_PREFIX = "cfnode_"

# CultForge cloud defaults — live worker subdomains (apex cultforge.com is static).
# Override with env (CULTAGENT_*_BASE) or config for localhost 8071–8074.
DEFAULT_AUTH_BASE = "https://auth.cultforge.com"
DEFAULT_API_BASE = "https://api.cultforge.com"
DEFAULT_INVITE_BASE = "https://invite.cultforge.com"
DEFAULT_GUILDS_BASE = "https://guilds.cultforge.com"

# Agent routes expected on live api.cultforge.com/manifest.json.
REQUIRED_AGENT_ROUTES = (
    "/v1/agents/device/start",
    "/v1/agents/device/approve",
    "/v1/agents/device/token",
    "/v1/agents/claim",
    "/v1/agents/register",
    "/v1/agent/me",
    "/v1/agent/heartbeat",
    "/v1/agent/poll",
    "/v1/agent/telemetry",
    "/v1/agent/workloads/report",
    "/v1/agent/guild/builds",
    "/v1/agent/guild/builds/{build_id}/manifest",
    "/v1/agent/guild/builds/{build_id}/provision",
    "/v1/agent/guild/servers",
    "/v1/agent/guild/servers/{server_id}",
    "/v1/agent/guild/servers/{server_id}/tunnel",
    "/v1/agent/guild/runtime",
    "/v1/agent/guild/players",
    "/v1/agent/guild/live",
    "/v1/agent/guild/events",
    "/v1/agent/guild/stats",
    "/v1/agent/score/batch",
    "/v1/agent/commands/schema",
    "/v1/agent/bindings",
    "/v1/agent/servers",
    "/v1/agent/builds/search",
    "/v1/agent/builds/{build_id}/manifest",
    "/v1/agent/builds/{build_id}/provision",
    "/v1/agent/personal/servers/{server_id}/tunnel",
    "/v1/agent/personal/servers/{server_id}/runtime",
    "/v1/agent/personal/servers/{server_id}/live",
    "/v1/guilds/{guild_id}/agents/{node_id}/attach",
)

# Advertised in manifest `&` metadata (not always listed in the flat route table).
ADVERTISED_AGENT_WS = "/v1/agent/ws"

# Controlled capability surface (authorization is cloud-authoritative).
COMMANDS = (
    "server.list",
    "server.status",
    "server.start",
    "server.stop",
    "server.restart",
    "server.console.read",
    "server.console.execute",
    "server.player.kick",
    "server.player.ban",
    "server.config.read",
    "server.config.update",
    "server.mods.list",
    "server.mods.install",
    "server.mods.remove",
    "server.mods.update",
    "server.mods.resolve",
    "server.mods.search",
    "server.mods.project",
    "server.mods.versions",
    "server.backup.create",
    "server.backup.restore",
    "builds.list",
    "builds.manifest",
    "builds.provision",
    "server.clone",
    "server.remove",
    "agent.bindings.list",
    "agent.servers.list",
    "guild.servers.get",
    "servers.tunnel",
    "runtime.upsert",
    "node.status",
    "node.metrics",
    "network.status",
    "network.restart",
    "network.use",
    "playit.setup",
    "playit.claim.wait",
    "playit.reset",
    "playit.start",
    "playit.stop",
    "playit.secret",
    "playit.logs",
    "config.profile.list",
    "config.profile.save",
    "config.profile.delete",
    "config.profile.apply",
    "config.profile.capture",
    "sidecar.list",
    "sidecar.issue",
    "sidecar.revoke",
    "node.doctor",
    "node.update.check",
    "node.update.apply",
    "server.refresh",
)

VISIBILITY_LEVELS = (
    "PUBLIC",
    "INTERNAL",
    "RESTRICTED",
    "SENSITIVE",
    "SECRET",
)
