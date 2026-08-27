"""Где на ленте картинки и на ленте звука стоит место этого слота.

Спрашивает это выкладка упаковщика (:mod:`torrcast.adapters.stream_pack.packer_publish`) у
каждой склейки, прежде чем отдать её приёмнику.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.adapters.stream_pack.packer_state import _State


def slot_place(state: _State, slot: int) -> tuple[float, float]:
    """Место слота на обеих лентах прогона; ``nan`` - сверять не с чем, и места не проверяют.

    Мест два, а не одно, потому что лент две: на CMAF счётчик у каждой дорожки свой, и живой
    замер даёт между ними 10.0 с на одном и том же куске
    (:func:`torrcast.adapters.stream_pack.run_tape.run_tape`). На mpegts обе ленты равны общему
    :attr:`~.grid.Grid.origin`, и место выходит прежним ``grid.start(slot) + grid.origin``
    знак в знак.

    ``nan`` бывает по двум разным поводам, и оба честные: сетки у прогона нет (щупы и стенды)
    либо лента прогона ещё не измерена. Во втором случае прогон измерит её следующим куском.
    """
    if state.grid is None or state.tape is None:
        return math.nan, math.nan
    place = state.grid.start(slot)
    return place + state.tape[0], place + state.tape[1]
