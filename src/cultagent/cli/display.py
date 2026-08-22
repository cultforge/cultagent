"""Rich console helpers for cf-agent CLI output."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from rich.console import Console, Group
from rich.panel import Panel
from rich.pretty import Pretty
from rich.table import Table
from rich.text import Text

console = Console()

_CAPTURE_JSON = False


def set_capture_json(enabled: bool) -> None:
    """Enable raw JSON stdout for this process (``cf-agent --capture-json …``)."""
    global _CAPTURE_JSON
    _CAPTURE_JSON = bool(enabled)


def capture_json_enabled() -> bool:
    return _CAPTURE_JSON


def print_json_payload(data: Any) -> None:
    """Emit machine-readable JSON to stdout (for --capture-json)."""
    sys.stdout.write(
        json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n"
    )
    sys.stdout.flush()


def dump_json_file(data: Any, path: Path) -> Path:
    """Write a JSON payload to disk (used by --dump-json)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, default=str) + "\n",
        encoding="utf-8",
    )
    console.print(Text("Wrote ", style="dim") + Text(str(path), style="cyan"))
    return path


def print_data(data: Any, *, raw: bool = False) -> None:
    """Pretty-print arbitrary payloads (never raw JSON dumps by default)."""
    if capture_json_enabled() or raw:
        print_json_payload(data)
        return
    if isinstance(data, dict) and {"product", "identity"}.issubset(data.keys()):
        print_status(data)
        return
    if isinstance(data, dict) and _looks_like_build_manifest(data):
        print_build_manifest(data)
        return
    if isinstance(data, dict) and "ok" in data and ("command" in data or "data" in data):
        print_result(data)
        return
    if isinstance(data, dict) and {"api_base", "services", "required_ok"}.issubset(data.keys()):
        print_manifest(data)
        return
    if isinstance(data, dict):
        console.print(_dict_panel(data))
        return
    if isinstance(data, list):
        print_list(data)
        return
    console.print(data)


def _looks_like_build_manifest(data: dict[str, Any]) -> bool:
    if "files" in data and ("build_id" in data or "mode" in data):
        return True
    # dispatch wrapper: {ok, command, data: manifest}
    inner = data.get("data")
    if isinstance(inner, dict) and "files" in inner and ("build_id" in inner or "mode" in inner):
        return True
    return False


def _looks_like_build_install(data: dict[str, Any]) -> bool:
    """builds.install / content deploy result (stats view, not file dump)."""
    install = data.get("install")
    if isinstance(install, dict) and (
        "installed" in install or "compatibility" in install or "mode" in install
    ):
        return True
    if "installed" in data and ("build_id" in data or "mode" in data or "compatibility" in data):
        return True
    return False


def print_result(result: dict[str, Any]) -> None:
    """Render a command dispatch result."""
    if capture_json_enabled():
        print_json_payload(result)
        return
    data = result.get("data")
    if isinstance(data, dict) and _looks_like_build_manifest(data):
        print_build_manifest(data)
        if not result.get("ok", True):
            err = result.get("error") or result.get("detail")
            if err:
                console.print(Text(str(err), style="red"))
        return
    if isinstance(data, dict) and data.get("cloned") and data.get("local_server_id"):
        print_server_clone(data)
        if not result.get("ok", True):
            err = result.get("error") or result.get("detail")
            if err:
                console.print(Text(str(err), style="red"))
        return
    if isinstance(data, dict) and _looks_like_build_install(data):
        print_build_install(data, command=str(result.get("command") or "builds.provision"))
        if not result.get("ok", True):
            err = result.get("error") or result.get("detail")
            if err:
                console.print(Text(str(err), style="red"))
        return
    if isinstance(data, dict) and "hits" in data and "query" in data:
        print_modrinth_search(data)
        return
    if isinstance(data, dict) and "project" in data and isinstance(data.get("project"), dict):
        print_modrinth_project(data)
        return
    if isinstance(data, dict) and "versions" in data and "game_version" in data:
        print_modrinth_versions(data)
        return
    if isinstance(data, dict) and "mods" in data and isinstance(data.get("mods"), list):
        print_mods_list(data)
        return
    if isinstance(data, dict) and (
        ("identified" in data and "added_count" in data)
        or data.get("source") in {"crash", "jars", "both"}
    ):
        print_mods_resolve(data)
        return
    if isinstance(data, dict) and (
        data.get("provider") in {"direct", "playit"} or "active" in data and "providers" in data
    ):
        print_network_status(data)
        return

    ok = bool(result.get("ok"))
    title = Text()
    title.append("OK" if ok else "FAILED", style="bold green" if ok else "bold red")
    if result.get("command"):
        title.append(f"  ·  {result['command']}", style="dim")

    err = result.get("error") or result.get("detail")
    parts: list[Any] = []

    if err:
        parts.append(Text(str(err), style="red"))

    if isinstance(data, dict):
        if "servers" in data and isinstance(data["servers"], list):
            parts.append(_servers_table(data["servers"]))
        elif "builds" in data and isinstance(data["builds"], list):
            parts.append(_builds_table(data["builds"]))
        elif "lines" in data and isinstance(data["lines"], list):
            parts.append(_console_block(data["lines"]))
        elif "compatibility" in data and "installed" in data:
            parts.append(_install_result_block(data))
        else:
            parts.append(_dict_table(data))
    elif isinstance(data, list):
        parts.append(_list_preview(data))
    elif data is not None:
        parts.append(Text(str(data)))

    # leftover top-level keys
    skip = {"ok", "command", "data", "error", "detail"}
    extra = {k: v for k, v in result.items() if k not in skip}
    if extra and not data:
        parts.append(_dict_table(extra))

    body = Group(*parts) if parts else Text("done", style="dim")
    console.print(Panel(body, title=title, border_style="green" if ok else "red", padding=(1, 2)))


