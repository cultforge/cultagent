"""Parse Forge FML crash reports / latest.log and install the missing mods."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import httpx

from cultagent.content.modrinth import (
    ModrinthClient,
    _disable_client_jar,
    download_and_install,
    is_platform_dependency,
    loader_candidates,
    resolve_installed_mod_dependencies,
)

logger = logging.getLogger("cultagent.content.crash_resolve")

STAMP_NAME = ".cultagent-crash-resolve.json"

# Forge modId → Modrinth slug when they differ.
_MODID_ALIASES = {
    "cloth_config": "cloth-config",
    "yungsapi": "yungs-api",
    "puzzleslib": "puzzles-lib",
    "resourcefullib": "resourceful-lib",
    "resourcefulconfig": "resourceful-config",
    "connectormod": "connector",
    "epicfight": "epic-fight",
    "iceandfire": "ice-and-fire-dragons",
    "cristellib": "cristel-lib",
    "sophisticatedcore": "sophisticated-core",
    "attributeslib": "apothic-attributes",
    "invincible": "epic-fight-invincible-lib",
    "forgeendertech": "forgeendertech",
}

_LOG_LINE = re.compile(
    r"Mod ID:\s*'(?P<required>[^']+)'\s*,\s*"
    r"Requested by:\s*'(?P<requester>[^']+)'\s*,\s*"
    r"Expected range:\s*'(?P<range>[^']+)'\s*,\s*"
    r"Actual version:\s*'(?P<actual>[^']+)'",
    re.I,
)

_CRASH_BLOCK = re.compile(
    r"-- MOD (?P<requester>\S+) --\s+"
    r"Details:\s+"
    r"(?:Mod File:\s*(?P<file>.+?)\s+)?"
    r"Failure message:\s*Mod \S+ requires (?P<required>\S+)"
    r"(?: (?P<range>.+?))?\s+"
    r"Currently,\s+\S+\s+is\s+(?P<actual>.+)",
    re.I,
)

_MOD_SECTION = re.compile(
    r"-- MOD (?P<requester>\S+) --\s+"
    r"Details:\s+"
    r"(?:Mod File:\s*(?P<file>.+?)\s+)?"
    r"Failure message:\s*(?P<message>.+?)"
    r"(?=\n-- MOD |\n-- System Details --|\Z)",
    re.I | re.S,
)

_MISSING_ACTUALS = {"not installed", "[missing]", "missing", "[MISSING]"}


@dataclass(frozen=True)
class DepFailure:
    required: str
    requester: str
    version_range: str
    actual: str
    jar: str | None = None
    kind: str = "dep"

    @property
    def missing(self) -> bool:
        return str(self.actual).strip().lower() in _MISSING_ACTUALS

    @property
    def platform(self) -> bool:
        return is_platform_dependency(self.required)

    @property
    def client_dist(self) -> bool:
        return self.kind == "client_dist"


def _jar_name(raw_file: str | None) -> str | None:
    raw = (raw_file or "").strip()
    if not raw:
        return None
    name = Path(raw.replace("\\", "/")).name
    if name.lower().endswith(".jar"):
        return name
    return None


def parse_dep_failures(text: str) -> list[DepFailure]:
    """Extract missing/outdated mandatory deps from an FML crash or latest.log."""
    found: dict[tuple[str, str, str], DepFailure] = {}

    def _store(item: DepFailure) -> None:
        found[(item.kind, item.required, item.requester)] = item

    for match in _LOG_LINE.finditer(text or ""):
        _store(
            DepFailure(
                required=match.group("required").strip().lower(),
                requester=match.group("requester").strip().lower(),
                version_range=(match.group("range") or "*").strip(),
                actual=(match.group("actual") or "").strip(),
            )
        )

    for match in _CRASH_BLOCK.finditer(text or ""):
        _store(
            DepFailure(
                required=match.group("required").strip().lower(),
                requester=match.group("requester").strip().lower(),
                version_range=(match.group("range") or "*").strip(),
                actual=(match.group("actual") or "").strip(),
                jar=_jar_name(match.group("file")),
            )
        )

    for match in _MOD_SECTION.finditer(text or ""):
        message = match.group("message") or ""
        low = message.lower()
        if "requires " in low and "currently," in low:
            continue
        if "dedicated_server" not in low and "invalid dist" not in low:
            continue
        requester = match.group("requester").strip().lower()
        _store(
            DepFailure(
                required="_client",
                requester=requester,
                version_range="*",
                actual="client-only",
                jar=_jar_name(match.group("file")),
                kind="client_dist",
            )
        )

    return sorted(found.values(), key=lambda i: (i.kind, i.required, i.requester))


def collect_crash_text(server_dir: str | Path, crash_path: str | Path | None = None) -> tuple[str, list[str]]:
    """Load the newest FML crash + latest.log. Returns (text, source paths)."""
    root = Path(server_dir)
    sources: list[Path] = []
    if crash_path:
        explicit = Path(crash_path)
        if explicit.is_file():
            sources.append(explicit)
    else:
        reports = root / "crash-reports"
        if reports.is_dir():
            fml = sorted(
                reports.glob("crash-*-fml.txt"),
                key=lambda p: p.stat().st_mtime,
                reverse=True,
            )
            sources.extend(fml[:5])
        for name in ("latest.log", "debug.log"):
            log = root / "logs" / name
            if log.is_file():
                sources.append(log)

    chunks: list[str] = []
    used: list[str] = []
    for path in sources:
        try:
            chunks.append(path.read_text(encoding="utf-8", errors="replace"))
            used.append(str(path))
        except OSError:
            continue
    return "\n".join(chunks), used


def fingerprint_issues(issues: list[DepFailure]) -> str:
    payload = "|".join(
        f"{i.required}:{i.requester}:{i.version_range}:{i.actual}" for i in issues
    )
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def _modids_in_jar(path: Path) -> list[str]:
    try:
        with zipfile.ZipFile(path) as zf:
            names = [
                n
                for n in zf.namelist()
                if n.lower().endswith("mods.toml") or n.lower().endswith("neoforge.mods.toml")
            ]
            if not names:
                return []
            text = zf.read(names[0]).decode("utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        return []
    return [m.lower() for m in re.findall(r'(?im)^\s*modId\s*=\s*"([^"]+)"', text)]


def index_modid_jars(mods_dir: Path) -> dict[str, str]:
    mapping: dict[str, str] = {}
    if not mods_dir.is_dir():
        return mapping
    for jar in mods_dir.glob("*.jar"):
        for mid in _modids_in_jar(jar):
            mapping[mid] = jar.name
    return mapping


def _slug_candidates(modid: str) -> list[str]:
    raw = (modid or "").strip().lower()
    out: list[str] = []
    alias = _MODID_ALIASES.get(raw)
    if alias:
        out.append(alias)
    out.append(raw)
    dashed = raw.replace("_", "-")
    if dashed not in out:
        out.append(dashed)
    return out


async def lookup_modrinth_project(
    client: ModrinthClient,
    modid: str,
    *,
    loader: str,
    game_version: str,
) -> dict[str, Any] | None:
    """Resolve a Forge/Fabric modId to a Modrinth project."""
    for slug in _slug_candidates(modid):
        try:
            project = await client.project(slug)
            if isinstance(project, dict) and project.get("id"):
                return project
        except httpx.HTTPStatusError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                continue
            logger.debug("Modrinth project %s failed: %s", slug, exc)
        except Exception:  # noqa: BLE001
            logger.debug("Modrinth project %s failed", slug, exc_info=True)

    try:
        data = await client.search(
            modid.replace("_", " "),
            limit=8,
            project_type="mod",
            loader=loader_candidates(loader)[0],
            game_version=game_version,
        )
    except Exception:  # noqa: BLE001
        logger.debug("Modrinth search for %s failed", modid, exc_info=True)
        return None
    compact = re.sub(r"[^a-z0-9]", "", modid.lower())
    hits = [h for h in (data.get("hits") or []) if isinstance(h, dict)]
    ranked: list[tuple[int, dict[str, Any]]] = []
    for hit in hits:
        slug = str(hit.get("slug") or "").lower()
        slug_compact = re.sub(r"[^a-z0-9]", "", slug)
        score = 0
        if slug_compact == compact:
            score += 100
        if slug in {modid.lower(), modid.lower().replace("_", "-")}:
            score += 50
        if slug.endswith("-ce") and not modid.lower().endswith("ce"):
            score -= 40
        ranked.append((score, hit))
    ranked.sort(key=lambda x: x[0], reverse=True)
    for score, hit in ranked:
        if score < 0:
            continue
        pid = str(hit.get("project_id") or hit.get("id") or hit.get("slug") or "")
        if not pid:
            continue
        try:
            return await client.project(pid)
        except Exception:  # noqa: BLE001
            return hit
    return None


async def resolve_from_crash_reports(
    client: ModrinthClient,
    server_dir: str | Path,
    *,
    loader: str,
    game_version: str,
    disable_unsatisfiable: bool = True,
    crash_path: str | Path | None = None,
) -> dict[str, Any]:
    """Install/upgrade mods named in the latest FML crash or latest.log."""
    root = Path(server_dir).resolve()
    text, sources = collect_crash_text(root, crash_path)
    issues = parse_dep_failures(text)
    jars = index_modid_jars(root / "mods")
    installed: list[dict[str, Any]] = []
    disabled: list[str] = []
    unresolved: list[dict[str, Any]] = []
    visited: set[str] = set()

    def _jar_for(modid: str, hint: str | None = None) -> str | None:
        if hint and (root / "mods" / hint).is_file():
            return hint
        return jars.get(modid)

    unique_required: dict[str, DepFailure] = {}
    for issue in issues:
        if issue.jar and issue.requester not in jars:
            jars[issue.requester] = issue.jar
        if issue.client_dist:
            if disable_unsatisfiable:
                name = _jar_for(issue.requester, issue.jar)
                if name:
                    renamed = _disable_client_jar(root, name)
                    if renamed and renamed not in disabled:
                        disabled.append(renamed)
            continue
        prev = unique_required.get(issue.required)
        if prev is None or (issue.missing and not prev.missing):
            unique_required[issue.required] = issue

    for required, issue in unique_required.items():
        requesters = [i for i in issues if i.required == required and not i.client_dist]
        if issue.platform:
            if disable_unsatisfiable:
                for req in requesters:
                    name = _jar_for(req.requester, req.jar)
                    if name:
                        renamed = _disable_client_jar(root, name)
                        if renamed and renamed not in disabled:
                            disabled.append(renamed)
            # Handled by disabling the demanding jar — not a hard failure.
            installed.append(
                {
                    "ok": True,
                    "skipped": True,
                    "reason": "platform",
                    "required": required,
                    "range": issue.version_range,
                    "actual": issue.actual,
                    "disabled_requesters": [r.requester for r in requesters],
                }
            )
            continue

        # Already present from a prior install / guild pack.
        if required in jars:
            installed.append(
                {
                    "ok": True,
                    "skipped": True,
                    "reason": "already_present",
                    "required": required,
                    "filename": jars[required],
                }
            )
            continue

        project = await lookup_modrinth_project(
            client, required, loader=loader, game_version=game_version
        )
        if not project:
            unresolved.append(
                {
                    "required": required,
                    "reason": "not_on_modrinth",
                    "requesters": [r.requester for r in requesters],
                }
            )
            continue

        pid = str(project.get("id") or project.get("project_id") or required)
        slug = str(project.get("slug") or pid)
        # Modrinth often marks server libraries as client-only incorrectly
        # (e.g. Crossroads' "essentials"). Still install; only disable jars that
        # themselves crash with invalid dist DEDICATED_SERVER.
        allow_client = str(project.get("server_side") or "").lower() == "unsupported"

        try:
            result = await download_and_install(
                client,
                root,
                project_id=pid,
                loader=loader,
                game_version=game_version,
                install_deps=True,
                allow_client=allow_client,
                _visited=visited,
            )
            result["required"] = required
            installed.append(result)
        except Exception as exc:  # noqa: BLE001
            logger.warning("crash-resolve install %s failed: %s", required, exc)
            unresolved.append(
                {
                    "required": required,
                    "reason": str(exc),
                    "slug": slug,
                    "requesters": [r.requester for r in requesters],
                }
            )

    if disable_unsatisfiable:
        seen_req: set[str] = set()
        for issue in issues:
            if issue.requester in seen_req:
                continue
            seen_req.add(issue.requester)
            try:
                req_project = await lookup_modrinth_project(
                    client, issue.requester, loader=loader, game_version=game_version
                )
            except Exception:  # noqa: BLE001
                req_project = None
            if str((req_project or {}).get("server_side") or "").lower() != "unsupported":
                continue
            name = _jar_for(issue.requester, issue.jar)
            if name:
                renamed = _disable_client_jar(root, name)
                if renamed and renamed not in disabled:
                    disabled.append(renamed)

    added = [r for r in installed if r.get("ok") and not r.get("skipped")]
    failed = [r for r in installed if r.get("ok") is False]
    stamp = {
        "fingerprint": fingerprint_issues(issues),
        "sources": sources,
        "added_count": len(added),
        "disabled_count": len(disabled),
    }
    try:
        (root / STAMP_NAME).write_text(json.dumps(stamp, indent=2) + "\n", encoding="utf-8")
    except OSError:
        pass

    return {
        "ok": not failed and not unresolved,
        "source": "crash",
        "sources": sources,
        "issues": [asdict(i) for i in issues],
        "issue_count": len(issues),
        "identified": [asdict(i) for i in issues],
        "installed": added,
        "skipped": [r for r in installed if r.get("skipped")],
        "disabled_client_only": disabled,
        "unresolved": unresolved,
        "failed": failed
        + [{"ok": False, "project_id": u.get("required"), "error": u.get("reason")} for u in unresolved],
        "errors": [],
        "added_count": len(added),
        "disabled_count": len(disabled),
        "jars": len(list((root / "mods").glob("*.jar"))) if (root / "mods").is_dir() else 0,
        "unknown": [],
    }


def already_resolved(server_dir: str | Path, issues: list[DepFailure]) -> bool:
    path = Path(server_dir) / STAMP_NAME
    if not path.is_file() or not issues:
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return False
    return str(data.get("fingerprint") or "") == fingerprint_issues(issues)


async def resolve_mod_issues(
    client: ModrinthClient,
    server_dir: str | Path,
    *,
    loader: str,
    game_version: str,
    source: str = "auto",
    crash_path: str | Path | None = None,
    also_scan_jars: bool = False,
    disable_client_only: bool = True,
) -> dict[str, Any]:
    """Crash/log-driven resolve, with optional full jar hash walk."""
    mode = (source or "auto").strip().lower()
    text, sources = collect_crash_text(server_dir, crash_path)
    issues = parse_dep_failures(text) if mode in {"auto", "crash", "both"} else []
    crash_result: dict[str, Any] | None = None
    if issues and mode in {"auto", "crash", "both"}:
        crash_result = await resolve_from_crash_reports(
            client,
            server_dir,
            loader=loader,
            game_version=game_version,
            disable_unsatisfiable=disable_client_only,
            crash_path=crash_path,
        )
        crash_result["sources"] = sources
        if mode == "crash" or (mode == "auto" and not also_scan_jars):
            return crash_result
    elif mode == "crash":
        return {
            "ok": True,
            "source": "crash",
            "sources": sources,
            "issues": [],
            "issue_count": 0,
            "identified": [],
            "installed": [],
            "disabled_client_only": [],
            "unresolved": [],
            "failed": [],
            "errors": [],
            "added_count": 0,
            "disabled_count": 0,
            "jars": 0,
            "unknown": [],
            "note": "no FML dependency failures in crash-reports/ or logs/",
        }

    jar_result = await resolve_installed_mod_dependencies(
        client,
        server_dir,
        loader=loader,
        game_version=game_version,
        disable_client_only=disable_client_only,
    )
    jar_result["source"] = "jars" if not crash_result else "both"
    if crash_result:
        jar_result["crash"] = {
            "added_count": crash_result.get("added_count"),
            "disabled_count": crash_result.get("disabled_count"),
            "issue_count": crash_result.get("issue_count"),
            "unresolved": crash_result.get("unresolved"),
        }
        jar_result["issues"] = crash_result.get("issues")
        jar_result["issue_count"] = crash_result.get("issue_count")
        jar_result["added_count"] = int(crash_result.get("added_count") or 0) + int(
            jar_result.get("added_count") or 0
        )
        jar_result["disabled_count"] = int(crash_result.get("disabled_count") or 0) + int(
            jar_result.get("disabled_count") or 0
        )
        jar_result["ok"] = bool(crash_result.get("ok")) and bool(jar_result.get("ok"))
    return jar_result
