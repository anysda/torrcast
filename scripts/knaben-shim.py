#!/usr/bin/env python3
"""Локальный TLS-шим для API Knaben — обход DPI-троттлинга по SNI.

Домашний канал режет соединения по имени в SNI: с `api.knaben.org` заголовки приходят,
а тело обрывается на 16–20 КБ и висит (мелкие ответы проходят, крупные — нет). Тот же
IP того же Cloudflare с другим SNI отдаёт мегабайт за 0.38 с — то есть это не MTU, не
HTTP/2 и не сторона Knaben.

Псевдоним `knaben.eu` живёт на отдельном origin, которого в списке DPI нет, и origin
маршрутизирует по заголовку `Host`. Переопределить адрес API у Prowlarr нельзя — он
зашит константой в C#-индексере, — поэтому имя `api.knaben.org` прибивается в
`/etc/hosts` к этому шиму, а шим переспрашивает у origin с нужным `Host`.

Слушает только `127.0.0.1`; наружу не смотрит и ничего не кэширует.

    knaben-shim.py <upstream-url> <front-host> <cert> <key> [порт]
"""

from __future__ import annotations

import http.server
import socketserver
import ssl
import sys
import urllib.error
import urllib.request

#: Заголовки, которые имеет смысл донести до origin; остальное — от лукавого.
_PASS = ("Content-Type", "Accept", "User-Agent")
_TIMEOUT = 30


def main() -> int:
    upstream, front, cert, key = sys.argv[1:5]
    port = int(sys.argv[5]) if len(sys.argv) > 5 else 443

    class Handler(http.server.BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args: object) -> None:
            """В journald и так всё видно, а тело запроса светить незачем."""

        def _forward(self, method: str) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length) if length else None
            request = urllib.request.Request(upstream + self.path, data=body, method=method)
            request.add_header("Host", front)
            for name in _PASS:
                if self.headers.get(name):
                    request.add_header(name, self.headers[name])
            try:
                with urllib.request.urlopen(request, timeout=_TIMEOUT) as response:
                    data = response.read()
                    status = response.status
                    ctype = response.headers.get("Content-Type", "application/json")
            except urllib.error.HTTPError as exc:  # ответ есть, просто не 2xx — отдаём как есть
                data, status = exc.read(), exc.code
                ctype = exc.headers.get("Content-Type", "application/json")
            except Exception as exc:
                data, status, ctype = str(exc).encode(), 502, "text/plain"
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            self._forward("GET")

        def do_POST(self) -> None:
            self._forward("POST")

    class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True

    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    server = Server(("127.0.0.1", port), Handler)
    server.socket = context.wrap_socket(server.socket, server_side=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
