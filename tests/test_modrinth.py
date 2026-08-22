"""Modrinth client helpers / compatibility."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from cultagent.content.modrinth import (
    _disable_client_jar,
    _is_other_loader_slug,
    _version_matches_loader,
    compatibility_report,
    is_platform_dependency,
    load_index,
    loader_candidates,
    resolve_installed_mod_dependencies,
    save_index,
)
from cultagent.content.progress import install_progress


def test_compatibility_ok() -> None:
    report = compatibility_report(
        project={"server_side": "required"},
        version={
            "loaders": ["fabric"],
            "game_versions": ["1.20.1"],
            "dependencies": [],
        },
        loader="fabric",
        game_version="1.20.1",
    )
    assert report["ok"] is True


def test_compatibility_loader_mismatch() -> None:
    report = compatibility_report(
        project={"server_side": "required"},
        version={
            "loaders": ["forge"],
            "game_versions": ["1.20.1"],
            "dependencies": [],
        },
        loader="fabric",
        game_version="1.20.1",
    )
    assert report["ok"] is False
    assert any("loaders" in i for i in report["issues"])


def test_compatibility_server_unsupported() -> None:
    report = compatibility_report(
        project={"server_side": "unsupported"},
        version={
            "loaders": ["fabric"],
            "game_versions": ["1.20.1"],
            "dependencies": [],
        },
        loader="fabric",
        game_version="1.20.1",
    )
    assert report["ok"] is False


def test_compatibility_required_deps_are_notes() -> None:
    report = compatibility_report(
        project={"server_side": "required"},
        version={
            "loaders": ["forge"],
            "game_versions": ["1.20.1"],
            "dependencies": [
                {"project_id": "curios", "dependency_type": "required"},
                {"project_id": "jei", "dependency_type": "optional"},
            ],
        },
        loader="forge",
        game_version="1.20.1",
    )
    assert report["ok"] is True
    assert len(report["dependencies"]["required"]) == 1
    assert len(report["dependencies"]["optional"]) == 1


def test_loader_candidates_neoforge_falls_back_to_forge() -> None:
    assert loader_candidates("neoforge") == ["neoforge", "forge"]
    assert loader_candidates("forge") == ["forge"]


def test_is_platform_dependency() -> None:
    assert is_platform_dependency("forge") is True
    assert is_platform_dependency("minecraft") is True
    assert is_platform_dependency("fabric-api") is True
    assert is_platform_dependency("curios") is False


def test_is_other_loader_slug() -> None:
    assert _is_other_loader_slug("fabric-api", "forge") is True
    assert _is_other_loader_slug("cardinal-components-api", "forge") is True
    assert _is_other_loader_slug("forge-config-api-port", "forge") is False


def test_version_matches_loader() -> None:
    assert _version_matches_loader({"loaders": ["forge"]}, "forge") is True
    assert _version_matches_loader({"loaders": ["fabric"]}, "forge") is False
    assert _version_matches_loader({}, "forge") is True


def test_disable_client_jar(tmp_path: Path) -> None:
    mods = tmp_path / "mods"
    mods.mkdir()
    jar = mods / "Fog-forge-1.5.3.jar"
    jar.write_bytes(b"fake")
    save_index(
        tmp_path,
        {
            "schema_version": 1,
            "entries": {"Fog-forge-1.5.3.jar": {"project_id": "fog", "filename": jar.name}},
        },
    )
    renamed = _disable_client_jar(tmp_path, jar.name)
    assert renamed == "Fog-forge-1.5.3.jar.disabled"
    assert not jar.exists()
    assert (mods / renamed).is_file()
    index = load_index(tmp_path)
    assert "Fog-forge-1.5.3.jar" not in index["entries"]
    assert index["entries"][renamed]["disabled"] is True


def test_index_roundtrip(tmp_path: Path) -> None:
    save_index(
        tmp_path,
        {
            "schema_version": 1,
            "entries": {
                "demo.jar": {"project_id": "abc", "slug": "demo", "filename": "demo.jar"}
            },
        },
    )
    loaded = load_index(tmp_path)
    assert loaded["entries"]["demo.jar"]["slug"] == "demo"


@pytest.mark.asyncio
async def test_resolve_deps_emits_progress(tmp_path: Path) -> None:
    mods = tmp_path / "mods"
    mods.mkdir()
    jar = mods / "demo.jar"
    jar.write_bytes(b"fake-mod")

    client = MagicMock()
    client.versions_by_hashes = AsyncMock(
        return_value={
            "abc123": {
                "project_id": "demo-project",
                "id": "ver_1",
                "version_number": "1.0.0",
                "dependencies": [],
            }
        }
    )
    client.project = AsyncMock(return_value={"server_side": "required"})

    # Patch sha1 to a known value
    import cultagent.content.modrinth as modrinth_mod

    original_sha1 = modrinth_mod._sha1_file
    modrinth_mod._sha1_file = lambda _p: "abc123"  # noqa: ARG005

    events: list[dict[str, Any]] = []
    try:
        with install_progress(events.append):
            result = await resolve_installed_mod_dependencies(
                client,
                tmp_path,
                loader="forge",
                game_version="1.20.1",
                disable_client_only=False,
            )
    finally:
        modrinth_mod._sha1_file = original_sha1

    assert result["ok"] is True
    types = [e.get("type") for e in events]
    assert "deps_start" in types
    assert "deps_jar" in types
    assert "deps_done" in types
