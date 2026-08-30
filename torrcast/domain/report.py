"""Лента меток критического пути как таблица: время от нуля и цена каждой фазы.

Чистый разбор уже прочитанных меток; читает их с диска сам секундомер
(:mod:`torrcast.adapters.filesystem.stopwatch`), а зовёт таблицу ``scripts/startbench.py``.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.json_number import json_number
from torrcast.domain.json_value import JsonValue


def report(marks: Sequence[Mapping[str, JsonValue]], zero: str = "") -> str:
    """Лента как таблица: время от нуля и цена каждой фазы.

    ``zero`` — метка, от которой считать ноль (обычно ``ответы``: старт меряется от
    Enter'а после последнего вопроса). Пусто — от первой метки.
    """
    rows = list(marks)
    if not rows:
        return phrase("trace.no_marks")
    base = next((json_number(m["at"]) for m in rows if m.get("name") == zero), None)
    if base is None:
        base = json_number(rows[0]["at"])
    head = (phrase("trace.column_phase"), phrase("trace.column_from_zero"))
    lines = [f"{head[0]:<28}{head[1]:>9}{phrase('trace.column_cost'):>8}  {'pid':>7}"]
    previous = base
    for entry in rows:
        at = json_number(entry["at"])
        facts = {k: v for k, v in entry.items() if k not in {"at", "name", "pid"}}
        tail = ("  " + " ".join(f"{k}={v}" for k, v in facts.items())) if facts else ""
        lines.append(
            f"{entry['name']!s:<28}{at - base:>+9.2f}{at - previous:>8.2f}"
            f"  {entry.get('pid', 0)!s:>7}{tail}"
        )
        previous = at
    return "\n".join(lines)
