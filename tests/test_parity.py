"""Backups, mods helpers, crash flags."""

from __future__ import annotations

from pathlib import Path

import pytest

from cultagent.files import BackupManager
from cultagent.servers.models import ServerRecord


def test_backup_zip_and_restore(tmp_path: Path) -> None:
    src = tmp_path / "server"
    src.mkdir()
    (src / "server.properties").write_text("motd=hi\n", encoding="utf-8")
    (src / "logs").mkdir()
    (src / "logs" / "latest.log").write_text("noise\n", encoding="utf-8")
    (src / "world").mkdir()
    (src / "world" / "level.dat").write_bytes(b"abc")

    mgr = BackupManager(tmp_path / "backups")
    created = mgr.create_backup(src, "srv_test")
    assert created["path"].endswith(".zip")
    assert Path(created["path"]).is_file()

    target = tmp_path / "restore"
    with pytest.raises(PermissionError):
        mgr.restore_backup(Path(created["path"]), target, confirm=False)

    result = mgr.restore_backup(Path(created["path"]), target, confirm=True)
    assert result["restored"] is True
    assert (target / "server.properties").read_text(encoding="utf-8") == "motd=hi\n"
    assert not (target / "logs" / "latest.log").exists()


def test_neoforge_mc_match() -> None:
    from cultagent.servers.install import SERVER_LOADERS, _neoforge_matches_mc

    assert "forge" in SERVER_LOADERS
    assert "neoforge" in SERVER_LOADERS
    assert "purpur" in SERVER_LOADERS
    assert _neoforge_matches_mc("21.1.92", "1.21.1")
    assert _neoforge_matches_mc("20.4.237", "1.20.4")
    assert not _neoforge_matches_mc("21.1.92", "1.20.1")


def test_server_record_crash_defaults() -> None:
    rec = ServerRecord(server_id="srv_x", name="X", path="/tmp/x")
    assert rec.crash_detection is True
    assert rec.auto_restart is True
    assert rec.auto_start is False
