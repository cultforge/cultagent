"""playit.gg agent-key REST client (create/list/configure tunnels).

Auth: ``Authorization: agent-key <hex secret>`` against ``https://api.playit.gg``.
"""

from __future__ import annotations

from typing import Any

import httpx

PLAYIT_API = "https://api.playit.gg"
USER_AGENT = "CultForge-Agent/0.1 (cf-agent; +https://cultforge.com)"
DEFAULT_TUNNEL_NAME = "CultAgent Minecraft"
MINECRAFT_JAVA = "minecraft-java"


class PlayitApiError(RuntimeError):
    def __init__(self, message: str, *, path: str = "", payload: Any = None) -> None:
        super().__init__(message)
        self.path = path
        self.payload = payload


def _headers(secret: str) -> dict[str, str]:
    return {
        "Authorization": f"agent-key {secret}",
        "Content-Type": "application/json",
        "Accept": "application/json",
        "User-Agent": USER_AGENT,
    }


def _unwrap(path: str, body: dict[str, Any]) -> Any:
    status = body.get("status")
    if status == "success":
        return body.get("data")
    data = body.get("data")
    if isinstance(data, dict) and data.get("error"):
        err = data["error"]
        details = data.get("details")
        msg = f"{err}" if details is None else f"{err}: {details}"
        raise PlayitApiError(msg, path=path, payload=body)
    if isinstance(data, dict) and data.get("type") == "validation":
        raise PlayitApiError(
            str(data.get("message") or "validation error"),
            path=path,
            payload=body,
        )
    raise PlayitApiError(str(body)[:400], path=path, payload=body)


async def _post(
    client: httpx.AsyncClient,
    secret: str,
    path: str,
    payload: dict[str, Any] | None = None,
) -> Any:
    resp = await client.post(
        f"{PLAYIT_API}{path}",
        headers=_headers(secret),
        json=payload if payload is not None else {},
    )
    try:
        body = resp.json()
    except Exception as exc:  # noqa: BLE001
        raise PlayitApiError(
            f"HTTP {resp.status_code}: non-JSON response",
            path=path,
            payload=resp.text[:300],
        ) from exc
    if not isinstance(body, dict):
        raise PlayitApiError(f"unexpected response: {body!r}"[:400], path=path)
    if resp.status_code >= 400 and body.get("status") != "success":
        # Prefer structured fail/error unwrap when present.
        try:
            return _unwrap(path, body)
        except PlayitApiError:
            raise
    return _unwrap(path, body)


def agent_config_fields(*, host: str, port: int) -> dict[str, Any]:
    return {
        "fields": [
            {"name": "local_ip", "value": str(host)},
            {"name": "local_port", "value": str(int(port))},
        ]
    }


def pick_public_address(tunnel: dict[str, Any]) -> str | None:
    """Prefer hostname/SRV-style address from v1 list or legacy rundata."""
    for entry in tunnel.get("connect_addresses") or []:
        if not isinstance(entry, dict):
            continue
        value = entry.get("value")
        if isinstance(value, dict):
            addr = value.get("address")
            if addr:
                return str(addr)
        elif isinstance(value, str) and value:
            return value
    for key in ("assigned_domain", "display_address", "assigned_srv"):
        val = tunnel.get(key)
        if val:
            return str(val)
    alloc = tunnel.get("alloc")
    if isinstance(alloc, dict):
        data = alloc.get("data") if alloc.get("status") == "allocated" else None
        if isinstance(data, dict):
            domain = data.get("assigned_domain") or data.get("assigned_srv")
            if domain:
                return str(domain)
            host = data.get("ip_hostname") or data.get("tunnel_ip")
            port = data.get("port_start")
            if host and port is not None:
                return f"{host}:{port}"
    return None


def tunnel_local_port(tunnel: dict[str, Any]) -> int | None:
    origin = tunnel.get("origin")
    if isinstance(origin, dict):
        details = origin.get("details") or origin.get("data") or {}
        if isinstance(details, dict) and details.get("local_port") is not None:
            try:
                return int(details["local_port"])
            except (TypeError, ValueError):
                pass
        # v1 agent origin embeds config_data.fields
        cfg = details.get("config_data") if isinstance(details, dict) else None
        if isinstance(cfg, dict):
            for field in cfg.get("fields") or []:
                if isinstance(field, dict) and field.get("name") == "local_port":
                    try:
                        return int(field.get("value"))
                    except (TypeError, ValueError):
                        pass
    if tunnel.get("local_port") is not None:
        try:
            return int(tunnel["local_port"])
        except (TypeError, ValueError):
            pass
    for field in (tunnel.get("agent_config") or {}).get("fields") or []:
        if isinstance(field, dict) and field.get("name") == "local_port":
            try:
                return int(field.get("value"))
            except (TypeError, ValueError):
                pass
    return None


def is_minecraft_java(tunnel: dict[str, Any]) -> bool:
    return str(tunnel.get("tunnel_type") or "").lower() == MINECRAFT_JAVA


async def rundata(client: httpx.AsyncClient, secret: str) -> dict[str, Any]:
    data = await _post(client, secret, "/v1/agents/rundata", {})
    return data if isinstance(data, dict) else {}


async def list_tunnels_v1(client: httpx.AsyncClient, secret: str) -> list[dict[str, Any]]:
    data = await _post(client, secret, "/v1/tunnels/list", {})
    tunnels = (data or {}).get("tunnels") if isinstance(data, dict) else None
    return [t for t in (tunnels or []) if isinstance(t, dict)]


