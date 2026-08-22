"""Logging setup — technical formatters vs friendly console mode."""

from __future__ import annotations

import logging
import re
from collections import deque
from pathlib import Path
from typing import Callable


_TECH_FORMAT = logging.Formatter(
    "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# Recent friendly lines for the runtime HUD (newest last).
FRIENDLY_EVENTS: deque[str] = deque(maxlen=40)
_FRIENDLY_SINKS: list[Callable[[str], None]] = []


def add_friendly_sink(callback: Callable[[str], None]) -> None:
    if callback not in _FRIENDLY_SINKS:
        _FRIENDLY_SINKS.append(callback)


def remove_friendly_sink(callback: Callable[[str], None]) -> None:
    try:
        _FRIENDLY_SINKS.remove(callback)
    except ValueError:
        pass


def clear_friendly_sinks(*, clear_events: bool = False) -> None:
    _FRIENDLY_SINKS.clear()
    if clear_events:
        FRIENDLY_EVENTS.clear()


def _emit_friendly(line: str) -> None:
    FRIENDLY_EVENTS.append(line)
    for sink in list(_FRIENDLY_SINKS):
        try:
            sink(line)
        except Exception:  # noqa: BLE001
            pass


def friendly_line(record: logging.LogRecord) -> str | None:
    """Map a LogRecord to a short human sentence, or None to hide it."""
    msg = record.getMessage()
    name = record.name
    low = msg.lower()

    if record.levelno >= logging.ERROR:
        if "revoked" in low:
            return "Cloud rejected this agent - token revoked"
        if "crash-loop" in low:
            return "Server keeps crashing - auto-restart paused"
        if "local api failed" in low:
            return "Local panel failed to start"
        if "heartbeat failed" in low or "control plane tick failed" in low:
            return "Having trouble reaching CultForge"
        cmd_fail = _friendly_command_failure(msg)
        if cmd_fail:
            return cmd_fail
        short = msg.split("\n", 1)[0]
        if len(short) > 80:
            short = short[:77] + "..."
        return f"Something went wrong: {short}"

    if "CultAgent panel on" in msg:
        return "Local panel ready"

    if "CultAgent started" in msg:
        return "Agent started"
    if "CultAgent stopped" in msg:
        return "Agent stopped"
    if "cloud using https poll" in low:
        return "Cloud linked (polling — no WebSocket yet)"
    if "cloud websocket advertised" in low or "cloud websocket now available" in low:
        return "Cloud WebSocket available — switching..."
    if "connected to cultforge realtime" in low:
        return "Connected to CultForge realtime"
    if "realtime dropped" in low or "realtime session ended" in low:
        return "Realtime dropped — back to polling"
    if "cloud realtime disabled" in low:
        return "Cloud realtime disabled — poll only"
    if "playit started" in low:
        return "playit tunnel agent started"
    if "playit stopped" in low:
        return "playit tunnel agent stopped"
    if "playit auto-start" in low:
        return "playit auto-start skipped or failed"
    if "is unregistered" in low:
        return "Not logged in yet - run cf-agent login"
    if "auto-starting server" in low:
        return "Starting a server on boot..."
    if "Resolving" in msg and "crash log" in low:
        return "Reading crash log and installing missing mods"
    if "auto-restarting crashed" in low:
        return "Restarting a crashed server..."
    if "reported crashed" in low:
        return "A server crashed"
    if "control plane: executed" in low:
        m = re.search(r"(\d+)", msg)
        n = m.group(1) if m else "some"
        return f"Running {n} cloud command(s)..."
    if name.endswith("audit") or msg.startswith("audit "):
        return _friendly_audit(msg)
    if "heartbeat failed" in low:
        return "Cloud heartbeat failed - retrying"
    if "non-loopback bind" in low:
        return "Panel bind forced to localhost for safety"
    if low.startswith("starting ") and "(cwd=" in low:
        return "Launching Minecraft process..."
    if "stopping" in low and "via" in low:
        return "Stopping Minecraft process..."
    if "ignore terminate" in low or "killing" in low and "server" in low:
        return "Force-stopping a stuck server..."
    if "created server" in low:
        return "Created a new server folder..."
    if "installer completed" in low:
        return "Server install finished"
    if "installer failed" in low:
        return "Server install failed"
    if "downloading" in low and "server" in low:
        return "Downloading server files..."
    if "detected java" in low:
        return "Found a Java runtime"
    if "no java runtime" in low:
        return "No Java found - install Java to run servers"
    if "creating zip backup" in low:
        return "Creating a backup..."
    if "restoring backup" in low:
        return "Restoring a backup..."

    # Hide noisy technical chatter in friendly mode
    if name.startswith("uvicorn"):
        return None
    if record.levelno < logging.WARNING and name.startswith("cultagent"):
        # Drop unmapped info/debug from console (still in file)
        return None
    if record.levelno >= logging.WARNING:
        short = msg.split("\n", 1)[0]
        if len(short) > 100:
            short = short[:97] + "..."
        return short
    return None


_CMD_LABELS = {
    "server.start": "start the server",
    "server.stop": "stop the server",
    "server.restart": "restart the server",
    "server.create": "create the server",
    "server.console.execute": "run that console command",
    "server.backup.create": "create a backup",
    "server.backup.restore": "restore a backup",
    "server.mods.install": "install a mod",
    "server.mods.remove": "remove a mod",
    "server.mods.resolve": "resolve mod dependencies",
}


def _friendly_command_failure(msg: str) -> str | None:
    m = re.search(r"Command failed:\s*(\S+)", msg, re.I)
    if not m:
        return None
    cmd = m.group(1)
    label = _CMD_LABELS.get(cmd)
    if label:
        return f"Couldn't {label}"
    plain = cmd.replace(".", " ")
    return f"Couldn't complete: {plain}"


def _friendly_audit(msg: str) -> str | None:
    # audit server.stop resource=srv_... result=requested
    op = ""
    m = re.search(r"audit\s+(\S+)", msg)
    if m:
        op = m.group(1)
    resource = ""
    rm = re.search(r"resource=(\S+)", msg)
    if rm:
        resource = rm.group(1)
    result = ""
    rsm = re.search(r"result=(\S+)", msg)
    if rsm:
        result = rsm.group(1)

    labels = {
        "server.start": "Starting server",
        "server.stop": "Stopping server",
        "server.restart": "Restarting server",
        "server.create": "Creating server",
        "server.console.execute": "Sending console command",
        "server.crash_detected": "Server crash detected",
        "server.auto_restart": "Auto-restarting server",
        "server.backup.create": "Creating backup",
        "server.backup.restore": "Restoring backup",
        "server.mods.install": "Installing mod",
        "server.mods.remove": "Removing mod",
        "server.mods.resolve": "Resolving mod dependencies",
    }
    base = labels.get(op, op.replace(".", " ") if op else "Working")
    if resource and resource not in {"None", "none"}:
        rid = resource if len(resource) <= 16 else resource[:12]
        base = f"{base} ({rid})"
    if result in {"ok", "requested"}:
        return base + "..."
    if result in {"error", "failed", "fail"}:
        return f"Couldn't finish: {base.lower().rstrip('.')}"
    if result:
        return f"{base} - {result}"
    return base + "..."


class FriendlyHandler(logging.Handler):
    """Console handler that prints plain sentences and feeds the HUD."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            line = friendly_line(record)
            if not line:
                return
            _emit_friendly(line)
            # Also print immediately if no HUD sink is attached yet
            if not _FRIENDLY_SINKS:
                stream = getattr(self, "stream", None)
                if stream is None:
                    import sys

                    stream = sys.stderr
                stream.write(line + "\n")
                stream.flush()
        except Exception:  # noqa: BLE001
            self.handleError(record)


def setup_logging(
    level: str = "INFO",
    log_file: Path | None = None,
    *,
    debug: bool = False,
) -> logging.Logger:
    """Configure cultagent (+ optionally quiet uvicorn) logging.

    Friendly mode (debug=False): human lines on console, full detail in log file.
    Debug mode: classic technical console format + uvicorn noise.
    """
    root = logging.getLogger("cultagent")
    # Reset handlers so run --debug / friendly can switch
    for h in list(root.handlers):
        root.removeHandler(h)

    level_name = level.upper() if debug else "INFO"
    root.setLevel(getattr(logging, level_name, logging.INFO))
    root.propagate = False

    if debug:
        stream = logging.StreamHandler()
        stream.setFormatter(_TECH_FORMAT)
        root.addHandler(stream)
    else:
        friendly = FriendlyHandler()
        friendly.setLevel(logging.INFO)
        root.addHandler(friendly)

    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(_TECH_FORMAT)
        file_handler.setLevel(logging.DEBUG)
        root.addHandler(file_handler)

    # Uvicorn / access logs
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uv = logging.getLogger(name)
        uv.handlers.clear()
        if debug:
            uv.setLevel(logging.INFO)
            uv.propagate = True
        else:
            uv.setLevel(logging.CRITICAL)
            uv.propagate = False
            uv.addHandler(logging.NullHandler())

    return root
