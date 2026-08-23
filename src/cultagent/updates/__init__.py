"""Agent self-update / version check helpers (verified artifacts only)."""

from __future__ import annotations

import hashlib
import logging
import os
import platform
import re
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

import httpx

from cultagent import __version__

logger = logging.getLogger("cultagent.updates")

# Prefer GitHub Releases (source of truth), then cloud mirror / legacy feed.
DEFAULT_GITHUB_LATEST_URL = (
    "https://github.com/cultforge/cultagent/releases/latest/download/latest.json"
)
DEFAULT_LATEST_URL = "https://api.cultforge.com/static/agent/latest.json"
DEFAULT_VERSION_URL = "https://api.cultforge.com/v1/agent/version"

_USER_AGENT = f"CultForge-Agent/{__version__} (cf-agent)"


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


def _version_parts(version: str) -> tuple[int, ...]:
    nums = [int(p) for p in re.findall(r"\d+", str(version or ""))]
    return tuple(nums) if nums else (0,)


def is_newer(latest: str, current: str) -> bool:
    """True when ``latest`` is strictly greater than ``current`` (numeric parts)."""
    return _version_parts(latest) > _version_parts(current)


def is_frozen_binary() -> bool:
    """True for Nuitka onefile / PyInstaller frozen builds."""
    if getattr(sys, "frozen", False):
        return True
    # Nuitka sets __compiled__ on the main module
    main = sys.modules.get("__main__")
    if main is not None and hasattr(main, "__compiled__"):
        return True
    exe = Path(sys.executable).resolve()
    name = exe.name.lower()
    if name.startswith("cf-agent") or name in {"cf-agent.exe", "cf-agent"}:
        # Heuristic: not a python interpreter
        if "python" not in name:
            return True
    return False


def current_executable() -> Path:
    return Path(sys.executable).resolve()


def _normalize_hash(value: Any) -> str | None:
    if not value:
        return None
    text = str(value).strip().lower()
    if text.startswith("sha256:"):
        text = text[7:]
    text = text.replace(" ", "")
    if re.fullmatch(r"[0-9a-f]{64}", text):
        return text
    return None


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


async def check_for_update(
    *,
    current: str | None = None,
    url: str | None = None,
    timeout: float = 15.0,
) -> dict[str, Any]:
    """Compare local version to ``latest.json`` (GitHub / cloud mirror).

    Never downloads or executes update packages here — only reports metadata.
    """
    current = current or __version__
    key = platform_key()
    env_latest = os.environ.get("CULTAGENT_LATEST_URL")
    urls = [
        u
        for u in [
            url,
            env_latest,
            DEFAULT_GITHUB_LATEST_URL,
            DEFAULT_LATEST_URL,
            DEFAULT_VERSION_URL,
        ]
        if u
    ]
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
        "latest_version": None,
        "update_available": False,
        "url": ordered[0] if ordered else DEFAULT_GITHUB_LATEST_URL,
        "platform": key,
        "notes": None,
        "checked": False,
        "hash": None,
        "filelink": None,
        "frozen": is_frozen_binary(),
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
                        "User-Agent": _USER_AGENT,
                    },
                    follow_redirects=True,
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
            result["latest_version"] = latest or None
            result["hash"] = digest
            result["filelink"] = filelink
            result["notes"] = data.get("notes") or data.get("changelog")
            result["download"] = filelink
            result["sha256"] = digest
            result["checked"] = True
            result["released_at"] = data.get("released_at")
            if latest and is_newer(latest, current):
                result["update_available"] = True
            elif latest and latest == current:
                result["notes"] = result.get("notes") or "Up to date"
            elif latest and not is_newer(latest, current):
                result["notes"] = result.get("notes") or "Local version is newer or equal"
            return result
        except Exception as exc:  # noqa: BLE001
            last_err = f"check failed: {exc}"
            continue

    result["notes"] = last_err if last_err != "404" else "Cloud version feed not published yet"
    if "404" in str(last_err):
        result["notes"] = "Version feed not published yet (latest.json)"
    return result


