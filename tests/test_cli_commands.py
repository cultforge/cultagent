"""CLI command surface: merged commands and hidden backward-compat aliases."""

from __future__ import annotations

from typer.testing import CliRunner

from cultagent.cli.main import app

runner = CliRunner()


def test_merged_builds_help_shows_search_flags() -> None:
    result = runner.invoke(app, ["builds", "--help"])
    assert result.exit_code == 0
    assert "--q" in result.stdout
    assert "--loader" in result.stdout


def test_merged_build_help_shows_new_flag() -> None:
    result = runner.invoke(app, ["build", "--help"])
    assert result.exit_code == 0
    assert "--new" in result.stdout
    assert "--build" in result.stdout


def test_merged_mods_help_shows_modrinth_modes() -> None:
    result = runner.invoke(app, ["mods", "--help"])
    assert result.exit_code == 0
    assert "--search" in result.stdout
    assert "--info" in result.stdout
    assert "--versions" in result.stdout


def test_merged_agent_servers_help_shows_bindings() -> None:
    result = runner.invoke(app, ["agent-servers", "--help"])
    assert result.exit_code == 0
    assert "--bindings" in result.stdout


def test_merged_profile_apply_help_shows_diff() -> None:
    result = runner.invoke(app, ["profile-apply", "--help"])
    assert result.exit_code == 0
    assert "--diff" in result.stdout


def test_hidden_alias_builds_search_help() -> None:
    result = runner.invoke(app, ["builds-search", "--help"])
    assert result.exit_code == 0


def test_hidden_alias_build_provision_help() -> None:
    result = runner.invoke(app, ["build-provision", "--help"])
    assert result.exit_code == 0


def test_hidden_alias_modrinth_search_help() -> None:
    result = runner.invoke(app, ["modrinth-search", "--help"])
    assert result.exit_code == 0


def test_hidden_aliases_omitted_from_top_level_help() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "builds-search" not in result.stdout
    assert "build-provision" not in result.stdout
    assert "modrinth-search" not in result.stdout
    assert "agent-bindings" not in result.stdout


def test_top_level_help_lists_canonical_commands() -> None:
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Local" in result.stdout
    assert "servers" in result.stdout


def test_top_level_help_flag() -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "servers" in result.stdout
