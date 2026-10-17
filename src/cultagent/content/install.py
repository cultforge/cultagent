"""Install CultForge build manifests onto a local server directory."""

from __future__ import annotations

import hashlib
import logging
import shutil
import zipfile
from pathlib import Path
from typing import Any

import httpx

from cultagent.cache import cache_file_path
from cultagent.content.progress import report_progress

logger = logging.getLogger("cultagent.content.install")

_KIND_DIRS = {
    "mod": "mods",
    "mods": "mods",
    "shader": "shaderpacks",
    "shaders": "shaderpacks",
    "shaderpack": "shaderpacks",
    "resourcepack": "resourcepacks",
    "resourcepacks": "resourcepacks",
    "resource_pack": "resourcepacks",
    "datapack": "datapacks",
    "datapacks": "datapacks",
    "data_pack": "datapacks",
    "config": "config",
}

_CONTENT_ROOT_FOLDERS = ("mods", "resourcepacks", "shaderpacks", "datapacks", "plugins")


def read_level_name(server_root: Path) -> str:
    """Active world folder from server.properties (default ``world``)."""
    props = Path(server_root) / "server.properties"
    if not props.is_file():
        return "world"
    try:
        for line in props.read_text(encoding="utf-8", errors="replace").splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            key, _, value = raw.partition("=")
            if key.strip() == "level-name":
                name = value.strip() or "world"
                # Reject path traversal / absolute paths
                if "/" in name or "\\" in name or name in {".", ".."}:
                    return "world"
                return name
    except OSError:
        pass
    return "world"


def datapack_dir(server_root: Path) -> Path:
    """Minecraft loads datapacks from ``<level-name>/datapacks/``, not server-root."""
    return Path(server_root) / read_level_name(server_root) / "datapacks"


def resolve_entry_path(entry: dict[str, Any], server_root: Path | None = None) -> str:
    """Normalize relative install path; place bare filenames under kind dirs.

    Datapacks always target ``{level-name}/datapacks/…`` so the server actually
    loads them (vanilla / Forge / NeoForge).
    """
    rel = str(entry.get("path") or "").replace("\\", "/").lstrip("/")
    kind = str(entry.get("kind") or "").lower().replace(" ", "")
    if not rel:
        return rel

    # Remap legacy / mistaken server-root datapacks/… → world/datapacks/…
    lower = rel.lower()
    if lower.startswith("datapacks/") or kind in {"datapack", "datapacks", "data_pack"}:
        name = Path(rel).name
        if server_root is not None:
            level = read_level_name(server_root)
            return f"{level}/datapacks/{name}"
        return f"world/datapacks/{name}"

    if "/" in rel:
        return rel
    folder = _KIND_DIRS.get(kind)
    if folder == "datapacks":
        if server_root is not None:
            level = read_level_name(server_root)
            return f"{level}/datapacks/{rel}"
        return f"world/datapacks/{rel}"
    if folder:
        return f"{folder}/{rel}"
    return rel


def migrate_root_datapacks(server_root: Path) -> list[str]:
    """Move leftover ``server/datapacks/*`` into the active world datapacks folder."""
    root = Path(server_root).resolve()
    legacy = root / "datapacks"
    if not legacy.is_dir():
        return []
    dest = datapack_dir(root)
    dest.mkdir(parents=True, exist_ok=True)
    moved: list[str] = []
    for item in list(legacy.iterdir()):
        if not item.is_file():
            continue
        target = dest / item.name
        try:
            if target.exists():
                item.unlink(missing_ok=True)
            else:
                shutil.move(str(item), str(target))
                moved.append(str(target.relative_to(root)).replace("\\", "/"))
        except OSError as exc:
            logger.warning("datapack migrate %s failed: %s", item.name, exc)
    try:
        if legacy.is_dir() and not any(legacy.iterdir()):
            legacy.rmdir()
    except OSError:
        pass
    return moved


def _safe_join(root: Path, relative: str) -> Path:
    target = (root / relative).resolve()
    if not str(target).startswith(str(root.resolve())):
        raise PermissionError(f"path escapes server root: {relative}")
    return target


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 64), b""):
            h.update(chunk)
    return h.hexdigest()


def _sha512_file(path: Path) -> str:
    h = hashlib.sha512()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 64), b""):
            h.update(chunk)
    return h.hexdigest()


