"""Agent self-update / version check helpers (verified artifacts only)."""

from __future__ import annotations

import os
import platform
from typing import Any

import httpx

from cultagent import __version__

# Canonical release feed (usually a mirror of the GitHub Release latest.json)
DEFAULT_LATEST_URL = "https://api.cultforge.com/static/agent/latest.json"
# Legacy single-object feed (still accepted)
DEFAULT_VERSION_URL = "https://api.cultforge.com/v1/agent/version"


def platform_key() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    if machine in {"x86_64", "amd64"}:
        arch = "amd64"
    elif machine in {"aarch64", "arm64"}:
        arch = "arm64"
    else:
        arch = machine or "unknown"
    if system.startswith("darwin") or system == "macos":
        os_name = "darwin"
    elif system.startswith("win"):
        os_name = "windows"
    elif system.startswith("linux"):
        os_name = "linux"
    else:
        os_name = system
    return f"{os_name}-{arch}"


def _pick_platform_entry(data: dict[str, Any], key: str) -> dict[str, Any]:
    platforms = data.get("platforms")
    if isinstance(platforms, dict):
        entry = platforms.get(key)
        if isinstance(entry, dict):
            return entry
        # soft fallbacks
        if key.startswith("darwin-"):
            for alt in ("darwin-arm64", "darwin-amd64"):
                if isinstance(platforms.get(alt), dict):
                    return platforms[alt]
    # Flat latest.json (this build's platform only)
    if data.get("hash") or data.get("filelink") or data.get("version"):
        return data
    return {}


async def check_for_update(
    *,
    current: str | None = None,
    url: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Compare local version to ``latest.json`` (or legacy version feed).

    Never downloads or executes update packages here — only reports metadata.
    """
    current = current or __version__
    key = platform_key()
    env_latest = os.environ.get("CULTAGENT_LATEST_URL")
    urls = [u for u in [url, env_latest, DEFAULT_LATEST_URL, DEFAULT_VERSION_URL] if u]
    # Dedupe preserving order
    seen: set[str] = set()
    ordered: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            ordered.append(u)

    result: dict[str, Any] = {
        "current": current,
        "latest": None,
        "update_available": False,
        "url": ordered[0] if ordered else DEFAULT_LATEST_URL,
        "platform": key,
        "notes": None,
        "checked": False,
        "hash": None,
        "filelink": None,
    }

    last_err = "no feed"
    for feed_url in ordered:
        result["url"] = feed_url
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.get(
                    feed_url,
                    headers={
                        "Accept": "application/json",
                        "User-Agent": f"CultForge-Agent/{current} (cf-agent)",
                    },
                )
            if response.status_code == 404:
                last_err = f"404 {feed_url}"
                continue
            response.raise_for_status()
            payload = response.json()
            data = payload.get("data") if isinstance(payload, dict) else payload
            if not isinstance(data, dict):
                last_err = "Unexpected version payload"
                continue

            entry = _pick_platform_entry(data, key)
            latest = str(
                entry.get("version")
                or data.get("version")
                or data.get("latest")
                or ""
            )
            digest = entry.get("hash") or entry.get("sha256") or data.get("sha256")
            filelink = (
                entry.get("filelink")
                or entry.get("download")
                or entry.get("url")
                or data.get("download")
                or data.get("url")
            )
            result["latest"] = latest or None
            result["hash"] = digest
            result["filelink"] = filelink
            result["notes"] = data.get("notes") or data.get("changelog")
            result["download"] = filelink
            result["sha256"] = digest
            result["checked"] = True
            result["released_at"] = data.get("released_at")
            if latest and latest != current:
                result["update_available"] = True
            elif latest and latest == current:
                result["notes"] = result.get("notes") or "Up to date"
            return result
        except Exception as exc:  # noqa: BLE001
            last_err = f"check failed: {exc}"
            continue

    result["notes"] = last_err if last_err != "404" else "Cloud version feed not published yet"
    if "404" in str(last_err):
        result["notes"] = "Cloud version feed not published yet (latest.json)"
    return result
