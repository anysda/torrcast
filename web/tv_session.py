"""Одна живая связь с приёмником ТВ на весь процесс страницы: `` /api/to-tv``/``/api/to-web``.

Каст «на ТВ» (ТЗ §7.5) не поднимает новый показ - поток, упаковка и перекод остаются
теми же, что уже идут для вкладки. Соединение с приёмником при этом ровно одно: второе,
поднятое поверх первого, было бы вторым сендером той же медиасессии, а не безобидным
вторым сендером ради числа, каким законно живёт :class:`hass.volume.Volume` для громкости
(её же докстрока и называет разницу). `TvSession` - тот самый единственный держатель,
которым делятся оба маршрута, а не пара независимых соединений.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field

from torrcast.domain.position import Position
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.segment_container import SegmentContainer
from torrcast.ports.receiver import Receiver
from web.live_receiver import POLL_SECONDS, live_receiver
from web.tv_load import tv_load


@dataclass
class TvSession:
    """Держит приёмник ТВ между запросом «на ТВ» и запросом «на комп».

    Профиль и контейнер кусков LOAD - те же, что у прямого показа на ТВ: :mod:`web.to_tv`
    берёт их из ящика показа, а :attr:`profile` - только умолчание для ящика без них.
    """

    #: Ключ показа, отданного на ТВ. Каст принадлежит ЯЩИКУ, из которого он поднят: пока
    #: он идёт, вкладка помолчит про место (ТЗ §7.5.3), - но ящик мог уехать под другой
    #: показ, и молчать про НЕГО уже нельзя, иначе новая картина не двинет закладку ни
    #: разу и навсегда останется в ``starting``.
    key: str = ""
    factory: Callable[[str, Profile], Receiver] = live_receiver
    profile: Profile = CAUTIOUS
    poll_seconds: float = POLL_SECONDS
    _receiver: Receiver | None = field(default=None, init=False, repr=False)
    _heard: Position | None = field(default=None, init=False, repr=False)
    _alive: Callable[[], bool] | None = field(default=None, init=False, repr=False)
    _stop_poll: threading.Event | None = field(default=None, init=False, repr=False)
    _poll: threading.Thread | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def active(self) -> bool:
        """Идёт ли каст на ТВ прямо сейчас."""
        return self._receiver is not None

    def owns(self, key: str) -> bool:
        """Каст идёт и он про ЭТОТ показ; чужой ключ - «не мой», а не «каста нет»."""
        return self._receiver is not None and self.key == key

    def settle(self, key: str) -> bool:
        """Идёт ли каст ИМЕННО этого ящика; каст осиротел - снять его и ответить «нет».

        🔴 Каст держится ящиком, а не временем: зритель, ушедший в браузере на ДРУГУЮ
        картину, оставлял старый каст играть на ТВ навсегда - «На комп» относился к
        показу, которого уже нет. Вкладке отвечали ``tv: true``, и она КАЖДЫЕ 10 СЕКУНД
        тянула свою секунду назад, к чужой картине на ТВ (стенд `.104` 07-09-2026: за
        116 с показа 12 откатов на ~5 с, ход 22.8 с вместо 116).

        Секунду осиротевшего каста никто не спрашивает - связь отпускается тем же тихим
        путём, что и при повторном «На ТВ».
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

        Старую связь, если она была, отпускаем первой: иначе повторное нажатие «На ТВ»
        оставляло бы прежнее соединение висеть незакрытым и опрашиваемым.

        ``echo`` слышит каждый опрос приёмника: пока каст идёт, место показа знает ТВ, а
        не вкладка (ТЗ §7.5.3), и опрос из повода «держать ``current_time`` свежим»
        становится ещё и единственным источником секунды.

        ``alive`` спрашивается перед каждым опросом: сказал «нет» - каст снимается (:meth:`_pump`).
        """
        self._release()
        receiver = self.factory(address, profile or self.profile)
        tv_load(receiver, url, title, at, container)
        self._receiver = receiver
        self._heard = None
        self._alive = alive
        self.key = key
        self._arm(receiver, echo)

    def stop(self) -> float:
        """Снять каст и назвать секунду, на которой он стоял; без каста - ноль.

        Секунда - ПОСЛЕДНИЙ УСЛЫШАННЫЙ опрос, а не свежее чтение: чтение на излёте
        отдало место ДЕСЯТИСЕКУНДНОЙ давности (стенд `.104` 10-09-2026: показ на
        ~14-й секунде, ``position()`` в ``stop`` ответил 4.8, «На комп» отматывал назад).

        ``_heard`` читается ПОД замком - опрос пишет его тоже под замком, иначе чтение
        снаружи иногда ловило недописанный доклад (флап на `test_stop_answers_with_
        the_last_polled_position_not_a_stale_reread`, ~1/30 без соседних процессов).
        """
        receiver, self._receiver = self._receiver, None
        self.key = ""
        if receiver is None:
            return 0.0
        self._disarm()
        with self._lock:
            heard, self._heard = self._heard, None
            at = heard.pos if heard is not None else receiver.position().pos
            receiver.stop(quit_app=True)
        return at

    def _release(self) -> None:
        """Закрыть прежнюю связь без чтения её места - её никто не спрашивал."""
        receiver, self._receiver = self._receiver, None
        self.key = ""
        self._heard = None
        if receiver is None:
            return
        self._disarm()
        with self._lock:
            receiver.stop(quit_app=True)

    def _arm(self, receiver: Receiver, echo: Callable[[Position], None] | None = None) -> None:
        """Завести опрос: держит место у pychromecast свежим, пока каст живёт."""
        stop_poll = threading.Event()
        self._stop_poll = stop_poll
        poll = threading.Thread(target=self._pump, args=(receiver, stop_poll, echo), daemon=True)
        self._poll = poll
        poll.start()

    def _disarm(self) -> None:
        """Остановить опрос и дождаться его конца перед тем, как трогать приёмник."""
        if self._stop_poll is not None:
            self._stop_poll.set()
        # Опрос, снимающий каст сам (:meth:`_pump`), себя не ждёт: join самого себя - ошибка.
        if self._poll is not None and self._poll is not threading.current_thread():
            self._poll.join(timeout=self.poll_seconds)
        self._stop_poll = self._poll = None

    def _pump(
        self,
        receiver: Receiver,
        stop_poll: threading.Event,
        echo: Callable[[Position], None] | None,
    ) -> None:
        """Опрашивать приёмник, пока сеанс жив; чужому сеансу опрос не отвечает.

        Слушателю место уходит ВНЕ замка - держать его на файловой записи значило бы
        заставлять ``stop`` ждать. 🔴 Показ снят - каст снимается тут же: чтение места у
        погасшего потока поднимало LOAD заново («retrying LOAD»; стенд `.104` 11-09-2026).
        """
        while not stop_poll.wait(self.poll_seconds):
            if self._alive is not None and not self._alive():
                if self._receiver is receiver:
                    self._release()
                return
            with self._lock:
                if self._receiver is not receiver:
                    return
                spot = receiver.position()
                if self._backwards(spot):
                    continue
                self._heard = spot
            if echo is not None:
                echo(spot)

    def _backwards(self, spot: Position) -> bool:
        """Доклад, ушедший НАЗАД посреди каста: это чтение на излёте, а не перемотка.

        Перемотка идёт файлом-пультом в юнит показа и приёмника не касается - новый каст
        начинается с чистого :attr:`_heard`. 🔴 Это число ведёт и плёнку вкладки: один
        доклад назад дёргал её (стенд `.104`: 5.4, следом 3.6, вкладка с 15.9 на 4.5).
        """
        heard = self._heard
        return heard is not None and spot.pos < heard.pos


#: Один держатель на процесс страницы: оба маршрута спрашивают именно его.
SESSION: TvSession = TvSession()
