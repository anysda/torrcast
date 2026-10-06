"""Поднять TorrServer заново, когда он перестал отвечать, и повторить вопрос один раз.

🔴 TC-1199. MatriX.143 умеет молча повиснуть: HTTP жив (``/echo`` и ``get`` по базе
отвечают), а любой новый ``add`` не отвечает никогда. Сам себя он из этого не выводит, и
systemd его не поднимет: процесс жив. Раньше человек получал «TorrServer не отвечает» и
чинил руками. Теперь вопрос, не дождавшийся ответа, убивает службу и поднимает её заново.

Рядом то же другим лицом: служба упала (паника в горутине ``GotInfo``, когда ``rem`` закрыл
кэш раздачи, которую ещё будил ``get`` или ``add``; стенд, 400 пачек: падения, не завис).
Тогда соединение отвергнуто, и systemd поднимает службу сам через ``RestartSec``: это
дожидаемся, а не поднимаем сами. Не поднял - поднимаем.

🔴 Убивать можно не всегда, и где нельзя, вопрос дожидается прежнего полного срока и
отдаёт прежний отказ:

- служба жива (``/echo``) и кто-то читает из неё раздачу: идёт чей-то показ, и KILL
  оборвал бы его ради одного медленного ``add`` (замок базы на слабой машине). Не
  сказала, читают ли, - тоже не убиваем: живой показ дороже лишнего ожидания;
- служба уже убита нами меньше :data:`PAUSE` назад: завис, который подъём не лечит,
  иначе убивал бы службу на каждом новом вопросе. Отметка общая для моста и процессов
  показа (:mod:`.kill_stamp`);
- службу остановил человек (``inactive``): отказ сразу, без ожидания. Служба в
  движении (``deactivating``, ``activating``) - ждём ``COMEBACK``, вдруг это ``restart``.

Подъём один на процесс: параллельные вопросы, упавшие на том же зависе, ждут идущего
подъёма и повторяют вопрос. Отказ человека от подъёма показа обрывает ожидание: новое
«Играть» ждёт снятый показ :data:`hass.starting.YIELD_SECONDS`, и подъём службы ради
брошенного показа не вправе съесть это время. Не наш TorrServer (чужой адрес) и
TorrServer без службы (песочница, dev) не трогаются.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Final, Literal, Protocol
from urllib.parse import urlsplit

from torrcast.adapters.system_clock import CLOCK
from torrcast.adapters.torrserver.engine_service import EngineService
from torrcast.adapters.torrserver.kill_stamp import KillStamp
from torrcast.domain.server_down_error import ServerDownError
from torrcast.ports.abandon.slot import abandoned
from torrcast.ports.clock import Clock
from torrcast.ports.journal.slot import journal

#: Сколько ждать ``add`` у своей службы, прежде чем решать, не повисла ли она. Здоровый
#: отвечает за миллисекунды, со спорным замком базы (:mod:`.add_once`) до 2.6 с на стенде.
ADD_TIMEOUT: Final = 10.0

#: Сколько ждать, пока systemd поднимет упавшую службу сам: ``RestartSec=5`` и старт.
COMEBACK: Final = 12.0

#: Сколько ждать ``/echo`` от поднятой нами службы. Здоровый старт на стенде - доли секунды.
UP: Final = 15.0

#: Не убивать службу чаще: завис, который подъём не вылечил, получает прежний отказ.
PAUSE: Final = 600.0

STEP: Final = 0.25
LOCAL: Final = frozenset({"127.0.0.1", "localhost", "::1"})

#: Итог разбора отказа: спросить заново, дождаться остатка прежнего срока или отказать.
Verdict = Literal["again", "rest", "no"]


class _Probes(Protocol):
    """Что подъём спрашивает у клиента службы, решая, можно ли её убить."""

    def alive(self) -> bool: ...

    def reading(self) -> bool | None: ...


def _silent() -> None:
    return None


class EngineRestart:
    """Ответ на вопрос службе, при зависе или падении - после её подъёма."""

    def __init__(
        self,
        service: EngineService | None = None,
        clock: Clock = CLOCK,
        stamp: KillStamp | None = None,
    ) -> None:
        self._service = service or EngineService()
        self._stamp = stamp or KillStamp()
        self._clock = clock
        self._lock = threading.Lock()
        self._rounds = 0
        self._last: Verdict = "no"
        self._killed: float | None = None
        #: Кому сказать, что служба повисла или упала и поднимается заново. Назначает
        #: композиционный корень: экран ожидания вкладки показа.
        self.tell: Callable[[], None] = _silent

    def answered[T](
        self, base_url: str, probes: _Probes, ask: Callable[[float], T], timeout: float, add: bool
    ) -> T:
        """Ответ на ``ask(срок)``; ``add`` своей службы ждёт сперва :data:`ADD_TIMEOUT`.

        Короткий срок (щуп показа, уборка на выходе: три секунды) службу не чинит вовсе:
        молчание для них не беда по договору, и их тайм-аут - не довод, что служба повисла.
        """
        mends = urlsplit(base_url).hostname in LOCAL and timeout >= ADD_TIMEOUT
        first = min(timeout, ADD_TIMEOUT) if add and mends else timeout
        rounds = self._rounds
        try:
            return ask(first)
        except ServerDownError as exc:
            verdict = self._mend(probes, rounds, exc) if mends else "no"
            if abandoned() or verdict == "no" or (verdict == "rest" and first >= timeout):
                raise
        return ask(timeout - first if verdict == "rest" else first)

    def _mend(self, probes: _Probes, rounds: int, exc: ServerDownError) -> Verdict:
        import requests

        cause = exc.__cause__
        hung = isinstance(cause, requests.Timeout)
        if not hung and not isinstance(cause, requests.ConnectionError):
            return "no"
        if abandoned():
            return "no"
        with self._lock:
            if self._rounds != rounds:  # пока ждали ответа, подъём уже был: его итог
                return self._last
            if not self._service.known():
                return "rest"
            began = self._clock.monotonic()
            verdict = self._back(probes, hung)
            seconds = round(self._clock.monotonic() - began, 1)
            journal().emit("torrserver", "restart", hung=hung, verdict=verdict, seconds=seconds)
            self._rounds += 1
            self._last = verdict
            return verdict

    def _back(self, probes: _Probes, hung: bool) -> Verdict:
        """Служба снова отвечает (systemd поднял её сам, или подняли мы), или почему нет."""
        state = self._service.state()
        if state == "inactive":  # остановил человек: не наше дело её поднимать
            return "no"
        told = state == "deactivating" or (not hung and state != "failed")
        if told:
            self.tell()
            if self._waited(probes, COMEBACK):
                return "again"
            if state == "deactivating":
                return "no"
        spared = self._spared(probes, hung)
        if spared:
            journal().emit("torrserver", "spared", why=spared)
            return "rest" if hung else "no"
        self._killed = self._clock.wall()
        self._stamp.mark(self._killed)
        if not told:
            self.tell()
        return "again" if self._service.restart() and self._waited(probes, UP) else "no"

    def _spared(self, probes: _Probes, hung: bool) -> str:
        """Почему службу убивать нельзя; пусто - можно."""
        killed = max((t for t in (self._killed, self._stamp.at()) if t is not None), default=None)
        if killed is not None and 0 <= self._clock.wall() - killed < PAUSE:
            return "pause"
        if hung and probes.alive():
            reading = probes.reading()
            if reading is not False:
                return "reading" if reading else "unknown"
        return ""

    def _waited(self, probes: _Probes, seconds: float) -> bool:
        deadline = self._clock.monotonic() + seconds
        while not probes.alive():
            if self._clock.monotonic() >= deadline or abandoned():
                return False
            self._clock.sleep(STEP)
        return True


#: Подъём движка этого процесса: служба на машине одна.
ENGINE: Final = EngineRestart()

__all__ = ["ADD_TIMEOUT", "ENGINE", "EngineRestart"]
