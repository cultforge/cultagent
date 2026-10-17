"""cf-agent CLI."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Optional

import typer
from rich import print as rprint
from typer.core import TyperGroup

from cultagent import __product__, __version__
from cultagent.app import create_app
from cultagent.cli.display import (
    console,
    dump_json_file,
    print_build_manifest,
    print_data,
    print_doctor,
    print_health,
    print_java,
    print_listeners,
    print_login_success,
    print_login_waiting,
    print_manifest,
    print_modrinth_project,
    print_modrinth_search,
    print_modrinth_versions,
    print_mods_list,
    print_network_status,
    print_profile_diff,
    print_profiles,
    print_result,
    print_server_clone,
    print_servers,
    print_sidecar_issue,
    print_status,
    set_capture_json,
)
from cultagent.cli.interact import (
    confirm,
    find_listeners,
    install_progress_ui,
    kill_pids,
    select,
    select_map,
    spinner,
    text_input,
)
from cultagent.cache import clear_agent_cache
from cultagent.paths import default_config_dir
from cultagent.servers.install import SERVER_LOADERS
from cultagent.service import (
    launchd_plist,
    service_hint,
    systemd_unit,
    windows_service_bundle,
)
from cultagent.settings import write_example_config


class ModeGatedGroup(TyperGroup):
    """Gate commands in ``invoke`` after Click has handled ``--help``.

    Help is emitted in ``make_context`` / ``parse_args`` and never reaches
    ``command.invoke``, so cloud help works on unregistered CI machines.
    """

    def invoke(self, ctx: typer.Context) -> Any:
        from cultagent.cli.context import ensure_command_allowed

        original_get = self.get_command

        def get_command_gated(ctx_inner: typer.Context, cmd_name: str) -> Any:
            cmd = original_get(ctx_inner, cmd_name)
            if cmd is None:
                return None
            original_invoke = cmd.invoke

            def invoke_gated(sub_ctx: typer.Context) -> Any:
                config = ctx_inner.params.get("config")
                obj = ctx_inner.obj
                if isinstance(obj, dict) and "config" in obj:
                    config = obj.get("config", config)
                ensure_command_allowed(cmd_name, config)
                return original_invoke(sub_ctx)

            cmd.invoke = invoke_gated  # type: ignore[method-assign]
            return cmd

        self.get_command = get_command_gated  # type: ignore[method-assign]
        try:
            return super().invoke(ctx)
        finally:
            self.get_command = original_get  # type: ignore[method-assign]


app = typer.Typer(
    name="cf-agent",
    help="CultForge Agent — local machine-side execution layer.",
    no_args_is_help=False,
    invoke_without_command=True,
    add_completion=False,
    cls=ModeGatedGroup,
)

service_app = typer.Typer(help="Background service helpers.", cls=ModeGatedGroup)
app.add_typer(service_app, name="service")


def _out(data: Any, *, raw: bool = False, dump_json: Path | None = None) -> None:
    if dump_json is not None:
        dump_json_file(data, dump_json)
    print_data(data, raw=raw)


def _emit(
    data: Any,
    *,
    dump_json: Path | None = None,
    printer: Any = None,
) -> None:
    """Rich print + optional JSON file dump / --capture-json stdout."""
    from cultagent.cli.display import capture_json_enabled, print_json_payload

    if dump_json is not None:
        dump_json_file(data, dump_json)
    if capture_json_enabled():
        print_json_payload(data)
        return
    if printer is not None:
        printer(data)
    else:
        print_data(data)


def _dump_opt() -> Any:
    return typer.Option(
        None,
        "--dump-json",
        help="Also write the raw JSON payload to this file",
        show_default=False,
    )


async def _pick_server_id(agent: Any, server_id: str | None) -> str:
    if server_id:
        return server_id
    result = await agent.dispatch("server.list")
    servers = (result.get("data") or {}).get("servers") or []
    if not servers:
        console.print("[yellow]No servers configured.[/yellow]")
        raise typer.Exit(code=1)
    picked = select_map(
        "Select server",
        servers,
        label=lambda s: f"{s.get('name')}  ({s.get('server_id')})  :{s.get('port')}",
    )
    if not picked:
        raise typer.Abort()
    return str(picked["server_id"])


@app.callback(invoke_without_command=True)
def main_callback(
    ctx: typer.Context,
    clear_cache: bool = typer.Option(
        False,
        "--clear-cache",
        help="Clear the agent download/content cache and exit.",
        is_eager=True,
    ),
    capture_json: bool = typer.Option(
        False,
        "--capture-json",
        help="Print raw JSON to stdout instead of Rich summaries (any subcommand).",
    ),
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        metavar="PATH",
        help="Path to config.yaml (optional).",
        show_default=False,
    ),
) -> None:
    """CultForge Agent CLI."""
    from cultagent.cli.context import (
        print_mode_help,
        validated_config_path,
    )

    config = validated_config_path(config)
    ctx.ensure_object(dict)
    ctx.obj["config"] = config
    set_capture_json(capture_json)
    if clear_cache:
        agent = create_app(str(config) if config else None)
        summary = clear_agent_cache(agent.paths.cache_dir)
        removed = summary.get("removed_bytes") or 0
        entries = summary.get("removed_entries") or 0
        if removed >= 1024 * 1024:
            size_txt = f"{removed / (1024 * 1024):.1f} MiB"
        elif removed >= 1024:
            size_txt = f"{removed / 1024:.1f} KiB"
        else:
            size_txt = f"{removed} B"
        rprint(
            f"[green]Cleared cache[/green] {summary['path']} "
            f"([cyan]{entries}[/cyan] entries, [cyan]{size_txt}[/cyan])"
        )
        raise typer.Exit(code=0)
    if ctx.invoked_subcommand is None:
        print_mode_help(app, config)
        raise typer.Exit(code=0)
    # Mode gating runs in ModeGatedCommand.invoke (skipped for --help).


@app.command("help")
def help_cmd(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
) -> None:
    """Show commands available in the current agent mode (guild / personal / local)."""
    from cultagent.cli.context import print_mode_help

    print_mode_help(app, config)


@app.command("version")
def version_cmd() -> None:
    """Show product version."""
    rprint(f"[bold]{__product__}[/bold] [cyan]{__version__}[/cyan]")


@app.command("init")
def init_cmd(
    force: bool = typer.Option(False, "--force", help="Overwrite existing config.yaml"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Create local config + data directories."""
    with spinner("Initializing CultAgent…"):
        agent = create_app()
        agent.bootstrap_identity()
        dest = default_config_dir() / "config.yaml"
        created = False
        if not dest.exists() or force:
            write_example_config(dest)
            created = True
        status = agent.public_status()

    if created:
        rprint(f"[green]Wrote[/green] {dest}")
    else:
        rprint(f"[yellow]Config already exists:[/yellow] {dest}")
    rprint("[green]Initialized CultAgent[/green]")
    _emit(status, dump_json=dump_json, printer=print_status)


