"""playit network helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cultagent.network.playit import (
    PlayitAgent,
    claim_url_for,
    normalize_secret,
    parse_claim_code,
    platform_asset_name,
    platform_profile,
)
from cultagent.network import NetworkManager
from cultagent.settings import NetworkSection, PlayitSection


def test_platform_asset_name_known() -> None:
    name = platform_asset_name()
    if name is not None:
        assert name.startswith("playit-")


def test_platform_profile_has_docs() -> None:
    profile = platform_profile()
    assert profile["support_hub"] == "https://playit.gg/support/"
    assert profile["platform"] in {"windows", "linux", "macos", "unknown"}
    assert isinstance(profile.get("install_methods"), list)
    assert len(profile["install_methods"]) >= 1
    import platform as py_platform

    if py_platform.system() == "Darwin":
        assert profile["managed_download"] is False
    elif py_platform.system() in {"Windows", "Linux"}:
        assert profile["managed_download"] is True


def test_parse_claim_code_from_ansi_tui() -> None:
    raw = "\x1b[;m69f76b0ad1\x1b[17;120H"
    assert parse_claim_code(raw) == "69f76b0ad1"
    assert claim_url_for("69f76b0ad1") == "https://playit.gg/claim/69f76b0ad1"


def test_normalize_secret_rejects_claim_url() -> None:
    with pytest.raises(ValueError, match="claim URL"):
        normalize_secret("https://playit.gg/claim/2f1bc2b8ee")
    with pytest.raises(ValueError, match="claim code"):
        normalize_secret("2f1bc2b8ee")


def test_normalize_secret_hex_and_toml() -> None:
    hex_key = "a" * 64
    assert normalize_secret(hex_key) == hex_key
    assert normalize_secret(f'secret_key = "{hex_key}"') == hex_key
    with pytest.raises(ValueError):
        normalize_secret("not-a-hex-secret")
    with pytest.raises(ValueError):
        normalize_secret("")


def test_secret_roundtrip_playit_toml(tmp_path: Path) -> None:
    agent = PlayitAgent(tmp_path)
    assert agent.has_secret() is False
    hex_key = "ab" * 32
    agent.write_secret(hex_key)
    assert agent.secret_path.name == "playit.toml"
    assert "secret_key" in agent.secret_path.read_text(encoding="utf-8")
    assert agent.has_secret() is True
    assert agent.read_secret() == hex_key
    agent.clear_secret()
    assert agent.has_secret() is False


def test_legacy_secret_key_migrates_on_read(tmp_path: Path) -> None:
    agent = PlayitAgent(tmp_path)
    hex_key = "cd" * 32
    agent.legacy_secret_path.write_text(hex_key + "\n", encoding="utf-8")
    assert agent.read_secret() == hex_key


def test_launch_args_claim_cli_style(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agent = PlayitAgent(tmp_path)
    hex_key = "ef" * 32
    agent.write_secret(hex_key)
    fake_bin = tmp_path / "bin" / "playit-test"
    fake_bin.parent.mkdir(parents=True, exist_ok=True)
    fake_bin.write_text("", encoding="utf-8")
    agent.binary_override = str(fake_bin)
    monkeypatch.setattr(agent, "supports_claim_cli", lambda _b=None: True)
    args = agent._launch_args(secret=hex_key)
    assert "--secret_path" in args
    assert "start" in args
    assert "--secret-path" not in args


def test_launch_args_daemon_style(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agent = PlayitAgent(tmp_path)
    hex_key = "ef" * 32
    fake_bin = tmp_path / "bin" / "playit-test"
    fake_bin.parent.mkdir(parents=True, exist_ok=True)
    fake_bin.write_text("", encoding="utf-8")
    agent.binary_override = str(fake_bin)
    monkeypatch.setattr(agent, "supports_claim_cli", lambda _b=None: False)
    args = agent._launch_args(secret=hex_key)
    assert "--secret-path" in args
    assert "--socket-path" in args
    assert "start" not in args


@pytest.mark.asyncio
async def test_playit_reset_clears_secret(tmp_path: Path) -> None:
    agent = PlayitAgent(tmp_path)
    agent.write_secret("ab" * 32)
    agent._save_state(pid=None, claim_code="deadbeef01")
    result = await agent.reset()
    assert result["ok"] is True
    assert result["secret_cleared"] is True
    assert agent.has_secret() is False


@pytest.mark.asyncio
async def test_playit_setup_opens_claim_url(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = PlayitAgent(tmp_path)
    fake_bin = tmp_path / "bin" / "playit-windows-x86_64.exe"
    fake_bin.parent.mkdir(parents=True, exist_ok=True)
    fake_bin.write_bytes(b"MZ")

    async def fake_install(*, force: bool = False, pin_tag: bool = True) -> dict:
        return {
            "ok": True,
            "path": str(fake_bin),
            "asset": "playit-windows-x86_64.exe",
            "downloaded": False,
            "note": "already installed",
        }

    opened: list[str] = []

    def fake_open(url: str, new: int = 0) -> bool:
        opened.append(url)
        return True

    monkeypatch.setattr(agent, "install", fake_install)
    monkeypatch.setattr(
        agent,
        "generate_claim_code",
        lambda: {"claim_code": "abcdef1234", "claim_url": "https://playit.gg/claim/abcdef1234"},
    )
    monkeypatch.setattr("webbrowser.open", fake_open)

    result = await agent.setup(force=False, open_browser=True, wait_exchange=False)
    assert result["ok"] is True
    assert result["browser_opened"] is True
    assert result["claim_code"] == "abcdef1234"
    assert opened == ["https://playit.gg/claim/abcdef1234"]
    assert result["claim_exchanged"] is False


@pytest.mark.asyncio
async def test_network_manager_direct_status(tmp_path: Path) -> None:
    section = NetworkSection(
        default_provider="direct",
        playit=PlayitSection(enabled=False, target_port=25566),
    )
    mgr = NetworkManager(section, data_dir=tmp_path / "playit")
    status = await mgr.status()
    assert status["active"] == "direct"
    assert status["provider"] == "direct"
    assert "25566" in str(status["target"]) or status["target"].endswith("25566")


@pytest.mark.asyncio
async def test_network_use_playit(tmp_path: Path) -> None:
    section = NetworkSection(default_provider="direct")
    mgr = NetworkManager(section, data_dir=tmp_path / "playit")
    mgr.use("playit")
    status = await mgr.status()
    assert status["active"] == "playit"
    assert status["details"]["has_secret"] is False
    assert status["details"].get("stub") is False
    assert status["details"].get("setup_url")


@pytest.mark.asyncio
async def test_playit_start_persists_active_provider(tmp_path: Path) -> None:
    """playit-start must survive a new process (fresh NetworkManager)."""
    data_dir = tmp_path / "playit"
    section = NetworkSection(default_provider="direct")
    first = NetworkManager(section, data_dir=data_dir)
    first.use("playit")
    assert first.active_name == "playit"
    state = first.playit.load_state()
    assert state.get("active_provider") == "playit"
    assert state.get("enabled") is True

    second = NetworkManager(
        NetworkSection(default_provider="direct"),
        data_dir=data_dir,
    )
    assert second.active_name == "playit"
    status = await second.status()
    assert status["active"] == "playit"
    assert "playit" not in status  # active is playit — no inactive-provider block


def test_network_use_direct_persists_over_enabled(tmp_path: Path) -> None:
    data_dir = tmp_path / "playit"
    first = NetworkManager(NetworkSection(default_provider="direct"), data_dir=data_dir)
    first.use("playit")
    first.use("direct")
    second = NetworkManager(NetworkSection(default_provider="direct"), data_dir=data_dir)
    assert second.active_name == "direct"


def test_enabled_state_migrates_active_when_provider_missing(tmp_path: Path) -> None:
    """Older state.json had enabled=true but no active_provider."""
    data_dir = tmp_path / "playit"
    first = NetworkManager(NetworkSection(default_provider="direct"), data_dir=data_dir)
    first.playit.enabled = True
    first.playit._save_state()  # noqa: SLF001
    state = first.playit.load_state()
    state.pop("active_provider", None)
    first.playit.state_path.write_text(json.dumps(state) + "\n", encoding="utf-8")
    second = NetworkManager(NetworkSection(default_provider="direct"), data_dir=data_dir)
    assert second.active_name == "playit"


def test_pick_public_address_prefers_auto() -> None:
    from cultagent.network.playit_api import pick_public_address, tunnel_local_port

    tunnel = {
        "tunnel_type": "minecraft-java",
        "connect_addresses": [
            {"type": "auto", "value": {"address": "demo.tun.ply.gg"}},
            {"type": "addr4", "value": {"address": "1.2.3.4:12345"}},
        ],
        "origin": {
            "type": "agent",
            "details": {
                "config_data": {
                    "fields": [
                        {"name": "local_ip", "value": "127.0.0.1"},
                        {"name": "local_port", "value": "25565"},
                    ]
                }
            },
        },
    }
    assert pick_public_address(tunnel) == "demo.tun.ply.gg"
    assert tunnel_local_port(tunnel) == 25565


@pytest.mark.asyncio
async def test_ensure_minecraft_creates_when_empty(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from cultagent.network import playit_api

    calls: list[tuple[str, dict | None]] = []

    async def fake_post(client, secret, path, payload=None):  # noqa: ANN001
        calls.append((path, payload))
        if path == "/v1/agents/rundata":
            return {"agent_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee", "tunnels": []}
        if path == "/v1/tunnels/list":
            # After create, second list returns the tunnel
            creates = [c for c in calls if c[0] == "/v1/tunnels/create"]
            if not creates:
                return {"tunnels": []}
            return {
                "tunnels": [
                    {
                        "id": "11111111-2222-3333-4444-555555555555",
                        "tunnel_type": "minecraft-java",
                        "connect_addresses": [
                            {"type": "auto", "value": {"address": "join.tun.ply.gg"}}
                        ],
                        "origin": {
                            "type": "agent",
                            "details": {
                                "config_data": {
                                    "fields": [
                                        {"name": "local_ip", "value": "127.0.0.1"},
                                        {"name": "local_port", "value": "25565"},
                                    ]
                                }
                            },
                        },
                    }
                ]
            }
        if path == "/v1/tunnels/create":
            assert payload is not None
            assert payload["protocol"]["details"] == "minecraft-java"
            fields = payload["origin"]["data"]["config"]["fields"]
            assert {"name": "local_port", "value": "25565"} in fields
            return {"id": "11111111-2222-3333-4444-555555555555"}
        raise AssertionError(path)

    monkeypatch.setattr(playit_api, "_post", fake_post)
    result = await playit_api.ensure_minecraft_java_tunnel(
        "ab" * 32, host="127.0.0.1", port=25565, wait_seconds=0.5
    )
    assert result["created"] is True
    assert result["public_endpoint"] == "join.tun.ply.gg"
    assert any(p == "/v1/tunnels/create" for p, _ in calls)


@pytest.mark.asyncio
async def test_ensure_minecraft_updates_local_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from cultagent.network import playit_api

    calls: list[str] = []

    async def fake_post(client, secret, path, payload=None):  # noqa: ANN001
        calls.append(path)
        if path == "/v1/agents/rundata":
            return {
                "agent_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "tunnels": [
                    {
                        "id": "11111111-2222-3333-4444-555555555555",
                        "local_port": 30386,
                        "tunnel_type": "minecraft-java",
                    }
                ],
            }
        if path == "/v1/tunnels/list":
            return {
                "tunnels": [
                    {
                        "id": "11111111-2222-3333-4444-555555555555",
                        "tunnel_type": "minecraft-java",
                        "connect_addresses": [
                            {"type": "auto", "value": {"address": "join.tun.ply.gg"}}
                        ],
                        "origin": {
                            "data": {"local_port": 30386},
                        },
                    }
                ]
            }
        if path == "/v1/tunnels/config":
            assert payload["new_config"]["fields"][-1]["value"] == "25565"
            return None
        raise AssertionError(path)

    monkeypatch.setattr(playit_api, "_post", fake_post)
    result = await playit_api.ensure_minecraft_java_tunnel(
        "ab" * 32, port=25565, wait_seconds=0.5
    )
    assert result["created"] is False
    assert result["updated"] is True
    assert "/v1/tunnels/config" in calls
    assert "/v1/tunnels/create" not in calls


@pytest.mark.asyncio
async def test_fetch_public_join(monkeypatch: pytest.MonkeyPatch) -> None:
    from cultagent.network import playit_api

    async def fake_post(client, secret, path, payload=None):  # noqa: ANN001
        if path == "/v1/tunnels/list":
            return {
                "tunnels": [
                    {
                        "id": "11111111-2222-3333-4444-555555555555",
                        "tunnel_type": "minecraft-java",
                        "connect_addresses": [
                            {"type": "auto", "value": {"address": "join.me.tun.ply.gg"}}
                        ],
                    }
                ]
            }
        raise AssertionError(path)

    monkeypatch.setattr(playit_api, "_post", fake_post)
    info = await playit_api.fetch_public_join("ab" * 32)
    assert info["public_join"] == "join.me.tun.ply.gg"
    assert info["public_endpoint"] == "join.me.tun.ply.gg"


@pytest.mark.asyncio
async def test_status_recognizes_public_join(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    agent = PlayitAgent(tmp_path)
    agent.write_secret("ab" * 32)

    async def fake_refresh(*, force: bool = False, max_age: float = 45.0) -> str | None:
        agent._public_join = "recognized.tun.ply.gg"
        agent._tunnel_count = 1
        return agent._public_join

    monkeypatch.setattr(agent, "refresh_public_join", fake_refresh)
    status = await agent.status_dict()
    assert status["public_join"] == "recognized.tun.ply.gg"
    assert status["public_endpoint"] == "recognized.tun.ply.gg"


@pytest.mark.asyncio
async def test_network_status_promotes_playit_join(tmp_path: Path) -> None:
    section = NetworkSection(default_provider="direct")
    mgr = NetworkManager(section, data_dir=tmp_path / "playit")
    mgr.playit._public_join = "promo.tun.ply.gg"
    mgr.playit._public_join_checked_at = 1e18  # skip API
    mgr.playit.write_secret("ab" * 32)

    async def no_refresh(*, force: bool = False, max_age: float = 45.0) -> str | None:
        return mgr.playit._public_join

    mgr.playit.refresh_public_join = no_refresh  # type: ignore[method-assign]
    status = await mgr.status()
    assert status["active"] == "direct"
    assert status["public_join"] == "promo.tun.ply.gg"
    assert status["public_endpoint"] == "promo.tun.ply.gg"
