"""CLI mode detection and context-aware command visibility."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Any, Iterable

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel

from cultagent.app import create_app

console = Console()


class CliMode(str, Enum):
    UNREGISTERED = "unregistered"
    PERSONAL = "personal"
    GUILD = "guild"


# Always available (or mode-gated inside the command).
SETUP_COMMANDS: frozenset[str] = frozenset(
    {
        "help",
        "version",
        "init",
        "status",
        "doctor",
        "java",
        "kill",
        "login",
        "register",
        "unregister",
        "service",
    }
)

# Machine-side Minecraft / network — no CultForge account required.
LOCAL_COMMANDS: frozenset[str] = frozenset(
    {
        "run",
        "exec",
        "servers",
        "server-create",
        "server-install",
        "eula-accept",
        "server-start",
        "server-stop",
        "server-remove",
        "console",
        "mods",
        "mod-install",
        "mod-remove",
        "mod-update",
        "mod-resolve",
        "network",
        "network-use",
        "playit-setup",
        "playit-claim",
        "playit-reset",
        "playit-secret",
        "playit-start",
        "playit-stop",
        "playit-logs",
        "profiles",
        "profile-capture",
        "profile-apply",
        "profile-delete",
    }
)

# Signed-in CultForge agent (personal or guild node).
CLOUD_COMMANDS: frozenset[str] = frozenset(
    {
        "builds",
        "build",
        "build-manifest",
        "agent-servers",
        "cloud-health",
        "cloud-manifest",
        "update-check",
        "sidecar-list",
        "sidecar-issue",
        "sidecar-revoke",
    }
)

# Guild-attached node only.
GUILD_COMMANDS: frozenset[str] = frozenset(
    {
        "server-clone",
        "guild-server",
        "guild-tunnel",
    }
)

HELP_SECTIONS: tuple[tuple[str, frozenset[str], frozenset[CliMode]], ...] = (
    (
        "Setup & identity",
        SETUP_COMMANDS,
        frozenset({CliMode.UNREGISTERED, CliMode.PERSONAL, CliMode.GUILD}),
    ),
    (
        "Local — Minecraft on this PC",
        LOCAL_COMMANDS,
        frozenset({CliMode.UNREGISTERED, CliMode.PERSONAL, CliMode.GUILD}),
    ),
    (
        "Cloud — CultForge account",
        CLOUD_COMMANDS,
        frozenset({CliMode.PERSONAL, CliMode.GUILD}),
    ),
    (
        "Guild — guild server hosting",
        GUILD_COMMANDS,
        frozenset({CliMode.GUILD}),
    ),
)

# Hidden aliases inherit visibility from their canonical command.
ALIAS_CANONICAL: dict[str, str] = {
    "builds-search": "builds",
    "guild-servers": "agent-servers",
    "agent-bindings": "agent-servers",
    "build-provision": "build",
    "build-install": "build",
    "playit-tunnel": "playit-start",
    "reset": "playit-reset",
    "profile-show": "profiles",
    "profile-diff": "profile-apply",
    "modrinth-search": "mods",
    "modrinth-info": "mods",
    "modrinth-versions": "mods",
}


def validated_config_path(config: Path | str | None) -> Path | None:
    """Reject mistaken ``cf-agent --config -c`` (missing path) with a clear error."""
    if config is None:
        return None
    path = Path(config)
    token = str(path)
    if token in {"-c", "--config"} or (token.startswith("-") and token not in {".", ".."}):
        rprint(
            "[red]Missing config path[/red] after [cyan]-c[/cyan] / [cyan]--config[/cyan].\n"
            "Example: [cyan]cf-agent -c config.yaml status[/cyan]"
        )
        raise typer.Exit(code=2)
    if not path.is_file():
        rprint(f"[red]Config file not found:[/red] {path}")
        raise typer.Exit(code=2)
    return path


def detect_cli_mode(config_path: str | Path | None = None) -> tuple[CliMode, dict[str, Any]]:
    """Return CLI mode and a small identity summary for help banners."""
    config_path = validated_config_path(config_path)
    agent = create_app(str(config_path) if config_path else None)
    agent.bootstrap_identity()
    creds = agent.identity_store.load_credentials()
    identity = agent.identity_store.load_identity()
    summary: dict[str, Any] = {
        "registered": creds.has_credentials,
        "guild_id": getattr(identity, "guild_id", None) if identity else None,
        "node_id": getattr(identity, "cloud_node_id", None) or getattr(identity, "node_id", None)
        if identity
        else None,
        "status": getattr(getattr(identity, "status", None), "value", None) if identity else None,
    }
    if not creds.has_credentials:
        return CliMode.UNREGISTERED, summary
    if identity and identity.guild_id:
        return CliMode.GUILD, summary
    return CliMode.PERSONAL, summary


def allowed_commands(mode: CliMode) -> frozenset[str]:
    allowed: set[str] = set()
    for _title, commands, modes in HELP_SECTIONS:
        if mode in modes:
            allowed |= set(commands)
    return frozenset(allowed)


def resolve_command_name(name: str) -> str:
    return ALIAS_CANONICAL.get(name, name)


def _canonical_for_row(name: str) -> str:
    token = name.split()[-1] if " " in name else name
    return resolve_command_name(token)


def _section_for_command(name: str) -> str | None:
    if name.startswith("service "):
        return "Setup & identity"
    canonical = _canonical_for_row(name)
    for title, commands, _modes in HELP_SECTIONS:
        if canonical in commands:
            return title
    return None


def command_allowed(mode: CliMode, command_name: str) -> bool:
    canonical = resolve_command_name(command_name)
    if canonical == "service":
        return True
    return canonical in allowed_commands(mode)


def ensure_command_allowed(
    command_name: str,
    config_path: str | Path | None = None,
    *,
    ctx: typer.Context | None = None,
) -> CliMode:
    import sys

    # Real CLI: argv contains --help. Tests (CliRunner): rely on ctx.resilient_parsing.
    if (
        (ctx is not None and ctx.resilient_parsing)
        or "--help" in sys.argv
        or "-h" in sys.argv
    ):
        mode, _ = detect_cli_mode(config_path)
        return mode

    mode, summary = detect_cli_mode(config_path)
    if command_allowed(mode, command_name):
        return mode
    canonical = resolve_command_name(command_name)
    if mode == CliMode.UNREGISTERED:
        hint = "Run [cyan]cf-agent login[/cyan] for Cloud and Guild commands."
    elif mode == CliMode.PERSONAL and canonical in GUILD_COMMANDS:
        hint = (
            "Guild commands need a [bold]guild-attached[/bold] node. "
            "Ask a GuildMaster to attach this agent, then [cyan]cf-agent login[/cyan] again."
        )
    else:
        hint = f"Not available in [bold]{mode.value}[/bold] mode."
    rprint(
        Panel(
            f"[red]Command not available:[/red] [cyan]{command_name}[/cyan]\n"
            f"Mode: [bold]{mode.value}[/bold]"
            + (f" · guild [dim]{summary.get('guild_id')}[/dim]" if summary.get("guild_id") else "")
            + (f"\n{hint}" if hint else ""),
            title="cf-agent",
            border_style="red",
        )
    )
    raise typer.Exit(code=2)


def _mode_banner(mode: CliMode, summary: dict[str, Any]) -> str:
    if mode == CliMode.UNREGISTERED:
        return "local machine — not signed in ([cyan]cf-agent login[/cyan] for cloud)"
    if mode == CliMode.GUILD:
        gid = summary.get("guild_id") or "guild"
        return f"guild agent · {gid}"
    return "personal cloud agent — no guild attached"


def _iter_visible_commands(typer_app: typer.Typer) -> Iterable[tuple[str, str]]:
    for cmd in typer_app.registered_commands:
        if cmd.hidden:
            continue
        yield cmd.name, (cmd.help or "").strip()
    for group in typer_app.registered_groups:
        sub = group.typer_instance
        prefix = group.name or ""
        for cmd in sub.registered_commands:
            if cmd.hidden:
                continue
            name = f"{prefix} {cmd.name}".strip()
            yield name, (cmd.help or "").strip()


def print_mode_help(typer_app: typer.Typer, config_path: str | Path | None = None) -> None:
    """Print filtered command list grouped by local / cloud / guild."""
    mode, summary = detect_cli_mode(config_path)
    banner = _mode_banner(mode, summary)
    allowed = allowed_commands(mode)

    visible: list[tuple[str, str]] = []
    for name, help_text in _iter_visible_commands(typer_app):
        canonical = _canonical_for_row(name)
        if name.startswith("service ") or canonical in allowed:
            visible.append((name, help_text))

    console.print(
        Panel(
            f"CultForge Agent — [bold]{banner}[/bold]\n"
            "[dim]Commands are grouped: Local = this PC, Cloud = your CultForge account, "
            "Guild = guild-attached node only.[/dim]",
            border_style="cyan",
        )
    )
    console.print()
    console.print("[bold]Usage:[/bold] cf-agent [OPTIONS] COMMAND [ARGS]...")
    console.print()
    console.print("[bold]Options[/bold]")
    console.print("  --clear-cache    Clear download cache and exit")
    console.print("  --capture-json   Raw JSON on stdout")
    console.print("  --config -c      Optional config.yaml")
    console.print("  --help           Full command reference (all names)")
    console.print()

    by_section: dict[str, list[tuple[str, str]]] = {
        title: [] for title, _cmds, modes in HELP_SECTIONS if mode in modes
    }
    for name, help_text in visible:
        section = _section_for_command(name)
        if section and section in by_section:
            by_section[section].append((name, help_text))

    name_w = max((len(n) for n, _ in visible), default=8)
    for title, _commands, modes in HELP_SECTIONS:
        if mode not in modes:
            continue
        rows = by_section.get(title) or []
        if not rows:
            continue
        console.print(f"[bold]{title}[/bold]")
        for name, help_text in rows:
            pad = " " * (name_w - len(name) + 2)
            line = f"  [cyan]{name}[/cyan]{pad}"
            if help_text:
                line += f"[dim]{help_text}[/dim]"
            console.print(line)
        console.print()
