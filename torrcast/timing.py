"""Секундомер критического пути старта: где именно уходят секунды до картинки.

Зачем отдельный модуль, а не `print` с временем: старт живёт **в двух процессах**. CLI
ищет, греет раздачи и задаёт вопросы, а сам показ уезжает в transient-юнит
(:func:`torrcast.stream.start_play_unit`), и склеить их логи по времени иначе нечем.
Поэтому метки пишутся в один файл, путь к которому едет юниту через окружение
(``TORRCAST_TIMELINE``, см. :data:`torrcast.stream._PASS_ENV`), а время берётся стенное
(:func:`time.time`) — монотонное у двух процессов разное.

Выключено по умолчанию: без переменной окружения :func:`mark` не делает ничего и не
стоит ничего. Разбор ленты — :func:`report`, им пользуется ``scripts/startbench.py``.

Здесь же живёт источник времени показа (:class:`Clock`, :data:`CLOCK`): всё, что ждёт
секундами - терпение приёмника, выдержка между попытками подъёма, опрос показа раз в
2 с, - спрашивает время у него, а не у :mod:`time` напрямую.
"""

from __future__ import annotations

import contextlib
import json
import os
import time
from pathlib import Path
from typing import Any, Final, Protocol, runtime_checkable

__all__ = ["CLOCK", "TIMELINE_ENV", "Clock", "RealClock", "mark", "read", "report"]

#: Куда писать ленту меток. Пусто - секундомера нет.
TIMELINE_ENV: Final = "TORRCAST_TIMELINE"


@runtime_checkable
class Clock(Protocol):
    """Часы показа: монотонное время и сон. Ровно то, чем меряют терпение и выдержки.

    Заведены не ради «чистоты», а ради сухого прогона. Времени тут ждут минутами
    (терпение приёмника, выдержка между попытками подъёма), и тест, честно выждавший их,
    никто гонять не станет. Подменять же :func:`time.sleep` на весь процесс - хуже
    настоящего сна: патч видят и чужие потоки, живые в этот момент, и каждый их сон
    двигает часы теста. Отсюда часы отдельным объектом: у боевого пути они настоящие
    (:data:`CLOCK`), у теста - свои, и никто, кроме него, их не трогает.
    """

    def monotonic(self) -> float:
        """Монотонные секунды: считать ими разрешено только разницу."""

    def sleep(self, seconds: float) -> None:
        """Подождать ``seconds`` секунд."""


class RealClock:
    """Настоящее время: ровно :func:`time.monotonic` и :func:`time.sleep`."""

    def monotonic(self) -> float:
        return time.monotonic()

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


#: Часы боевого пути. Заводить свои незачем - объект без состояния.
CLOCK: Final[Clock] = RealClock()


def mark(name: str, **facts: object) -> None:
    """Отметить фазу критического пути.

    Секундомер старта (файл ``TORRCAST_TIMELINE``) остаётся выключенным по умолчанию, а вот
    в недельный след фаза уходит всегда: он и заведён затем, чтобы знать про сеанс всё, и
    все точки ``mark`` (поиск, индексеры, старт показа, прогрев) он подбирает даром, не
    заводя вторых вызовов. Запись буферизованная и не в горячем пути (:func:`torrcast.trace.emit`).
    """
    from torrcast import trace

    trace.emit("timeline", name, **facts)
    path = os.environ.get(TIMELINE_ENV)
    if not path:
        return
    line = json.dumps({"at": time.time(), "name": name, "pid": os.getpid(), **facts})
    # Дозапись строкой короче PIPE_BUF атомарна и без замка: пишут два процесса.
    with contextlib.suppress(OSError), open(path, "a", encoding="utf-8") as fp:
        fp.write(line + "\n")


def read(path: str | Path) -> list[dict[str, Any]]:
    """Лента меток по возрастанию времени."""
    found: list[dict[str, Any]] = []
    with contextlib.suppress(OSError):
        for raw in Path(path).read_text("utf-8").splitlines():
            with contextlib.suppress(ValueError):
                found.append(json.loads(raw))
    return sorted(found, key=lambda e: float(e.get("at", 0.0)))


def report(path: str | Path, zero: str = "") -> str:
    """Лента как таблица: время от нуля и цена каждой фазы.

    ``zero`` — метка, от которой считать ноль (обычно ``ответы``: старт меряется от
    Enter'а после последнего вопроса). Пусто — от первой метки.
    """
    marks = read(path)
    if not marks:
        return "меток нет"
    base = next((float(m["at"]) for m in marks if m.get("name") == zero), None)
    if base is None:
        base = float(marks[0]["at"])
    lines = [f"{'фаза':<28}{'от нуля':>9}{'цена':>8}  {'pid':>7}"]
    previous = base
    for entry in marks:
        at = float(entry["at"])
        facts = {k: v for k, v in entry.items() if k not in {"at", "name", "pid"}}
        tail = ("  " + " ".join(f"{k}={v}" for k, v in facts.items())) if facts else ""
        lines.append(
            f"{entry['name']!s:<28}{at - base:>+9.2f}{at - previous:>8.2f}"
            f"  {entry.get('pid', 0)!s:>7}{tail}"
        )
        previous = at
    return "\n".join(lines)
