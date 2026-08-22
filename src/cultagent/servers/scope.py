"""Classify local server records (guild-bound, personal-bound, or local-only)."""

from __future__ import annotations

from typing import Any

SCOPE_LABELS: dict[str, str] = {
    "guild": "Guild",
    "personal": "Personal",
    "local": "Local",
}


def _meta_and_id(record: Any) -> tuple[dict[str, Any], str]:
    if isinstance(record, dict):
        return dict(record.get("metadata") or {}), str(
            record.get("server_id") or record.get("id") or ""
        )
    meta = dict(getattr(record, "metadata", None) or {})
    return meta, str(getattr(record, "server_id", "") or "")


def server_scope(record: Any) -> str:
    """Return ``guild``, ``personal``, or ``local`` for a catalog row."""
    meta, sid = _meta_and_id(record)
    explicit = str(meta.get("scope") or "").strip().lower()
    if explicit in SCOPE_LABELS:
        return explicit
    if meta.get("guild_server_id") or meta.get("cloned_from") == "guild":
        return "guild"
    if meta.get("personal_server_id") or sid.startswith("upsrv_"):
        return "personal"
    return "local"


def server_scope_label(record: Any) -> str:
    return SCOPE_LABELS.get(server_scope(record), "Local")


def server_scope_info(record: Any) -> dict[str, str]:
    scope = server_scope(record)
    return {"scope": scope, "scope_label": SCOPE_LABELS[scope]}
