"""CultAgent application runtime."""

from __future__ import annotations

import asyncio
import logging
import platform
from typing import Any

from cultagent import __version__
from cultagent.audit import AuditLog
from cultagent.cloud import (
    AuthFlow,
    ControlPlane,
    CultForgeClient,
    RegistrationService,
)
from cultagent.cloud.realtime import CloudRealtime
from cultagent.commands import CommandContext, CommandRegistry, build_default_registry
from cultagent.constants import COMMANDS
from cultagent.content import BuildService
from cultagent.files import BackupManager, FileManager
from cultagent.identity import AgentStatus, IdentityStore
from cultagent.logging_setup import setup_logging
from cultagent.metrics import MetricsCollector
from cultagent.network import NetworkManager
from cultagent.rbac import HIGH_RISK_COMMANDS, LocalAuthorizer, VisibilityFilter
from cultagent.config import ProfileStore
from cultagent.builds import BuildsOrchestrator
from cultagent.cloud.bindings import BindingCache
from cultagent.guild import GuildOrchestrator
from cultagent.personal import PersonalOrchestrator
from cultagent.servers import ServerManager
from cultagent.settings import AgentConfig, load_config, resolve_paths
from cultagent.sidecars import SidecarStore, ensure_chloe_grants

logger = logging.getLogger("cultagent.app")


