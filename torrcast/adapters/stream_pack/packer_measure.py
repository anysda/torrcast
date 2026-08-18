"""Три замера прогона упаковки: когда достанет, сколько держит и докуда дошёл каталог.

Спрашивают их горячий путь показа и часы показа (:mod:`torrcast.usecases.feed_pack`).
"""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING

from torrcast.adapters.stream_pack._segment_files import _names
from torrcast.adapters.stream_probe.segment_slot import segment_slot

if TYPE_CHECKING:
    from torrcast.adapters.stream_pack.packer_state import _State


def _eta(state: _State, film: float) -> float:
    """Через сколько секунд ffmpeg дочитает вход до секунды ``film``. Оценка снизу.

    Считается по собственной планке ffmpeg, а не по нашим наблюдениям: с
    ``-readrate R -readrate_initial_burst B`` он читает всё, что ниже
    ``-ss + B + прошло * R``, на полной скорости, а выше — ровно в темпе ``R``
    (``readrate_sleep`` в ``ffmpeg.c``). Значит место ``film`` он тронет не раньше, чем
    через ``(film - планка) / R``.

    Оценка **снизу** намеренно: реальный прогон может отставать и от планки (холодный
    рой, слабый процессор), и тогда ждать придётся дольше. Но решение, которое на ней
    строится, — «перезапустить упаковку с этого места» (:meth:`Feed._steer`), а
    перезапуск лечит ровно упирание в темп и ничем не помогает отставанию по входу.
    Поэтому недооценка тут безопасна, а переоценка стоила бы лишних перезапусков.

    ``rate <= 0`` — темпа нет, ffmpeg читает во весь опор: ждать нечего, ноль.
    """
    if state.rate <= 0:
        return 0.0
    reach: float = state.at + state.burst + (time.monotonic() - state.began) * state.rate
    return max(0.0, (film - reach) / state.rate)


def _pending(state: _State) -> int:
    """Сколько байт этот прогон уже написал в tmpfs, но наружу не отдал.

    Всё, что лежит в каталоге прогона: и кусок, который ffmpeg пишет прямо сейчас, и
    те, что выкладка не пропустила (придержаны под перекод, тяжелее потолка). Наружу
    уходит переименованием (:meth:`Packer.publish`), поэтому выложенное сюда не попадает и
    считается дважды быть не может.
    """
    total = 0
    with contextlib.suppress(OSError):
        for path in state.run.iterdir():
            with contextlib.suppress(OSError):
                total += path.stat().st_size
    return total


def _frontier(state: _State) -> int:
    """Последний готовый сегмент в каталоге показа; ``first - 1`` — готового нет.

    ⚠️ Это **не** край прогона (:attr:`edge`): счёт идёт глобом каталога, где лежат и
    куски прошлых прогонов, поэтому после перемотки назад число врёт вверх. Решения
    об упаковке на нём больше не строятся (:meth:`Feed._steer`); осталось оно ровно
    под :meth:`Feed.front` — запас показа для сторожа приёмника, который доказан на
    живом ТВ, и менять его без такой же живой проверки нельзя.
    """
    slots = [s for s in map(segment_slot, _names(state.out)) if s >= state.first]
    return max(slots, default=state.first - 1)