async def apply_update(
    *,
    force: bool = False,
    restart: bool = True,
    timeout: float = 120.0,
) -> dict[str, Any]:
    """Download a verified binary from the update feed and replace this executable.

    Only supported for frozen builds. Verifies SHA-256 when the feed provides one.
    On Windows, schedules a short helper script to replace the running file.
    """
    if not is_frozen_binary() and not force:
        return {
            "ok": False,
            "error": (
                "Self-update only applies to frozen cf-agent binaries. "
                "Dev installs: pip install -U / git pull."
            ),
            "frozen": False,
        }

    check = await check_for_update(timeout=min(timeout, 30.0))
    if not check.get("checked"):
        return {"ok": False, "error": check.get("notes") or "update check failed", "check": check}
    if not check.get("update_available") and not force:
        return {
            "ok": True,
            "skipped": True,
            "reason": "up_to_date",
            "check": check,
        }

    filelink = check.get("filelink") or check.get("download")
    if not filelink:
        return {
            "ok": False,
            "error": "No download URL in latest.json for this platform",
            "check": check,
        }

    expected = _normalize_hash(check.get("hash") or check.get("sha256"))
    target = current_executable()
    suffix = ".exe" if platform.system() == "Windows" else ""
    tmp_dir = Path(tempfile.mkdtemp(prefix="cf-agent-update-"))
    download_path = tmp_dir / f"cf-agent-new{suffix}"

    try:
        async with httpx.AsyncClient(
            timeout=timeout,
            follow_redirects=True,
            headers={"User-Agent": _USER_AGENT},
        ) as client:
            async with client.stream("GET", str(filelink)) as response:
                response.raise_for_status()
                with download_path.open("wb") as fh:
                    async for chunk in response.aiter_bytes():
                        fh.write(chunk)

        digest = _sha256_file(download_path)
        if expected and digest != expected:
            download_path.unlink(missing_ok=True)
            return {
                "ok": False,
                "error": f"SHA-256 mismatch (expected {expected}, got {digest})",
                "check": check,
            }

        if platform.system() != "Windows":
            download_path.chmod(download_path.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

        replaced = False
        restart_scheduled = False
        if platform.system() == "Windows":
            # Running binary is locked — write beside it and schedule replace after exit.
            sibling = target.with_name(target.name + ".new")
            shutil.copy2(download_path, sibling)
            bat = tmp_dir / "apply_update.bat"
            bat.write_text(
                "\r\n".join(
                    [
                        "@echo off",
                        "timeout /t 2 /nobreak >nul",
                        f'move /Y "{sibling}" "{target}"',
                        (
                            f'start "" "{target}"'
                            if restart
                            else "rem skip restart"
                        ),
                        f'rmdir /S /Q "{tmp_dir}"',
                    ]
                ),
                encoding="utf-8",
            )
            subprocess.Popen(  # noqa: S603
                ["cmd", "/c", str(bat)],
                close_fds=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                | getattr(subprocess, "DETACHED_PROCESS", 0),
            )
            restart_scheduled = bool(restart)
            replaced = True
        else:
            backup = target.with_suffix(target.suffix + ".bak")
            try:
                if backup.exists():
                    backup.unlink()
                shutil.move(str(target), str(backup))
            except OSError:
                backup = None  # type: ignore[assignment]
            try:
                shutil.copy2(download_path, target)
                target.chmod(target.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
                replaced = True
            except OSError as exc:
                if backup and backup.is_file():
                    shutil.move(str(backup), str(target))
                return {"ok": False, "error": f"replace failed: {exc}", "check": check}
            if backup and backup.is_file():
                try:
                    backup.unlink()
                except OSError:
                    pass
            if restart:
                try:
                    os.execv(str(target), [str(target), *sys.argv[1:]])
                except OSError as exc:
                    logger.warning("restart exec failed: %s", exc)
                    restart_scheduled = False
                else:
                    restart_scheduled = True  # unreachable if exec succeeds

        return {
            "ok": True,
            "replaced": replaced,
            "path": str(target),
            "version": check.get("latest"),
            "sha256": digest,
            "restart_scheduled": restart_scheduled,
            "check": check,
            "note": (
                "Windows: new binary will replace after this process exits; "
                "restart cf-agent if it does not auto-start."
                if platform.system() == "Windows"
                else None
            ),
        }
    finally:
        if platform.system() != "Windows":
            shutil.rmtree(tmp_dir, ignore_errors=True)

