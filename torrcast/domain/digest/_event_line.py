"""Одна запись ленты в одну строку выжимки: чья это ветка и что печатать, если ничья.

Зовёт это сборка блока сеанса (:mod:`torrcast.domain.digest._session_block`).
"""

from __future__ import annotations

from collections.abc import Mapping

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.digest._search_line import _search_line
from torrcast.domain.digest._session_line import _session_line
from torrcast.domain.digest._show_line import _show_line
from torrcast.domain.digest._warm_line import _warm_line
from torrcast.domain.digest._words import _facts
from torrcast.domain.json_number import json_number
from torrcast.domain.json_value import JsonValue


def _event_line(rec: Mapping[str, JsonValue], began: float, seam: bool = False) -> str:
    """Запись ленты одной строкой; пусто - событие в выжимке не печатается вовсе.

    Ветки разведены по разборщикам: показ, поиск, прогрев, сеанс. Имя события у них не
    пересекается, поэтому порядок опроса на строку не влияет, а ``None`` значит ровно
    «событие не моё», в отличие от пустой строки - «моё, и печатать его не надо».
    """
    at = json_number(rec.get("at", 0.0)) - began
    stamp = phrase("digest.stamp", at=f"{at:6.1f}")
    event = str(rec.get("event", ""))
    told = _show_line(rec, stamp, seam)
    if told is None:
        told = _search_line(rec, stamp)
    if told is None:
        told = _warm_line(rec, stamp)
    if told is None:
        told = _session_line(rec, stamp)
    if told is not None:
        return told
    if str(rec.get("phase", "")) == "timeline":
        # Фазы критического пути (:func:`torrcast.adapters.filesystem.stopwatch.mark`)
        # уходят в ленту ВСЕГДА, а до
        # TC-194 не печатались НИКОГДА: своей ветки у них нет, и они выпадали в общий
        # «вернуть пусто» - целый класс событий, которого человек в `cast log` не видел,
        # хотя в jsonl он лежит. Имя фазы и её числа уже по-русски («отбор релиза
        # релиз=2»), поэтому печатаются как есть.
        return phrase("digest.phase", stamp=stamp, event=event, facts=_facts(rec))
    # Событие, о котором ЭТА версия не знает: чужая ветка, старая лента, новое поле.
    # Молчать о нём нельзя ровно по той же причине: пустая строка в выжимке читается как
    # «события не было», а оно было и лежит в файле.
    return f"{stamp}{rec.get('phase', '?')}/{event}{_facts(rec)}"
