"""Память IPv4-адресов Wikimedia на процесс с собственным сроком DNS-ожидания."""

import contextlib
import socket
import threading
import time
from collections.abc import Callable
from typing import Any, Final

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


class AddressMemory:
    """Адреса имён: одна нитка резолвера на имя, ответ живёт :data:`_RESOLVE_TTL`.

    ``lookup`` - чем спрашиваются адреса. Умолчание ходит в систему; тест подставляет
    свой и получает ту же память и тот же собственный таймаут без похода в DNS.
    """

    def __init__(self, lookup: Callable[[str], list[Any]] = _getaddrinfo) -> None:
        self.lookup = lookup
        self._resolved: dict[str, tuple[float, str]] = {}
        self._looking: dict[str, threading.Thread] = {}
        self._lock = threading.Lock()

    def warm(self, host: str) -> None:
        """Пустить разрешение имени заранее и вернуться сразу: ответа тут не ждут.

        Нитка та же и память та же, что у :meth:`_resolve`, - поэтому греть можно сколько
        угодно раз: вторая нитка на то же имя не поднимается (:meth:`_looker`), а уже
        известный адрес не спрашивается заново (:meth:`_known`). Зачем греют - в
        :meth:`~torrcast.ports.json_client.JsonClient.warm`.
        """
        if self._known(host) is None:
            self._looker(host)

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
            raise OSError(f"{host}: address not resolved in {timeout:.1f} s")
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