@app.command("status")
def status_cmd(
    config: Optional[Path] = typer.Option(None, "--config", "-c", help="Config path"),
    raw: bool = typer.Option(False, "--raw", help="Pretty-print raw structure"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Show agent identity and runtime status."""
    with spinner("Loading status…"):
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        status = agent.public_status()
    _out(status, raw=raw, dump_json=dump_json)


@app.command("kill")
def kill_cmd(
    port: Optional[int] = typer.Option(
        None,
        "--port",
        "-p",
        help="TCP port to clear (default: local panel bind port, usually 8720)",
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
) -> None:
    """Kill whatever is listening on the CultAgent panel port."""
    if port is None:
        agent = create_app(str(config) if config else None)
        port = int(agent.config.local.bind_port)

    with spinner(f"Scanning :{port}…"):
        listeners = find_listeners(port)

    if not listeners:
        rprint(f"[dim]Nothing listening on[/dim] [cyan]:{port}[/cyan]")
        raise typer.Exit(code=0)

    print_listeners(listeners, port=port)
    pids = [int(row["pid"]) for row in listeners]
    if not yes and not confirm(f"Kill {len(pids)} process(es) on :{port}?", default=False):
        raise typer.Abort()

    with spinner("Sending SIGKILL…"):
        results = kill_pids(pids)

    for pid, msg in results:
        style = "green" if msg == "killed" else "yellow"
        console.print(f"  [{style}]PID {pid}[/{style}]  {msg}")

    left = find_listeners(port)
    if left:
        rprint(f"[red]Still listening on :{port}[/red]")
        print_listeners(left, port=port)
        raise typer.Exit(code=1)
    rprint(f"[bold green]Port :{port} is free[/bold green]")


@app.command("login")
def login_cmd(
    provider: str = typer.Option(
        "google",
        "--provider",
        "-p",
        help="OAuth provider: google | github | discord | microsoft",
    ),
    jwt: Optional[str] = typer.Option(
        None,
        "--jwt",
        help="Automation only: skip browser and approve with a user session JWT",
    ),
    guild_id: Optional[str] = typer.Option(
        None, "--guild-id", help="Optional guild to attach on approve"
    ),
    no_browser: bool = typer.Option(
        False, "--no-browser", help="Print auth URL only (still waits on loopback)"
    ),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Sign in with CultForge (opens auth.cultforge.com — no JWT paste)."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        identity = agent.identity_store.load_identity()
        assert identity is not None

        def _prompt(info: dict[str, Any]) -> None:
            print_login_waiting(info)

        try:
            await agent.registration.device_login(
                identity,
                open_browser=not no_browser,
                approve_jwt=jwt,
                guild_id=guild_id,
                oauth_provider=provider,
                on_prompt=_prompt,
            )
        except Exception as exc:  # noqa: BLE001
            console.print(f"[red]Login failed:[/red] {exc}")
            raise typer.Exit(code=1) from exc

        status = agent.public_status()
        _emit(status, dump_json=dump_json, printer=print_login_success)

    asyncio.run(_run())


@app.command("register")
def register_cmd(
    code: Optional[str] = typer.Option(
        None, "--code", "-C", help="Pairing code fallback (headless / remote)"
    ),
    jwt: Optional[str] = typer.Option(
        None, "--jwt", help="User session JWT for direct POST /v1/agents/register"
    ),
    guild_id: Optional[str] = typer.Option(None, "--guild-id"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Fallback registration (prefer `cf-agent login`)."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        identity = agent.identity_store.load_identity()
        assert identity is not None

        if not code and not jwt:
            rprint("[yellow]Prefer:[/yellow] [bold]cf-agent login[/bold]")
            with spinner("Requesting connect session…"):
                begin = await agent.auth.begin_connect()
            _out(begin, dump_json=dump_json)
            raise typer.Exit(code=2)

        if code and jwt:
            rprint("[red]Use either --code or --jwt, not both[/red]")
            raise typer.Exit(code=2)

        try:
            with spinner("Registering with CultForge…"):
                if code:
                    identity = await agent.registration.claim_pairing_code(identity, code=code)
                else:
                    assert jwt is not None
                    identity = await agent.registration.register_with_jwt(
                        identity, user_jwt=jwt, guild_id=guild_id
                    )
        except Exception as exc:  # noqa: BLE001
            detail = str(exc)
            cause = exc.__cause__ or exc.__context__
            if cause is not None and str(cause) and str(cause) != detail:
                detail = f"{detail} — {cause}"
            rprint(f"[red]Registration failed:[/red] {detail}")
            raise typer.Exit(code=1) from exc

        rprint("[green]Registered with CultForge[/green]")
        _emit(agent.public_status(), dump_json=dump_json, printer=print_status)

    asyncio.run(_run())


@app.command("unregister")
def unregister_cmd(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    yes: bool = typer.Option(False, "--yes", "-y"),
) -> None:
    """Clear local registration credentials (revocable agent secret)."""
    if not yes and not confirm("Clear local CultForge registration?", default=False):
        raise typer.Abort()
    agent = create_app(str(config) if config else None)
    identity = agent.identity_store.clear_registration()
    rprint(f"[green]Cleared registration for[/green] {identity.node_id}")


@app.command("run")
def run_cmd(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    debug: bool = typer.Option(
        False,
        "--debug",
        help="Show technical logs (uvicorn access lines, logger names, etc.)",
    ),
) -> None:
    """Run the agent in the foreground."""

    async def _run() -> None:
        from cultagent.cli.runtime_ui import RuntimeHUD, print_run_banner

        agent = create_app(str(config) if config else None, debug=debug)
        print_run_banner(agent, debug=debug)
        if debug:
            await agent.run_forever()
            return

        with RuntimeHUD(agent, debug=False) as hud:

            async def _hud_tick() -> None:
                while not hud._stopped:  # noqa: SLF001
                    await asyncio.sleep(2)
                    hud.refresh()

            tick = asyncio.create_task(_hud_tick())
            try:
                await agent.run_forever()
            finally:
                tick.cancel()
                await asyncio.gather(tick, return_exceptions=True)

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        rprint("\n[dim]Stopped.[/dim]")


@app.command("exec")
def exec_cmd(
    command: str = typer.Argument(..., help="Command name, e.g. node.status"),
    params: Optional[str] = typer.Option(
        None, "--params", "-p", help="JSON object of parameters"
    ),
    resource_id: Optional[str] = typer.Option(None, "--resource", "-r"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    raw: bool = typer.Option(False, "--raw"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Dispatch a controlled agent command."""

    async def _run() -> dict[str, Any]:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        payload = json.loads(params) if params else {}
        with spinner(f"exec {command}…"):
            return await agent.dispatch(
                command,
                params=payload,
                resource_id=resource_id,
            )

    result = asyncio.run(_run())
    _out(result, raw=raw, dump_json=dump_json)
    if not result.get("ok"):
        raise typer.Exit(code=1)


@app.command("servers")
def servers_cmd(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    raw: bool = typer.Option(False, "--raw"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """List managed Minecraft servers."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        with spinner("Listing servers…"):
            result = await agent.dispatch("server.list")
        if dump_json is not None:
            dump_json_file(result, dump_json)
        if raw:
            _out(result, raw=True)
            return
        servers = (result.get("data") or {}).get("servers") or []
        if result.get("ok"):
            print_servers(servers)
        else:
            print_result(result)

    asyncio.run(_run())


@app.command("server-create")
def server_create_cmd(
    name: Optional[str] = typer.Argument(None),
    version: Optional[str] = typer.Option(None, "--mc-version"),
    loader: Optional[str] = typer.Option(
        None,
        "--loader",
        help="Server platform: vanilla|paper|purpur|folia|fabric|quilt|forge|neoforge",
    ),
    port: int = typer.Option(25565, "--port"),
    download: bool = typer.Option(
        False, "--download", help="Download/install server files for --loader"
    ),
    accept_eula: bool = typer.Option(False, "--accept-eula"),
    interactive: bool = typer.Option(
        False, "--interactive", "-i", help="Prompt for name/loader/version"
    ),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Create a local Minecraft *server* directory + catalog entry.

    To clone from the guild catalog (git-style), use::

        cf-agent server-clone ?
        cf-agent server-clone <guild_server_id>
    """

    async def _run() -> None:
        nonlocal name, version, loader, download, accept_eula
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()

        # `server-create ?` → redirect mental model to guild clone picker
        if name and name.strip() in {"?", "*", "list", "ls"}:
            rprint(
                "[dim]Listing guild servers — use[/dim] [cyan]cf-agent server-clone ?[/cyan]"
            )
            raise typer.Exit(code=await _server_clone_flow(agent, "?", dump_json=dump_json))

        if interactive or not name:
            name = name or text_input("Server name", default="My Server")
            if not name:
                console.print("[red]Name required[/red]")
                raise typer.Exit(code=2)
            loader = loader or select("Loader", list(SERVER_LOADERS), default="vanilla")
            ver = text_input("Minecraft version (blank = latest)", default="")
            version = version or (ver or None)
            if not download:
                download = confirm("Download/install now?", default=True)
            if not accept_eula:
                accept_eula = confirm("Accept Minecraft EULA?", default=True)

        assert name
        loader = loader or "vanilla"

        with spinner(f"Creating {name}…"):
            record = await agent.servers.create(
                name,
                minecraft_version=version,
                loader=loader,
                port=port,
                accept_eula=accept_eula,
                download_jar=download,
            )
            await agent.audit.record(
                operation="server.create",
                resource_id=record.server_id,
                result="ok",
                extra={"name": name},
            )
        rprint(f"[green]Created[/green] [bold]{record.name}[/bold]  [cyan]{record.server_id}[/cyan]")
        _out(record.model_dump(), dump_json=dump_json)

    asyncio.run(_run())


async def _server_clone_flow(
    agent: Any,
    target: str | None,
    *,
    dump_json: Optional[Path] = None,
    name: str | None = None,
    port: int | None = None,
    download: bool = True,
    accept_eula: bool = True,
) -> int:
    """Shared clone UX: `?` lists guild servers; otherwise clones by id."""
    from cultagent.builds import BuildsOrchestrator
    from cultagent.guild.servers_view import (
        guild_server_id,
        is_list_request,
        labeler_with_builds,
    )

    guild_attached = False
    try:
        identity = agent.identity_store.load_identity()
        guild_attached = bool(identity and identity.guild_id)
    except Exception:  # noqa: BLE001
        guild_attached = False

    builds_by_id: dict[str, dict[str, Any]] = {}
    try:
        with spinner("Fetching builds map…"):
            blist = await agent.dispatch("builds.list", params={"limit": 100})
        if blist.get("ok"):
            builds = (blist.get("data") or {}).get("builds") or []
            builds_by_id = BuildsOrchestrator.builds_by_id(builds)
    except Exception:  # noqa: BLE001
        builds_by_id = {}
    label_fn = labeler_with_builds(builds_by_id)

    if is_list_request(target):
        with spinner("Fetching guild servers…"):
            listed = await agent.dispatch("agent.servers.list", params={"limit": 100})
        if not listed.get("ok"):
            _emit(listed, dump_json=dump_json, printer=print_result)
            return 1
        servers = (listed.get("data") or {}).get("servers") or []
        if not servers:
            rprint(
                "[yellow]No guild servers[/yellow] — attach this agent to a guild "
                "and create a GuildMinecraftServer first."
            )
            if not guild_attached:
                rprint("[dim]Status shows guild: none — ask a GuildMaster to attach.[/dim]")
            return 1
        rprint("[bold]Guild servers[/bold]  (like remotes to clone)")
        for row in servers:
            rprint(f"  [cyan]{label_fn(row)}[/cyan]")
        picked = select_map(
            "Clone which guild server?",
            servers,
            label=label_fn,
        )
        if not picked:
            return 1
        target = guild_server_id(picked)
        if not target:
            rprint("[red]Selected row has no server id[/red]")
            return 1

    assert target
    with spinner(f"Cloning {target}…"):
        result = await agent.dispatch(
            "server.clone",
            params={
                "guild_server_id": target,
                "name": name,
                "port": port,
                "download": download,
                "accept_eula": accept_eula,
            },
        )
    if dump_json is not None:
        dump_json_file(result, dump_json)
    if not result.get("ok"):
        _emit(result, dump_json=None, printer=print_result)
        return 1
    data = result.get("data") or {}
    from cultagent.cli.display import capture_json_enabled, print_json_payload

    if capture_json_enabled():
        print_json_payload(result)
    elif isinstance(data, dict):
        print_server_clone(data)
    else:
        print_result(result)
    if capture_json_enabled():
        return 0
    rprint(
        f"[green]Cloned[/green]  [bold]{data.get('name')}[/bold]  "
        f"[cyan]{data.get('local_server_id')}[/cyan]  "
        f"<- [dim]{data.get('guild_server_id')}[/dim]"
    )
    if data.get("join"):
        rprint(f"[dim]Guild join[/dim]  {data['join']}")
    if data.get("chambered"):
        b = data.get("build") if isinstance(data.get("build"), dict) else {}
        bname = b.get("name") or data.get("build_id") or "build"
        rprint(
            f"[green]Chambered[/green]  [bold]{bname}[/bold]  "
            f"({data.get('loader') or '—'} {data.get('minecraft_version') or ''})  "
            f"- run [cyan]cf-agent build[/cyan] to install (shoot)"
        )
    elif not data.get("downloaded"):
        rprint("[dim]Jar not downloaded — run server-install or attach a guild build[/dim]")
    return 0


@app.command("server-clone")
def server_clone_cmd(
    target: Optional[str] = typer.Argument(
        None,
        help="Guild server id, or ? to list/pick (git-clone style)",
    ),
    name: Optional[str] = typer.Option(None, "--name", help="Local display name"),
    port: Optional[int] = typer.Option(None, "--port", help="Local listen port"),
    no_download: bool = typer.Option(
        False, "--no-download", help="Skip jar download even if version is known"
    ),
    no_eula: bool = typer.Option(False, "--no-eula", help="Do not auto-accept EULA"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Clone a guild catalog server into a local server folder (git-style).

    Examples::

        cf-agent server-clone ?
        cf-agent server-clone gsrv_…
        cf-agent server-create ?   # same picker redirect
    """

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        code = await _server_clone_flow(
            agent,
            target,
            dump_json=dump_json,
            name=name,
            port=port,
            download=not no_download,
            accept_eula=not no_eula,
        )
        if code:
            raise typer.Exit(code=code)

    asyncio.run(_run())


@app.command("server-install")
def server_install_cmd(
    server_id: Optional[str] = typer.Argument(None),
    version: Optional[str] = typer.Option(None, "--mc-version"),
    loader: Optional[str] = typer.Option(
        None,
        "--loader",
        help="Server platform: vanilla|paper|purpur|folia|fabric|quilt|forge|neoforge",
    ),
    loader_version: Optional[str] = typer.Option(
        None,
        "--loader-version",
        help="Pin Forge/NeoForge build (default: recommended/latest for MC version)",
    ),
    interactive: bool = typer.Option(False, "--interactive", "-i"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Download/install a Minecraft *server* (not a client) for a platform."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        sid = await _pick_server_id(agent, server_id)
        picked_loader = loader or "vanilla"
        if interactive or loader is None:
            choice = select("Loader", list(SERVER_LOADERS), default=picked_loader)
            if choice:
                picked_loader = choice
        with spinner(f"Installing {picked_loader}…"):
            result = await agent.servers.install_loader(
                sid,
                loader=picked_loader,
                version=version,
                loader_version=loader_version,
            )
        _out(
            result if isinstance(result, dict) else {"ok": True, "data": result},
            dump_json=dump_json,
        )

    asyncio.run(_run())


@app.command("eula-accept")
def eula_accept_cmd(
    server_id: Optional[str] = typer.Argument(None),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Accept the Minecraft EULA for a server (writes eula.txt)."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        sid = await _pick_server_id(agent, server_id)
        with spinner("Writing eula.txt…"):
            result = await agent.servers.accept_eula(sid)
        _out(
            result if isinstance(result, dict) else {"ok": True, "data": result},
            dump_json=dump_json,
        )

    asyncio.run(_run())


@app.command("server-start")
def server_start_cmd(
    server_id: Optional[str] = typer.Argument(None),
    accept_eula: bool = typer.Option(False, "--accept-eula"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Start a managed Minecraft server process."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        sid = await _pick_server_id(agent, server_id)
        with spinner(f"Starting {sid}…"):
            result = await agent.dispatch(
                "server.start",
                resource_id=sid,
                params={"accept_eula": accept_eula},
            )
        _emit(result, dump_json=dump_json, printer=print_result)
        if not result.get("ok"):
            raise typer.Exit(code=1)

    asyncio.run(_run())


@app.command("server-stop")
def server_stop_cmd(
    server_id: Optional[str] = typer.Argument(None),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Stop a managed Minecraft server process."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        sid = await _pick_server_id(agent, server_id)
        with spinner(f"Stopping {sid}…"):
            result = await agent.dispatch("server.stop", resource_id=sid)
        _emit(result, dump_json=dump_json, printer=print_result)
        if not result.get("ok"):
            raise typer.Exit(code=1)

    asyncio.run(_run())


@app.command("server-refresh")
def server_refresh_cmd(
    server_id: Optional[str] = typer.Argument(
        None,
        help="Local server id, or omit/? to pick",
    ),
    prune: bool = typer.Option(
        True,
        "--prune/--no-prune",
        help="Remove mods/packs not listed in the chambered build manifest",
    ),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Re-sync chambered build content: install missing, remove extras.

    Pulls the latest build manifest for the server's chambered build, then
    installs mods / resource packs / shader packs / datapacks and optionally
    deletes unmanaged files under those folders.
    """

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        sid = await _pick_server_id(agent, server_id)
        with install_progress_ui(f"Refreshing {sid}"):
            result = await agent.dispatch(
                "server.refresh",
                resource_id=sid,
                params={"prune": prune},
            )
        _emit(result, dump_json=dump_json, printer=print_result)
        if not result.get("ok"):
            raise typer.Exit(code=1)

    asyncio.run(_run())


@app.command("server-remove")
def server_remove_cmd(
    server_id: Optional[str] = typer.Argument(
        None,
        help="Local server id, or omit/? to pick",
    ),
    keep_files: bool = typer.Option(
        False,
        "--keep-files",
        help="Unregister from catalog only; leave the server folder on disk",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Skip confirmation prompt",
    ),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Remove a local server from the catalog (stops it, deletes folder by default).

    Examples::

        cf-agent server-remove ?
        cf-agent server-remove srv_…
        cf-agent server-remove srv_… --keep-files
        cf-agent server-remove srv_… -y
    """

    async def _run() -> None:
        from cultagent.guild.servers_view import is_list_request

        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        pick = None if (server_id is None or is_list_request(server_id)) else server_id
        sid = await _pick_server_id(agent, pick)
        record = await agent.servers.get(sid)
        if record is None:
            rprint(f"[red]Unknown server[/red]  {sid}")
            raise typer.Exit(code=1)

        action = "unregister (keep files)" if keep_files else "remove and delete files"
        if not yes:
            ok = confirm(
                f"{action}: {record.name} ({sid})?",
                default=False,
            )
            if not ok:
                rprint("[dim]Cancelled[/dim]")
                raise typer.Exit(code=1)

        with spinner(f"Removing {sid}…"):
            result = await agent.dispatch(
                "server.remove",
                resource_id=sid,
                params={"delete_files": not keep_files, "force_stop": True},
            )
        _emit(result, dump_json=dump_json, printer=print_result)
        if not result.get("ok"):
            raise typer.Exit(code=1)
        data = result.get("data") or {}
        rprint(
            f"[green]Removed[/green]  [bold]{data.get('name') or record.name}[/bold]  "
            f"[cyan]{sid}[/cyan]"
            + ("  [dim](files kept)[/dim]" if keep_files else "")
        )

    asyncio.run(_run())


@app.command("console")
def console_cmd(
    server_id: Optional[str] = typer.Argument(None),
    line: Optional[str] = typer.Option(None, "--send", "-s", help="Send a console command"),
    limit: int = typer.Option(50, "--limit", "-n"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Read recent console output or send a command."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        sid = await _pick_server_id(agent, server_id)
        sent_payload: dict[str, Any] | None = None
        if line:
            with spinner("Sending…"):
                sent = await agent.dispatch(
                    "server.console.execute",
                    resource_id=sid,
                    params={"command": line},
                )
            print_result(sent)
            sent_payload = sent
            if not sent.get("ok"):
                if dump_json is not None:
                    dump_json_file(sent, dump_json)
                raise typer.Exit(code=1)
        with spinner("Reading console…"):
            result = await agent.dispatch(
                "server.console.read",
                resource_id=sid,
                params={"limit": limit},
            )
        print_result(result)
        if dump_json is not None:
            dump_json_file(
                {"sent": sent_payload, "console": result} if sent_payload is not None else result,
                dump_json,
            )
        if not result.get("ok"):
            raise typer.Exit(code=1)

    asyncio.run(_run())


@app.command("builds")
def builds_cmd(
    q: Optional[str] = typer.Option(None, "--q", help="Search text (omit to list all)"),
    keywords: Optional[str] = typer.Option(
        None, "--keywords", "-k", help="Comma-separated catalog keywords"
    ),
    loader: Optional[str] = typer.Option(None, "--loader"),
    minecraft_version: Optional[str] = typer.Option(None, "--mc", "--minecraft-version"),
    limit: int = typer.Option(50, "--limit", "-n"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """List or search installable builds (public catalog + guild when attached)."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        params: dict[str, Any] = {"limit": limit}
        if q:
            params["q"] = q
        if keywords:
            params["keywords"] = keywords
        if loader:
            params["loader"] = loader
        if minecraft_version:
            params["minecraft_version"] = minecraft_version
        label = "Searching builds…" if q or keywords else "Fetching builds…"
        with spinner(label):
            result = await agent.dispatch("builds.list", params=params)
        _emit(result, dump_json=dump_json, printer=print_result)
        if not result.get("ok"):
            raise typer.Exit(code=1)

    asyncio.run(_run())


@app.command("agent-servers")
def agent_servers_cmd(
    limit: int = typer.Option(100, "--limit", "-n"),
    bindings: bool = typer.Option(False, "--bindings", help="Show raw binding cache instead of servers"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """List bound cloud servers (or raw bindings with --bindings)."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        if bindings:
            with spinner("Fetching bindings…"):
                result = await agent.dispatch("agent.bindings.list")
        else:
            with spinner("Fetching bound servers…"):
                result = await agent.dispatch(
                    "agent.servers.list", params={"limit": limit}
                )
        _emit(result, dump_json=dump_json, printer=print_result)
        if not result.get("ok"):
            raise typer.Exit(code=1)

    asyncio.run(_run())


@app.command("guild-server")
def guild_server_cmd(
    server_id: str = typer.Argument(..., help="Guild server id"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Show one guild server + effective join address."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        with spinner("Fetching guild server…"):
            result = await agent.dispatch(
                "guild.servers.get", params={"server_id": server_id}
            )
        _emit(result, dump_json=dump_json, printer=print_result)
        if not result.get("ok"):
            raise typer.Exit(code=1)
        data = (result.get("data") or {}).get("server") or {}
        for key in (
            "effective_address",
            "effective_port",
            "address_source",
            "configured_address",
            "tunnel_address",
            "join_address",
            "address",
            "public_join",
            "endpoint",
        ):
            if data.get(key) is not None:
                rprint(f"[dim]{key}[/dim]  [bold]{data[key]}[/bold]")

    asyncio.run(_run())


@app.command("guild-tunnel")
def guild_tunnel_cmd(
    server_id: str = typer.Argument(..., help="Guild server id"),
    workload_id: Optional[str] = typer.Option(
        None, "--workload", help="Linked workload id (awl_…)"
    ),
    address: Optional[str] = typer.Option(
        None, "--address", help="tunnel_address host (default: playit public join host)"
    ),
    port: Optional[int] = typer.Option(None, "--port", help="tunnel_port"),
    join: Optional[str] = typer.Option(
        None, "--join", help="host or host:port shortcut for tunnel_address/port"
    ),
    network_mode: Optional[str] = typer.Option(
        None, "--mode", help="network_mode (default playit, or direct with --clear)"
    ),
    clear: bool = typer.Option(
        False, "--clear", help="clear_tunnel — revert to configured address"
    ),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """POST tunnel override — tunnel_address / tunnel_port -> effective join."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        params: dict[str, Any] = {"server_id": server_id}
        if workload_id:
            params["workload_id"] = workload_id
        if address:
            params["tunnel_address"] = address
        if port is not None:
            params["tunnel_port"] = port
        if join:
            params["join"] = join
        if network_mode:
            params["network_mode"] = network_mode
        if clear:
            params["clear_tunnel"] = True
        with spinner("Reporting tunnel override to CultForge…"):
            result = await agent.dispatch("servers.tunnel", params=params)
        _emit(result, dump_json=dump_json, printer=print_result)
        if not result.get("ok"):
            raise typer.Exit(code=1)
        data = result.get("data") or {}
        if data.get("clear_tunnel"):
            rprint("[green]Cleared[/green] tunnel — address_source -> configured")
        elif data.get("tunnel_address"):
            port_s = data.get("tunnel_port")
            shown = (
                f"{data['tunnel_address']}:{port_s}"
                if port_s is not None
                else str(data["tunnel_address"])
            )
            rprint(f"[green]Reported tunnel[/green]  [bold]{shown}[/bold]")

    asyncio.run(_run())


@app.command("build")
def build_cmd(
    server_id: Optional[str] = typer.Argument(
        None,
        help="Local server id, or ? to pick (uses chambered build_id)",
    ),
    build_id: Optional[str] = typer.Option(
        None,
        "--build",
        "-b",
        help="Override chambered build id",
    ),
    new: bool = typer.Option(
        False,
        "--new",
        help="Create a new local server from a build instead of installing onto an existing one",
    ),
    name: Optional[str] = typer.Option(
        None,
        "--name",
        help="Display name for the new server (only with --new)",
    ),
    no_install: bool = typer.Option(
        False,
        "--no-install",
        help="Create server record but skip content install (only with --new)",
    ),
    optional: bool = typer.Option(False, "--optional", help="Include optional mods"),
    skip_platform: bool = typer.Option(
        False,
        "--skip-platform",
        help="Only install mods/packs — do not download Forge/vanilla server jar",
    ),
    force_platform: bool = typer.Option(
        False,
        "--force-platform",
        help="Re-run server platform installer even if libraries/jar already exist",
    ),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Install a guild build onto a local server.

    Without --new: installs onto an existing server (uses chambered build_id
    by default, or --build to override).

    With --new: provisions a brand-new local server from the build.
    """

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()

        if new:
            bid = build_id
            if not bid:
                rprint("[red]--build is required with --new[/red]")
                raise typer.Exit(code=1)
            with install_progress_ui("Provisioning build"):
                result = await agent.dispatch(
                    "builds.provision",
                    params={
                        "build_id": bid,
                        "display_name": name,
                        "install": not no_install,
                        "include_optional": optional,
                    },
                )
            _emit(result, dump_json=dump_json, printer=print_result)
            if not result.get("ok"):
                raise typer.Exit(code=1)
            return

        from cultagent.guild.servers_view import is_list_request

        pick = None if is_list_request(server_id) else server_id
        sid = await _pick_server_id(agent, pick)
        record = await agent.servers.get(sid)
        if record is None:
            rprint(f"[red]Unknown server[/red]  {sid}")
            raise typer.Exit(code=1)
        bid = build_id or record.build_id or (record.metadata or {}).get("build_id")
        if not bid:
            rprint(
                "[yellow]No chambered build[/yellow] — this server has no build_id. "
                "Pass [cyan]--build bld_…[/cyan] or clone a guild server that has one."
            )
            raise typer.Exit(code=1)
        rprint(
            f"[dim]Shooting[/dim]  [cyan]{bid}[/cyan]  ->  "
            f"[bold]{record.name}[/bold]  ({sid})"
        )
        if not skip_platform:
            rprint(
                f"[dim]Platform[/dim]  {record.loader or 'forge'}/"
                f"{record.minecraft_version or '?'}  "
                f"(jar + libraries, then content)"
            )
        with install_progress_ui(f"Installing {bid}"):
            result = await agent.dispatch(
                "builds.provision",
                resource_id=sid,
                params={
                    "build_id": str(bid),
                    "server_id": sid,
                    "include_optional": optional,
                    "install_platform": not skip_platform,
                    "force_platform": force_platform,
                    "accept_eula": True,
                },
            )
        _emit(result, dump_json=dump_json, printer=print_result)
        data = result.get("data") or {}
        install = data.get("install") if isinstance(data.get("install"), dict) else {}
        if not result.get("ok") or not install.get("ok", True):
            raise typer.Exit(code=1)
        deps = install.get("dependencies") if isinstance(install.get("dependencies"), dict) else {}
        failed_deps = [
            d for d in (deps.get("failed") or []) if isinstance(d, dict) and not d.get("skipped")
        ]
        if data.get("launch_ready"):
            if failed_deps:
                rprint(
                    f"[yellow]Built[/yellow]  [bold]{record.name}[/bold]  "
                    f"from [cyan]{bid}[/cyan]  — launch ready with "
                    f"{len(failed_deps)} dependency warning(s) "
                    f"([cyan]cf-agent server-start {sid}[/cyan])"
                )
            else:
                rprint(
                    f"[green]Built[/green]  [bold]{record.name}[/bold]  "
                    f"from [cyan]{bid}[/cyan]  — launch ready "
                    f"([cyan]cf-agent server-start {sid}[/cyan])"
                )
        else:
            rprint(
                f"[yellow]Built content[/yellow]  but platform not ready — "
                f"run [cyan]cf-agent server-install {sid} --loader "
                f"{data.get('loader') or 'forge'}[/cyan]"
            )

    asyncio.run(_run())


@app.command("build-manifest")
def build_manifest_cmd(
    build_id: str = typer.Argument(..., help="Guild build id"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Show a guild build install manifest (Rich view — not raw JSON)."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        with spinner("Fetching build manifest…"):
            result = await agent.dispatch(
                "builds.manifest",
                params={"build_id": build_id},
            )
        if dump_json is not None:
            dump_json_file(result, dump_json)
        if not result.get("ok"):
            print_result(result)
            raise typer.Exit(code=1)
        data = result.get("data")
        if isinstance(data, dict):
            print_build_manifest(data)
        else:
            print_result(result)

    asyncio.run(_run())



@app.command("mods")
def mods_cmd(
    server_id: Optional[str] = typer.Argument(None, help="Server id (for local listing)"),
    search: Optional[str] = typer.Option(None, "--search", "-s", help="Search Modrinth"),
    info: Optional[str] = typer.Option(None, "--info", help="Show Modrinth project by slug"),
    versions: Optional[str] = typer.Option(None, "--versions", help="List Modrinth versions for slug"),
    limit: int = typer.Option(20, "--limit", "-n"),
    loader: Optional[str] = typer.Option(None, "--loader"),
    game_version: Optional[str] = typer.Option(None, "--mc-version"),
    project_type: str = typer.Option("mod", "--type", help="mod|resourcepack|datapack|shader|plugin"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """List local mods, or search/inspect Modrinth with --search/--info/--versions."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()

        if search is not None:
            with spinner(f"Searching Modrinth for {search!r}…"):
                result = await agent.dispatch(
                    "server.mods.search",
                    params={
                        "query": search,
                        "limit": limit,
                        "loader": loader,
                        "game_version": game_version,
                        "project_type": project_type,
                    },
                )
            if dump_json is not None:
                dump_json_file(result, dump_json)
            if not result.get("ok"):
                print_result(result)
                raise typer.Exit(code=1)
            data = result.get("data") if isinstance(result.get("data"), dict) else {}
            print_modrinth_search(data if isinstance(data, dict) else result)
            return

        if info is not None:
            with spinner(f"Fetching {info}…"):
                result = await agent.dispatch("server.mods.project", params={"slug": info})
            if dump_json is not None:
                dump_json_file(result, dump_json)
            if not result.get("ok"):
                print_result(result)
                raise typer.Exit(code=1)
            data = result.get("data") if isinstance(result.get("data"), dict) else {}
            print_modrinth_project(data if isinstance(data, dict) else result)
            return

        if versions is not None:
            with spinner("Fetching versions…"):
                result = await agent.dispatch(
                    "server.mods.versions",
                    params={
                        "slug": versions,
                        "loader": loader or "fabric",
                        "game_version": game_version or "",
                    },
                )
            if dump_json is not None:
                dump_json_file(result, dump_json)
            if not result.get("ok"):
                print_result(result)
                raise typer.Exit(code=1)
            data = result.get("data") if isinstance(result.get("data"), dict) else {}
            print_modrinth_versions(data if isinstance(data, dict) else result)
            return

        sid = await _pick_server_id(agent, server_id)
        with spinner("Listing mods…"):
            result = await agent.dispatch("server.mods.list", resource_id=sid)
        if dump_json is not None:
            dump_json_file(result, dump_json)
        if not result.get("ok"):
            print_result(result)
            raise typer.Exit(code=1)
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        print_mods_list(data if isinstance(data, dict) else result)

    asyncio.run(_run())


@app.command("mod-install")
def mod_install_cmd(
    slug: str = typer.Argument(..., help="Modrinth project slug or id"),
    server_id: Optional[str] = typer.Argument(None),
    version_id: Optional[str] = typer.Option(None, "--version-id"),
    loader: Optional[str] = typer.Option(None, "--loader"),
    game_version: Optional[str] = typer.Option(None, "--mc-version"),
    deps: bool = typer.Option(
        True,
        "--deps/--no-deps",
        help="Install required Modrinth dependencies (default: yes)",
    ),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Install a Modrinth project onto a local server."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        sid = await _pick_server_id(agent, server_id)
        with install_progress_ui(f"Installing {slug}"):
            result = await agent.dispatch(
                "server.mods.install",
                resource_id=sid,
                params={
                    "project_id": slug,
                    "version_id": version_id,
                    "loader": loader,
                    "game_version": game_version,
                    "install_deps": deps,
                },
            )
        _emit(result, dump_json=dump_json, printer=print_result)
        if not result.get("ok"):
            raise typer.Exit(code=1)
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        if isinstance(data, dict) and data.get("ok") is False:
            raise typer.Exit(code=1)

    asyncio.run(_run())


@app.command("mod-remove")
def mod_remove_cmd(
    filename: str = typer.Argument(..., help="Jar filename in mods/"),
    server_id: Optional[str] = typer.Argument(None),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Remove a mod jar from a server."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        sid = await _pick_server_id(agent, server_id)
        with spinner(f"Removing {filename}…"):
            result = await agent.dispatch(
                "server.mods.remove",
                resource_id=sid,
                params={"filename": filename},
            )
        _emit(result, dump_json=dump_json, printer=print_result)
        if not result.get("ok"):
            raise typer.Exit(code=1)

    asyncio.run(_run())


@app.command("mod-update")
def mod_update_cmd(
    filename: Optional[str] = typer.Argument(None, help="Jar filename (or use --slug)"),
    server_id: Optional[str] = typer.Option(None, "--server"),
    slug: Optional[str] = typer.Option(None, "--slug", help="Modrinth project slug/id"),
    loader: Optional[str] = typer.Option(None, "--loader"),
    game_version: Optional[str] = typer.Option(None, "--mc-version"),
    deps: bool = typer.Option(
        True,
        "--deps/--no-deps",
        help="Install required Modrinth dependencies (default: yes)",
    ),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Update a Modrinth-tracked mod (uses local index when filename was installed via agent)."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        sid = await _pick_server_id(agent, server_id)
        if not filename and not slug:
            rprint("[red]Provide a filename and/or --slug[/red]")
            raise typer.Exit(code=2)
        with spinner("Updating mod…"):
            result = await agent.dispatch(
                "server.mods.update",
                resource_id=sid,
                params={
                    "filename": filename,
                    "project_id": slug,
                    "loader": loader,
                    "game_version": game_version,
                    "install_deps": deps,
                },
            )
        _emit(result, dump_json=dump_json, printer=print_result)
        if not result.get("ok"):
            raise typer.Exit(code=1)

    asyncio.run(_run())


@app.command("mod-resolve")
def mod_resolve_cmd(
    server_id: Optional[str] = typer.Argument(None),
    keep_client: bool = typer.Option(
        False,
        "--keep-client",
        help="Leave client-only jars enabled (HUD/sound/fog mods crash dedicated servers)",
    ),
    full: bool = typer.Option(
        False,
        "--full",
        help="Also hash-scan every jar (slow). Default reads crash-reports/ + logs/latest.log",
    ),
    crash_path: Optional[Path] = typer.Option(
        None,
        "--crash",
        help="Explicit crash report or latest.log to parse",
    ),
    loader: Optional[str] = typer.Option(None, "--loader"),
    game_version: Optional[str] = typer.Option(None, "--mc-version"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Read the latest Forge crash/log and install the mods it says are missing."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        sid = await _pick_server_id(agent, server_id)
        with spinner("Reading crash report and resolving mods…"):
            result = await agent.dispatch(
                "server.mods.resolve",
                resource_id=sid,
                params={
                    "loader": loader,
                    "game_version": game_version,
                    "disable_client_only": not keep_client,
                    "source": "both" if full else "auto",
                    "full": full,
                    "crash_path": str(crash_path) if crash_path else None,
                },
            )
        _emit(result, dump_json=dump_json, printer=print_result)
        if not result.get("ok"):
            raise typer.Exit(code=1)
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        if isinstance(data, dict) and data.get("ok") is False:
            raise typer.Exit(code=1)

    asyncio.run(_run())


@app.command("network")
def network_cmd(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Show active network provider status (direct | playit)."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        with spinner("Checking network…"):
            result = await agent.dispatch("network.status")
        if dump_json is not None:
            dump_json_file(result, dump_json)
        if not result.get("ok"):
            print_result(result)
            raise typer.Exit(code=1)
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        print_network_status(data if isinstance(data, dict) else result)

    asyncio.run(_run())


@app.command("network-use")
def network_use_cmd(
    provider: str = typer.Argument(..., help="direct | playit"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Switch active network provider."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        with spinner(f"Switching to {provider}…"):
            result = await agent.dispatch("network.use", params={"provider": provider})
        _emit(result, dump_json=dump_json, printer=print_result)
        if not result.get("ok"):
            raise typer.Exit(code=1)

    asyncio.run(_run())


@app.command("playit-setup")
def playit_setup_cmd(
    force: bool = typer.Option(False, "--force", help="Re-download even if present"),
    no_browser: bool = typer.Option(
        False,
        "--no-browser",
        help="Do not open the claim URL in a browser",
    ),
    no_wait: bool = typer.Option(
        False,
        "--no-wait",
        help="Generate claim code only; do not run claim exchange",
    ),
    timeout: int = typer.Option(
        300,
        "--timeout",
        help="Seconds to wait for browser claim approval",
    ),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Download playit, generate a claim code, open claim URL, wait for approval."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        # Install + generate + open browser first (no wait) so we can print the code.
        with spinner("Setting up playit (install + claim code)…"):
            result = await agent.dispatch(
                "playit.setup",
                params={
                    "force": force,
                    "open_browser": not no_browser,
                    "wait_exchange": False,
                },
            )
        if not result.get("ok"):
            _emit(result, dump_json=dump_json, printer=print_result)
            raise typer.Exit(code=1)
        data = result.get("data") or {}
        code = data.get("claim_code")
        claim_url = data.get("claim_url") or data.get("setup_url")
        if code:
            rprint(f"[bold cyan]Claim code[/bold cyan]  [bold yellow]{code}[/bold yellow]")
        if claim_url:
            if data.get("browser_opened"):
                rprint(f"[green]Opened[/green] {claim_url}")
            else:
                rprint(f"[yellow]Open in browser:[/yellow] {claim_url}")
        rprint(
            "[dim]Browser shows “Waiting for agent…” — that agent is this terminal. "
            "Do not paste the claim URL.[/dim]"
        )

        if no_wait:
            _emit(result, dump_json=dump_json, printer=print_result)
            rprint("[dim]Later: cf-agent playit-claim[/dim]")
            return

        if code and not data.get("has_secret"):
            with spinner(
                "Waiting for playit.gg claim approval (leave the browser tab open)…"
            ):
                waited = await agent.dispatch(
                    "playit.claim.wait",
                    params={"claim_code": code, "timeout": timeout},
                )
            _emit(waited, dump_json=dump_json, printer=print_result)
            if waited.get("ok") and (waited.get("data") or {}).get("has_secret"):
                rprint("[green]Claim complete[/green] — secret stored. Next: cf-agent playit-start")
                return
            rprint(
                "[yellow]Claim not finished yet.[/yellow] Keep the tab open and run: "
                "[cyan]cf-agent playit-claim[/cyan]"
            )
            raise typer.Exit(code=1)

        _emit(result, dump_json=dump_json, printer=print_result)
        if data.get("has_secret"):
            rprint("[dim]Secret already set. Next: cf-agent playit-start (creates the tunnel)[/dim]")

    asyncio.run(_run())


@app.command("playit-claim")
def playit_claim_cmd(
    code: Optional[str] = typer.Argument(
        None, help="Claim code (default: last code from playit-setup)"
    ),
    timeout: int = typer.Option(300, "--timeout", help="Seconds to wait"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Finish a claim: run agent-side exchange while the browser claim page is open."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        rprint(
            "[dim]Leave https://playit.gg/claim/… open. Do not paste the URL as a secret.[/dim]"
        )
        with spinner("Waiting for claim approval…"):
            result = await agent.dispatch(
                "playit.claim.wait",
                params={"claim_code": code, "timeout": timeout},
            )
        _emit(result, dump_json=dump_json, printer=print_result)
        if not result.get("ok"):
            raise typer.Exit(code=1)
        rprint("[green]Claim complete[/green] — next: cf-agent playit-start")

    asyncio.run(_run())


@app.command("playit-reset")
def playit_reset_cmd(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Stop playit and clear stored secrets / claim state."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        if not confirm("Stop playit and clear the stored secret?", default=False):
            raise typer.Abort()
        with spinner("Resetting playit…"):
            result = await agent.dispatch("playit.reset")
        _emit(result, dump_json=dump_json, printer=print_result)
        if not result.get("ok"):
            raise typer.Exit(code=1)
        rprint("[green]playit reset[/green] — secret cleared. Next: cf-agent playit-setup")

    asyncio.run(_run())


@app.command("playit-secret")
def playit_secret_cmd(
    secret: Optional[str] = typer.Option(
        None,
        "--secret",
        help="Secret key (prefer --file; avoid shell history)",
    ),
    file: Optional[Path] = typer.Option(None, "--file", "-f", help="Read secret from file"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Store playit.gg agent secret key (hex from claim/secret wizard; never shown again)."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        value = secret
        if file is not None:
            value = file.read_text(encoding="utf-8").strip()
        if not value:
            value = text_input("Playit hex secret (from claim / secret wizard)")
        if not value:
            rprint("[red]Secret required[/red]")
            raise typer.Exit(code=2)
        with spinner("Saving secret…"):
            result = await agent.dispatch("playit.secret", params={"secret": value})
        _emit(result, dump_json=dump_json, printer=print_result)
        if not result.get("ok"):
            raise typer.Exit(code=1)
        rprint("[dim]Secret stored under the agent data directory (not printed).[/dim]")

    asyncio.run(_run())


@app.command("playit-start")
def playit_start_cmd(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Start playit and ensure a Minecraft Java tunnel -> local target port."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        with spinner("Starting playit + ensuring Minecraft tunnel…"):
            result = await agent.dispatch("playit.start")
        _emit(result, dump_json=dump_json, printer=print_result)
        if not result.get("ok"):
            raise typer.Exit(code=1)
        data = result.get("data") or {}
        public = data.get("public_endpoint") or data.get("public_join") or (
            data.get("tunnel") or {}
        ).get("public_endpoint") or (data.get("tunnel") or {}).get("public_join")
        if public:
            rprint(f"[green]Public join[/green]  [bold]{public}[/bold]")
        elif data.get("tunnel_error"):
            rprint(f"[yellow]Tunnel API:[/yellow] {data['tunnel_error']}")
            rprint("[dim]Retry: cf-agent playit-start[/dim]")

    asyncio.run(_run())


@app.command("playit-stop")
def playit_stop_cmd(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Stop the managed playit agent process."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        with spinner("Stopping playit…"):
            result = await agent.dispatch("playit.stop")
        _emit(result, dump_json=dump_json, printer=print_result)
        if not result.get("ok"):
            raise typer.Exit(code=1)

    asyncio.run(_run())


@app.command("playit-logs")
def playit_logs_cmd(
    limit: int = typer.Option(60, "--limit", "-n"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Show recent playit agent stdout (claim URL / tunnel hints often appear here)."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        agent.bootstrap_identity()
        result = await agent.dispatch("playit.logs", params={"limit": limit})
        if dump_json is not None:
            dump_json_file(result, dump_json)
        if not result.get("ok"):
            print_result(result)
            raise typer.Exit(code=1)
        lines = ((result.get("data") or {}) if isinstance(result.get("data"), dict) else {}).get(
            "lines"
        ) or []
        if not lines:
            rprint("[dim]No playit log lines yet — start playit first.[/dim]")
            return
        for line in lines:
            console.print(str(line))

    asyncio.run(_run())


@app.command("java")
def java_cmd(
    path: Optional[str] = typer.Option(None, "--path", help="Preferred java binary"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Detect a usable Java runtime."""
    from cultagent.servers.java import detect_java

    with spinner("Detecting Java…"):
        runtime = detect_java(path)
    if runtime is None:
        rprint("[red]No Java runtime found[/red]")
        raise typer.Exit(code=1)
    info = {"path": runtime.path, "version": runtime.version}
    _emit(info, dump_json=dump_json, printer=print_java)


@app.command("profiles")
def profiles_cmd(
    name: Optional[str] = typer.Argument(None, help="Show a single profile by name"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """List reusable server.properties profiles, or show one by name."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        params: dict[str, Any] = {}
        if name:
            params["name"] = name
        printer = print_result if name else print_profiles
        result = await agent.dispatch("config.profile.list", params=params)
        _emit(result, dump_json=dump_json, printer=printer)

    asyncio.run(_run())


@app.command("profile-capture")
def profile_capture_cmd(
    name: str = typer.Argument(..., help="Profile name"),
    server_id: Optional[str] = typer.Argument(None),
    description: Optional[str] = typer.Option(None, "--description", "-d"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Capture current server.properties into a named profile."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        sid = await _pick_server_id(agent, server_id)
        params: dict[str, Any] = {"name": name, "server_id": sid}
        if description:
            params["description"] = description
        result = await agent.dispatch(
            "config.profile.capture",
            params=params,
            resource_id=sid,
        )
        _emit(result, dump_json=dump_json, printer=print_result)

    asyncio.run(_run())


@app.command("profile-apply")
def profile_apply_cmd(
    name: str = typer.Argument(...),
    server_id: Optional[str] = typer.Argument(None),
    mode: str = typer.Option("merge", "--mode", help="merge | replace"),
    diff: bool = typer.Option(False, "--diff", help="Show diff only, do not apply"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Apply without interactive confirm"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Apply a profile to server.properties (shows diff; requires confirm).

    Use --diff to only show what would change without applying.
    """

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        sid = await _pick_server_id(agent, server_id)
        preview = await agent.dispatch(
            "config.profile.apply",
            params={"name": name, "server_id": sid, "mode": mode, "dry_run": True},
            resource_id=sid,
        )
        preview_data = preview.get("data") if isinstance(preview.get("data"), dict) else {}
        print_profile_diff(preview_data if isinstance(preview_data, dict) else preview)
        if diff:
            if dump_json is not None:
                dump_json_file(preview, dump_json)
            return
        changes = (preview_data or {}).get("changes") if isinstance(preview_data, dict) else {}
        if not changes:
            console.print("[dim]Nothing to apply.[/dim]")
            if dump_json is not None:
                dump_json_file(preview, dump_json)
            return
        if not yes and not confirm(f"Apply {len(changes)} change(s) to {sid}?"):
            raise typer.Abort()
        result = await agent.dispatch(
            "config.profile.apply",
            params={
                "name": name,
                "server_id": sid,
                "mode": mode,
                "confirm": True,
            },
            resource_id=sid,
        )
        _emit(result, dump_json=dump_json, printer=print_profile_diff)

    asyncio.run(_run())


@app.command("profile-delete")
def profile_delete_cmd(
    name: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", "-y"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Delete a config profile."""

    async def _run() -> None:
        if not yes and not confirm(f"Delete profile {name}?"):
            raise typer.Abort()
        agent = create_app(str(config) if config else None)
        result = await agent.dispatch("config.profile.delete", params={"name": name})
        _emit(result, dump_json=dump_json, printer=print_result)

    asyncio.run(_run())


@app.command("sidecar-list")
def sidecar_list_cmd(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """List authorized sidecar clients (tokens never shown)."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        result = await agent.dispatch("sidecar.list")
        _emit(result, dump_json=dump_json, printer=print_result)

    asyncio.run(_run())


@app.command("sidecar-issue")
def sidecar_issue_cmd(
    name: str = typer.Argument("chloe", help="Sidecar client name"),
    role: str = typer.Option("chloe", "--role"),
    actor_id: Optional[str] = typer.Option(None, "--actor-id", help="CultForge actor id"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Issue a local sidecar token (shown once). Chloe gets the chloe role only."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        params: dict[str, Any] = {"name": name, "role": role}
        if actor_id:
            params["actor_id"] = actor_id
        result = await agent.dispatch("sidecar.issue", params=params)
        _emit(result, dump_json=dump_json, printer=print_sidecar_issue)

    asyncio.run(_run())


@app.command("sidecar-revoke")
def sidecar_revoke_cmd(
    name: str = typer.Argument(...),
    yes: bool = typer.Option(False, "--yes", "-y"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Revoke a sidecar client token."""

    async def _run() -> None:
        if not yes and not confirm(f"Revoke sidecar {name}?"):
            raise typer.Abort()
        agent = create_app(str(config) if config else None)
        result = await agent.dispatch("sidecar.revoke", params={"name": name})
        _emit(result, dump_json=dump_json, printer=print_result)

    asyncio.run(_run())


@app.command("doctor")
def doctor_cmd(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Run local health / hardening checks."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        result = await agent.dispatch("node.doctor")
        _emit(result, dump_json=dump_json, printer=print_doctor)
        data = result.get("data") if isinstance(result.get("data"), dict) else {}
        if isinstance(data, dict) and not data.get("ok"):
            raise typer.Exit(code=1)

    asyncio.run(_run())


@app.command("update-check")
def update_check_cmd(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Check GitHub Releases / version feed (does not download or install)."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        with spinner("Checking for updates…"):
            result = await agent.dispatch("node.update.check")
        _emit(result, dump_json=dump_json, printer=print_result)

    asyncio.run(_run())


@app.command("update")
def update_cmd(
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Apply without confirming when an update is available",
    ),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Download and apply a newer cf-agent binary from GitHub Releases.

    Only works for frozen (Nuitka/PyInstaller) builds. Dev installs should use
    ``pip install -U`` / git pull instead.
    """

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        with spinner("Checking for updates…"):
            check = await agent.dispatch("node.update.check")
        _emit(check, dump_json=None, printer=print_result)
        data = (check.get("data") or check) if isinstance(check, dict) else {}
        if isinstance(data.get("data"), dict):
            data = data["data"]
        if not data.get("update_available"):
            console.print("[dim]Already up to date.[/dim]")
            return
        latest = data.get("latest_version") or data.get("latest") or "?"
        if not yes:
            if not typer.confirm(f"Update to {latest} now?"):
                raise typer.Exit(code=0)
        with spinner(f"Downloading and applying {latest}…"):
            result = await agent.dispatch(
                "node.update.apply",
                params={"force": False, "restart": False},
            )
        _emit(result, dump_json=dump_json, printer=print_result)
        if not result.get("ok"):
            raise typer.Exit(code=1)
        console.print(
            "[green]Update applied.[/green] Restart cf-agent to use the new binary."
        )

    asyncio.run(_run())


@app.command("cloud-health")
def cloud_health_cmd(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Ping auth / api / invite / guilds worker bases."""

    async def _run() -> None:
        agent = create_app(str(config) if config else None)
        with spinner("Pinging CultForge workers…"):
            result = await agent.cloud_client.health()
        payload = result if isinstance(result, dict) else {"data": result}
        _emit(payload, dump_json=dump_json, printer=print_health)

    asyncio.run(_run())


@app.command("cloud-manifest")
def cloud_manifest_cmd(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Fetch api…/manifest.json and check required agent routes."""

    async def _run() -> None:
        from cultagent.cloud.manifest import summarize_manifest

        agent = create_app(str(config) if config else None)
        with spinner("Fetching manifest…"):
            summary = await summarize_manifest(agent.config.cloud)
        _emit(summary, dump_json=dump_json, printer=print_manifest)
        if not summary.get("required_ok"):
            raise typer.Exit(code=1)

    asyncio.run(_run())


@service_app.command("hint")
def service_hint_cmd() -> None:
    """Show how to install as a background service on this OS."""
    rprint(service_hint())


@service_app.command("systemd")
def service_systemd_cmd(
    out: Optional[Path] = typer.Option(None, "--out", help="Write unit file here"),
) -> None:
    """Print or write a systemd unit template (Linux paths only)."""
    import platform as _platform

    unit = systemd_unit(Path(sys.executable), Path.cwd())
    if _platform.system() != "Linux":
        rprint(
            "[yellow]Note:[/yellow] systemd is Linux-only. "
            "This is a template with POSIX paths (not your Windows .exe)."
        )
    if out:
        out.write_text(unit, encoding="utf-8")
        rprint(f"[green]Wrote[/green] {out}")
    else:
        console.print(unit)


@service_app.command("launchd")
def service_launchd_cmd(
    out: Optional[Path] = typer.Option(None, "--out", help="Write plist here"),
) -> None:
    """Print or write a launchd plist template (macOS paths only)."""
    import platform as _platform

    plist = launchd_plist(Path(sys.executable), Path.cwd())
    if _platform.system() != "Darwin":
        rprint(
            "[yellow]Note:[/yellow] launchd is macOS-only. "
            "This is a template with POSIX paths (not your Windows .exe)."
        )
    if out:
        out.write_text(plist, encoding="utf-8")
        rprint(f"[green]Wrote[/green] {out}")
    else:
        console.print(plist)


@service_app.command("windows")
def service_windows_cmd(
    out: Optional[Path] = typer.Option(
        None,
        "--out",
        help="Write helpers to a file (e.g. service-windows.ps1 / notes.txt)",
    ),
    winsw: Optional[Path] = typer.Option(
        None,
        "--winsw",
        help="Also write WinSW XML only to this path (e.g. CultAgent.xml)",
    ),
) -> None:
    """Windows background helpers: WinSW XML, NSSM, and schtasks."""
    from cultagent.service import windows_winsw_xml

    python = Path(sys.executable)
    cwd = Path.cwd()
    bundle = windows_service_bundle(python, cwd)
    if winsw:
        winsw.write_text(windows_winsw_xml(python, cwd), encoding="utf-8")
        rprint(f"[green]Wrote WinSW XML[/green] {winsw}")
    if out:
        out.write_text(bundle, encoding="utf-8")
        rprint(f"[green]Wrote[/green] {out}")
    else:
        console.print(bundle)


# --- Hidden backward-compat aliases (still work; omitted from top-level help) ---


@app.command("builds-search", hidden=True)
def builds_search_alias(
    q: Optional[str] = typer.Option(None, "--q"),
    keywords: Optional[str] = typer.Option(None, "--keywords", "-k"),
    loader: Optional[str] = typer.Option(None, "--loader"),
    minecraft_version: Optional[str] = typer.Option(None, "--mc", "--minecraft-version"),
    limit: int = typer.Option(50, "--limit", "-n"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Deprecated: use `cf-agent builds --q …`."""
    builds_cmd(
        q=q,
        keywords=keywords,
        loader=loader,
        minecraft_version=minecraft_version,
        limit=limit,
        config=config,
        dump_json=dump_json,
    )


@app.command("guild-servers", hidden=True)
def guild_servers_alias(
    limit: int = typer.Option(50, "--limit", "-n"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Deprecated: use `cf-agent agent-servers`."""
    agent_servers_cmd(limit=limit, bindings=False, config=config, dump_json=dump_json)


@app.command("agent-bindings", hidden=True)
def agent_bindings_alias(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Deprecated: use `cf-agent agent-servers --bindings`."""
    agent_servers_cmd(limit=100, bindings=True, config=config, dump_json=dump_json)


@app.command("build-provision", hidden=True)
def build_provision_alias(
    build_id: str = typer.Argument(...),
    name: Optional[str] = typer.Option(None, "--name"),
    no_install: bool = typer.Option(False, "--no-install"),
    optional: bool = typer.Option(False, "--optional"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Deprecated: use `cf-agent build --new --build <id>`."""
    build_cmd(
        server_id=None,
        build_id=build_id,
        new=True,
        name=name,
        no_install=no_install,
        optional=optional,
        skip_platform=False,
        force_platform=False,
        config=config,
        dump_json=dump_json,
    )


@app.command("build-install", hidden=True)
def build_install_alias(
    build_id: str = typer.Argument(...),
    server_id: Optional[str] = typer.Argument(None),
    optional: bool = typer.Option(False, "--optional"),
    skip_platform: bool = typer.Option(False, "--skip-platform"),
    force_platform: bool = typer.Option(False, "--force-platform"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Deprecated: use `cf-agent build <server> --build <id>`."""
    build_cmd(
        server_id=server_id,
        build_id=build_id,
        new=False,
        name=None,
        no_install=False,
        optional=optional,
        skip_platform=skip_platform,
        force_platform=force_platform,
        config=config,
        dump_json=dump_json,
    )


@app.command("playit-tunnel", hidden=True)
def playit_tunnel_alias(
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Deprecated: use `cf-agent playit-start`."""
    playit_start_cmd(config=config, dump_json=dump_json)


@app.command("reset", hidden=True)
def reset_alias(
    target: str = typer.Argument(...),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Deprecated: use `cf-agent playit-reset`."""
    if target.strip().lower() != "playit":
        rprint(f"[red]Unknown reset target:[/red] {target} (try: playit)")
        raise typer.Exit(code=2)
    playit_reset_cmd(config=config, dump_json=dump_json)


@app.command("profile-show", hidden=True)
def profile_show_alias(
    name: str = typer.Argument(...),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Deprecated: use `cf-agent profiles <name>`."""
    profiles_cmd(name=name, config=config, dump_json=dump_json)


@app.command("profile-diff", hidden=True)
def profile_diff_alias(
    name: str = typer.Argument(...),
    server_id: Optional[str] = typer.Argument(None),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Deprecated: use `cf-agent profile-apply <name> --diff`."""
    profile_apply_cmd(
        name=name,
        server_id=server_id,
        mode="merge",
        diff=True,
        yes=False,
        config=config,
        dump_json=dump_json,
    )


@app.command("modrinth-search", hidden=True)
def modrinth_search_alias(
    query: str = typer.Argument(...),
    limit: int = typer.Option(20, "--limit", "-n"),
    loader: Optional[str] = typer.Option(None, "--loader"),
    game_version: Optional[str] = typer.Option(None, "--mc-version"),
    project_type: str = typer.Option("mod", "--type"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Deprecated: use `cf-agent mods --search <query>`."""
    mods_cmd(
        server_id=None,
        search=query,
        info=None,
        versions=None,
        limit=limit,
        loader=loader,
        game_version=game_version,
        project_type=project_type,
        config=config,
        dump_json=dump_json,
    )


@app.command("modrinth-info", hidden=True)
def modrinth_info_alias(
    slug: str = typer.Argument(...),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Deprecated: use `cf-agent mods --info <slug>`."""
    mods_cmd(
        server_id=None,
        search=None,
        info=slug,
        versions=None,
        limit=20,
        loader=None,
        game_version=None,
        project_type="mod",
        config=config,
        dump_json=dump_json,
    )


@app.command("modrinth-versions", hidden=True)
def modrinth_versions_alias(
    slug: str = typer.Argument(...),
    game_version: str = typer.Option(..., "--mc-version"),
    loader: str = typer.Option("fabric", "--loader"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    dump_json: Optional[Path] = _dump_opt(),
) -> None:
    """Deprecated: use `cf-agent mods --versions <slug>`."""
    mods_cmd(
        server_id=None,
        search=None,
        info=None,
        versions=slug,
        limit=20,
        loader=loader,
        game_version=game_version,
        project_type="mod",
        config=config,
        dump_json=dump_json,
    )


if __name__ == "__main__":
    app()
