"""Ставит голый кусок - перекод или ужатие - на ленту показа.

Зовут это выкладка перекодированного места (:mod:`torrcast.adapters.stream_pack._merged_out`)
и ужатия на месте (:mod:`torrcast.adapters.stream_pack._shrunk_out`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from torrcast.adapters.stream_pack.splice_on_tape import splice_on_tape
from torrcast.domain.segment_container import FMP4, SegmentContainer
from torrcast.ports.journal.slot import journal

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


def bare_on_tape(
    chunk: Path,
    tape: Path,
    slot: int,
    what: str,
    container: SegmentContainer,
    heads: tuple[Path | None, Path | None],
    *,
    on_tape: Callable[..., bool] = splice_on_tape,
) -> bool:
    """Переставить счётчики ``chunk`` на счётчики куска ``tape``; ``False`` - не вышло.

    🔴 Ради этого написано. На CMAF ``tfdt`` - не время фильма, а счётчик прогона ffmpeg
    (:func:`torrcast.domain.tape_spots.tape_spots`), и склейку на ленту показа уже ставят
    (:func:`torrcast.adapters.stream_pack.splice_on_tape.splice_on_tape`). А наружу уходит
    не только склейка: перекод несёт счётчик ЗАХОДА КОДИРОВЩИКА, ужатие - счётчик своего,
    второго прогона над одним местом. Оба уезжают зрителю мимо всякой ленты, и оба уводят
    приёмник туда, где стоял их собственный ноль.

    ``tape`` - копия этого же места из своего прогона упаковки: кусок, ВМЕСТО которого
    уедет ``chunk``. Его счётчики - продолжение счётчиков соседей, и брать их надо целиком,
    а не считать по сетке: сосед справа продолжит счёт от них же.

    ``heads`` - заголовки прогонов, сделавших картинку (``[0]``) и звук (``[1]``). Голый
    фрагмент своего ``moov`` не несёт, поэтому шкалы своих дорожек он называет заголовком
    своего прогона, а ленту показа - заголовком копии. Не сошлись шкалы - кусок не
    трогается вовсе: счётчик значил бы в них разное.

    ``what`` - каким исходом кусок уезжает (``перекод`` или ``ужатие``): отказ обязан
    называть путь, потому что лечится он у каждого свой.

    ⚠️ Отказ не отменяет выкладку: кусок уходит наружу как уходил, со счётчиком своего
    прогона. Молчать о нём нельзя - это ровно тот скачок ленты, за который приёмник платит
    голоданием, - но и придержать место дороже: пропуск стоит зрителю всего куска.
    """
    if container != FMP4:
        return True
    if on_tape(chunk, tape, heads[1], heads[0]):
        return True
    journal().mark(f"{what} не поставить на ленту показа", слот=slot)
    return False
