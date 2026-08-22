"""Guild server clone helpers."""

from __future__ import annotations

from cultagent.guild.servers_view import (
    extract_clone_spec,
    guild_server_effective_join,
    guild_server_id,
    guild_server_label,
    is_list_request,
    summarize_chambered_build,
)


def test_is_list_request() -> None:
    assert is_list_request(None) is True
    assert is_list_request("?") is True
    assert is_list_request("list") is True
    assert is_list_request("gsrv_abc") is False


def test_guild_server_label_and_spec() -> None:
    row = {
        "id": "gsrv_abc",
        "name": "Survival",
        "loader": "paper",
        "minecraft_version": "1.20.1",
        "configured_address": "glitchx.aternos.me",
        "configured_port": 25565,
        "effective_address": "abc.playit.gg",
        "effective_port": 12345,
        "address_source": "tunnel",
        "tunnel_address": "abc.playit.gg",
        "tunnel_port": 12345,
    }
    assert guild_server_id(row) == "gsrv_abc"
    assert guild_server_effective_join(row) == "abc.playit.gg:12345"
    label = guild_server_label(row)
    assert "gsrv_abc" in label
    assert "Survival" in label
    assert "abc.playit.gg:12345" in label
    assert "[tunnel]" in label

    spec = extract_clone_spec(row)
    assert spec["guild_server_id"] == "gsrv_abc"
    assert spec["loader"] == "paper"
    assert spec["minecraft_version"] == "1.20.1"
    assert spec["port"] == 25565
    assert spec["join"] == "abc.playit.gg:12345"


def test_effective_join_falls_back_to_configured() -> None:
    row = {
        "server_id": "gsrv_x",
        "display_name": "Lan",
        "server_address": "play.example.com",
        "port": 25566,
    }
    assert guild_server_id(row) == "gsrv_x"
    assert guild_server_effective_join(row) == "play.example.com:25566"


def test_build_id_prefers_build_loader_over_outer() -> None:
    row = {
        "id": "srv_adastra",
        "name": "AdAstra",
        "loader": "vanilla",
        "minecraft_version": None,
        "build_id": "bld_valthera",
        "configured_address": "play.cultforge.com",
        "configured_port": 25565,
    }
    build = {
        "id": "bld_valthera",
        "name": "Valthera",
        "loader": "forge",
        "minecraft_version": "1.20.1",
    }
    manifest = {
        "build_id": "bld_valthera",
        "loader": "forge",
        "minecraft_version": "1.20.1",
        "mode": "resolved",
        "files": [
            {"kind": "mod", "path": "mods/a.jar"},
            {"kind": "mod", "path": "mods/b.jar"},
            {"kind": "resourcepack", "path": "resourcepacks/x.zip"},
        ],
        "unresolved": [],
    }
    # Outer loader must not win when build is present
    spec = extract_clone_spec(row, build=build, manifest=manifest)
    assert spec["loader"] == "forge"
    assert spec["minecraft_version"] == "1.20.1"
    assert spec["build_id"] == "bld_valthera"
    assert spec["build_name"] == "Valthera"

    label = guild_server_label(row, builds_by_id={"bld_valthera": build})
    assert "forge" in label
    assert "1.20.1" in label
    assert "Valthera" in label

    chamber = summarize_chambered_build(
        build_id="bld_valthera", build=build, manifest=manifest
    )
    assert chamber["installable"] is True
    assert chamber["files"] == 3
    assert chamber["by_kind"]["mod"] == 2
    assert chamber["loader"] == "forge"
