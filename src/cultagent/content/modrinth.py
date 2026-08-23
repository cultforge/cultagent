"""Modrinth API client + install helpers (content provider only)."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

import httpx

from cultagent.content.progress import report_progress
from cultagent.settings import ModrinthSection

logger = logging.getLogger("cultagent.content.modrinth")

INDEX_NAME = ".cultagent-modrinth.json"

_PROJECT_TYPE_DIRS = {
    "mod": "mods",
    "plugin": "plugins",
    "resourcepack": "resourcepacks",
    "datapack": "datapacks",
    "shader": "shaderpacks",
}


class ModrinthClient:
    def __init__(self, section: ModrinthSection) -> None:
        self.section = section

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self.section.user_agent,
            "Accept": "application/json",
        }

    async def search(
        self,
        query: str,
        *,
        limit: int = 20,
        offset: int = 0,
        project_type: str | None = "mod",
        loader: str | None = None,
        game_version: str | None = None,
    ) -> dict[str, Any]:
        facets: list[list[str]] = []
        if project_type:
            facets.append([f"project_type:{project_type}"])
        if loader:
            facets.append([f"categories:{loader}"])
        if game_version:
            facets.append([f"versions:{game_version}"])
        params: dict[str, Any] = {
            "query": query,
            "limit": max(1, min(int(limit), 100)),
            "offset": max(0, int(offset)),
        }
        if facets:
            params["facets"] = json.dumps(facets)
        async with httpx.AsyncClient(
            base_url=self.section.api_base.rstrip("/"),
            headers=self._headers(),
            timeout=30.0,
        ) as client:
            response = await client.get("/search", params=params)
            response.raise_for_status()
            return response.json()

    async def project(self, project_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self.section.api_base.rstrip("/"),
            headers=self._headers(),
            timeout=30.0,
        ) as client:
            response = await client.get(f"/project/{project_id}")
            response.raise_for_status()
            return response.json()

    async def version(self, version_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self.section.api_base.rstrip("/"),
            headers=self._headers(),
            timeout=30.0,
        ) as client:
            response = await client.get(f"/version/{version_id}")
            response.raise_for_status()
            return response.json()

    async def version_files(
        self,
        project_id: str,
        *,
        loader: str,
        game_version: str,
    ) -> list[dict[str, Any]]:
        params = {
            "loaders": json.dumps([loader]),
            "game_versions": json.dumps([game_version]),
        }
        async with httpx.AsyncClient(
            base_url=self.section.api_base.rstrip("/"),
            headers=self._headers(),
            timeout=30.0,
        ) as client:
            response = await client.get(f"/project/{project_id}/version", params=params)
            response.raise_for_status()
            return list(response.json() or [])

    async def dependencies(self, project_id: str) -> dict[str, Any]:
        async with httpx.AsyncClient(
            base_url=self.section.api_base.rstrip("/"),
            headers=self._headers(),
            timeout=30.0,
        ) as client:
            response = await client.get(f"/project/{project_id}/dependencies")
            response.raise_for_status()
            return response.json()

    async def versions_by_hashes(
        self,
        hashes: list[str],
        *,
        algorithm: str = "sha1",
    ) -> dict[str, dict[str, Any]]:
        """POST /version_files — map file hash → Modrinth version (empty if unknown)."""
        cleaned = [h for h in hashes if h]
        if not cleaned:
            return {}
        out: dict[str, dict[str, Any]] = {}
        async with httpx.AsyncClient(
            base_url=self.section.api_base.rstrip("/"),
            headers=self._headers(),
            timeout=60.0,
        ) as client:
            for i in range(0, len(cleaned), 64):
                chunk = cleaned[i : i + 64]
                response = await client.post(
                    "/version_files",
                    json={"hashes": chunk, "algorithm": algorithm},
                )
                response.raise_for_status()
                payload = response.json()
                if isinstance(payload, dict):
                    for key, value in payload.items():
                        if isinstance(value, dict):
                            out[str(key)] = value
        return out


def load_index(server_dir: Path) -> dict[str, Any]:
    path = Path(server_dir) / INDEX_NAME
    if not path.is_file():
        return {"schema_version": 1, "entries": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"schema_version": 1, "entries": {}}
        data.setdefault("entries", {})
        return data
    except Exception:  # noqa: BLE001
        return {"schema_version": 1, "entries": {}}


def save_index(server_dir: Path, index: dict[str, Any]) -> None:
    path = Path(server_dir) / INDEX_NAME
    path.write_text(json.dumps(index, indent=2) + "\n", encoding="utf-8")


def _pick_primary_file(version: dict[str, Any]) -> dict[str, Any] | None:
    files = version.get("files") or []
    if not files:
        return None
    return next((f for f in files if f.get("primary")), files[0])


def _dest_dir(server_root: Path, project_type: str) -> Path:
    folder = _PROJECT_TYPE_DIRS.get(project_type, "mods")
    if folder == "datapacks":
        from cultagent.content.install import datapack_dir

        dest = datapack_dir(server_root)
    else:
        dest = server_root / folder
    dest.mkdir(parents=True, exist_ok=True)
    return dest


_PLATFORM_PROJECTS = {
    "minecraft",
    "java",
    "forge",
    "neoforge",
    "fabric-loader",
    "fabricloader",
    "fabric-api",
    "fabric-api-base",
    "quilt-loader",
    "quilt_loader",
    "quilted-fabric-api",
    "qsl",
    "quilt-standard-libraries",
    "cardinal-components-api",
    "cardinal-components-base",
}


def _is_other_loader_slug(slug: str, server_loader: str) -> bool:
    """True when a dependency slug clearly targets a different mod loader."""
    s = slug.lower()
    sl = server_loader.lower()
    if sl in {"forge", "neoforge"}:
        return any(k in s for k in ("fabric", "quilt", "qsl", "cardinal-components"))
    if sl in {"fabric", "quilt"}:
        return any(k in s for k in ("forge", "neoforge", "neoforge"))
    return False


def _version_matches_loader(version: dict[str, Any], loader: str) -> bool:
    loaders = {str(x).lower() for x in (version.get("loaders") or [])}
    if not loaders:
        return True
    return not loaders.isdisjoint({c.lower() for c in loader_candidates(loader)})


def loader_candidates(loader: str) -> list[str]:
    """Modrinth loader tags to try, including Forge↔NeoForge fallbacks."""
    raw = (loader or "forge").strip().lower()
    if raw in {"neoforge", "neo"}:
        return ["neoforge", "forge"]
    if raw == "quilt":
        return ["quilt", "fabric"]
    return [raw]


def is_platform_dependency(project_id: str | None, slug: str | None = None) -> bool:
    tokens = {str(project_id or "").strip().lower(), str(slug or "").strip().lower()}
    tokens.discard("")
    return bool(tokens & _PLATFORM_PROJECTS)


def _sha1_file(path: Path) -> str:
    h = hashlib.sha1()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 64), b""):
            h.update(chunk)
    return h.hexdigest()


def _verify_hashes(path: Path, hashes: dict[str, Any] | None) -> dict[str, Any]:
    if not hashes:
        return {"verified": False, "reason": "no hashes from Modrinth"}
    raw = path.read_bytes()
    checks: dict[str, bool] = {}
    if hashes.get("sha512"):
        checks["sha512"] = hashlib.sha512(raw).hexdigest().lower() == str(hashes["sha512"]).lower()
    if hashes.get("sha1"):
        checks["sha1"] = hashlib.sha1(raw).hexdigest().lower() == str(hashes["sha1"]).lower()
    ok = all(checks.values()) if checks else False
    if checks and not ok:
        path.unlink(missing_ok=True)
        raise RuntimeError(f"hash mismatch for {path.name}: {checks}")
    return {"verified": ok, "checks": checks}


def compatibility_report(
    *,
    project: dict[str, Any],
    version: dict[str, Any],
    loader: str,
    game_version: str,
) -> dict[str, Any]:
    issues: list[str] = []
    notes: list[str] = []
    loaders = [str(x).lower() for x in (version.get("loaders") or [])]
    games = [str(x) for x in (version.get("game_versions") or [])]
    if loader.lower() not in loaders and loaders:
        issues.append(f"version loaders {loaders} do not include {loader}")
    if game_version not in games and games:
        issues.append(f"version game_versions do not include {game_version}")

    server_side = str(project.get("server_side") or "").lower()
    if server_side == "unsupported":
        issues.append("project marks server_side=unsupported")
    elif server_side == "optional":
        notes.append("project is optional on servers")

    deps = [d for d in (version.get("dependencies") or []) if isinstance(d, dict)]
    required = [d for d in deps if str(d.get("dependency_type") or "").lower() == "required"]
    optional = [d for d in deps if str(d.get("dependency_type") or "").lower() == "optional"]
    incompatible = [
        d for d in deps if str(d.get("dependency_type") or "").lower() == "incompatible"
    ]
    if required:
        notes.append(f"{len(required)} required dependency(ies)")
    if incompatible:
        issues.append(f"{len(incompatible)} incompatible dependency flag(s) on this version")

    return {
        "ok": not issues,
        "issues": issues,
        "notes": notes,
        "loaders": loaders,
        "game_versions": games[:12],
        "dependencies": {
            "required": required,
            "optional": optional,
            "incompatible": incompatible,
        },
    }


def _index_entries_for_project(root: Path, project_id: str) -> list[tuple[str, dict[str, Any]]]:
    index = load_index(root)
    entries = index.get("entries") if isinstance(index.get("entries"), dict) else {}
    pid = str(project_id)
    out: list[tuple[str, dict[str, Any]]] = []
    for name, entry in entries.items():
        if isinstance(entry, dict) and str(entry.get("project_id") or "") == pid:
            out.append((str(name), entry))
    return out


def _index_entry_for_project(root: Path, project_id: str) -> tuple[str, dict[str, Any]] | None:
    matches = _index_entries_for_project(root, project_id)
    return matches[0] if matches else None


def _remove_indexed_jar(root: Path, filename: str) -> None:
    name = Path(filename).name
    for folder in ("mods", "plugins", "resourcepacks", "datapacks", "shaderpacks"):
        path = root / folder / name
        if path.is_file():
            path.unlink(missing_ok=True)
            break
    # Also check world datapacks
    try:
        from cultagent.content.install import datapack_dir

        dp = datapack_dir(root) / name
        if dp.is_file():
            dp.unlink(missing_ok=True)
    except Exception:  # noqa: BLE001
        pass
    index = load_index(root)
    entries = index.setdefault("entries", {})
    if isinstance(entries, dict):
        entries.pop(name, None)
        save_index(root, index)


def _remove_all_project_jars(root: Path, project_id: str) -> list[str]:
    """Remove every indexed jar for a Modrinth project (all versions / filenames)."""
    removed: list[str] = []
    for name, _meta in list(_index_entries_for_project(root, project_id)):
        _remove_indexed_jar(root, name)
        removed.append(name)
    return removed


def dedupe_mods_by_project(server_dir: str | Path) -> dict[str, Any]:
    """Keep one jar per project_id; drop older / duplicate filenames.

    Preference: entry with highest ``version_number`` string (best-effort), else
    the last indexed entry. Orphan jars without an index entry are left alone.
    """
    root = Path(server_dir).resolve()
    index = load_index(root)
    entries = index.get("entries") if isinstance(index.get("entries"), dict) else {}
    by_project: dict[str, list[tuple[str, dict[str, Any]]]] = {}
    for name, meta in list(entries.items()):
        if not isinstance(meta, dict):
            continue
        pid = str(meta.get("project_id") or "").strip()
        if not pid:
            continue
        by_project.setdefault(pid, []).append((name, meta))

    removed: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = []
    for pid, rows in by_project.items():
        if len(rows) < 2:
            if rows:
                kept.append({"project_id": pid, "filename": rows[0][0]})
            continue
        # Prefer non-disabled, then highest version_number lexicographically.
        def _rank(item: tuple[str, dict[str, Any]]) -> tuple[int, str]:
            name, meta = item
            disabled = 1 if name.endswith(".disabled") or meta.get("disabled") else 0
            ver = str(meta.get("version_number") or meta.get("version_id") or "")
            return (disabled, ver)

        rows_sorted = sorted(rows, key=_rank)
        winner_name, winner_meta = rows_sorted[-1]
        for name, meta in rows_sorted[:-1]:
            _remove_indexed_jar(root, name)
            removed.append(
                {
                    "project_id": pid,
                    "filename": name,
                    "version_id": meta.get("version_id"),
                    "kept": winner_name,
                }
            )
        kept.append(
            {
                "project_id": pid,
                "filename": winner_name,
                "version_id": winner_meta.get("version_id"),
            }
        )
    return {"ok": True, "removed": removed, "kept": kept, "removed_count": len(removed)}


async def _pick_compatible_version(
    client: ModrinthClient,
    project_id: str,
    *,
    loader: str,
    game_version: str,
    version_id: str | None = None,
) -> dict[str, Any] | None:
    if version_id:
        try:
            return await client.version(str(version_id))
        except Exception:  # noqa: BLE001
            logger.debug("Modrinth version %s lookup failed", version_id, exc_info=True)
    for cand in loader_candidates(loader):
        versions = await client.version_files(
            project_id, loader=cand, game_version=game_version
        )
        if versions:
            return versions[0]
    return None


async def download_and_install(
    client: ModrinthClient,
    server_dir: str | Path,
    *,
    project_id: str,
    version_id: str | None = None,
    loader: str = "fabric",
    game_version: str,
    install_deps: bool = True,
    allow_client: bool = False,
    _visited: set[str] | None = None,
) -> dict[str, Any]:
    """Install a Modrinth project file into the server, with required deps by default."""
    root = Path(server_dir).resolve()
    visited = _visited if _visited is not None else set()
    project = await client.project(project_id)
    pid = str(project.get("id") or project_id)
    slug = str(project.get("slug") or pid)
    project_type = str(project.get("project_type") or "mod")

    if is_platform_dependency(pid, slug):
        return {
            "ok": True,
            "skipped": True,
            "reason": "platform",
            "project_id": pid,
            "slug": slug,
        }

    server_side = str(project.get("server_side") or "").lower()
    if server_side == "unsupported" and not allow_client:
        return {
            "ok": True,
            "skipped": True,
            "reason": "client_only",
            "project_id": pid,
            "slug": slug,
            "title": project.get("title"),
        }

    chosen = await _pick_compatible_version(
        client,
        pid,
        loader=loader,
        game_version=game_version,
        version_id=version_id,
    )
    if chosen is None:
        raise LookupError(f"no Modrinth versions for {slug} ({loader}/{game_version})")

    chosen_vid = str(chosen.get("id") or "")

    # Already installing / installed this exact project+version in this walk.
    visit_key = f"{pid}@{chosen_vid}" if chosen_vid else pid
    if visit_key in visited or (pid in visited and not version_id):
        existing_skip = _index_entry_for_project(root, pid)
        if existing_skip:
            old_name, old_meta = existing_skip
            if str(old_meta.get("version_id") or "") == chosen_vid:
                return {
                    "ok": True,
                    "skipped": True,
                    "reason": "cycle",
                    "project_id": pid,
                    "slug": slug,
                    "filename": old_name,
                    "version_id": chosen_vid,
                }
        # Different version requested while pid already visited → still upgrade below.
    visited.add(pid)
    visited.add(visit_key)

    compat_loader = loader_candidates(loader)[0]
    compat = compatibility_report(
        project=project, version=chosen, loader=compat_loader, game_version=game_version
    )
    # Loader fallback (NeoForge→Forge) can flag a mismatch even when the jar is usable.
    if not compat["ok"]:
        issues = [i for i in compat["issues"] if "loaders" not in i]
        if issues and not version_id:
            return {
                "ok": False,
                "project_id": pid,
                "slug": slug,
                "compatibility": compat,
                "error": "; ".join(compat["issues"]),
            }

    existing_rows = _index_entries_for_project(root, pid)
    if existing_rows:
        same = [
            (n, m)
            for n, m in existing_rows
            if str(m.get("version_id") or "") == chosen_vid
        ]
        if same and (root / str(same[0][1].get("path") or f"mods/{same[0][0]}")).is_file():
            old_name, old_meta = same[0]
            # Drop any extra duplicate copies of other filenames
            for n, _m in existing_rows:
                if n != old_name:
                    _remove_indexed_jar(root, n)
            dep_results: list[dict[str, Any]] = []
            if install_deps:
                dep_results = await _install_required_deps(
                    client,
                    root,
                    version=chosen,
                    loader=loader,
                    game_version=game_version,
                    visited=visited,
                )
            return {
                "ok": True,
                "skipped": True,
                "reason": "already_present",
                "project_id": pid,
                "slug": slug,
                "filename": old_name,
                "version_id": old_meta.get("version_id"),
                "dependencies_installed": dep_results,
            }
        # Replace every indexed copy of this project before installing the new one.
        _remove_all_project_jars(root, pid)

    primary = _pick_primary_file(chosen)
    if not primary or not primary.get("url"):
        raise RuntimeError("Modrinth version has no downloadable file")

    dest_dir = _dest_dir(root, project_type)
    filename = str(primary.get("filename") or f"{slug}.jar")
    dest = dest_dir / Path(filename).name

    async with httpx.AsyncClient(
        timeout=None,
        follow_redirects=True,
        headers={"User-Agent": client.section.user_agent},
    ) as http:
        async with http.stream("GET", primary["url"]) as response:
            response.raise_for_status()
            with dest.open("wb") as fh:
                async for chunk in response.aiter_bytes():
                    fh.write(chunk)

    hash_info = _verify_hashes(dest, primary.get("hashes") if isinstance(primary.get("hashes"), dict) else None)

    entry = {
        "source": "modrinth",
        "project_id": pid,
        "slug": slug,
        "title": project.get("title"),
        "project_type": project_type,
        "version_id": chosen.get("id"),
        "version_number": chosen.get("version_number"),
        "filename": dest.name,
        "path": str(dest.relative_to(root)).replace("\\", "/"),
        "loader": loader,
        "game_version": game_version,
        "license": (project.get("license") or {}).get("id")
        if isinstance(project.get("license"), dict)
        else project.get("license"),
        "sha512": (primary.get("hashes") or {}).get("sha512"),
        "dependencies": chosen.get("dependencies") or [],
    }
    index = load_index(root)
    entries = index.setdefault("entries", {})
    entries[dest.name] = entry
    save_index(root, index)

    dep_results = []
    if install_deps:
        dep_results = await _install_required_deps(
            client,
            root,
            version=chosen,
            loader=loader,
            game_version=game_version,
            visited=visited,
        )

    return {
        "ok": True,
        "project_id": pid,
        "slug": slug,
        "title": project.get("title"),
        "version_id": chosen.get("id"),
        "version_number": chosen.get("version_number"),
        "filename": dest.name,
        "path": str(dest),
        "size": dest.stat().st_size,
        "project_type": project_type,
        "hash": hash_info,
        "compatibility": compat,
        "dependencies_installed": dep_results,
        "source": "modrinth",
    }


async def _install_required_deps(
    client: ModrinthClient,
    root: Path,
    *,
    version: dict[str, Any],
    loader: str,
    game_version: str,
    visited: set[str],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    deps = [d for d in (version.get("dependencies") or []) if isinstance(d, dict)]
    required = [d for d in deps if str(d.get("dependency_type") or "").lower() == "required"]
    for dep in required:
        dep_project = dep.get("project_id")
        if not dep_project:
            continue
        if is_platform_dependency(str(dep_project)):
            continue
        try:
            results.append(
                await download_and_install(
                    client,
                    root,
                    project_id=str(dep_project),
                    version_id=str(dep["version_id"]) if dep.get("version_id") else None,
                    loader=loader,
                    game_version=game_version,
                    install_deps=True,
                    allow_client=False,
                    _visited=visited,
                )
            )
        except LookupError as exc:
            err = str(exc)
            slug_part = ""
            if " for " in err and " (" in err:
                slug_part = err.split(" for ", 1)[1].split(" (", 1)[0].strip()
            if slug_part and (
                slug_part in _PLATFORM_PROJECTS or _is_other_loader_slug(slug_part, loader)
            ):
                results.append(
                    {
                        "ok": True,
                        "skipped": True,
                        "reason": "wrong_platform",
                        "project_id": dep_project,
                        "slug": slug_part,
                        "detail": err,
                    }
                )
            else:
                logger.warning("required dep %s failed: %s", dep_project, exc)
                results.append(
                    {"ok": False, "project_id": dep_project, "slug": slug_part, "error": err}
                )
        except Exception as exc:  # noqa: BLE001
            logger.warning("required dep %s failed: %s", dep_project, exc)
            results.append({"ok": False, "project_id": dep_project, "error": str(exc)})
    return results


def _disable_client_jar(root: Path, filename: str) -> str | None:
    name = Path(filename).name
    src = root / "mods" / name
    if not src.is_file():
        return None
    dest = src.with_name(src.name + ".disabled")
    if dest.exists():
        dest.unlink()
    src.rename(dest)
    index = load_index(root)
    entries = index.setdefault("entries", {})
    if isinstance(entries, dict) and name in entries:
        meta = dict(entries.pop(name) or {})
        meta["disabled"] = True
        meta["filename"] = dest.name
        entries[dest.name] = meta
        save_index(root, index)
    return dest.name


async def resolve_installed_mod_dependencies(
    client: ModrinthClient,
    server_dir: str | Path,
    *,
    loader: str,
    game_version: str,
    disable_client_only: bool = True,
) -> dict[str, Any]:
    """Identify jars via Modrinth hashes and install missing *required* deps.

    Guild manifests often list gameplay mods without library jars (curios,
    moonlight, yungsapi, …). This walk fills those gaps and can disable
    client-only jars that crash a dedicated Forge server.
    """
    root = Path(server_dir).resolve()
    mods_dir = root / "mods"
    jars = sorted(mods_dir.glob("*.jar")) if mods_dir.is_dir() else []
    hash_to_name = {_sha1_file(p): p.name for p in jars}
    identified: list[dict[str, Any]] = []
    unknown: list[str] = []
    disabled: list[str] = []
    installed: list[dict[str, Any]] = []
    errors: list[str] = []

    report_progress({"type": "deps_start", "total_jars": len(jars)})

    versions = await client.versions_by_hashes(list(hash_to_name)) if hash_to_name else {}
    visited: set[str] = set()

    for index, (sha, filename) in enumerate(hash_to_name.items()):
        report_progress(
            {
                "type": "deps_jar",
                "filename": filename,
                "index": index,
                "total_jars": len(hash_to_name),
            }
        )
        version = versions.get(sha)
        if not isinstance(version, dict):
            unknown.append(filename)
            continue
        pid = str(version.get("project_id") or "")
        identified.append(
            {
                "filename": filename,
                "project_id": pid,
                "version_id": version.get("id"),
                "version_number": version.get("version_number"),
            }
        )
        index = load_index(root)
        entries = index.setdefault("entries", {})
        if isinstance(entries, dict) and filename not in entries:
            entries[filename] = {
                "source": "modrinth-hash",
                "project_id": pid,
                "version_id": version.get("id"),
                "version_number": version.get("version_number"),
                "filename": filename,
                "path": f"mods/{filename}",
                "dependencies": version.get("dependencies") or [],
            }
            save_index(root, index)

        if not _version_matches_loader(version, loader):
            continue

        if disable_client_only and pid:
            try:
                project = await client.project(pid)
            except Exception:  # noqa: BLE001
                project = {}
            if str(project.get("server_side") or "").lower() == "unsupported":
                renamed = _disable_client_jar(root, filename)
                if renamed:
                    disabled.append(renamed)
                continue

        try:
            dep_results = await _install_required_deps(
                client,
                root,
                version=version,
                loader=loader,
                game_version=game_version,
                visited=visited,
            )
            installed.extend(dep_results)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{filename}: {exc}")

    added = [
        r
        for r in installed
        if r.get("ok") and not r.get("skipped")
    ]
    skipped = [r for r in installed if r.get("skipped")]
    failed = [r for r in installed if r.get("ok") is False]
    dedupe = dedupe_mods_by_project(root)
    report_progress(
        {
            "type": "deps_done",
            "added": len(added),
            "failed": len(failed),
            "disabled": len(disabled),
            "deduped": dedupe.get("removed_count", 0),
        }
    )
    return {
        "ok": not errors and not failed,
        "jars": len(jars),
        "identified": identified,
        "unknown": unknown,
        "disabled_client_only": disabled,
        "installed": added,
        "skipped": skipped,
        "failed": failed,
        "errors": errors,
        "added_count": len(added),
        "disabled_count": len(disabled),
        "dedupe": dedupe,
    }
