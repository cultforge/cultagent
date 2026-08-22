"""File manager and backups."""

from __future__ import annotations

import logging
import shutil
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("cultagent.files")

_BACKUP_SKIP_DIR_NAMES = {
    "logs",
    "cache",
    "crash-reports",
    ".cache",
}

# Server-root folders that get pinned + a special UI kind (lower = higher).
_IMPORTANT_FOLDER_KIND: dict[str, str] = {
    "world": "world",
    "mods": "mods",
    "config": "config",
    "configs": "config",
    "defaultconfigs": "config",
    "logs": "logs",
    "crash-reports": "crash",
    "libraries": "libraries",
    "resourcepacks": "packs",
    "datapacks": "packs",
    "shaderpacks": "packs",
    "backups": "backup",
}


def _folder_kind(name: str, *, is_world: bool) -> str | None:
    if is_world:
        return "world"
    return _IMPORTANT_FOLDER_KIND.get(name.lower())


def _list_sort_key(path: Path) -> tuple[int, int, str]:
    """important dirs → other dirs → files, then name."""
    name = path.name.lower()
    if not path.is_dir():
        return (2, 99, name)
    is_world = (path / "level.dat").is_file() or (path / "level.dat_old").is_file()
    kind = _folder_kind(path.name, is_world=is_world)
    if kind:
        # Stable priority among important folders
        order = {
            "world": 0,
            "mods": 1,
            "config": 2,
            "logs": 3,
            "crash": 4,
            "libraries": 5,
            "packs": 6,
            "backup": 7,
        }.get(kind, 8)
        return (0, order, name)
    return (1, 50, name)


class FileManager:
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()

    def _safe(self, relative: str) -> Path:
        target = (self.root / relative).resolve()
        if not str(target).startswith(str(self.root)):
            raise PermissionError("path escapes managed root")
        return target

    def list_dir(self, relative: str = ".") -> list[dict[str, Any]]:
        path = self._safe(relative)
        if not path.is_dir():
            raise NotADirectoryError(relative)
        items: list[dict[str, Any]] = []
        for child in sorted(path.iterdir(), key=_list_sort_key):
            is_dir = child.is_dir()
            is_world = False
            folder_kind: str | None = None
            if is_dir:
                is_world = (child / "level.dat").is_file() or (child / "level.dat_old").is_file()
                folder_kind = _folder_kind(child.name, is_world=is_world)
            items.append(
                {
                    "name": child.name,
                    "path": str(child.relative_to(self.root)).replace("\\", "/"),
                    "is_dir": is_dir,
                    "is_world": is_world,
                    "folder_kind": folder_kind,
                    "size": child.stat().st_size if child.is_file() else None,
                }
            )
        return items

    def list_worlds(self) -> list[dict[str, Any]]:
        """Discover world folders under the server root (dirs with level.dat)."""
        worlds: list[dict[str, Any]] = []
        if not self.root.is_dir():
            return worlds
        for child in sorted(self.root.iterdir(), key=lambda p: p.name.lower()):
            if not child.is_dir():
                continue
            if child.name.startswith("."):
                continue
            # Skip obvious non-world directories
            if child.name.lower() in {
                "mods",
                "config",
                "configs",
                "logs",
                "crash-reports",
                "libraries",
                "versions",
                "resourcepacks",
                "shaderpacks",
                "datapacks",
                "defaultconfigs",
                "patchouli_books",
                "journeymap",
                "modernfix",
                "tacz",
                "cache",
                ".mixin.out",
            }:
                continue
            # Dimension side-folders (world_nether / world_the_end) are not selectable level-names
            lower = child.name.lower()
            if lower.endswith("_nether") or lower.endswith("_the_end"):
                continue
            has_level = (child / "level.dat").is_file() or (child / "level.dat_old").is_file()
            has_dims = (child / "DIM-1").exists() or (child / "DIM1").exists()
            has_chunks = (child / "region").is_dir() or (child / "playerdata").is_dir()
            # Include classic empty "world" placeholder dirs so the picker can select them
            is_named_world = lower == "world"
            if not (has_level or has_dims or has_chunks or is_named_world):
                continue
            size = 0
            try:
                for f in child.rglob("*"):
                    if f.is_file():
                        try:
                            size += f.stat().st_size
                        except OSError:
                            pass
            except OSError:
                size = 0
            worlds.append(
                {
                    "name": child.name,
                    "path": child.name,
                    "has_level_dat": (child / "level.dat").is_file(),
                    "size": size,
                }
            )
        return worlds

    def read_text(self, relative: str, *, max_bytes: int = 1_000_000) -> str:
        path = self._safe(relative)
        if path.stat().st_size > max_bytes:
            raise ValueError("file too large")
        return path.read_text(encoding="utf-8")

    def write_text(self, relative: str, content: str) -> None:
        path = self._safe(relative)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


class BackupManager:
    def __init__(self, backups_dir: Path) -> None:
        self.backups_dir = backups_dir
        self.backups_dir.mkdir(parents=True, exist_ok=True)

    def list_backups(self, server_id: str | None = None) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for path in sorted(self.backups_dir.glob("**/*")):
            if not path.is_file():
                continue
            if server_id and server_id not in path.name:
                continue
            items.append(
                {
                    "name": path.name,
                    "path": str(path),
                    "size": path.stat().st_size,
                    "mtime": datetime.fromtimestamp(
                        path.stat().st_mtime, tz=timezone.utc
                    ).isoformat(),
                }
            )
        return items

    def create_backup(self, source: Path, server_id: str) -> dict[str, Any]:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        dest = self.backups_dir / f"{server_id}_{stamp}.zip"
        source = source.resolve()
        if not source.exists():
            raise FileNotFoundError(source)

        logger.info("Creating zip backup %s from %s", dest, source)
        with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            if source.is_file():
                zf.write(source, arcname=source.name)
            else:
                for path in source.rglob("*"):
                    if path.is_dir():
                        continue
                    rel_parts = path.relative_to(source).parts
                    if any(part in _BACKUP_SKIP_DIR_NAMES for part in rel_parts[:-1]):
                        continue
                    zf.write(path, arcname=str(path.relative_to(source)))

        return {
            "path": str(dest),
            "server_id": server_id,
            "size": dest.stat().st_size,
            "format": "zip",
        }

    def restore_backup(
        self,
        backup_path: Path,
        target: Path,
        *,
        confirm: bool = False,
    ) -> dict[str, Any]:
        if not confirm:
            raise PermissionError("restore requires confirm=true")
        backup_path = backup_path.resolve()
        target = target.resolve()
        if not backup_path.exists():
            raise FileNotFoundError(backup_path)
        target.mkdir(parents=True, exist_ok=True)

        logger.warning("Restoring backup %s -> %s", backup_path, target)
        if backup_path.is_dir():
            for child in backup_path.iterdir():
                dest = target / child.name
                if child.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(child, dest)
                else:
                    shutil.copy2(child, dest)
        elif zipfile.is_zipfile(backup_path):
            with zipfile.ZipFile(backup_path, "r") as zf:
                zf.extractall(target)
        else:
            raise ValueError("backup must be a zip file or directory")

        return {"path": str(backup_path), "target": str(target), "restored": True}
