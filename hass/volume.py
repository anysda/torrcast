"""Громкость приёмника: абсолютный уровень 0..1 прямо у приёмника, мимо файла-пульта.

🔴 Почему мимо. В файле-пульте громкость - это СДВИГ
(:meth:`torrcast.adapters.chromecast.cast.chromecast_receiver.ChromecastReceiver.volume`:
читает уровень и складывает), а голосовой помощник Home Assistant умеет только «поставь
громкость N процентов». Собрать уровень из сдвигов снаружи нельзя: своего уровня мост не
знает, а прошлый мог сдвинуть кто угодно, хоть пульт телевизора.

Второе соединение тут законно, и это не то же самое, что вторая MEDIA-команда. Пустым
``MEDIA_STATUS`` приёмник отвечает второму сендеру про СЕАНС показа
(:data:`torrcast.domain.debug_handles.CTL_ENV`), а громкость - свойство самого приёмника:
она лежит в статусе устройства и меняется командой RECEIVER, которую шлёт и пульт, и
телефон, и любой другой сендер. Идущий показ такой командой не трогается.
"""

from __future__ import annotations

import contextlib
import time
from collections.abc import Callable
from typing import Any

#: Свежесть прочитанного уровня, секунды: опрос раз в 5 с не должен выть на приёмник.
FRESH_SECONDS = 10.0
#: Сколько ждём приёмник. Столько же ждёт его показ при подключении
#: (:meth:`torrcast.adapters.chromecast.cast.receiver_link._Link._device`).
CONNECT_TIMEOUT = 10.0
WAIT_TIMEOUT = 20.0


def _connect(address: str) -> Any:
    """Поднять соединение тем же способом, каким его поднимает показ."""
    import uuid

    import pychromecast

    from torrcast.adapters.chromecast.cast.hush_cosmetic_noise import hush_cosmetic_noise

    hush_cosmetic_noise()
    device = pychromecast.get_chromecast_from_host(
        (address, 8009, uuid.UUID(int=0), None, None), timeout=CONNECT_TIMEOUT
    )
    device.wait(timeout=WAIT_TIMEOUT)
    return device


class Volume:
    """Ленивое соединение с приёмником ради одного числа.

    Отказ приёмника не поднимается наружу и не роняет снимок показа: громкость - одно
    поле из тринадцати, и молчащий телевизор не повод не сказать, что играет. Соединение
    после отказа забывается: следующий вопрос поднимет его заново.
    """

    def __init__(
        self,
        address: str,
        *,
        connect: Callable[[str], Any] = _connect,
        fresh: float = FRESH_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        #: Адрес приёмника, на который это соединение заведено.
        self.address = address
        self._connect = connect
        self._fresh = fresh
        self._clock = clock
        self._device: Any = None
        self._level: float | None = None
        self._read_at = 0.0

    def level(self) -> float | None:
        """Уровень 0..1; приёмник не отозвался - ``None``, а не прошлое число."""
        if not self.address:
            return None
        if self._level is not None and self._clock() - self._read_at < self._fresh:
            return self._level
        device = self._alive()
        if device is None:
            return None
        try:
            level = getattr(device.status, "volume_level", None)
        except Exception:
            self._drop()
            return None
        self._level = None if level is None else float(level)
        self._read_at = self._clock()
        return self._level

    def set(self, level: float) -> bool:
        """Поставить абсолютный уровень; ``False`` - приёмника нет или он отказал."""
        device = self._alive()
        if device is None:
            return False
        want = max(0.0, min(1.0, level))
        try:
            device.set_volume(want)
        except Exception:
            self._drop()
            return False
        self._level, self._read_at = want, self._clock()
        return True

    def close(self) -> None:
        """Отпустить приёмник: мост уходит, соединение за собой не оставляем."""
        self._drop()

    def _alive(self) -> Any:
        """Живое соединение; поднять его не вышло - ``None`` и ни одного исключения."""
        if not self.address:
            return None
        if self._device is None:
            try:
                self._device = self._connect(self.address)
            except Exception:
                self._device = None
        return self._device

    def _drop(self) -> None:
        """Забыть соединение вместе с прочитанным уровнем."""
        device, self._device = self._device, None
        self._level, self._read_at = None, 0.0
        if device is not None:
            with contextlib.suppress(Exception):
                device.disconnect()
