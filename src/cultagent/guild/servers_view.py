"""Normalize GuildMinecraftServer payloads for local clone UX."""

from __future__ import annotations

from typing import Any, Callable


def guild_server_id(row: dict[str, Any]) -> str:
    for key in ("id", "server_id", "guild_server_id"):
        val = row.get(key)
        if val:
            return str(val)
    return ""


def guild_server_name(row: dict[str, Any]) -> str:
    for key in ("name", "display_name", "title", "label"):
        val = row.get(key)
        if val:
            return str(val)
    sid = guild_server_id(row)
    return sid or "unnamed"


def guild_server_build_id(row: dict[str, Any]) -> str | None:
    for key in ("build_id", "guild_build_id", "published_build_id"):
        val = row.get(key)
        if val:
            return str(val)
    return None


def guild_server_effective_join(row: dict[str, Any]) -> str | None:
    """Prefer effective_* (tunnel-aware), then configured, then legacy fields."""
    eff_host = row.get("effective_address") or row.get("effective_host")
    eff_port = row.get("effective_port")
    if eff_host:
        if eff_port is not None:
            return f"{eff_host}:{eff_port}"
        return str(eff_host)
    for key in (
        "join_address",
        "public_join",
        "tunnel_address",
        "address",
        "server_address",
        "configured_address",
    ):
        val = row.get(key)
        if val:
            port = row.get("tunnel_port") or row.get("configured_port") or row.get("port")
            if port is not None and ":" not in str(val):
                return f"{val}:{port}"
            return str(val)
    return None


def _row_loader_version(
    row: dict[str, Any],
    *,
    build: dict[str, Any] | None = None,
) -> tuple[str | None, str | None]:
    """Loader/MC — prefer linked build metadata over sparse guild server fields."""
    loader = None
    version = None
    if build:
        loader = build.get("loader") or build.get("software") or build.get("platform")
        version = (
            build.get("minecraft_version")
            or build.get("mc_version")
            or build.get("version")
        )
    if not loader:
        loader = (
            row.get("loader")
            or row.get("software")
            or row.get("platform")
            or row.get("server_type")
        )
    if not version:
        version = (
            row.get("minecraft_version")
            or row.get("mc_version")
            or row.get("version")
        )
    return (
        str(loader).lower() if loader else None,
        str(version) if version else None,
    )


def guild_server_label(
    row: dict[str, Any],
    *,
    builds_by_id: dict[str, dict[str, Any]] | None = None,
) -> str:
    """One-line picker label (git-remote style)."""
    sid = guild_server_id(row) or "?"
    name = guild_server_name(row)
    bid = guild_server_build_id(row)
    build = None
    if bid and builds_by_id:
        build = builds_by_id.get(bid)
    loader, ver = _row_loader_version(row, build=build)
    loader_s = loader or "—"
    ver_s = ver or "—"
    join = guild_server_effective_join(row) or "no join yet"
    source = row.get("address_source") or ""
    src = f" [{source}]" if source else ""
    build_bit = ""
    if bid:
        bname = (build or {}).get("name") or (build or {}).get("display_name") or bid
        build_bit = f"  · {bname}"
    return f"{sid}  {name}  {loader_s} {ver_s}{build_bit}  → {join}{src}"


def labeler_with_builds(
    builds_by_id: dict[str, dict[str, Any]],
) -> Callable[[dict[str, Any]], str]:
    def _label(row: dict[str, Any]) -> str:
        return guild_server_label(row, builds_by_id=builds_by_id)

    return _label


def extract_clone_spec(
    row: dict[str, Any],
    *,
    build: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Fields used to create a local CultAgent server from a guild catalog row.

    When ``build_id`` is present, loader / minecraft_version come from the build
    (or its install manifest) — not from sparse outer guild-server fields.
    """
    sid = guild_server_id(row)
    bid = guild_server_build_id(row)
    meta_build = build
    if meta_build is None and isinstance(manifest, dict):
        # Manifest carries loader/mc; treat as build-shaped for preference.
        meta_build = {
            "loader": manifest.get("loader"),
            "minecraft_version": manifest.get("minecraft_version"),
            "name": manifest.get("name"),
            "id": manifest.get("build_id") or bid,
        }
    loader, version = _row_loader_version(row, build=meta_build)
    # Bare catalog row with no build → vanilla default; chambered build keeps None
    # until build metadata resolves (caller should always pass build when bid set).
    if not loader and not bid:
        loader = "vanilla"
    if manifest and not loader:
        loader = str(manifest.get("loader") or "").lower() or None
    if manifest and not version:
        version = manifest.get("minecraft_version")
        version = str(version) if version else None

    port = (
        row.get("configured_port")
        or row.get("port")
        or row.get("effective_port")
        or 25565
    )
    try:
        port_i = int(port)
    except (TypeError, ValueError):
        port_i = 25565

    build_name = None
    if build:
        build_name = build.get("name") or build.get("display_name")
    if not build_name and manifest:
        build_name = manifest.get("name")

    return {
        "guild_server_id": sid,
        "name": guild_server_name(row),
        "minecraft_version": str(version) if version else None,
        "loader": str(loader).lower() if loader else None,
        "port": port_i,
        "configured_address": row.get("configured_address") or row.get("server_address"),
        "configured_port": row.get("configured_port") or row.get("port"),
        "effective_address": row.get("effective_address"),
        "effective_port": row.get("effective_port"),
        "address_source": row.get("address_source"),
        "tunnel_address": row.get("tunnel_address"),
        "tunnel_port": row.get("tunnel_port"),
        "build_id": bid,
        "build_name": str(build_name) if build_name else None,
        "join": guild_server_effective_join(row),
        "raw": row,
    }


def summarize_chambered_build(
    *,
    build_id: str,
    build: dict[str, Any] | None = None,
    manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compact build card for clone result / CLI (magazine chambered, not fired)."""
    build = build or {}
    manifest = manifest or {}
    files = [f for f in (manifest.get("files") or []) if isinstance(f, dict)]
    unresolved = list(manifest.get("unresolved") or [])
    mode = str(manifest.get("mode") or build.get("mode") or "—")
    loader = (
        manifest.get("loader")
        or build.get("loader")
        or None
    )
    mc = (
        manifest.get("minecraft_version")
        or build.get("minecraft_version")
        or build.get("mc_version")
        or None
    )
    name = (
        build.get("name")
        or build.get("display_name")
        or manifest.get("name")
        or None
    )
    installable = mode in {"pack", "resolved"} and bool(files) and not unresolved
    by_kind: dict[str, int] = {}
    for entry in files:
        kind = str(entry.get("kind") or "file").lower()
        by_kind[kind] = by_kind.get(kind, 0) + 1
    return {
        "build_id": build_id,
        "name": name,
        "loader": str(loader).lower() if loader else None,
        "minecraft_version": str(mc) if mc else None,
        "mode": mode,
        "files": len(files),
        "unresolved": len(unresolved),
        "by_kind": by_kind,
        "installable": installable,
        "chambered": True,
    }


def is_list_request(value: str | None) -> bool:
    """True when user asked to list/pick (`?` like git)."""
    if value is None:
        return True
    return value.strip() in {"?", "*", "list", "ls"}
