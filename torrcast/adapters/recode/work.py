"""Нитка фонового кодировщика: выбрать заход, свериться с потолком кэша, отработать.

Поднимает её :meth:`Recoder.start`, и больше никто."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

from torrcast.adapters.recode.pick import _pick
from torrcast.adapters.recode.run import _run

if TYPE_CHECKING:
    from torrcast.adapters.recode.recoder_state import _State


def _work(state: _State) -> None:
    """Крутится, пока идёт показ: заход за заходом от места показа вперёд."""
    while not state.stopped:
        try:
            state._sweep()
            job = _pick(state)
            if job is None:
                time.sleep(1.0)
                continue
            # Потолок кэша голову прогона не касается: её ждёт показ, а не запас
            # впрок, и уснуть тут значит отдать первый сегмент копией. Ровно так же
            # он не касается куска, на котором ВСТАЛА выкладка (:attr:`blocked`):
            # заснуть под потолком кэша значит держать показ до предохранителя и
            # потом всё равно выпустить тяжёлую копию.
            if job[0] not in (state.head, state.blocked) and state._weight() >= state.cache_mb:
                time.sleep(2.0)
                continue
            _run(state, *job)
        # Кодировщик не имеет права ронять показ: он работает впрок, и его беда -
        # это в худшем случае тяжёлый кусок, ушедший как есть, а не конец фильма.
        except Exception as exc:
            state._say(f"перекодирование сорвалось ({exc}) - показ идёт как есть")
            time.sleep(5.0)
