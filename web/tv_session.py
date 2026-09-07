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
from torrcast.ports.receiver import Receiver

#: Как часто держатель спрашивает приёмник, пока каст на ТВ идёт. Тот же шаг, что и у
#: обычного показа (:mod:`torrcast.adapters.chromecast.cast.position`, «раз в две
#: секунды»), и не для красоты: без опроса ``current_time`` у pychromecast застревает на
#: значении первой картинки и не сдвигается сам - замерено на живом стенде ``.104``
#: (``ChromecastReceiver.position()`` через 19.5 с показа отдал 0.2 с вместо ожидаемых
#: ~15 с). «На комп» без опроса вернул бы зрителя почти в начало вместо настоящего места.
POLL_SECONDS = 2.0


def _live_receiver(address: str, profile: Profile) -> Receiver:
    """Настоящий Chromecast; импорт внутри функции - чтобы страница не тянула pychromecast,
    пока никто не нажал «На ТВ» (тем же приёмом, что и в :mod:`hass.volume`)."""
    from torrcast.adapters.chromecast.cast.chromecast_receiver import ChromecastReceiver

    return ChromecastReceiver(address, profile=profile)


@dataclass
class TvSession:
    """Держит приёмник ТВ между запросом «на ТВ» и запросом «на комп».

    Профиль - нарочно всегда :data:`torrcast.domain.profile.CAUTIOUS`: паспорт устройства
    спрашивать здесь неоткуда без опроса сети (настройка ``receiver`` у страницы навсегда
    ``browser``, и штатный :class:`torrcast.adapters.chromecast.profile_detector.
    ProfileDetector` на ней и не пробует спрашивать паспорт). Осторожный профиль - тот же
    компромисс, что и с порогом перекода (ТЗ §7.5, решение 3): назван, а не спрятан.
    """

    factory: Callable[[str, Profile], Receiver] = _live_receiver
    profile: Profile = CAUTIOUS
    poll_seconds: float = POLL_SECONDS
    _receiver: Receiver | None = field(default=None, init=False, repr=False)
    _stop_poll: threading.Event | None = field(default=None, init=False, repr=False)
    _poll: threading.Thread | None = field(default=None, init=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def active(self) -> bool:
        """Идёт ли каст на ТВ прямо сейчас."""
        return self._receiver is not None

    def start(
        self,
        address: str,
        title: str,
        url: str,
        at: float,
        echo: Callable[[Position], None] | None = None,
    ) -> None:
        """Позвать приёмник ТВ тем же ``play``, каким продукт стартует консольный показ.

        Старую связь, если она была, отпускаем первой: иначе повторное нажатие «На ТВ»
        оставляло бы прежнее соединение висеть незакрытым и опрашиваемым.

        ``echo`` слышит каждый опрос приёмника: пока каст идёт, место показа знает ТВ, а
        не вкладка (ТЗ §7.5.3), и опрос из повода «держать ``current_time`` свежим»
        становится ещё и единственным источником секунды.
        """
        self._release()
        receiver = self.factory(address, self.profile)
        receiver.play(url, title, at=at)
        self._receiver = receiver
        self._arm(receiver, echo)

    def stop(self) -> float:
        """Снять каст и назвать секунду, на которой он стоял; без каста - ноль."""
        receiver, self._receiver = self._receiver, None
        if receiver is None:
            return 0.0
        self._disarm()
        with self._lock:
            at = receiver.position().pos
            receiver.stop(quit_app=True)
        return at

    def _release(self) -> None:
        """Закрыть прежнюю связь без чтения её места - её никто не спрашивал."""
        receiver, self._receiver = self._receiver, None
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
        if self._poll is not None:
            self._poll.join(timeout=self.poll_seconds)
        self._stop_poll = self._poll = None

    def _pump(
        self,
        receiver: Receiver,
        stop_poll: threading.Event,
        echo: Callable[[Position], None] | None,
    ) -> None:
        """Опрашивать приёмник, пока сеанс жив; чужому сеансу опрос не отвечает.

        Слушателю место передаётся ВНЕ замка: он пишет на диск, и держать на этом время
        замок значило бы заставлять ``stop`` ждать файловой записи.
        """
        while not stop_poll.wait(self.poll_seconds):
            with self._lock:
                if self._receiver is not receiver:
                    return
                spot = receiver.position()
            if echo is not None:
                echo(spot)


#: Один держатель на процесс страницы: оба маршрута спрашивают именно его.
SESSION: TvSession = TvSession()
