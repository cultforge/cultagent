"""Configuration models and loader."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from cultagent.constants import (
    DEFAULT_API_BASE,
    DEFAULT_AUTH_BASE,
    DEFAULT_GUILDS_BASE,
    DEFAULT_INVITE_BASE,
)
from cultagent.paths import AgentPaths, default_config_dir, default_data_dir


class AgentSection(BaseModel):
    display_name: str = ""
    data_dir: str = ""


class CloudSection(BaseModel):
    auth_base: str = DEFAULT_AUTH_BASE
    api_base: str = DEFAULT_API_BASE
    invite_base: str = DEFAULT_INVITE_BASE
    guilds_base: str = DEFAULT_GUILDS_BASE
    poll_interval_seconds: int = 15
    telemetry_interval_seconds: int = 15
    # Aternos-style live share cadence (R.md §4); clamped 3–10s at runtime.
    live_share_interval_seconds: int = 5
    # Prefer cloud WebSocket when api…/manifest.json advertises it; else HTTPS poll.
    realtime_enabled: bool = True
    control_plane_enabled: bool = True


class LocalSection(BaseModel):
    bind_host: str = "127.0.0.1"
    bind_port: int = 8720
    auto_start_servers: bool = False


class ServersSection(BaseModel):
    root_dir: str = ""
    java_path: str = ""


class PlayitSection(BaseModel):
    enabled: bool = False
    auto_start: bool = False
    target_host: str = "127.0.0.1"
    target_port: int = 25565
    binary_path: str = ""  # optional override; empty = managed download under data_dir/playit/bin


class NetworkSection(BaseModel):
    default_provider: str = "direct"  # direct | playit
    playit: PlayitSection = Field(default_factory=PlayitSection)


class ModrinthSection(BaseModel):
    api_base: str = "https://api.modrinth.com/v2"
    user_agent: str = "CultForge-Agent/0.1 (cf-agent)"


class ContentSection(BaseModel):
    modrinth: ModrinthSection = Field(default_factory=ModrinthSection)


class LoggingSection(BaseModel):
    level: str = "INFO"
    file: str = ""


class AgentConfig(BaseModel):
    agent: AgentSection = Field(default_factory=AgentSection)
    cloud: CloudSection = Field(default_factory=CloudSection)
    local: LocalSection = Field(default_factory=LocalSection)
    servers: ServersSection = Field(default_factory=ServersSection)
    network: NetworkSection = Field(default_factory=NetworkSection)
    content: ContentSection = Field(default_factory=ContentSection)
    logging: LoggingSection = Field(default_factory=LoggingSection)


class EnvOverrides(BaseSettings):
    """Environment overrides (CULTAGENT_*)."""

    model_config = SettingsConfigDict(env_prefix="CULTAGENT_", extra="ignore")

    config: str = ""
    data_dir: str = ""
    auth_base: str = ""
    api_base: str = ""
    invite_base: str = ""
    guilds_base: str = ""
    log_level: str = ""


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def config_search_paths() -> list[Path]:
    paths: list[Path] = []
    env = EnvOverrides()
    if env.config:
        paths.append(Path(env.config))
    paths.extend(
        [
            Path.cwd() / "config.yaml",
            default_config_dir() / "config.yaml",
            Path(__file__).resolve().parents[2] / "config.yaml",
        ]
    )
    return paths


def load_config(path: Path | None = None) -> AgentConfig:
    raw: dict[str, Any] = {}
    if path is not None:
        if not path.is_file():
            raise FileNotFoundError(f"Config file not found: {path}")
        with path.open(encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
    else:
        for candidate in config_search_paths():
            if candidate.is_file():
                with candidate.open(encoding="utf-8") as fh:
                    raw = yaml.safe_load(fh) or {}
                break

    env = EnvOverrides()
    env_patch: dict[str, Any] = {}
    if env.data_dir:
        env_patch.setdefault("agent", {})["data_dir"] = env.data_dir
    if env.auth_base:
        env_patch.setdefault("cloud", {})["auth_base"] = env.auth_base
    if env.api_base:
        env_patch.setdefault("cloud", {})["api_base"] = env.api_base
    if env.invite_base:
        env_patch.setdefault("cloud", {})["invite_base"] = env.invite_base
    if env.guilds_base:
        env_patch.setdefault("cloud", {})["guilds_base"] = env.guilds_base
    if env.log_level:
        env_patch.setdefault("logging", {})["level"] = env.log_level

    merged = _deep_merge(raw, env_patch)
    return AgentConfig.model_validate(merged)


def resolve_paths(config: AgentConfig) -> AgentPaths:
    data = config.agent.data_dir.strip()
    paths = AgentPaths(Path(data) if data else default_data_dir())
    if config.servers.root_dir.strip():
        paths.servers_dir = Path(config.servers.root_dir).expanduser().resolve()
    if config.logging.file.strip():
        paths.log_file = Path(config.logging.file).expanduser().resolve()
    return paths


def write_example_config(dest: Path) -> None:
    example = Path(__file__).resolve().parents[2] / "config.example.yaml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if example.is_file():
        dest.write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
    else:
        dest.write_text(yaml.safe_dump(AgentConfig().model_dump()), encoding="utf-8")
