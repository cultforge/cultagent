"""Controlled command surface for CultAgent."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from cultagent.constants import COMMANDS

logger = logging.getLogger("cultagent.commands")

CommandHandler = Callable[["CommandContext"], Awaitable[dict[str, Any]]]


@dataclass
class CommandContext:
    name: str
    params: dict[str, Any] = field(default_factory=dict)
    actor_id: str | None = None
    resource_id: str | None = None
    # Injected by the app at runtime.
    app: Any = None


@dataclass
class CommandResult:
    ok: bool
    command: str
    data: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "command": self.command,
            "data": self.data,
            "error": self.error,
        }


class CommandRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, CommandHandler] = {}

    def register(self, name: str, handler: CommandHandler) -> None:
        if name not in COMMANDS:
            logger.warning("Registering non-standard command: %s", name)
        self._handlers[name] = handler

    def list_commands(self) -> list[str]:
        return sorted(self._handlers.keys())

    async def dispatch(self, ctx: CommandContext) -> CommandResult:
        handler = self._handlers.get(ctx.name)
        if handler is None:
            return CommandResult(ok=False, command=ctx.name, error="unknown_command")
        try:
            data = await handler(ctx)
            return CommandResult(ok=True, command=ctx.name, data=data)
        except PermissionError as exc:
            return CommandResult(ok=False, command=ctx.name, error=f"forbidden: {exc}")
        except Exception as exc:  # noqa: BLE001 — command boundary
            logger.exception("Command failed: %s", ctx.name)
            return CommandResult(ok=False, command=ctx.name, error=str(exc))


def build_default_registry() -> CommandRegistry:
    from cultagent.commands import handlers

    registry = CommandRegistry()
    handlers.register_all(registry)
    return registry
