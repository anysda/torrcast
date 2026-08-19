"""Нитка фонового кодировщика: выбрать заход, свериться с потолком кэша, отработать.

Поднимает её :meth:`Recoder.start`, и больше никто."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from torrcast.adapters.recode.pick import _pick
from torrcast.adapters.recode.run import _run
from torrcast.adapters.recode.spare_weight import spare_weight
from torrcast.adapters.recode.sweep_spare import sweep_spare

if TYPE_CHECKING:
    from torrcast.adapters.recode.recoder_state import _State


def _work(
    state: _State,
    pick: Callable[[_State], tuple[int, int] | None] = _pick,
    run: Callable[[_State, int, int], None] = _run,
    nap: Callable[[float], None] = time.sleep,
) -> None:
    """Крутится, пока идёт показ: заход за заходом от места показа вперёд.

    ``pick``, ``run`` и ``nap`` - выбор захода, сам заход и сон между кругами. Доводами,
    а не именами внутри модуля: заход поднимает ffmpeg, а сон стоит стенных секунд, тогда
    как меряется тут одно - какие решения принимает нитка и в каком порядке.
    """
    while not state.stopped:
        try:
            sweep_spare(state.spare, state.grid, state.played, state.done)
            job = pick(state)
            if job is None:
                nap(1.0)
                continue
            # Потолок кэша голову прогона не касается: её ждёт показ, а не запас
            # впрок, и уснуть тут значит отдать первый сегмент копией. Ровно так же
            # он не касается куска, на котором ВСТАЛА выкладка (:attr:`blocked`):
            # заснуть под потолком кэша значит держать показ до предохранителя и
            # потом всё равно выпустить тяжёлую копию.
            spared = job[0] in (state.head, state.blocked)
            if not spared and spare_weight(state.spare) >= state.cache_mb:
                nap(2.0)
                continue
            run(state, *job)
        # Кодировщик не имеет права ронять показ: он работает впрок, и его беда -
        # это в худшем случае тяжёлый кусок, ушедший как есть, а не конец фильма.
        except Exception as exc:
            state._say(f"перекодирование сорвалось ({exc}) - показ идёт как есть")
            nap(5.0)
