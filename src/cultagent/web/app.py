"""Starlette app: Crafty-parity local panel + JSON API."""

from __future__ import annotations

import asyncio
import logging
import socket
from pathlib import Path
from typing import Any

from cultagent.app import CultAgentApp
from cultagent.files import FileManager
from cultagent.servers.install import SERVER_LOADERS
from cultagent.web import STATIC_DIR, TEMPLATES_DIR

logger = logging.getLogger("cultagent.web")


def _flat_metrics(raw: dict[str, Any]) -> dict[str, Any]:
    system = raw.get("system") if isinstance(raw.get("system"), dict) else {}
    ram = system.get("ram") if isinstance(system.get("ram"), dict) else {}
    disk = system.get("disk") if isinstance(system.get("disk"), dict) else {}
    return {
        **raw,
        "cpu_percent": system.get("cpu_percent"),
        "memory_percent": ram.get("percent"),
        "memory_used_gb": round((ram.get("total", 0) - ram.get("available", 0)) / (1024**3), 2)
        if ram
        else None,
        "memory_total_gb": round(ram.get("total", 0) / (1024**3), 2) if ram else None,
        "disk_percent": disk.get("percent"),
    }


def _detect_lan_ip() -> str | None:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        if ip and not ip.startswith("127."):
            return ip
    except Exception:  # noqa: BLE001
        return None
    return None


def _join_info(port: int, network: dict[str, Any] | None = None) -> dict[str, Any]:
    """Aternos-style join addresses for LAN + optional playit public endpoint."""
    lan_ip = _detect_lan_ip()
    public = None
    claim_url = None
    provider = "direct"
    if isinstance(network, dict):
        provider = str(network.get("active") or network.get("provider") or "direct")
        public = (
            network.get("public_join")
            or network.get("public_endpoint")
            or None
        )
        details = network.get("details") if isinstance(network.get("details"), dict) else {}
        claim_url = details.get("claim_url") if isinstance(details, dict) else None
        if not public and isinstance(details, dict):
            public = details.get("public_join")
            if not public:
                hints = details.get("public_hints")
                if isinstance(hints, list) and hints:
                    public = str(hints[-1])
        playit = network.get("playit") if isinstance(network.get("playit"), dict) else None
        if not public and playit:
            public = playit.get("public_join") or playit.get("public_endpoint")
            pdetails = playit.get("details") if isinstance(playit.get("details"), dict) else {}
            if not public and pdetails:
                public = pdetails.get("public_join")
            if not claim_url:
                claim_url = (pdetails or {}).get("claim_url")
            if public and provider == "direct":
                provider = "playit"
    return {
        "port": port,
        "localhost": f"localhost:{port}",
        "lan": f"{lan_ip}:{port}" if lan_ip else None,
        "lan_ip": lan_ip,
        "public": public,
        "public_join": public,
        "claim_url": claim_url,
        "provider": provider,
        "primary": public or (f"{lan_ip}:{port}" if lan_ip else f"localhost:{port}"),
    }


def _uptime_label(uptime: float | int | None) -> str:
    if uptime is None:
        return "—"
    total = int(uptime)
    days, rem = divmod(total, 86400)
    hours, rem = divmod(rem, 3600)
    mins, secs = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h {mins}m"
    if hours:
        return f"{hours}h {mins}m {secs}s"
    return f"{mins}m {secs}s"


def _status_dict(status: Any) -> dict[str, Any]:
    """Serialize ServerStatus with a plain lowercase state string."""
    data = status.model_dump() if hasattr(status, "model_dump") else dict(status)
    state = data.get("state")
    if hasattr(state, "value"):
        data["state"] = str(state.value)
    elif state is not None:
        s = str(state)
        data["state"] = s.split(".")[-1].lower() if "." in s else s.lower()
    return data


def _server_public(record: Any) -> dict[str, Any]:
    from cultagent.servers.scope import server_scope_info

    data = record.model_dump() if hasattr(record, "model_dump") else dict(record)
    data.update(server_scope_info(record))
    return data


SPA_INDEX = STATIC_DIR / "spa" / "index.html"


async def _network_safe(agent: CultAgentApp) -> dict[str, Any]:
    try:
        result = await agent.dispatch("network.status")
        if result.get("ok") and isinstance(result.get("data"), dict):
            network = dict(result["data"])
        else:
            network = {}
    except Exception as exc:  # noqa: BLE001
        network = {"status": "error", "details": {"last_error": str(exc)}}
    details = network.get("details") if isinstance(network.get("details"), dict) else {}
    if isinstance(details, dict):
        details = dict(details)
        details.pop("secret", None)
        details["has_secret"] = bool(details.get("has_secret"))
        network["details"] = details
    return network


async def _server_rows(agent: CultAgentApp) -> list[dict[str, Any]]:
    from cultagent.servers.scope import server_scope_info

    rows: list[dict[str, Any]] = []
    for record in await agent.servers.list_servers():
        status = await agent.servers.status(record.server_id)
        rows.append({"server": record, "status": status, **server_scope_info(record)})
    return rows


