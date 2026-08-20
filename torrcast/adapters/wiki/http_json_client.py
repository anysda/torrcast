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

from torrcast.domain.facts.settings import FACTS_BUDGET

_RESOLVE_TTL: Final = 600.0
#: Сколько ждём резолвер ПОСЛЕ отказа по сроку, секунды. Нитку поднял клиент - ему её
#: и закрывать, а закрыть её можно только дождавшись: убить нитку, залипшую в системном
#: резолвере, в Python нечем. Потолок у закрытия не свой: дольше, чем всё меню согласно
#: ждать справку, держать его незачем - ответа к этому сроку не ждёт уже никто.
_CLOSING: Final = FACTS_BUDGET


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
        self._looking: dict[str, threading.Thread] = {}
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
        """Адрес имени в отведённый срок; отказ по сроку уносит с собой поднятую нитку.

        Имя разрешается отдельной ниткой: ``getaddrinfo`` таймауту не подчиняется, и срок
        у него появляется только так. Нитку поднимает этот метод - он же за ней и
        закрывает: отказ объявляется по сроку, но отдаётся спрашивающему лишь после того,
        как резолвер отпустил нитку (:data:`_CLOSING`). Платит это ожидание фоновый
        спрашивающий, а не человек: потолок ожидания справки держит тот, кто позвал сюда,
        и от закрытия он не сдвигается.

        Опоздавший ответ - тоже ответ: его пишет сама нитка, и следующему спросившему
        адрес достаётся из памяти даром. Без этого молчащий резолвер стоил КАЖДОМУ запросу
        своей нитки, и за вечер их набиралось столько же, сколько было запросов.

        Не отпустил резолвер и за :data:`_CLOSING` - нитка остаётся ОДНА на имя: следующий
        спросивший ждёт её же (:meth:`_looker`), а не заводит вторую.
        """
        known = self._known(host)
        if known is not None:
            return known
        worker = self._looker(host)
        worker.join(timeout)
        found = self._known(host)
        if worker.is_alive():
            worker.join(_CLOSING)  # закрываем за собой то, что подняли
        if found is None:
            raise OSError(f"{host}: адрес не разрешён за {timeout:.1f} с")
        return found

    def _known(self, host: str) -> str | None:
        """Адрес имени из памяти клиента, пока он не протух."""
        with self._lock:
            hit = self._resolved.get(host)
        if hit is None or time.monotonic() - hit[0] >= _RESOLVE_TTL:
            return None
        return hit[1]

    def _looker(self, host: str) -> threading.Thread:
        """Нитка, разрешающая имя: одна на имя, а не одна на запрос.

        Память пишет она сама - тогда ответ, приехавший после срока, не пропадает даром.
        """

        def look() -> None:
            with contextlib.suppress(OSError):
                info = self.lookup(host)
                if info:
                    with self._lock:
                        self._resolved[host] = (time.monotonic(), str(info[0][4][0]))
            with self._lock:
                self._looking.pop(host, None)

        with self._lock:
            running = self._looking.get(host)
            if running is not None and running.is_alive():
                return running
            worker = threading.Thread(target=look, daemon=True, name=f"resolve-{host}")
            self._looking[host] = worker
        worker.start()
        return worker


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
