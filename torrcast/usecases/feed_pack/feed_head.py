"""Общий заголовок показа, взятый из прогретого, когда живая упаковка молчит.

Зовёт его лента показа (:meth:`torrcast.usecases.feed_pack.feed.Feed.init`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torrcast.usecases.feed_pack._state as _state
from torrcast.domain.segment_container import FMP4

if TYPE_CHECKING:
    from pathlib import Path

    from torrcast.usecases.feed_pack.feed_state import _State


def _head(state: _State, head: Path) -> None:
    """Положить общий заголовок из прогретого, если своего у показа ещё нет.

    Манифест называет заголовок (``EXT-X-MAP``), и приёмник берёт его ПЕРВЫМ, до всякого
    куска: без него разбор не начинается вовсе - живой замер, приставка скачала 32 куска,
    а картинки не дала ни кадра.

    Кладёт его в каталог показа живая упаковка, одним файлом на весь прогон. Прогретое
    едет зрителю мимо упаковки - прямо с диска
    (:func:`torrcast.usecases.feed_pack.feed_segment._warm`), - и на прогретом фильме с мёртвым
    источником живая упаковка не поднимется вовсе. Отсюда и второй источник: прогрев
    пакует тем же муксером и свой заголовок в своём каталоге уже держит
    (:meth:`torrcast.usecases.warm.vault.Vault.head`).

    Прежний контейнер сюда не заходит вовсе: общего заголовка у него нет и в манифесте.
    """
    if state.container != FMP4 or state.vault is None or head.exists():
        return
    _state.lay_head(state.vault.head(), state.out)
