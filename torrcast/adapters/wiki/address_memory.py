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
#: After how long a silent lookup gets one spare, seconds. A resolver that lost its UDP answer
#: waits out its own retry (five seconds by default); a fresh query is usually back in tens of ms.
_SPARE_AFTER: Final = 1.0


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
        self._looking: dict[str, list[threading.Thread]] = {}
        self._answered: dict[str, threading.Event] = {}
        self._shunned: dict[str, dict[str, float]] = {}  # host -> stalled address -> until
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
        спросивший ждёт её же (:meth:`_looker`), а не заводит вторую. The one exception is the
        spare after :data:`_SPARE_AFTER`: a lost UDP answer holds the system resolver for its
        whole retry, and one fresh query per silent name is what the first screen can afford.
        """
        known = self._known(host)
        if known is not None:
            return known
        began = time.monotonic()
        workers = [self._looker(host)]
        answered = self._arrival(host)
        if not answered.wait(min(timeout, _SPARE_AFTER)) and workers[0].is_alive():
            workers.append(self._looker(host, spare=True))
        answered.wait(max(0.0, began + timeout - time.monotonic()))
        found = self._known(host)
        closing = time.monotonic() + _CLOSING
        for worker in workers if found is None else ():
            worker.join(max(0.0, closing - time.monotonic()))  # закрываем за собой поднятое
        if found is None:
            raise OSError(f"{host}: address not resolved in {timeout:.1f} s")
        return found

    def stalled(self, host: str, address: str | None) -> None:
        """Forget an address that went silent mid-request and pass it over for a while.

        A CDN name rotates edges, and one edge may freeze every connection after its first
        bytes: kept for the whole TTL it starved every request to the name. The next request
        asks again and takes the first answer not passed over; none left - the first one.
        """
        if address is None:
            return
        with self._lock:
            self._shunned.setdefault(host, {})[address] = time.monotonic() + _RESOLVE_TTL
            if self._resolved.get(host, (0.0, ""))[1] == address:
                del self._resolved[host]

    def _pick(self, host: str, info: list[Any]) -> str:
        """The first answered address not passed over by :meth:`stalled`, else the first."""
        now = time.monotonic()
        with self._lock:
            shunned = self._shunned.get(host, {})
            fresh = [str(one[4][0]) for one in info if shunned.get(str(one[4][0]), 0.0) <= now]
        return fresh[0] if fresh else str(info[0][4][0])

    def _known(self, host: str) -> str | None:
        """Адрес имени из памяти клиента, пока он не протух."""
        with self._lock:
            hit = self._resolved.get(host)
        if hit is None or time.monotonic() - hit[0] >= _RESOLVE_TTL:
            return None
        return hit[1]

    def _arrival(self, host: str) -> threading.Event:
        """Set once the name's current round has an address or no lookup left running."""
        with self._lock:
            return self._answered[host]

    def _looker(self, host: str, spare: bool = False) -> threading.Thread:
        """Нитка, разрешающая имя: одна на имя, а не одна на запрос; ``spare`` - вторая.

        Память пишет она сама - тогда ответ, приехавший после срока, не пропадает даром.
        The spare is one more fresh query for a lookup that went silent, never a third one.
        """

        def look() -> None:
            with contextlib.suppress(OSError):
                info = self.lookup(host)
                if info:
                    address = self._pick(host, info)
                    with self._lock:
                        self._resolved[host] = (time.monotonic(), address)
                    arrived.set()
            with self._lock:
                mine = self._looking.get(host, [])
                if worker in mine:  # a thread of an ended round leaves the new one alone
                    mine.remove(worker)
                    if not mine:
                        arrived.set()

        with self._lock:
            running = [one for one in self._looking.get(host, ()) if one.is_alive()]
            if running and self._answered[host].is_set():
                running = []  # that round is over: a hung lookup there is nobody's answer
            if running and (not spare or len(running) > 1):
                return running[-1]
            if not running:
                self._answered[host] = threading.Event()
            arrived = self._answered[host]
            worker = threading.Thread(target=look, daemon=True, name=f"resolve-{host}")
            self._looking[host] = [*running, worker]
            worker.start()  # under the lock: a thread not yet started is not alive to the next
        return worker
