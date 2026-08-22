"""Network manager abstraction (playit.gg, direct port, future providers)."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any

from cultagent.network.playit import PlayitAgent
from cultagent.network.types import NetworkStatus, TunnelState
from cultagent.settings import NetworkSection

logger = logging.getLogger("cultagent.network")

__all__ = [
    "DirectPortProvider",
    "NetworkManager",
    "NetworkProvider",
    "NetworkStatus",
    "PlayitProvider",
    "TunnelState",
]


class NetworkProvider(ABC):
    name: str

    @abstractmethod
    async def status(self) -> NetworkStatus:
        raise NotImplementedError

    @abstractmethod
    async def restart(self) -> NetworkStatus:
        raise NotImplementedError

    @abstractmethod
    async def configure(self, options: dict[str, Any]) -> None:
        raise NotImplementedError


class DirectPortProvider(NetworkProvider):
    name = "direct"

    def __init__(self, host: str = "0.0.0.0", port: int = 25565) -> None:
        self.host = host
        self.port = port

    async def status(self) -> NetworkStatus:
        return NetworkStatus(
            provider=self.name,
            status=TunnelState.ONLINE,
            target=f"{self.host}:{self.port}",
            public_endpoint=None,
            details={"mode": "direct_port"},
        )

    async def restart(self) -> NetworkStatus:
        return await self.status()

    async def configure(self, options: dict[str, Any]) -> None:
        if "port" in options:
            self.port = int(options["port"])
        if "host" in options:
            self.host = str(options["host"])


class PlayitProvider(NetworkProvider):
    """playit.gg integration — download agent, store secret, supervise process."""

    name = "playit"

    def __init__(self, agent: PlayitAgent) -> None:
        self.agent = agent

    @property
    def enabled(self) -> bool:
        return self.agent.enabled

    async def status(self) -> NetworkStatus:
        return await self.agent.as_network_status()

    async def restart(self) -> NetworkStatus:
        if not self.agent.enabled and not self.agent.has_secret():
            return await self.status()
        await self.agent.restart()
        return await self.status()

    async def configure(self, options: dict[str, Any]) -> None:
        if "target" in options:
            target = str(options["target"])
            if ":" in target:
                host, _, port_s = target.rpartition(":")
                self.agent.target_host = host or "127.0.0.1"
                self.agent.target_port = int(port_s)
            else:
                self.agent.target_port = int(target)
        if "target_host" in options:
            self.agent.target_host = str(options["target_host"])
        if "target_port" in options:
            self.agent.target_port = int(options["target_port"])
        if "enabled" in options:
            self.agent.enabled = bool(options["enabled"])
        if "auto_start" in options:
            self.agent.auto_start = bool(options["auto_start"])
        if "binary_path" in options:
            self.agent.binary_override = str(options["binary_path"] or "")
        if "secret" in options and options["secret"]:
            self.agent.write_secret(str(options["secret"]))
        self.agent._save_state()  # noqa: SLF001


class NetworkManager:
    def __init__(
        self,
        section: NetworkSection,
        *,
        data_dir: Path | None = None,
    ) -> None:
        self.section = section
        root = Path(data_dir) if data_dir else Path.cwd() / "playit"
        playit_cfg = section.playit
        self.playit = PlayitAgent(
            root,
            target_host=getattr(playit_cfg, "target_host", "127.0.0.1") or "127.0.0.1",
            target_port=int(getattr(playit_cfg, "target_port", 25565) or 25565),
            binary_override=str(getattr(playit_cfg, "binary_path", "") or ""),
            auto_start=bool(getattr(playit_cfg, "auto_start", False)),
            enabled=bool(playit_cfg.enabled),
        )
        # Restore runtime prefs from state file if present
        state = self.playit.load_state()
        if state.get("target_host"):
            self.playit.target_host = str(state["target_host"])
        if state.get("target_port"):
            self.playit.target_port = int(state["target_port"])
        if "auto_start" in state:
            self.playit.auto_start = bool(state["auto_start"])
        if "enabled" in state and not playit_cfg.enabled:
            # config still wins when explicitly enabled in yaml
            self.playit.enabled = bool(state["enabled"])

        self.providers: dict[str, NetworkProvider] = {
            "direct": DirectPortProvider(
                host="0.0.0.0",
                port=self.playit.target_port,
            ),
            "playit": PlayitProvider(self.playit),
        }
        default = section.default_provider
        self.active_name = default if default in self.providers else "direct"
        # CLI commands are short-lived processes. Persist the last chosen
        # provider in playit state.json so `cf-agent network` matches
        # `cf-agent playit-start` instead of always falling back to yaml.
        saved = state.get("active_provider")
        if saved in self.providers:
            self.active_name = str(saved)
        elif self.playit.enabled:
            self.active_name = "playit"

    @property
    def active(self) -> NetworkProvider:
        return self.providers[self.active_name]

    async def status(self) -> dict[str, Any]:
        status = await self.active.status()
        payload = status.model_dump(mode="json")
        payload["active"] = self.active_name
        payload["providers"] = list(self.providers.keys())
        playit_payload: dict[str, Any] | None = None
        if self.active_name != "playit":
            playit_status = await self.playit.as_network_status()
            playit_payload = playit_status.model_dump(mode="json")
            payload["playit"] = playit_payload
        else:
            playit_payload = payload

        public = (
            payload.get("public_join")
            or payload.get("public_endpoint")
            or (playit_payload or {}).get("public_join")
            or (playit_payload or {}).get("public_endpoint")
        )
        if public:
            payload["public_join"] = public
            payload["public_endpoint"] = public
        return payload

    async def restart(self) -> dict[str, Any]:
        status = await self.active.restart()
        return status.model_dump(mode="json")

    def use(self, provider_name: str) -> None:
        if provider_name not in self.providers:
            raise KeyError(f"unknown network provider: {provider_name}")
        self.active_name = provider_name
        if provider_name == "playit":
            self.playit.enabled = True
        self.playit._save_state(active_provider=provider_name)  # noqa: SLF001

    async def configure(self, options: dict[str, Any]) -> dict[str, Any]:
        provider = str(options.get("provider") or self.active_name)
        if provider in self.providers:
            await self.providers[provider].configure(options)
            if options.get("use") or options.get("activate"):
                self.use(provider)
        return await self.status()

    async def install_playit(self, *, force: bool = False) -> dict[str, Any]:
        return await self.playit.install(force=force)

    async def setup_playit(
        self,
        *,
        force: bool = False,
        open_browser: bool = True,
        wait_exchange: bool = True,
        exchange_timeout: float = 300,
    ) -> dict[str, Any]:
        return await self.playit.setup(
            force=force,
            open_browser=open_browser,
            wait_exchange=wait_exchange,
            exchange_timeout=exchange_timeout,
        )

    async def wait_playit_claim(
        self, code: str | None = None, *, timeout: float = 300
    ) -> dict[str, Any]:
        return await self.playit.wait_claim(code, timeout=timeout)

    async def reset_playit(self) -> dict[str, Any]:
        result = await self.playit.reset()
        self.active_name = "direct"
        self.playit._save_state(active_provider="direct")  # noqa: SLF001
        return result

    async def start_playit(self) -> dict[str, Any]:
        self.use("playit")
        return await self.playit.start()

    async def ensure_playit_tunnel(self) -> dict[str, Any]:
        self.use("playit")
        return await self.playit.ensure_minecraft_tunnel()

    async def stop_playit(self) -> dict[str, Any]:
        return await self.playit.stop()

    def set_secret(self, secret: str) -> dict[str, Any]:
        self.playit.write_secret(secret)
        return {"ok": True, "has_secret": True, "secret_path": str(self.playit.secret_path)}

    def playit_logs(self, *, limit: int = 80) -> dict[str, Any]:
        return {"lines": self.playit.recent_logs(limit=limit)}

    async def maybe_autostart(self) -> None:
        if self.active_name != "playit" and not self.playit.auto_start:
            return
        if not (self.playit.enabled or self.playit.auto_start):
            return
        if not self.playit.has_secret() or self.playit.binary_path() is None:
            logger.info("playit auto-start skipped (secret or binary missing)")
            return
        try:
            self.use("playit")
            await self.playit.start()
        except Exception:  # noqa: BLE001
            logger.exception("playit auto-start failed")
