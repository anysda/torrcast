"""Приговоры играбельности полок несколькими руками: по порядку и ровно сколько нужно.

Одна проверка стоит секунды (круг индексеров и дорожки TorrServer, :mod:`web.shelf_playable`),
а на полку их нужно десятки: по одной руке холодная полка ждала приговоров 160-210 с из
186 (замер TC-1322). Здесь их ведут ``workers`` рук разом, но не шире нужного: полка
просит приговор следующего кандидата, только пока «играет» или ещё не решённых у неё
меньше ``limit`` - ровно та очередь, которой шёл :func:`web.shelf_tiles._covered` по
одной руке, и при одной руке порядок вызовов тот же.

Полки идут по очереди старшинства: руки берут кандидата первой полки, пока она просит, и
только свободная рука уходит ко второй. Полка, которой больше ничего не нужно и чьи
приговоры все вернулись, закрывается сразу (``closed``), не дожидаясь соседней.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from typing import Final

#: Приговор: ``True`` играет, ``False`` не играет, ``None`` не знаем (плитка остаётся).
Verdict = bool | None
#: Кандидаты полок в их порядке: пары (запрос, ключ) у плиток с обложкой. Список
#: зовётся заново на каждом шаге - обложки доезжают, и кандидатов у полки прибавляется.
Lanes = Callable[[], list[list[tuple[str, str]]]]
#: Как часто сборщик оглядывается, пока приговоры в пути: ему же обновлять видимую полку.
TICK: Final = 0.5


def shelf_judge(
    lanes: Lanes,
    limit: int,
    playable: Callable[[str, str], Verdict],
    workers: int,
    closed: Callable[[int], None],
    tick: Callable[[], None],
    verdicts: dict[str, Verdict],
    growing: Callable[[], bool] = lambda: False,
) -> None:
    """Приговоры кандидатов всех полок в ``verdicts``; ``closed(i)`` - полке ``i`` ждать нечего.

    ``verdicts`` пишет только этот поток, и читают его ``closed`` и ``tick`` - тоже в нём.
    Пока ``growing()`` - обложки ещё едут, - полка, дошедшая до конца очереди, не закрывается:
    её очередь ещё прибавится; закрывает её тогда только набранный ``limit``.
    """
    cursors: dict[int, int] = {}
    running: dict[Future[Verdict], tuple[str, set[int]]] = {}
    shut: set[int] = set()
    hands = max(workers, 1)

    def owed(index: int, lane: list[tuple[str, str]]) -> bool:
        at = cursors.get(index, 0)
        kept = sum(1 for _query, key in lane[:at] if verdicts.get(key, True) is not False)
        return kept < limit and at < len(lane)

    def full(index: int, lane: list[tuple[str, str]]) -> bool:
        at = cursors.get(index, 0)
        return sum(1 for _query, key in lane[:at] if verdicts.get(key, True) is not False) >= limit

    def busy(index: int) -> bool:
        return any(index in lanes_of for _key, lanes_of in running.values())

    with ThreadPoolExecutor(hands, thread_name_prefix="shelf-judge") as pool:
        while True:
            current, more = lanes(), growing()
            for index, lane in enumerate(current):
                idle = not owed(index, lane) and not busy(index)
                if index not in shut and idle and (not more or full(index, lane)):
                    shut.add(index)
                    closed(index)
            for index, lane in enumerate(current):
                while index not in shut and len(running) < hands and owed(index, lane):
                    query, key = lane[cursors.get(index, 0)]
                    cursors[index] = cursors.get(index, 0) + 1
                    twin = next((lanes_of for k, lanes_of in running.values() if k == key), None)
                    if twin is not None:
                        twin.add(index)
                    elif key not in verdicts:
                        running[pool.submit(playable, query, key)] = (key, {index})
            if not running:
                if all(index in shut for index in range(len(current))):
                    return
                time.sleep(TICK)  # covers are still landing: the lanes grow, nothing to wait on
                tick()
                continue
            done, _ = wait(running, timeout=TICK, return_when=FIRST_COMPLETED)
            for future in done:
                key, _lanes = running.pop(future)
                verdicts[key] = future.result()
            tick()


__all__ = ["TICK", "Lanes", "Verdict", "shelf_judge"]
