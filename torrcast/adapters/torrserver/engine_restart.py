"""Поднять TorrServer заново, когда он перестал отвечать, и повторить вопрос один раз.

🔴 TC-1199. MatriX.143 умеет молча повиснуть: HTTP жив (``/echo`` и ``get`` по базе
отвечают), а любой новый ``add`` не отвечает никогда. Сам себя он из этого не выводит, и
systemd его не поднимет: процесс жив. Раньше человек получал «TorrServer не отвечает» и
чинил руками. Теперь вопрос, не дождавшийся ответа при живом ``/echo``, убивает службу и
поднимает её заново.

Рядом то же другим лицом: служба упала (паника в горутине ``GotInfo``, когда ``rem`` закрыл
кэш раздачи, которую ещё будил ``get`` или ``add``; стенд, 400 пачек: падения, не завис).
Тогда соединение отвергнуто, и systemd поднимает службу сам через ``RestartSec``: это
дожидаемся, а не поднимаем сами. Не поднял - поднимаем.

Подъём один на процесс: параллельные вопросы, упавшие на том же зависе, ждут идущего
подъёма и повторяют вопрос, а не перезапускают службу каждый по разу. Не наш TorrServer
(чужой адрес) и TorrServer без службы (песочница, dev) не трогаются: ошибка уходит дальше
прежней.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Final
from urllib.parse import urlsplit

from torrcast.adapters.system_clock import CLOCK
from torrcast.adapters.torrserver.engine_service import EngineService
from torrcast.domain.server_down_error import ServerDownError
from torrcast.ports.clock import Clock
from torrcast.ports.journal.slot import journal

#: Сколько ждать ``add``. Здоровый отвечает за миллисекунды, со спорным замком базы
#: (см. :mod:`~torrcast.adapters.torrserver.add_once`) до 2.6 с на стенде; десять секунд
#: - с запасом вчетверо, а не прежние тридцать, которые человек стоял перед отказом.
ADD_TIMEOUT: Final = 10.0

#: Сколько ждать, пока systemd поднимет упавшую службу сам: ``RestartSec=5`` и старт.
COMEBACK: Final = 12.0

#: Сколько ждать ``/echo`` от поднятой нами службы. Здоровый старт на стенде - секунды.
UP: Final = 30.0

STEP: Final = 0.25
LOCAL: Final = frozenset({"127.0.0.1", "localhost", "::1"})


def _silent(_on: bool) -> None:
    return None


class EngineRestart:
    """Ответ на вопрос службе, при зависе или падении - после её подъёма."""

    def __init__(self, service: EngineService | None = None, clock: Clock = CLOCK) -> None:
        self._service = service or EngineService()
        self._clock = clock
        self._lock = threading.Lock()
        self._rounds = 0
        self._back_last = False
        #: Кому сказать, что служба поднимается (``True``) и что подъём кончился
        #: (``False``). Назначает композиционный корень: вкладка показа.
        self.tell: Callable[[bool], None] = _silent

    def answered[T](self, base_url: str, alive: Callable[[], bool], ask: Callable[[], T]) -> T:
        rounds = self._rounds
        try:
            return ask()
        except ServerDownError as exc:
            if not self._mend(base_url, alive, rounds, exc):
                raise
        return ask()

    def _mend(
        self, base_url: str, alive: Callable[[], bool], rounds: int, exc: ServerDownError
    ) -> bool:
        import requests

        cause = exc.__cause__
        hung = isinstance(cause, requests.Timeout)
        if not hung and not isinstance(cause, requests.ConnectionError):
            return False
        if urlsplit(base_url).hostname not in LOCAL:
            return False
        with self._lock:
            if self._rounds != rounds:  # пока ждали ответа, подъём уже был: его итог
                return self._back_last
            if not self._service.known():
                return False
            began = self._clock.monotonic()
            self.tell(True)
            try:
                back = self._back(alive, hung)
            finally:
                self.tell(False)
            seconds = round(self._clock.monotonic() - began, 1)
            journal().emit("torrserver", "restart", hung=hung, back=back, seconds=seconds)
            self._rounds += 1
            self._back_last = back
            return back

    def _back(self, alive: Callable[[], bool], hung: bool) -> bool:
        """Служба снова отвечает: systemd поднял её сам, или подняли мы."""
        if not hung and self._service.coming() and self._wait(alive, COMEBACK):
            return True
        return self._service.restart() and self._wait(alive, UP)

    def _wait(self, alive: Callable[[], bool], seconds: float) -> bool:
        deadline = self._clock.monotonic() + seconds
        while not alive():
            if self._clock.monotonic() >= deadline:
                return False
            self._clock.sleep(STEP)
        return True


#: Подъём движка этого процесса: служба на машине одна.
ENGINE: Final = EngineRestart()

__all__ = ["ADD_TIMEOUT", "ENGINE", "EngineRestart"]
