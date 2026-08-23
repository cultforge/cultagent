#!/usr/bin/env python3
"""Build cf-agent onefile binary with Nuitka + write dist/latest.json.

Usage (repo root, venv)::

    pip install -e ".[release]"
    python scripts/build_release.py
    python scripts/build_release.py --base-url https://github.com/org/repo/releases/download/v0.2.0

Env:
  CULTAGENT_RELEASE_BASE_URL  — prefix for filelink in latest.json (no trailing slash)
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
BUILD = ROOT / "build" / "nuitka"
# Package dir so Nuitka treats cultagent as runnable with -m (not __main__.py path)
ENTRY = ROOT / "src" / "cultagent"


def _platform_key() -> str:
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


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _read_version() -> str:
    try:
        from cultagent import __version__

        return str(__version__)
    except Exception:
        pass
    text = (ROOT / "src" / "cultagent" / "__init__.py").read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.startswith("__version__"):
            return line.split("=", 1)[1].strip().strip("\"'")
    return "0.0.0"


def _run_nuitka() -> Path:
    DIST.mkdir(parents=True, exist_ok=True)
    BUILD.mkdir(parents=True, exist_ok=True)
    is_win = sys.platform.startswith("win")
    out_name = "cf-agent.exe" if is_win else "cf-agent"

    cmd = [
        sys.executable,
        "-m",
        "nuitka",
        "--onefile",
        "--assume-yes-for-downloads",
        "--remove-output",
        "--output-dir=" + str(BUILD),
        "--output-filename=" + out_name,
        "--include-package=cultagent",
        "--include-package-data=cultagent",
        # yaspin.spinners loads data/spinners.json via pkgutil.get_data
        "--include-package-data=yaspin",
        # websockets 12+ lazy-loads websockets.asyncio (cloud realtime)
        "--include-package=websockets",
        "--include-module=uvicorn.logging",
        "--include-module=uvicorn.loops",
        "--include-module=uvicorn.loops.auto",
        "--include-module=uvicorn.protocols",
        "--include-module=uvicorn.protocols.http",
        "--include-module=uvicorn.protocols.http.auto",
        "--include-module=uvicorn.protocols.websockets",
        "--include-module=uvicorn.protocols.websockets.auto",
        "--include-module=uvicorn.lifespan",
        "--include-module=uvicorn.lifespan.on",
        "--nofollow-import-to=pytest",
        "--nofollow-import-to=tests",
        "--python-flag=-m",
        str(ENTRY),
    ]
    if is_win:
        cmd.insert(-1, "--windows-console-mode=force")
    print("+", " ".join(cmd), flush=True)
    env = os.environ.copy()
    # Prefer src layout during compile
    env["PYTHONPATH"] = os.pathsep.join(
        [str(ROOT / "src"), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)
    subprocess.check_call(cmd, cwd=str(ROOT), env=env)

    built = BUILD / out_name
    if not built.is_file():
        # Some Nuitka versions nest under *.dist / *.onefile-build
        candidates = list(BUILD.rglob(out_name))
        if not candidates:
            raise SystemExit(f"Expected binary missing under {BUILD}")
        built = max(candidates, key=lambda p: p.stat().st_mtime)
    dest = DIST / out_name
    if dest.exists():
        dest.unlink()
    shutil.copy2(built, dest)
    return dest


def _rename_artifact(built: Path, platform_key: str, version: str) -> Path:
    suffix = ".exe" if built.suffix.lower() == ".exe" else ""
    name = f"cf-agent-{version}-{platform_key}{suffix}"
    dest = DIST / name
    if dest.exists():
        dest.unlink()
    shutil.copy2(built, dest)
    return dest


def _merge_latest(
    *,
    version: str,
    platform_key: str,
    artifact: Path,
    digest: str,
    filelink: str,
) -> dict:
    path = DIST / "latest.json"
    payload: dict = {}
    if path.is_file():
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            payload = {}
    platforms = payload.get("platforms") if isinstance(payload.get("platforms"), dict) else {}
    platforms[platform_key] = {
        "version": version,
        "hash": f"sha256:{digest}",
        "filelink": filelink,
        "filename": artifact.name,
        "size": artifact.stat().st_size,
    }
    out = {
        "version": version,
        "hash": f"sha256:{digest}",
        "filelink": filelink,
        "platform": platform_key,
        "filename": artifact.name,
        "released_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "platforms": platforms,
    }
    path.write_text(json.dumps(out, indent=2) + "\n", encoding="utf-8")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Build cf-agent release binary (Nuitka) + latest.json")
    parser.add_argument(
        "--base-url",
        default=os.environ.get(
            "CULTAGENT_RELEASE_BASE_URL",
            "https://api.cultforge.com/static/agent",
        ),
        help="GitHub Releases or CDN prefix for filelink (no trailing slash)",
    )
    parser.add_argument(
        "--skip-build",
        action="store_true",
        help="Only hash existing dist binary and refresh latest.json",
    )
    args = parser.parse_args()
    version = _read_version()
    platform_key = _platform_key()
    print(f"version={version} platform={platform_key} backend=nuitka", flush=True)

    if args.skip_build:
        candidates = list(DIST.glob(f"cf-agent-{version}-{platform_key}*"))
        if not candidates:
            candidates = [p for p in DIST.glob("cf-agent*") if p.is_file() and p.suffix != ".json"]
        if not candidates:
            raise SystemExit("No binary in dist/ — run without --skip-build")
        artifact = max(candidates, key=lambda p: p.stat().st_mtime)
    else:
        built = _run_nuitka()
        artifact = _rename_artifact(built, platform_key, version)

    digest = _sha256(artifact)
    base = str(args.base_url).rstrip("/")
    filelink = f"{base}/{artifact.name}"
    latest = _merge_latest(
        version=version,
        platform_key=platform_key,
        artifact=artifact,
        digest=digest,
        filelink=filelink,
    )
    print(json.dumps(latest, indent=2))
    print(f"Wrote {DIST / 'latest.json'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
