"""Получает JSON Wikimedia по HTTPS через IPv4 с ограниченным DNS-ожиданием."""

import contextlib
import http as http
import http.client
import json
import socket as socket
import ssl as ssl
import threading
import time
from collections.abc import Callable
from typing import Any, Final
from urllib.parse import urlencode

_RESOLVE_TTL: Final = 600.0


def _getaddrinfo(host: str) -> list[Any]:
    """Спросить у системы адреса хоста строго по IPv4."""
    return list(socket.getaddrinfo(host, None, socket.AF_INET, socket.SOCK_STREAM))


class HttpJsonClient:
    """HTTPS-клиент с прежней памятью IPv4-адресов на процесс.

    ``lookup`` - чем спрашиваются адреса. Умолчание ходит в систему; тест подставляет
    свой и получает ту же память и тот же собственный таймаут без похода в DNS.
    """

    def __init__(self, user_agent: str, lookup: Callable[[str], list[Any]] = _getaddrinfo) -> None:
        self.user_agent = user_agent
        self.lookup = lookup
        self._resolved: dict[str, tuple[float, str]] = {}
        self._lock = threading.Lock()

    def get(
        self,
        host: str,
        path: str,
        params: dict[str, str],
        headers: dict[str, str],
        timeout: float,
    ) -> Any:
        """Выполняет GET и разбирает JSON; неуспех оставляет исключением."""
        connection = _IPv4Connection(host, timeout=timeout, resolver=self._resolve)
        try:
            connection.request(
                "GET",
                f"{path}?{urlencode(params)}",
                headers={"User-Agent": self.user_agent, **headers},
            )
            response = connection.getresponse()
            if response.status != 200:
                raise OSError(f"{host} ответил {response.status}")
            return json.loads(response.read())
        finally:
            connection.close()

    def _resolve(self, host: str, timeout: float) -> str:
        now = time.monotonic()
        with self._lock:
            hit = self._resolved.get(host)
            if hit is not None and now - hit[0] < _RESOLVE_TTL:
                return hit[1]
        box: list[str] = []

        def look() -> None:
            with contextlib.suppress(OSError):
                info = self.lookup(host)
                if info:
                    box.append(str(info[0][4][0]))

        worker = threading.Thread(target=look, daemon=True)
        worker.start()
        worker.join(timeout)
        if not box:
            raise OSError(f"{host}: адрес не разрешён за {timeout:.1f} с")
        address = box[0]
        with self._lock:
            self._resolved[host] = (time.monotonic(), address)
        return address


class _IPv4Connection(http.client.HTTPSConnection):
    """Устанавливает проверенное TLS-соединение строго по IPv4."""

    context: ssl.SSLContext = ssl.create_default_context()

    def __init__(self, host: str, timeout: float, resolver: Any) -> None:
        super().__init__(host, timeout=timeout)
        self._resolver = resolver

    def connect(self) -> None:
        timeout = float(self.timeout) if self.timeout is not None else 1.2
        address = self._resolver(self.host, timeout)
        raw = socket.create_connection((address, self.port), self.timeout)
        self.sock = self.context.wrap_socket(raw, server_hostname=self.host)
