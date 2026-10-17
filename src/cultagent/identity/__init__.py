"""Agent / node identity models and local persistence."""

from __future__ import annotations

import json
import logging
import secrets
import string
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, ValidationError

from cultagent.constants import NODE_ID_PREFIX

logger = logging.getLogger("cultagent.identity")


def _read_json_object(path: Path) -> dict[str, Any] | None:
    """Load a JSON object from disk; treat empty/corrupt files as missing.

    Empty or truncated identity/credentials files are common after a killed
    write or a bad copy onto a host — never crash the CLI on decode.
    """
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.warning("Could not read %s: %s", path, exc)
        return None
    if not text.strip():
        logger.warning("Empty identity/credentials file at %s — ignoring", path)
        _quarantine_corrupt(path, reason="empty")
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        logger.warning("Corrupt JSON in %s (%s) — ignoring", path, exc)
        _quarantine_corrupt(path, reason="json")
        return None
    if not isinstance(data, dict):
        logger.warning("Unexpected JSON root in %s — ignoring", path)
        _quarantine_corrupt(path, reason="shape")
        return None
    return data


def _quarantine_corrupt(path: Path, *, reason: str) -> None:
    """Rename a bad file aside so the next ensure_* can recreate a clean one."""
    try:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = path.with_name(f"{path.name}.corrupt-{reason}-{stamp}")
        path.replace(dest)
        logger.warning("Quarantined %s → %s", path.name, dest.name)
    except OSError as exc:
        logger.debug("Could not quarantine %s: %s", path, exc)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def generate_node_id() -> str:
    alphabet = string.ascii_lowercase + string.digits
    suffix = "".join(secrets.choice(alphabet) for _ in range(22))
    return f"{NODE_ID_PREFIX}{suffix}"


class AgentStatus(str, Enum):
    UNREGISTERED = "unregistered"
    REGISTERING = "registering"
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"
    REVOKED = "revoked"


class AgentIdentity(BaseModel):
    """Local + cloud identity. After claim/register, node_id becomes the cloud id."""

    node_id: str = Field(default_factory=generate_node_id)
    local_node_id: str | None = None
    cloud_node_id: str | None = None
    display_name: str = ""
    owner_account_id: str | None = None
    guild_id: str | None = None
    platform: str = ""
    architecture: str = ""
    agent_version: str = ""
    capabilities: list[str] = Field(default_factory=list)
    status: AgentStatus = AgentStatus.UNREGISTERED
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    last_seen: datetime | None = None
    registered_at: datetime | None = None

    def touch(self) -> None:
        self.updated_at = utc_now()
        self.last_seen = self.updated_at


class AgentCredentials(BaseModel):
    """Revocable agent credentials — never reuse the user's main account secret."""

    agent_token: str | None = None  # cagt_… from CultForge
    agent_secret: str | None = None  # legacy alias for agent_token
    access_token: str | None = None
    refresh_token: str | None = None
    expires_at: datetime | None = None
    issued_at: datetime | None = None

    def clear(self) -> None:
        self.agent_token = None
        self.agent_secret = None
        self.access_token = None
        self.refresh_token = None
        self.expires_at = None
        self.issued_at = None

    @property
    def token(self) -> str | None:
        return self.agent_token or self.agent_secret or self.access_token

    @property
    def has_credentials(self) -> bool:
        return bool(self.token)


