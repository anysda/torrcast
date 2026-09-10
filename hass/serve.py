"""Точка сборки HTTP-сервера моста."""

from __future__ import annotations

from http.server import ThreadingHTTPServer

from hass.bridge import Bridge
from hass.http_handler import _Handler
from hass.http_routes import ANY_INTERFACE, PORT

__all__ = ["ANY_INTERFACE", "PORT", "serve"]


def serve(bridge: Bridge, port: int = PORT, host: str = ANY_INTERFACE) -> ThreadingHTTPServer:
    """Поднять сервер моста; слушать он начинает в потоке вызывающего."""
    handler = type("_BoundHandler", (_Handler,), {"bridge": bridge})
    return ThreadingHTTPServer((host, port), handler)
