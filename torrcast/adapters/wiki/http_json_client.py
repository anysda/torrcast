"""Получает JSON Wikimedia по HTTPS через IPv4 с ограниченным DNS-ожиданием."""

import http as http
import http.client
import json
import socket as socket
import ssl as ssl
from collections.abc import Callable
from typing import Any, Final
from urllib.parse import urlencode, urlsplit

from torrcast.adapters.wiki.address_memory import AddressMemory, _getaddrinfo
from torrcast.adapters.wiki.minute_budget import UPLOAD_HOST, MinuteBudget
from torrcast.adapters.wiki.request_lanes import RequestLanes

#: Потолок скачанного файла, байт. Постер шириной 500 точек весит сотню килобайт;
#: мегабайт тут - запас, а не мера, и стоит он ровно затем, чтобы чужой ответ не мог
#: занять память серва целиком.
_BODY_LIMIT: Final = 4 * 1024 * 1024
#: Сколько картинок Wikimedia качаем разом: больше двух их сервер файлов отвечает 429.
IMAGE_LANES: Final = 2


class HttpJsonClient(AddressMemory):
    """HTTPS-клиент с прежней памятью IPv4-адресов на процесс и минутным счётом Wikimedia.

    ``urgent`` - запрос видимого списка: он идёт впереди фона и не ждёт тишины дольше
    своего срока. Отказ по счёту или 429 клиент помнит (:meth:`troubled_since`): молчание
    источника в такую минуту не значит «картинки нет».
    """

    def __init__(self, user_agent: str, lookup: Callable[[str], list[Any]] = _getaddrinfo) -> None:
        super().__init__(lookup)
        self.user_agent = user_agent
        #: Полосы у каждого хоста свои: долгий SPARQL полки не держит выдержки Википедии.
        self._requests: dict[str, RequestLanes] = {}
        self._images = RequestLanes(IMAGE_LANES)
        self._minute = MinuteBudget()  # one per process: Wikimedia counts its sites together
        self.troubled_since = self._minute.troubled_since
        self.calm_at = self._minute.calm_at

    def get(
        self,
        host: str,
        path: str,
        params: dict[str, str],
        headers: dict[str, str],
        timeout: float,
        foreground: bool = False,
        urgent: bool = False,
    ) -> Any:
        """Выполняет GET и разбирает JSON; неуспех оставляет исключением."""
        with self._lock:
            lanes = self._requests.setdefault(host, RequestLanes())
        admitted = self._minute.admit(host, timeout, foreground, urgent)
        if not admitted or not lanes.acquire(timeout, foreground or urgent):
            raise OSError(f"{host}: request lane unavailable after {timeout:.1f} s")
        connection: _IPv4Connection | None = None
        try:
            connection = _IPv4Connection(host, timeout=timeout, resolver=self._resolve)
            connection.request(
                "GET",
                f"{path}?{urlencode(params)}",
                headers={"User-Agent": self.user_agent, **headers},
            )
            response = connection.getresponse()
            if response.status == 429:
                self._minute.throttled(host, response.getheader("Retry-After"))
            if response.status != 200:
                raise OSError(f"{host} ответил {response.status}")
            return json.loads(response.read())
        finally:
            if connection is not None:
                connection.close()
            lanes.release()

    def fetch(self, address: str, timeout: float, urgent: bool = False) -> bytes:
        """Забрать файл по полному адресу тем же соединением, что и JSON.

        Тем же - это буквально: та же память IPv4-адресов, тот же именной ``User-Agent``
        (без него Wikimedia отвечает 429 уже на второй запрос подряд) и тот же
        проверенный TLS. Разбора тут нет: приезжает картинка, и разбирать в ней нечего.

        Потолок :data:`_BODY_LIMIT` стоит на ЧТЕНИИ, а не на объявленной длине: чужой
        ответ вправе соврать в ``Content-Length``, а память тут наша.

        Хост берётся вместе с портом (``netloc``, а не ``hostname``): в бою порт всегда
        подразумеваемый, а вот проба, поднявшая свой сервер, живёт на случайном - и
        отброшенный порт увёл бы её в чужой 443, то есть измерялось бы не то.

        Файлы Wikimedia идут не больше :data:`IMAGE_LANES` разом, и их 429 глушит файлы
        до конца ``Retry-After``: без этого полка и выдача добивали сервер файлов подряд.
        """
        where = urlsplit(address)
        path = where.path + (f"?{where.query}" if where.query else "")
        files = where.netloc == UPLOAD_HOST
        if files and not (
            self._minute.admit(UPLOAD_HOST, timeout, False, urgent)
            and self._images.acquire(timeout, urgent)
        ):
            raise OSError(f"{UPLOAD_HOST}: image lane unavailable after {timeout:.1f} s")
        connection = _IPv4Connection(where.netloc, timeout=timeout, resolver=self._resolve)
        try:
            connection.request("GET", path, headers={"User-Agent": self.user_agent})
            response = connection.getresponse()
            if response.status == 429:
                self._minute.throttled(where.netloc, response.getheader("Retry-After"))
            if response.status != 200:
                raise OSError(f"{where.hostname}: HTTP {response.status}")
            return response.read(_BODY_LIMIT)
        finally:
            connection.close()
            if files:
                self._images.release()


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
