"""Отказ человека от идущего подъёма: место, где подъём его читает и прекращается.

Подъём идёт минутами - поиск, раздача, упаковка, ожидание картинки, - и всё это время
человек вправе передумать. Отказ приходит извне и лежит фактом в порту
(:mod:`torrcast.ports.abandon.slot`); здесь он превращается в конец подъёма.
"""

from __future__ import annotations

from torrcast.domain.cancelled_error import CancelledError
from torrcast.domain.catalogs.phrase import phrase
from torrcast.ports.abandon.slot import abandoned
from torrcast.ports.progress.progress import Progress
from torrcast.ports.show_unit.show_unit import ShowUnit


def refuse_called_off(progress: Progress | None = None, unit: ShowUnit | None = None) -> None:
    """Прекратить подъём, если человек от него отказался; живой юнит при этом погасить.

    Спрашивают это на двух поворотах, и разница между ними ровно одна: успел ли уже
    подняться юнит показа. До юнита гасить нечего, и звать сюда нечего; при живом юните
    его передают сюда, и он гаснет тем же движением.

    🔴 До юнита спрошено нарочно. Подняться и тут же погаснуть - это кадр чужой картины
    на экране человека и лишний сендер на приёмнике, а не аккуратная отмена. И гасит
    юнит именно подъём, а не кто-то снаружи: отказ мог прийти в ту долю секунды, когда
    юнита ещё не было, и снаружи гасить было нечего.
    """
    if not abandoned():
        return
    if progress is not None and unit is not None:
        progress.phase("")
        unit.stop()
    raise CancelledError(phrase("playback.abandoned"))
