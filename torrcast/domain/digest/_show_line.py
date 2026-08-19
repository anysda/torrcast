"""Строки выжимки про сам показ: куски, план кодирования и всё, что мешало играть.

Ветка отдаёт ``None``, если событие не её: разбор идёт дальше по разборщикам
(:func:`torrcast.domain.digest._event_line._event_line`).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from torrcast.domain.digest._words import _hms
from torrcast.domain.json_number import json_number
from torrcast.domain.json_value import JsonValue
from torrcast.domain.trace_sources import PACKED, WARMED

#: Решение о кодировании куска по-русски (:func:`plan`).
_PLAN: Final = {"copy": "копия", "recode": "перекод"}

#: Как называется источник куска в выжимке.
_SOURCES: Final = {PACKED: "живая упаковка", WARMED: "прогретое"}


def _show_line(rec: Mapping[str, JsonValue], stamp: str, seam: bool) -> str | None:
    """Событие показа одной строкой; не его событие - ``None``."""
    event = str(rec.get("event", ""))
    if event == "segment":
        # Каждый кусок в выжимку не печатаем - их сотни; печатаем только смену источника.
        if not seam:
            return ""
        src = str(rec.get("src", ""))
        return f"{stamp}v{rec.get('slot', '?')}: источник сменился на {_SOURCES.get(src, src)}"
    if event == "plan":
        spots = int(json_number(rec.get("spots", 0)))
        tail = f", точечный перекод {spots}" if spots else ""
        return (
            f"{stamp}куски: упаковка - {_PLAN.get(str(rec.get('pack', '')), '?')},"
            f" прогрев - {_PLAN.get(str(rec.get('warm', '')), '?')}{tail}"
        )
    if event == "note":
        return f"{stamp}{rec.get('text', '')}"
    if event == "buffering":
        return f"{stamp}ребуфер на {_hms(json_number(rec.get('pos', 0.0)))}"
    if event == "offline":
        # Спрошенный источник называется источником: «сеть» тут была бы догадкой, а мы
        # знаем точно - служба ответила (или не ответила) нам сама.
        head = "источник" if rec.get("asked") else "сеть"
        return f"{stamp}{head}: {rec.get('why', 'обрыв')}"
    if event == "resupply":
        end = "раздача вернулась" if rec.get("ok") else "служба ещё не отдала раздачу"
        return f"{stamp}раздачу добавил магнитом заново - {end}"
    if event == "nudge":
        return (
            f"{stamp}нудж сторожа {rec.get('hit', 1)}:"
            f" {_hms(json_number(rec.get('pos', 0.0)))} -> {_hms(json_number(rec.get('to', 0.0)))}"
            f" (стоял {json_number(rec.get('stuck', 0.0)):.0f} с,"
            f" готово впереди"
            f" {json_number(rec.get('front', 0.0)) - json_number(rec.get('pos', 0.0)):.0f} с)"
        )
    if event == "reload":
        error = ""
        if "error" in rec:
            error = f", код {rec['error']}" if rec.get("error") is not None else ", без кода"
        return (
            f"{stamp}приёмник отвалился на {_hms(json_number(rec.get('pos', 0.0)))}"
            f"{error} - повтор LOAD {rec.get('tries', 1)}"
        )
    if event == "dark":
        # Поле shown разделяет две разные аварии: погасший показ человек успел
        # посмотреть, а показ без единого кадра - это «включил и не включилось»
        # (:func:`torrcast.adapters.filesystem.trace_journal.dark`). В записях прежних
        # версий поля нет - они все про погасший показ, поэтому умолчание True.
        head = (
            f"показ погас на {_hms(json_number(rec.get('pos', 0.0)))}"
            if rec.get("shown", True)
            else "показ не дал ни кадра"
        )
        return f"{stamp}{head}: {rec.get('why', 'приёмник бросил показ')}"
    if event == "revive":
        took = "показ поднят" if rec.get("ok") else "приёмник показ не взял"
        return (
            f"{stamp}{took} с {_hms(json_number(rec.get('pos', 0.0)))}"
            f" (попытка {rec.get('tries', 1)},"
            f" темнота {json_number(rec.get('waited', 0.0)):.0f} с)"
        )
    if event == "seek":
        wait = rec.get("wait")
        # Картинки не было вовсе - это отдельный исход, а не нулевое ожидание: нулём его
        # печатала как раз старая метрика, верившая слову приёмника.
        back = (
            f" картинка через {json_number(wait):.1f} с"
            if wait is not None
            else f" картинки так и не было: {rec.get('why', 'причина не названа')}"
        )
        return (
            f"{stamp}перемотка {_hms(json_number(rec.get('frm', 0.0)))}"
            f" -> {_hms(json_number(rec.get('to', 0.0)))},{back}"
        )
    return None
