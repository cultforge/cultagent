"""Apply server.properties changes to a running Minecraft process when possible.

Vanilla/Forge cannot hot-reload most properties. We map what we can to console
commands; anything else needs a process restart to take effect.
"""

from __future__ import annotations

from typing import Any

# Keys that only apply after stop/start (no reliable console equivalent).
RESTART_REQUIRED: frozenset[str] = frozenset(
    {
        "online-mode",
        "server-port",
        "server-ip",
        "max-players",
        "network-compression-threshold",
        "prevent-proxy-connections",
        "enable-status",
        "enable-query",
        "enable-rcon",
        "view-distance",
        "simulation-distance",
        "max-tick-time",
        "entity-broadcast-range-percentage",
        "level-name",
        "level-seed",
        "level-type",
        "generator-settings",
        "max-world-size",
        "spawn-protection",
        "allow-nether",
        "enable-command-block",
        "hardcore",
        "force-gamemode",
        "pvp",
        "allow-flight",
        "spawn-monsters",
        "spawn-animals",
        "spawn-npcs",
        "motd",
        "resource-pack",
        "resource-pack-sha1",
        "resource-pack-prompt",
        "require-resource-pack",
        "player-idle-timeout",
        "broadcast-console-to-ops",
        "broadcast-rcon-to-ops",
        "sync-chunk-writes",
        "use-native-transport",
        "enable-jmx-monitoring",
        "rate-limit",
        "hide-online-players",
        "op-permission-level",
        "function-permission-level",
        "enforce-secure-profile",
        "text-filtering-config",
    }
)


def _bool_cmd(on: str, off: str, value: str) -> str:
    return on if str(value).lower() in {"true", "1", "yes", "on"} else off


def console_command_for(key: str, value: str) -> str | None:
    """Return a Minecraft console line that applies ``key=value``, or None."""
    k = str(key).strip()
    v = str(value).strip()
    if k == "difficulty":
        low = v.lower()
        if low in {"peaceful", "easy", "normal", "hard"}:
            return f"difficulty {low}"
        return None
    if k == "gamemode":
        low = v.lower()
        if low in {"survival", "creative", "adventure", "spectator"}:
            return f"defaultgamemode {low}"
        return None
    if k in {"white-list", "whitelist"}:
        return _bool_cmd("whitelist on", "whitelist off", v)
    if k == "enforce-whitelist":
        # No dedicated command; whitelist reload picks up enforce on some builds —
        # still treat as restart-required for correctness.
        return None
    return None


def plan_live_apply(updates: dict[str, Any]) -> dict[str, Any]:
    """Split property updates into console commands vs restart-required keys."""
    commands: list[str] = []
    applied_keys: list[str] = []
    needs_restart: list[str] = []
    unknown: list[str] = []

    for key, raw in updates.items():
        k = str(key)
        v = str(raw)
        cmd = console_command_for(k, v)
        if cmd:
            commands.append(cmd)
            applied_keys.append(k)
            continue
        if k in RESTART_REQUIRED or k.startswith("rcon.") or k.startswith("query."):
            needs_restart.append(k)
        else:
            # Unknown keys: assume restart to be safe (file is already written).
            needs_restart.append(k)
            unknown.append(k)

    # Dedupe while preserving order
    def _uniq(items: list[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            if item in seen:
                continue
            seen.add(item)
            out.append(item)
        return out

    return {
        "commands": _uniq(commands),
        "applied_keys": _uniq(applied_keys),
        "needs_restart": _uniq(needs_restart),
        "unknown_keys": _uniq(unknown),
    }


async def apply_config_to_running(
    app: Any,
    server_id: str,
    updates: dict[str, Any],
    *,
    auto_restart: bool = True,
) -> dict[str, Any]:
    """Push live console commands; optionally restart if remaining keys need it.

    File write must already be done by the caller.
    """
    plan = plan_live_apply(updates)
    result: dict[str, Any] = {
        **plan,
        "running": False,
        "console_sent": [],
        "restarted": False,
        "message": "Saved to server.properties",
    }

    if not updates:
        return result

    running = bool(app.servers.is_process_running(server_id))
    result["running"] = running
    if not running:
        result["message"] = "Saved — will apply on next start"
        result["needs_restart"] = []  # nothing running; next start loads file
        return result

    sent: list[str] = []
    for cmd in plan["commands"]:
        try:
            await app.servers.console_execute(server_id, cmd)
            sent.append(cmd)
        except Exception as exc:  # noqa: BLE001
            result.setdefault("console_errors", []).append(
                {"command": cmd, "error": str(exc)}
            )
    result["console_sent"] = sent

    needs = list(plan["needs_restart"])
    if needs and auto_restart:
        try:
            await app.servers.restart(server_id)
            result["restarted"] = True
            result["needs_restart"] = []
            live_bit = (
                f"Applied live ({', '.join(plan['applied_keys'])}); "
                if plan["applied_keys"]
                else ""
            )
            result["message"] = (
                f"Saved and restarted so {', '.join(needs)} take effect"
                if not plan["applied_keys"]
                else f"Saved. {live_bit}restarted for {', '.join(needs)}"
            )
        except Exception as exc:  # noqa: BLE001
            result["restart_error"] = str(exc)
            result["message"] = (
                f"Saved; live commands sent, but restart failed — "
                f"restart manually for: {', '.join(needs)} ({exc})"
            )
    elif needs:
        result["message"] = (
            "Saved"
            + (f"; applied live: {', '.join(plan['applied_keys'])}" if sent else "")
            + f". Restart required for: {', '.join(needs)}"
        )
    elif sent:
        result["message"] = f"Saved and applied live: {', '.join(plan['applied_keys'])}"
    else:
        result["message"] = "Saved"

    return result