def create_web_app(agent: CultAgentApp):
    from starlette.applications import Starlette
    from starlette.requests import Request
    from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse
    from starlette.routing import Mount, Route, WebSocketRoute
    from starlette.staticfiles import StaticFiles
    from starlette.templating import Jinja2Templates
    from starlette.websockets import WebSocket, WebSocketDisconnect

    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    def render(request: Request, name: str, context: dict[str, Any] | None = None) -> HTMLResponse:
        ctx = {"nav": None, "tab": None, "server": None}
        if context:
            ctx.update(context)
        return templates.TemplateResponse(request, name, ctx)

    async def require_server(server_id: str):
        record = await agent.servers.get(server_id)
        if record is None:
            return None
        status = await agent.servers.status(server_id)
        return record, status

    # --- Pages ---

    async def root(_: Request) -> RedirectResponse:
        return RedirectResponse("/panel/dashboard")

    async def spa_index(_: Request) -> HTMLResponse:
        """Serve the React panel shell (Dashboard / Servers / Network / Builds / Overview)."""
        if not SPA_INDEX.is_file():
            return HTMLResponse(
                "<h1>Panel SPA not built</h1>"
                "<p>Run <code>cd panel-ui &amp;&amp; npm run build</code>.</p>",
                status_code=503,
            )
        return HTMLResponse(
            SPA_INDEX.read_text(encoding="utf-8"),
            media_type="text/html",
        )

    async def dashboard(request: Request) -> HTMLResponse:
        # React SPA owns core routes when built; fall back to Jinja otherwise.
        if SPA_INDEX.is_file():
            return await spa_index(request)
        rows = await _server_rows(agent)
        metrics = _flat_metrics(await agent.metrics.collect())
        identity = agent.identity_store.export_public()
        network = await _network_safe(agent)
        stats = {
            "total": len(rows),
            "running": sum(1 for r in rows if r["status"].state.value == "running"),
            "stopped": sum(1 for r in rows if r["status"].state.value == "stopped"),
            "crashed": sum(1 for r in rows if r["status"].state.value == "crashed"),
        }
        primary = None
        join = None
        if rows:
            # Prefer a running server, else first configured.
            primary = next(
                (r for r in rows if r["status"].state.value == "running"),
                rows[0],
            )
            join = _join_info(int(primary["server"].port), network)
        return render(
            request,
            "dashboard.html",
            {
                "nav": "dashboard",
                "servers": rows,
                "metrics": metrics,
                "identity": identity,
                "server_stats": stats,
                "primary": primary,
                "join": join,
                "network": network,
            },
        )

    async def servers_page(request: Request) -> HTMLResponse:
        if SPA_INDEX.is_file():
            return await spa_index(request)
        return render(
            request,
            "servers.html",
            {"nav": "servers", "servers": await _server_rows(agent)},
        )

    async def server_new(request: Request) -> HTMLResponse:
        if SPA_INDEX.is_file():
            return await spa_index(request)
        return render(
            request,
            "server_create.html",
            {"nav": "new", "loaders": SERVER_LOADERS},
        )

    async def server_overview(request: Request) -> HTMLResponse:
        if SPA_INDEX.is_file():
            return await spa_index(request)
        sid = request.path_params["server_id"]
        found = await require_server(sid)
        if not found:
            return HTMLResponse("Server not found", status_code=404)
        record, status = found
        metrics = _flat_metrics(await agent.metrics.collect())
        console = await agent.servers.console_read(sid, limit=40)
        mods = await agent.content.list_installed_mods(record.path)
        backups = agent.backups.list_backups(sid)[:5]
        network = await _network_safe(agent)
        join = _join_info(int(record.port), network)
        from cultagent.servers.scope import server_scope_info

        scope_ctx = server_scope_info(record)
        return render(
            request,
            "server/overview.html",
            {
                "nav": "servers",
                "tab": "overview",
                "server": record,
                **scope_ctx,
                "status": status,
                "metrics": metrics,
                "console_lines": console.get("lines") or [],
                "mod_count": len(mods),
                "backups": backups,
                "uptime_label": _uptime_label(status.uptime_seconds),
                "join": join,
                "network": network,
            },
        )

    async def server_console(request: Request) -> HTMLResponse:
        if SPA_INDEX.is_file():
            return await spa_index(request)
        sid = request.path_params["server_id"]
        found = await require_server(sid)
        if not found:
            return HTMLResponse("Server not found", status_code=404)
        record, status = found
        return render(
            request,
            "server/console.html",
            {"nav": "servers", "tab": "console", "server": record, "status": status},
        )

    async def server_files(request: Request) -> HTMLResponse:
        if SPA_INDEX.is_file():
            return await spa_index(request)
        sid = request.path_params["server_id"]
        found = await require_server(sid)
        if not found:
            return HTMLResponse("Server not found", status_code=404)
        record, status = found
        return render(
            request,
            "server/files.html",
            {"nav": "servers", "tab": "files", "server": record, "status": status},
        )

    async def server_config(request: Request) -> HTMLResponse:
        if SPA_INDEX.is_file():
            return await spa_index(request)
        from cultagent.config import parse_server_properties, structured_view

        sid = request.path_params["server_id"]
        found = await require_server(sid)
        if not found:
            return HTMLResponse("Server not found", status_code=404)
        record, status = found
        props = Path(record.path) / "server.properties"
        raw = props.read_text(encoding="utf-8") if props.is_file() else ""
        structured = structured_view(parse_server_properties(raw)) if raw else {}
        return render(
            request,
            "server/config.html",
            {
                "nav": "servers",
                "tab": "config",
                "server": record,
                "status": status,
                "raw": raw,
                "structured": structured,
            },
        )

    async def server_backups(request: Request) -> HTMLResponse:
        if SPA_INDEX.is_file():
            return await spa_index(request)
        sid = request.path_params["server_id"]
        found = await require_server(sid)
        if not found:
            return HTMLResponse("Server not found", status_code=404)
        record, status = found
        return render(
            request,
            "server/backups.html",
            {
                "nav": "servers",
                "tab": "backups",
                "server": record,
                "status": status,
                "backups": agent.backups.list_backups(sid),
            },
        )

    async def server_mods(request: Request) -> HTMLResponse:
        if SPA_INDEX.is_file():
            return await spa_index(request)
        sid = request.path_params["server_id"]
        found = await require_server(sid)
        if not found:
            return HTMLResponse("Server not found", status_code=404)
        record, status = found
        mods = await agent.content.list_installed_mods(record.path)
        return render(
            request,
            "server/mods.html",
            {
                "nav": "servers",
                "tab": "mods",
                "server": record,
                "status": status,
                "mods": mods,
            },
        )

    async def server_metrics(request: Request) -> HTMLResponse:
        if SPA_INDEX.is_file():
            return await spa_index(request)
        sid = request.path_params["server_id"]
        found = await require_server(sid)
        if not found:
            return HTMLResponse("Server not found", status_code=404)
        record, status = found
        metrics = _flat_metrics(await agent.metrics.collect())
        return render(
            request,
            "server/metrics.html",
            {
                "nav": "servers",
                "tab": "metrics",
                "server": record,
                "status": status,
                "metrics": metrics,
            },
        )

    async def server_admin(request: Request) -> HTMLResponse:
        if SPA_INDEX.is_file():
            return await spa_index(request)
        sid = request.path_params["server_id"]
        found = await require_server(sid)
        if not found:
            return HTMLResponse("Server not found", status_code=404)
        record, status = found
        return render(
            request,
            "server/admin.html",
            {
                "nav": "servers",
                "tab": "admin",
                "server": record,
                "status": status,
                "server_dump": record.model_dump(mode="json"),
            },
        )

    async def server_tuner(request: Request) -> HTMLResponse:
        if SPA_INDEX.is_file():
            return await spa_index(request)
        sid = request.path_params["server_id"]
        found = await require_server(sid)
        if not found:
            return HTMLResponse("Server not found", status_code=404)
        record, status = found
        return render(
            request,
            "server/admin.html",
            {
                "nav": "servers",
                "tab": "tuner",
                "server": record,
                "status": status,
                "server_dump": record.model_dump(mode="json"),
            },
        )

    async def system_page(request: Request) -> HTMLResponse:
        if SPA_INDEX.is_file():
            return await spa_index(request)
        return render(
            request,
            "system.html",
            {"nav": "system", "metrics": _flat_metrics(await agent.metrics.collect())},
        )

    async def network_page(request: Request) -> HTMLResponse:
        if SPA_INDEX.is_file():
            return await spa_index(request)
        network = await _network_safe(agent)
        return render(
            request,
            "network.html",
            {"nav": "network", "network": network},
        )

    async def builds_page(request: Request) -> HTMLResponse:
        if SPA_INDEX.is_file():
            return await spa_index(request)
        builds: list[Any] = []
        error: str | None = None
        try:
            result = await agent.dispatch("builds.list")
            if result.get("ok"):
                data = result.get("data") if isinstance(result.get("data"), dict) else {}
                raw = data.get("builds") if isinstance(data, dict) else None
                if isinstance(raw, list):
                    builds = [b for b in raw if isinstance(b, dict)]
            else:
                error = str(result.get("error") or "Could not list builds")
        except Exception as exc:  # noqa: BLE001
            error = str(exc)
        return render(
            request,
            "builds.html",
            {"nav": "builds", "builds": builds, "error": error},
        )

    async def api_network(_: Request) -> JSONResponse:
        network = await _network_safe(agent)
        return JSONResponse({"ok": True, "network": network})

    async def api_builds(_: Request) -> JSONResponse:
        try:
            result = await agent.dispatch("builds.list")
            if not result.get("ok"):
                err = str(result.get("error") or "Could not list builds")
                needs_login = "not registered" in err.lower() or "login" in err.lower()
                # Soft-fail so the SPA can show an empty/onboarding state instead of a red 404.
                return JSONResponse(
                    {
                        "ok": True,
                        "builds": [],
                        "warning": err,
                        "needs_login": needs_login,
                    }
                )
            data = result.get("data") if isinstance(result.get("data"), dict) else {}
            raw = data.get("builds") if isinstance(data, dict) else None
            builds = [b for b in raw if isinstance(b, dict)] if isinstance(raw, list) else []
            return JSONResponse({"ok": True, "builds": builds})
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
            needs_login = "not registered" in err.lower() or "login" in err.lower()
            return JSONResponse(
                {
                    "ok": True,
                    "builds": [],
                    "warning": err,
                    "needs_login": needs_login,
                }
            )

    async def api_cloud_health(_: Request) -> JSONResponse:
        try:
            services = await agent.cloud_client.health()
            return JSONResponse({"ok": True, "services": services})
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(
                {"ok": True, "services": {}, "warning": str(exc)}
            )

    async def api_cloud_manifest(_: Request) -> JSONResponse:
        try:
            from cultagent.cloud.manifest import summarize_manifest

            summary = await summarize_manifest(agent.config.cloud)
            return JSONResponse({"ok": True, **summary})
        except Exception as exc:  # noqa: BLE001
            return JSONResponse(
                {
                    "ok": False,
                    "error": str(exc),
                    "required_ok": False,
                    "services": {
                        "api": getattr(agent.config.cloud, "api_base", None),
                        "auth": getattr(agent.config.cloud, "auth_base", None),
                        "invite": getattr(agent.config.cloud, "invite_base", None),
                        "guilds": getattr(agent.config.cloud, "guilds_base", None),
                    },
                },
                status_code=200,
            )

    async def api_dashboard(_: Request) -> JSONResponse:
        """Soft-fail aggregate for the SPA home strip."""
        status = agent.public_status()
        identity = status.get("identity") if isinstance(status.get("identity"), dict) else {}
        guild_id = identity.get("guild_id") if isinstance(identity, dict) else None

        cloud_health: dict[str, Any] | None = None
        cloud_warning: str | None = None
        try:
            cloud_health = await agent.cloud_client.health()
        except Exception as exc:  # noqa: BLE001
            cloud_warning = str(exc)

        guild_summary: dict[str, Any] = {
            "attached": bool(guild_id),
            "guild_id": guild_id,
            "server_count": 0,
            "warning": None,
            "needs_login": False,
        }
        try:
            listed = await agent.dispatch("agent.servers.list", params={"limit": 100})
            if listed.get("ok"):
                data = listed.get("data") if isinstance(listed.get("data"), dict) else {}
                servers = data.get("servers") if isinstance(data, dict) else None
                guild_summary["server_count"] = (
                    len(servers) if isinstance(servers, list) else 0
                )
            else:
                err = str(listed.get("error") or "Could not list guild servers")
                guild_summary["warning"] = err
                guild_summary["needs_login"] = (
                    "not registered" in err.lower() or "login" in err.lower()
                )
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
            guild_summary["warning"] = err
            guild_summary["needs_login"] = (
                "not registered" in err.lower() or "login" in err.lower()
            )

        builds_summary: dict[str, Any] = {
            "count": 0,
            "warning": None,
            "needs_login": False,
        }
        try:
            blist = await agent.dispatch("builds.list", params={"limit": 100})
            if blist.get("ok"):
                data = blist.get("data") if isinstance(blist.get("data"), dict) else {}
                builds = data.get("builds") if isinstance(data, dict) else None
                builds_summary["count"] = len(builds) if isinstance(builds, list) else 0
            else:
                err = str(blist.get("error") or "Could not list builds")
                builds_summary["warning"] = err
                builds_summary["needs_login"] = (
                    "not registered" in err.lower() or "login" in err.lower()
                )
        except Exception as exc:  # noqa: BLE001
            err = str(exc)
            builds_summary["warning"] = err
            builds_summary["needs_login"] = (
                "not registered" in err.lower() or "login" in err.lower()
            )

        java_info: dict[str, Any] = {"ok": False, "path": None, "version": None}
        try:
            from cultagent.servers.java import detect_java

            runtime = detect_java(getattr(agent.config.servers, "java_path", None) or None)
            if runtime is not None:
                java_info = {
                    "ok": True,
                    "path": runtime.path,
                    "version": runtime.version,
                }
        except Exception:  # noqa: BLE001
            pass

        local_count = 0
        try:
            local_count = len(await agent.servers.list_servers())
        except Exception:  # noqa: BLE001
            local_count = 0

        return JSONResponse(
            {
                "ok": True,
                "status": status,
                "cloud_health": cloud_health,
                "cloud_warning": cloud_warning,
                "guild": guild_summary,
                "builds": builds_summary,
                "java": java_info,
                "local_server_count": local_count,
            }
        )

    async def cloud_page(request: Request) -> HTMLResponse:
        if SPA_INDEX.is_file():
            return await spa_index(request)
        status = agent.public_status()
        return render(
            request,
            "cloud.html",
            {
                "nav": "cloud",
                "identity": status.get("identity") or {},
                "cloud": status.get("cloud") or {},
            },
        )

    async def profiles_page(request: Request) -> HTMLResponse:
        if SPA_INDEX.is_file():
            return await spa_index(request)
        profiles: list[Any] = []
        try:
            result = await agent.dispatch("config.profile.list")
            if result.get("ok") and isinstance(result.get("data"), dict):
                raw = result["data"].get("profiles")
                if isinstance(raw, list):
                    profiles = [p for p in raw if isinstance(p, dict)]
        except Exception:  # noqa: BLE001
            profiles = []
        servers = await agent.servers.list_servers()
        return render(
            request,
            "profiles.html",
            {
                "nav": "profiles",
                "profiles": profiles,
                "servers": servers,
            },
        )

    # --- JSON API ---

    def _json(payload: Any, *, status_code: int = 200) -> JSONResponse:
        return JSONResponse(agent.visibility.redact_secrets(payload), status_code=status_code)

    async def health(_: Request) -> JSONResponse:
        return _json({"ok": True, "service": "cultagent-local"})

    async def api_status(_: Request) -> JSONResponse:
        return _json(agent.public_status())

    async def api_metrics(_: Request) -> JSONResponse:
        return _json(await agent.metrics.collect())

    async def api_commands(_: Request) -> JSONResponse:
        return _json({"commands": agent.commands.list_commands()})

    async def api_command(request: Request) -> JSONResponse:
        body = await request.json()
        name = body.get("command")
        if not name:
            return _json({"ok": False, "error": "command required"}, status_code=400)
        result = await agent.dispatch(
            name,
            params=body.get("params") or {},
            actor_id=body.get("actor_id"),
            resource_id=body.get("resource_id"),
        )
        return _json(result, status_code=200 if result.get("ok") else 400)

    async def api_sidecar_command(request: Request) -> JSONResponse:
        """Chloe / sidecar entry — Bearer token + local RBAC (no privilege bypass)."""
        auth = request.headers.get("authorization") or ""
        token = auth[7:].strip() if auth.lower().startswith("bearer ") else ""
        client = agent.sidecars.verify(token)
        if client is None:
            return _json({"ok": False, "error": "unauthorized_sidecar"}, status_code=401)
        body = await request.json()
        name = body.get("command")
        if not name:
            return _json({"ok": False, "error": "command required"}, status_code=400)
        result = await agent.dispatch(
            str(name),
            params=body.get("params") or {},
            actor_id=str(client.get("actor_id") or ""),
            resource_id=body.get("resource_id"),
            enforce_local=True,
        )
        return _json(result, status_code=200 if result.get("ok") else 400)

    async def api_servers_list(_: Request) -> JSONResponse:
        rows = await _server_rows(agent)
        return JSONResponse(
            {
                "ok": True,
                "servers": [
                    {
                        "server": _server_public(r["server"]),
                        "status": _status_dict(r["status"]),
                    }
                    for r in rows
                ],
            }
        )

    async def api_servers_create(request: Request) -> JSONResponse:
        body = await request.json()
        name = body.get("name")
        if not name:
            return JSONResponse({"ok": False, "error": "name required"}, status_code=400)
        try:
            record = await agent.servers.create(
                str(name),
                minecraft_version=body.get("minecraft_version"),
                loader=body.get("loader") or "vanilla",
                port=int(body.get("port") or 25565),
                accept_eula=bool(body.get("accept_eula")),
                download_jar=bool(body.get("download")),
            )
            if body.get("auto_start"):
                record.auto_start = True
                await agent.servers.update_record(record)
            return JSONResponse({"ok": True, "data": record.model_dump()})
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    async def api_server_detail(request: Request) -> JSONResponse:
        sid = request.path_params["server_id"]
        found = await require_server(sid)
        if not found:
            return JSONResponse({"ok": False, "error": "unknown server"}, status_code=404)
        record, status = found
        network = await _network_safe(agent)
        join = _join_info(int(record.port), network)
        try:
            mods = await agent.content.list_installed_mods(record.path)
            mod_count = len(mods)
        except Exception:  # noqa: BLE001
            mod_count = 0
        players: list[dict[str, Any]] = []
        try:
            from cultagent.cloud.presence import get_presence_tracker

            snap = get_presence_tracker().snapshot(sid)
            players = list(snap.get("players") or [])
        except Exception:  # noqa: BLE001
            players = []
        return JSONResponse(
            {
                "ok": True,
                "server": _server_public(record),
                "status": _status_dict(status),
                "join": join,
                "uptime_label": _uptime_label(status.uptime_seconds),
                "mod_count": mod_count,
                "players": players,
            }
        )

    async def api_server_action(request: Request) -> JSONResponse:
        sid = request.path_params["server_id"]
        action = request.path_params["action"]
        mapping = {
            "start": "server.start",
            "stop": "server.stop",
            "restart": "server.restart",
        }
        command = mapping.get(action)
        if not command:
            return JSONResponse({"ok": False, "error": "unknown action"}, status_code=404)
        body: dict[str, Any] = {}
        try:
            body = await request.json()
        except Exception:  # noqa: BLE001
            body = {}
        result = await agent.dispatch(
            command, params=body if isinstance(body, dict) else {}, resource_id=sid
        )
        return JSONResponse(result, status_code=200 if result.get("ok") else 400)

    async def api_server_console(request: Request) -> JSONResponse:
        sid = request.path_params["server_id"]
        if request.method == "GET":
            after = int(request.query_params.get("after_seq") or 0)
            limit = int(request.query_params.get("limit") or 200)
            result = await agent.dispatch(
                "server.console.read",
                params={"after_seq": after, "limit": limit},
                resource_id=sid,
            )
            return JSONResponse(result)
        body = await request.json()
        result = await agent.dispatch(
            "server.console.execute",
            params={"command": body.get("command") or body.get("line")},
            resource_id=sid,
        )
        return JSONResponse(result, status_code=200 if result.get("ok") else 400)

    async def api_server_backups(request: Request) -> JSONResponse:
        sid = request.path_params["server_id"]
        if request.method == "GET":
            return JSONResponse({"ok": True, "backups": agent.backups.list_backups(sid)})
        result = await agent.dispatch("server.backup.create", resource_id=sid)
        return JSONResponse(result, status_code=200 if result.get("ok") else 400)

    async def api_server_mods(request: Request) -> JSONResponse:
        sid = request.path_params["server_id"]
        result = await agent.dispatch("server.mods.list", resource_id=sid)
        return JSONResponse(result)

    async def api_server_eula(request: Request) -> JSONResponse:
        sid = request.path_params["server_id"]
        try:
            data = await agent.servers.accept_eula(sid)
            return JSONResponse({"ok": True, "data": data})
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    async def api_server_config(request: Request) -> JSONResponse:
        from cultagent.config import (
            field_schema_payload,
            parse_server_properties,
            render_server_properties,
            structured_view,
        )

        sid = request.path_params["server_id"]
        record = await agent.servers.get(sid)
        if record is None:
            return JSONResponse({"ok": False, "error": "unknown server"}, status_code=404)
        props = Path(record.path) / "server.properties"
        if request.method == "GET":
            raw = props.read_text(encoding="utf-8") if props.is_file() else ""
            properties = parse_server_properties(raw) if raw else {}
            fm = FileManager(Path(record.path))
            worlds = fm.list_worlds()
            active = str(properties.get("level-name") or "world")
            return JSONResponse(
                {
                    "ok": True,
                    "raw": raw,
                    "properties": properties,
                    "structured": structured_view(properties),
                    "schema": field_schema_payload(),
                    "worlds": worlds,
                    "active_world": active,
                }
            )
        body = await request.json()
        if "values" in body and isinstance(body.get("values"), dict):
            from cultagent.config.live_apply import apply_config_to_running

            current = (
                parse_server_properties(props.read_text(encoding="utf-8"))
                if props.is_file()
                else {}
            )
            updates = {str(k): str(v) for k, v in body["values"].items()}
            merged = {**current, **updates}
            # Ensure chosen world folder exists so Files / picker see it immediately
            level_name = str(merged.get("level-name") or "").strip()
            if level_name and "/" not in level_name and "\\" not in level_name:
                try:
                    (Path(record.path) / level_name).mkdir(parents=True, exist_ok=True)
                except OSError:
                    pass
            props.write_text(render_server_properties(merged), encoding="utf-8")
            auto_restart = body.get("auto_restart", True)
            live = await apply_config_to_running(
                agent, sid, updates, auto_restart=bool(auto_restart)
            )
            fm = FileManager(Path(record.path))
            return JSONResponse(
                {
                    "ok": True,
                    "properties": merged,
                    "structured": structured_view(merged),
                    "raw": render_server_properties(merged),
                    "worlds": fm.list_worlds(),
                    "active_world": str(merged.get("level-name") or "world"),
                    "live": live,
                    "message": live.get("message"),
                    "restarted": live.get("restarted"),
                    "needs_restart": live.get("needs_restart") or [],
                    "applied_keys": live.get("applied_keys") or [],
                }
            )
        raw = body.get("raw")
        if raw is None:
            return JSONResponse(
                {"ok": False, "error": "values object or raw string required"},
                status_code=400,
            )
        props.write_text(str(raw), encoding="utf-8")
        properties = parse_server_properties(str(raw))
        live: dict[str, Any] = {
            "message": "Saved raw server.properties",
            "restarted": False,
        }
        if agent.servers.is_process_running(sid) and bool(body.get("auto_restart", True)):
            try:
                await agent.servers.restart(sid)
                live = {
                    "message": "Saved raw properties and restarted so they take effect",
                    "restarted": True,
                }
            except Exception as exc:  # noqa: BLE001
                live = {
                    "message": f"Saved raw file; restart manually ({exc})",
                    "restarted": False,
                    "restart_error": str(exc),
                }
        return JSONResponse(
            {
                "ok": True,
                "properties": properties,
                "structured": structured_view(properties),
                "raw": str(raw),
                "live": live,
                "message": live.get("message"),
                "restarted": live.get("restarted"),
            }
        )

    async def api_server_jvm(request: Request) -> JSONResponse:
        from cultagent.jvm import (
            apply_jvm_args,
            field_schema_payload,
            parse_jvm_args,
            render_jvm_args,
            resolve_jvm_args,
        )

        sid = request.path_params["server_id"]
        record = await agent.servers.get(sid)
        if record is None:
            return JSONResponse({"ok": False, "error": "unknown server"}, status_code=404)

        if request.method == "GET":
            raw, source = resolve_jvm_args(record)
            values = parse_jvm_args(raw)
            return JSONResponse(
                {
                    "ok": True,
                    "raw": raw,
                    "source": source,
                    "values": values,
                    "schema": field_schema_payload(),
                    "preview": f"java {raw} -jar {record.executable or 'server.jar'} nogui",
                }
            )

        body = await request.json()
        if "values" in body and isinstance(body.get("values"), dict):
            rendered = render_jvm_args(body["values"])
        elif body.get("raw") is not None:
            rendered = str(body.get("raw") or "").strip() or "-Xms1G -Xmx2G"
        elif body.get("preset"):
            schema = field_schema_payload()
            preset_id = str(body["preset"])
            match = next((p for p in schema["presets"] if p["id"] == preset_id), None)
            if match is None:
                return JSONResponse(
                    {"ok": False, "error": f"unknown preset: {preset_id}"},
                    status_code=400,
                )
            rendered = render_jvm_args(match["values"])
        else:
            return JSONResponse(
                {"ok": False, "error": "values, raw, or preset required"},
                status_code=400,
            )

        record = apply_jvm_args(record, rendered)
        await agent.servers.update_record(record)
        raw, source = resolve_jvm_args(record)
        return JSONResponse(
            {
                "ok": True,
                "raw": raw,
                "source": source,
                "values": parse_jvm_args(raw),
                "preview": f"java {raw} -jar {record.executable or 'server.jar'} nogui",
            }
        )

    async def api_server_worlds(request: Request) -> JSONResponse:
        sid = request.path_params["server_id"]
        record = await agent.servers.get(sid)
        if record is None:
            return JSONResponse({"ok": False, "error": "unknown server"}, status_code=404)
        from cultagent.config import parse_server_properties

        fm = FileManager(Path(record.path))
        props_path = Path(record.path) / "server.properties"
        props = (
            parse_server_properties(props_path.read_text(encoding="utf-8"))
            if props_path.is_file()
            else {}
        )
        active = str(props.get("level-name") or "world")
        worlds = fm.list_worlds()
        # Ensure the configured name appears even if the folder does not exist yet
        names = {w["name"] for w in worlds}
        if active and active not in names:
            worlds.insert(
                0,
                {
                    "name": active,
                    "path": active,
                    "has_level_dat": False,
                    "size": 0,
                    "pending": True,
                },
            )
        if request.method == "GET":
            return JSONResponse(
                {"ok": True, "worlds": worlds, "active_world": active, "properties": props}
            )
        body = await request.json()
        name = str(body.get("level_name") or body.get("name") or "").strip()
        if not name or "/" in name or "\\" in name or name in {".", ".."}:
            return JSONResponse({"ok": False, "error": "invalid world name"}, status_code=400)
        # Reject path traversal / reserved
        if any(ch in name for ch in '<>:"|?*'):
            return JSONResponse({"ok": False, "error": "invalid characters in world name"}, status_code=400)
        props["level-name"] = name
        from cultagent.config import render_server_properties

        props_path.write_text(render_server_properties(props), encoding="utf-8")
        # Optionally create empty folder so Files shows it immediately
        if body.get("create_folder", True):
            (Path(record.path) / name).mkdir(parents=True, exist_ok=True)
        worlds = fm.list_worlds()
        names = {w["name"] for w in worlds}
        if name not in names:
            worlds.insert(
                0,
                {"name": name, "path": name, "has_level_dat": False, "size": 0, "pending": True},
            )
        return JSONResponse({"ok": True, "active_world": name, "worlds": worlds, "properties": props})

    async def api_server_files(request: Request) -> JSONResponse:
        sid = request.path_params["server_id"]
        record = await agent.servers.get(sid)
        if record is None:
            return JSONResponse({"ok": False, "error": "unknown server"}, status_code=404)
        fm = FileManager(Path(record.path))
        rel = request.query_params.get("path") or "."
        try:
            return JSONResponse({"ok": True, "items": fm.list_dir(rel)})
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    async def api_server_file_content(request: Request) -> JSONResponse:
        sid = request.path_params["server_id"]
        record = await agent.servers.get(sid)
        if record is None:
            return JSONResponse({"ok": False, "error": "unknown server"}, status_code=404)
        fm = FileManager(Path(record.path))
        if request.method == "GET":
            rel = request.query_params.get("path") or ""
            try:
                return JSONResponse({"ok": True, "content": fm.read_text(rel)})
            except Exception as exc:  # noqa: BLE001
                return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
        body = await request.json()
        try:
            fm.write_text(str(body.get("path") or ""), str(body.get("content") or ""))
            return JSONResponse({"ok": True})
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    async def api_server_mod_configs(request: Request) -> JSONResponse:
        """List or read/write mod config files under config/."""
        from cultagent.content.mod_config import (
            list_mod_config_files,
            read_mod_config,
            write_mod_config,
        )

        sid = request.path_params["server_id"]
        record = await agent.servers.get(sid)
        if record is None:
            return JSONResponse({"ok": False, "error": "unknown server"}, status_code=404)
        if request.method == "GET":
            rel = request.query_params.get("path")
            if rel:
                try:
                    return JSONResponse(read_mod_config(record.path, str(rel)))
                except Exception as exc:  # noqa: BLE001
                    return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)
            return JSONResponse(
                {"ok": True, "files": list_mod_config_files(record.path)}
            )
        body = await request.json()
        rel = str(body.get("path") or "")
        if not rel:
            return JSONResponse({"ok": False, "error": "path required"}, status_code=400)
        try:
            result = write_mod_config(
                record.path,
                rel,
                raw=body.get("raw") if "raw" in body else None,
                values=body.get("values") if isinstance(body.get("values"), dict) else None,
            )
            return JSONResponse(result)
        except Exception as exc:  # noqa: BLE001
            return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    async def ws_server_console(websocket: WebSocket) -> None:
        """Live console stream for the local panel (HTTP poll remains as fallback)."""
        sid = websocket.path_params["server_id"]
        record = await agent.servers.get(sid)
        if record is None:
            await websocket.close(code=4404)
            return
        await websocket.accept()
        try:
            snap = await agent.servers.console_read(sid, limit=300)
            after = int(snap.get("next_seq") or 0)
            await websocket.send_json({"type": "snapshot", **snap})
        except Exception as exc:  # noqa: BLE001
            await websocket.send_json({"type": "error", "error": str(exc)})
            await websocket.close(code=1011)
            return

        async def pump_out() -> None:
            nonlocal after
            while True:
                batch = await agent.servers.console_wait(sid, after_seq=after, timeout=20.0)
                lines = batch.get("lines") or []
                if lines:
                    after = int(batch.get("next_seq") or after)
                    await websocket.send_json({"type": "lines", **batch})
                else:
                    await websocket.send_json({"type": "ping"})

        async def pump_in() -> None:
            while True:
                raw = await websocket.receive_json()
                if not isinstance(raw, dict):
                    continue
                mtype = str(raw.get("type") or "").lower()
                if mtype == "ping":
                    await websocket.send_json({"type": "pong"})
                    continue
                # Immediate control: start over WS (stop/restart stay HTTP with UI debounce)
                if mtype == "control":
                    action = str(raw.get("action") or "").lower()
                    if action == "start":
                        try:
                            await agent.dispatch(
                                "server.start",
                                resource_id=sid,
                                params={"accept_eula": bool(raw.get("accept_eula", True))},
                            )
                            st = await agent.servers.status(sid)
                            await websocket.send_json(
                                {
                                    "type": "control_ack",
                                    "action": "start",
                                    "ok": True,
                                    "state": getattr(st.state, "value", str(st.state)),
                                }
                            )
                        except Exception as exc:  # noqa: BLE001
                            await websocket.send_json(
                                {
                                    "type": "control_ack",
                                    "action": "start",
                                    "ok": False,
                                    "error": str(exc),
                                }
                            )
                    continue
                command = raw.get("command") or raw.get("line")
                if command:
                    try:
                        await agent.servers.console_execute(sid, str(command))
                        await websocket.send_json(
                            {"type": "command_ack", "command": str(command), "ok": True}
                        )
                    except Exception as exc:  # noqa: BLE001
                        await websocket.send_json(
                            {
                                "type": "command_ack",
                                "command": str(command),
                                "ok": False,
                                "error": str(exc),
                            }
                        )

        out_task = asyncio.create_task(pump_out())
        in_task = asyncio.create_task(pump_in())
        try:
            done, pending = await asyncio.wait(
                {out_task, in_task},
                return_when=asyncio.FIRST_EXCEPTION,
            )
            for task in pending:
                task.cancel()
            for task in done:
                exc = task.exception()
                if exc and not isinstance(exc, WebSocketDisconnect):
                    raise exc
        except WebSocketDisconnect:
            pass
        except Exception:  # noqa: BLE001
            logger.debug("console ws closed for %s", sid, exc_info=True)
        finally:
            out_task.cancel()
            in_task.cancel()
            await asyncio.gather(out_task, in_task, return_exceptions=True)

    routes = [
        Route("/", root),
        Route("/panel", spa_index),
        Route("/panel/dashboard", dashboard),
        Route("/panel/servers", servers_page),
        Route("/panel/servers/new", server_new),
        Route("/panel/servers/{server_id}", server_overview),
        Route("/panel/servers/{server_id}/console", server_console),
        Route("/panel/servers/{server_id}/files", server_files),
        Route("/panel/servers/{server_id}/config", server_config),
        Route("/panel/servers/{server_id}/tuner", server_tuner),
        Route("/panel/servers/{server_id}/backups", server_backups),
        Route("/panel/servers/{server_id}/mods", server_mods),
        Route("/panel/servers/{server_id}/metrics", server_metrics),
        Route("/panel/servers/{server_id}/admin", server_admin),
        Route("/panel/system", system_page),
        Route("/panel/builds", builds_page),
        Route("/panel/network", network_page),
        Route("/panel/cloud", cloud_page),
        Route("/panel/profiles", profiles_page),
        Route("/health", health),
        Route("/v1/status", api_status),
        Route("/v1/metrics", api_metrics),
        Route("/v1/network", api_network),
        Route("/v1/builds", api_builds),
        Route("/v1/dashboard", api_dashboard),
        Route("/v1/cloud/health", api_cloud_health),
        Route("/v1/cloud/manifest", api_cloud_manifest),
        Route("/v1/commands", api_commands),
        Route("/v1/command", api_command, methods=["POST"]),
        Route("/v1/sidecar/command", api_sidecar_command, methods=["POST"]),
        Route("/v1/servers", api_servers_list, methods=["GET"]),
        Route("/v1/servers", api_servers_create, methods=["POST"]),
        Route("/v1/servers/{server_id}", api_server_detail),
        Route(
            "/v1/servers/{server_id}/console",
            api_server_console,
            methods=["GET", "POST"],
        ),
        WebSocketRoute("/ws/servers/{server_id}/console", ws_server_console),
        Route(
            "/v1/servers/{server_id}/backups",
            api_server_backups,
            methods=["GET", "POST"],
        ),
        Route("/v1/servers/{server_id}/mods", api_server_mods),
        Route("/v1/servers/{server_id}/eula", api_server_eula, methods=["POST"]),
        Route(
            "/v1/servers/{server_id}/config",
            api_server_config,
            methods=["GET", "PUT"],
        ),
        Route(
            "/v1/servers/{server_id}/worlds",
            api_server_worlds,
            methods=["GET", "PUT"],
        ),
        Route(
            "/v1/servers/{server_id}/jvm",
            api_server_jvm,
            methods=["GET", "PUT"],
        ),
        Route("/v1/servers/{server_id}/files", api_server_files),
        Route(
            "/v1/servers/{server_id}/files/content",
            api_server_file_content,
            methods=["GET", "PUT"],
        ),
        Route(
            "/v1/servers/{server_id}/mod-configs",
            api_server_mod_configs,
            methods=["GET", "PUT"],
        ),
        Route("/v1/servers/{server_id}/{action}", api_server_action, methods=["POST"]),
        Mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static"),
    ]
    return Starlette(routes=routes)


async def serve_local_api(agent: CultAgentApp) -> Any:
    try:
        import uvicorn
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("uvicorn is required for the local panel") from exc

    host = agent.config.local.bind_host
    port = agent.config.local.bind_port
    if host not in {"127.0.0.1", "localhost", "::1"}:
        logger.warning("Non-loopback bind %s — forcing 127.0.0.1", host)
        host = "127.0.0.1"

    asgi = create_web_app(agent)
    debug = bool(getattr(agent, "debug", False))
    config = uvicorn.Config(
        asgi,
        host=host,
        port=port,
        log_level="info" if debug else "warning",
        access_log=debug,
        # Don't let uvicorn reconfigure our root/cultagent loggers.
        log_config=None,
    )
    server = uvicorn.Server(config)
    logger.info("CultAgent panel on http://%s:%s/panel/dashboard", host, port)
    await server.serve()
    return server
