"""Ближайший заход: подряд идущие тяжёлые куски, ещё не готовые и ещё успеваемые.

Зовёт его нитка кодировщика (:func:`_work`) перед каждым заходом."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.adapters.recode.recoder_state import _State


def _pick(state: _State) -> tuple[int, int] | None:
    """Ближайший заход: подряд идущие тяжёлые куски, ещё не готовые и ещё успеваемые.

    Заход не растягивается дальше, чем кодировщик успеет: каждый следующий кусок
    обязан быть готов раньше, чем до него дойдёт упаковщик, — иначе длинный заход
    сам себе и создаёт опоздание.
    """
    # Считать от края упаковки, а не от показа: то, что уже выложено, перекодировать
    # поздно - приёмник это либо забрал, либо заберёт из tmpfs.
    here = max(state.grid.slot_at(state.played), state.edge + 1)
    horizon = state.played + state.ahead
    heavy = set(state.targets)
    quickest = state.pace.table()[-1][1]
    first = None
    for slot in sorted(heavy):
        if slot < here or state.grid.start(slot) > horizon:
            continue
        if slot in state.done or state.ready(slot) is not None:
            continue
        first = slot
        break
    if first is None:
        return None
    # Голова прогона идёт заходом в один кусок - и потому самым быстрым пресетом
    # (:func:`preset_for` от нулевого срока). Возьми её в общий заход - срок считался
    # бы по последнему куску, вышел бы superfast, и голова была бы готова к 4-5-й
    # секунде вместо 2-3-й. Остальное подхватит следующий заход.
    if first == state.head:
        return first, first
    last = first
    spent = state.grid.span(first) / quickest
    while (
        last + 1 in heavy
        and last + 1 - first + 1 <= state.run_max
        and last + 1 not in state.done
        and state.ready(last + 1) is None
    ):
        spent += state.grid.span(last + 1) / quickest
        if spent > state.slack(last + 1):
            break
        last += 1
    # Одиночный тяжёлый кусок посреди потока не оставляй островом перекода между
    # двумя копиями: на некоторых приёмниках оба стыка подряд роняют медиасессию,
    # хотя каждый сегмент сам по себе исправен. Если до цели ещё есть зазор, возьми
    # по лёгкому соседу с каждой стороны и сделай один однородный заход. Голова выше
    # нарочно исключена, а срок правого соседа не даёт этой страховке устроить
    # подгруз ради более красивого стыка.
    if (
        last == first
        and first > here
        and first + 1 < state.grid.count
        and state.run_max >= 3
        and first - 1 not in state.done
        and first + 1 not in state.done
        and state.ready(first - 1) is None
        and state.ready(first + 1) is None
    ):
        joined = sum(state.grid.span(slot) for slot in range(first - 1, first + 2))
        if joined / quickest <= state.slack(first + 1):
            return first - 1, first + 1
    return first, last
