"""Content providers: Modrinth + CultForge Builds."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from cultagent.content.install import install_manifest
from cultagent.content.crash_resolve import resolve_mod_issues
from cultagent.content.modrinth import (
    INDEX_NAME,
    ModrinthClient,
    download_and_install,
    load_index,
    resolve_installed_mod_dependencies,
    save_index,
)
from cultagent.settings import ContentSection

logger = logging.getLogger("cultagent.content")

__all__ = [
    "BuildManifest",
    "BuildService",
    "ContentRef",
    "INDEX_NAME",
    "ModrinthClient",
]


class ContentRef(BaseModel):
    """Pinned content reference — CultForge owns the build definition."""

    source: str = "modrinth"
    project_id: str
    version_id: str | None = None
    checksum: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    license: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class BuildManifest(BaseModel):
    build_id: str
    name: str = ""
    minecraft_version: str
    loader: str
    mods: list[ContentRef] = Field(default_factory=list)
    resource_packs: list[ContentRef] = Field(default_factory=list)
    datapacks: list[ContentRef] = Field(default_factory=list)
    shaders: list[ContentRef] = Field(default_factory=list)
    config: dict[str, Any] = Field(default_factory=dict)


class BuildService:
    """CultForge build awareness — launcher and agent share build definitions."""

    def __init__(self, content: ContentSection) -> None:
        self.section = content
        self.modrinth = ModrinthClient(content.modrinth)

    async def validate_cloud_manifest(self, manifest: dict[str, Any]) -> dict[str, Any]:
        issues: list[str] = []
        notes: list[str] = []
        mode = str(manifest.get("mode") or "")
        if mode not in {"pack", "resolved"}:
            issues.append(f"manifest mode not installable: {mode or 'missing'}")
        files = [f for f in (manifest.get("files") or []) if isinstance(f, dict)]
        if not files:
            issues.append("manifest has no files")
        unresolved = manifest.get("unresolved") or []
        if unresolved:
            issues.append(f"{len(unresolved)} unresolved entries")

        by_kind: dict[str, int] = {}
        optional_n = 0
        client_only = 0
        missing_hash = 0
        for entry in files:
            kind = str(entry.get("kind") or "file").lower()
            by_kind[kind] = by_kind.get(kind, 0) + 1
            if entry.get("optional"):
                optional_n += 1
            if str(entry.get("env") or "").lower() == "client":
                client_only += 1
            if not entry.get("sha256"):
                missing_hash += 1
            if not (entry.get("urls") or entry.get("url")):
                issues.append(f"no download URL for {entry.get('path') or kind}")

        if missing_hash:
            notes.append(f"{missing_hash} file(s) lack sha256 (install will not verify)")
        if client_only:
            notes.append(f"{client_only} client-only file(s) skipped on servers")
        if optional_n:
            notes.append(f"{optional_n} optional file(s) (use --optional to include)")

        return {
            "ok": not issues,
            "issues": issues,
            "notes": notes,
            "counts": {
                "files": len(files),
                "optional": optional_n,
                "client_only": client_only,
                "missing_sha256": missing_hash,
                "unresolved": len(unresolved) if isinstance(unresolved, list) else 0,
                "by_kind": by_kind,
            },
        }

    async def deploy_cloud_manifest(
        self,
        manifest: dict[str, Any],
        target_dir: str | Path,
        *,
        include_optional: bool = False,
        cache_dir: Path | None = None,
        resolve_deps: bool = True,
        loader: str | None = None,
        game_version: str | None = None,
    ) -> dict[str, Any]:
        check = await self.validate_cloud_manifest(manifest)
        if not check["ok"]:
            return {
                "ok": False,
                "compatibility": check,
                "installed": [],
                "errors": check["issues"],
            }
        result = await install_manifest(
            manifest,
            Path(target_dir),
            include_optional=include_optional,
            user_agent=self.section.modrinth.user_agent,
            cache_dir=cache_dir,
        )
        result["compatibility"] = check
        if resolve_deps:
            mc = str(
                game_version
                or manifest.get("minecraft_version")
                or ""
            ).strip()
            ld = str(loader or manifest.get("loader") or "forge").strip() or "forge"
            if mc:
                try:
                    deps = await resolve_installed_mod_dependencies(
                        self.modrinth,
                        target_dir,
                        loader=ld,
                        game_version=mc,
                    )
                    result["dependencies"] = deps
                    if deps.get("errors"):
                        result["ok"] = False
                    for item in deps.get("failed") or []:
                        if not isinstance(item, dict):
                            continue
                        msg = str(item.get("error") or item.get("slug") or item.get("project_id") or item)
                        result.setdefault("warnings", []).append(f"dependency: {msg}")
                    notes = check.setdefault("notes", [])
                    if isinstance(notes, list):
                        notes.append(
                            f"resolved {deps.get('added_count', 0)} required "
                            f"Modrinth deps; disabled {deps.get('disabled_count', 0)} client-only"
                        )
                except Exception as exc:  # noqa: BLE001
                    logger.warning("mod dependency resolve failed: %s", exc)
                    result.setdefault("warnings", []).append(f"dependency resolve: {exc}")
        return result

    async def list_installed_mods(self, server_dir: str | Path) -> list[dict[str, Any]]:
        root = Path(server_dir)
        index = load_index(root)
        entries = index.get("entries") if isinstance(index.get("entries"), dict) else {}
        mods_dir = root / "mods"
        out: list[dict[str, Any]] = []
        if mods_dir.is_dir():
            jar_paths = sorted(mods_dir.glob("*.jar")) + sorted(mods_dir.glob("*.jar.disabled"))
            for path in jar_paths:
                meta = entries.get(path.name) if isinstance(entries.get(path.name), dict) else {}
                disabled = path.name.endswith(".disabled") or bool(meta.get("disabled"))
                out.append(
                    {
                        "name": path.name,
                        "path": str(path),
                        "size": path.stat().st_size,
                        "enabled": not disabled,
                        "source": meta.get("source") or "local",
                        "project_id": meta.get("project_id"),
                        "slug": meta.get("slug"),
                        "version_id": meta.get("version_id"),
                        "version_number": meta.get("version_number"),
                        "title": meta.get("title"),
                    }
                )
        return out

    async def install_mod(
        self,
        server_dir: str | Path,
        *,
        project_id: str,
        version_id: str | None = None,
        loader: str = "fabric",
        game_version: str,
        install_deps: bool = True,
    ) -> dict[str, Any]:
        return await download_and_install(
            self.modrinth,
            server_dir,
            project_id=project_id,
            version_id=version_id,
            loader=loader,
            game_version=game_version,
            install_deps=install_deps,
        )

    async def remove_mod(self, server_dir: str | Path, filename: str) -> dict[str, Any]:
        root = Path(server_dir).resolve()
        name = Path(filename).name
        if not name or name in {".", ".."}:
            raise ValueError("invalid mod filename")

        # Search known content folders
        from cultagent.content.install import datapack_dir

        candidates = [
            root / "mods" / name,
            root / "plugins" / name,
            root / "resourcepacks" / name,
            root / "datapacks" / name,
            datapack_dir(root) / name,
            root / "shaderpacks" / name,
        ]
        target = next((p for p in candidates if p.is_file()), None)
        if target is None:
            raise FileNotFoundError(name)
        target = target.resolve()
        if not str(target).startswith(str(root)):
            raise PermissionError("path escapes server directory")
        target.unlink()

        index = load_index(root)
        entries = index.setdefault("entries", {})
        entries.pop(name, None)
        save_index(root, index)
        return {"removed": name, "ok": True}

    async def update_mod(
        self,
        server_dir: str | Path,
        *,
        filename: str | None = None,
        project_id: str | None = None,
        loader: str = "fabric",
        game_version: str,
        install_deps: bool = True,
    ) -> dict[str, Any]:
        root = Path(server_dir)
        index = load_index(root)
        entries = index.get("entries") if isinstance(index.get("entries"), dict) else {}

        meta: dict[str, Any] = {}
        if filename and isinstance(entries.get(filename), dict):
            meta = entries[filename]
        elif project_id:
            for entry in entries.values():
                if isinstance(entry, dict) and entry.get("project_id") == project_id:
                    meta = entry
                    filename = str(entry.get("filename") or filename)
                    break

        pid = project_id or meta.get("project_id")
        if not pid:
            raise ValueError("project_id required (or install via Modrinth first so index knows it)")
        if filename:
            try:
                await self.remove_mod(server_dir, str(filename))
            except FileNotFoundError:
                pass

        installed = await self.install_mod(
            server_dir,
            project_id=str(pid),
            loader=loader,
            game_version=game_version,
            install_deps=install_deps,
        )
        return {"previous": {"filename": filename, "project_id": pid}, "installed": installed}

    async def resolve_mod_dependencies(
        self,
        server_dir: str | Path,
        *,
        loader: str,
        game_version: str,
        disable_client_only: bool = True,
        source: str = "auto",
        crash_path: str | Path | None = None,
        also_scan_jars: bool = False,
    ) -> dict[str, Any]:
        return await resolve_mod_issues(
            self.modrinth,
            server_dir,
            loader=loader,
            game_version=game_version,
            source=source,
            crash_path=crash_path,
            also_scan_jars=also_scan_jars,
            disable_client_only=disable_client_only,
        )