def print_build_install(
    data: dict[str, Any],
    *,
    command: str = "builds.provision",
) -> None:
    """Stats-only view of a build install (no per-file dump)."""
    install = data.get("install") if isinstance(data.get("install"), dict) else data
    if not isinstance(install, dict):
        install = {}

    installed = [x for x in (install.get("installed") or []) if isinstance(x, dict)]
    skipped = list(install.get("skipped") or [])
    errors = list(install.get("errors") or [])
    warnings = list(install.get("warnings") or [])
    unresolved = list(install.get("unresolved") or [])
    compat = install.get("compatibility") if isinstance(install.get("compatibility"), dict) else {}
    counts = compat.get("counts") if isinstance(compat.get("counts"), dict) else {}
    by_kind = counts.get("by_kind") if isinstance(counts.get("by_kind"), dict) else {}
    if not by_kind:
        for entry in installed:
            kind = str(entry.get("kind") or "file").lower()
            # path-based fallback
            path = str(entry.get("path") or "")
            if "/mods/" in path.replace("\\", "/") or path.replace("\\", "/").startswith("mods/"):
                kind = "mod"
            elif "resourcepack" in path.replace("\\", "/"):
                kind = "resourcepack"
            elif "shader" in path.replace("\\", "/"):
                kind = "shader"
            by_kind[kind] = by_kind.get(kind, 0) + 1

    total_bytes = 0
    cached_n = 0
    for entry in installed:
        try:
            total_bytes += int(entry.get("size") or 0)
        except (TypeError, ValueError):
            pass
        if entry.get("cached"):
            cached_n += 1

    header = Table.grid(padding=(0, 2))
    header.add_column(style="dim", justify="right")
    header.add_column()
    if data.get("server_id"):
        header.add_row("server", Text(str(data["server_id"]), style="cyan"))
    bid = data.get("build_id") or install.get("build_id")
    if bid:
        header.add_row("build", Text(str(bid), style="cyan"))
    loader = data.get("loader") or install.get("loader") or "—"
    mc = data.get("minecraft_version") or install.get("minecraft_version") or "—"
    header.add_row("loader / mc", f"{loader} / {mc}")
    header.add_row("mode", str(install.get("mode") or "—"))
    ok_install = install.get("ok", True)
    header.add_row(
        "install",
        Text("ok", style="bold green") if ok_install else Text("failed", style="bold red"),
    )

    platform = data.get("platform") if isinstance(data.get("platform"), dict) else None
    if platform is not None or data.get("launch_ready") is not None:
        header.add_row(
            "launch ready",
            Text("yes", style="bold green")
            if data.get("launch_ready")
            else Text("no", style="yellow"),
        )
        if platform:
            if platform.get("installed"):
                header.add_row(
                    "platform",
                    Text(
                        f"installed  {platform.get('loader') or data.get('loader') or '—'} "
                        f"{platform.get('version') or data.get('minecraft_version') or ''}",
                        style="green",
                    ),
                )
            elif platform.get("skipped"):
                reason = platform.get("reason") or "skipped"
                header.add_row(
                    "platform",
                    Text(
                        f"{reason}  {platform.get('loader') or data.get('loader') or '—'} "
                        f"{platform.get('version') or data.get('minecraft_version') or ''}",
                        style="dim",
                    ),
                )
            if platform.get("execution_command") or data.get("execution_command"):
                header.add_row(
                    "exec",
                    str(
                        platform.get("execution_command")
                        or data.get("execution_command")
                        or ""
                    )[:80],
                )

    stats = Table.grid(padding=(0, 2))
    stats.add_column(style="dim", justify="right")
    stats.add_column()
    stats.add_row("installed", str(len(installed)))
    stats.add_row("skipped", str(len(skipped)))
    stats.add_row("cached", str(cached_n))
    stats.add_row("downloaded", str(max(0, len(installed) - cached_n)))
    stats.add_row("bytes", _fmt_size(total_bytes) if total_bytes else "—")
    stats.add_row(
        "errors",
        Text(str(len(errors)), style="red" if errors else "dim"),
    )
    stats.add_row("warnings", str(len(warnings)))
    stats.add_row(
        "unresolved",
        Text(str(len(unresolved)), style="red" if unresolved else "dim"),
    )
    if by_kind:
        stats.add_row(
            "by kind",
            ", ".join(f"{k}={v}" for k, v in sorted(by_kind.items())),
        )

    deps = install.get("dependencies") if isinstance(install.get("dependencies"), dict) else {}
    if deps:
        stats.add_row("deps added", str(deps.get("added_count") or 0))
        failed_deps = [
            d for d in (deps.get("failed") or []) if isinstance(d, dict) and not d.get("skipped")
        ]
        if failed_deps:
            stats.add_row(
                "deps failed",
                Text(str(len(failed_deps)), style="yellow"),
            )

    parts: list[Any] = [header, Text(""), Text("Summary", style="bold"), stats]

    notes = list(compat.get("notes") or [])
    if notes:
        note_tbl = Table(show_header=False, box=None, padding=(0, 1), title="Notes")
        note_tbl.add_column(style="dim")
        for note in notes[:8]:
            note_tbl.add_row(str(note))
        parts.append(Text(""))
        parts.append(note_tbl)

    if errors:
        err_tbl = Table(show_header=False, box=None, padding=(0, 1), title="Errors")
        err_tbl.add_column(style="red")
        for e in errors[:15]:
            err_tbl.add_row(str(e))
        parts.append(Text(""))
        parts.append(err_tbl)

    if deps:
        failed_deps = [
            d for d in (deps.get("failed") or []) if isinstance(d, dict) and not d.get("skipped")
        ]
        if failed_deps:
            dep_tbl = Table(show_header=False, box=None, padding=(0, 1), title="Dependency warnings")
            dep_tbl.add_column(style="yellow")
            for item in failed_deps[:10]:
                dep_tbl.add_row(str(item.get("error") or item.get("project_id") or item))
            parts.append(Text(""))
            parts.append(dep_tbl)

    if skipped:
        parts.append(Text(""))
        parts.append(
            Text(
                f"Skipped {len(skipped)} optional — pass --optional to include",
                style="dim",
            )
        )

    title = Text("OK" if ok_install else "FAILED", style="bold green" if ok_install else "bold red")
    title.append(f"  ·  {command}", style="dim")
    console.print(
        Panel(
            Group(*parts),
            title=title,
            border_style="green" if ok_install else "red",
            padding=(1, 2),
        )
    )


