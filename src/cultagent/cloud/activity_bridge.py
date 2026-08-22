"""Bridge friendly Activity HUD + Minecraft console tails into cloud telemetry.

Phase 1: embed recent lines in POST /v1/agent/telemetry metrics.
Phase 2 (API): dedicated /v1/agent/activity when advertised in manifest.
"""

from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Literal

from cultagent.logging_setup import FRIENDLY_EVENTS, add_friendly_sink, remove_friendly_sink

if TYPE_CHECKING:
    from cultagent.servers.manager import ServerManager

EventKind = Literal["ok", "warn", "err", "info", "work"]

ACTIVITY_MAX = 40
CONSOLE_LINES_PER_SERVER = 50
CONSOLE_MAX_SERVERS = 3
LINE_MAX_CHARS = 240
CONSOLE_BUDGET_BYTES = 24_000


def classify_event(line: str) -> EventKind:
    low = line.lower()
    if any(w in low for w in ("went wrong", "failed", "couldn't", "could not", "error", "crash")):
        return "err"
    if any(w in low for w in ("warning", "trouble", "retry", "not logged")):
        return "warn"
    if low.endswith("...") or any(
        w in low
        for w in (
            "starting",
            "stopping",
            "restarting",
            "launching",
            "downloading",
            "creating",
            "sending",
        )
    ):
        return "work"
    if any(w in low for w in ("ready", "started", "stopped", "finished", "found")):
        return "ok"
    return "info"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _truncate(text: str, *, max_chars: int = LINE_MAX_CHARS) -> str:
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3] + "..."


@dataclass(frozen=True)
class ActivityLine:
    ts: str
    kind: EventKind
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"ts": self.ts, "kind": self.kind, "text": self.text}


class ActivityBridge:
    """Ring buffer of friendly Activity lines; always-on while the agent runs."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._lines: deque[ActivityLine] = deque(maxlen=ACTIVITY_MAX)
        self._registered = False

    def start(self) -> None:
        """Register friendly sink and seed from in-memory HUD history."""
        if self._registered:
            return
        with self._lock:
            for raw in FRIENDLY_EVENTS:
                text = _truncate(str(raw))
                if not text:
                    continue
                self._lines.append(
                    ActivityLine(ts=_utc_now_iso(), kind=classify_event(text), text=text)
                )
        add_friendly_sink(self._on_friendly)
        self._registered = True

    def stop(self) -> None:
        if not self._registered:
            return
        remove_friendly_sink(self._on_friendly)
        self._registered = False

    def _on_friendly(self, line: str) -> None:
        text = _truncate(str(line))
        if not text:
            return
        event = ActivityLine(ts=_utc_now_iso(), kind=classify_event(text), text=text)
        with self._lock:
            self._lines.append(event)

    def snapshot_activity(self) -> dict[str, Any]:
        with self._lock:
            lines = [ln.to_dict() for ln in self._lines]
        return {"schema_version": 1, "lines": lines}

    def push_line(self, text: str, *, kind: EventKind | None = None) -> None:
        """Test/helper: append a line without going through logging."""
        cleaned = _truncate(text)
        if not cleaned:
            return
        event = ActivityLine(
            ts=_utc_now_iso(),
            kind=kind or classify_event(cleaned),
            text=cleaned,
        )
        with self._lock:
            self._lines.append(event)

    def clear(self) -> None:
        with self._lock:
            self._lines.clear()

    async def snapshot_consoles(self, servers: ServerManager) -> list[dict[str, Any]]:
        """Last N console lines for up to CONSOLE_MAX_SERVERS running processes."""
        out: list[dict[str, Any]] = []
        budget = CONSOLE_BUDGET_BYTES
        for record in await servers.list_servers():
            if len(out) >= CONSOLE_MAX_SERVERS:
                break
            if not servers.is_process_running(record.server_id):
                continue
            try:
                snap = await servers.console_read(
                    record.server_id, limit=CONSOLE_LINES_PER_SERVER
                )
            except Exception:  # noqa: BLE001
                continue
            raw_lines = snap.get("lines") or []
            lines: list[dict[str, Any]] = []
            for item in raw_lines:
                if not isinstance(item, dict):
                    continue
                text = _truncate(str(item.get("text") or ""))
                if not text:
                    continue
                ts_val = item.get("ts")
                if isinstance(ts_val, (int, float)):
                    ts_str = datetime.fromtimestamp(
                        float(ts_val), tz=timezone.utc
                    ).strftime("%Y-%m-%dT%H:%M:%SZ")
                else:
                    ts_str = str(ts_val or _utc_now_iso())
                entry = {
                    "seq": int(item.get("seq") or 0),
                    "ts": ts_str,
                    "text": text,
                }
                entry_size = len(text) + 48
                if budget - entry_size < 0 and lines:
                    break
                budget -= entry_size
                lines.append(entry)
            out.append(
                {
                    "server_id": record.server_id,
                    "seq": int(snap.get("seq") or 0),
                    "lines": lines,
                }
            )
            if budget <= 0:
                break
        return out


# Process-wide bridge used by CultAgentApp + control plane.
_bridge = ActivityBridge()


def get_activity_bridge() -> ActivityBridge:
    return _bridge
