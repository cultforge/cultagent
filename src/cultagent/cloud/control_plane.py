"""HTTP poll control plane (~15s): heartbeat, poll commands, telemetry, workloads."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING, Any

from cultagent.cloud.client import CloudError, CultForgeClient
from cultagent.cloud.registration import normalize_action
from cultagent.identity import AgentStatus, IdentityStore

if TYPE_CHECKING:
    from cultagent.app import CultAgentApp

logger = logging.getLogger("cultagent.cloud.control_plane")


class ControlPlane:
    def __init__(self, app: CultAgentApp) -> None:
        self.app = app
        self.client: CultForgeClient = app.cloud_client
        self.store: IdentityStore = app.identity_store
        self._poll_interval = max(5, int(app.config.cloud.poll_interval_seconds))
        self._seen_command_ids: set[str] = set()
        self._backoff_until = 0.0
        self._backoff_seconds = 0
        self._read_cache: dict[str, tuple[float, dict[str, Any]]] = {}
        self._READ_CACHE_TTL = 8.0
        self._READ_ACTIONS = frozenset({"server.status", "server.console.read"})

    @property
    def poll_interval(self) -> int:
        remaining = self._backoff_until - time.time()
        if remaining > 0:
            return max(self._poll_interval, int(remaining) + 1)
        return self._poll_interval

    def _in_backoff(self) -> bool:
        return time.time() < self._backoff_until

    def _note_cloud_error(self, exc: CloudError) -> None:
        if exc.status_code != 429:
            return
        previous = self._backoff_seconds or 15
        self._backoff_seconds = min(120, max(30, previous * 2))
        self._backoff_until = time.time() + self._backoff_seconds
        logger.warning(
            "Cloud rate-limited (429) — backing off %ss (heartbeat/telemetry paused)",
            self._backoff_seconds,
        )

    def _clear_backoff(self) -> None:
        if self._backoff_seconds or self._backoff_until:
            logger.info("Cloud rate-limit backoff cleared")
        self._backoff_seconds = 0
        self._backoff_until = 0.0

    def _read_cache_key(
        self, action: str, resource_id: str | None, payload: dict[str, Any]
    ) -> str:
        rid = str(resource_id or "")
        if action == "server.console.read":
            return (
                f"{action}:{rid}:"
                f"{payload.get('limit', 200)}:{payload.get('after_seq', 0)}"
            )
        return f"{action}:{rid}"

    def _cached_read(
        self, action: str, resource_id: str | None, payload: dict[str, Any]
    ) -> dict[str, Any] | None:
        key = self._read_cache_key(action, resource_id, payload)
        hit = self._read_cache.get(key)
        if hit is None:
            return None
        ts, result = hit
        if time.time() - ts > self._READ_CACHE_TTL:
            self._read_cache.pop(key, None)
            return None
        return result

    def _store_read(
        self,
        action: str,
        resource_id: str | None,
        payload: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        if len(self._read_cache) > 64:
            self._read_cache.clear()
        key = self._read_cache_key(action, resource_id, payload)
        self._read_cache[key] = (time.time(), result)

    def _token(self) -> str | None:
        return self.store.load_credentials().token

    async def tick(self) -> dict[str, Any]:
        """One control-plane cycle. Returns a summary for logging/tests."""
        token = self._token()
        identity = self.store.load_identity()
        if not token or identity is None:
            return {"skipped": True, "reason": "unregistered"}

        summary: dict[str, Any] = {"heartbeat": False, "commands": 0, "telemetry": False}
        chatter = not self._in_backoff()
        if not chatter:
            summary["backoff_seconds"] = int(self._backoff_until - time.time()) + 1

        if chatter:
            try:
                bind_summary = await self.app.bindings.refresh(
                    self.client, token, identity=identity
                )
                summary["bindings_refresh"] = bind_summary
                try:
                    summary["bound_locals"] = await self._ensure_bound_locals()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("ensure bound locals failed: %s", exc)
            except CloudError as exc:
                self._note_cloud_error(exc)
                logger.debug("bindings refresh failed: %s", exc)

            try:
                await self.client.heartbeat(
                    token,
                    status="online",
                    agent_version=identity.agent_version or None,
                    platform=identity.platform or None,
                    arch=identity.architecture or None,
                    capabilities=identity.capabilities,
                )
                identity.status = AgentStatus.ONLINE
                identity.touch()
                self.store.save_identity(identity)
                summary["heartbeat"] = True
            except CloudError as exc:
                self._note_cloud_error(exc)
                logger.warning("Heartbeat failed: %s", exc)
                if exc.status_code in {401, 403}:
                    identity.status = AgentStatus.REVOKED
                    self.store.save_identity(identity)
                    return {"skipped": True, "reason": "revoked", "error": str(exc)}
                identity.status = AgentStatus.DEGRADED
                self.store.save_identity(identity)
                summary["error"] = str(exc)

        try:
            poll = await self.client.poll(token)
            data = poll.get("data") if isinstance(poll.get("data"), dict) else poll
            interval = data.get("poll_interval_seconds")
            if isinstance(interval, int) and interval >= 5:
                self._poll_interval = interval

            commands = data.get("commands") or []
            for cmd in commands:
                if not isinstance(cmd, dict):
                    continue
                await self._execute_command(token, cmd)
                summary["commands"] = int(summary["commands"]) + 1

            desired = data.get("desired_workloads") or []
            if desired:
                await self._sync_workloads(token, desired)
                summary["workloads"] = len(desired)
        except CloudError as exc:
            self._note_cloud_error(exc)
            logger.warning("Poll failed: %s", exc)
            summary["poll_error"] = str(exc)

        if chatter and not self._in_backoff():
            try:
                metrics = await self._build_telemetry()
                await self.client.publish_telemetry(token, metrics=metrics, schema_version=1)
                summary["telemetry"] = True
            except CloudError as exc:
                self._note_cloud_error(exc)
                logger.warning("Telemetry failed: %s", exc)
                summary["telemetry_error"] = str(exc)

            try:
                presence = await self._sync_guild_presence(token)
                summary["presence"] = presence
            except Exception as exc:  # noqa: BLE001
                logger.debug("guild presence sync failed: %s", exc)
                summary["presence_error"] = str(exc)

        if summary.get("heartbeat") and summary.get("telemetry"):
            self._clear_backoff()

        return summary

    def _bound_server_label(self, cloud_id: str) -> str:
        for row in self.app.bindings.servers:
            rid = str(row.get("id") or row.get("server_id") or "")
            if rid == cloud_id:
                return str(row.get("name") or row.get("display_name") or cloud_id)
        return cloud_id

    def _cloud_server_row(self, cloud_id: str) -> dict[str, Any]:
        for row in self.app.bindings.servers:
            rid = str(row.get("id") or row.get("server_id") or "")
            if rid == cloud_id:
                return row
        return {}

    async def _sync_bound_record(
        self,
        record: Any,
        cloud_id: str,
        binding: dict[str, Any],
    ) -> None:
        from cultagent.guild.servers_view import guild_server_build_id

        row = self._cloud_server_row(cloud_id)
        scope = str(binding.get("scope") or self.app.bindings.mode)
        meta = dict(record.metadata or {})
        if scope == "personal":
            meta["personal_server_id"] = cloud_id
            meta["scope"] = "personal"
        else:
            meta["guild_server_id"] = cloud_id
            meta["scope"] = "guild"
        meta["cloud_server_id"] = cloud_id
        if binding.get("workload_id"):
            meta["workload_id"] = binding.get("workload_id")
        bid = guild_server_build_id(row) or meta.get("build_id")
        if bid:
            meta["build_id"] = str(bid)

        loader = row.get("loader") or row.get("software") or row.get("platform")
        new_loader = str(loader) if loader else record.loader
        mc = (
            row.get("minecraft_version")
            or row.get("mc_version")
            or row.get("version")
        )
        new_mc = (
            str(mc)
            if mc and not str(mc).startswith("srv_")
            else record.minecraft_version
        )
        name = str(row.get("name") or row.get("display_name") or "").strip()
        new_name = name or record.name
        new_build_id = str(bid) if bid else record.build_id

        unchanged = (
            meta == (record.metadata or {})
            and new_loader == record.loader
            and new_mc == record.minecraft_version
            and new_name == record.name
            and new_build_id == record.build_id
        )
        if unchanged:
            return

        record.loader = new_loader
        record.minecraft_version = new_mc
        record.name = new_name
        if new_build_id:
            record.build_id = new_build_id
        record.metadata = meta
        await self.app.servers.update_record(record)

    async def _ensure_bound_locals(self) -> dict[str, Any]:
        """Bind = this PC hosts that cloud server. Create a local catalog row if missing.

        Does not download a jar or start the process — that is start/provision.
        Uses the cloud server id as the local id so launcher commands for
        ``srv_…`` / ``upsrv_…`` resolve.
        """
        created: list[str] = []
        skipped: list[str] = []
        for binding in self.app.bindings.active_bindings():
            cloud_id = self.app.bindings.cloud_server_id(binding)
            if not cloud_id:
                cloud_id = str(
                    binding.get("guild_server_id")
                    or binding.get("personal_server_id")
                    or ""
                ).strip() or None
            if not cloud_id:
                continue
            existing = self.app.servers.resolve_local_id(cloud_id)
            if existing:
                record = await self.app.servers.get(existing)
                if record is not None:
                    await self._sync_bound_record(record, cloud_id, binding)
                skipped.append(cloud_id)
                continue
            name = self._bound_server_label(cloud_id)
            record = await self.app.servers.create(name, server_id=cloud_id)
            await self._sync_bound_record(record, cloud_id, binding)
            created.append(record.server_id)
            logger.info("Bound server materialized locally %s (%s)", name, record.server_id)
        return {"created": created, "already": skipped}

    async def _execute_command(self, token: str, cmd: dict[str, Any]) -> None:
        command_id = str(cmd.get("id") or cmd.get("command_id") or "")
        if command_id and command_id in self._seen_command_ids:
            return
        if command_id:
            self._seen_command_ids.add(command_id)
            if len(self._seen_command_ids) > 500:
                self._seen_command_ids.clear()
        action = normalize_action(str(cmd.get("action") or ""))
        if not action:
            return
        payload = cmd.get("payload") if isinstance(cmd.get("payload"), dict) else {}
        actor_id = cmd.get("actor_user_id")
        resource_id = (
            payload.get("local_server_id")
            or payload.get("resource_id")
            or payload.get("server_id")
        )
        if not resource_id:
            wl = payload.get("workload_id") or cmd.get("workload_id")
            if wl:
                binding = self.app.bindings.binding_for_workload(str(wl))
                if binding:
                    resource_id = self.app.bindings.cloud_server_id(binding)
        if resource_id:
            mapped = self.app.servers.resolve_local_id(str(resource_id))
            if mapped:
                resource_id = mapped

        await self.app.audit.record(
            actor_id=str(actor_id) if actor_id else None,
            resource_id=str(resource_id) if resource_id else None,
            operation=f"cloud.{action}",
            extra={"command_id": command_id},
        )

        try:
            if action in self._READ_ACTIONS:
                cached = self._cached_read(action, str(resource_id) if resource_id else None, payload)
                if cached is not None:
                    await self.client.report_command_result(
                        token,
                        command_id,
                        success=bool(cached.get("ok")),
                        result=cached,
                    )
                    return
            result = await self.app.dispatch(
                action,
                params=dict(payload),
                actor_id=str(actor_id) if actor_id else None,
                resource_id=str(resource_id) if resource_id else None,
            )
            success = bool(result.get("ok"))
            if action in self._READ_ACTIONS and success:
                self._store_read(
                    action,
                    str(resource_id) if resource_id else None,
                    payload,
                    result,
                )
            await self.client.report_command_result(
                token,
                command_id,
                success=success,
                result=result,
            )
        except CloudError as exc:
            self._note_cloud_error(exc)
            logger.warning("Cloud command report failed for %s: %s", command_id, exc)
        except Exception as exc:  # noqa: BLE001
            logger.exception("Cloud command failed: %s", action)
            try:
                await self.client.report_command_result(
                    token,
                    command_id,
                    success=False,
                    result={"ok": False, "error": str(exc), "command": action},
                )
            except CloudError as report_exc:
                self._note_cloud_error(report_exc)
                logger.warning("Failed to report command result for %s", command_id)

    async def _sync_workloads(self, token: str, desired: list[Any]) -> None:
        reports: list[dict[str, Any]] = []
        for item in desired:
            if not isinstance(item, dict):
                continue
            local_id = item.get("local_server_id")
            workload_id = item.get("id")
            want = str(item.get("desired_state") or "stopped").lower()
            reported = "unknown"
            meta: dict[str, Any] = {}

            if local_id:
                try:
                    status = await self.app.servers.status(str(local_id))
                    reported = status.state.value
                    meta = {"pid": status.pid, "name": status.name}
                    if want == "running" and status.state.value != "running":
                        try:
                            await self.app.servers.start(str(local_id))
                            reported = "running"
                        except Exception as exc:  # noqa: BLE001
                            meta["start_error"] = str(exc)
                    elif want == "stopped" and status.state.value == "running":
                        await self.app.servers.stop(str(local_id))
                        reported = "stopped"
                    elif want == "restart":
                        await self.app.servers.restart(str(local_id))
                        reported = "running"
                except KeyError:
                    reported = "missing"
                    meta["error"] = "local_server_id not found"

            reports.append(
                {
                    "workload_id": workload_id,
                    "local_server_id": local_id,
                    "reported_state": reported,
                    "reported_meta": meta,
                }
            )

        if reports:
            await self.client.report_workloads(token, reports)

        # CONTEXT: runtime snapshot + optional tunnel fold-in (tunnel_address/port)
        from cultagent.cloud.guild_payloads import split_join_address

        net = await self.app.network.status()
        public_join = net.get("public_join") or net.get("public_endpoint")
        tunnel_host: str | None = None
        tunnel_port: int | None = None
        if public_join:
            tunnel_host, tunnel_port = split_join_address(str(public_join))
            if not tunnel_host:
                tunnel_host = None

        by_wl = {
            str(r["workload_id"]): r for r in reports if r.get("workload_id")
        }
        mode = self.app.bindings.mode
        for item in desired:
            if not isinstance(item, dict):
                continue
            workload_id = item.get("id")
            if not workload_id:
                continue
            report = by_wl.get(str(workload_id), {})
            binding = self.app.bindings.binding_for_workload(str(workload_id))
            # Never push tunnel/runtime for workloads not bound to THIS agent.
            # Previous loophole: when active_bindings() was empty we still wrote
            # this PC's playit join onto any guild_server_id in desired_workloads,
            # which let a friend's agent overwrite another member's guild server.
            if binding is None:
                logger.debug(
                    "skip runtime/tunnel for workload %s — not bound on this agent",
                    workload_id,
                )
                continue

            guild_server_id = (
                binding.get("guild_server_id")
                or item.get("guild_server_id")
                or item.get("server_id")
            )
            personal_server_id = binding.get("personal_server_id") or item.get(
                "personal_server_id"
            )
            # Prefer binding ids — ignore foreign ids on the workload row.
            bound_guild = str(binding.get("guild_server_id") or "").strip() or None
            bound_personal = str(binding.get("personal_server_id") or "").strip() or None
            if bound_guild:
                guild_server_id = bound_guild
            if bound_personal:
                personal_server_id = bound_personal

            cloud_server_id = (
                str(personal_server_id)
                if personal_server_id
                else (str(guild_server_id) if guild_server_id else None)
            )
            scope = str(binding.get("scope") or mode)

            if not cloud_server_id:
                logger.debug(
                    "skip runtime/tunnel — binding %s has no cloud server id",
                    workload_id,
                )
                continue

            reported_state = str(report.get("reported_state") or "unknown")
            local_id = (
                report.get("local_server_id")
                or item.get("local_server_id")
                or binding.get("local_server_id")
                or binding.get("resource_id")
            )
            # Only publish a public join address when this agent is actually
            # hosting the bound local process (or clearing tunnel on stop).
            hosting = False
            if local_id:
                try:
                    hosting = self.app.servers.is_process_running(str(local_id))
                except Exception:  # noqa: BLE001
                    hosting = False
            publish_tunnel = bool(tunnel_host) and hosting
            clear_tunnel = bool(
                (not hosting)
                and (
                    reported_state in {"stopped", "missing", "offline"}
                    or item.get("network_mode") == "direct"
                )
            )

            mc_version = None
            player_count: int | None = None
            if local_id:
                try:
                    rec = await self.app.servers.get(str(local_id))
                    if rec:
                        mc_version = rec.minecraft_version
                except Exception:  # noqa: BLE001
                    pass
                try:
                    from cultagent.cloud.presence import get_presence_tracker

                    snap = get_presence_tracker().snapshot(str(local_id))
                    player_count = int(snap.get("player_count") or 0)
                except Exception:  # noqa: BLE001
                    player_count = None

            if scope == "personal" and personal_server_id:
                try:
                    await self.app.cloud_client.upsert_personal_runtime(
                        token,
                        str(personal_server_id),
                        workload_id=str(workload_id),
                        reported_state=reported_state,
                        minecraft_version=mc_version,
                        player_count=player_count,
                        tunnel_address=tunnel_host if publish_tunnel else None,
                        tunnel_port=tunnel_port if publish_tunnel else None,
                        network_mode="playit" if publish_tunnel else "direct",
                        clear_tunnel=clear_tunnel and not publish_tunnel,
                    )
                except CloudError as exc:
                    logger.debug("personal runtime upsert skipped: %s", exc)
                if personal_server_id and publish_tunnel:
                    try:
                        await self.app.cloud_client.set_personal_server_tunnel(
                            token,
                            str(personal_server_id),
                            workload_id=str(workload_id),
                            tunnel_address=tunnel_host,
                            tunnel_port=tunnel_port,
                            network_mode="playit",
                            tunnel_meta={"provider": "playit"},
                        )
                    except CloudError as exc:
                        logger.debug("personal tunnel override skipped: %s", exc)
                continue

            if scope != "personal" and guild_server_id:
                try:
                    await self.client.upsert_guild_runtime(
                        token,
                        workload_id=str(workload_id),
                        state=reported_state,
                        player_count=player_count,
                        tunnel_address=tunnel_host if publish_tunnel else None,
                        tunnel_port=tunnel_port if publish_tunnel else None,
                        network_mode="playit" if publish_tunnel else "direct",
                        clear_tunnel=clear_tunnel and not publish_tunnel,
                        guild_server_id=str(guild_server_id),
                        local_server_id=str(local_id) if local_id else None,
                    )
                except CloudError as exc:
                    logger.debug("guild runtime upsert skipped: %s", exc)

                if publish_tunnel:
                    try:
                        await self.client.set_guild_server_tunnel(
                            token,
                            str(guild_server_id),
                            workload_id=str(workload_id),
                            tunnel_address=tunnel_host,
                            tunnel_port=tunnel_port,
                            network_mode="playit",
                            tunnel_meta={"provider": "playit"},
                        )
                    except CloudError as exc:
                        logger.debug("guild tunnel override skipped: %s", exc)

    async def _sync_guild_presence(self, token: str) -> dict[str, Any]:
        """Ingest console → POST guild players/events (live manifest routes)."""
        from cultagent.cloud.presence import get_presence_tracker

        tracker = get_presence_tracker()
        summary: dict[str, Any] = {"servers": 0, "rosters": 0, "events": 0, "lists": 0}

        for binding in self.app.bindings.active_bindings():
            scope = str(binding.get("scope") or self.app.bindings.mode)
            if scope == "personal":
                continue
            workload_id = binding.get("workload_id")
            cloud_id = self.app.bindings.cloud_server_id(binding)
            if not workload_id or not cloud_id:
                continue
            local_id = self.app.servers.resolve_local_id(str(cloud_id))
            if not local_id or not self.app.servers.is_process_running(local_id):
                continue

            summary["servers"] = int(summary["servers"]) + 1
            sp = tracker.for_server(local_id)
            sp.ticks_since_list += 1

            try:
                snap = await self.app.servers.console_read(
                    local_id, limit=200, after_seq=sp.console_seq
                )
                lines = snap.get("lines") or []
                tracker.ingest_lines(local_id, lines if isinstance(lines, list) else [])
                if snap.get("seq"):
                    sp.console_seq = max(sp.console_seq, int(snap["seq"]))
            except Exception as exc:  # noqa: BLE001
                logger.debug("presence console read failed %s: %s", local_id, exc)

            # Refresh roster from /list every ~2 minutes (8 ticks @ 15s) or when empty.
            if sp.ticks_since_list >= 8 or (not sp.online and sp.ticks_since_list >= 2):
                try:
                    await self.app.servers.console_execute(local_id, "list")
                    summary["lists"] = int(summary["lists"]) + 1
                    sp.ticks_since_list = 0
                    await asyncio.sleep(0.35)
                    snap2 = await self.app.servers.console_read(
                        local_id, limit=30, after_seq=sp.console_seq
                    )
                    tracker.ingest_lines(local_id, snap2.get("lines") or [])
                    if snap2.get("seq"):
                        sp.console_seq = max(sp.console_seq, int(snap2["seq"]))
                except Exception as exc:  # noqa: BLE001
                    logger.debug("presence list failed %s: %s", local_id, exc)

            roster = tracker.snapshot(local_id)
            try:
                await self.client.replace_guild_players(
                    token,
                    workload_id=str(workload_id),
                    players=list(roster.get("players") or []),
                )
                tracker.mark_roster_synced(local_id)
                summary["rosters"] = int(summary["rosters"]) + 1
            except CloudError as exc:
                logger.debug("replace_guild_players skipped: %s", exc)

            events = tracker.drain_events(local_id, limit=50)
            if events:
                # Attach workload for API correlation when supported.
                for ev in events:
                    ev.setdefault("workload_id", str(workload_id))
                    if cloud_id:
                        ev.setdefault("guild_server_id", str(cloud_id))
                try:
                    await self.client.append_guild_events(token, events=events)
                    summary["events"] = int(summary["events"]) + len(events)
                except CloudError as exc:
                    logger.debug("append_guild_events skipped: %s", exc)

        return summary

    async def _build_telemetry(self) -> dict[str, Any]:
        from cultagent.cloud.activity_bridge import get_activity_bridge
        from cultagent.cloud.presence import get_presence_tracker

        raw = await self.app.metrics.collect()
        network = await self.app.network.status()
        identity = self.store.export_public()
        bridge = get_activity_bridge()
        activity = bridge.snapshot_activity()
        consoles = await bridge.snapshot_consoles(self.app.servers)
        tracker = get_presence_tracker()
        presence_rows: list[dict[str, Any]] = []
        for record in await self.app.servers.list_servers():
            if not self.app.servers.is_process_running(record.server_id):
                continue
            presence_rows.append(tracker.snapshot(record.server_id))
        return {
            "schema_version": 1,
            "public": {
                "node_id": identity.get("node_id"),
                "status": identity.get("status"),
                "platform": identity.get("platform"),
                "agent_version": identity.get("agent_version"),
            },
            "system": raw.get("system") or {},
            "minecraft": {
                **(raw.get("minecraft") or {}),
                "presence": presence_rows,
            },
            "network": {**(raw.get("network") or {}), **network},
            "activity": activity,
            "consoles": consoles,
            "presence": presence_rows,
        }
