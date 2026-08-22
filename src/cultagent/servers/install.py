"""Minecraft *server* installers (not clients).

Supported loaders: vanilla, paper, purpur, folia, fabric, quilt, forge, neoforge.
"""

from __future__ import annotations

import asyncio
import logging
import platform
import re
from pathlib import Path
from typing import Any

import httpx

from cultagent.config import render_server_properties
from cultagent.servers.eula import write_eula
from cultagent.servers.java import (
    detect_java,
    java_requirement_message,
    required_java_major,
)
from cultagent.servers.models import ServerRecord

logger = logging.getLogger("cultagent.servers.install")

MOJANG_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"
PAPER_API = "https://api.papermc.io/v2"
PURPUR_API = "https://api.purpurmc.org/v2"
FABRIC_META = "https://meta.fabricmc.net/v2"
QUILT_META = "https://meta.quiltmc.org/v3"
FORGE_PROMOTIONS = (
    "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
)
FORGE_MAVEN = "https://maven.minecraftforge.net/net/minecraftforge/forge"
NEOFORGE_META = (
    "https://maven.neoforged.net/releases/net/neoforged/neoforge/maven-metadata.xml"
)
NEOFORGE_MAVEN = "https://maven.neoforged.net/releases/net/neoforged/neoforge"

# Server platforms only — no client launchers / Prism / MultiMC.
SERVER_LOADERS = (
    "vanilla",
    "paper",
    "purpur",
    "folia",
    "fabric",
    "quilt",
    "forge",
    "neoforge",
)

_PAPER_FAMILY = {"paper", "folia"}
_MOD_LOADERS = {"fabric", "quilt", "forge", "neoforge"}
_PLUGIN_LOADERS = {"paper", "purpur", "folia", "spigot", "bukkit"}


def default_server_properties(*, port: int = 25565, motd: str = "CultForge Server") -> dict[str, str]:
    return {
        "server-port": str(port),
        "motd": motd,
        "online-mode": "true",
        "difficulty": "easy",
        "gamemode": "survival",
        "max-players": "20",
        "view-distance": "10",
        "simulation-distance": "10",
        "pvp": "true",
        "spawn-protection": "16",
        "enable-command-block": "false",
    }


def bootstrap_server_dir(record: ServerRecord, *, accept_eula: bool = False) -> None:
    root = Path(record.path)
    root.mkdir(parents=True, exist_ok=True)
    loader = (record.loader or "vanilla").lower()
    if loader in _MOD_LOADERS or loader == "vanilla":
        (root / "mods").mkdir(exist_ok=True)
    if loader in _PLUGIN_LOADERS:
        (root / "plugins").mkdir(exist_ok=True)
    props_path = root / "server.properties"
    if not props_path.is_file():
        props = default_server_properties(port=record.port, motd=record.name)
        props_path.write_text(render_server_properties(props), encoding="utf-8")
    write_eula(root, accepted=accept_eula)
    (root / "logs").mkdir(exist_ok=True)


async def resolve_vanilla_server_jar_url(version: str) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=60.0) as client:
        manifest = (await client.get(MOJANG_MANIFEST)).raise_for_status().json()
        entry = next((v for v in manifest["versions"] if v["id"] == version), None)
        if entry is None:
            raise ValueError(f"unknown Minecraft version: {version}")
        detail = (await client.get(entry["url"])).raise_for_status().json()
        downloads = detail.get("downloads", {}).get("server")
        if not downloads or "url" not in downloads:
            raise ValueError(f"no server jar for version {version}")
        return downloads


async def _stream_download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    async with httpx.AsyncClient(timeout=None, follow_redirects=True) as client:
        async with client.stream("GET", url) as response:
            response.raise_for_status()
            with dest.open("wb") as fh:
                async for chunk in response.aiter_bytes():
                    fh.write(chunk)


def _require_mc_version(record: ServerRecord, version: str | None) -> str:
    mc = version or record.minecraft_version
    if not mc:
        raise ValueError("minecraft_version required")
    return mc


def _ensure_user_jvm_args(root: Path, jvm_args: str) -> None:
    path = root / "user_jvm_args.txt"
    defaults = [a for a in jvm_args.split() if a.strip()] or ["-Xms1G", "-Xmx4G"]
    if path.is_file():
        text = path.read_text(encoding="utf-8")
        active = [
            ln.strip()
            for ln in text.splitlines()
            if ln.strip() and not ln.strip().startswith("#")
        ]
        if active:
            return
        path.write_text(
            text.rstrip() + "\n\n" + "\n".join(defaults) + "\n",
            encoding="utf-8",
        )
        return
    path.write_text("\n".join(defaults) + "\n", encoding="utf-8")


