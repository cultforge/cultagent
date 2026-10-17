"""Track online players + gameplay events from Minecraft console (live API guild routes).

Live manifest:
  POST /v1/agent/guild/players  — replace roster
  POST /v1/agent/guild/events   — append gameplay events
  POST /v1/agent/guild/runtime  — includes player_count
"""

from __future__ import annotations

import re
import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# Vanilla / Forge-ish console lines (strip ANSI/timestamps via search, not full match).
_RE_JOIN = re.compile(r"(?P<name>[A-Za-z0-9_]{1,16}) joined the game\b", re.I)
_RE_LEAVE = re.compile(r"(?P<name>[A-Za-z0-9_]{1,16}) left the game\b", re.I)
_RE_UUID = re.compile(
    r"UUID of player (?P<name>[A-Za-z0-9_]{1,16}) is (?P<uuid>[0-9a-fA-F-]{32,36})",
    re.I,
)
_RE_LIST_HEADER = re.compile(
    r"There are (?P<count>\d+) of a max of (?P<max>\d+) players online\s*:\s*(?P<names>.*)$",
    re.I,
)
_RE_LIST_ALT = re.compile(
    r"(?:Online players|Players online)\s*:\s*(?P<names>.+)$",
    re.I,
)
_RE_DEATH = re.compile(
    r"(?P<name>[A-Za-z0-9_]{1,16}) (?:was slain by|was shot by|was blown up by|"
    r"was killed by|was fireballed by|was pummeled by|was stung to death by|"
    r"was squashed by|hit the ground|fell from|fell off|fell out of|"
    r"drowned|burned to death|tried to swim in lava|discovered the floor was lava|"
    r"went up in flames|walked into fire|suffocated|starved to death|"
    r"was pricked to death|froze to death|was poked to death|"
    r"experienced kinetic energy|didn't want to live|"
    r"withstood|was doomed|died)\b",
    re.I,
)
_RE_DEATH_KILLER = re.compile(
    r"\b(?:was slain by|was shot by|was blown up by|was killed by|"
    r"was fireballed by|was pummeled by)\s+(?P<killer>[A-Za-z0-9_ :.-]{1,64})",
    re.I,
)
_RE_ADVANCEMENT = re.compile(
    r"(?P<name>[A-Za-z0-9_]{1,16}) has (?:made the advancement|completed the challenge|"
    r"reached the goal) (?:\[(?P<title>[^\]]+)\]|(?P<title2>.+))$",
    re.I,
)

_MAX_EVENTS_BUFFER = 100


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _split_names(raw: str) -> list[str]:
    text = (raw or "").strip()
    if not text:
        return []
    # "Alice, Bob and Carol" / "Alice, Bob"
    text = text.replace(" and ", ", ")
    out: list[str] = []
    for part in text.split(","):
        name = part.strip()
        if re.fullmatch(r"[A-Za-z0-9_]{1,16}", name or ""):
            out.append(name)
    return out


@dataclass
class PresenceEvent:
    event_type: str
    minecraft_name: str
    at: str
    payload: dict[str, Any] = field(default_factory=dict)

    def to_api(self) -> dict[str, Any]:
        body: dict[str, Any] = {
            "event_type": self.event_type,
            "minecraft_name": self.minecraft_name,
            "at": self.at,
        }
        if self.payload:
            body["payload"] = self.payload
        return body


@dataclass
class ServerPresence:
    server_id: str
    online: dict[str, dict[str, Any]] = field(default_factory=dict)
    uuid_hints: dict[str, str] = field(default_factory=dict)
    pending_events: deque[PresenceEvent] = field(
        default_factory=lambda: deque(maxlen=_MAX_EVENTS_BUFFER)
    )
    console_seq: int = 0
    max_players: int | None = None
    dirty_roster: bool = False
    ticks_since_list: int = 0

    def roster_payload(self) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for name, meta in sorted(self.online.items(), key=lambda x: x[0].lower()):
            row: dict[str, Any] = {
                "name": name,
                "minecraft_name": name,
            }
            uuid = meta.get("uuid") or self.uuid_hints.get(name)
            if uuid:
                row["uuid"] = uuid
                row["minecraft_uuid"] = uuid
            if meta.get("joined_at"):
                row["joined_at"] = meta["joined_at"]
            if isinstance(meta.get("session_stats"), dict) and meta["session_stats"]:
                row["session_stats"] = dict(meta["session_stats"])
            rows.append(row)
        return rows


