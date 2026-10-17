"""server.player.kick / server.player.ban command handlers."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from cultagent.commands import CommandContext
from cultagent.commands.handlers import (
    _player_target,
    server_player_ban,
    server_player_kick,
)
from cultagent.constants import COMMANDS
from cultagent.rbac import HIGH_RISK_COMMANDS


def test_kick_ban_in_command_catalog() -> None:
    assert "server.player.kick" in COMMANDS
    assert "server.player.ban" in COMMANDS
    assert "server.player.ban" in HIGH_RISK_COMMANDS
    assert "server.player.kick" not in HIGH_RISK_COMMANDS


def test_player_target_validates_name() -> None:
    ctx = CommandContext(name="server.player.kick", params={"minecraft_name": "Steve"})
    assert _player_target(ctx) == "Steve"
    with pytest.raises(ValueError):
        _player_target(CommandContext(name="x", params={"minecraft_name": "bad;name"}))
    with pytest.raises(ValueError):
        _player_target(CommandContext(name="x", params={}))


@pytest.mark.asyncio
async def test_server_player_kick_runs_console() -> None:
    console = AsyncMock(return_value={"ok": True, "line": "kick Steve griefing"})
    audit = MagicMock()
    audit.record = AsyncMock()
    app = MagicMock()
    app.servers.console_execute = console
    app.audit = audit
    app.servers.resolve_local_id = MagicMock(return_value="srv_1")
    app.bindings.local_server_id_for = MagicMock(return_value=None)

    ctx = CommandContext(
        name="server.player.kick",
        params={
            "server_id": "srv_1",
            "minecraft_name": "Steve",
            "reason": "griefing",
        },
        app=app,
        actor_id="actor_1",
    )
    result = await server_player_kick(ctx)
    assert result["ok"] is True
    assert result["action"] == "kick"
    assert result["player"] == "Steve"
    console.assert_awaited_once_with("srv_1", "kick Steve griefing")
    audit.record.assert_awaited()


@pytest.mark.asyncio
async def test_server_player_ban_runs_console() -> None:
    console = AsyncMock(return_value={"ok": True})
    audit = MagicMock()
    audit.record = AsyncMock()
    app = MagicMock()
    app.servers.console_execute = console
    app.audit = audit
    app.servers.resolve_local_id = MagicMock(return_value="srv_1")
    app.bindings.local_server_id_for = MagicMock(return_value=None)

    ctx = CommandContext(
        name="server.player.ban",
        params={"server_id": "srv_1", "player": "Alex", "reason": "cheat"},
        app=app,
        actor_id="actor_1",
    )
    result = await server_player_ban(ctx)
    assert result["ok"] is True
    assert result["action"] == "ban"
    console.assert_awaited_once_with("srv_1", "ban Alex cheat")
