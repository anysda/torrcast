"""Поток вкладке с того же origin, что и страница."""

from __future__ import annotations

import http.client
import ssl

from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.http_server.hls_asset import HLS_ASSET
from web.answer import Answer
from web.refusal import refusal
from web.request import Request

PREFIX = "/hls/"
_TIMEOUT = 125.0
_FORWARDED = ("Accept-Ranges", "Content-Range", "Access-Control-Allow-Origin")


def hls(request: Request) -> Answer:
    """Проксировать манифест или сегмент живому серверу показа на петле."""
    name = request.path[len(PREFIX) :]
    if not HLS_ASSET.fullmatch(name):
        return refusal(404, "not_found")
    configured = load_config()
    connection = _connection(configured.transport, "127.0.0.1", configured.hls_port)
    headers = {}
    byte_range = next(
        (value for name, value in request.headers.items() if name.lower() == "range"), ""
    )
    if byte_range:
        headers["Range"] = byte_range
    try:
        connection.request("GET", f"/{name}", headers=headers)
        response = connection.getresponse()
        body = response.read()
    except (OSError, http.client.HTTPException):
        return refusal(502, "hls_unavailable")
    finally:
        connection.close()
    kind = response.getheader("Content-Type", "application/octet-stream")
    extra = tuple(
        (header, value)
        for header in _FORWARDED
        if (value := response.getheader(header)) is not None
    )
    return Answer(response.status, body, kind, extra=extra)


def _connection(scheme: str, host: str, port: int | None) -> http.client.HTTPConnection:
    if scheme != "https":
        return http.client.HTTPConnection(host, port, timeout=_TIMEOUT)
    # Петля не пересекает сеть, а сертификат сервера выписан на его LAN-адрес или имя,
    # не на 127.0.0.1. Внешний TLS заканчивается на веб-сервере/прокси страницы.
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return http.client.HTTPSConnection(host, port, timeout=_TIMEOUT, context=context)


__all__ = ["hls"]
