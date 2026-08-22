"""Registration: pairing claim (preferred) + optional user-JWT register."""

from __future__ import annotations

import logging
from typing import Any

from cultagent.cloud.client import CloudError, CultForgeClient
from cultagent.identity import (
    AgentCredentials,
    AgentIdentity,
    AgentStatus,
    IdentityStore,
    utc_now,
)

logger = logging.getLogger("cultagent.cloud.registration")

# Backend aliases → canonical cf-agent actions
ACTION_ALIASES: dict[str, str] = {
    "server.command": "server.console.execute",
    "config.edit": "server.config.update",
    "backup.restore": "server.backup.restore",
    "mod.install": "server.mods.install",
    "mod.remove": "server.mods.remove",
    "files.write": "server.config.update",
    "agent.ping": "node.status",
    # Pruned duplicates — old names kept as aliases for backward compat
    "builds.install": "builds.provision",
    "builds.search": "builds.list",
    "personal.servers.tunnel": "servers.tunnel",
    "guild.servers.tunnel": "servers.tunnel",
    "personal.runtime.upsert": "runtime.upsert",
    "guild.runtime.upsert": "runtime.upsert",
    "guild.servers.list": "agent.servers.list",
    "playit.install": "playit.setup",
    "network.configure": "network.use",
    "playit.tunnel.ensure": "playit.start",
    "modrinth.search": "server.mods.search",
    "modrinth.project": "server.mods.project",
    "modrinth.versions": "server.mods.versions",
    "config.profile.diff": "config.profile.apply",
    "config.profile.show": "config.profile.list",
}


def normalize_action(action: str) -> str:
    act = (action or "").strip()
    return ACTION_ALIASES.get(act, act)


def _unwrap_register(payload: dict[str, Any]) -> tuple[dict[str, Any], str]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    node = data.get("node") if isinstance(data, dict) else None
    token = data.get("agent_token") if isinstance(data, dict) else None
    if not isinstance(node, dict) or not token:
        raise CloudError("Invalid register/claim response — missing node or agent_token")
    return node, str(token)


def apply_registration(
    store: IdentityStore,
    identity: AgentIdentity,
    *,
    node: dict[str, Any],
    agent_token: str,
) -> AgentIdentity:
    """Persist cloud node + one-time agent_token (cagt_…)."""
    cloud_id = str(node.get("id") or "")
    if not cloud_id:
        raise CloudError("Register response missing node.id")

    if not identity.local_node_id:
        identity.local_node_id = identity.node_id
    identity.cloud_node_id = cloud_id
    identity.node_id = cloud_id
    identity.owner_account_id = node.get("owner_id")
    identity.guild_id = node.get("guild_id")
    if node.get("name"):
        identity.display_name = str(node["name"])
    if node.get("platform"):
        identity.platform = str(node["platform"])
    if node.get("arch"):
        identity.architecture = str(node["arch"])
    if node.get("agent_version"):
        identity.agent_version = str(node["agent_version"])
    caps = node.get("capabilities")
    if isinstance(caps, list):
        identity.capabilities = [str(c) for c in caps]
    identity.status = AgentStatus.ONLINE
    identity.registered_at = utc_now()
    store.save_identity(identity)

    creds = AgentCredentials(
        agent_token=agent_token,
        agent_secret=agent_token,
        issued_at=utc_now(),
    )
    store.save_credentials(creds)
    logger.info(
        "Registered with CultForge (cloud_node_id=%s, guild_id=%s)",
        cloud_id,
        identity.guild_id,
    )
    return identity


