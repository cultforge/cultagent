"""Process supervisor + server lifecycle tests."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

from cultagent.app import CultAgentApp
from cultagent.servers.eula import is_eula_accepted, write_eula
from cultagent.servers.java import detect_java
from cultagent.servers.models import ServerRecord, ServerState
from cultagent.servers.process import ManagedProcess, build_execution_command, parse_command
from cultagent.settings import AgentConfig


def test_parse_command() -> None:
    parts = parse_command('java -Xmx2G -jar "server.jar" nogui')
    assert parts[0] == "java"
    assert "server.jar" in parts


def test_build_execution_command_replaces_java() -> None:
    record = ServerRecord(
        server_id="srv_x",
        name="t",
        path="/tmp",
        execution_command="java -jar server.jar nogui",
    )
    cmd = build_execution_command(record, java_bin="/usr/bin/java")
    assert cmd[0] == "/usr/bin/java"


def test_eula_roundtrip(tmp_path: Path) -> None:
    write_eula(tmp_path, accepted=False)
    assert not is_eula_accepted(tmp_path)
    write_eula(tmp_path, accepted=True)
    assert is_eula_accepted(tmp_path)


@pytest.mark.asyncio
async def test_managed_process_python_echo(tmp_path: Path) -> None:
    """Use a tiny Python child instead of Minecraft/Java."""
    script = tmp_path / "echo_server.py"
    script.write_text(
        "import sys\n"
        "print('ready', flush=True)\n"
        "for line in sys.stdin:\n"
        "    line=line.strip()\n"
        "    print(f'got:{line}', flush=True)\n"
        "    if line == 'stop':\n"
        "        break\n",
        encoding="utf-8",
    )
    record = ServerRecord(
        server_id="srv_echo",
        name="echo",
        path=str(tmp_path),
        execution_command=f'"{sys.executable}" "{script}"',
        stop_command="stop",
        shutdown_timeout_seconds=5,
    )
    proc = ManagedProcess(record)

    # Bypass Java detection by providing a fake start that uses execution_command only.
    # build_execution_command won't call detect_java if we patch start's java resolve —
    # ManagedProcess.start always calls detect_java. Use a monkeypatch.
    from cultagent.servers import process as process_mod

    original = process_mod.detect_java

    class FakeJava:
        path = sys.executable
        version = "test"
        major = 17

    process_mod.detect_java = lambda preferred=None, min_major=None: FakeJava()  # type: ignore[assignment]
    try:
        # Force command to python script (execution_command already set).
        # build_execution_command will try to replace java — our command starts with python path.
        status = await proc.start()
        assert status.state == ServerState.RUNNING
        assert proc.is_running()

        await asyncio.sleep(0.2)
        assert await proc.send_command("hello")
        await asyncio.sleep(0.2)
        buf = proc.console.read(limit=50)
        texts = "\n".join(line["text"] for line in buf["lines"])
        assert "ready" in texts or "got:hello" in texts or "> hello" in texts

        stopped = await proc.stop()
        assert stopped.state == ServerState.STOPPED
        assert not proc.is_running()
    finally:
        process_mod.detect_java = original  # type: ignore[assignment]
        if proc.is_running():
            await proc.stop()


@pytest.mark.asyncio
async def test_update_record_does_not_orphan_running_process(tmp_path: Path) -> None:
    """Binding metadata sync must not replace ManagedProcess (UI Stopped while Java lives)."""
    from cultagent.servers.manager import ServerManager

    mgr = ServerManager(tmp_path / "servers")
    mgr.ensure()
    record = await mgr.create("KeepAlive", server_id="srv_keep")
    proc = mgr._proc(record)
    proc.state = ServerState.RUNNING
    proc.process = object()  # type: ignore[assignment]  # sentinel "alive" handle
    proc.started_at = 1.0

    record.metadata = {**(record.metadata or {}), "workload_id": "awlk_new"}
    await mgr.update_record(record)

    again = mgr._proc(await mgr.get("srv_keep"))  # type: ignore[arg-type]
    assert again is proc
    assert again.state == ServerState.RUNNING
    assert again.record.metadata.get("workload_id") == "awlk_new"

    # Catalog reload with different dump must also keep the supervisor.
    fresh = await mgr.get("srv_keep")
    assert fresh is not None
    fresh.name = "Renamed"
    kept = mgr._proc(fresh)
    assert kept is proc
    assert kept.record.name == "Renamed"

    config = AgentConfig()
    config.agent.data_dir = str(tmp_path / "data")
    app = CultAgentApp(config)
    app.bootstrap_identity()
    record = await app.servers.create("Dev", minecraft_version="1.20.1", loader="vanilla")

    start = await app.dispatch("server.start", resource_id=record.server_id)
    assert start["ok"] is False
    assert "missing executable" in (start.get("error") or "")

    jar = Path(record.path) / record.executable
    jar.write_bytes(b"fake-jar")
    start2 = await app.dispatch("server.start", resource_id=record.server_id)
    assert start2["ok"] is False
    assert "EULA" in (start2.get("error") or "")

    await app.servers.accept_eula(record.server_id)
    # Will fail at Java/process launch with fake jar — that's OK; EULA gate passed.
    start3 = await app.dispatch("server.start", resource_id=record.server_id)
    # Either crashed immediately or failed java — must not be EULA/missing jar.
    err = start3.get("error") or ""
    assert "EULA" not in err
    assert "missing executable" not in err


@pytest.mark.asyncio
async def test_config_read_write(tmp_path: Path) -> None:
    config = AgentConfig()
    config.agent.data_dir = str(tmp_path / "data")
    app = CultAgentApp(config)
    app.bootstrap_identity()
    record = await app.servers.create("Cfg", minecraft_version="1.20.1")

    updated = await app.dispatch(
        "server.config.update",
        resource_id=record.server_id,
        params={"values": {"difficulty": "hard", "view-distance": "12"}},
    )
    assert updated["ok"] is True
    assert updated["data"]["properties"]["difficulty"] == "hard"

    read = await app.dispatch("server.config.read", resource_id=record.server_id)
    assert read["ok"] is True
    assert read["data"]["structured"]["gameplay"]["difficulty"] == "hard"


@pytest.mark.asyncio
async def test_server_remove_deletes_folder(tmp_path: Path) -> None:
    config = AgentConfig()
    config.agent.data_dir = str(tmp_path / "data")
    app = CultAgentApp(config)
    app.bootstrap_identity()
    record = await app.servers.create("Gone", minecraft_version="1.20.1")
    path = Path(record.path)
    assert path.is_dir()

    removed = await app.dispatch("server.remove", resource_id=record.server_id)
    assert removed["ok"] is True
    assert removed["data"]["removed"] is True
    assert removed["data"]["files_deleted"] is True
    assert not path.exists()
    assert await app.servers.get(record.server_id) is None


@pytest.mark.asyncio
async def test_server_remove_keep_files(tmp_path: Path) -> None:
    config = AgentConfig()
    config.agent.data_dir = str(tmp_path / "data")
    app = CultAgentApp(config)
    app.bootstrap_identity()
    record = await app.servers.create("Keep", minecraft_version="1.20.1")
    path = Path(record.path)

    removed = await app.dispatch(
        "server.remove",
        resource_id=record.server_id,
        params={"delete_files": False},
    )
    assert removed["ok"] is True
    assert removed["data"]["files_deleted"] is False
    assert path.is_dir()
    assert await app.servers.get(record.server_id) is None


def test_detect_java_smoke() -> None:
    # May be None on machines without Java — just ensure call doesn't crash.
    detect_java()
