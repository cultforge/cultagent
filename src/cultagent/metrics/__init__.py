"""Local metrics collection."""

from __future__ import annotations

import platform
from typing import Any

import psutil


class MetricsCollector:
    async def collect(self) -> dict[str, Any]:
        vm = psutil.virtual_memory()
        disk = psutil.disk_usage("/")
        return {
            "system": {
                "os": platform.system(),
                "release": platform.release(),
                "architecture": platform.machine(),
                "cpu_percent": psutil.cpu_percent(interval=0.1),
                "cpu_count": psutil.cpu_count() or 0,
                "ram": {
                    "total": vm.total,
                    "available": vm.available,
                    "percent": vm.percent,
                },
                "disk": {
                    "total": disk.total,
                    "used": disk.used,
                    "free": disk.free,
                    "percent": disk.percent,
                },
            },
            "minecraft": {
                # Filled by server process introspection later.
                "tps": None,
                "mspt": None,
                "players": None,
                "entities": None,
                "chunks": None,
                "state": None,
            },
            "network": {
                "playit_state": None,
                "latency_ms": None,
                "tunnel_state": None,
                "endpoint_state": None,
            },
        }
