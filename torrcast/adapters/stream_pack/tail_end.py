"""Где на сетке кончается последний кусок фильма: по списку нарезки и звуку за картинкой.

Спрашивают сверка прогона (:func:`torrcast.adapters.stream_pack.packer_finished._reached`)
и выкладка (:func:`torrcast.adapters.stream_pack.done_slots.done_slots`) - одним местом,
чтобы прогон и выкладка не расходились во мнении о том же самом куске.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from torrcast.adapters.stream_pack.chunk_head import INIT
from torrcast.adapters.stream_pack.piece_overhang import piece_overhang
from torrcast.adapters.stream_probe.segment_name import segment_name
from torrcast.domain.segment_container import FMP4

if TYPE_CHECKING:
    from torrcast.adapters.stream_pack.packer_state import _State
    from torrcast.ports.feed_grid import FeedGrid


def tail_end(state: _State, grid: FeedGrid, listed: float) -> float:
    """Конец хвоста в секундах сетки: конец из списка (по видео) плюс звук за картинкой.

    Метки списка уже сдвинуты на начало ленты
    (:attr:`torrcast.adapters.stream_pack.grid.Grid.origin`), поэтому сдвиг вычитается.
    Звук за картинкой меряется по самому куску (:func:`piece_overhang`) с заголовком
    прогона, если кусок fMP4. Не прочли кусок - остаётся конец из списка.
    """
    tail = grid.count - 1
    piece = state.run / segment_name(tail, state.container)
    header = state.run / INIT if state.container == FMP4 else None
    over = piece_overhang(piece, header)
    end = listed - grid.origin
    return end if math.isnan(over) else end + over


__all__ = ["tail_end"]
