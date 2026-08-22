"""Interactive CLI helpers (yaspin / questionary / tqdm)."""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable, Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from typing import Any, TypeVar

from rich.console import Console

console = Console()
T = TypeVar("T")


def _in_async_loop() -> bool:
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def _run_blocking(fn: Callable[[], T]) -> T:
    """Run a blocking prompt.

    questionary/prompt_toolkit call ``asyncio.run()`` internally, which fails if we
    are already inside an event loop (e.g. Typer ``async def`` + ``asyncio.run``).
    Offload to a worker thread when that happens.
    """
    if not _in_async_loop():
        return fn()
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(fn).result()


@contextmanager
def spinner(text: str = "Working…"):
    """Yaspin on a real TTY; silent no-op when piped/non-TTY (avoids Windows encode errors)."""
    if not sys.stdout.isatty():
        yield None
        return

    try:
        from yaspin import yaspin
        from yaspin.spinners import Spinners

        # Avoid color/attrs on Windows consoles that warn; Spinners.line is ASCII-safe.
        # Spinners loads package data (spinners.json) — missing in some frozen builds.
        with yaspin(Spinners.line, text=text) as sp:
            yield sp
            return
    except Exception:  # noqa: BLE001 — ImportError, FileNotFoundError, frozen-data gaps
        pass

    with console.status(f"[cyan]{text}[/cyan]", spinner="dots"):
        yield None


def confirm(message: str, *, default: bool = False) -> bool:
    def _do() -> bool:
        try:
            import questionary
        except ImportError:
            return console.input(
                f"{message} [{'Y/n' if default else 'y/N'}] "
            ).strip().lower() in (
                "y",
                "yes",
                *(["", "y"] if default else []),
            )
        result = questionary.confirm(message, default=default).ask()
        return bool(result)

    return _run_blocking(_do)


def text_input(message: str, *, default: str = "") -> str | None:
    def _do() -> str | None:
        try:
            import questionary
        except ImportError:
            raw = console.input(f"{message} [{default}]: ").strip()
            return raw if raw else default
        return questionary.text(message, default=default).ask()

    return _run_blocking(_do)


def select(message: str, choices: Sequence[str], *, default: str | None = None) -> str | None:
    if not choices:
        return None
    choice_list = list(choices)
    default_choice = default or choice_list[0]

    def _do() -> str | None:
        try:
            import questionary
        except ImportError:
            console.print(f"[dim]{message}[/dim]")
            for i, c in enumerate(choice_list, 1):
                console.print(f"  [cyan]{i}[/cyan] {c}")
            raw = console.input("Choice #: ").strip()
            if raw.isdigit() and 1 <= int(raw) <= len(choice_list):
                return choice_list[int(raw) - 1]
            return default_choice

        return questionary.select(
            message, choices=choice_list, default=default_choice
        ).ask()

    return _run_blocking(_do)


def select_map(
    message: str,
    items: Sequence[T],
    *,
    label: Callable[[T], str],
) -> T | None:
    if not items:
        return None
    labels = [label(i) for i in items]
    picked = select(message, labels)
    if picked is None:
        return None
    for item, lab in zip(items, labels, strict=True):
        if lab == picked:
            return item
    return None


def progress(iterable: Iterable[T], *, desc: str = "", total: int | None = None) -> Iterable[T]:
    try:
        from tqdm import tqdm
    except ImportError:
        return iterable
    disable = not sys.stdout.isatty()
    return tqdm(iterable, desc=desc, total=total, leave=False, disable=disable)


