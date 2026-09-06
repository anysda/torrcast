"""Одна живая связь с приёмником ТВ на весь процесс страницы: `` /api/to-tv``/``/api/to-web``.

Каст «на ТВ» (ТЗ §7.5) не поднимает новый показ - поток, упаковка и перекод остаются
теми же, что уже идут для вкладки. Соединение с приёмником при этом ровно одно: второе,
поднятое поверх первого, было бы вторым сендером той же медиасессии, а не безобидным
вторым сендером ради числа, каким законно живёт :class:`hass.volume.Volume` для громкости
(её же докстрока и называет разницу). `TvSession` - тот самый единственный держатель,
которым делятся оба маршрута, а не пара независимых соединений.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.ports.receiver import Receiver


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
    _receiver: Receiver | None = field(default=None, init=False, repr=False)

    def active(self) -> bool:
        """Идёт ли каст на ТВ прямо сейчас."""
        return self._receiver is not None

    def start(self, address: str, title: str, url: str, at: float) -> None:
        """Позвать приёмник ТВ тем же ``play``, каким продукт стартует консольный показ.

        Старую связь, если она была, отпускаем первой: иначе повторное нажатие «На ТВ»
        оставляло бы прежнее соединение висеть незакрытым.
        """
        if self._receiver is not None:
            self._receiver.stop(quit_app=True)
        receiver = self.factory(address, self.profile)
        receiver.play(url, title, at=at)
        self._receiver = receiver

    def stop(self) -> float:
        """Снять каст и назвать секунду, на которой он стоял; без каста - ноль."""
        receiver, self._receiver = self._receiver, None
        if receiver is None:
            return 0.0
        at = receiver.position().pos
        receiver.stop(quit_app=True)
        return at


#: Один держатель на процесс страницы: оба маршрута спрашивают именно его.
SESSION: TvSession = TvSession()
