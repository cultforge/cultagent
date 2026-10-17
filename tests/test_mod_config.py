"""Mod config scan / flatten / round-trip."""

from __future__ import annotations

from pathlib import Path

from cultagent.content.mod_config import list_mod_config_files, read_mod_config, write_mod_config


def test_list_and_read_toml(tmp_path: Path) -> None:
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "demo.toml").write_text(
        'enabled = true\nlimit = 12\nname = "pack"\n',
        encoding="utf-8",
    )
    files = list_mod_config_files(tmp_path)
    assert any(f["path"] == "config/demo.toml" for f in files)
    data = read_mod_config(tmp_path, "config/demo.toml")
    keys = {f["key"]: f for f in data["fields"]}
    assert keys["enabled"]["type"] == "bool"
    assert keys["enabled"]["value"] is True
    assert keys["limit"]["type"] == "number"
    assert keys["limit"]["value"] == 12


def test_write_values_roundtrip(tmp_path: Path) -> None:
    cfg = tmp_path / "config"
    cfg.mkdir()
    (cfg / "demo.toml").write_text("enabled = false\n", encoding="utf-8")
    write_mod_config(tmp_path, "config/demo.toml", values={"enabled": True, "limit": 3})
    data = read_mod_config(tmp_path, "config/demo.toml")
    keys = {f["key"]: f["value"] for f in data["fields"]}
    assert keys["enabled"] is True
    assert keys["limit"] == 3
