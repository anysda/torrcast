"""Подъём погасшего показа сухого приёмника: LOAD и ожидание настоящей картинки.

Зовёт его :meth:`torrcast.adapters.chromecast.mock.mock_receiver.MockReceiver.replay`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.infra_error import InfraError
from torrcast.domain.not_raised import NOT_RAISED
from torrcast.domain.why import why

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
) -> tuple[float, str]:
    """Поднять погасший показ с ``at``; вернуть секунду показа и причину, если её нет.

    Тот же договор, что и у приёмника на живом ТВ: позиция приходит снаружи (у мёртвой
    сессии её нет), исключения наружу не выпускаются, а место подъёма называется только
    про действительно вернувшуюся картинку, а не про отправленный LOAD;
    :data:`torrcast.domain.not_raised.NOT_RAISED` - её нет. Ждать её дольше ``timeout``
    незачем: попытка тут не одна, интервалы держит зовущий.

    Своей сетки сухой приёмник не знает и куски не перешагивает, поэтому пошла картинка
    ровно оттуда, откуда просили.

    🔴 Причина возвращается ВТОРЫМ ответом, а не остаётся в исключении. Ответ про место
    у всех неудач один - :data:`NOT_RAISED`, - и пока сухой тракт отвечал только им,
    лента сухого прогона несла ту самую двусмысленность, которую живой уже снял
    (:class:`torrcast.usecases.revive_playback._blame._Blaming`): «упал» (источника нет,
    лечится следующей попыткой) и «не взял» (LOAD ушёл, картинки нет) стояли в ней одной
    строкой. Слова тут ровно живые: сухую ленту затем и читают, чтобы судить о живой.
    """
    try:
        open_at(at)
    except (InfraError, OSError) as exc:
        # Источника всё ещё нет - зовущий попробует ещё или погасит показ. Исключение
        # проглочено, но причина его - нет: она уезжает в ленту тем же словом, что на ТВ.
        return NOT_RAISED, phrase("chromecast_talk.refused_crashed", reason=why(exc))
    screen.jumped(at)
    deadline = clock.monotonic() + timeout
    while clock.monotonic() < deadline:
        clock.sleep(1.0)
        if decoder.pos.pos > at:  # декодер поехал - картинка на экране
            screen.dead = False
            return at, ""
        if not decoder.pos.playing:
            # Декодер лёг, не начав: показа нет, и врать о нём нельзя. Снаружи это тот же
            # исход, что и на ТВ, - LOAD взяли, кадра не дали, - и назван он так же.
            decoder.stop()
            return NOT_RAISED, phrase("chromecast_talk.refused_decoder_died")
    decoder.stop()
    return NOT_RAISED, phrase("chromecast_talk.refused_not_taken")


def _replay_paused(
    open_at: Callable[[float], None],
    screen: ScreenWatch,
    pause: Callable[[], None],
    at: float,
) -> tuple[float, str]:
    """LOAD без автостарта: сессия возвращается на закладку и ждёт зрителя.

    Картинки ждать нечего - её и не просили: готовность такого подъёма на живом
    приёмнике - слово ``PAUSED``, и здесь оно выставляется тем же ``pause``, которым его
    выставляет пульт.

    Живёт рядом с :func:`mock_replay`, а не в приёмнике: на ТВ обе ветки подъёма стоят в
    одном месте (``paused`` - флаг ``LOAD``), и причину отказа они называют одну на двоих.
    """
    try:
        open_at(at)
    except (InfraError, OSError) as exc:
        # зовущий попробует ещё или дождётся паузы
        return NOT_RAISED, phrase("chromecast_talk.refused_crashed", reason=why(exc))
    screen.jumped(at)
    screen.dead = False
    pause()
    return at, ""