@contextmanager
def install_progress_ui(title: str = "Installing build"):
    """Rich progress bar for build installs (files + Modrinth dependency pass)."""
    from cultagent.content.progress import install_progress

    if not sys.stdout.isatty():
        with install_progress(None):
            yield
        return

    from rich.progress import (
        BarColumn,
        MofNCompleteColumn,
        Progress,
        SpinnerColumn,
        TextColumn,
    )

    progress = Progress(
        SpinnerColumn(),
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(bar_width=28),
        MofNCompleteColumn(),
        TextColumn("[dim]{task.fields[detail]}"),
        console=console,
        expand=False,
        transient=True,
    )
    task_id: Any = None
    files_done = 0
    total_files = 0
    total_jars = 0

    def _short(path: str, limit: int = 42) -> str:
        path = path or ""
        if len(path) <= limit:
            return path
        return "…" + path[-(limit - 1) :]

    def _ensure_task(*, description: str, total: int | None) -> None:
        nonlocal task_id
        if task_id is None:
            task_id = progress.add_task(description, total=total, detail="")
        else:
            progress.update(
                task_id,
                description=description,
                total=float(total) if total is not None else None,
                completed=0,
                detail="",
            )

    def on_event(event: dict[str, Any]) -> None:
        nonlocal task_id, files_done, total_files, total_jars
        et = event.get("type")
        if et == "install_start":
            files_done = 0
            total_files = int(event.get("total_files") or 0)
            desc = f"{title} ({total_files} files)" if total_files else title
            _ensure_task(description=desc, total=total_files or None)
        elif et == "file_begin":
            path = str(event.get("path") or "")
            if task_id is not None:
                progress.update(task_id, detail=_short(path))
        elif et == "file_start":
            path = str(event.get("path") or "")
            if task_id is not None:
                progress.update(task_id, detail=_short(path))
        elif et == "file_progress":
            path = str(event.get("path") or "")
            downloaded = int(event.get("downloaded") or 0)
            total = event.get("total")
            cached = bool(event.get("cached"))
            if task_id is not None:
                if isinstance(total, int) and total > 0:
                    detail = f"{_short(path, 28)}  {downloaded}/{total}"
                elif cached:
                    detail = f"{_short(path, 28)}  cache"
                else:
                    detail = _short(path)
                progress.update(task_id, detail=detail)
        elif et == "file_skip":
            reason = str(event.get("reason") or "")
            if reason == "optional" or reason.startswith("env="):
                return
            files_done += 1
            if task_id is not None and total_files:
                progress.update(
                    task_id,
                    completed=min(files_done, total_files),
                )
        elif et in ("file_done", "file_error"):
            files_done += 1
            if task_id is not None and total_files:
                progress.update(
                    task_id,
                    completed=min(files_done, total_files),
                )
        elif et == "install_done":
            if task_id is not None and total_files:
                progress.update(
                    task_id,
                    completed=float(total_files),
                    detail="checking Modrinth dependencies…",
                )
            elif task_id is not None:
                progress.update(task_id, detail="checking Modrinth dependencies…")
        elif et == "deps_start":
            total_jars = int(event.get("total_jars") or 0)
            desc = f"Resolving dependencies ({total_jars} mods)" if total_jars else "Resolving dependencies"
            _ensure_task(description=desc, total=total_jars or None)
        elif et == "deps_jar":
            index = int(event.get("index") or 0)
            filename = str(event.get("filename") or "")
            if task_id is not None:
                progress.update(
                    task_id,
                    completed=float(index + 1),
                    detail=_short(filename, 36),
                )
        elif et == "deps_done":
            added = int(event.get("added") or 0)
            failed = int(event.get("failed") or 0)
            if task_id is not None:
                if total_jars:
                    progress.update(task_id, completed=float(total_jars))
                detail = "done"
                if added or failed:
                    detail = f"done  +{added} deps"
                    if failed:
                        detail += f"  {failed} failed"
                progress.update(task_id, detail=detail)

    with progress:
        with install_progress(on_event):
            yield


def find_listeners(port: int) -> list[dict[str, Any]]:
    """Return processes listening on TCP `port` (Windows/Unix via psutil)."""
    import psutil

    found: list[dict[str, Any]] = []
    seen: set[int] = set()
    for conn in psutil.net_connections(kind="inet"):
        if conn.status != psutil.CONN_LISTEN:
            continue
        if not conn.laddr or conn.laddr.port != port:
            continue
        pid = conn.pid
        if pid is None or pid in seen:
            continue
        seen.add(pid)
        try:
            proc = psutil.Process(pid)
            found.append(
                {
                    "pid": pid,
                    "name": proc.name(),
                    "cmdline": " ".join(proc.cmdline()) or proc.name(),
                    "create_time": proc.create_time(),
                }
            )
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            found.append({"pid": pid, "name": "?", "cmdline": "?", "create_time": None})
    return found


def kill_pids(pids: Sequence[int]) -> list[tuple[int, str]]:
    """Force-kill PIDs. Returns list of (pid, result message)."""
    import psutil

    results: list[tuple[int, str]] = []
    for pid in pids:
        try:
            proc = psutil.Process(pid)
            proc.kill()
            proc.wait(timeout=5)
            results.append((pid, "killed"))
        except psutil.NoSuchProcess:
            results.append((pid, "already gone"))
        except psutil.AccessDenied as exc:
            results.append((pid, f"denied: {exc}"))
        except Exception as exc:  # noqa: BLE001
            results.append((pid, f"error: {exc}"))
    return results