def ensure_forge_launch_files(record: ServerRecord) -> None:
    """Ensure Forge/NeoForge @argfile launch inputs exist before start."""
    cmd = (record.execution_command or "").strip()
    if "@user_jvm_args.txt" not in cmd:
        return
    _ensure_user_jvm_args(Path(record.path), record.jvm_args)


def _apply_forge_style_launch(record: ServerRecord) -> ServerRecord:
    """Point execution at Forge/NeoForge args files after --installServer."""
    root = Path(record.path)
    is_windows = platform.system() == "Windows"
    args_name = "win_args.txt" if is_windows else "unix_args.txt"
    matches = sorted(root.rglob(args_name))
    if not matches:
        # Fallback: run scripts produced by installer
        script = root / ("run.bat" if is_windows else "run.sh")
        if script.is_file():
            if is_windows:
                record.execution_command = f'cmd /c "{script.name}"'
            else:
                record.execution_command = f"bash {script.name}"
            record.executable = script.name
            return record
        raise RuntimeError(
            f"Forge/NeoForge install finished but {args_name} / run script not found"
        )

    args_file = matches[0]
    rel = args_file.relative_to(root).as_posix()
    _ensure_user_jvm_args(root, record.jvm_args)
    # @argfile form is the supported headless server launch.
    record.execution_command = f"java @user_jvm_args.txt @{rel} nogui"
    record.executable = args_file.name
    return record


async def _run_installer_jar(installer: Path, cwd: Path, *, minecraft_version: str | None = None) -> None:
    min_major = required_java_major(minecraft_version)
    runtime = detect_java(min_major=min_major) or detect_java()
    if runtime is None:
        raise RuntimeError(
            java_requirement_message(minecraft_version=minecraft_version, found=None)
        )
    if runtime.major is not None and runtime.major < min_major:
        raise RuntimeError(
            java_requirement_message(minecraft_version=minecraft_version, found=runtime)
        )
    cmd = [runtime.path, "-jar", str(installer), "--installServer"]
    logger.info("Running server installer: %s (cwd=%s)", cmd, cwd)
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        cwd=str(cwd),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    out, _ = await proc.communicate()
    text = (out or b"").decode("utf-8", errors="replace")
    if proc.returncode != 0:
        logger.error("Installer failed:\n%s", text[-4000:])
        raise RuntimeError(
            f"server installer exited {proc.returncode} — see agent logs"
        )
    logger.info("Installer completed successfully")


async def download_vanilla_jar(
    record: ServerRecord,
    *,
    version: str | None = None,
) -> Path:
    mc_version = _require_mc_version(record, version)
    info = await resolve_vanilla_server_jar_url(mc_version)
    dest = Path(record.path) / record.executable
    logger.info("Downloading vanilla server %s -> %s", mc_version, dest)
    await _stream_download(info["url"], dest)
    expected = info.get("sha1")
    if expected:
        import hashlib

        digest = hashlib.sha1(dest.read_bytes()).hexdigest()  # noqa: S324
        if digest != expected:
            dest.unlink(missing_ok=True)
            raise RuntimeError(f"jar checksum mismatch: expected {expected}, got {digest}")
    return dest


async def _download_papermc_project(
    record: ServerRecord,
    *,
    project: str,
    version: str | None = None,
) -> Path:
    mc_version = _require_mc_version(record, version)
    async with httpx.AsyncClient(timeout=60.0) as client:
        builds = (
            await client.get(f"{PAPER_API}/projects/{project}/versions/{mc_version}/builds")
        ).raise_for_status().json()
        build_list = builds.get("builds") or []
        if not build_list:
            raise ValueError(f"no {project} builds for {mc_version}")
        latest = build_list[-1]
        build_no = latest["build"]
        download_name = latest["downloads"]["application"]["name"]
        url = (
            f"{PAPER_API}/projects/{project}/versions/{mc_version}/builds/{build_no}"
            f"/downloads/{download_name}"
        )
    dest = Path(record.path) / record.executable
    logger.info("Downloading %s server %s build %s -> %s", project, mc_version, build_no, dest)
    await _stream_download(url, dest)
    return dest


async def download_paper_jar(
    record: ServerRecord, *, version: str | None = None
) -> Path:
    return await _download_papermc_project(record, project="paper", version=version)


async def download_folia_jar(
    record: ServerRecord, *, version: str | None = None
) -> Path:
    return await _download_papermc_project(record, project="folia", version=version)


