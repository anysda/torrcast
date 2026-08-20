"""Сторож утёкших потоков: тест обязан закрыть за собой всё, что поднял.

Поток, переживший свою пробу, попадает в среду СЛЕДУЮЩЕЙ и пишет туда свои сны и свои
записи. Краснеет при этом сосед - обвиняется невиновный, а виновник уезжает дальше, и
следующий настоящий красный спишут на ту же «флаки». Сторож называет виновника: живой
после пробы поток роняет ровно ту пробу, которая его подняла.
"""

from __future__ import annotations

import threading
import time

from torrcast.adapters.filesystem.trace_journal import writer

#: Сколько ждать поток, которому осталось доработать миллисекунды. Проба, дождавшаяся
#: своего потока (``join``), платит тут ноль: цикл сразу видит пустой остаток. Выдержка
#: нужна против гонки «поток кончается ровно в этот миг» - ложный красный сторожа был бы
#: ровно той болезнью, которую он лечит.
GRACE = 0.5
#: Шаг опроса внутри выдержки.
STEP = 0.01


def alive() -> set[threading.Thread]:
    """Живые потоки прогона прямо сейчас."""
    return {thread for thread in threading.enumerate() if thread.is_alive()}


def _forgiven(thread: threading.Thread) -> bool:
    """Поток, который принадлежит не пробе, а процессу целиком.

    Такой тут ровно один - фоновая запись ленты следа
    (:class:`torrcast.adapters.filesystem.trace_journal.writer._Writer`). Она заводится
    на первой же записи и живёт до конца процесса; закрыть её «за собой» проба не может,
    да и незачем: файл ленты выбирается в момент события, а не в момент записи, поэтому в
    чужую пробу такой поток ничего не приносит. Сверяем по САМОМУ объекту, а не по имени:
    второй писатель с тем же именем потока прощён уже не будет.
    """
    return thread is writer._writer._thread


def leaked(before: set[threading.Thread]) -> list[threading.Thread]:
    """Потоки, поднятые пробой и живые после неё; ждёт их до :data:`GRACE`."""
    end = time.monotonic() + GRACE
    while True:
        left = [
            thread for thread in alive() - before if thread.is_alive() and not _forgiven(thread)
        ]
        if not left or time.monotonic() >= end:
            return left
        time.sleep(STEP)


def _named(thread: threading.Thread) -> str:
    """Поток по имени и по телу: имени мало, чтобы найти, кто его поднял."""
    target = getattr(thread, "_target", None)
    where = getattr(target, "__qualname__", "")
    module = getattr(target, "__module__", "")
    tail = f", тело {module}.{where}" if where else ""
    return f"{thread.name!r}{tail}"


def complain(nodeid: str, left: list[threading.Thread]) -> str:
    """Строка сторожа: кто оставил поток и чем это грозит соседу."""
    names = "; ".join(_named(thread) for thread in left)
    return (
        f"{nodeid}: после теста остался живой поток: {names}. "
        "Он попадёт в среду следующей пробы и покрасит её ложно, а виновным окажется "
        "сосед: останови поток и дождись его (join) в самом тесте"
    )
