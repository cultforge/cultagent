"""Console → guild presence / events parsing."""

from __future__ import annotations

from cultagent.cloud.presence import PresenceTracker, get_presence_tracker


def test_join_leave_and_uuid() -> None:
    t = PresenceTracker()
    sid = "srv_test"
    t.ingest_lines(
        sid,
        [
            "[Server thread/INFO]: UUID of player GliTCH is 01234567-89ab-cdef-0123-456789abcdef",
            "[Server thread/INFO]: GliTCH joined the game",
        ],
    )
    snap = t.snapshot(sid)
    assert snap["player_count"] == 1
    assert snap["players"][0]["minecraft_name"] == "GliTCH"
    assert snap["players"][0]["uuid"].startswith("01234567")

    t.ingest_lines(sid, ["[Server thread/INFO]: GliTCH left the game"])
    assert t.snapshot(sid)["player_count"] == 0
    events = t.drain_events(sid)
    types = [e["event_type"] for e in events]
    assert "player.joined" in types
    assert "player.left" in types


def test_list_header_replaces_roster() -> None:
    t = PresenceTracker()
    sid = "srv_list"
    t.ingest_lines(sid, ["Alice joined the game", "Bob joined the game"])
    t.ingest_lines(
        sid,
        ["There are 1 of a max of 20 players online: Alice"],
    )
    snap = t.snapshot(sid)
    assert snap["player_count"] == 1
    assert snap["players"][0]["name"] == "Alice"
    assert snap["max_players"] == 20


def test_death_and_advancement_events() -> None:
    t = PresenceTracker()
    sid = "srv_ev"
    t.ingest_lines(
        sid,
        [
            "Steve was slain by Zombie",
            "Alex has made the advancement [Stone Age]",
        ],
    )
    events = t.drain_events(sid)
    assert any(e["event_type"] == "player.died" and e["minecraft_name"] == "Steve" for e in events)
    assert any(
        e["event_type"] == "player.advancement" and e["minecraft_name"] == "Alex" for e in events
    )


def test_process_global_tracker_singleton() -> None:
    a = get_presence_tracker()
    b = get_presence_tracker()
    assert a is b
