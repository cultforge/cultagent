"""Process supervisor for Minecraft (and similar) server processes.

Architecture mirrors Crafty Controller's proven model:
subprocess with stdin/stdout pipes, virtual console buffer, stop-command then
escalate — without copying Crafty source.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shlex
import time
from pathlib import Path
from typing import Any

from cultagent.servers.console import ConsoleBuffer
from cultagent.servers.install import ensure_forge_launch_files
from cultagent.servers.java import (
    detect_java,
    java_requirement_message,
    required_java_major,
)
from cultagent.servers.models import ServerRecord, ServerState, ServerStatus

logger = logging.getLogger("cultagent.servers.process")


def parse_command(command: str) -> list[str]:
    """Split an execution command into argv.

    Uses Windows-safe shlex (posix=False) and strips surrounding quotes so
    CreateProcess receives bare paths.
    """
    if not command.strip():
        raise ValueError("empty execution command")
    parts = shlex.split(command, posix=False)
    cleaned: list[str] = []
    for part in parts:
        if len(part) >= 2 and part[0] == part[-1] and part[0] in {'"', "'"}:
            cleaned.append(part[1:-1])
        else:
            cleaned.append(part)
    return cleaned


def _read_java_argfile(path: Path, root: Path) -> list[str]:
    tokens: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("@") and len(stripped) > 1:
            nested = root / stripped[1:].replace("/", os.sep)
            if nested.is_file():
                tokens.extend(_read_java_argfile(nested, root))
            else:
                tokens.append(stripped)
        else:
            # Forge win_args.txt puts "-p" and the module path on one line on Windows.
            tokens.extend(shlex.split(stripped, posix=False))
    return tokens


def expand_java_argfiles(parts: list[str], server_root: str | Path) -> list[str]:
    """Expand ``@file`` tokens for Java 8 runtimes without native argfile support."""
    root = Path(server_root)
    out: list[str] = []
    for part in parts:
        if part.startswith("@") and len(part) > 1:
            argpath = root / part[1:].replace("/", os.sep)
            if argpath.is_file():
                out.extend(_read_java_argfile(argpath, root))
            else:
                logger.warning("Java argfile missing: %s", argpath)
                out.append(part)
        else:
            out.append(part)
    return out


def build_execution_command(
    record: ServerRecord,
    java_bin: str,
    *,
    java_major: int | None = None,
) -> list[str]:
    ensure_forge_launch_files(record)
    if record.execution_command.strip():
        parts = parse_command(record.execution_command)
        if parts and parts[0].lower() in {"java", "java.exe"}:
            parts[0] = java_bin
        uses_argfiles = any(p.startswith("@") for p in parts)
        # Java 9+ parses @argfiles natively (required for Forge win_args.txt layout).
        if uses_argfiles and (java_major is None or java_major < 9):
            parts = expand_java_argfiles(parts, record.path)
        return parts

    jvm = parse_command(record.jvm_args) if record.jvm_args.strip() else []
    return [java_bin, *jvm, "-jar", record.executable, "nogui"]


class ManagedProcess:
    def __init__(self, record: ServerRecord) -> None:
        self.record = record
        self.console = ConsoleBuffer()
        self.process: asyncio.subprocess.Process | None = None
        self.state = ServerState.STOPPED
        self.started_at: float | None = None
        self.exit_code: int | None = None
        self._reader_task: asyncio.Task[None] | None = None
        self.intentional_stop = False

    @property
    def pid(self) -> int | None:
        return self.process.pid if self.process and self.process.returncode is None else None

    def is_running(self) -> bool:
        return self.process is not None and self.process.returncode is None

    def status(self) -> ServerStatus:
        uptime = None
        if self.started_at and self.is_running():
            uptime = time.time() - self.started_at
        return ServerStatus(
            server_id=self.record.server_id,
            name=self.record.name,
            state=self.state,
            version=self.record.minecraft_version,
            loader=self.record.loader,
            pid=self.pid,
            exit_code=self.exit_code,
            uptime_seconds=uptime,
        )

    async def start(self, *, java_path: str | None = None) -> ServerStatus:
        if self.is_running():
            raise RuntimeError("server already running")

        preferred = java_path or self.record.java_path or None
        min_major = required_java_major(self.record.minecraft_version)
        runtime = detect_java(preferred, min_major=min_major)
        if runtime is None:
            fallback = detect_java(preferred)
            if fallback is not None:
                raise RuntimeError(java_requirement_message(
                    minecraft_version=self.record.minecraft_version,
                    found=fallback,
                ))
            raise RuntimeError(
                java_requirement_message(
                    minecraft_version=self.record.minecraft_version,
                    found=None,
                )
            )

        cmd = build_execution_command(
            self.record,
            runtime.path,
            java_major=runtime.major,
        )
        cwd = self.record.path
        logger.info("Starting %s: %s (cwd=%s)", self.record.server_id, cmd, cwd)

        self.state = ServerState.STARTING
        self.exit_code = None
        self.intentional_stop = False
        try:
            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                cwd=cwd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except Exception:
            self.state = ServerState.CRASHED
            raise

        self.started_at = time.time()
        self._reader_task = asyncio.create_task(self._read_stdout())
        await asyncio.sleep(0.15)

        if not self.is_running():
            self.exit_code = self.process.returncode if self.process else None
            self.state = ServerState.CRASHED
            logger.error(
                "Server %s exited immediately (code=%s)",
                self.record.server_id,
                self.exit_code,
            )
            return self.status()

        self.state = ServerState.RUNNING
        logger.info(
            "Server %s running with PID %s",
            self.record.server_id,
            self.process.pid if self.process else None,
        )
        return self.status()

    async def _read_stdout(self) -> None:
        assert self.process is not None and self.process.stdout is not None
        try:
            while True:
                line = await self.process.stdout.readline()
                if not line:
                    break
                text = line.decode("utf-8", errors="replace")
                await self.console.append(text)
        finally:
            code = await self.process.wait()
            self.exit_code = code
            if self.intentional_stop or self.state == ServerState.STOPPING:
                self.state = ServerState.STOPPED
            elif self.state != ServerState.STOPPED:
                self.state = ServerState.CRASHED
            logger.info(
                "Server %s process exited code=%s state=%s",
                self.record.server_id,
                code,
                self.state.value,
            )

    async def send_command(self, command: str) -> bool:
        if not self.is_running() or self.process is None or self.process.stdin is None:
            return False
        payload = (command.rstrip("\r\n") + "\n").encode("utf-8")
        self.process.stdin.write(payload)
        await self.process.stdin.drain()
        await self.console.append(f"> {command}")
        return True

    async def stop(self, *, timeout: float | None = None) -> ServerStatus:
        if not self.is_running() or self.process is None:
            self.state = ServerState.STOPPED
            return self.status()

        self.state = ServerState.STOPPING
        self.intentional_stop = True
        timeout = (
            float(timeout)
            if timeout is not None
            else float(self.record.shutdown_timeout_seconds)
        )
        stop_cmd = self.record.stop_command or "stop"
        logger.info("Stopping %s via '%s'", self.record.server_id, stop_cmd)
        try:
            await self.send_command(stop_cmd)
        except Exception:  # noqa: BLE001
            logger.exception("Failed to send stop command; terminating")
            self.process.terminate()

        try:
            await asyncio.wait_for(self.process.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning(
                "Server %s did not stop in %ss — terminating",
                self.record.server_id,
                timeout,
            )
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=10)
            except asyncio.TimeoutError:
                logger.error("Server %s ignore terminate — killing", self.record.server_id)
                self.process.kill()
                await self.process.wait()

        if self._reader_task:
            try:
                await asyncio.wait_for(self._reader_task, timeout=2)
            except asyncio.TimeoutError:
                self._reader_task.cancel()
            self._reader_task = None

        self.state = ServerState.STOPPED
        self.process = None
        return self.status()

    async def restart(self) -> ServerStatus:
        await self.stop()
        await asyncio.sleep(1)
        return await self.start()

    def to_public(self) -> dict[str, Any]:
        return self.status().model_dump()
