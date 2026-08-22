"""Filesystem layout for CultAgent (cross-platform)."""

from __future__ import annotations

from pathlib import Path

from platformdirs import user_config_dir, user_data_dir, user_log_dir

APP_NAME = "CultAgent"
APP_AUTHOR = "CultForge"


def default_data_dir() -> Path:
    return Path(user_data_dir(APP_NAME, APP_AUTHOR))


def default_config_dir() -> Path:
    return Path(user_config_dir(APP_NAME, APP_AUTHOR))


def default_log_dir() -> Path:
    return Path(user_log_dir(APP_NAME, APP_AUTHOR))


class AgentPaths:
    """Resolved runtime paths under the agent data directory."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self.root = (data_dir or default_data_dir()).resolve()
        self.config_dir = default_config_dir().resolve()
        self.log_dir = default_log_dir().resolve()

        self.identity_file = self.root / "identity.json"
        self.credentials_file = self.root / "credentials.json"
        self.state_file = self.root / "state.json"
        self.servers_dir = self.root / "servers"
        self.backups_dir = self.root / "backups"
        self.profiles_dir = self.root / "profiles"
        self.cache_dir = self.root / "cache"
        self.audit_dir = self.root / "audit"
        self.log_file = self.log_dir / "cultagent.log"

    def ensure(self) -> None:
        for path in (
            self.root,
            self.config_dir,
            self.log_dir,
            self.servers_dir,
            self.backups_dir,
            self.profiles_dir,
            self.cache_dir,
            self.audit_dir,
        ):
            path.mkdir(parents=True, exist_ok=True)
