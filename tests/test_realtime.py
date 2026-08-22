"""Tests for agent WebSocket discovery / URL helpers."""

from __future__ import annotations

from cultagent.cloud.realtime_discover import (
    CANDIDATE_AGENT_WS_PATHS,
    api_base_to_ws_url,
    discover_agent_ws,
)


def test_discover_none_on_poll_only_manifest() -> None:
    manifest = {
        "&": {"build_id": "test"},
        "api": {
            "/v1/agent/poll": {"uri": "/v1/agent/poll"},
            "/v1/agent/heartbeat": {"uri": "/v1/agent/heartbeat"},
        },
    }
    assert discover_agent_ws(manifest) is None


def test_discover_candidate_path() -> None:
    path = CANDIDATE_AGENT_WS_PATHS[0]
    manifest = {
        "&": {},
        "api": {
            path: {"uri": path},
            "/v1/agent/poll": {"uri": "/v1/agent/poll"},
        },
    }
    assert discover_agent_ws(manifest) == path


def test_discover_meta_hint() -> None:
    manifest = {
        "&": {"agent_ws": "/v1/agent/realtime/ws"},
        "api": {},
    }
    assert discover_agent_ws(manifest) == "/v1/agent/realtime/ws"


def test_discover_capabilities_flag() -> None:
    manifest = {
        "&": {"capabilities": {"agent_websocket": True}},
        "api": {},
    }
    assert discover_agent_ws(manifest) == CANDIDATE_AGENT_WS_PATHS[0]


def test_api_base_to_ws_url() -> None:
    assert (
        api_base_to_ws_url("https://api.cultforge.com", "/v1/agent/ws")
        == "wss://api.cultforge.com/v1/agent/ws"
    )
    assert (
        api_base_to_ws_url("http://localhost:8071", "/v1/agent/ws")
        == "ws://localhost:8071/v1/agent/ws"
    )
    assert (
        api_base_to_ws_url("https://api.cultforge.com", "wss://other.example/ws")
        == "wss://other.example/ws"
    )