def print_server_clone(data: dict[str, Any]) -> None:
    """Rich clone summary — chambered magazine, no nested server JSON dump."""
    header = Table.grid(padding=(0, 2))
    header.add_column(style="dim", justify="right")
    header.add_column()
    header.add_row("cloned", Text("yes", style="bold green") if data.get("cloned") else "no")
    header.add_row("guild server", Text(str(data.get("guild_server_id") or "—"), style="cyan"))
    header.add_row("local server", Text(str(data.get("local_server_id") or "—"), style="cyan"))
    header.add_row("name", Text(str(data.get("name") or "—"), style="bold"))
    header.add_row(
        "loader / mc",
        f"{data.get('loader') or '—'} / {data.get('minecraft_version') or '—'}",
    )
    header.add_row("port", str(data.get("port") or "—"))
    header.add_row("path", str(data.get("path") or "—"))
    if data.get("join"):
        header.add_row("guild join", str(data["join"]))
    header.add_row(
        "jar downloaded",
        Text("yes", style="green") if data.get("downloaded") else Text("no", style="dim"),
    )

    parts: list[Any] = [header]
    build = data.get("build") if isinstance(data.get("build"), dict) else None
    bid = data.get("build_id") or (build or {}).get("build_id")
    if bid or build:
        chamber = Table.grid(padding=(0, 2))
        chamber.add_column(style="dim", justify="right")
        chamber.add_column()
        chamber.add_row(
            "magazine",
            Text("chambered" if data.get("chambered") else "empty", style="bold green" if data.get("chambered") else "dim"),
        )
        chamber.add_row("build", Text(str(bid or "—"), style="cyan"))
        if build and build.get("name"):
            chamber.add_row("build name", Text(str(build["name"]), style="bold"))
        chamber.add_row(
            "loader / mc",
            f"{(build or {}).get('loader') or data.get('loader') or '—'} / "
            f"{(build or {}).get('minecraft_version') or data.get('minecraft_version') or '—'}",
        )
        if build:
            chamber.add_row("mode", str(build.get("mode") or "—"))
            chamber.add_row("files", str(build.get("files") if build.get("files") is not None else "—"))
            by_kind = build.get("by_kind") if isinstance(build.get("by_kind"), dict) else {}
            if by_kind:
                chamber.add_row(
                    "by kind",
                    ", ".join(f"{k}={v}" for k, v in sorted(by_kind.items())),
                )
            installable = build.get("installable")
            if installable is not None:
                chamber.add_row(
                    "installable",
                    Text("yes", style="bold green") if installable else Text("no", style="yellow"),
                )
        parts.append(Text(""))
        parts.append(Text("Chambered build", style="bold"))
        parts.append(chamber)

    if data.get("next"):
        parts.append(Text(""))
        parts.append(Text(f"Next  {data['next']}", style="bold cyan"))

    title = Text("OK  ·  server.clone", style="bold green")
    console.print(Panel(Group(*parts), title=title, border_style="green", padding=(1, 2)))


def print_build_manifest(payload: dict[str, Any]) -> None:
    """Rich view of a CultForge guild build install manifest."""
    manifest = payload.get("data") if isinstance(payload.get("data"), dict) and "files" in (
        payload.get("data") or {}
    ) else payload
    if not isinstance(manifest, dict):
        console.print(Pretty(payload))
        return

    files = [f for f in (manifest.get("files") or []) if isinstance(f, dict)]
    unresolved = list(manifest.get("unresolved") or [])
    warnings = list(manifest.get("warnings") or [])
    excludes = list(manifest.get("excludes") or [])
    mode = str(manifest.get("mode") or "—")
    installable = mode in {"pack", "resolved"} and bool(files) and not unresolved

    header = Table.grid(padding=(0, 2))
    header.add_column(style="dim", justify="right")
    header.add_column()
    header.add_row("build", Text(str(manifest.get("build_id") or "—"), style="cyan"))
    if manifest.get("name"):
        header.add_row("name", Text(str(manifest.get("name")), style="bold"))
    header.add_row("guild", str(manifest.get("guild_id") or "—"))
    header.add_row("mode", Text(mode, style="green" if installable else "yellow"))
    header.add_row(
        "minecraft",
        f"{manifest.get('minecraft_version') or '—'} / {manifest.get('loader') or '—'}",
    )
    header.add_row(
        "installable",
        Text("yes", style="bold green") if installable else Text("no", style="bold yellow"),
    )

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

    counts = Table.grid(padding=(0, 2))
    counts.add_column(style="dim", justify="right")
    counts.add_column()
    counts.add_row("files", str(len(files)))
    counts.add_row("optional", str(optional_n))
    counts.add_row("client-only", str(client_only))
    counts.add_row("missing sha256", str(missing_hash))
    counts.add_row("unresolved", Text(str(len(unresolved)), style="red" if unresolved else "dim"))
    counts.add_row("warnings", str(len(warnings)))
    if by_kind:
        counts.add_row(
            "by kind",
            ", ".join(f"{k}={v}" for k, v in sorted(by_kind.items())),
        )

    file_tbl = Table(
        show_header=True,
        header_style="dim",
        box=None,
        padding=(0, 1),
        title=f"Files ({len(files)})",
    )
    file_tbl.add_column("Kind", style="cyan", max_width=12)
    file_tbl.add_column("Path", overflow="fold")
    file_tbl.add_column("Env", max_width=8)
    file_tbl.add_column("Opt", max_width=4)
    file_tbl.add_column("SHA", max_width=10)
    file_tbl.add_column("Size", justify="right", max_width=10)
    for entry in files[:80]:
        sha = str(entry.get("sha256") or "")
        sha_short = sha[:8] + "…" if len(sha) > 8 else (sha or "—")
        size = entry.get("size")
        size_s = _fmt_size(size) if isinstance(size, int) else "—"
        file_tbl.add_row(
            str(entry.get("kind") or "file"),
            str(entry.get("path") or ""),
            str(entry.get("env") or "both"),
            "yes" if entry.get("optional") else "",
            sha_short,
            size_s,
        )
    if len(files) > 80:
        file_tbl.add_row("…", f"+{len(files) - 80} more", "", "", "", "")

    parts: list[Any] = [header, Text(""), Text("Summary", style="bold"), counts, Text(""), file_tbl]

    if excludes:
        ex = Table(show_header=False, box=None, padding=(0, 1), title="Excludes")
        ex.add_column(style="dim")
        for pattern in excludes[:30]:
            ex.add_row(str(pattern))
        parts.extend([Text(""), ex])

    if warnings:
        warn = Table(show_header=False, box=None, padding=(0, 1), title="Warnings")
        warn.add_column(style="yellow")
        for w in warnings[:30]:
            warn.add_row(str(w))
        parts.extend([Text(""), warn])

    if unresolved:
        un = Table(show_header=False, box=None, padding=(0, 1), title="Unresolved")
        un.add_column(style="red")
        for item in unresolved[:40]:
            un.add_row(str(item))
        parts.extend([Text(""), un])

    compat = manifest.get("compatibility")
    if isinstance(compat, dict) and compat.get("issues"):
        iss = Table(show_header=False, box=None, padding=(0, 1), title="Compatibility")
        iss.add_column(style="red")
        for issue in compat["issues"]:
            iss.add_row(str(issue))
        parts.extend([Text(""), iss])

    border = "green" if installable else "yellow"
    console.print(
        Panel(
            Group(*parts),
            title="[bold]Build manifest[/bold]",
            border_style=border,
            padding=(1, 2),
        )
    )


