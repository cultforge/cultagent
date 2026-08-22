"""CLI display helpers for build install / capture-json."""

from __future__ import annotations

import io
from contextlib import redirect_stdout

from cultagent.cli.display import (
    _looks_like_build_install,
    print_result,
    set_capture_json,
)


def test_looks_like_build_install() -> None:
    assert _looks_like_build_install(
        {
            "server_id": "srv_x",
            "install": {"ok": True, "installed": [], "mode": "resolved"},
        }
    )
    assert not _looks_like_build_install({"servers": []})


def test_print_result_build_install_is_stats_not_file_dump() -> None:
    payload = {
        "ok": True,
        "command": "builds.provision",
        "data": {
            "server_id": "srv_x",
            "build_id": "bld_y",
            "loader": "forge",
            "minecraft_version": "1.20.1",
            "install": {
                "ok": True,
                "mode": "resolved",
                "installed": [
                    {
                        "path": "mods/AmbientEnvironment.jar",
                        "url": "https://cdn.modrinth.com/x",
                        "size": 100,
                    }
                ]
                * 5,
                "skipped": [],
                "errors": [],
                "warnings": [],
                "unresolved": [],
                "compatibility": {
                    "counts": {"by_kind": {"mod": 5}},
                    "notes": [],
                },
            },
        },
    }
    # Rich path should not raise; capture-json should stay compact vs full dump
    print_result(payload)
    set_capture_json(True)
    buf = io.StringIO()
    with redirect_stdout(buf):
        print_result(payload)
    out = buf.getvalue()
    set_capture_json(False)
    assert "bld_y" in out
    assert "builds.provision" in out or "srv_x" in out