class CultAgentApp:
    def __init__(self, config: AgentConfig | None = None, *, debug: bool = False) -> None:
        self.config = config or load_config()
        self.paths = resolve_paths(self.config)
        self.paths.ensure()
        self.debug = debug

        setup_logging(self.config.logging.level, self.paths.log_file, debug=debug)

        self.identity_store = IdentityStore(
            self.paths.identity_file,
            self.paths.credentials_file,
        )
        self.cloud_client = CultForgeClient(self.config.cloud)
        self.registration = RegistrationService(self.cloud_client, self.identity_store)
        self.auth = AuthFlow(self.registration)
        self.control_plane = ControlPlane(self)
        self.realtime = CloudRealtime(self, self.control_plane)

        self.servers = ServerManager(
            self.paths.servers_dir,
            default_java_path=self.config.servers.java_path,
        )
        self.network = NetworkManager(
            self.config.network,
            data_dir=self.paths.root / "playit",
        )
        self.content = BuildService(self.config.content)
        self.builds = BuildsOrchestrator(self)
        self.guild = GuildOrchestrator(self)
        self.personal = PersonalOrchestrator(self)
        self.bindings = BindingCache()
        self.metrics = MetricsCollector()
        self.files = FileManager(self.paths.root)
        self.backups = BackupManager(self.paths.backups_dir)
        self.profiles = ProfileStore(self.paths.profiles_dir)
        self.audit = AuditLog(self.paths.audit_dir)
        self.authorizer = LocalAuthorizer()
        self.visibility = VisibilityFilter()
        self.sidecars = SidecarStore(self.paths.root / "sidecars")
        ensure_chloe_grants(self.authorizer)
        self.commands: CommandRegistry = build_default_registry()

        self._running = False
        self._tasks: list[asyncio.Task[Any]] = []

    def bootstrap_identity(self) -> None:
        self.identity_store.ensure_local_identity(
            display_name=self.config.agent.display_name or platform.node(),
            platform=platform.system(),
            architecture=platform.machine(),
            agent_version=__version__,
            capabilities=list(COMMANDS),
        )
        self.servers.ensure()

    def public_status(self) -> dict[str, Any]:
        identity = self.identity_store.export_public()
        payload = {
            "product": "CultForge Agent",
            "version": __version__,
            "running": self._running,
            "identity": identity,
            "cloud": {
                "api_base": self.config.cloud.api_base,
                "poll_interval_seconds": self.control_plane.poll_interval,
                "control_plane_enabled": self.config.cloud.control_plane_enabled,
                "realtime_enabled": self.config.cloud.realtime_enabled,
                "transport": self.realtime.status_dict(),
            },
            "local": {
                "bind": f"{self.config.local.bind_host}:{self.config.local.bind_port}",
                "data_dir": str(self.paths.root),
            },
            "network_provider": self.network.active_name,
            "network": {
                "active": self.network.active_name,
                "playit_running": self.network.playit.is_running(),
                "playit_has_secret": self.network.playit.has_secret(),
                "playit_target": self.network.playit.target,
            },
            "sidecars": {
                "clients": self.sidecars.list_clients(),
                "chloe_role": "chloe",
            },
        }
        # Defense in depth: never surface SECRET-class keys via status.
        return self.visibility.redact_secrets(payload)

    async def dispatch(
        self,
        command: str,
        *,
        params: dict[str, Any] | None = None,
        actor_id: str | None = None,
        resource_id: str | None = None,
        enforce_local: bool = False,
    ) -> dict[str, Any]:
        from cultagent.cloud.registration import normalize_action

        command = normalize_action(command)
        params = dict(params or {})
        # Local authorizer is defense-in-depth for authorized sidecars only.
        # Cloud remains authoritative for control-plane commands.
        if enforce_local:
            try:
                self.authorizer.require(actor_id, command, resource_id or "*")
            except PermissionError as exc:
                return {
                    "ok": False,
                    "command": command,
                    "data": {},
                    "error": f"forbidden: {exc}",
                }
            if (
                command in HIGH_RISK_COMMANDS
                and not params.get("confirm")
                and not params.get("dry_run")
            ):
                return {
                    "ok": False,
                    "command": command,
                    "data": {"needs_confirm": True},
                    "error": "confirm=true required for high-risk command",
                }
        ctx = CommandContext(
            name=command,
            params=params,
            actor_id=actor_id,
            resource_id=resource_id,
            app=self,
        )
        result = await self.commands.dispatch(ctx)
        out = result.to_dict()
        out["data"] = self.visibility.redact_secrets(out.get("data") or {})
        return out

    async def start(self) -> None:
        if self._running:
            return
        self.bootstrap_identity()
        self._running = True

        from cultagent.cloud.activity_bridge import get_activity_bridge

        get_activity_bridge().start()

        identity = self.identity_store.load_identity()
        creds = self.identity_store.load_credentials()
        assert identity is not None

        if not creds.has_credentials or identity.status == AgentStatus.UNREGISTERED:
            logger.info(
                "Agent %s is unregistered — run `cf-agent login` to connect CultForge.",
                identity.local_node_id or identity.node_id,
            )
        elif self.config.cloud.control_plane_enabled:
            self._tasks.append(asyncio.create_task(self.realtime.run()))
            self._tasks.append(asyncio.create_task(self._live_share_loop()))

        self._tasks.append(asyncio.create_task(self._run_local_api()))
        self._tasks.append(asyncio.create_task(self._crash_watch_loop()))
        self._tasks.append(asyncio.create_task(self._auto_start_servers()))
        self._tasks.append(asyncio.create_task(self._maybe_start_playit()))

        logger.info(
            "CultAgent started (node_id=%s, status=%s)",
            identity.node_id,
            identity.status.value,
        )

    async def _maybe_start_playit(self) -> None:
        try:
            await self.network.maybe_autostart()
        except Exception:  # noqa: BLE001
            logger.exception("playit auto-start error")

    async def _run_local_api(self) -> None:
        try:
            from cultagent.api import serve_local_api

            await serve_local_api(self)
        except Exception:  # noqa: BLE001
            logger.exception("Local API failed to start")

    async def _auto_start_servers(self) -> None:
        """Honor per-server auto_start (and global auto_start_servers)."""
        await asyncio.sleep(2)
        if not self._running:
            return
        global_on = bool(self.config.local.auto_start_servers)
        for record in await self.servers.list_servers():
            if not (record.auto_start or global_on):
                continue
            try:
                status = await self.servers.status(record.server_id)
                if status.state.value in {"running", "starting"}:
                    continue
                logger.info("Auto-starting server %s", record.server_id)
                await self.servers.start(record.server_id)
            except Exception:  # noqa: BLE001
                logger.exception("Auto-start failed for %s", record.server_id)

    async def _control_plane_loop(self) -> None:
        while self._running:
            try:
                summary = await self.control_plane.tick()
                if summary.get("commands"):
                    logger.info("Control plane: executed %s cloud command(s)", summary["commands"])
                if summary.get("reason") == "revoked":
                    logger.error("Agent token revoked — stopping control plane loop")
                    break
            except Exception:  # noqa: BLE001
                logger.exception("Control plane tick failed")
            await asyncio.sleep(self.control_plane.poll_interval)

    async def _live_share_loop(self) -> None:
        """Post Aternos-style live snapshots on a 3–10s cadence (independent of poll)."""
        from cultagent.cloud.live_share import clamp_live_interval

        while self._running:
            try:
                await self.control_plane.flush_live_share()
            except Exception:  # noqa: BLE001
                logger.debug("live share loop error", exc_info=True)
            await asyncio.sleep(
                clamp_live_interval(self.config.cloud.live_share_interval_seconds)
            )

    async def _try_resolve_from_crash(self, record: Any) -> None:
        """If latest.log / FML crash lists missing mods, install them before restart."""
        from cultagent.content.crash_resolve import (
            already_resolved,
            collect_crash_text,
            parse_dep_failures,
        )

        loader = str(record.loader or "forge")
        if loader == "vanilla":
            return
        game_version = str(record.minecraft_version or "")
        if not game_version:
            return
        text, sources = collect_crash_text(record.path)
        issues = parse_dep_failures(text)
        if not issues:
            return
        if already_resolved(record.path, issues):
            logger.info(
                "Crash-log deps already resolved for %s — skipping",
                record.server_id,
            )
            return
        logger.info(
            "Resolving %s missing/outdated mods from crash log for %s (%s)",
            len(issues),
            record.server_id,
            ", ".join(sources[:2]),
        )
        result = await self.content.resolve_mod_dependencies(
            record.path,
            loader=loader,
            game_version=game_version,
            source="crash",
        )
        logger.info(
            "Crash-log resolve for %s: +%s libraries, %s disabled, %s unresolved",
            record.server_id,
            result.get("added_count") or 0,
            result.get("disabled_count") or 0,
            len(result.get("unresolved") or []),
        )

    async def _crash_watch_loop(self) -> None:
        """Detect crashes and optionally auto-restart (Crafty-style)."""
        # server_id -> timestamps of recent restart attempts
        recent: dict[str, list[float]] = {}
        while self._running:
            try:
                now = asyncio.get_event_loop().time()
                for record in await self.servers.list_servers():
                    if not record.crash_detection:
                        continue
                    status = await self.servers.status(record.server_id)
                    if status.state.value != "crashed":
                        continue
                    logger.warning(
                        "Server %s reported crashed (exit=%s)",
                        record.server_id,
                        status.exit_code,
                    )
                    await self.audit.record(
                        resource_id=record.server_id,
                        operation="server.crash_detected",
                        result="crashed",
                        extra={"exit_code": status.exit_code},
                    )
                    if not record.auto_restart:
                        continue
                    stamps = [t for t in recent.get(record.server_id, []) if now - t < 600]
                    if len(stamps) >= 3:
                        logger.error(
                            "Server %s crash-looping — skipping auto-restart",
                            record.server_id,
                        )
                        continue
                    if stamps and now - stamps[-1] < 30:
                        continue
                    try:
                        await self._try_resolve_from_crash(record)
                    except Exception:  # noqa: BLE001
                        logger.exception(
                            "Crash-log mod resolve failed for %s", record.server_id
                        )
                    stamps.append(now)
                    recent[record.server_id] = stamps
                    try:
                        logger.info("Auto-restarting crashed server %s", record.server_id)
                        await self.servers.start(record.server_id)
                        await self.audit.record(
                            resource_id=record.server_id,
                            operation="server.auto_restart",
                            result="ok",
                        )
                    except Exception:  # noqa: BLE001
                        logger.exception("Auto-restart failed for %s", record.server_id)
            except Exception:  # noqa: BLE001
                logger.exception("Crash watch error")
            await asyncio.sleep(15)

    async def stop(self) -> None:
        self._running = False
        try:
            from cultagent.cloud.activity_bridge import get_activity_bridge

            get_activity_bridge().stop()
        except Exception:  # noqa: BLE001
            logger.debug("activity bridge stop failed", exc_info=True)
        try:
            await self.network.stop_playit()
        except Exception:  # noqa: BLE001
            logger.exception("Error stopping playit")
        try:
            await self.servers.stop_all()
        except Exception:  # noqa: BLE001
            logger.exception("Error stopping servers")
        for task in self._tasks:
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        try:
            await self.cloud_client.aclose()
        except Exception:  # noqa: BLE001
            logger.exception("Error closing cloud HTTP client")
        logger.info("CultAgent stopped")

    async def run_forever(self) -> None:
        await self.start()
        try:
            while self._running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            raise
        finally:
            await self.stop()


def create_app(config_path: str | None = None, *, debug: bool = False) -> CultAgentApp:
    from pathlib import Path

    from cultagent.settings import load_config

    config = load_config(Path(config_path) if config_path else None)
    return CultAgentApp(config, debug=debug)
