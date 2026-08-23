"""Datapack path remapping + server-refresh prune."""

from __future__ import annotations

from pathlib import Path

from cultagent.content.install import (
    datapack_dir,
    migrate_root_datapacks,
    read_level_name,
    resolve_entry_path,
    _should_install_file,
)
from cultagent.content.modrinth import dedupe_mods_by_project, load_index, save_index
from cultagent.content.refresh import expected_content_paths, prune_unmanaged_content


def test_read_level_name_default(tmp_path: Path) -> None:
    assert read_level_name(tmp_path) == "world"


def test_read_level_name_from_properties(tmp_path: Path) -> None:
    (tmp_path / "server.properties").write_text(
        "motd=hi\nlevel-name=survival\n", encoding="utf-8"
    )
    assert read_level_name(tmp_path) == "survival"
    assert datapack_dir(tmp_path) == tmp_path / "survival" / "datapacks"


def test_resolve_entry_path_remaps_datapacks(tmp_path: Path) -> None:
    (tmp_path / "server.properties").write_text("level-name=flat\n", encoding="utf-8")
    assert resolve_entry_path({"path": "datapacks/foo.zip", "kind": "mod"}, tmp_path) == (
        "flat/datapacks/foo.zip"
    )
    assert resolve_entry_path({"path": "foo.zip", "kind": "datapack"}, tmp_path) == (
        "flat/datapacks/foo.zip"
    )


def test_datapack_env_client_still_installs() -> None:
    assert _should_install_file(
        {"path": "datapacks/x.zip", "kind": "datapack", "env": "client"},
        server_side=True,
    )


def test_migrate_root_datapacks(tmp_path: Path) -> None:
    legacy = tmp_path / "datapacks"
    legacy.mkdir()
    (legacy / "pack.zip").write_bytes(b"abc")
    moved = migrate_root_datapacks(tmp_path)
    assert moved == ["world/datapacks/pack.zip"]
    assert (tmp_path / "world" / "datapacks" / "pack.zip").is_file()
    assert not legacy.exists()


def test_dedupe_mods_by_project(tmp_path: Path) -> None:
    mods = tmp_path / "mods"
    mods.mkdir()
    (mods / "lib-a.jar").write_bytes(b"a")
    (mods / "lib-b.jar").write_bytes(b"b")
    index = {
        "entries": {
            "lib-a.jar": {
                "project_id": "abc",
                "path": "mods/lib-a.jar",
                "version_number": "1.0.0",
                "version_id": "v1",
            },
            "lib-b.jar": {
                "project_id": "abc",
                "path": "mods/lib-b.jar",
                "version_number": "1.1.0",
                "version_id": "v2",
            },
        }
    }
    save_index(tmp_path, index)
    result = dedupe_mods_by_project(tmp_path)
    assert result["removed_count"] == 1
    assert not (mods / "lib-a.jar").exists()
    assert (mods / "lib-b.jar").exists()
    kept = load_index(tmp_path)["entries"]
    assert "lib-b.jar" in kept
    assert "lib-a.jar" not in kept


def test_prune_unmanaged_content(tmp_path: Path) -> None:
    mods = tmp_path / "mods"
    mods.mkdir()
    (mods / "keep.jar").write_bytes(b"k")
    (mods / "drop.jar").write_bytes(b"d")
    dp = tmp_path / "world" / "datapacks"
    dp.mkdir(parents=True)
    (dp / "keep.zip").write_bytes(b"k")
    (dp / "drop.zip").write_bytes(b"d")
    keep = {"mods/keep.jar", "world/datapacks/keep.zip"}
    removed = prune_unmanaged_content(tmp_path, keep)
    paths = {r["path"] for r in removed}
    assert "mods/drop.jar" in paths
    assert "world/datapacks/drop.zip" in paths
    assert (mods / "keep.jar").is_file()
    assert not (mods / "drop.jar").exists()


def test_expected_content_paths_uses_world_datapacks(tmp_path: Path) -> None:
    manifest = {
        "files": [
            {"path": "datapacks/a.zip", "kind": "datapack", "urls": ["http://x"]},
            {"path": "mods/b.jar", "kind": "mod", "env": "client", "urls": ["http://x"]},
            {"path": "mods/c.jar", "kind": "mod", "urls": ["http://x"]},
        ]
    }
    paths = expected_content_paths(manifest, tmp_path)
    assert "world/datapacks/a.zip" in paths
    assert "mods/c.jar" in paths
    assert "mods/b.jar" not in paths
