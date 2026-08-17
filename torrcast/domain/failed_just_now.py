"""Случился ли отказ источника уже после начала этого поиска."""

from __future__ import annotations

from typing import Final

from torrcast.domain.failure_moment import failure_moment

#: Припуск к отметке отказа (TC-291): доли секунды мы отрезаем при разборе, а саму
#: отметку ставит Prowlarr, а не наш секундомер. Две секунды - это заведомо больше
#: обеих неточностей и заведомо меньше любого поиска.
CLOCK_SLACK: Final = 2.0


def failed_just_now(failed: str, since: float) -> bool:
    """Случился ли отказ уже ПОСЛЕ начала этого поиска (TC-291).

    Судим строго: время не прочиталось - значит не обвиняем. Ошибиться сюда дёшево
    (промолчим о том, о чём молчали и раньше), а в другую сторону - дорого: это
    честное «ничего не нашлось», объявленное отказом канала.

    :data:`CLOCK_SLACK` - припуск на отрезанные доли секунды и на то, что отметку
    ставит не наш секундомер. Часы при этом одни и те же: Prowlarr живёт на той же машине.
    """
    moment = failure_moment(failed)
    return moment is not None and moment >= since - CLOCK_SLACK


__all__ = ["CLOCK_SLACK", "failed_just_now"]
