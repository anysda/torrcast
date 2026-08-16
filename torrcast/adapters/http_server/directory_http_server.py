"""Раздаёт каталог HLS встроенным многопоточным HTTP-сервером."""

from __future__ import annotations

import functools
import http.server
import threading

from torrcast.domain.server_address import ServerAddress


class _Handler(http.server.SimpleHTTPRequestHandler):
    """Добавляет CORS к ответам встроенного файлового обработчика."""

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        super().end_headers()

    def log_message(self, _format: str, *_args: object) -> None:
        return


class DirectoryHttpServer:
    """Реализация порта HTTP-сервера для локального каталога."""

    def __init__(self, host: str = "0.0.0.0", public_host: str = "127.0.0.1") -> None:
        self._host = host
        self._public_host = public_host
        self._server: http.server.ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self, directory: str, port: int) -> ServerAddress:
        handler = functools.partial(_Handler, directory=directory)
        self._server = http.server.ThreadingHTTPServer((self._host, port), handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        actual_port = int(self._server.server_address[1])
        return ServerAddress(f"http://{self._public_host}:{actual_port}")

    def stop(self) -> None:
        if self._server is None:
            return
        self._server.shutdown()
        self._server.server_close()
        if self._thread is not None:
            self._thread.join()
        self._server = None
        self._thread = None
