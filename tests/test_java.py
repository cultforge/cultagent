"""Java detection + Forge launch argv helpers."""

from __future__ import annotations

from pathlib import Path

from cultagent.servers.java import (
    parse_java_major,
    required_java_major,
)
from cultagent.servers.models import ServerRecord
from cultagent.servers.process import build_execution_command, expand_java_argfiles


def test_parse_java_major() -> None:
    assert parse_java_major("1.8.0_503") == 8
    assert parse_java_major("17.0.12") == 17
    assert parse_java_major("21.0.2") == 21


def test_required_java_major() -> None:
    assert required_java_major("1.20.1") == 17
    assert required_java_major("1.17.1") == 16
    assert required_java_major("1.16.5") == 8


def test_expand_java_argfiles_unix_lines(tmp_path: Path) -> None:
    (tmp_path / "user_jvm_args.txt").write_text("-Xms1G\n-Xmx2G\n", encoding="utf-8")
    (tmp_path / "forge_args.txt").write_text(
        "-p\nlibraries/demo.jar\n--main-class\ncpw.mods.bootstraplauncher.BootstrapLauncher\n",
        encoding="utf-8",
    )
    parts = expand_java_argfiles(
        ["java", "@user_jvm_args.txt", "@forge_args.txt", "nogui"],
        tmp_path,
    )
    assert parts[0] == "java"
    assert "-Xms1G" in parts
    assert "-Xmx2G" in parts
    assert "-p" in parts
    assert "libraries/demo.jar" in parts
    assert parts[-1] == "nogui"


def test_expand_java_argfiles_windows_single_line_cp(tmp_path: Path) -> None:
    (tmp_path / "win_args.txt").write_text(
        "-p libraries/a.jar;libraries/b.jar\n"
        "cpw.mods.bootstraplauncher.BootstrapLauncher\n",
        encoding="utf-8",
    )
    parts = expand_java_argfiles(["java", "@win_args.txt", "nogui"], tmp_path)
    idx = parts.index("-p")
    assert parts[idx + 1] == "libraries/a.jar;libraries/b.jar"
    assert "cpw.mods.bootstraplauncher.BootstrapLauncher" in parts


def test_build_execution_command_keeps_argfiles_on_java17(tmp_path: Path) -> None:
    (tmp_path / "user_jvm_args.txt").write_text("-Xmx4G\n", encoding="utf-8")
    (tmp_path / "win_args.txt").write_text("-p libraries/demo.jar\n", encoding="utf-8")
    record = ServerRecord(
        server_id="srv_x",
        name="forge",
        path=str(tmp_path),
        minecraft_version="1.20.1",
        loader="forge",
        execution_command="java @user_jvm_args.txt @win_args.txt nogui",
    )
    cmd = build_execution_command(
        record,
        java_bin=r"C:\Java\17\bin\java.exe",
        java_major=17,
    )
    assert cmd[0] == r"C:\Java\17\bin\java.exe"
    assert "@user_jvm_args.txt" in cmd
    assert "@win_args.txt" in cmd


def test_build_execution_command_expands_forge_args_on_java8(tmp_path: Path) -> None:
    (tmp_path / "user_jvm_args.txt").write_text("-Xmx4G\n", encoding="utf-8")
    (tmp_path / "win_args.txt").write_text(
        "-p libraries/demo.jar\ncpw.mods.bootstraplauncher.BootstrapLauncher\n",
        encoding="utf-8",
    )
    record = ServerRecord(
        server_id="srv_x",
        name="forge",
        path=str(tmp_path),
        minecraft_version="1.20.1",
        loader="forge",
        execution_command="java @user_jvm_args.txt @win_args.txt nogui",
    )
    cmd = build_execution_command(
        record,
        java_bin=r"C:\Java\8\bin\java.exe",
        java_major=8,
    )
    assert cmd[0] == r"C:\Java\8\bin\java.exe"
    assert "-Xmx4G" in cmd
    assert "cpw.mods.bootstraplauncher.BootstrapLauncher" in cmd
    assert "@user_jvm_args.txt" not in cmd
