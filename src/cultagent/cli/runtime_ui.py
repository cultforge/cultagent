"""Rich live HUD for `cf-agent run` (friendly mode)."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from rich import box
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.table import Table
from rich.text import Text

from cultagent.cli.display import print_status
from cultagent.cloud.activity_bridge import EventKind, classify_event
from cultagent.logging_setup import (
    FRIENDLY_EVENTS,
    add_friendly_sink,
    remove_friendly_sink,
)

if TYPE_CHECKING:
    from cultagent.app import CultAgentApp

console = Console()


@dataclass
class ActivityEvent:
    ts: str
    kind: EventKind
    text: str


_KIND_MARK = {
    "ok": ("+", "green"),
    "warn": ("!", "yellow"),
    "err": ("x", "red"),
    "info": ("*", "cyan"),
    "work": (">", "bright_blue"),
}


def _short_server_id(text: str) -> str:
    """srv_d108d837728c -> srv_d108d837."""

    def _trim(m: re.Match[str]) -> str:
        sid = m.group(0)
        return sid if len(sid) <= 16 else sid[:12]

    return re.sub(r"srv_[A-Za-z0-9_-]+", _trim, text)


class RuntimeHUD:
    """Compact status header + activity feed while the agent runs."""

    def __init__(self, agent: CultAgentApp, *, debug: bool = False) -> None:
        self.agent = agent
        self.debug = debug
        self._lock = threading.Lock()
        self._events: list[ActivityEvent] = []
        self._live: Live | None = None
        self._stopped = False

    def _on_event(self, line: str) -> None:
        text = _short_server_id(line.strip())
        # Skip redundant panel URL line — already shown in header
        if text.lower().startswith("local panel ready"):
            text = "Local panel ready"
        event = ActivityEvent(
            ts=datetime.now().strftime("%H:%M:%S"),
            kind=classify_event(text),
            text=text,
        )
        with self._lock:
            self._events.append(event)
            self._events = self._events[-16:]
        if self._live is not None:
            try:
                self._live.update(self.render())
            except Exception:  # noqa: BLE001
                pass

    def _header(self) -> Group:
        status = self.agent.public_status()
        identity = status.get("identity") if isinstance(status.get("identity"), dict) else {}
        local = status.get("local") if isinstance(status.get("local"), dict) else {}
        state = str(identity.get("status") or "unknown")
        node = str(identity.get("cloud_node_id") or identity.get("node_id") or "-")
        name = str(identity.get("display_name") or "Agent")
        bind = str(local.get("bind") or "127.0.0.1:8720")
        panel_url = f"http://{bind}/panel/dashboard"

        state_style = {
            "online": "bold green",
            "registering": "bold yellow",
            "degraded": "bold yellow",
            "offline": "bold red",
            "unregistered": "dim",
        }.get(state.lower(), "bold white")

        title = Text()
        title.append(f" {state.upper()} ", style=f"{state_style} reverse")
        title.append("  ")
        title.append(name, style="bold")

        meta = Text()
        meta.append(node, style="dim")
        meta.append("   ")
        meta.append(panel_url, style="green")

        return Group(title, meta)

    def _feed(self) -> Table:
        feed = Table(
            show_header=False,
            box=None,
            expand=True,
            padding=(0, 0),
            pad_edge=False,
        )
        feed.add_column(width=8, no_wrap=True)
        feed.add_column(width=3, no_wrap=True, justify="center")
        feed.add_column(overflow="ellipsis", no_wrap=True, ratio=1)

        with self._lock:
            events = list(self._events)

        if not events:
            feed.add_row(
                Text("", style="dim"),
                Text("*", style="dim"),
                Text(" Waiting for activity...", style="dim"),
            )
            return feed

        for ev in events[-12:]:
            mark, color = _KIND_MARK.get(ev.kind, ("*", "cyan"))
            msg_style = {
                "err": "bold red",
                "warn": "yellow",
                "work": "bright_blue",
                "ok": "green",
                "info": "",
            }.get(ev.kind, "")
            feed.add_row(
                Text(ev.ts, style="dim"),
                Text(mark, style=color),
                Text(f" {ev.text}", style=msg_style or None),
            )
        return feed

    def render(self) -> Panel:
        version = str(self.agent.public_status().get("version") or "?")
        body = Group(
            self._header(),
            Rule(style="dim"),
            Text("Activity", style="bold dim"),
            self._feed(),
            Text(""),
            Text("Ctrl+C to stop", style="dim italic"),
        )
        return Panel(
            body,
            title=f"[bold]CultForge Agent[/bold]  [dim]v{version}[/dim]",
            subtitle="[dim]friendly mode · --debug for tech logs[/dim]",
            subtitle_align="right",
            border_style="cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )

    def __enter__(self) -> RuntimeHUD:
        # Do not clear other sinks (cloud activity_bridge stays registered).
        with self._lock:
            for line in FRIENDLY_EVENTS:
                text = _short_server_id(str(line).strip())
                if text.lower().startswith("local panel ready"):
                    text = "Local panel ready"
                self._events.append(
                    ActivityEvent(
                        ts=datetime.now().strftime("%H:%M:%S"),
                        kind=classify_event(text),
                        text=text,
                    )
                )
        add_friendly_sink(self._on_event)
        self._live = Live(
            self.render(),
            console=console,
            refresh_per_second=4,
            transient=False,
            vertical_overflow="ellipsis",
        )
        self._live.start()
        return self

    def __exit__(self, *exc: Any) -> None:
        self._stopped = True
        remove_friendly_sink(self._on_event)
        if self._live is not None:
            self._live.stop()
            self._live = None

    def refresh(self) -> None:
        if self._live is not None:
            self._live.update(self.render())


def print_run_banner(agent: CultAgentApp, *, debug: bool) -> None:
    if debug:
        print_status(agent.public_status())
        console.print("[dim]Debug mode - technical logs enabled[/dim]\n")
        return
    # Friendly mode: HUD is the UI — keep the splash minimal.
    console.print()
