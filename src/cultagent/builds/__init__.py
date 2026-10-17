"""Guild build list / provision / install orchestration."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cultagent.cloud.client import CloudError
from cultagent.servers.install import jar_present

if TYPE_CHECKING:
    from cultagent.app import CultAgentApp

logger = logging.getLogger("cultagent.builds")


class BuildsOrchestrator:
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

    async def list_builds(self, *, limit: int = 50) -> list[dict[str, Any]]:
        token = self._token()
        try:
            payload = await self.app.cloud_client.search_builds(token, limit=limit)
            data = self._unwrap(payload)
            if isinstance(data, list):
                return [b if isinstance(b, dict) else {} for b in data]
            if isinstance(data, dict):
                for key in ("builds", "items", "results"):
                    items = data.get(key)
                    if isinstance(items, list):
                        return [b if isinstance(b, dict) else {} for b in items]
        except CloudError as exc:
            if exc.status_code not in {404, 405}:
                raise
            logger.debug("builds search unavailable, falling back to guild list: %s", exc)
        payload = await self.app.cloud_client.list_guild_builds(token, limit=limit)
        data = self._unwrap(payload)
        if isinstance(data, list):
            return [b if isinstance(b, dict) else {} for b in data]
        return []

    async def search_builds(
        self,
        *,
        q: str | None = None,
        keywords: str | None = None,
        loader: str | None = None,
        minecraft_version: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        payload = await self.app.cloud_client.search_builds(
            self._token(),
            q=q,
            keywords=keywords,
            loader=loader,
            minecraft_version=minecraft_version,
            limit=limit,
            offset=offset,
        )
        data = self._unwrap(payload)
        if isinstance(data, list):
            return [b if isinstance(b, dict) else {} for b in data]
        if isinstance(data, dict):
            for key in ("builds", "items", "results"):
                items = data.get(key)
                if isinstance(items, list):
                    return [b if isinstance(b, dict) else {} for b in items]
        return []

    @staticmethod
    def builds_by_id(builds: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        out: dict[str, dict[str, Any]] = {}
        for b in builds:
            if not isinstance(b, dict):
                continue
            for key in ("id", "build_id"):
                val = b.get(key)
                if val:
                    out[str(val)] = b
        return out

    async def find_build(self, build_id: str) -> dict[str, Any] | None:
        """Locate a published guild build row by id (from list endpoint)."""
        builds = await self.list_builds(limit=100)
        return self.builds_by_id(builds).get(str(build_id))

    async def get_manifest(self, build_id: str) -> dict[str, Any]:
        token = self._token()
        try:
            payload = await self.app.cloud_client.get_build_manifest(token, build_id)
        except CloudError as exc:
            if exc.status_code not in {404, 405}:
                raise
            payload = await self.app.cloud_client.get_guild_build_manifest(
                token, build_id
            )
        data = self._unwrap(payload)
        if not isinstance(data, dict):
            raise CloudError("Invalid manifest response")
        return data

    async def provision(
        self,
        build_id: str,
        *,
        create_local_server: bool = True,
        install: bool = True,
        desired_state: str = "stopped",
        display_name: str | None = None,
        include_optional: bool = False,
        network_mode: str = "direct",
    ) -> dict[str, Any]:
        """Option A: create cloud workload (+ local server) and install manifest."""
        local_server_id: str | None = None
        record = None
        if create_local_server:
            name = display_name or build_id
            mc = None
            loader = None
            try:
                builds = await self.list_builds()
                for b in builds:
                    if b.get("id") == build_id:
                        name = display_name or str(b.get("name") or name)
                        mc = b.get("minecraft_version")
                        loader = b.get("loader")
                        break
            except CloudError:
                logger.warning("Could not list builds before provision; creating bare server")
            record = await self.app.servers.create(
                name,
                minecraft_version=str(mc) if mc else None,
                loader=str(loader) if loader else None,
                accept_eula=False,
            )
            local_server_id = record.server_id

        try:
            payload = await self.app.cloud_client.provision_build(
                self._token(),
                build_id,
                desired_state=desired_state,
                display_name=display_name or (record.name if record else None),
                local_server_id=local_server_id,
                network_mode=network_mode,
            )
        except CloudError as exc:
            if exc.status_code not in {404, 405}:
                raise
            payload = await self.app.cloud_client.provision_from_build(
                self._token(),
                build_id,
                desired_state=desired_state,
                display_name=display_name or (record.name if record else None),
                local_server_id=local_server_id,
                network_mode=network_mode,
            )
        data = self._unwrap(payload)
        if not isinstance(data, dict):
            raise CloudError("Invalid provision response")

        manifest = data.get("manifest") if isinstance(data.get("manifest"), dict) else {}
        workload = data.get("workload") if isinstance(data.get("workload"), dict) else {}
        build = data.get("build") if isinstance(data.get("build"), dict) else {}

        install_result: dict[str, Any] | None = None
        if install and local_server_id:
            # Full shoot: platform jar/libraries + content (mods/packs)
            install_result = await self.install_to_server(
                build_id,
                local_server_id,
                include_optional=include_optional,
                install_platform=True,
                accept_eula=True,
            )
            # Report workload linkage back to cloud.
            try:
                await self.app.cloud_client.report_workloads(
                    self._token(),
                    [
                        {
                            "workload_id": workload.get("id"),
                            "local_server_id": local_server_id,
                            "reported_state": "stopped",
                            "reported_meta": {
                                "install_ok": bool(
                                    (install_result.get("install") or {}).get("ok", True)
                                ),
                                "installed_count": len(
                                    (install_result.get("install") or {}).get("installed")
                                    or []
                                ),
                                "launch_ready": bool(install_result.get("launch_ready")),
                            },
                            "minecraft_version": build.get("minecraft_version")
                            or manifest.get("minecraft_version"),
                            "loader": build.get("loader") or manifest.get("loader"),
                            "network_mode": network_mode,
                        }
                    ],
                )
            except CloudError as exc:
                logger.warning("workload report after install failed: %s", exc)

        return {
            "workload": workload,
            "build": build,
            "manifest": manifest,
            "local_server_id": local_server_id,
            "install": install_result,
        }

    async def install_to_server(
        self,
        build_id: str,
        server_id: str,
        *,
        include_optional: bool = False,
        install_platform: bool = True,
        force_platform: bool = False,
        accept_eula: bool = True,
        loader_version: str | None = None,
        resolve_deps: bool = False,
    ) -> dict[str, Any]:
        """Shoot a chambered build: install server platform, then content files.

        Guild manifests are content-only (mods / packs). The Minecraft *server*
        jar + Forge/NeoForge libraries come from the local installer, not the
        cloud file list. Content files use pinned URLs/hashes from the
        manifest — Modrinth "latest" is not re-resolved unless
        ``resolve_deps=True``.
        """
        record = await self.app.servers.get(server_id)
        if record is None:
            raise KeyError(f"unknown server: {server_id}")
        manifest = await self.get_manifest(build_id)

        loader = str(
            manifest.get("loader") or record.loader or "vanilla"
        ).strip().lower()
        mc = str(
            manifest.get("minecraft_version")
            or record.minecraft_version
            or ""
        ).strip() or None
        pin = (
            loader_version
            or manifest.get("loader_version")
            or manifest.get("forge_version")
            or manifest.get("neoforge_version")
        )
        pin_s = str(pin) if pin else None

        if accept_eula:
            await self.app.servers.accept_eula(server_id)

        platform_info: dict[str, Any] | None = None
        if install_platform and mc:
            record = await self.app.servers.get(server_id)
            assert record is not None
            need = force_platform or not jar_present(record)
            if need:
                logger.info(
                    "Installing server platform %s %s for %s (build %s)",
                    loader,
                    mc,
                    server_id,
                    build_id,
                )
                platform_info = await self.app.servers.install_loader(
                    server_id,
                    loader=loader,
                    version=mc,
                    loader_version=pin_s,
                )
                platform_info = {
                    **platform_info,
                    "installed": True,
                    "skipped": False,
                }
            else:
                platform_info = {
                    "installed": False,
                    "skipped": True,
                    "reason": "already_installed",
                    "loader": record.loader,
                    "version": record.minecraft_version,
                    "execution_command": record.execution_command,
                    "jar": str(Path(record.path) / record.executable),
                }
        elif install_platform and not mc:
            platform_info = {
                "installed": False,
                "skipped": True,
                "reason": "no_minecraft_version",
            }

        record = await self.app.servers.get(server_id)
        assert record is not None
        result = await self.app.content.deploy_cloud_manifest(
            manifest,
            record.path,
            include_optional=include_optional,
            cache_dir=self.app.paths.cache_dir,
            loader=loader,
            game_version=mc,
            resolve_deps=resolve_deps,
        )
        # Sync chambered magazine metadata onto the local server record
        record = await self.app.servers.get(server_id)
        assert record is not None
        record.build_id = build_id
        if loader:
            record.loader = loader
        if mc:
            record.minecraft_version = mc
        meta = dict(record.metadata or {})
        meta["build_id"] = build_id
        meta["chambered"] = True
        meta["platform_ready"] = bool(
            platform_info
            and (platform_info.get("installed") or platform_info.get("skipped"))
        )
        if manifest.get("name"):
            meta["build_name"] = manifest.get("name")
        record.metadata = meta
        await self.app.servers.update_record(record)
        await self.app.audit.record(
            resource_id=server_id,
            operation="build.install",
            result="ok" if result.get("ok") else "error",
            extra={
                "build_id": build_id,
                "platform": (platform_info or {}).get("reason")
                or (
                    "installed"
                    if (platform_info or {}).get("installed")
                    else "skipped"
                ),
            },
        )
        return {
            "server_id": server_id,
            "build_id": build_id,
            "loader": record.loader,
            "minecraft_version": record.minecraft_version,
            "platform": platform_info,
            "install": result,
            "launch_ready": jar_present(record),
            "execution_command": record.execution_command or None,
        }