async def download_purpur_jar(
    record: ServerRecord, *, version: str | None = None
) -> Path:
    mc_version = _require_mc_version(record, version)
    async with httpx.AsyncClient(timeout=60.0) as client:
        meta = (
            await client.get(f"{PURPUR_API}/purpur/{mc_version}")
        ).raise_for_status().json()
        build = str(meta.get("builds", {}).get("latest") or "")
        if not build:
            raise ValueError(f"no Purpur builds for {mc_version}")
        url = f"{PURPUR_API}/purpur/{mc_version}/{build}/download"
    dest = Path(record.path) / record.executable
    logger.info("Downloading Purpur server %s build %s -> %s", mc_version, build, dest)
    await _stream_download(url, dest)
    return dest


async def download_fabric_jar(
    record: ServerRecord, *, version: str | None = None
) -> Path:
    mc_version = _require_mc_version(record, version)
    async with httpx.AsyncClient(timeout=60.0) as client:
        loaders = (
            await client.get(f"{FABRIC_META}/versions/loader/{mc_version}")
        ).raise_for_status().json()
        if not loaders:
            raise ValueError(f"no Fabric loader for {mc_version}")
        loader_ver = loaders[0]["loader"]["version"]
        installers = (
            await client.get(f"{FABRIC_META}/versions/installer")
        ).raise_for_status().json()
        if not installers:
            raise ValueError("no Fabric installer versions")
        installer_ver = installers[0]["version"]
        url = (
            f"{FABRIC_META}/versions/loader/{mc_version}/{loader_ver}/"
            f"{installer_ver}/server/jar"
        )
    dest = Path(record.path) / record.executable
    logger.info("Downloading Fabric server %s / %s -> %s", mc_version, loader_ver, dest)
    await _stream_download(url, dest)
    return dest


async def download_quilt_jar(
    record: ServerRecord, *, version: str | None = None
) -> Path:
    """Quilt server launcher jar via Quilt Meta (server-only)."""
    mc_version = _require_mc_version(record, version)
    async with httpx.AsyncClient(timeout=60.0) as client:
        loaders = (
            await client.get(f"{QUILT_META}/versions/loader/{mc_version}")
        ).raise_for_status().json()
        if not loaders:
            raise ValueError(f"no Quilt loader for {mc_version}")
        loader_ver = loaders[0]["loader"]["version"]
        installers = (
            await client.get(f"{QUILT_META}/versions/installer")
        ).raise_for_status().json()
        if not installers:
            raise ValueError("no Quilt installer versions")
        installer_ver = installers[0]["version"]
        # Quilt meta mirrors Fabric-style server jar endpoint under v3.
        url = (
            f"{QUILT_META}/versions/loader/{mc_version}/{loader_ver}/"
            f"{installer_ver}/server/jar"
        )
    dest = Path(record.path) / record.executable
    logger.info("Downloading Quilt server %s / %s -> %s", mc_version, loader_ver, dest)
    try:
        await _stream_download(url, dest)
    except httpx.HTTPStatusError:
        # Fallback: installer jar + --installServer is uncommon for Quilt;
        # try fabric-compatible hashed endpoint alternate.
        raise ValueError(
            f"Quilt server jar unavailable for {mc_version} "
            f"(loader {loader_ver}). Try Fabric or pin another MC version."
        )
    return dest


async def _resolve_forge_version(mc_version: str, loader_version: str | None) -> str:
    if loader_version:
        return loader_version
    async with httpx.AsyncClient(timeout=60.0) as client:
        promo = (await client.get(FORGE_PROMOTIONS)).raise_for_status().json()
        promos = promo.get("promos") or {}
        for key in (f"{mc_version}-recommended", f"{mc_version}-latest"):
            if key in promos:
                return str(promos[key])
    raise ValueError(f"no Forge promotion for Minecraft {mc_version}")


async def download_forge_server(
    record: ServerRecord,
    *,
    version: str | None = None,
    loader_version: str | None = None,
) -> Path:
    """Download Forge *server* installer and run --installServer (not client)."""
    mc_version = _require_mc_version(record, version)
    forge_ver = await _resolve_forge_version(mc_version, loader_version)
    coord = f"{mc_version}-{forge_ver}"
    url = f"{FORGE_MAVEN}/{coord}/forge-{coord}-installer.jar"
    root = Path(record.path)
    installer = root / f"forge-{coord}-installer.jar"
    logger.info("Downloading Forge server installer %s", url)
    await _stream_download(url, installer)
    await _run_installer_jar(installer, root, minecraft_version=mc_version)
    installer.unlink(missing_ok=True)
    _apply_forge_style_launch(record)
    # Marker file for jar_present checks
    marker = root / "server.jar"
    if not marker.is_file():
        marker.write_text(
            "# CultAgent: Forge server launch uses execution_command (@args)\n",
            encoding="utf-8",
        )
    record.executable = "server.jar"
    record.metadata = {
        **record.metadata,
        "forge_version": forge_ver,
        "install_kind": "forge_server",
    }
    return marker


