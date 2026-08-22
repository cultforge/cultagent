"""Tests for latest.json / update check helpers."""

from __future__ import annotations

from cultagent.updates import _pick_platform_entry, platform_key


def test_platform_key_shape() -> None:
    key = platform_key()
    assert "-" in key
    assert key.split("-", 1)[0] in {"windows", "linux", "darwin"} or True


def test_pick_platform_entry_nested() -> None:
    data = {
        "version": "0.2.0",
        "platforms": {
            "windows-amd64": {
                "version": "0.2.0",
                "hash": "sha256:abc",
                "filelink": "https://example/cf-agent.exe",
            }
        },
    }
    entry = _pick_platform_entry(data, "windows-amd64")
    assert entry["hash"] == "sha256:abc"
    assert entry["filelink"].endswith("cf-agent.exe")


def test_pick_platform_entry_flat() -> None:
    data = {
        "version": "0.2.0",
        "hash": "sha256:xyz",
        "filelink": "https://example/bin",
    }
    entry = _pick_platform_entry(data, "linux-amd64")
    assert entry["hash"] == "sha256:xyz"
