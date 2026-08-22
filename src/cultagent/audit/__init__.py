"""Audit trail for privileged operations (no secrets)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("cultagent.audit")


class AuditLog:
    def __init__(self, audit_dir: Path) -> None:
        self.audit_dir = audit_dir
        self.audit_dir.mkdir(parents=True, exist_ok=True)
        self.path = self.audit_dir / "audit.jsonl"

    async def record(
        self,
        *,
        operation: str,
        actor_id: str | None = None,
        resource_id: str | None = None,
        result: str = "requested",
        failure_reason: str | None = None,
        extra: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "actor_id": actor_id,
            "resource_id": resource_id,
            "operation": operation,
            "result": result,
            "failure_reason": failure_reason,
        }
        if extra:
            # Never log secrets — callers must scrub first.
            entry["extra"] = extra
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry) + "\n")
        logger.info("audit %s resource=%s result=%s", operation, resource_id, result)
        return entry