def _copy_from_cache(cache_path: Path, dest: Path) -> dict[str, Any]:
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(cache_path, dest)
    digest = _sha256_file(dest)
    return {
        "path": str(dest),
        "url": "cache",
        "sha256": digest,
        "size": dest.stat().st_size,
        "cached": True,
    }


def _file_matches_hashes(
    path: Path,
    *,
    expected_sha256: str | None = None,
    expected_sha512: str | None = None,
) -> bool:
    if expected_sha256:
        return _sha256_file(path).lower() == str(expected_sha256).lower()
    if expected_sha512:
        return _sha512_file(path).lower() == str(expected_sha512).lower()
    return False


async def _download(
    client: httpx.AsyncClient,
    urls: list[str],
    dest: Path,
    *,
    expected_sha256: str | None = None,
    expected_sha512: str | None = None,
    expected_size: int | None = None,
    label: str = "",
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    name = label or dest.name
    if cache_dir and expected_sha256:
        cached = cache_file_path(cache_dir, sha256=str(expected_sha256))
        if cached.is_file():
            try:
                if _sha256_file(cached).lower() == str(expected_sha256).lower():
                    size = cached.stat().st_size
                    report_progress(
                        {
                            "type": "file_progress",
                            "path": name,
                            "downloaded": size,
                            "total": size,
                            "cached": True,
                        }
                    )
                    return _copy_from_cache(cached, dest)
            except OSError:
                pass

    last_error: Exception | None = None
    for url in urls:
        try:
            dest.parent.mkdir(parents=True, exist_ok=True)
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                hasher256 = hashlib.sha256()
                hasher512 = hashlib.sha512() if expected_sha512 else None
                total = 0
                header_len = response.headers.get("content-length")
                known_total: int | None = None
                if header_len and header_len.isdigit():
                    known_total = int(header_len)
                elif expected_size is not None:
                    known_total = int(expected_size)
                report_progress(
                    {
                        "type": "file_start",
                        "path": name,
                        "total": known_total,
                        "url": url,
                    }
                )
                with dest.open("wb") as fh:
                    async for chunk in response.aiter_bytes():
                        total += len(chunk)
                        hasher256.update(chunk)
                        if hasher512 is not None:
                            hasher512.update(chunk)
                        fh.write(chunk)
                        report_progress(
                            {
                                "type": "file_progress",
                                "path": name,
                                "downloaded": total,
                                "total": known_total,
                            }
                        )
            digest = hasher256.hexdigest()
            digest512 = hasher512.hexdigest() if hasher512 is not None else None
            if expected_sha256 and digest.lower() != expected_sha256.lower():
                dest.unlink(missing_ok=True)
                raise RuntimeError(
                    f"sha256 mismatch for {dest.name}: expected {expected_sha256}, got {digest}"
                )
            if expected_sha512 and digest512 and digest512.lower() != expected_sha512.lower():
                dest.unlink(missing_ok=True)
                raise RuntimeError(
                    f"sha512 mismatch for {dest.name}: expected {expected_sha512}, got {digest512}"
                )
            if expected_size is not None and total != expected_size:
                logger.warning(
                    "size mismatch for %s: expected %s got %s",
                    dest.name,
                    expected_size,
                    total,
                )
            if cache_dir and digest:
                try:
                    cached = cache_file_path(cache_dir, sha256=digest)
                    if not cached.is_file():
                        cached.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(dest, cached)
                except OSError:
                    logger.debug("could not write download cache", exc_info=True)
            report_progress(
                {
                    "type": "file_done",
                    "path": name,
                    "downloaded": total,
                    "total": total,
                    "sha256": digest,
                }
            )
            out: dict[str, Any] = {
                "path": str(dest),
                "url": url,
                "sha256": digest,
                "size": total,
                "cached": False,
            }
            if digest512:
                out["sha512"] = digest512
            return out
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.warning("download failed %s: %s", url, exc)
            dest.unlink(missing_ok=True)
    raise RuntimeError(f"all download URLs failed: {last_error}")


def _is_datapack_entry(entry: dict[str, Any]) -> bool:
    kind = str(entry.get("kind") or "").lower().replace(" ", "")
    if kind in {"datapack", "datapacks", "data_pack"}:
        return True
    path = str(entry.get("path") or "").replace("\\", "/").lower()
    return path.startswith("datapacks/") or "/datapacks/" in path


def _should_install_file(entry: dict[str, Any], *, server_side: bool = True) -> bool:
    if entry.get("optional") and entry.get("skip_optional"):
        return False
    # Datapacks load from the world folder on dedicated servers — never treat as
    # client-only even if the chambered build marks env=client.
    if _is_datapack_entry(entry):
        return True
    env = str(entry.get("env") or "both").lower()
    if server_side and env == "client":
        return False
    if not server_side and env == "server":
        return False
    return True


def _extract_pack(pack_path: Path, server_root: Path, excludes: list[str]) -> list[str]:
    """Extract a pack zip into the server root (best-effort exclude globs)."""
    extracted: list[str] = []
    if not zipfile.is_zipfile(pack_path):
        raise RuntimeError(f"pack is not a zip: {pack_path}")
    with zipfile.ZipFile(pack_path, "r") as zf:
        for info in zf.infolist():
            name = info.filename.replace("\\", "/")
            if name.endswith("/"):
                continue
            # Strip a single top-level folder if present.
            parts = name.split("/")
            rel = "/".join(parts[1:]) if len(parts) > 1 and not parts[0].endswith(".jar") else name
            if any(_match_exclude(rel, pattern) for pattern in excludes):
                continue
            dest = _safe_join(server_root, rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, dest.open("wb") as out:
                out.write(src.read())
            extracted.append(rel)
    return extracted


def _match_exclude(path: str, pattern: str) -> bool:
    # Minimal glob: ** and * support for common exclude patterns.
    import fnmatch

    return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path.split("/")[-1], pattern)


async def install_manifest(
    manifest: dict[str, Any],
    server_root: Path,
    *,
    include_optional: bool = False,
    user_agent: str = "CultForge-Agent/0.1 (cf-agent)",
    cache_dir: Path | None = None,
) -> dict[str, Any]:
    """Download and place files from a CultForge install manifest."""
    server_root = server_root.resolve()
    server_root.mkdir(parents=True, exist_ok=True)

    mode = str(manifest.get("mode") or "pending")
    files = list(manifest.get("files") or [])
    excludes = list(manifest.get("excludes") or [])
    warnings = list(manifest.get("warnings") or [])
    unresolved_raw = list(manifest.get("unresolved") or [])
    required_unresolved = [
        u
        for u in unresolved_raw
        if not (isinstance(u, dict) and u.get("optional"))
    ]
    unresolved = unresolved_raw

    # Ensure world datapacks folder exists and migrate any root-level leftovers.
    migrated = migrate_root_datapacks(server_root)
    if migrated:
        warnings.append(f"migrated {len(migrated)} datapack(s) into world folder")
    datapack_dir(server_root).mkdir(parents=True, exist_ok=True)

    if required_unresolved:
        labels = []
        for item in required_unresolved[:12]:
            if isinstance(item, dict):
                labels.append(
                    str(
                        item.get("path")
                        or item.get("slug")
                        or item.get("project_id")
                        or item.get("name")
                        or item
                    )
                )
            else:
                labels.append(str(item))
        return {
            "ok": False,
            "mode": mode,
            "installed": [],
            "skipped": [],
            "errors": [
                "manifest has unresolved pinned mods — fix version pins before install: "
                + ", ".join(labels)
            ],
            "warnings": warnings,
            "unresolved": unresolved,
        }

    if mode == "pending" or not files:
        return {
            "ok": False,
            "mode": mode,
            "installed": [],
            "skipped": [],
            "errors": ["manifest not installable (pending or empty files)"],
            "warnings": warnings,
            "unresolved": unresolved,
        }

    installed: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    errors: list[str] = []

    work = [
        e
        for e in files
        if isinstance(e, dict)
        and (include_optional or not e.get("optional"))
        and _should_install_file(e, server_side=True)
    ]
    report_progress(
        {
            "type": "install_start",
            "total_files": len(work),
            "build_id": manifest.get("build_id"),
        }
    )

    headers = {"User-Agent": user_agent}
    async with httpx.AsyncClient(
        timeout=None, follow_redirects=True, headers=headers
    ) as client:
        for index, entry in enumerate(files):
            if not isinstance(entry, dict):
                continue
            if not include_optional and entry.get("optional"):
                skipped.append({"path": entry.get("path"), "reason": "optional"})
                report_progress(
                    {
                        "type": "file_skip",
                        "path": entry.get("path"),
                        "reason": "optional",
                        "index": index,
                    }
                )
                continue
            if not _should_install_file(entry, server_side=True):
                skipped.append({"path": entry.get("path"), "reason": f"env={entry.get('env')}"})
                report_progress(
                    {
                        "type": "file_skip",
                        "path": entry.get("path"),
                        "reason": f"env={entry.get('env')}",
                        "index": index,
                    }
                )
                continue

            rel = resolve_entry_path(entry, server_root)
            urls = [str(u) for u in (entry.get("urls") or []) if u]
            if not rel or not urls:
                errors.append(f"invalid file entry: {entry.get('path')}")
                continue

            dest = _safe_join(server_root, rel)
            try:
                if dest.is_file() and (
                    entry.get("sha256") or entry.get("sha512")
                ):
                    report_progress(
                        {
                            "type": "file_hash_start",
                            "path": rel,
                            "index": index,
                            "algo": "sha256" if entry.get("sha256") else "sha512",
                        }
                    )
                    if _file_matches_hashes(
                        dest,
                        expected_sha256=entry.get("sha256"),
                        expected_sha512=entry.get("sha512"),
                    ):
                        skipped.append({"path": rel, "reason": "already_present"})
                        report_progress(
                            {
                                "type": "file_hash_ok",
                                "path": rel,
                                "index": index,
                                "reason": "already_present",
                            }
                        )
                        report_progress(
                            {
                                "type": "file_skip",
                                "path": rel,
                                "reason": "already_present",
                                "index": index,
                            }
                        )
                        continue
                report_progress(
                    {
                        "type": "file_begin",
                        "path": rel,
                        "index": index,
                        "total_files": len(work),
                        "size": entry.get("size"),
                    }
                )
                result = await _download(
                    client,
                    urls,
                    dest,
                    expected_sha256=entry.get("sha256"),
                    expected_sha512=entry.get("sha512"),
                    expected_size=entry.get("size"),
                    label=rel,
                    cache_dir=cache_dir,
                )
                if entry.get("sha256") or entry.get("sha512"):
                    report_progress(
                        {
                            "type": "file_hash_ok",
                            "path": rel,
                            "index": index,
                            "reason": "downloaded",
                        }
                    )
                installed.append({"path": rel, **result})
            except Exception as exc:  # noqa: BLE001
                msg = f"{rel}: {exc}"
                errors.append(msg)
                report_progress({"type": "file_error", "path": rel, "error": str(exc)})
                logger.exception("install failed for %s", rel)

    pack_extracted: list[str] = []
    if mode == "pack" and installed:
        for item in installed:
            if item.get("path", "").startswith("_pack/"):
                try:
                    pack_extracted = _extract_pack(
                        Path(item["path"]) if Path(item["path"]).is_absolute()
                        else server_root / item["path"],
                        server_root,
                        excludes,
                    )
                except Exception as exc:  # noqa: BLE001
                    errors.append(f"pack extract failed: {exc}")

    config_written: list[str] = []
    config = manifest.get("config")
    if isinstance(config, dict):
        for rel, body in config.items():
            try:
                path = _safe_join(server_root, str(rel).replace("\\", "/").lstrip("/"))
                path.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(body, (dict, list)):
                    import json

                    path.write_text(json.dumps(body, indent=2) + "\n", encoding="utf-8")
                else:
                    path.write_text(str(body), encoding="utf-8")
                config_written.append(str(rel))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"config {rel}: {exc}")

    ok = not errors and (bool(installed) or bool(skipped) or bool(pack_extracted) or bool(config_written))
    report_progress(
        {
            "type": "install_done",
            "ok": ok,
            "installed": len(installed),
            "skipped": len(skipped),
            "errors": len(errors),
        }
    )
    return {
        "ok": ok and not unresolved,
        "mode": mode,
        "build_id": manifest.get("build_id"),
        "minecraft_version": manifest.get("minecraft_version"),
        "loader": manifest.get("loader"),
        "installed": installed,
        "skipped": skipped,
        "pack_extracted": pack_extracted,
        "config_written": config_written,
        "errors": errors,
        "warnings": warnings,
        "unresolved": unresolved,
    }
