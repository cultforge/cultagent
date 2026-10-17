"""Aternos-style live share — POST /v1/agent/guild/live (and personal).

Agent token only. Competitive score totals stay on score/batch.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from cultagent.cloud.guild_payloads import build_live_body
from cultagent.config import parse_server_properties

logger = logging.getLogger("cultagent.cloud.live_share")


def clamp_live_interval(seconds: int | float | None) -> float:
    try:
        val = float(seconds if seconds is not None else 5)
    except (TypeError, ValueError):
        val = 5.0
    return max(3.0, min(10.0, val))


def _playtime_seconds(joined_at: str | None) -> int:
    if not joined_at:
        return 0
    try:
        t0 = datetime.fromisoformat(str(joined_at).replace("Z", "+00:00"))
        now = datetime.now(timezone.utc)
        return max(0, int((now - t0).total_seconds()))
    except ValueError:
        return 0


def _world_from_server(root: str | Path | None) -> dict[str, Any] | None:
    if root is None:
        return None
    path = Path(root)
    props_path = path / "server.properties"
    if not props_path.is_file():
        return None
    try:
        props = parse_server_properties(props_path.read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return None
    name = str(props.get("level-name") or "world").strip() or "world"
    return {
        "name": name,
        "dimension": "minecraft:overworld",
    }


def build_live_players_from_presence(snap: dict[str, Any]) -> list[dict[str, Any]]:
    """Map presence snapshot → R.md live player rows (best-effort fields only)."""
    rows: list[dict[str, Any]] = []
    for p in snap.get("players") or []:
        if not isinstance(p, dict):
            continue
        name = str(p.get("minecraft_name") or p.get("name") or "").strip()
        uuid_val = str(p.get("minecraft_uuid") or p.get("uuid") or "").strip()
        if not name and not uuid_val:
            continue
        row: dict[str, Any] = {}
        if name:
            row["minecraft_name"] = name
        if uuid_val:
            row["minecraft_uuid"] = uuid_val
        for key in ("ping_ms", "gamemode", "dimension", "health", "food", "position"):
            if p.get(key) is not None:
                row[key] = p[key]
        stats: dict[str, Any] = {}
        session = p.get("session_stats") if isinstance(p.get("session_stats"), dict) else {}
        stats.update(session)
        # Derive playtime from joined_at when not already set
        if "playtime_seconds" not in stats:
            secs = _playtime_seconds(p.get("joined_at"))
            if secs >= 5:
                stats["playtime_seconds"] = secs
        if stats:
            row["session_stats"] = stats
        rows.append(row)
    return rows


class LiveSharePublisher:
    """Throttle and publish live snapshots for primary-bound running servers."""

    def __init__(self, app: Any) -> None:
        self.app = app
        self._last_post: dict[str, float] = {}

    def _interval(self) -> float:
        return clamp_live_interval(
            getattr(self.app.config.cloud, "live_share_interval_seconds", 5)
        )

    def due(self, key: str, *, force: bool = False) -> bool:
        if force:
            return True
        now = time.monotonic()
        last = self._last_post.get(key, 0.0)
        return (now - last) >= self._interval()

    def mark(self, key: str) -> None:
        self._last_post[key] = time.monotonic()

    async def flush(self, agent_token: str) -> dict[str, Any]:
        """Post live for each primary binding whose local process is running."""
        from cultagent.cloud.client import CloudError
        from cultagent.cloud.presence import get_presence_tracker
        from cultagent.cloud.scoring import read_server_facet

        summary: dict[str, Any] = {"posted": 0, "skipped": 0, "errors": 0}
        tracker = get_presence_tracker()
        bindings = list(self.app.bindings.active_bindings() or [])

        for binding in bindings:
            if not self.app.bindings.is_primary_binding(binding):
                summary["skipped"] = int(summary["skipped"]) + 1
                continue

            workload_id = str(binding.get("workload_id") or "").strip()
            scope = str(binding.get("scope") or "guild")
            guild_server_id = binding.get("guild_server_id") or binding.get("server_id")
            personal_server_id = binding.get("personal_server_id")
            local_id = (
                binding.get("local_server_id")
                or binding.get("resource_id")
                or self.app.bindings.local_server_id_for(
                    str(personal_server_id or guild_server_id or "")
                )
            )
            if not workload_id or not local_id:
                summary["skipped"] = int(summary["skipped"]) + 1
                continue

            key = f"{scope}:{local_id}"
            if not self.due(key):
                continue

            try:
                running = self.app.servers.is_process_running(str(local_id))
            except Exception:  # noqa: BLE001
                running = False
            if not running:
                # Still post stopped occasionally so launcher clears live UI
                if not self.due(key + ":stopped"):
                    continue
                reported_state = "stopped"
            else:
                reported_state = "running"

            rec = None
            try:
                rec = await self.app.servers.get(str(local_id))
            except Exception:  # noqa: BLE001
                rec = None

            snap = tracker.snapshot(str(local_id))
            players = build_live_players_from_presence(snap)
            events = tracker.peek_events(str(local_id), limit=20) if running else []

            facet = read_server_facet(rec.path if rec else None, record=rec)
            mc_version = (
                (rec.minecraft_version if rec else None)
                or facet.get("minecraft_version")
            )
            world = _world_from_server(rec.path if rec else None)

            tps = None
            mspt = None
            try:
                metrics = await self.app.metrics.collect()
                mc = metrics.get("minecraft") if isinstance(metrics, dict) else None
                if isinstance(mc, dict):
                    if mc.get("tps") is not None:
                        tps = float(mc["tps"])
                    if mc.get("mspt") is not None:
                        mspt = float(mc["mspt"])
            except Exception:  # noqa: BLE001
                pass

            body = build_live_body(
                workload_id=workload_id,
                guild_server_id=str(guild_server_id) if guild_server_id and scope != "personal" else None,
                personal_server_id=str(personal_server_id) if personal_server_id and scope == "personal" else None,
                reported_state=reported_state,
                minecraft_version=str(mc_version) if mc_version else None,
                player_count=int(snap.get("player_count") or len(players)),
                max_players=snap.get("max_players"),
                tps=tps,
                mspt=mspt,
                world=world,
                server_facet=facet,
                players=players,
                events=events,
            )

            try:
                if scope == "personal" and personal_server_id:
                    await self.app.cloud_client.post_personal_live(
                        agent_token,
                        str(personal_server_id),
                        body=body,
                    )
                elif guild_server_id:
                    await self.app.cloud_client.post_guild_live(
                        agent_token,
                        body=body,
                    )
                else:
                    summary["skipped"] = int(summary["skipped"]) + 1
                    continue
                self.mark(key)
                if reported_state != "running":
                    self.mark(key + ":stopped")
                summary["posted"] = int(summary["posted"]) + 1
            except CloudError as exc:
                summary["errors"] = int(summary["errors"]) + 1
                code = getattr(exc, "status_code", None)
                msg = str(exc).lower()
                if code in {403, 404} or "not_verified" in msg or "no_primary" in msg:
                    logger.info(
                        "live share skipped for %s: %s",
                        local_id,
                        exc,
                    )
                else:
                    logger.debug("live share failed for %s: %s", local_id, exc)
            except Exception as exc:  # noqa: BLE001
                summary["errors"] = int(summary["errors"]) + 1
                logger.debug("live share error for %s: %s", local_id, exc)

        return summary