async def create_minecraft_java_tunnel(
    client: httpx.AsyncClient,
    secret: str,
    *,
    agent_id: str,
    host: str,
    port: int,
    name: str = DEFAULT_TUNNEL_NAME,
) -> str:
    body = {
        "name": name,
        "protocol": {"type": "tunnel-type", "details": MINECRAFT_JAVA},
        "origin": {
            "type": "agent",
            "data": {
                "agent_id": agent_id,
                "config": agent_config_fields(host=host, port=port),
            },
        },
        "endpoint": {"type": "region", "details": {"region": "global"}},
        "enabled": True,
    }
    data = await _post(client, secret, "/v1/tunnels/create", body)
    if isinstance(data, dict) and data.get("id"):
        return str(data["id"])
    raise PlayitApiError("tunnel create returned no id", path="/v1/tunnels/create", payload=data)


async def configure_tunnel_origin(
    client: httpx.AsyncClient,
    secret: str,
    *,
    tunnel_id: str,
    host: str,
    port: int,
) -> None:
    await _post(
        client,
        secret,
        "/v1/tunnels/config",
        {
            "tunnel_id": tunnel_id,
            "new_config": agent_config_fields(host=host, port=port),
        },
    )


async def fetch_public_join(
    secret: str,
    *,
    tunnel_type: str = MINECRAFT_JAVA,
) -> dict[str, Any]:
    """Resolve the current public join address from playit (no create/update)."""
    async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
        tunnels = await list_tunnels_v1(client, secret)
        matched = [t for t in tunnels if str(t.get("tunnel_type") or "").lower() == tunnel_type]
        pool = matched or tunnels
        public: str | None = None
        tunnel_id: str | None = None
        local_port: int | None = None
        for tunnel in pool:
            addr = pick_public_address(tunnel)
            if not addr:
                continue
            public = addr
            tunnel_id = str(tunnel.get("id") or "") or None
            local_port = tunnel_local_port(tunnel)
            break
        if public is None and tunnels:
            # Fallback: rundata display_address
            rd = await rundata(client, secret)
            for rt in rd.get("tunnels") or []:
                if not isinstance(rt, dict):
                    continue
                if tunnel_type and str(rt.get("tunnel_type") or "").lower() not in {
                    tunnel_type,
                    "",
                }:
                    if matched:
                        continue
                addr = rt.get("display_address") or rt.get("assigned_domain")
                if addr:
                    public = str(addr)
                    tunnel_id = str(rt.get("id") or "") or tunnel_id
                    if rt.get("local_port") is not None:
                        try:
                            local_port = int(rt["local_port"])
                        except (TypeError, ValueError):
                            pass
                    break
        return {
            "ok": True,
            "public_join": public,
            "public_endpoint": public,
            "tunnel_id": tunnel_id,
            "local_port": local_port,
            "tunnel_count": len(tunnels),
            "tunnel_type": tunnel_type if matched else None,
        }


async def ensure_minecraft_java_tunnel(
    secret: str,
    *,
    host: str = "127.0.0.1",
    port: int = 25565,
    name: str = DEFAULT_TUNNEL_NAME,
    wait_seconds: float = 8.0,
) -> dict[str, Any]:
    """List / create / reconfigure a Minecraft Java tunnel → local host:port."""
    import asyncio
    import time

    async with httpx.AsyncClient(timeout=45.0, follow_redirects=True) as client:
        rd = await rundata(client, secret)
        agent_id = str(rd.get("agent_id") or "")
        if not agent_id:
            raise PlayitApiError("agents/rundata missing agent_id")

        tunnels = await list_tunnels_v1(client, secret)
        mc = [t for t in tunnels if is_minecraft_java(t)]
        created = False
        updated = False

        if mc:
            tunnel = mc[0]
            tid = str(tunnel["id"])
            cur_port = tunnel_local_port(tunnel)
            for rt in rd.get("tunnels") or []:
                if isinstance(rt, dict) and str(rt.get("id")) == tid:
                    if rt.get("local_port") is not None:
                        try:
                            cur_port = int(rt["local_port"])
                        except (TypeError, ValueError):
                            pass
                    break
            if cur_port != int(port):
                await configure_tunnel_origin(
                    client, secret, tunnel_id=tid, host=host, port=port
                )
                updated = True
        else:
            await create_minecraft_java_tunnel(
                client, secret, agent_id=agent_id, host=host, port=port, name=name
            )
            created = True

        public: str | None = None
        tunnel_id: str | None = None
        deadline = time.monotonic() + max(0.5, wait_seconds)
        while True:
            tunnels = await list_tunnels_v1(client, secret)
            mc = [t for t in tunnels if is_minecraft_java(t)]
            if mc:
                tunnel = mc[0]
                tunnel_id = str(tunnel["id"])
                public = pick_public_address(tunnel)
                if public:
                    break
            if time.monotonic() >= deadline:
                break
            await asyncio.sleep(1.0)

        return {
            "ok": True,
            "created": created,
            "updated": updated,
            "tunnel_id": tunnel_id,
            "tunnel_type": MINECRAFT_JAVA,
            "local_target": f"{host}:{int(port)}",
            "public_endpoint": public,
            "agent_id": agent_id,
            "tunnel_count": len(tunnels) if tunnels else 0,
        }
