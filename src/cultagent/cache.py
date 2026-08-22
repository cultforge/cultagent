"""Agent download / content cache helpers."""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any


def cache_file_path(cache_dir: Path, *, sha256: str | None = None, name: str = "") -> Path:
    """Content-addressed path under cache/downloads."""
    root = Path(cache_dir) / "downloads"
    if sha256:
        digest = sha256.lower()
        return root / digest[:2] / digest
    safe = "".join(c for c in name if c.isalnum() or c in ("-", "_", ".", "+"))[:120]
    return root / "_named" / (safe or "blob")


def clear_agent_cache(cache_dir: Path) -> dict[str, Any]:
    """Remove contents of the agent cache directory. Returns summary."""
    cache_dir = Path(cache_dir)
    if not cache_dir.exists():
        return {"ok": True, "path": str(cache_dir), "removed_bytes": 0, "removed_entries": 0}
    removed_bytes = 0
    removed_entries = 0
    for child in list(cache_dir.iterdir()):
        try:
            if child.is_file() or child.is_symlink():
                removed_bytes += child.stat().st_size
                child.unlink(missing_ok=True)
                removed_entries += 1
            elif child.is_dir():
                size = sum(p.stat().st_size for p in child.rglob("*") if p.is_file())
                shutil.rmtree(child, ignore_errors=True)
                removed_bytes += size
                removed_entries += 1
        except OSError:
            continue
    return {
        "ok": True,
        "path": str(cache_dir),
        "removed_bytes": removed_bytes,
        "removed_entries": removed_entries,
    }
