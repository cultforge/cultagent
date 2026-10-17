"""Competitive score delta buffer — agent emits raw facts; API owns formula.

See docs/AGENT_RANKING_0.2.4.md. Launcher never posts score facts.
"""

from __future__ import annotations

import logging
import secrets
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cultagent.cloud.guild_payloads import MAX_SCORE_DELTAS

logger = logging.getLogger("cultagent.cloud.scoring")

_MAX_BUFFER = 500


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def read_server_facet(
    server_root: str | Path | None,
    *,
    record: Any | None = None,
) -> dict[str, Any]:
    """Facet axes for ranking metadata (game mode / cheats / difficulty / pack / version)."""
    facet: dict[str, Any] = {}
    props: dict[str, str] = {}
    if server_root is not None:
        path = Path(server_root) / "server.properties"
        if path.is_file():
            try:
                for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
                    raw = line.strip()
                    if not raw or raw.startswith("#") or "=" not in raw:
                        continue
                    key, _, value = raw.partition("=")
                    props[key.strip()] = value.strip()
            except OSError as exc:
                logger.debug("facet properties read failed: %s", exc)

    if props.get("gamemode"):
        facet["game_mode"] = props["gamemode"].lower()
    if props.get("difficulty"):
        facet["difficulty"] = props["difficulty"].lower()

    cheats = False
    for key in ("allow-cheats", "enable-command-block"):
        val = (props.get(key) or "").lower()
        if val in {"true", "1", "yes"}:
            cheats = True
            break
    facet["cheats"] = cheats

    if record is not None:
        mc = getattr(record, "minecraft_version", None) or (
            record.get("minecraft_version") if isinstance(record, dict) else None
        )
        loader = getattr(record, "loader", None) or (
            record.get("loader") if isinstance(record, dict) else None
        )
        build_id = getattr(record, "build_id", None) or (
            record.get("build_id") if isinstance(record, dict) else None
        )
        meta = getattr(record, "metadata", None) or (
            record.get("metadata") if isinstance(record, dict) else None
        )
        if isinstance(meta, dict) and not build_id:
            build_id = meta.get("build_id")
        if mc:
            facet["minecraft_version"] = str(mc)
        if loader:
            facet["loader"] = str(loader)
        if build_id:
            facet["pack_id"] = str(build_id)
        elif loader:
            facet["pack_id"] = str(loader)
    return facet


def event_to_delta(ev: dict[str, Any]) -> dict[str, Any] | None:
    """Map guild/presence event dict → raw score delta fact."""
    if not isinstance(ev, dict):
        return None
    etype = str(
        ev.get("event_type") or ev.get("type") or ev.get("kind") or ""
    ).strip()
    if not etype:
        return None
    name = (
        ev.get("minecraft_name")
        or ev.get("name")
        or ev.get("player")
        or ""
    )
    uuid_val = ev.get("minecraft_uuid") or ev.get("uuid")
    delta: dict[str, Any] = {
        "kind": etype,
        "at": ev.get("at") or _utc_now(),
    }
    if name:
        delta["minecraft_name"] = str(name)
    if uuid_val:
        delta["minecraft_uuid"] = str(uuid_val)
    payload = ev.get("payload")
    if isinstance(payload, dict) and payload:
        delta["payload"] = payload
    return delta


def _victim_type_from_name(raw: str) -> str:
    """Best-effort registry id from a console mob/player name."""
    text = (raw or "").strip()
    if not text:
        return "minecraft:unknown"
    # Already namespaced
    if ":" in text and " " not in text:
        return text.lower()
    # "Zombie" / "Cave Spider" → minecraft:zombie / minecraft:cave_spider
    slug = text.lower().replace(" ", "_")
    slug = "".join(c for c in slug if c.isalnum() or c == "_")
    return f"minecraft:{slug or 'unknown'}"