class RegistrationService:
    def __init__(self, client: CultForgeClient, store: IdentityStore) -> None:
        self.client = client
        self.store = store

    async def claim_pairing_code(
        self,
        identity: AgentIdentity,
        *,
        code: str,
    ) -> AgentIdentity:
        identity.status = AgentStatus.REGISTERING
        self.store.save_identity(identity)
        try:
            payload = await self.client.claim_pairing(
                code=code.strip().upper(),
                name=identity.display_name or "CultAgent",
                platform=identity.platform or None,
                arch=identity.architecture or None,
                agent_version=identity.agent_version or None,
                capabilities=identity.capabilities,
                local_node_id=identity.local_node_id or identity.node_id,
            )
            node, token = _unwrap_register(payload)
            return apply_registration(self.store, identity, node=node, agent_token=token)
        except Exception:
            identity.status = AgentStatus.UNREGISTERED
            self.store.save_identity(identity)
            raise

    async def register_with_jwt(
        self,
        identity: AgentIdentity,
        *,
        user_jwt: str,
        guild_id: str | None = None,
    ) -> AgentIdentity:
        identity.status = AgentStatus.REGISTERING
        self.store.save_identity(identity)
        try:
            payload = await self.client.register_with_user_jwt(
                user_jwt,
                name=identity.display_name or "CultAgent",
                guild_id=guild_id or identity.guild_id,
                platform=identity.platform or None,
                arch=identity.architecture or None,
                agent_version=identity.agent_version or None,
                capabilities=identity.capabilities,
            )
            node, token = _unwrap_register(payload)
            return apply_registration(self.store, identity, node=node, agent_token=token)
        except Exception:
            identity.status = AgentStatus.UNREGISTERED
            self.store.save_identity(identity)
            raise

    async def device_login(
        self,
        identity: AgentIdentity,
        *,
        open_browser: bool = True,
        approve_jwt: str | None = None,
        guild_id: str | None = None,
        oauth_provider: str = "google",
        on_prompt: Any | None = None,
    ) -> AgentIdentity:
        """Easy login: browser OAuth on auth.* → device approve on api.* → cagt_….

        Users should not paste JWTs. ``approve_jwt`` remains for automation only.
        """
        import asyncio

        from cultagent.cloud.browser_auth import BrowserAuthError, capture_oauth_session

        identity.status = AgentStatus.REGISTERING
        self.store.save_identity(identity)
        try:
            started = await self.client.device_start(
                name=identity.display_name or "CultAgent",
                platform=identity.platform or None,
                arch=identity.architecture or None,
                agent_version=identity.agent_version or None,
                capabilities=identity.capabilities,
                local_node_id=identity.local_node_id or identity.node_id,
            )
            data = started.get("data") if isinstance(started.get("data"), dict) else started
            device_code = str(data.get("device_code") or "")
            user_code = str(data.get("user_code") or "")
            interval = int(data.get("interval") or 5)
            expires_in = int(data.get("expires_in") or 600)
            if not device_code or not user_code:
                raise CloudError("device/start missing device_code or user_code")

            approve_path = f"{self.client.api_base}/v1/agents/device/approve"
            auth_base = self.client.cloud.auth_base.rstrip("/")
            prompt = {
                "user_code": user_code,
                "approve_url": approve_path,
                "auth_base": auth_base,
                "oauth_provider": oauth_provider,
                "expires_in": expires_in,
                "interval": interval,
                "mode": "browser" if not approve_jwt else "jwt",
            }
            if on_prompt:
                on_prompt(prompt)

            session_jwt = (approve_jwt or "").strip() or None
            if not session_jwt:
                try:
                    captured = await capture_oauth_session(
                        auth_base=auth_base,
                        provider=oauth_provider,
                        open_browser=open_browser,
                        timeout_seconds=float(max(60, expires_in)),
                    )
                except BrowserAuthError as exc:
                    raise CloudError(str(exc)) from exc
                session_jwt = captured.token

            await self.client.device_approve(
                session_jwt,
                user_code=user_code,
                guild_id=guild_id,
            )

            deadline = asyncio.get_event_loop().time() + max(30, expires_in)
            while asyncio.get_event_loop().time() < deadline:
                await asyncio.sleep(max(1, min(interval, 3)))
                polled = await self.client.device_token(device_code=device_code)
                pdata = polled.get("data") if isinstance(polled.get("data"), dict) else polled
                state = str(pdata.get("state") or "")
                if state == "pending":
                    interval = int(pdata.get("interval") or interval)
                    continue
                if state == "denied":
                    raise CloudError("Device login was denied in CultForge.")
                if state == "expired":
                    raise CloudError("Device login expired — run cf-agent login again.")
                if state == "approved":
                    node = pdata.get("node")
                    token = pdata.get("agent_token")
                    if not isinstance(node, dict) or not token:
                        raise CloudError("Approved device login missing node/token")
                    return apply_registration(
                        self.store, identity, node=node, agent_token=str(token)
                    )
                raise CloudError(f"Unexpected device login state: {state}")

            raise CloudError("Timed out waiting for CultForge approval.")
        except Exception:
            identity.status = AgentStatus.UNREGISTERED
            self.store.save_identity(identity)
            raise

    async def heartbeat(self, identity: AgentIdentity, credentials: AgentCredentials) -> None:
        token = credentials.token
        if not token:
            return
        await self.client.heartbeat(
            token,
            status="online" if identity.status != AgentStatus.DEGRADED else "degraded",
            agent_version=identity.agent_version or None,
            platform=identity.platform or None,
            arch=identity.architecture or None,
            capabilities=identity.capabilities,
        )
        identity.touch()
        self.store.save_identity(identity)


class AuthFlow:
    """User-facing registration entrypoints."""

    def __init__(self, registration: RegistrationService) -> None:
        self.registration = registration

    async def begin_connect(self) -> dict[str, Any]:
        return {
            "status": "ready",
            "method": "device_login",
            "message": (
                "Run:\n"
                "  cf-agent login\n"
                "Sign in via auth.cultforge.com in the browser — no JWT paste.\n"
                "Fallbacks:\n"
                "  cf-agent login --provider github\n"
                "  cf-agent login --jwt <USER_TOKEN>   # automation\n"
                "  cf-agent register --code <PAIRING>"
            ),
            "api_base": self.registration.client.api_base,
            "auth_base": self.registration.client.cloud.auth_base,
            "device_start_path": "/v1/agents/device/start",
            "device_approve_path": "/v1/agents/device/approve",
            "oauth_path": "/v1/oauth",
            "claim_path": "/v1/agents/claim",
        }
