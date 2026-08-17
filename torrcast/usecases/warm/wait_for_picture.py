"""Ожидание картинки перед первым байтом прогрева.

Зовёт нитка прогрева (:func:`_work`) один раз, прежде чем лезть в раздачу.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torrcast.usecases.warm._state as _state
from torrcast.usecases.warm.settings import GUARD_HIGH, START_GRACE

if TYPE_CHECKING:
    from torrcast.usecases.warm.warmer_state import _State


def _wait_for_picture(state: _State) -> None:
    """Дождаться, пока у показа появится запас, и только потом лезть в раздачу.

    ⚠️ Замер: прогрев, поднятый вместе с показом, отнимает у первого сегмента 0.2 с
    (2.10 → 2.28 с готовности LOAD на «Моане 2») — свой ffmpeg, свой запрос к той же
    раздаче. Путь до картинки дорожать не имеет права ни на сотую, поэтому прогрев
    стоит, пока живая упаковка не наберёт запас, и трогается с места уже при играющем
    показе. Потолок ожидания нужен на случай, когда запас не меряют вовсе (mock,
    приёмник молчит): тогда прогрев всё равно начнётся, просто позже.
    """
    deadline = _state._environment.monotonic() + START_GRACE
    while (
        not state.stopped
        and state.slack < GUARD_HIGH
        and _state._environment.monotonic() < deadline
    ):
        _state._environment.sleep(0.5)
