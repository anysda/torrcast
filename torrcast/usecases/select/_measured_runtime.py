"""Длительность картины, замеренная паспортом файла прошлого показа."""

from __future__ import annotations

from torrcast.domain.entry import Entry
from torrcast.domain.watch_state import WatchState


def _measured_runtime(state: WatchState, key: str, found: tuple[str, Entry] | None = None) -> float:
    """Сколько секунд длится файл этой картины по записи состояния; ноль - не смотрели.

    Знаменатель битрейта у ворот отбора до первого ffprobe - прикидка по типу картины
    (:data:`torrcast.domain.runtime_guess.RUNTIME_GUESS`), и ошибается она в разы: серия
    «Киберпанка» длится 27 минут, а не 45, и релиз, прикинутый «9.1 Мбит/с», едет
    зрителю сплошным перекодом на честных 17. У уже начатой картины замер лежит в записи
    (:attr:`Entry.dur` пишет паспорт ffprobe), и гадать рядом с ним незачем: серии одного
    сериала и части одной франшизы различаются минутами, а не вдвое.

    Ищется так же, как память студии (:func:`_studio_seen`): сперва по каноническому
    ключу картины, а запись, найденная по тексту запроса, берём запасным вариантом -
    у соседней части франшизы хронометраж тот же по порядку, и замер соседа честнее
    прикидки «фильм это два часа».
    """
    entry = state.get(key) or (found[1] if found is not None else None)
    if entry is None or entry.dur <= 0:
        return 0.0
    return entry.dur
