"""Нитка фонового кодировщика: выбрать заход, свериться с потолком кэша, отработать.

Поднимает её :meth:`Recoder.start`, и больше никто."""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Final

from torrcast.adapters.recode.pick import _pick
from torrcast.adapters.recode.run import _run
from torrcast.adapters.recode.spare_weight import spare_weight
from torrcast.adapters.recode.sweep_spare import sweep_spare

if TYPE_CHECKING:
    from torrcast.adapters.recode.recoder_state import _State

#: Пауза перед повтором брошенного захода, секунды. Условия, по которым заход
#: бросается (место показа, голова прогона, вставшая выкладка), меняются снаружи и
#: не чаще, чем раз в две секунды: с таким шагом приходит место показа
#: (:meth:`Recoder.opening`), а вставшая выкладка отлипает, когда её кусок уйдёт
#: наружу. Повтор раньше этого шага заведомо видит те же условия и бросается снова -
#: чистый подъём ffmpeg в никуда. У упаковки между перезапусками тот же шаг
#: (:func:`torrcast.usecases.feed_pack.feed_steer._steer`).
RETRY_PAUSE: Final = 2.0

#: Сколько брошенных заходов подряд ещё имеет смысл повторять. У упаковки тот же
#: потолок: три обрыва подряд - это уже не помеха, а сломанный вход
#: (:attr:`torrcast.usecases.feed_pack.feed_state._State.limit`). Тут - условия,
#: которые не меняются: дальше круг сдаётся и помечает куски захода сделанными, как
#: заход, не давший ни куска (:func:`_run`), - выкладка это видит
#: (:meth:`torrcast.adapters.recode.hold_bulky._hold_bulky`) и решает кусок сама.
RETRY_LIMIT: Final = 3


def _work(
    state: _State,
    pick: Callable[[_State], tuple[int, int] | None] = _pick,
    run: Callable[[_State, int, int], str | None] = _run,
    nap: Callable[[float], None] = time.sleep,
) -> None:
    """Крутится, пока идёт показ: заход за заходом от места показа вперёд.

    ``pick``, ``run`` и ``nap`` - выбор захода, сам заход и сон между кругами. Доводами,
    а не именами внутри модуля: заход поднимает ffmpeg, а сон стоит стенных секунд, тогда
    как меряется тут одно - какие решения принимает нитка и в каком порядке. Заход
    возвращает причину, по которой он брошен, и ``None``, когда отработал до конца:
    по ней нитка отличает повтор от новой работы (:data:`RETRY_PAUSE`).
    """
    abandons = 0
    abandoned: tuple[int, int] | None = None
    while not state.stopped:
        try:
            sweep_spare(state.spare, state.grid, state.played, state.done, state.container)
            job = pick(state)
            if job is None:
                abandons, abandoned = 0, None
                nap(1.0)
                continue
            # Потолок кэша голову прогона не касается: её ждёт показ, а не запас
            # впрок, и уснуть тут значит отдать первый сегмент копией. Ровно так же
            # он не касается куска, на котором ВСТАЛА выкладка (:attr:`blocked`):
            # заснуть под потолком кэша значит держать показ до предохранителя и
            # потом всё равно выпустить тяжёлую копию.
            spared = job[0] in (state.head, state.blocked)
            if not spared and spare_weight(state.spare, state.container) >= state.cache_mb:
                nap(2.0)
                continue
            if job == abandoned:
                # Тот же заход только что бросили, а условия броска за этот миг
                # измениться не могли: повтор сразу - это гарантированно тот же
                # бросок плюс подъём ffmpeg. Паузу отспали - выбираем заново: если за
                # неё условия изменились, круг пойдёт дальше уже без сна. Другой заход
                # (голова прогона, кусок вставшей выкладки) этой паузы не ждёт - его
                # ждёт показ.
                abandoned = None
                nap(RETRY_PAUSE)
                continue
            why = run(state, *job)
            if why is None:
                abandons = 0
                continue
            abandons += 1
            if abandons > RETRY_LIMIT:
                # Повторять дальше нечего: заход бросается подряд, а условия броска
                # не меняются. Сдаёмся, как заход, не давший ни куска: куски числятся
                # сделанными, и дальше их решает выкладка, а не лавина подъёмов.
                state.done.update(range(job[0], job[1] + 1))
                state._say(
                    f"заход v{job[0]}...v{job[1]} брошен {abandons} раз подряд ({why}) - сдаюсь"
                )
                abandons, abandoned = 0, None
                continue
            abandoned = job
        # Кодировщик не имеет права ронять показ: он работает впрок, и его беда -
        # это в худшем случае тяжёлый кусок, ушедший как есть, а не конец фильма.
        except Exception as exc:
            state._say(f"перекодирование сорвалось ({exc}) - показ идёт как есть")
            nap(5.0)
