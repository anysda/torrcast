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
    """Положить общий заголовок из прогретого куска, если своего у показа ещё нет.

    Манифест называет заголовок (``EXT-X-MAP``), и приёмник берёт его ПЕРВЫМ, до всякого
    куска: без него разбор не начинается вовсе - живой замер, приставка скачала 32 куска,
    а картинки не дала ни кадра.

    Кладёт его выкладка живой упаковки, вырезая из первого же выложенного куска
    (:func:`torrcast.adapters.stream_pack.lay_head.lay_head`). Прогретое едет зрителю мимо
    выкладки - прямо с диска (:func:`torrcast.usecases.feed_pack.feed_segment._warm`), - и
    на прогретом фильме с мёртвым источником живая упаковка не выложит ничего никогда.
    Отсюда и второй источник заголовка: каталог прогретого, где лежат такие же куски.

    Годится кусок любого места, поэтому берётся первый попавшийся: кусок fMP4
    самодостаточен, свои параметры несёт сам и дальше переопределяет ими то, что приёмник
    прочитал из заголовка. Спрашивается каталог целиком (:meth:`_Vault.slots`), а не место
    показа: заголовок нужен раньше, чем приёмник назвал хоть одно место.

    Прежний контейнер сюда не заходит вовсе: общего заголовка у него нет и в манифесте.
    """
    if state.container != FMP4 or state.vault is None or head.exists():
        return
    warmed = state.vault.slots()
    if not warmed:
        return
    _state.lay_head(state.vault.path(min(warmed)), state.out)
