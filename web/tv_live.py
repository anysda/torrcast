"""Идёт ли каст на телевизор прямо сейчас - один ответ на все экраны страницы.

Признак показа (:meth:`torrcast.domain.watch_state.WatchState.showing`) места показа НЕ
знает: он судит по непустому :attr:`torrcast.domain.entry.Entry.torrent` и приёмника не
спрашивает вовсе. Экраны брали его за «приёмник занят» и рисовали состояние приёмника
поверх показа, который идёт во вкладке: карточка ставила «Подключиться»/«Завершить», а
шапка главной - плашку показа. Телевизора при этом могло не быть у машины вовсе.

Слово о касте приходит двумя путями, теми же, что и у ящика вкладки (:mod:`web.box`):
сырым полем ``tv`` ящика (его пишет :mod:`torrcast.usecases.playback._play` любому
приёмнику, кроме вкладки) и держателем каста, унесённого из вкладки по «На ТВ»
(:mod:`web.tv_session`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from torrcast.ports.state_store.slot import store
from web.tv_session import SESSION


def tv_live(seen: Mapping[str, Any]) -> bool:
    """Каст на ТВ по УЖЕ прочитанному ящику; ``seen`` - тело :func:`web.box.box`.

    Сырому слову ящика веры нет без живого показа: раз написанное ``tv: true`` переживает
    снятый «cast stop» показ навсегда (:mod:`web.box`). Держатель каста вкладки отвечает
    сам за себя и в этой проверке не нуждается.
    """
    raised = bool(seen.get("tv", False)) and store().load().showing() is not None
    return raised or SESSION.settle(str(seen.get("key", "")))
