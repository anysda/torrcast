"""Уборка по часам показа: сдать успевшее и не дать несданному расти без предела.

Зовут отсюда часы показа (:mod:`torrcast.usecases.feed_pack.feed`), а не запрос сегмента.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torrcast.usecases.feed_pack._state as _state
from torrcast.ports.journal import journal
from torrcast.usecases.feed_pack._segment_files import _paths

if TYPE_CHECKING:
    from torrcast.usecases.feed_pack.feed_state import _State


def _sweep(state: _State) -> None:
    """Сдать всё, что упаковка успела, и не дать несданному расти без предела.

    Зовётся по часам показа, а не по запросу приёмника, и в этом весь смысл. Выкладка
    (:meth:`Packer.publish`) стоит на пути запроса сегмента, а запросов может не быть
    вовсе: пока показ берёт куски с диска (:meth:`_warm`), к упаковке никто не
    обращается, а ffmpeg продолжает писать в tmpfs. Замер: 897 МБ несданного за 14
    минут показа, рост без предела и без единой строки о нём.

    Потолок (:data:`PACK_PENDING_BYTES`) нужен и сверх этого. Выкладка встаёт на
    куске, придержанном под перекод, - и всё, что за ним, копится в памяти, сколько
    бы её ни было. (Тяжёлая копия выкладку больше не держит: она ужимается на месте
    или честно пропускается - :meth:`_shrink`.) Дойдя до потолка, показ гасит прогон
    одной честной строкой: куски, которых никто не забирает, стоят памяти и не дают
    приёмнику ничего, а снятый прогон отдаёт её обратно (:meth:`Packer.stop`).

    Подгруза это не добавляет: гасится то, что и так никуда не шло, уже выложенное
    остаётся лежать, а запрос следующего сегмента поднимает упаковку заново
    (:meth:`_steer`) - ровно как после паузы на пульте.
    """
    packer = state.packer
    if packer is None or packer.halted:
        return
    packer.publish()
    pending = packer.pending()
    if pending <= state.pending_cap:
        return
    state._say(
        f"несданных кусков {pending / 1e6:.0f} МБ в памяти - упаковку гашу, "
        "подниму её по запросу приёмника"
    )
    journal().mark("несданное копится", мб=round(pending / 1e6), край=packer.edge)
    packer.halt(reason=f"несданного {pending / 1e6:.0f} МБ в памяти")


def _prune(state: _State, played: float) -> None:
    """Убрать из tmpfs то, чего показу уже не нужно, — и позади показа, и впереди.

    Позади окно ``keep`` секунд: глубже — уже перемотка, и она честно перепакует поток.

    Впереди убирается то, что осталось от **прошлого места показа**. После отката
    назад глубже окна упаковка идёт с нового места, а сегменты той минуты, откуда
    ушёл зритель, лежат в tmpfs и не выметаются ничем: окно смотрит только назад, а
    снова дойти до них показ может уже и не дойти. Десяток откатов подряд — и в
    памяти лежат места фильма, которых на экране не будет.

    Граница честная и не задевает ни запаса, ни префетча: остаётся всё, что этот
    прогон уже выложил или вот-вот выложит (``edge + ahead``), и всё, что рядом с
    позицией приёмника. Выше — куски, которых текущий прогон не делал и в ближайшее
    время не сделает. Упаковки нет вовсе — вперёд не трогаем ничего: без прогона край
    неизвестен, а гадать на этом месте дороже, чем подождать.
    """
    packer = state.packer
    keep_upto = -1
    if packer is not None:
        keep_upto = max(state.grid.slot_at(played), packer.edge) + state.ahead
    behind = state.grid.slot_at(played - state.keep) if played - state.keep > 0 else 0
    for path in _paths(state.out):
        slot = _state.segment_slot(path.name)
        if slot < 0:
            continue
        if slot < behind or (keep_upto >= 0 and slot > keep_upto):
            path.unlink(missing_ok=True)
