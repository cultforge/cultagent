"""Reconcile a chambered build manifest with on-disk content (server-refresh)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from cultagent.content.install import (
    _CONTENT_ROOT_FOLDERS,
    datapack_dir,
    migrate_root_datapacks,
    resolve_entry_path,
)
from cultagent.content.modrinth import dedupe_mods_by_project

logger = logging.getLogger("cultagent.content.refresh")

_MANAGED_SUFFIXES = {".jar", ".zip", ".jar.disabled"}


def expected_content_paths(
    manifest: dict[str, Any],
    server_root: Path,
    *,
    include_optional: bool = False,
) -> set[str]:
    """Relative paths the manifest wants on disk (server-side only)."""
    root = Path(server_root).resolve()
    out: set[str] = set()
    for entry in manifest.get("files") or []:
        if not isinstance(entry, dict):
            continue
        if not include_optional and entry.get("optional"):
            continue
        env = str(entry.get("env") or "both").lower()
        if env == "client":
            continue
        rel = resolve_entry_path(entry, root)
        if rel:
            out.add(rel.replace("\\", "/"))
    return out


def _is_content_file(path: Path) -> bool:
    name = path.name.lower()
    if name.startswith("."):
        return False
    if name.endswith(".disabled"):
        return True
    return path.suffix.lower() in {".jar", ".zip"}


def prune_unmanaged_content(
    server_root: Path,
    keep: set[str],
    *,
    dry_run: bool = False,
) -> list[dict[str, Any]]:
    """Remove mods/packs/shaders/datapacks not listed in the keep set.

    Only touches known content folders. Does not touch configs, worlds (except
    ``<level>/datapacks``), or jars outside those folders.
    """
    root = Path(server_root).resolve()
    keep_norm = {p.replace("\\", "/").lstrip("/") for p in keep}
    removed: list[dict[str, Any]] = []

    folders: list[Path] = [root / f for f in _CONTENT_ROOT_FOLDERS if f != "datapacks"]
    folders.append(datapack_dir(root))

    for folder in folders:
        if not folder.is_dir():
            continue
        for path in sorted(folder.iterdir()):
            if not path.is_file() or not _is_content_file(path):
                continue
            try:
                rel = path.relative_to(root).as_posix()
            except ValueError:
                continue
            if rel in keep_norm:
                continue
            # Keep disabled twin if enabled form is kept
            if rel.endswith(".disabled"):
                base = rel[: -len(".disabled")]
                if base in keep_norm:
                    continue
            removed.append({"path": rel, "size": path.stat().st_size})
            if not dry_run:
                try:
                    path.unlink(missing_ok=True)
                except OSError as exc:
                    logger.warning("prune failed %s: %s", rel, exc)
    return removed


async def refresh_server_from_manifest(
    *,
    app: Any,
    server_id: str,
    build_id: str | None = None,
    include_optional: bool = False,
    prune: bool = True,
    resolve_deps: bool = False,
    install_platform: bool = False,
) -> dict[str, Any]:
    """Sync chambered build content: install missing, prune extras, dedupe deps.

    Honors pinned manifest ``files[]`` by default (``resolve_deps=False``).
    """
    record = await app.servers.get(server_id)
    if record is None:
        raise KeyError(f"unknown server: {server_id}")

    bid = (
        build_id
        or getattr(record, "build_id", None)
        or (record.metadata or {}).get("build_id")
    )
    if not bid:
        raise ValueError(
            "server has no build_id — bind/clone a chambered build or pass --build"
        )

    root = Path(record.path).resolve()
    migrated = migrate_root_datapacks(root)

    # Full reinstall of content (+ optional platform) via existing pipeline
    install_result = await app.builds.install_to_server(
        str(bid),
        server_id,
        include_optional=include_optional,
        install_platform=install_platform,
        force_platform=False,
        accept_eula=True,
        resolve_deps=resolve_deps,
    )
    manifest = await app.builds.get_manifest(str(bid))
    expected = expected_content_paths(
        manifest, root, include_optional=include_optional
    )

    # Keep jars that dep-resolve just installed (indexed Modrinth entries)
    from cultagent.content.modrinth import load_index

    index = load_index(root)
    entries = index.get("entries") if isinstance(index.get("entries"), dict) else {}
    for _name, meta in entries.items():
        if isinstance(meta, dict) and meta.get("path"):
            expected.add(str(meta["path"]).replace("\\", "/"))

    pruned: list[dict[str, Any]] = []
    if prune:
        pruned = prune_unmanaged_content(root, expected, dry_run=False)

    dedupe = dedupe_mods_by_project(root)

    install_ok = bool((install_result.get("install") or {}).get("ok", True))
    return {
        "ok": install_ok,
        "server_id": server_id,
        "build_id": str(bid),
        "install": install_result,
        "expected_count": len(expected),
        "pruned": pruned,
        "pruned_count": len(pruned),
        "migrated_datapacks": migrated,
        "dedupe": dedupe,
        "datapack_dir": str(datapack_dir(root).relative_to(root)).replace("\\", "/"),
    }
