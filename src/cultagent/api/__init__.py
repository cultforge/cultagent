"""Loopback local management HTTP API (panel + JSON)."""

from __future__ import annotations

from typing import Any

from cultagent.app import CultAgentApp
from cultagent.web.app import create_web_app, serve_local_api

__all__ = ["create_asgi_app", "serve_local_api"]


def create_asgi_app(agent: CultAgentApp):
    return create_web_app(agent)