class PresenceTracker:
    """Process-wide console → presence/events for guild API sync."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._servers: dict[str, ServerPresence] = {}

    def for_server(self, server_id: str) -> ServerPresence:
        with self._lock:
            sp = self._servers.get(server_id)
            if sp is None:
                sp = ServerPresence(server_id=server_id)
                self._servers[server_id] = sp
            return sp

    def ingest_lines(self, server_id: str, lines: list[dict[str, Any]] | list[str]) -> list[PresenceEvent]:
        """Parse new console lines; return newly emitted events."""
        sp = self.for_server(server_id)
        emitted: list[PresenceEvent] = []
        with self._lock:
            for item in lines:
                if isinstance(item, dict):
                    text = str(item.get("text") or "")
                    seq = int(item.get("seq") or 0)
                    if seq and seq <= sp.console_seq:
                        continue
                    if seq:
                        sp.console_seq = max(sp.console_seq, seq)
                else:
                    text = str(item)
                for ev in self._parse_line(sp, text):
                    sp.pending_events.append(ev)
                    emitted.append(ev)
        return emitted

    def _parse_line(self, sp: ServerPresence, text: str) -> list[PresenceEvent]:
        line = text.strip()
        if not line:
            return []
        # Drop leading forge/minecraft logger noise for regexes that use $
        now = _utc_now()
        out: list[PresenceEvent] = []

        m = _RE_UUID.search(line)
        if m:
            name = m.group("name")
            uuid = m.group("uuid")
            sp.uuid_hints[name] = uuid
            if name in sp.online:
                sp.online[name]["uuid"] = uuid
                sp.dirty_roster = True
            return out

        m = _RE_JOIN.search(line)
        if m:
            name = m.group("name")
            if name not in sp.online:
                meta: dict[str, Any] = {"minecraft_name": name, "joined_at": now}
                if name in sp.uuid_hints:
                    meta["uuid"] = sp.uuid_hints[name]
                sp.online[name] = meta
                sp.dirty_roster = True
                out.append(
                    PresenceEvent(
                        event_type="player.joined",
                        minecraft_name=name,
                        at=now,
                    )
                )
            return out

        m = _RE_LEAVE.search(line)
        if m:
            name = m.group("name")
            payload: dict[str, Any] = {}
            if name in sp.online:
                meta = sp.online.pop(name, None) or {}
                sp.dirty_roster = True
                joined = meta.get("joined_at")
                if joined:
                    try:
                        t0 = datetime.fromisoformat(str(joined).replace("Z", "+00:00"))
                        t1 = datetime.fromisoformat(now.replace("Z", "+00:00"))
                        secs = max(0, int((t1 - t0).total_seconds()))
                        # Cap absurd clock skew; treat < 5s bursts as non-AFK session slice
                        if secs >= 5:
                            payload["playtime_seconds"] = secs
                    except ValueError:
                        pass
            out.append(
                PresenceEvent(
                    event_type="player.left",
                    minecraft_name=name,
                    at=now,
                    payload=payload,
                )
            )
            return out

        m = _RE_LIST_HEADER.search(line)
        if m:
            names = _split_names(m.group("names") or "")
            try:
                sp.max_players = int(m.group("max"))
            except ValueError:
                pass
            self._replace_online(sp, names, now)
            return out

        m = _RE_LIST_ALT.search(line)
        if m:
            names = _split_names(m.group("names") or "")
            self._replace_online(sp, names, now)
            return out

        m = _RE_DEATH.search(line)
        if m:
            name = m.group("name")
            payload: dict[str, Any] = {"line": line[-200:], "cause": "mob"}
            low = line.lower()
            if "fell" in low or "hit the ground" in low:
                payload["cause"] = "fall"
            elif "drown" in low:
                payload["cause"] = "drown"
            elif "lava" in low or "flame" in low or "fire" in low or "burn" in low:
                payload["cause"] = "fire"
            elif "starv" in low:
                payload["cause"] = "starve"
            km = _RE_DEATH_KILLER.search(line)
            if km:
                killer = (km.group("killer") or "").strip()
                # Strip trailing "using …"
                if " using " in killer.lower():
                    killer = killer[: killer.lower().index(" using ")].strip()
                if killer:
                    payload["killer"] = killer
                    payload["cause"] = "mob"
            if name in sp.online:
                sess = sp.online[name].setdefault("session_stats", {})
                sess["deaths"] = int(sess.get("deaths") or 0) + 1
            out.append(
                PresenceEvent(
                    event_type="player.died",
                    minecraft_name=name,
                    at=now,
                    payload=payload,
                )
            )
            return out

        m = _RE_ADVANCEMENT.search(line)
        if m:
            name = m.group("name")
            title = (m.group("title") or m.group("title2") or "").strip()
            out.append(
                PresenceEvent(
                    event_type="player.advancement",
                    minecraft_name=name,
                    at=now,
                    payload={"title": title} if title else {},
                )
            )
        return out

    def _replace_online(self, sp: ServerPresence, names: list[str], now: str) -> None:
        prev = set(sp.online.keys())
        nxt = set(names)
        for name in nxt - prev:
            sp.online[name] = {"minecraft_name": name, "joined_at": now}
            sp.pending_events.append(
                PresenceEvent(event_type="player.joined", minecraft_name=name, at=now)
            )
        for name in prev - nxt:
            sp.online.pop(name, None)
            sp.pending_events.append(
                PresenceEvent(event_type="player.left", minecraft_name=name, at=now)
            )
        # Preserve uuids for survivors
        for name in nxt & prev:
            sp.online.setdefault(name, {"minecraft_name": name})
        sp.dirty_roster = True

    def drain_events(self, server_id: str, *, limit: int = 50) -> list[dict[str, Any]]:
        sp = self.for_server(server_id)
        with self._lock:
            out: list[dict[str, Any]] = []
            while sp.pending_events and len(out) < limit:
                out.append(sp.pending_events.popleft().to_api())
            return out

    def peek_events(self, server_id: str, *, limit: int = 20) -> list[dict[str, Any]]:
        """Non-destructive view for live share (guild events drain owns the queue)."""
        sp = self.for_server(server_id)
        with self._lock:
            return [ev.to_api() for ev in list(sp.pending_events)[:limit]]

    def snapshot(self, server_id: str) -> dict[str, Any]:
        sp = self.for_server(server_id)
        with self._lock:
            return {
                "server_id": server_id,
                "player_count": len(sp.online),
                "max_players": sp.max_players,
                "players": sp.roster_payload(),
                "console_seq": sp.console_seq,
            }

    def mark_roster_synced(self, server_id: str) -> None:
        with self._lock:
            sp = self._servers.get(server_id)
            if sp:
                sp.dirty_roster = False


_tracker = PresenceTracker()


def get_presence_tracker() -> PresenceTracker:
    return _tracker