class IdentityStore:
    def __init__(self, identity_path: Path, credentials_path: Path) -> None:
        self.identity_path = identity_path
        self.credentials_path = credentials_path

    def load_identity(self) -> AgentIdentity | None:
        if not self.identity_path.is_file():
            return None
        data = _read_json_object(self.identity_path)
        if data is None:
            return None
        try:
            return AgentIdentity.model_validate(data)
        except ValidationError as exc:
            logger.warning("Invalid identity schema in %s: %s", self.identity_path, exc)
            _quarantine_corrupt(self.identity_path, reason="schema")
            return None

    def save_identity(self, identity: AgentIdentity) -> None:
        identity.touch()
        self.identity_path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic-ish write: temp then replace, avoids empty files on kill mid-write.
        tmp = self.identity_path.with_suffix(self.identity_path.suffix + ".tmp")
        tmp.write_text(identity.model_dump_json(indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.identity_path)

    def load_credentials(self) -> AgentCredentials:
        if not self.credentials_path.is_file():
            return AgentCredentials()
        data = _read_json_object(self.credentials_path)
        if data is None:
            return AgentCredentials()
        try:
            creds = AgentCredentials.model_validate(data)
        except ValidationError as exc:
            logger.warning(
                "Invalid credentials schema in %s: %s", self.credentials_path, exc
            )
            _quarantine_corrupt(self.credentials_path, reason="schema")
            return AgentCredentials()
        if creds.agent_secret and not creds.agent_token:
            creds.agent_token = creds.agent_secret
        return creds

    def save_credentials(self, credentials: AgentCredentials) -> None:
        self.credentials_path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic-ish write + restrictive permissions where the OS supports it.
        tmp = self.credentials_path.with_suffix(self.credentials_path.suffix + ".tmp")
        tmp.write_text(credentials.model_dump_json(indent=2) + "\n", encoding="utf-8")
        tmp.replace(self.credentials_path)
        try:
            self.credentials_path.chmod(0o600)
        except OSError:
            pass

    def clear_registration(self) -> AgentIdentity:
        identity = self.load_identity() or AgentIdentity()
        # Restore local id if we had swapped to cloud id.
        if identity.local_node_id:
            identity.node_id = identity.local_node_id
        identity.cloud_node_id = None
        identity.status = AgentStatus.UNREGISTERED
        identity.owner_account_id = None
        identity.guild_id = None
        identity.registered_at = None
        self.save_identity(identity)
        creds = self.load_credentials()
        creds.clear()
        self.save_credentials(creds)
        return identity

    def ensure_local_identity(
        self,
        *,
        display_name: str = "",
        platform: str = "",
        architecture: str = "",
        agent_version: str = "",
        capabilities: list[str] | None = None,
    ) -> AgentIdentity:
        identity = self.load_identity()
        if identity is None:
            identity = AgentIdentity(
                display_name=display_name,
                platform=platform,
                architecture=architecture,
                agent_version=agent_version,
                capabilities=capabilities or [],
            )
            identity.local_node_id = identity.node_id
            self.save_identity(identity)
            return identity

        if not identity.local_node_id:
            identity.local_node_id = identity.node_id
            self.save_identity(identity)

        changed = False
        if display_name and identity.display_name != display_name and not identity.cloud_node_id:
            identity.display_name = display_name
            changed = True
        if platform and identity.platform != platform:
            identity.platform = platform
            changed = True
        if architecture and identity.architecture != architecture:
            identity.architecture = architecture
            changed = True
        if agent_version and identity.agent_version != agent_version:
            identity.agent_version = agent_version
            changed = True
        if capabilities is not None and identity.capabilities != capabilities:
            identity.capabilities = capabilities
            changed = True
        if changed:
            self.save_identity(identity)
        return identity

    def export_public(self) -> dict[str, Any]:
        identity = self.load_identity()
        if identity is None:
            return {"status": AgentStatus.UNREGISTERED.value, "registered": False}
        return {
            "node_id": identity.node_id,
            "local_node_id": identity.local_node_id,
            "cloud_node_id": identity.cloud_node_id,
            "display_name": identity.display_name,
            "status": identity.status.value,
            "guild_id": identity.guild_id,
            "owner_account_id": identity.owner_account_id,
            "platform": identity.platform,
            "architecture": identity.architecture,
            "agent_version": identity.agent_version,
            "capabilities": identity.capabilities,
            "registered": identity.status
            not in (AgentStatus.UNREGISTERED, AgentStatus.REVOKED)
            and bool(self.load_credentials().has_credentials),
            "last_seen": identity.last_seen.isoformat() if identity.last_seen else None,
        }
