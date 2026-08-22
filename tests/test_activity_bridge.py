"""Activity bridge: friendly HUD lines + console tails for telemetry."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from cultagent.cloud.activity_bridge import (
    ACTIVITY_MAX,
    LINE_MAX_CHARS,
    ActivityBridge,
    classify_event,
    get_activity_bridge,
)
from cultagent.cloud.control_plane import ControlPlane
from cultagent.settings import AgentConfig


def test_classify_event_kinds() -> None:
    assert classify_event("Something went wrong: boom") == "err"
    assert classify_event("Having trouble reaching CultForge") == "warn"
    assert classify_event("Starting server...") == "work"
    assert classify_event("Local panel ready") == "ok"
    assert classify_event("Connected to CultForge realtime") == "info"


def test_bridge_ring_buffer_and_truncate() -> None:
    bridge = ActivityBridge()
    bridge.clear()
    for i in range(ACTIVITY_MAX + 5):
        bridge.push_line(f"line {i}")
    snap = bridge.snapshot_activity()
    assert snap["schema_version"] == 1
    assert len(snap["lines"]) == ACTIVITY_MAX
    assert snap["lines"][0]["text"] == "line 5"
    assert snap["lines"][-1]["text"] == f"line {ACTIVITY_MAX + 4}"

    long = "x" * (LINE_MAX_CHARS + 50)
    bridge.push_line(long)
    last = bridge.snapshot_activity()["lines"][-1]["text"]
    assert len(last) == LINE_MAX_CHARS
    assert last.endswith("...")


def test_bridge_friendly_sink_roundtrip() -> None:
    bridge = ActivityBridge()
    bridge.clear()
    bridge.stop()
    bridge.start()
    try:
        from cultagent.logging_setup import _emit_friendly

        _emit_friendly("Agent started")
        lines = bridge.snapshot_activity()["lines"]
        assert any(x["text"] == "Agent started" for x in lines)
    finally:
        bridge.stop()
        bridge.clear()


@pytest.mark.asyncio
async def test_snapshot_consoles_caps_running_only() -> None:
    bridge = ActivityBridge()

    class FakeServers:
        def __init__(self) -> None:
            self._ids = ["srv_a", "srv_b", "srv_c", "srv_d"]

        async def list_servers(self) -> list[Any]:
            return [MagicMock(server_id=sid) for sid in self._ids]

        def is_process_running(self, server_id: str) -> bool:
            return server_id != "srv_b"

        async def console_read(self, server_id: str, *, limit: int = 50) -> dict[str, Any]:
            return {
                "seq": 10,
                "lines": [
                    {"seq": i, "ts": 1_700_000_000.0, "text": f"{server_id} line {i}"}
                    for i in range(1, 6)
                ],
            }

    consoles = await bridge.snapshot_consoles(FakeServers())  # type: ignore[arg-type]
    assert len(consoles) == 3  # max servers; srv_b skipped
    assert [c["server_id"] for c in consoles] == ["srv_a", "srv_c", "srv_d"]
    assert consoles[0]["seq"] == 10
    assert len(consoles[0]["lines"]) == 5
    assert consoles[0]["lines"][0]["text"].startswith("srv_a")


@pytest.mark.asyncio
async def test_build_telemetry_includes_activity_and_consoles(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config = AgentConfig()
    config.agent.data_dir = str(tmp_path / "data")
    from cultagent.app import CultAgentApp

    app = CultAgentApp(config)
    app.bootstrap_identity()

    bridge = get_activity_bridge()
    bridge.clear()
    bridge.push_line("Connected to CultForge realtime")

    async def fake_collect() -> dict[str, Any]:
        return {"system": {"cpu": 1}, "minecraft": {}, "network": {}}

    async def fake_network_status() -> dict[str, Any]:
        return {"active": "direct"}

    async def fake_consoles(_servers: Any) -> list[dict[str, Any]]:
        return [
            {
                "server_id": "srv_test",
                "seq": 3,
                "lines": [{"seq": 3, "ts": "2026-01-01T00:00:00Z", "text": "Done!"}],
            }
        ]

    monkeypatch.setattr(app.metrics, "collect", fake_collect)
    monkeypatch.setattr(app.network, "status", fake_network_status)
    monkeypatch.setattr(bridge, "snapshot_consoles", fake_consoles)

    cp = ControlPlane(app)
    metrics = await cp._build_telemetry()  # noqa: SLF001
    assert metrics["activity"]["schema_version"] == 1
    assert metrics["activity"]["lines"][-1]["text"] == "Connected to CultForge realtime"
    assert metrics["consoles"][0]["server_id"] == "srv_test"
    assert "system" in metrics
    bridge.clear()
