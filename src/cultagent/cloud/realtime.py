"""Cloud realtime transport: prefer WebSocket when API advertises it, else HTTPS poll."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from cultagent.cloud.manifest import _collect_uris, fetch_api_manifest
from cultagent.cloud.realtime_discover import api_base_to_ws_url, discover_agent_ws
from cultagent.identity import AgentStatus

if TYPE_CHECKING:
    from cultagent.app import CultAgentApp
    from cultagent.cloud.control_plane import ControlPlane

logger = logging.getLogger("cultagent.cloud.realtime")


class CloudRealtime:
    """Runs alongside the control plane: auto-upgrade to WS when available."""

    def __init__(self, app: CultAgentApp, control_plane: ControlPlane) -> None:
        self.app = app
        self.control_plane = control_plane
        self.mode: str = "poll"  # poll | websocket
        self.ws_path: str | None = None
        self.connected: bool = False
        self._discover_interval = 300.0
        self._ws: Any = None
        self._reader_task: asyncio.Task[None] | None = None
        self._last_telemetry = 0.0

    def status_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "connected": self.connected,
            "ws_path": self.ws_path,
            "prefer_realtime": bool(self.app.config.cloud.realtime_enabled),
        }

    async def discover(self) -> str | None:
        """Check live manifest for an agent WebSocket route."""
        if not self.app.config.cloud.realtime_enabled:
            return None
        try:
            manifest = await fetch_api_manifest(self.app.config.cloud)
            path = discover_agent_ws(manifest, uris=_collect_uris(manifest))
            return path
        except Exception as exc:  # noqa: BLE001
            logger.debug("Realtime discovery failed: %s", exc)
            return None

    async def run(self) -> None:
        """Poll always. WebSocket is an extra push path with the same command shape."""
        prefer = bool(self.app.config.cloud.realtime_enabled)
        if prefer:
            path = await self.discover()
            if path:
                logger.info(
                    "Cloud WebSocket advertised at %s — connecting (poll stays on)",
                    path,
                )
                await self._connect_ws(path)
            else:
                logger.info("Cloud using HTTPS poll (API has no agent WebSocket yet)")
        else:
            logger.info("Cloud realtime disabled — HTTPS poll only")

        next_discover = asyncio.get_event_loop().time() + self._discover_interval

        while self.app._running:  # noqa: SLF001
            now = asyncio.get_event_loop().time()

            if prefer and now >= next_discover:
                next_discover = now + self._discover_interval
                path = await self.discover()
                if path and not self.connected:
                    logger.info("Cloud WebSocket available — connecting (poll stays on)")
                    await self._connect_ws(path)
                elif not path and self.connected:
                    logger.info("Cloud WebSocket removed from manifest — poll only")
                    await self._disconnect_ws()

            try:
                summary = await self.control_plane.tick()
                if summary.get("commands"):
                    logger.info(
                        "Control plane: executed %s cloud command(s)",
                        summary["commands"],
                    )
                if summary.get("reason") == "revoked":
                    logger.error("Agent token revoked — stopping control plane loop")
                    break
            except Exception:  # noqa: BLE001
                logger.exception("Control plane tick failed")
            await asyncio.sleep(self.control_plane.poll_interval)

        await self._disconnect_ws()

    async def _connect_ws(self, path: str) -> None:
        token = self.control_plane._token()  # noqa: SLF001
        if not token:
            return
        url = api_base_to_ws_url(self.app.config.cloud.api_base, path)
        try:
            import inspect

            import websockets  # noqa: F401 — ensure package is importable when frozen
            import websockets.asyncio  # noqa: F401 — Nuitka must include asyncio backend
            import websockets.asyncio.client  # noqa: F401

            kwargs: dict[str, Any] = {
                "open_timeout": 20,
                "ping_interval": 20,
                "ping_timeout": 20,
            }
            params = inspect.signature(websockets.connect).parameters
            if "additional_headers" in params:
                kwargs["additional_headers"] = {"Authorization": f"Bearer {token}"}
            elif "extra_headers" in params:
                kwargs["extra_headers"] = {"Authorization": f"Bearer {token}"}
            self._ws = await websockets.connect(url, **kwargs)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cloud WebSocket connect failed (%s) — staying on poll", exc)
            self._ws = None
            self.connected = False
            self.mode = "poll"
            return

        self.ws_path = path
        self.mode = "websocket"
        self.connected = True
        identity = self.app.identity_store.load_identity()
        hello = {
            "type": "hello",
            "agent_version": identity.agent_version if identity else None,
            "node_id": identity.node_id if identity else None,
            "capabilities": list(identity.capabilities) if identity else [],
        }
        try:
            await self._ws.send(json.dumps(hello))
        except Exception:  # noqa: BLE001
            await self._disconnect_ws()
            return

        if self._reader_task:
            self._reader_task.cancel()
        self._reader_task = asyncio.create_task(self._ws_reader())
        logger.info("Connected to CultForge realtime (%s)", path)

    async def _disconnect_ws(self) -> None:
        self.connected = False
        self.mode = "poll"
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001
                pass
            self._ws = None

    async def _ws_reader(self) -> None:
        assert self._ws is not None
        try:
            async for raw in self._ws:
                try:
                    msg = json.loads(raw) if isinstance(raw, str) else json.loads(raw.decode())
                except Exception:  # noqa: BLE001
                    continue
                if not isinstance(msg, dict):
                    continue
                await self._handle_ws_message(msg)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Cloud realtime dropped (%s) — back to polling", exc)
        finally:
            was = self.connected
            self.connected = False
            self.mode = "poll"
            self._ws = None
            if was:
                logger.info("Realtime session ended — using HTTPS poll")

    async def _handle_ws_message(self, msg: dict[str, Any]) -> None:
        mtype = str(msg.get("type") or "").lower()
        if mtype in {"ping", "keepalive"}:
            await self._ws_send({"type": "pong"})
            return
        # Same job as a poll item: { type: "command", id, action, payload }.
        if mtype == "command":
            token = self.control_plane._token() or ""
            if token:
                await self.control_plane._execute_command(token, msg)  # noqa: SLF001
            return
        if mtype in {"desired_workloads", "workloads"}:
            token = self.control_plane._token()  # noqa: SLF001
            desired = msg.get("desired_workloads") or msg.get("workloads") or []
            if token and isinstance(desired, list):
                await self.control_plane._sync_workloads(token, desired)  # noqa: SLF001

    async def _ws_send(self, payload: dict[str, Any]) -> None:
        if self._ws is None:
            return
        try:
            await self._ws.send(json.dumps(payload))
        except Exception as exc:  # noqa: BLE001
            logger.debug("WS send failed: %s", exc)

    async def _ws_idle_tick(self) -> None:
        """While on WebSocket: keep identity online + periodic telemetry over HTTP."""
        now = asyncio.get_event_loop().time()
        token = self.control_plane._token()  # noqa: SLF001
        identity = self.app.identity_store.load_identity()
        if not token or identity is None:
            return

        # Lightweight heartbeat over HTTP so revoke still works if WS has no ping auth.
        tel_every = max(15, int(self.app.config.cloud.telemetry_interval_seconds))
        if now - self._last_telemetry >= tel_every:
            self._last_telemetry = now
            try:
                from cultagent.cloud.client import CloudError

                await self.control_plane.client.heartbeat(
                    token,
                    status="online",
                    agent_version=identity.agent_version or None,
                    platform=identity.platform or None,
                    arch=identity.architecture or None,
                    capabilities=identity.capabilities,
                )
                identity.status = AgentStatus.ONLINE
                identity.touch()
                self.app.identity_store.save_identity(identity)
                metrics = await self.control_plane._build_telemetry()  # noqa: SLF001
                await self.control_plane.client.publish_telemetry(
                    token, metrics=metrics, schema_version=1
                )
                # Also push over WS when connected (forward-compatible)
                await self._ws_send({"type": "telemetry", "metrics": metrics})
            except Exception as exc:  # noqa: BLE001
                from cultagent.cloud.client import CloudError

                if isinstance(exc, CloudError) and exc.status_code in {401, 403}:
                    identity.status = AgentStatus.REVOKED
                    self.app.identity_store.save_identity(identity)
                    await self._disconnect_ws()
                else:
                    logger.debug("Realtime idle tick failed: %s", exc)
