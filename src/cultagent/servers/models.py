"""Server domain models."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ServerState(str, Enum):
    UNKNOWN = "unknown"
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    CRASHED = "crashed"


class ServerRecord(BaseModel):
    server_id: str
    name: str
    path: str
    minecraft_version: str | None = None
    loader: str | None = None  # server platforms: vanilla|paper|purpur|folia|fabric|quilt|forge|neoforge
    port: int = 25565
    auto_start: bool = False
    crash_detection: bool = True
    auto_restart: bool = True
    build_id: str | None = None
    executable: str = "server.jar"
    execution_command: str = ""
    jvm_args: str = "-Xms1G -Xmx2G"
    stop_command: str = "stop"
    java_path: str = ""
    shutdown_timeout_seconds: int = 60
    metadata: dict[str, Any] = Field(default_factory=dict)


class ServerStatus(BaseModel):
    server_id: str
    name: str
    state: ServerState = ServerState.STOPPED
    players: int = 0
    max_players: int | None = None
    tps: float | None = None
    mspt: float | None = None
    version: str | None = None
    loader: str | None = None
    pid: int | None = None
    exit_code: int | None = None
    uptime_seconds: float | None = None
