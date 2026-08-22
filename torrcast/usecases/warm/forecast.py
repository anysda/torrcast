"""Во сколько байт обойдётся участок прогрева.

Спрашивает его бюджет диска на входе в заход и по ходу укладки (:func:`_work`, :func:`_run`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torrcast.usecases.warm._state as _state

if TYPE_CHECKING:
    from torrcast.usecases.warm.warmer_state import _State


def _forecast(state: _State, first: int, last: int) -> float:
    """Во сколько байт обойдётся этот участок. Считаем по нашему же битрейту, когда
    перекодируем, и по карте опорных кадров, когда копируем."""
    seconds = sum(state.grid.span(s) for s in range(first, last + 1))
    if state.encode is not None:
        mbit = float(state.encode.mbit)
        return (mbit + _state.AUDIO_MBIT) * _state.TS_OVERHEAD * seconds * 1e6 / 8
    if state.grid.weigh is not None:
        # Копия: каждый кусок взвешивается по той же карте, по которой сетка ставила
        # границы, - «кусок равен потолку» ошибался в обе стороны разом: лёгкое кино
        # переспросило на треть и вытеснило соседей зря, тяжёлое недоспросило вдвое,
        # и бюджет проверялся на вдвое меньшем числе, чем потом легло.
        return sum(
            state.grid.weigh(state.grid.start(s), state.grid.end(s)) for s in range(first, last + 1)
        )
    if state.delivered > 0:
        # Карты нет, но паспорт знает средний вес фильма - и он же, тем же числом, служит
        # живому показу ровным профилем тяжести
        # (:meth:`torrcast.adapters.recode.weights.Weights.flat`). Спрашивать по нему честнее,
        # чем по потолку: потолок - это верхняя ГРАНИЦА куска, а не его вес, и оценкой веса
        # он промахивается в обе стороны разом. Замер на релизах без карты: осторожные
        # 16 МБ занижали нужду, потолок приставки 28 МБ завышал её, а настоящие куски
        # лежали между - там, куда и показывает паспорт.
        # Потолок при этом никуда не девается: кусок тяжелее его показ с диска не возьмёт
        # (:meth:`torrcast.usecases.feed_pack.feed.Feed._warm`), и просить на такой кусок
        # больше потолка незачем - отсюда зажим сверху, а не замена одного другим.
        return sum(
            min(state.delivered * state.grid.span(s) * 1e6 / 8, float(state.cap))
            for s in range(first, last + 1)
        )
    # Ни карты, ни паспорта - вес куска оценить нечем, и остаётся потолок ТОГО приёмника,
    # для которого греем (:attr:`torrcast.usecases.warm.warmer_state._State.cap`), а не
    # осторожное умолчание завода. Незнакомому приёмнику достаётся тот же осторожный:
    # умолчание не трогается, оно приезжает из состояния прогрева.
    return seconds / max(state.grid.span(first), 1.0) * state.cap