def aggregate_deltas_to_players(deltas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fold flat event deltas into contract ``players[].delta`` rows."""
    buckets: dict[str, dict[str, Any]] = {}

    def _row(d: dict[str, Any]) -> dict[str, Any]:
        uuid_val = str(d.get("minecraft_uuid") or "").strip()
        name = str(d.get("minecraft_name") or "").strip()
        key = uuid_val or name or "_unknown"
        row = buckets.get(key)
        if row is None:
            row = {
                "minecraft_uuid": uuid_val or None,
                "minecraft_name": name or None,
                "delta": {
                    "kills": [],
                    "deaths": [],
                    "advancements": [],
                    "playtime_seconds": 0,
                    "exploration": {},
                },
            }
            buckets[key] = row
        if uuid_val and not row.get("minecraft_uuid"):
            row["minecraft_uuid"] = uuid_val
        if name and not row.get("minecraft_name"):
            row["minecraft_name"] = name
        return row

    for d in deltas:
        if not isinstance(d, dict):
            continue
        kind = str(d.get("kind") or "")
        row = _row(d)
        delta = row["delta"]
        payload = d.get("payload") if isinstance(d.get("payload"), dict) else {}

        if kind in {"player.died", "death"}:
            cause = str(payload.get("cause") or "unknown")
            deaths: list[dict[str, Any]] = delta["deaths"]
            merged = False
            for item in deaths:
                if item.get("cause") == cause:
                    item["count"] = int(item.get("count") or 0) + 1
                    merged = True
                    break
            if not merged:
                deaths.append({"cause": cause, "count": 1})
            killer = payload.get("killer") or payload.get("killer_type")
            if killer:
                victim = _victim_type_from_name(str(killer))
                tags = list(payload.get("tags") or ["hostile"])
                kills: list[dict[str, Any]] = delta["kills"]
                # Attribute kill to the *victim* of the player? No — player died.
                # If we later emit player.kill events, they go below.
                _ = victim, tags, kills
        elif kind in {"player.kill", "entity.killed", "mob.killed"}:
            victim = str(
                payload.get("victim_type")
                or payload.get("entity")
                or payload.get("victim")
                or "minecraft:unknown"
            )
            if ":" not in victim:
                victim = _victim_type_from_name(victim)
            tags = list(payload.get("tags") or ["hostile"])
            count = int(payload.get("count") or 1)
            kills = delta["kills"]
            merged = False
            for item in kills:
                if item.get("victim_type") == victim:
                    item["count"] = int(item.get("count") or 0) + count
                    merged = True
                    break
            if not merged:
                kills.append({"victim_type": victim, "tags": tags, "count": count})
        elif kind in {"player.advancement", "advancement"}:
            adv = (
                payload.get("id")
                or payload.get("advancement")
                or payload.get("title")
            )
            if adv:
                advs: list[str] = delta["advancements"]
                text = str(adv)
                if text not in advs:
                    advs.append(text)
        elif kind in {"player.left", "playtime"}:
            secs = int(payload.get("playtime_seconds") or payload.get("seconds") or 0)
            # Exclude AFK when flagged
            if payload.get("afk"):
                secs = 0
            if secs > 0:
                delta["playtime_seconds"] = int(delta.get("playtime_seconds") or 0) + secs
        elif kind in {"exploration", "biome.discovered"}:
            explor = delta.setdefault("exploration", {})
            if "biomes_new" in payload:
                explor["biomes_new"] = int(explor.get("biomes_new") or 0) + int(
                    payload.get("biomes_new") or 0
                )

    out: list[dict[str, Any]] = []
    for row in buckets.values():
        dlt = row["delta"]
        # Drop empty delta sections for compact payloads
        clean: dict[str, Any] = {}
        if dlt.get("kills"):
            clean["kills"] = dlt["kills"]
        if dlt.get("deaths"):
            clean["deaths"] = dlt["deaths"]
        if dlt.get("advancements"):
            clean["advancements"] = dlt["advancements"]
        if int(dlt.get("playtime_seconds") or 0) > 0:
            clean["playtime_seconds"] = int(dlt["playtime_seconds"])
        if dlt.get("exploration"):
            clean["exploration"] = dlt["exploration"]
        if not clean:
            continue
        entry: dict[str, Any] = {"delta": clean}
        if row.get("minecraft_uuid"):
            entry["minecraft_uuid"] = row["minecraft_uuid"]
        if row.get("minecraft_name"):
            entry["minecraft_name"] = row["minecraft_name"]
        out.append(entry)
    return out


class ScoreDeltaBuffer:
    """Per-local-server queue of raw deltas with integrity counters."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._queues: dict[str, deque[dict[str, Any]]] = {}
        self._seq: dict[str, int] = {}
        self._fingerprint: dict[str, str] = {}
        self._process_salt = secrets.token_hex(8)

    def session_fingerprint(self, local_server_id: str) -> str:
        with self._lock:
            return self._fingerprint_unlocked(local_server_id)

    def _fingerprint_unlocked(self, local_server_id: str) -> str:
        fp = self._fingerprint.get(local_server_id)
        if not fp:
            fp = f"{self._process_salt}:{local_server_id}:{uuid.uuid4().hex[:12]}"
            self._fingerprint[local_server_id] = fp
        return fp

    def enqueue(self, local_server_id: str, deltas: list[dict[str, Any]]) -> int:
        if not deltas:
            return 0
        sid = str(local_server_id)
        added = 0
        with self._lock:
            q = self._queues.get(sid)
            if q is None:
                q = deque(maxlen=_MAX_BUFFER)
                self._queues[sid] = q
            for d in deltas:
                if isinstance(d, dict) and d.get("kind"):
                    q.append(d)
                    added += 1
        return added

    def enqueue_events(self, local_server_id: str, events: list[dict[str, Any]]) -> int:
        deltas = [d for ev in events if (d := event_to_delta(ev)) is not None]
        return self.enqueue(local_server_id, deltas)

    def drain(
        self, local_server_id: str, *, limit: int = MAX_SCORE_DELTAS
    ) -> tuple[list[dict[str, Any]], int, str]:
        """Return (deltas, batch_seq, session_fingerprint); seq increments when non-empty."""
        sid = str(local_server_id)
        with self._lock:
            q = self._queues.get(sid)
            fp = self._fingerprint_unlocked(sid)
            if not q:
                return [], self._seq.get(sid, 0), fp
            out: list[dict[str, Any]] = []
            while q and len(out) < limit:
                out.append(q.popleft())
            if out:
                self._seq[sid] = int(self._seq.get(sid, 0)) + 1
            seq = int(self._seq.get(sid, 0))
            return out, seq, fp

    def pending_count(self, local_server_id: str) -> int:
        with self._lock:
            q = self._queues.get(str(local_server_id))
            return len(q) if q else 0


_buffer: ScoreDeltaBuffer | None = None
_buffer_lock = threading.Lock()


def get_score_buffer() -> ScoreDeltaBuffer:
    global _buffer
    with _buffer_lock:
        if _buffer is None:
            _buffer = ScoreDeltaBuffer()
        return _buffer
