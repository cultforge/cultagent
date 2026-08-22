"""CLI command surface: merged commands and hidden backward-compat aliases."""

from __future__ import annotations

from typer.main import get_command
from typer.testing import CliRunner

from cultagent.cli.main import app

runner = CliRunner()

# Rich help rendering differs by OS/TTY; assert option *definitions* for flags.
_HELP_ENV = {
    "COLUMNS": "120",
    "TERM": "xterm-256color",
    "NO_COLOR": "1",
    "FORCE_COLOR": "0",
}


def _help(*args: str):
    return runner.invoke(app, list(args), env=_HELP_ENV)


def _option_flags(command_name: str) -> set[str]:
    group = get_command(app)
    cmd = group.commands[command_name]
    flags: set[str] = set()
    for param in cmd.params:
        flags.update(param.opts)
        flags.update(getattr(param, "secondary_opts", ()) or ())
    return flags


def _help_text(result) -> str:
    return (result.stdout or "") + (getattr(result, "stderr", None) or "")


def test_merged_builds_help_shows_search_flags() -> None:
    flags = _option_flags("builds")
    assert "--q" in flags
    assert "--loader" in flags
    result = _help("builds", "--help")
    assert result.exit_code == 0
    assert "builds" in _help_text(result).lower()


def test_merged_build_help_shows_new_flag() -> None:
    flags = _option_flags("build")
    assert "--new" in flags
    assert "--build" in flags
    result = _help("build", "--help")
    assert result.exit_code == 0


def test_merged_mods_help_shows_modrinth_modes() -> None:
    flags = _option_flags("mods")
    assert "--search" in flags
    assert "--info" in flags
    assert "--versions" in flags
    result = _help("mods", "--help")
    assert result.exit_code == 0


def test_merged_agent_servers_help_shows_bindings() -> None:
    flags = _option_flags("agent-servers")
    assert "--bindings" in flags
    result = _help("agent-servers", "--help")
    assert result.exit_code == 0


def test_merged_profile_apply_help_shows_diff() -> None:
    flags = _option_flags("profile-apply")
    assert "--diff" in flags
    result = _help("profile-apply", "--help")
    assert result.exit_code == 0


def test_hidden_alias_builds_search_help() -> None:
    result = _help("builds-search", "--help")
    assert result.exit_code == 0


def test_hidden_alias_build_provision_help() -> None:
    result = _help("build-provision", "--help")
    assert result.exit_code == 0


def test_hidden_alias_modrinth_search_help() -> None:
    result = _help("modrinth-search", "--help")
    assert result.exit_code == 0


def test_hidden_aliases_omitted_from_top_level_help() -> None:
    result = _help()
    assert result.exit_code == 0
    text = _help_text(result)
    assert "builds-search" not in text
    assert "build-provision" not in text
    assert "modrinth-search" not in text
    assert "agent-bindings" not in text


def test_top_level_help_lists_canonical_commands() -> None:
    result = _help()
    assert result.exit_code == 0
    text = _help_text(result)
    assert "Local" in text
    assert "servers" in text


def test_top_level_help_flag() -> None:
    result = _help("--help")
    assert result.exit_code == 0
    assert "servers" in _help_text(result)
