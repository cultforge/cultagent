"""Shared network types."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TunnelState(str, Enum):
    UNKNOWN = "unknown"
    OFFLINE = "offline"
    CONNECTING = "connecting"
    ONLINE = "online"
    ERROR = "error"


class NetworkStatus(BaseModel):
    provider: str
    status: TunnelState = TunnelState.OFFLINE
    target: str | None = None
    public_endpoint: str | None = None
    latency_ms: float | None = None
    details: dict[str, Any] = Field(default_factory=dict)
