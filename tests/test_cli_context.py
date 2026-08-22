"""CLI mode detection and command visibility."""

from __future__ import annotations

from cultagent.cli.context import (
    CliMode,
    allowed_commands,
    command_allowed,
    detect_cli_mode,
    resolve_command_name,
)


def test_unregistered_mode() -> None:
    mode, summary = detect_cli_mode(None)
    assert mode in {CliMode.UNREGISTERED, CliMode.PERSONAL, CliMode.GUILD}
    assert "registered" in summary


def test_allowed_commands_unregistered_excludes_guild_and_cloud() -> None:
    allowed = allowed_commands(CliMode.UNREGISTERED)
    assert "servers" in allowed
    assert "login" in allowed
    assert "server-clone" not in allowed
    assert "builds" not in allowed
    assert "agent-servers" not in allowed
    assert "guild-server" not in allowed


def test_personal_has_cloud_not_guild() -> None:
    allowed = allowed_commands(CliMode.PERSONAL)
    assert "builds" in allowed
    assert "agent-servers" in allowed
    assert "server-clone" not in allowed
    assert "guild-tunnel" not in allowed


def test_guild_has_all_sections() -> None:
    allowed = allowed_commands(CliMode.GUILD)
    assert "servers" in allowed
    assert "builds" in allowed
    assert "server-clone" in allowed
    assert "guild-server" in allowed


def test_alias_resolves_to_canonical() -> None:
    assert resolve_command_name("builds-search") == "builds"
    assert resolve_command_name("guild-servers") == "agent-servers"


def test_invalid_config_path_exits_cleanly() -> None:
    from typer.testing import CliRunner

    from cultagent.cli.main import app

    result = CliRunner().invoke(app, ["--config", "-c"])
    assert result.exit_code == 2
    combined = result.stdout + result.stderr
    assert "Missing config path" in combined


def test_command_allowed_respects_alias() -> None:
    assert command_allowed(CliMode.UNREGISTERED, "builds-search") is False
    assert command_allowed(CliMode.GUILD, "builds-search") is True
