"""Local RBAC / visibility helpers — cloud remains authoritative."""

from __future__ import annotations

from enum import Enum
from typing import Any


class Visibility(str, Enum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    RESTRICTED = "RESTRICTED"
    SENSITIVE = "SENSITIVE"
    SECRET = "SECRET"


_LEVEL_ORDER = {
    Visibility.PUBLIC: 0,
    Visibility.INTERNAL: 1,
    Visibility.RESTRICTED: 2,
    Visibility.SENSITIVE: 3,
    Visibility.SECRET: 4,
}


# Default classification for common response fields.
DEFAULT_FIELD_LEVELS: dict[str, Visibility] = {
    "product": Visibility.PUBLIC,
    "version": Visibility.PUBLIC,
    "running": Visibility.PUBLIC,
    "status": Visibility.PUBLIC,
    "name": Visibility.PUBLIC,
    "server_id": Visibility.PUBLIC,
    "loader": Visibility.PUBLIC,
    "minecraft_version": Visibility.PUBLIC,
    "port": Visibility.INTERNAL,
    "bind": Visibility.INTERNAL,
    "data_dir": Visibility.RESTRICTED,
    "identity": Visibility.INTERNAL,
    "cloud": Visibility.INTERNAL,
    "local": Visibility.RESTRICTED,
    "network": Visibility.INTERNAL,
    "network_provider": Visibility.INTERNAL,
    "token": Visibility.SECRET,
    "agent_token": Visibility.SECRET,
    "secret": Visibility.SECRET,
    "secret_path": Visibility.SENSITIVE,
    "credentials": Visibility.SECRET,
    "jwt": Visibility.SECRET,
    "password": Visibility.SECRET,
    "rcon": Visibility.SECRET,
    "claim_url": Visibility.RESTRICTED,
}


# Destructive / high-risk commands that need confirmation when dry_run isn't set.
HIGH_RISK_COMMANDS = frozenset(
    {
        "server.stop",
        "server.restart",
        "server.backup.restore",
        "server.mods.remove",
        "server.config.update",
        "builds.provision",
        "playit.secret",
        "network.use",
    }
)


class VisibilityFilter:
    """Strip fields the actor is not allowed to see.

    The backend filters what a client may receive; the agent also enforces
    sensitive local operations and never returns secrets just because a local
    endpoint exists.
    """

    def __init__(self, max_level: Visibility = Visibility.INTERNAL) -> None:
        self.max_level = max_level

    def allows(self, level: Visibility | str) -> bool:
        if isinstance(level, str):
            level = Visibility(level)
        return _LEVEL_ORDER[level] <= _LEVEL_ORDER[self.max_level]

    def filter_dict(
        self,
        payload: dict[str, Any],
        field_levels: dict[str, Visibility] | None = None,
        *,
        deep: bool = True,
    ) -> dict[str, Any]:
        levels = {**DEFAULT_FIELD_LEVELS, **(field_levels or {})}
        out: dict[str, Any] = {}
        for key, value in payload.items():
            level = levels.get(key, Visibility.INTERNAL)
            # Hard deny secrets by key name even if misclassified
            if key.lower() in {"token", "agent_token", "secret", "jwt", "password", "authorization"}:
                level = Visibility.SECRET
            if not self.allows(level):
                continue
            if deep and isinstance(value, dict):
                out[key] = self.filter_dict(value, field_levels, deep=True)
            else:
                out[key] = value
        return out

    def redact_secrets(self, payload: Any) -> Any:
        """Always strip SECRET-class keys regardless of max_level (defense in depth)."""
        if isinstance(payload, dict):
            out: dict[str, Any] = {}
            for key, value in payload.items():
                if key.lower() in {
                    "token",
                    "agent_token",
                    "secret",
                    "jwt",
                    "password",
                    "authorization",
                    "secret_key",
                }:
                    out[key] = "[redacted]"
                else:
                    out[key] = self.redact_secrets(value)
            return out
        if isinstance(payload, list):
            return [self.redact_secrets(v) for v in payload]
        return payload


class LocalAuthorizer:
    """Optional offline/temporary checks — do not duplicate cloud roles."""

    def __init__(self) -> None:
        self._grants: dict[str, set[str]] = {}

    def grant(self, actor_id: str, permission: str, resource_id: str = "*") -> None:
        key = f"{actor_id}:{resource_id}"
        self._grants.setdefault(key, set()).add(permission)

    def revoke(self, actor_id: str, permission: str, resource_id: str = "*") -> None:
        key = f"{actor_id}:{resource_id}"
        self._grants.get(key, set()).discard(permission)

    def check(self, actor_id: str | None, permission: str, resource_id: str) -> bool:
        if actor_id is None:
            return False
        for res in (resource_id, "*"):
            grants = self._grants.get(f"{actor_id}:{res}", set())
            if permission in grants or "*" in grants:
                return True
        return False

    def require(self, actor_id: str | None, permission: str, resource_id: str) -> None:
        if not self.check(actor_id, permission, resource_id):
            raise PermissionError(f"{permission} denied for resource {resource_id}")

    def has_policy(self, actor_id: str | None) -> bool:
        """True when this actor has any local grants (sidecar / offline overlay)."""
        if not actor_id:
            return False
        prefix = f"{actor_id}:"
        return any(key.startswith(prefix) and grants for key, grants in self._grants.items())

    def grant_role(self, actor_id: str, role: str, resource_id: str = "*") -> None:
        for perm in ROLE_PERMISSIONS.get(role, ()):
            self.grant(actor_id, perm, resource_id)


# Local role templates (mirrors CultForge concepts; cloud remains source of truth).
ROLE_PERMISSIONS: dict[str, tuple[str, ...]] = {
    "owner": ("*",),
    "admin": (
        "server.list",
        "server.status",
        "server.start",
        "server.stop",
        "server.restart",
        "server.console.read",
        "server.console.execute",
        "server.config.read",
        "server.config.update",
        "server.backup.create",
        "server.backup.restore",
        "server.mods.list",
        "server.mods.install",
        "server.mods.remove",
        "server.mods.update",
        "server.mods.resolve",
        "server.mods.search",
        "server.mods.project",
        "server.mods.versions",
        "server.refresh",
        "builds.list",
        "builds.manifest",
        "builds.provision",
        "server.clone",
        "server.remove",
        "agent.servers.list",
        "guild.servers.get",
        "servers.tunnel",
        "runtime.upsert",
        "node.status",
        "node.metrics",
        "node.update.check",
        "node.update.apply",
        "network.status",
        "network.restart",
        "network.use",
        "playit.setup",
        "playit.claim.wait",
        "playit.reset",
        "playit.start",
        "playit.stop",
        "playit.logs",
        "config.profile.list",
        "config.profile.apply",
    ),
    "moderator": (
        "server.list",
        "server.status",
        "server.start",
        "server.stop",
        "server.restart",
        "server.console.read",
        "server.console.execute",
        "server.config.read",
        "server.mods.list",
        "node.status",
        "node.metrics",
        "network.status",
        "builds.list",
        "builds.manifest",
    ),
    "player": (
        "server.list",
        "server.status",
        "node.status",
        "builds.list",
    ),
    "chloe": (
        "node.status",
        "node.metrics",
        "server.list",
        "server.status",
        "server.console.read",
        "builds.list",
        "builds.manifest",
        "server.mods.search",
        "server.mods.project",
        "server.mods.versions",
        "network.status",
        "config.profile.list",
    ),
}
