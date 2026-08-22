"""Authorized sidecar clients (e.g. Chloe) — never bypass CultForge auth."""

from __future__ import annotations

import json
import secrets
import time
from pathlib import Path
from typing import Any

from cultagent.rbac import ROLE_PERMISSIONS, LocalAuthorizer

# Well-known CultForge bot account id from live manifest (Chloe).
CHLOE_BOT_USER_ID = "cf_CH0E0001"
CHLOE_HANDLE = "chloe"


class SidecarStore:
    """Issue / verify loopback sidecar tokens stored under the agent data dir."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.index_path = self.root / "sidecars.json"

    def _load(self) -> dict[str, Any]:
        if not self.index_path.is_file():
            return {"schema_version": 1, "clients": {}}
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return {"schema_version": 1, "clients": {}}
            data.setdefault("clients", {})
            return data
        except Exception:  # noqa: BLE001
            return {"schema_version": 1, "clients": {}}

    def _save(self, data: dict[str, Any]) -> None:
        self.index_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    def list_clients(self) -> list[dict[str, Any]]:
        clients = self._load().get("clients") or {}
        out: list[dict[str, Any]] = []
        for name, meta in clients.items():
            if not isinstance(meta, dict):
                continue
            out.append(
                {
                    "name": name,
                    "actor_id": meta.get("actor_id"),
                    "role": meta.get("role"),
                    "created_at": meta.get("created_at"),
                    "has_token": bool(meta.get("token")),
                    # never return token here
                }
            )
        return out

    def issue(
        self,
        name: str,
        *,
        actor_id: str,
        role: str = "chloe",
        authorizer: LocalAuthorizer | None = None,
    ) -> dict[str, Any]:
        name = name.strip().lower()
        if not name:
            raise ValueError("sidecar name required")
        if role not in ROLE_PERMISSIONS:
            raise ValueError(f"unknown role: {role}")
        token = "cside_" + secrets.token_urlsafe(32)
        data = self._load()
        clients = data.setdefault("clients", {})
        clients[name] = {
            "actor_id": actor_id,
            "role": role,
            "token": token,
            "created_at": time.time(),
        }
        self._save(data)
        if authorizer is not None:
            authorizer.grant_role(actor_id, role)
        return {
            "ok": True,
            "name": name,
            "actor_id": actor_id,
            "role": role,
            "token": token,  # shown once at issue time only
            "note": "Store this token for the sidecar. It will not be shown again via list/status.",
        }

    def revoke(self, name: str) -> dict[str, Any]:
        data = self._load()
        clients = data.setdefault("clients", {})
        if name not in clients:
            raise FileNotFoundError(name)
        clients.pop(name, None)
        self._save(data)
        return {"ok": True, "revoked": name}

    def verify(self, token: str) -> dict[str, Any] | None:
        if not token:
            return None
        token = token.strip()
        clients = self._load().get("clients") or {}
        for name, meta in clients.items():
            if not isinstance(meta, dict):
                continue
            if meta.get("token") == token:
                return {
                    "name": name,
                    "actor_id": meta.get("actor_id"),
                    "role": meta.get("role"),
                }
        return None


def ensure_chloe_grants(authorizer: LocalAuthorizer, actor_id: str = CHLOE_BOT_USER_ID) -> None:
    authorizer.grant_role(actor_id, "chloe")
