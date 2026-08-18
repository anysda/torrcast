"""Стыки источника в ленте одного сеанса; зовёт их сборка блока сеанса и щупы."""

from __future__ import annotations

from collections.abc import Mapping, Sequence

from torrcast.domain.json_value import JsonValue


def _seams(rows: Sequence[Mapping[str, JsonValue]]) -> list[Mapping[str, JsonValue]]:
    """Записи сегментов, на которых сменился источник (:func:`segment`).

    Первый кусок сеанса стыком не считается: у него нет предыдущего источника, а «показ
    начался с прогретого» - не стык, а начало. Пустой список значит ровно «в ленте нет
    записей с полем ``src``» ИЛИ «источник за весь сеанс не менялся»: эти два случая
    различаются наличием самих записей сегментов, и путать их нельзя.
    """
    found: list[Mapping[str, JsonValue]] = []
    previous = ""
    for rec in rows:
        if rec.get("event") != "segment":
            continue
        src = str(rec.get("src", ""))
        if not src:
            continue
        if previous and src != previous:
            found.append(rec)
        previous = src
    return found
