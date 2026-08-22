"""Fetch and validate CultForge API route manifest (live discovery)."""

from __future__ import annotations

from typing import Any

import httpx

from cultagent.constants import REQUIRED_AGENT_ROUTES
from cultagent.settings import CloudSection


def _collect_uris(manifest: dict[str, Any]) -> set[str]:
    uris: set[str] = set()
    for key, value in manifest.items():
        if key == "&" or not isinstance(value, dict):
            continue
        for path, meta in value.items():
            if not isinstance(meta, dict):
                continue
            uri = meta.get("uri") or path
            if isinstance(uri, str) and uri.startswith("/"):
                uris.add(uri)
    return uris


async def fetch_api_manifest(
    cloud: CloudSection, *, timeout: float = 30.0
) -> dict[str, Any]:
    """GET {api_base}/manifest.json — source of truth for live worker routes."""
    url = f"{cloud.api_base.rstrip('/')}/manifest.json"
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.get(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "CultForge-Agent/0.1 (cf-agent)",
            },
        )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict):
        raise ValueError("manifest.json was not a JSON object")
    return payload


async def summarize_manifest(cloud: CloudSection) -> dict[str, Any]:
    """Compare required agent routes against live manifest + report service bases."""
    from cultagent.cloud.realtime_discover import discover_agent_ws

    manifest = await fetch_api_manifest(cloud)
    meta = manifest.get("&") if isinstance(manifest.get("&"), dict) else {}
    uris = _collect_uris(manifest)
    agent_uris = sorted(u for u in uris if "agent" in u.lower())
    missing = [r for r in REQUIRED_AGENT_ROUTES if r not in uris]
    ws_path = discover_agent_ws(manifest, uris=uris)
    return {
        "api_base": cloud.api_base.rstrip("/"),
        "build_id": meta.get("build_id"),
        "services": {
            "api": cloud.api_base,
            "auth": cloud.auth_base,
            "invite": cloud.invite_base,
            "guilds": cloud.guilds_base,
        },
        "agent_route_count": len(agent_uris),
        "agent_routes": agent_uris,
        "required_ok": not missing,
        "missing_required": missing,
        "realtime_ws": ws_path,
        "realtime_ready": bool(ws_path),
        "note": (
            "Apex cultforge.com is static; approve device login via "
            "POST /v1/agents/device/approve on api (user JWT), not a website page. "
            "Agent auto-switches to WebSocket when realtime_ws appears in this manifest. "
            "Guild presence: POST /v1/agent/guild/players + /events from console parse."
        ),
    }
