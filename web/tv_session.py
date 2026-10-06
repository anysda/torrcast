"""Одна живая связь с приёмником ТВ на весь процесс страницы: ``/api/to-tv``/``/api/to-web``.

Каст «на ТВ» (ТЗ §7.5) не поднимает новый показ - поток, упаковка и перекод те же, что у
вкладки. Соединение с приёмником ровно одно: второе было бы вторым сендером той же
медиасессии, а не сендером ради числа, как :class:`hass.volume.Volume` для громкости.
`TvSession` - единственный держатель, которым делятся маршруты и пульт (:mod:`hass.tab_cast`).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from torrcast.domain.position import Position
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.seek_place import seek_place
from torrcast.domain.segment_container import SegmentContainer
from torrcast.ports.receiver import Receiver
from web.live_receiver import POLL_SECONDS, live_receiver
from web.tv_fresh import tv_fresh
from web.tv_idle import tv_idle
from web.tv_load import tv_load
from web.tv_poll import TvPoll
from web.tv_settled import RECHECK_SECONDS, tv_settled
from web.tv_since import tv_since
from web.tv_stale import tv_stale
from web.tv_steer import tv_steer


@dataclass
class TvSession:
    """Держит приёмник ТВ между «на ТВ» и «на комп». Профиль и контейнер LOAD - из ящика
    показа (:mod:`web.to_tv`), как у прямого показа на ТВ; :attr:`profile` - умолчание."""

    #: Ключ показа, отданного на ТВ. Каст принадлежит ЯЩИКУ: пока он идёт, вкладка молчит
    #: про место (ТЗ §7.5.3), но ящик мог уехать под другой показ - молчи она про НЕГО,
    #: новая картина не двинула бы закладку ни разу и навсегда осталась в ``starting``.
    key: str = ""
    factory: Callable[[str, Profile], Receiver] = live_receiver
    profile: Profile = CAUTIOUS
    poll_seconds: float = POLL_SECONDS
    _receiver: Receiver | None = field(default=None, init=False, repr=False)
    _heard: Position | None = field(default=None, init=False, repr=False)
    _since: float | None = field(default=None, init=False, repr=False)  # :func:`tv_since`
    _asked: float = field(default=0.0, init=False, repr=False)  # миг прошлой просьбы статуса
    _aim: tuple[float, float] | None = field(default=None, init=False, repr=False)
    _doubt: Position | None = field(default=None, init=False, repr=False)
    _alive: Callable[[], bool] | None = field(default=None, init=False, repr=False)
    _poll: TvPoll = field(default_factory=TvPoll, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def active(self) -> bool:
        """Идёт ли каст на ТВ прямо сейчас."""
        return self._receiver is not None

    def owns(self, key: str) -> bool:
        """Каст идёт и он про ЭТОТ показ; чужой ключ - «не мой», а не «каста нет»."""
        return self._receiver is not None and self.key == key

    def heard(self, key: str) -> Position | None:
        """Последний доклад ТВ про ЭТОТ показ на сейчас (:func:`tv_fresh`); не его - ``None``."""
        spot = self._heard if self.owns(key) else None
        return None if spot is None else tv_fresh(spot, self._since, time.monotonic())

    def settle(self, key: str) -> bool:
        """Идёт ли каст ИМЕННО этого ящика; каст осиротел - снять его и ответить «нет».

        🔴 Каст держится ящиком, а не временем: ушедший в браузере на ДРУГУЮ картину оставлял
        старый каст играть навсегда, и вкладка каждые 10 с тянула свою секунду к чужой
        картине (07-09-2026: за 116 с 12 откатов на ~5 с). Связь отпускается тихо.
        """
        if self._receiver is None:
            return False
        if self.key == key:
            return True
        self._release()
        return False

    def start(
        self,
        address: str,
        title: str,
        url: str,
        at: float,
        echo: Callable[[Position], None] | None = None,
        key: str = "",
        alive: Callable[[], bool] | None = None,
        profile: Profile | None = None,
        container: SegmentContainer | None = None,
    ) -> None:
        """Позвать приёмник ТВ тем же LOAD, что и прямой показ на ТВ (:func:`web.tv_load.tv_load`).

        ``echo`` слышит каждый опрос приёмника: пока каст идёт, место показа знает ТВ, а
        не вкладка (ТЗ §7.5.3), и опрос - единственный источник секунды.
        ``alive`` спрашивается перед каждым опросом: сказал «нет» - каст снимается (:meth:`_pump`).
        """
        self._release()  # повторное «На ТВ» не оставляет прежнюю связь висеть и опрашиваться
        receiver = self.factory(address, profile or self.profile)
        tv_load(receiver, url, title, at, container)
        self._receiver = receiver
        self._alive = alive
        self.key = key
        self._poll.arm(lambda stop_poll: self._pump(receiver, stop_poll, echo))

    def stop(self) -> float:
        """Снять каст и назвать секунду, на которой он стоял; без каста - ноль.

        Секунда - ПОСЛЕДНИЙ УСЛЫШАННЫЙ опрос, а не свежее чтение: то на излёте отдало 4.8 при
        показе на ~14-й секунде (живой приёмник 10-09-2026), «На комп» отматывал назад.
        ``_heard`` читается ПОД замком, как и пишется: иначе ловился недописанный доклад.
        """
        receiver, self._receiver, self.key = self._receiver, None, ""
        if receiver is None:
            return 0.0
        self._poll.disarm(self.poll_seconds)
        with self._lock:
            heard, self._heard = self._heard, None
            at = heard.pos if heard is not None else receiver.position().pos
            receiver.stop(quit_app=True)
        return at

    def steer(self, command: str, arg: float) -> bool:
        """Пульт каста прямо приёмнику ТВ (:func:`web.tv_steer.tv_steer`); нечем - ``False``."""
        with self._lock:
            receiver = self._receiver
            if receiver is None:
                return False
            seek = command == "seekby"
            base = receiver.position() if seek and self._heard is None else self._heard
            if not tv_steer(receiver, base, command, arg):
                return False
            if seek and base is not None:  # доклад у цели `_backwards` не глотает
                self._heard, self._aim = None, (base.pos, seek_place(base.pos, arg, base.dur))
        return True

    def left(self, key: str, duration: float) -> float | None:
        """Остаток серии ``key`` до секунды перед концом по месту ТВ; каст не её - ``None``.

        Перемотку ТВ отсчитывает от СВОЕГО места (:meth:`steer`), а снимок моста мог отстать
        от него на опрос: остаток по снимку уводил цель «следующей серии» за конец файла.
        Место - сырой доклад, а не досчитанный :meth:`heard`: от него же считает и :meth:`steer`.
        """
        with self._lock:
            receiver = self._receiver
            if receiver is None or self.key != key:
                return None
            spot = self._heard or receiver.position()
        return max(0.0, duration - spot.pos - 1.0)

    def _release(self) -> None:
        """Закрыть прежнюю связь без чтения её места - её никто не спрашивал."""
        receiver, self._receiver, self.key = self._receiver, None, ""
        self._heard = self._aim = self._doubt = None
        if receiver is None:
            return
        self._poll.disarm(self.poll_seconds)
        with self._lock:
            receiver.stop(quit_app=True)

    def _pump(
        self,
        receiver: Receiver,
        stop_poll: threading.Event,
        echo: Callable[[Position], None] | None,
    ) -> None:
        """Опрашивать приёмник, пока сеанс жив; чужому сеансу опрос не отвечает.

        Слушателю место уходит ВНЕ замка - держать его на файловой записи значило бы
        заставлять ``stop`` ждать. 🔴 Показ снят - каст снимается тут же: чтение места у
        погасшего потока поднимало LOAD заново («retrying LOAD»; живой приёмник 11-09-2026).
        """
        while not stop_poll.wait(min(self.poll_seconds, RECHECK_SECONDS if self._doubt else 1e9)):
            if self._alive is not None and not self._alive():
                if self._receiver is receiver:
                    self._release()
                return
            with self._lock:
                if self._receiver is not receiver:
                    return
                asked, self._asked = self._asked, time.monotonic()
                spot = tv_idle(receiver.position(), self.heard(self.key), self._aim)
                if self._backwards(spot):
                    continue
                self._since, self._heard = tv_since(self._heard, spot, asked), spot
            if echo is not None:
                echo(spot)

    def _backwards(self, spot: Position) -> bool:
        """Доклад назад - излёт, кроме своей перемотки и устоявшегося места (`tv_settled`)."""
        stale, self._aim = tv_stale(spot, self._heard, self._aim)
        self._doubt = spot if stale and not tv_settled(spot, self._doubt) else None
        return self._doubt is not None


#: Один держатель на процесс страницы: оба маршрута спрашивают именно его.
SESSION: TvSession = TvSession()
