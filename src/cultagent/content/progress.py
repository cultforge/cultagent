"""Install progress reporting (CLI Rich bars, silent elsewhere)."""

from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Callable, Iterator

ProgressEvent = dict[str, Any]
ProgressCallback = Callable[[ProgressEvent], None]

_progress_cb: ContextVar[ProgressCallback | None] = ContextVar(
    "cultagent_install_progress", default=None
)


def report_progress(event: ProgressEvent) -> None:
    cb = _progress_cb.get()
    if cb is not None:
        try:
            cb(event)
        except Exception:  # noqa: BLE001 — never break installs for UI
            pass


@contextmanager
def install_progress(callback: ProgressCallback | None) -> Iterator[None]:
    token = _progress_cb.set(callback)
    try:
        yield
    finally:
        _progress_cb.reset(token)
