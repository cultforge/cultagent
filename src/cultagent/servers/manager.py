"""Multi-server registry + lifecycle orchestration."""

from __future__ import annotations

import json
import logging
import shutil
import uuid
from pathlib import Path
from typing import Any

from cultagent.servers.eula import is_eula_accepted, write_eula
from cultagent.servers.install import (
    bootstrap_server_dir,
    download_server_jar,
    jar_present,
)
from cultagent.servers.models import ServerRecord, ServerState, ServerStatus
from cultagent.servers.process import ManagedProcess

logger = logging.getLogger("cultagent.servers")


class ServerManager:
    """Local multi-server registry + process lifecycle.

    Process/console patterns follow Crafty's responsibilities (Popen pipes,
    stop-command, virtual console) without importing Crafty code.
    """

    def __init__(
        self,
        servers_dir: Path,
        catalog_path: Path | None = None,
        *,
        default_java_path: str = "",
    ) -> None:
        self.servers_dir = servers_dir
        self.catalog_path = catalog_path or (servers_dir / "catalog.json")
        self.default_java_path = default_java_path
        self._processes: dict[str, ManagedProcess] = {}

    def ensure(self) -> None:
        self.servers_dir.mkdir(parents=True, exist_ok=True)
        if not self.catalog_path.is_file():
            self._write_catalog([])

    def _read_catalog(self) -> list[ServerRecord]:
        if not self.catalog_path.is_file():
            return []
        raw = json.loads(self.catalog_path.read_text(encoding="utf-8"))
        return [ServerRecord.model_validate(item) for item in raw.get("servers", [])]

    def _write_catalog(self, servers: list[ServerRecord]) -> None:
        self.catalog_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"servers": [s.model_dump() for s in servers]}
        self.catalog_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def _upsert(self, record: ServerRecord) -> None:
        servers = self._read_catalog()
        out: list[ServerRecord] = []
        replaced = False
        for existing in servers:
            if existing.server_id == record.server_id:
                out.append(record)
                replaced = True
            else:
                out.append(existing)
        if not replaced:
            out.append(record)
        self._write_catalog(out)

    def _proc(self, record: ServerRecord) -> ManagedProcess:
        existing = self._processes.get(record.server_id)
        if existing is None:
            self._processes[record.server_id] = ManagedProcess(record)
            return self._processes[record.server_id]
        # Never replace a live supervisor — binding/metadata sync used to
        # construct a fresh ManagedProcess and orphan the Java PID (UI=Stopped
        # while Minecraft kept running).
        existing.record = record
        return existing

    async def list_servers(self) -> list[ServerRecord]:
        return self._read_catalog()

    def resolve_local_id(self, server_id: str) -> str | None:
        """Return the catalog id for a local or cloud server id, if installed."""
        sid = str(server_id or "").strip()
        if not sid:
            return None
        for rec in self._read_catalog():
            if rec.server_id == sid:
                return rec.server_id
            meta = rec.metadata or {}
            for key in (
                "guild_server_id",
                "personal_server_id",
                "cloud_server_id",
                "server_id",
            ):
                if str(meta.get(key) or "") == sid:
                    return rec.server_id
        return None

    async def get(self, server_id: str) -> ServerRecord | None:
        for server in self._read_catalog():
            if server.server_id == server_id:
                return server
        return None

    async def create(
        self,
        name: str,
        *,
        minecraft_version: str | None = None,
        loader: str | None = "vanilla",
        port: int = 25565,
        accept_eula: bool = False,
        download_jar: bool = False,
        jvm_args: str = "-Xms1G -Xmx2G",
        server_id: str | None = None,
    ) -> ServerRecord:
        servers = self._read_catalog()
        wanted = str(server_id or "").strip()
        if wanted:
            mapped = self.resolve_local_id(wanted)
            if mapped:
                for existing in servers:
                    if existing.server_id == mapped:
                        return existing
        server_id = wanted or f"srv_{uuid.uuid4().hex[:12]}"
        path = self.servers_dir / server_id
        path.mkdir(parents=True, exist_ok=True)
        record = ServerRecord(
            server_id=server_id,
            name=name,
            path=str(path),
            minecraft_version=minecraft_version,
            loader=loader or "vanilla",
            port=port,
            jvm_args=jvm_args,
            java_path=self.default_java_path,
        )
        bootstrap_server_dir(record, accept_eula=accept_eula)
        if download_jar:
            if not minecraft_version:
                raise ValueError("minecraft_version required when download_jar=True")
            await download_server_jar(
                record, version=minecraft_version, loader=loader or "vanilla"
            )
            # Forge/NeoForge mutate execution_command on the record.
        servers.append(record)
        self._write_catalog(servers)
        self._processes[server_id] = ManagedProcess(record)
        logger.info("Created server %s (%s)", name, server_id)
        return record

    async def update_record(self, record: ServerRecord) -> ServerRecord:
        self._upsert(record)
        existing = self._processes.get(record.server_id)
        if existing is not None:
            existing.record = record
        else:
            self._processes[record.server_id] = ManagedProcess(record)
        return record

    async def remove(
        self,
        server_id: str,
        *,
        delete_files: bool = True,
        force_stop: bool = True,
    ) -> dict[str, Any]:
        """Unregister a local server; optionally delete its folder.

        Stops a running process first (when ``force_stop``). File delete is
        confined to directories under ``servers_dir``.
        """
        record = await self.get(server_id)
        if record is None:
            raise KeyError(f"unknown server: {server_id}")

        stopped = False
        proc = self._processes.get(server_id)
        if proc is not None and proc.is_running():
            if not force_stop:
                raise RuntimeError(f"server {server_id} is running — stop it first")
            await proc.stop()
            stopped = True

        servers = [s for s in self._read_catalog() if s.server_id != server_id]
        self._write_catalog(servers)
        self._processes.pop(server_id, None)

        path = Path(record.path)
        files_deleted = False
        if delete_files and path.exists():
            try:
                path.resolve().relative_to(self.servers_dir.resolve())
            except ValueError as exc:
                raise RuntimeError(
                    f"refusing to delete path outside servers_dir: {path}"
                ) from exc
            shutil.rmtree(path, ignore_errors=False)
            files_deleted = True

        logger.info(
            "Removed server %s (%s) files_deleted=%s stopped=%s",
            record.name,
            server_id,
            files_deleted,
            stopped,
        )
        return {
            "ok": True,
            "removed": True,
            "server_id": server_id,
            "name": record.name,
            "path": record.path,
            "stopped": stopped,
            "files_deleted": files_deleted,
            "kept_files": bool(path.exists()) if not files_deleted else False,
        }

    async def accept_eula(self, server_id: str) -> dict[str, Any]:
        record = await self.get(server_id)
        if record is None:
            raise KeyError(f"unknown server: {server_id}")
        write_eula(Path(record.path), accepted=True)
        return {"server_id": server_id, "eula": True}

    async def install_vanilla(self, server_id: str, version: str | None = None) -> dict[str, Any]:
        return await self.install_loader(server_id, loader="vanilla", version=version)

    async def install_loader(
        self,
        server_id: str,
        *,
        loader: str = "vanilla",
        version: str | None = None,
        loader_version: str | None = None,
    ) -> dict[str, Any]:
        record = await self.get(server_id)
        if record is None:
            raise KeyError(f"unknown server: {server_id}")
        mc_version = version or record.minecraft_version
        if not mc_version:
            raise ValueError("minecraft_version required")
        path = await download_server_jar(
            record,
            version=mc_version,
            loader=loader,
            loader_version=loader_version,
        )
        record.minecraft_version = mc_version
        record.loader = loader
        self._upsert(record)
        existing = self._processes.get(server_id)
        if existing is not None:
            existing.record = record
        else:
            self._processes[server_id] = ManagedProcess(record)
        return {
            "server_id": server_id,
            "jar": str(path),
            "version": mc_version,
            "loader": loader,
            "execution_command": record.execution_command,
            "metadata": record.metadata,
        }

    async def status(self, server_id: str) -> ServerStatus:
        record = await self.get(server_id)
        if record is None:
            raise KeyError(f"unknown server: {server_id}")
        return self._proc(record).status()

    async def start(self, server_id: str, *, accept_eula: bool = False) -> dict[str, Any]:
        record = await self.get(server_id)
        if record is None:
            raise KeyError(f"unknown server: {server_id}")
        if not jar_present(record):
            raise FileNotFoundError(
                f"missing executable {record.executable} in {record.path} — "
                "run install or place a jar"
            )
        if accept_eula:
            write_eula(Path(record.path), accepted=True)
        if not is_eula_accepted(Path(record.path)):
            raise PermissionError(
                "Minecraft EULA not accepted — pass accept_eula=true or run "
                "`cf-agent eula-accept <server_id>`"
            )

        proc = self._proc(record)
        status = await proc.start(java_path=self.default_java_path or None)
        return {
            "server_id": server_id,
            "state": status.state.value,
            "pid": status.pid,
            "exit_code": status.exit_code,
            "stub": False,
        }

    async def stop(self, server_id: str) -> dict[str, Any]:
        record = await self.get(server_id)
        if record is None:
            raise KeyError(f"unknown server: {server_id}")
        status = await self._proc(record).stop()
        return {
            "server_id": server_id,
            "state": status.state.value,
            "exit_code": status.exit_code,
            "stub": False,
        }

    async def restart(self, server_id: str) -> dict[str, Any]:
        await self.stop(server_id)
        return await self.start(server_id)

    def is_process_running(self, server_id: str) -> bool:
        proc = self._processes.get(server_id)
        return bool(proc is not None and proc.is_running())

    async def console_read(self, server_id: str, *, limit: int = 200, after_seq: int = 0) -> dict[str, Any]:
        record = await self.get(server_id)
        if record is None:
            raise KeyError(f"unknown server: {server_id}")
        return self._proc(record).console.read(limit=limit, after_seq=after_seq)

    async def console_wait(
        self,
        server_id: str,
        *,
        after_seq: int = 0,
        timeout: float = 25.0,
    ) -> dict[str, Any]:
        """Block until new console lines (or timeout) — used by WebSocket streaming."""
        record = await self.get(server_id)
        if record is None:
            raise KeyError(f"unknown server: {server_id}")
        return await self._proc(record).console.wait_for_lines(
            after_seq=after_seq,
            timeout=timeout,
        )

    async def console_execute(self, server_id: str, command: str) -> dict[str, Any]:
        record = await self.get(server_id)
        if record is None:
            raise KeyError(f"unknown server: {server_id}")
        ok = await self._proc(record).send_command(command)
        if not ok:
            raise RuntimeError("server not running")
        return {"server_id": server_id, "command": command, "sent": True}

    async def stop_all(self) -> None:
        for server_id, proc in list(self._processes.items()):
            if proc.is_running():
                logger.info("Stopping server %s during shutdown", server_id)
                await proc.stop()
