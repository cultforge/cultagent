"""Discover CultForge agent WebSocket endpoints from live manifest.json."""

from __future__ import annotations

from typing import Any

# Paths we will auto-switch to when they appear in api…/manifest.json.
CANDIDATE_AGENT_WS_PATHS: tuple[str, ...] = (
    "/v1/agent/ws",
    "/v1/agent/realtime",
    "/v1/agent/realtime/ws",
    "/v1/agents/ws",
    "/v1/agents/realtime",
)


def _meta_ws_path(meta: dict[str, Any]) -> str | None:
    """Read optional capability hints from manifest `&` metadata."""
    for key in ("agent_ws", "agent_websocket", "realtime_ws", "ws_path"):
        value = meta.get(key)
        if isinstance(value, str) and value.startswith("/"):
            return value

    realtime = meta.get("realtime")
    if isinstance(realtime, dict):
        for key in ("agent_ws", "ws", "path", "url"):
            value = realtime.get(key)
            if isinstance(value, str):
                if value.startswith("/"):
                    return value
                # Allow full wss://… and keep path-only preference for join
                if value.startswith("ws://") or value.startswith("wss://"):
                    return value

    caps = meta.get("capabilities")
    if isinstance(caps, dict):
        value = caps.get("agent_websocket") or caps.get("agent_ws")
        if isinstance(value, str) and value.startswith("/"):
            return value
        if value is True:
            return CANDIDATE_AGENT_WS_PATHS[0]
    if isinstance(caps, list):
        for item in caps:
            if item in {"agent_websocket", "agent_ws", "realtime"}:
                return CANDIDATE_AGENT_WS_PATHS[0]
    return None


def discover_agent_ws(
    manifest: dict[str, Any],
    *,
    uris: set[str] | None = None,
) -> str | None:
    """Return a WebSocket path/URL if the API advertises agent realtime support.

    Prefers explicit `&` metadata, then known candidate routes present in the
    route table. Returns None when the API only supports HTTPS poll.
    """
    meta = manifest.get("&") if isinstance(manifest.get("&"), dict) else {}
    hinted = _meta_ws_path(meta)
    if hinted:
        return hinted

    if uris is None:
        from cultagent.cloud.manifest import _collect_uris

        uris = _collect_uris(manifest)

    for path in CANDIDATE_AGENT_WS_PATHS:
        if path in uris:
            return path

    # Fuzzy: any agent route looking like a socket endpoint
    for uri in sorted(uris):
        low = uri.lower()
        if "agent" not in low:
            continue
        if any(tok in low for tok in ("/ws", "websocket", "realtime")):
            return uri
    return None


def api_base_to_ws_url(api_base: str, path_or_url: str) -> str:
    """Join https://api… + /v1/agent/ws → wss://api…/v1/agent/ws."""
    if path_or_url.startswith("ws://") or path_or_url.startswith("wss://"):
        return path_or_url
    base = api_base.rstrip("/")
    if base.startswith("https://"):
        ws_base = "wss://" + base[len("https://") :]
    elif base.startswith("http://"):
        ws_base = "ws://" + base[len("http://") :]
    else:
        ws_base = "wss://" + base
    path = path_or_url if path_or_url.startswith("/") else f"/{path_or_url}"
    return f"{ws_base}{path}"