def _neoforge_matches_mc(neoforge_ver: str, mc_version: str) -> bool:
    """NeoForge 21.1.x ≈ MC 1.21.1; 20.4.x ≈ 1.20.4."""
    parts = mc_version.split(".")
    if len(parts) < 2:
        return False
    try:
        major = int(parts[1])
        minor = int(parts[2]) if len(parts) > 2 else 0
    except ValueError:
        return False
    prefix = f"{major}.{minor}."
    return neoforge_ver.startswith(prefix)


async def _resolve_neoforge_version(mc_version: str, loader_version: str | None) -> str:
    if loader_version:
        return loader_version
    async with httpx.AsyncClient(timeout=60.0) as client:
        xml = (await client.get(NEOFORGE_META)).raise_for_status().text
    versions = re.findall(r"<version>([^<]+)</version>", xml)
    matches = [v for v in versions if _neoforge_matches_mc(v, mc_version)]
    if not matches:
        raise ValueError(f"no NeoForge release matched Minecraft {mc_version}")
    # Prefer non-beta when available
    stable = [v for v in matches if "beta" not in v.lower()]
    return (stable or matches)[-1]


async def download_neoforge_server(
    record: ServerRecord,
    *,
    version: str | None = None,
    loader_version: str | None = None,
) -> Path:
    """Download NeoForge *server* installer and run --installServer."""
    mc_version = _require_mc_version(record, version)
    neo_ver = await _resolve_neoforge_version(mc_version, loader_version)
    url = f"{NEOFORGE_MAVEN}/{neo_ver}/neoforge-{neo_ver}-installer.jar"
    root = Path(record.path)
    installer = root / f"neoforge-{neo_ver}-installer.jar"
    logger.info("Downloading NeoForge server installer %s", url)
    await _stream_download(url, installer)
    await _run_installer_jar(installer, root, minecraft_version=mc_version)
    installer.unlink(missing_ok=True)
    _apply_forge_style_launch(record)
    marker = root / "server.jar"
    if not marker.is_file():
        marker.write_text(
            "# CultAgent: NeoForge server launch uses execution_command (@args)\n",
            encoding="utf-8",
        )
    record.executable = "server.jar"
    record.metadata = {
        **record.metadata,
        "neoforge_version": neo_ver,
        "install_kind": "neoforge_server",
    }
    return marker


async def download_server_jar(
    record: ServerRecord,
    *,
    version: str | None = None,
    loader: str | None = None,
    loader_version: str | None = None,
) -> Path:
    """Install a Minecraft *server* for the requested platform."""
    kind = (loader or record.loader or "vanilla").strip().lower()
    if kind == "bukkit":
        raise ValueError(
            "CraftBukkit is not auto-installed; use paper or purpur for plugin servers"
        )
    if kind == "spigot":
        raise ValueError(
            "Spigot BuildTools is not automated; use paper or purpur (recommended)"
        )

    if kind in {"", "vanilla"}:
        return await download_vanilla_jar(record, version=version)
    if kind == "paper":
        return await download_paper_jar(record, version=version)
    if kind == "folia":
        return await download_folia_jar(record, version=version)
    if kind == "purpur":
        return await download_purpur_jar(record, version=version)
    if kind == "fabric":
        return await download_fabric_jar(record, version=version)
    if kind == "quilt":
        return await download_quilt_jar(record, version=version)
    if kind == "forge":
        return await download_forge_server(
            record, version=version, loader_version=loader_version
        )
    if kind == "neoforge":
        return await download_neoforge_server(
            record, version=version, loader_version=loader_version
        )
    raise ValueError(
        f"unsupported server loader {kind!r}; supported: {', '.join(SERVER_LOADERS)}"
    )


def jar_present(record: ServerRecord) -> bool:
    root = Path(record.path)
    if record.execution_command.strip():
        # Forge/NeoForge may use args-file launch; presence of libraries/ is enough.
        if (root / "libraries").is_dir():
            return True
        if list(root.glob("run.*")):
            return True
    return (root / record.executable).is_file()
