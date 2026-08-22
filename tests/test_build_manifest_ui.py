"""Build manifest display / path resolve / dump-json helpers."""

from __future__ import annotations

from pathlib import Path

from cultagent.cli.display import dump_json_file, print_build_manifest
from cultagent.content.install import resolve_entry_path


def test_resolve_entry_path_kind_dirs() -> None:
    assert resolve_entry_path({"path": "foo.jar", "kind": "mod"}) == "mods/foo.jar"
    assert (
        resolve_entry_path({"path": "pack.zip", "kind": "resourcepack"})
        == "resourcepacks/pack.zip"
    )
    assert resolve_entry_path({"path": "mods/already.jar", "kind": "mod"}) == "mods/already.jar"


def test_dump_json_file(tmp_path: Path) -> None:
    out = tmp_path / "out.json"
    dump_json_file({"ok": True, "n": 1}, out)
    text = out.read_text(encoding="utf-8")
    assert '"ok": true' in text
    assert '"n": 1' in text


def test_print_build_manifest_smoke() -> None:
    print_build_manifest(
        {
            "build_id": "bld_demo",
            "name": "Demo",
            "mode": "resolved",
            "minecraft_version": "1.20.1",
            "loader": "fabric",
            "files": [
                {
                    "path": "mods/a.jar",
                    "kind": "mod",
                    "env": "both",
                    "sha256": "abcd" * 8,
                    "size": 1024,
                    "optional": False,
                }
            ],
            "unresolved": [],
            "warnings": [],
            "compatibility": {"ok": True, "issues": [], "notes": []},
        }
    )
