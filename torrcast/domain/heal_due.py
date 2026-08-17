"""Пора ли стучаться в заблокированный индексер, чтобы вернуть его в каталог."""

from __future__ import annotations

from typing import Final

from torrcast.domain.failed_just_now import CLOCK_SLACK
from torrcast.domain.failure_moment import failure_moment

#: 🔴 TC-259/TC-272. Как часто мы вправе стучаться после окончания отсрочки.
#:
#: Prowlarr держит бан по своим часам, а не по здоровью источника. На неответившем живом
#: источнике первая ступень - 60 секунд. У отсутствующего источника ступень дорастает до
#: суток, а неудачная проверка начинает её заново. Поэтому действующий ``disabledTill``
#: не трогаем; после его окончания минута от последнего отказа защищает от повторного
#: стука по одной и той же отметке.
HEAL_PAUSE: Final = 60.0


def heal_due(failed: str, disabled: str, now: float) -> bool:
    """Пора ли стучаться: отсрочка кончилась, а отказ отдохнул (:data:`HEAL_PAUSE`).

    ``failed`` - отметка последнего отказа, ``disabled`` - до какого времени Prowlarr
    обещает держать источник в недоступных. Пока отсрочка действует, стучаться нельзя
    вовсе: неудачная проверка начала бы её заново, причём с большей ступени.

    Время отказа не прочиталось - считаем, что пора: не полечить вовсе хуже, чем сходить
    лишний раз. Не прочиталась отсрочка - считаем её законченной по той же причине.
    """
    moment = failure_moment(failed)
    rested = moment is None or now - moment >= HEAL_PAUSE
    return rested and (failure_moment(disabled) or 0.0) <= now + CLOCK_SLACK


__all__ = ["HEAL_PAUSE", "heal_due"]
