"""Live apply / restart planning for server.properties updates."""

from __future__ import annotations

from cultagent.config.live_apply import console_command_for, plan_live_apply


def test_live_commands_for_common_keys() -> None:
    assert console_command_for("difficulty", "hard") == "difficulty hard"
    assert console_command_for("gamemode", "creative") == "defaultgamemode creative"
    assert console_command_for("white-list", "true") == "whitelist on"
    assert console_command_for("white-list", "false") == "whitelist off"
    assert console_command_for("online-mode", "false") is None


def test_plan_splits_live_vs_restart() -> None:
    plan = plan_live_apply(
        {
            "difficulty": "easy",
            "online-mode": "false",
            "white-list": "true",
            "motd": "hello",
        }
    )
    assert "difficulty easy" in plan["commands"]
    assert "whitelist on" in plan["commands"]
    assert "difficulty" in plan["applied_keys"]
    assert "white-list" in plan["applied_keys"]
    assert "online-mode" in plan["needs_restart"]
    assert "motd" in plan["needs_restart"]