def _fmt_size(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024**2:
        return f"{n / 1024:.1f} KB"
    if n < 1024**3:
        return f"{n / 1024**2:.1f} MB"
    return f"{n / 1024**3:.2f} GB"


def _install_result_block(data: dict[str, Any]) -> Group:
    rows = Table.grid(padding=(0, 2))
    rows.add_column(style="dim", justify="right")
    rows.add_column()
    rows.add_row("mode", str(data.get("mode") or "—"))
    rows.add_row("installed", str(len(data.get("installed") or [])))
    rows.add_row("skipped", str(len(data.get("skipped") or [])))
    rows.add_row("errors", Text(str(len(data.get("errors") or [])), style="red" if data.get("errors") else "dim"))
    if data.get("pack_extracted"):
        rows.add_row("pack files", str(len(data.get("pack_extracted") or [])))
    parts: list[Any] = [rows]
    errs = data.get("errors") or []
    if errs:
        t = Table(show_header=False, box=None, padding=(0, 1), title="Errors")
        t.add_column(style="red")
        for e in errs[:20]:
            t.add_row(str(e))
        parts.append(t)
    return Group(*parts)


def print_servers(servers: list[Any]) -> None:
    console.print(_servers_table(servers))


def print_list(items: list[Any], *, title: str | None = None) -> None:
    if not items:
        console.print("[dim](empty)[/dim]")
        return
    if all(isinstance(i, dict) for i in items):
        keys: list[str] = []
        for item in items:
            for k in item:
                if k not in keys:
                    keys.append(str(k))
        keys = keys[:6]
        table = Table(title=title, show_header=True, header_style="dim", box=None, padding=(0, 1))
        for k in keys:
            table.add_column(k)
        for item in items:
            table.add_row(*[str(item.get(k, ""))[:48] for k in keys])
        console.print(table)
        return
    console.print(Pretty(items))


def print_status(status: dict[str, Any]) -> None:
    """Render agent public_status as panels."""
    identity = status.get("identity") if isinstance(status.get("identity"), dict) else {}
    cloud = status.get("cloud") if isinstance(status.get("cloud"), dict) else {}
    local = status.get("local") if isinstance(status.get("local"), dict) else {}

    registered = bool(identity.get("registered"))
    running = bool(status.get("running"))
    guild = identity.get("guild_id") or "none"
    node = identity.get("cloud_node_id") or identity.get("node_id") or "none"
    state = str(identity.get("status") or "unknown")

    header = Text()
    header.append(str(status.get("product") or "CultForge Agent"), style="bold")
    header.append(f"  v{status.get('version') or '?'}", style="dim")

    summary = Table.grid(padding=(0, 2))
    summary.add_column(style="dim", justify="right")
    summary.add_column()
    summary.add_row("node", Text(str(node), style="cyan"))
    summary.add_row("name", str(identity.get("display_name") or "none"))
    summary.add_row("status", _status_text(state))
    summary.add_row("registered", _yes_no(registered))
    summary.add_row("running", _yes_no(running))
    summary.add_row("owner", str(identity.get("owner_account_id") or "none"))
    summary.add_row("guild", Text(str(guild), style="green" if identity.get("guild_id") else "dim"))
    summary.add_row(
        "platform",
        f"{identity.get('platform') or '?'} / {identity.get('architecture') or '?'}",
    )

    cloud_tbl = Table.grid(padding=(0, 2))
    cloud_tbl.add_column(style="dim", justify="right")
    cloud_tbl.add_column()
    cloud_tbl.add_row("api", Text(str(cloud.get("api_base") or "none"), style="cyan"))
    cloud_tbl.add_row("poll", f"{cloud.get('poll_interval_seconds', '?')}s")
    cloud_tbl.add_row(
        "control plane",
        _yes_no(bool(cloud.get("control_plane_enabled"))),
    )
    transport = cloud.get("transport") if isinstance(cloud.get("transport"), dict) else {}
    if transport.get("mode") == "websocket" and transport.get("connected"):
        cloud_tbl.add_row("transport", Text("websocket", style="bold green"))
    else:
        cloud_tbl.add_row("transport", Text("https poll", style="dim"))
    cloud_tbl.add_row("network", str(status.get("network_provider") or "none"))

    local_tbl = Table.grid(padding=(0, 2))
    local_tbl.add_column(style="dim", justify="right")
    local_tbl.add_column()
    local_tbl.add_row("bind", str(local.get("bind") or "none"))
    local_tbl.add_row("data", Text(str(local.get("data_dir") or "none"), overflow="fold"))

    caps = identity.get("capabilities") if isinstance(identity.get("capabilities"), list) else []
    caps_line = Text(", ".join(str(c) for c in caps[:8]), style="dim")
    if len(caps) > 8:
        caps_line.append(f"  (+{len(caps) - 8} more)", style="dim italic")

    body = Group(
        summary,
        Text(""),
        Text("Cloud", style="bold"),
        cloud_tbl,
        Text(""),
        Text("Local", style="bold"),
        local_tbl,
        Text(""),
        Text("Capabilities", style="bold"),
        caps_line or Text("none", style="dim"),
    )
    console.print(Panel(body, title=header, border_style="cyan", padding=(1, 2)))


def print_login_waiting(info: dict[str, Any]) -> None:
    rows = Table.grid(padding=(0, 2))
    rows.add_column(style="dim", justify="right")
    rows.add_column()
    if info.get("mode") == "jwt":
        rows.add_row("mode", "JWT approve")
    else:
        rows.add_row("auth", Text(str(info.get("auth_base") or ""), style="cyan"))
        rows.add_row("provider", str(info.get("oauth_provider") or "google"))
        rows.add_row("next", "Sign in in the browser, then return here")
    rows.add_row("device code", Text(str(info.get("user_code") or ""), style="bold green"))
    console.print(
        Panel(rows, title="[bold]CultForge Agent Login[/bold]", border_style="green", padding=(1, 2))
    )


def print_login_success(status: dict[str, Any]) -> None:
    console.print("[bold green]✓ Logged in to CultForge[/bold green]")
    print_status(status)


def print_health(result: dict[str, Any]) -> None:
    table = Table(title="Cloud health", show_header=True, header_style="dim", box=None, padding=(0, 1))
    table.add_column("Service")
    table.add_column("Status")
    table.add_column("Detail", overflow="fold")
    if isinstance(result.get("services"), dict):
        for name, info in result["services"].items():
            if isinstance(info, dict):
                ok = info.get("ok")
                status = Text("up", style="green") if ok else Text("down", style="red")
                detail = str(info.get("error") or info.get("status") or info.get("url") or "")
            else:
                status = Text(str(info))
                detail = ""
            table.add_row(str(name), status, detail)
        console.print(table)
        return
    console.print(_dict_panel(result, title="Cloud health"))


def print_manifest(summary: dict[str, Any]) -> None:
    """Render cloud-manifest summary: clean service URLs + route checklist."""
    ok = bool(summary.get("required_ok"))
    header = Table.grid(padding=(0, 2))
    header.add_column(style="dim", justify="right")
    header.add_column()
    header.add_row("api", Text(str(summary.get("api_base") or ""), style="cyan"))
    header.add_row("build", str(summary.get("build_id") or "—"))
    header.add_row(
        "required routes",
        Text("ok", style="bold green") if ok else Text("missing", style="bold red"),
    )
    header.add_row("agent routes", str(summary.get("agent_route_count") or 0))
    if summary.get("realtime_ready"):
        header.add_row("realtime ws", Text(str(summary.get("realtime_ws") or ""), style="green"))
    else:
        header.add_row("realtime ws", Text("not advertised (HTTPS poll)", style="dim"))

    services = summary.get("services") if isinstance(summary.get("services"), dict) else {}
    svc = Table(show_header=True, header_style="dim", box=None, padding=(0, 1), title="Workers")
    svc.add_column("Service", style="bold")
    svc.add_column("URL", style="cyan")
    for name in ("api", "auth", "invite", "guilds"):
        if name in services:
            svc.add_row(name, str(services[name]))
    for name, url in services.items():
        if name not in ("api", "auth", "invite", "guilds"):
            svc.add_row(str(name), str(url))

    parts: list[Any] = [header, Text(""), svc]

    missing = summary.get("missing_required") or []
    if missing:
        miss = Table(show_header=False, box=None, padding=(0, 1), title="Missing required")
        miss.add_column(style="red")
        for route in missing:
            miss.add_row(str(route))
        parts.extend([Text(""), miss])

    routes = summary.get("agent_routes") if isinstance(summary.get("agent_routes"), list) else []
    if routes:
        route_tbl = Table(
            show_header=False,
            box=None,
            padding=(0, 1),
            title=f"Agent routes ({len(routes)})",
        )
        route_tbl.add_column(style="dim")
        for route in routes:
            route_tbl.add_row(str(route))
        parts.extend([Text(""), route_tbl])

    note = summary.get("note")
    if note:
        parts.extend([Text(""), Text(str(note), style="dim italic")])

    border = "green" if ok else "red"
    console.print(
        Panel(
            Group(*parts),
            title="[bold]Cloud manifest[/bold]",
            border_style=border,
            padding=(1, 2),
        )
    )


def print_modrinth_search(payload: dict[str, Any]) -> None:
    hits = payload.get("hits") if isinstance(payload.get("hits"), list) else []
    data = payload.get("data") if isinstance(payload.get("data"), dict) else None
    if data and not hits:
        hits = data.get("hits") if isinstance(data.get("hits"), list) else []
        payload = data

    table = Table(
        show_header=True,
        header_style="dim",
        box=None,
        padding=(0, 1),
        title=f"Modrinth search · {payload.get('query') or ''} ({payload.get('total_hits', len(hits))})",
    )
    table.add_column("Slug", style="cyan")
    table.add_column("Title")
    table.add_column("Type", max_width=12)
    table.add_column("Downloads", justify="right")
    table.add_column("Versions", overflow="fold")
    for hit in hits[:40]:
        if not isinstance(hit, dict):
            continue
        versions = hit.get("versions") or []
        ver_s = ", ".join(str(v) for v in versions[-3:]) if isinstance(versions, list) else ""
        table.add_row(
            str(hit.get("slug") or hit.get("project_id") or ""),
            str(hit.get("title") or ""),
            str(hit.get("project_type") or ""),
            str(hit.get("downloads") or ""),
            ver_s,
        )
    if table.row_count == 0:
        table.add_row("—", "(no hits)", "", "", "")
    console.print(table)


def print_modrinth_project(payload: dict[str, Any]) -> None:
    project = payload.get("project") if isinstance(payload.get("project"), dict) else payload
    data = payload.get("data") if isinstance(payload.get("data"), dict) else None
    if data and "project" in data:
        project = data["project"] if isinstance(data["project"], dict) else project

    if not isinstance(project, dict):
        console.print(Pretty(payload))
        return

    rows = Table.grid(padding=(0, 2))
    rows.add_column(style="dim", justify="right")
    rows.add_column()
    rows.add_row("title", Text(str(project.get("title") or ""), style="bold"))
    rows.add_row("slug", Text(str(project.get("slug") or ""), style="cyan"))
    rows.add_row("id", str(project.get("id") or ""))
    rows.add_row("type", str(project.get("project_type") or ""))
    rows.add_row(
        "side",
        f"client={project.get('client_side')}  server={project.get('server_side')}",
    )
    license_v = project.get("license")
    if isinstance(license_v, dict):
        license_v = license_v.get("id") or license_v.get("name")
    rows.add_row("license", str(license_v or "—"))
    rows.add_row("downloads", str(project.get("downloads") or "—"))
    cats = project.get("categories") or []
    if isinstance(cats, list) and cats:
        rows.add_row("categories", ", ".join(str(c) for c in cats[:12]))
    desc = str(project.get("description") or "").strip()
    parts: list[Any] = [rows]
    if desc:
        parts.extend([Text(""), Text(desc[:400], style="dim")])
    console.print(
        Panel(Group(*parts), title="[bold]Modrinth project[/bold]", border_style="cyan", padding=(1, 2))
    )


def print_modrinth_versions(payload: dict[str, Any]) -> None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    versions = data.get("versions") if isinstance(data, dict) else None
    if not isinstance(versions, list):
        console.print(Pretty(payload))
        return
    table = Table(
        show_header=True,
        header_style="dim",
        box=None,
        padding=(0, 1),
        title=(
            f"Versions · {data.get('project_id')} · "
            f"{data.get('loader')}/{data.get('game_version')}"
        ),
    )
    table.add_column("Version", style="cyan")
    table.add_column("ID")
    table.add_column("Type", max_width=10)
    table.add_column("Loaders")
    table.add_column("Released", max_width=12)
    for v in versions[:30]:
        if not isinstance(v, dict):
            continue
        loaders = ", ".join(str(x) for x in (v.get("loaders") or [])[:4])
        table.add_row(
            str(v.get("version_number") or ""),
            str(v.get("id") or ""),
            str(v.get("version_type") or ""),
            loaders,
            str(v.get("date_published") or "")[:10],
        )
    if table.row_count == 0:
        table.add_row("—", "(none for this loader/MC)", "", "", "")
    console.print(table)


def print_mods_list(payload: dict[str, Any]) -> None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    mods = data.get("mods") if isinstance(data, dict) else None
    if not isinstance(mods, list):
        console.print(Pretty(payload))
        return
    table = Table(
        show_header=True,
        header_style="dim",
        box=None,
        padding=(0, 1),
        title=f"Installed mods · {data.get('server_id') or ''}",
    )
    table.add_column("File", style="cyan")
    table.add_column("Title")
    table.add_column("Slug")
    table.add_column("Ver")
    table.add_column("Size", justify="right")
    for m in mods:
        if not isinstance(m, dict):
            continue
        size = m.get("size")
        size_s = _fmt_size(int(size)) if isinstance(size, int) else str(size or "")
        table.add_row(
            str(m.get("name") or ""),
            str(m.get("title") or ""),
            str(m.get("slug") or ""),
            str(m.get("version_number") or ""),
            size_s,
        )
    if table.row_count == 0:
        table.add_row("—", "(none)", "", "", "")
    console.print(table)


def print_mods_resolve(payload: dict[str, Any]) -> None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        console.print(Pretty(payload))
        return
    rows = Table.grid(padding=(0, 2))
    rows.add_column(style="dim", justify="right")
    rows.add_column()
    ok = data.get("ok") is not False
    rows.add_row("result", Text("OK" if ok else "INCOMPLETE", style="bold green" if ok else "bold yellow"))
    if data.get("source"):
        rows.add_row("source", str(data.get("source")))
    if data.get("issue_count") is not None:
        rows.add_row("crash issues", str(data.get("issue_count")))
    rows.add_row("jars scanned", str(data.get("jars") or 0))
    rows.add_row("identified", str(len(data.get("identified") or [])))
    rows.add_row("unknown", str(len(data.get("unknown") or [])))
    rows.add_row("libraries added", str(data.get("added_count") or 0))
    rows.add_row("client-only disabled", str(data.get("disabled_count") or 0))
    failed = data.get("failed") or []
    errors = data.get("errors") or []
    rows.add_row(
        "failed",
        Text(str(len(failed) + len(errors)), style="red" if (failed or errors) else "dim"),
    )
    console.print(rows)

    added = data.get("installed") or []
    if isinstance(added, list) and added:
        table = Table(
            show_header=True,
            header_style="dim",
            box=None,
            padding=(0, 1),
            title="Installed libraries",
        )
        table.add_column("File", style="cyan")
        table.add_column("Slug")
        table.add_column("Ver")
        for item in added[:40]:
            if not isinstance(item, dict):
                continue
            table.add_row(
                str(item.get("filename") or ""),
                str(item.get("slug") or item.get("project_id") or ""),
                str(item.get("version_number") or ""),
            )
        if len(added) > 40:
            table.add_row(f"… {len(added) - 40} more", "", "")
        console.print(table)

    disabled = data.get("disabled_client_only") or []
    if isinstance(disabled, list) and disabled:
        table = Table(show_header=False, box=None, padding=(0, 1), title="Disabled client-only")
        table.add_column(style="yellow")
        for name in disabled[:30]:
            table.add_row(str(name))
        console.print(table)

    unknown = data.get("unknown") or []
    if isinstance(unknown, list) and unknown:
        table = Table(show_header=False, box=None, padding=(0, 1), title="Not on Modrinth")
        table.add_column(style="dim")
        for name in unknown[:20]:
            table.add_row(str(name))
        if len(unknown) > 20:
            table.add_row(f"… {len(unknown) - 20} more")
        console.print(table)

    if errors:
        table = Table(show_header=False, box=None, padding=(0, 1), title="Errors")
        table.add_column(style="red")
        for err in errors[:20]:
            table.add_row(str(err))
        console.print(table)
    if failed:
        table = Table(show_header=False, box=None, padding=(0, 1), title="Failed installs")
        table.add_column(style="red")
        for item in failed[:20]:
            if isinstance(item, dict):
                table.add_row(f"{item.get('project_id') or '?'}: {item.get('error') or 'failed'}")
            else:
                table.add_row(str(item))
        console.print(table)


def print_network_status(payload: dict[str, Any]) -> None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        console.print(Pretty(payload))
        return

    rows = Table.grid(padding=(0, 2))
    rows.add_column(style="dim", justify="right")
    rows.add_column()
    active = str(data.get("active") or data.get("provider") or "—")
    status = str(data.get("status") or "—")
    status_style = {
        "online": "bold green",
        "connecting": "bold yellow",
        "offline": "dim",
        "error": "bold red",
    }.get(status.lower(), "")
    rows.add_row("active", Text(active, style="cyan"))
    rows.add_row("status", Text(status, style=status_style or None))
    rows.add_row("target", str(data.get("target") or "—"))
    public = data.get("public_join") or data.get("public_endpoint")
    rows.add_row(
        "public join",
        Text(str(public or "—"), style="green" if public else "dim"),
    )
    details = data.get("details") if isinstance(data.get("details"), dict) else {}
    if details.get("has_secret") is not None:
        rows.add_row("secret", "set" if details.get("has_secret") else "missing")
    if details.get("binary"):
        rows.add_row("binary", Text(str(details.get("binary")), overflow="fold"))
    if details.get("claim_code"):
        rows.add_row("claim code", Text(str(details["claim_code"]), style="bold yellow"))
    if details.get("claim_url"):
        rows.add_row("claim", Text(str(details["claim_url"]), style="yellow"))
    if details.get("last_error"):
        rows.add_row("error", Text(str(details["last_error"]), style="red"))
    if details.get("public_hints"):
        rows.add_row("seen", ", ".join(str(x) for x in details["public_hints"][-4:]))

    playit = data.get("playit") if isinstance(data.get("playit"), dict) else None
    parts: list[Any] = [rows]
    if playit:
        p = Table.grid(padding=(0, 2))
        p.add_column(style="dim", justify="right")
        p.add_column()
        p.add_row("playit status", str(playit.get("status") or "—"))
        p.add_row(
            "playit public join",
            str(playit.get("public_join") or playit.get("public_endpoint") or "—"),
        )
        parts.extend([Text(""), Text("Playit (inactive provider)", style="bold dim"), p])

    console.print(
        Panel(Group(*parts), title="[bold]Network[/bold]", border_style="cyan", padding=(1, 2))
    )


def print_java(info: dict[str, Any]) -> None:
    rows = Table.grid(padding=(0, 2))
    rows.add_column(style="dim", justify="right")
    rows.add_column()
    rows.add_row("path", Text(str(info.get("path") or ""), style="cyan"))
    rows.add_row("version", str(info.get("version") or "?"))
    console.print(Panel(rows, title="[bold]Java[/bold]", border_style="cyan", padding=(1, 2)))


def print_profiles(payload: dict[str, Any]) -> None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    profiles = (data or {}).get("profiles") if isinstance(data, dict) else None
    if not isinstance(profiles, list):
        console.print(Pretty(payload))
        return
    table = Table(
        title="Config profiles",
        show_header=True,
        header_style="dim",
        box=None,
        padding=(0, 1),
    )
    table.add_column("Name", style="cyan")
    table.add_column("Keys", justify="right")
    table.add_column("Description", overflow="fold")
    for p in profiles:
        if not isinstance(p, dict):
            continue
        table.add_row(
            str(p.get("name") or ""),
            str(p.get("keys") or 0),
            str(p.get("description") or ""),
        )
    if table.row_count == 0:
        table.add_row("—", "", "(no profiles)")
    console.print(table)


def print_profile_diff(payload: dict[str, Any]) -> None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        console.print(Pretty(payload))
        return
    changes = data.get("changes") if isinstance(data.get("changes"), dict) else {}
    title = f"Profile diff · {data.get('profile') or '?'} → {data.get('server_id') or '?'}"
    if data.get("applied"):
        title += " (applied)"
    elif data.get("dry_run"):
        title += " (dry-run)"
    table = Table(title=title, show_header=True, header_style="dim", box=None, padding=(0, 1))
    table.add_column("Key", style="cyan")
    table.add_column("From", overflow="fold")
    table.add_column("To", overflow="fold")
    for key, change in sorted(changes.items()):
        if isinstance(change, dict):
            table.add_row(str(key), str(change.get("from")), str(change.get("to")))
        else:
            table.add_row(str(key), "", str(change))
    if table.row_count == 0:
        table.add_row("—", "(no changes)", "")
    console.print(table)
    note = data.get("note")
    if note:
        console.print(Text(str(note), style="dim"))


def print_doctor(payload: dict[str, Any]) -> None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        console.print(Pretty(payload))
        return
    checks = data.get("checks") if isinstance(data.get("checks"), list) else []
    overall = bool(data.get("ok"))
    table = Table(
        title=f"Doctor · {'OK' if overall else 'ISSUES'} · v{data.get('version') or '?'}",
        show_header=True,
        header_style="dim",
        box=None,
        padding=(0, 1),
    )
    table.add_column("Check")
    table.add_column("Status")
    table.add_column("Detail", overflow="fold")
    for c in checks:
        if not isinstance(c, dict):
            continue
        passed = bool(c.get("ok"))
        required = c.get("required", True)
        if passed:
            status = Text("ok", style="green")
        elif required:
            status = Text("FAIL", style="bold red")
        else:
            status = Text("warn", style="yellow")
        table.add_row(str(c.get("name") or ""), status, str(c.get("detail") or ""))
    console.print(table)


def print_sidecar_issue(payload: dict[str, Any]) -> None:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        console.print(Pretty(payload))
        return
    rows = Table.grid(padding=(0, 2))
    rows.add_column(style="dim", justify="right")
    rows.add_column()
    rows.add_row("name", Text(str(data.get("name") or ""), style="cyan"))
    rows.add_row("actor_id", str(data.get("actor_id") or ""))
    rows.add_row("role", str(data.get("role") or ""))
    token = data.get("token")
    if token:
        rows.add_row("token", Text(str(token), style="yellow"))
    console.print(
        Panel(
            Group(
                rows,
                Text(""),
                Text(str(data.get("note") or "Store the token securely."), style="dim"),
            ),
            title="[bold]Sidecar issued[/bold]",
            border_style="cyan",
            padding=(1, 2),
        )
    )


def print_listeners(rows: list[dict[str, Any]], *, port: int) -> None:
    table = Table(
        title=f"Listeners on :{port}",
        show_header=True,
        header_style="dim",
        box=None,
        padding=(0, 1),
    )
    table.add_column("PID", style="cyan")
    table.add_column("Name")
    table.add_column("Command", overflow="fold")
    for row in rows:
        table.add_row(str(row.get("pid")), str(row.get("name")), str(row.get("cmdline"))[:120])
    console.print(table)


def _servers_table(servers: list[Any]) -> Table:
    table = Table(show_header=True, header_style="dim", box=None, padding=(0, 1), title="Servers")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Loader")
    table.add_column("MC")
    table.add_column("Port")
    for s in servers:
        if hasattr(s, "model_dump"):
            s = s.model_dump()
        if not isinstance(s, dict):
            continue
        # nested {server, status} rows from some list shapes
        rec = s.get("server") if isinstance(s.get("server"), dict) else s
        table.add_row(
            str(rec.get("server_id") or ""),
            str(rec.get("name") or ""),
            str(rec.get("loader") or ""),
            str(rec.get("minecraft_version") or "—"),
            str(rec.get("port") or ""),
        )
    if table.row_count == 0:
        table.add_row("—", "(none)", "", "", "")
    return table


def _builds_table(builds: list[Any]) -> Table:
    table = Table(show_header=True, header_style="dim", box=None, padding=(0, 1), title="Builds")
    table.add_column("ID", style="cyan")
    table.add_column("Name")
    table.add_column("Loader")
    table.add_column("MC")
    for b in builds:
        if not isinstance(b, dict):
            continue
        table.add_row(
            str(b.get("build_id") or b.get("id") or ""),
            str(b.get("name") or b.get("display_name") or ""),
            str(b.get("loader") or "—"),
            str(b.get("minecraft_version") or b.get("version") or "—"),
        )
    if table.row_count == 0:
        table.add_row("—", "(none)", "", "")
    return table


def _console_block(lines: list[Any]) -> Panel:
    texts: list[str] = []
    for line in lines[-80:]:
        if isinstance(line, str):
            texts.append(line)
        elif isinstance(line, dict):
            texts.append(str(line.get("text") or line))
        else:
            texts.append(str(line))
    body = "\n".join(texts) if texts else "(no lines)"
    return Panel(body, title="Console", border_style="green", padding=(0, 1))


def _list_preview(items: list[Any]) -> Table | Pretty:
    if items and all(isinstance(i, dict) for i in items):
        return _inline_list_table(items)  # type: ignore[arg-type]
    return Pretty(items)


def _inline_list_table(items: list[dict[str, Any]]) -> Table:
    keys: list[str] = []
    for item in items:
        for k in item:
            if k not in keys:
                keys.append(str(k))
    keys = keys[:5]
    table = Table(show_header=True, header_style="dim", box=None, padding=(0, 1))
    for k in keys:
        table.add_column(k)
    for item in items:
        table.add_row(*[str(item.get(k, ""))[:40] for k in keys])
    return table


def _dict_table(data: dict[str, Any]) -> Table:
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column(style="dim", justify="right")
    table.add_column()
    for key, value in data.items():
        if isinstance(value, list):
            table.add_row(str(key), f"[{len(value)} items]")
        elif isinstance(value, dict):
            # Keep tiny dicts readable; summarize large nested payloads
            if len(value) <= 6 and all(
                not isinstance(v, (dict, list)) for v in value.values()
            ):
                table.add_row(str(key), Pretty(value, expand_all=False))
            else:
                table.add_row(str(key), f"{{{len(value)} keys}}")
        else:
            table.add_row(str(key), str(value))
    return table


def _dict_panel(data: dict[str, Any], *, title: str | None = None) -> Panel:
    return Panel(_dict_table(data), title=title, border_style="cyan", padding=(0, 1))


def _yes_no(value: bool) -> Text:
    return Text("yes", style="green") if value else Text("no", style="dim")


def _status_text(state: str) -> Text:
    color = {
        "online": "green",
        "registering": "yellow",
        "degraded": "yellow",
        "offline": "red",
        "unregistered": "dim",
    }.get(state.lower(), "white")
    return Text(state, style=f"bold {color}")
