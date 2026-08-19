"""Подъём погасшего показа сухого приёмника: LOAD и ожидание настоящей картинки.

Зовёт его :meth:`torrcast.adapters.chromecast.mock.mock_receiver.MockReceiver.replay`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.infra_error import InfraError
from torrcast.domain.not_raised import NOT_RAISED

if TYPE_CHECKING:
    from collections.abc import Callable

    from torrcast.adapters.chromecast.mock.hls_decoder import HlsDecoder
    from torrcast.adapters.chromecast.mock.screen_watch import ScreenWatch
    from torrcast.ports.clock import Clock


def mock_replay(
    open_at: Callable[[float], None],
    screen: ScreenWatch,
    decoder: HlsDecoder,
    clock: Clock,
    at: float,
    timeout: float,
) -> float:
    """Поднять погасший показ с секунды ``at``; вернуть секунду, с которой он пошёл.

    Тот же договор, что и у приёмника на живом ТВ: позиция приходит снаружи (у мёртвой
    сессии её нет), исключения наружу не выпускаются, а место подъёма называется только
    про действительно вернувшуюся картинку, а не про отправленный LOAD;
    :data:`torrcast.domain.not_raised.NOT_RAISED` - её нет. Ждать её дольше ``timeout``
    незачем: попытка тут не одна, интервалы держит зовущий.

    Своей сетки сухой приёмник не знает и куски не перешагивает, поэтому пошла картинка
    ровно оттуда, откуда просили.
    """
    try:
        open_at(at)
    except (InfraError, OSError):
        return NOT_RAISED  # источника всё ещё нет - зовущий попробует ещё или погасит
    screen.jumped(at)
    deadline = clock.monotonic() + timeout
    while clock.monotonic() < deadline:
        clock.sleep(1.0)
        if decoder.pos.pos > at:  # декодер поехал - картинка на экране
            screen.dead = False
            return at
        if not decoder.pos.playing:
            break  # декодер лёг, не начав: показа нет, и врать о нём нельзя
    decoder.stop()
    return NOT_RAISED
