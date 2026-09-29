"""Голова показа с полки: живая упаковка начинается за ней, а не кодирует её второй раз.

Зовут отсюда начало показа (:func:`torrcast.usecases.feed_pack.feed_restart._begin`) и
решение об упаковке (:func:`torrcast.usecases.feed_pack.feed_steer._steer`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

import torrcast.usecases.feed_pack._state as _state
from torrcast.ports.journal.slot import journal
from torrcast.usecases.feed_pack.feed_segment import _have
from torrcast.usecases.warm.head_work import head_work

if TYPE_CHECKING:
    from torrcast.usecases.feed_pack.feed_state import _State

#: Сколько показ ждёт голову, которую ещё кладут, прежде чем паковать её сам. Заход головы
#: 1080p на 4 ядрах - 3-4.7 с («Призрак в доспехах»), а рядом с отбором второй
#: раздачи - до 14 с; начатая голова и тогда ляжет раньше новой. Знак захода, брошенный
#: упавшим процессом страницы, стоит показу не больше этого.
HEAD_WAIT: Final = 20.0


def _heading(state: _State, slot: int) -> int:
    """С какого места паковать показ, который начинается с ``slot``.

    Голову тяжёлого файла кладёт на полку процесс страницы, с карточки и с клика
    (:class:`torrcast.usecases.playback.head_ahead.HeadAhead`). Показ берёт кусок с полки
    раньше своего (:func:`torrcast.usecases.feed_pack.feed_segment._segment`), но его
    упаковка и кодировщик об этом не знают и кодируют то же место второй раз, на тех же
    ядрах: замер: два ffmpeg по 8.8 с процессора на одну голову разом, и лёгшая
    голова опоздала на 2.6 с. Поэтому место, которое на полке уже лежит или которое туда
    сейчас кладут, живая упаковка обходит, как обходит прогретое (:func:`_seam`).
    """
    vault = state.vault
    if vault is None or slot + 1 >= state.grid.count:
        return slot
    if state.heading[0] == slot:
        return slot + 1  # голову уже взяли до кодировщика (:meth:`Feed.claim_head`)
    laying = head_work(vault.head().parent, slot).exists()
    if not laying and not _have(state, slot):
        return slot
    state.heading = (slot, _state.clock_port.monotonic())
    if state.recoder is not None:
        state.recoder.done.add(slot)  # кодировать это место кодировщику показа незачем
    journal().mark("голова с полки", слот=slot, кладут=laying)
    return slot + 1


def _awaiting(state: _State, slot: int) -> bool:
    """Место ``slot`` - голова, которую ещё кладут; ``True`` - ждать её, а не паковать.

    Заход головы кончился, а куска на полке нет - голова не легла, и место снова
    обычное: упаковка берёт его сама, и кодировщик тоже.
    """
    place, since = state.heading
    if place != slot or state.vault is None:
        return False
    fresh = _state.clock_port.monotonic() - since < HEAD_WAIT
    if fresh and head_work(state.vault.head().parent, slot).exists():
        return True
    state.heading = (-1, 0.0)
    if _have(state, slot):
        return True  # голова легла между взглядом на полку и этим: следующий взгляд её возьмёт
    if state.recoder is not None:
        state.recoder.done.discard(slot)
    journal().mark("голову с полки не дождался", слот=slot)
    return False
