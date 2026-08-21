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
    # Карты нет - вес куска неизвестен, и просим по потолку ТОГО приёмника, для которого
    # греем (:attr:`torrcast.usecases.warm.warmer_state._State.cap`), а не по осторожному
    # умолчанию завода. Замер на релизах, у которых карта отвергнута, а сетка выходит
    # ровная: с осторожными 16 МБ прогноз просил на 42.85 % меньше, чем нужно приёмнику
    # с потолком 28 МБ, и просил одно и то же на любом приёмнике. Места по такому расчёту
    # хватало всегда, а на диск ложилось меньше обещанного, и вылезало это ровно там, где
    # хуже всего: на тяжёлом релизе без карты, где эта ветка и работает.
    # Незнакомому приёмнику достаётся тот же осторожный потолок: умолчание не трогается,
    # оно приезжает из состояния прогрева.
    return seconds / max(state.grid.span(first), 1.0) * state.cap
