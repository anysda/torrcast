"""Голову упаковки ведёт самый свежий запрос приёмника, а не тот, что дольше всех ждёт.

Запрос сегмента ждёт файла ``wait`` секунд и всё это время каждые 0.2 с возвращается в
решение об упаковке (:func:`torrcast.usecases.feed_pack.feed_steer._steer`). Приёмник,
перемотанный дальше, этот запрос бросает, а поток раздачи - нет: старое место продолжает
спорить за голову с новым, и защёлка в 2 с задаёт лишь шаг спора.

Стенд 06-10-2026: «Start over», затем «+100». ТВ стоял на 102 с, а упаковка 90 с ходила
«packing from 100.1», «packing from 12.4» через каждые 2.5 с. Ни одна голова не доходила
до куска, круги сдались на обоих местах, ТВ висел в BUFFERING до стопа. Окно ``keep``
(:func:`torrcast.usecases.feed_pack.feed_steer._behind`) тут молчит: у начала фильма
позади зрителя нет ничего, а спор идёт о месте, а не о расстоянии.

Перемотку назад это не запирает: приёмник, вернувшийся к старому месту, приходит за ним
НОВЫМ запросом, и тот уже свежее.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torrcast.usecases.feed_pack._state as _state

if TYPE_CHECKING:
    from collections.abc import Callable

    from torrcast.usecases.feed_pack.feed_state import _State

__all__ = ["_newest"]


def _newest(state: _State, steer: Callable[[int], bool]) -> Callable[[int], bool]:
    """Решение об упаковке для запроса, пришедшего сейчас: голову уведший запрос новее - ждать."""
    arrived = _state.clock_port.monotonic()

    def steered(slot: int) -> bool:
        if state.asked > arrived:
            return True  # голову уже повёл запрос новее: этот ждёт файла и упаковку не трогает
        before = state.restarted
        hope = steer(slot)
        if state.restarted != before:
            state.asked = arrived
        return hope

    return steered
