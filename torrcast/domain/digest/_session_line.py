"""Строки выжимки про сам сеанс: ошибка, начало с порогами, конец и потери ленты.

Ветка отдаёт ``None``, если событие не её: разбор идёт дальше по разборщикам
(:func:`torrcast.domain.digest._event_line._event_line`).
"""

from __future__ import annotations

from collections.abc import Mapping

from torrcast.domain.digest._words import _hms
from torrcast.domain.json_map import json_map
from torrcast.domain.json_number import json_number
from torrcast.domain.json_value import JsonValue


def _session_line(rec: Mapping[str, JsonValue], stamp: str) -> str | None:
    """Событие сеанса одной строкой; не его событие - ``None``."""
    event = str(rec.get("event", ""))
    if event == "error":
        return f"{stamp}ошибка: {rec.get('text', '')}"
    if event == "session_start":
        return _session_start(rec, stamp)
    if event == "session_end":
        return ""  # конец сеанса печатает итоговая строка блока, второй раз незачем
    if event == "lost":
        return (
            f"{stamp}потеряно записей {rec.get('count', '?')}:"
            " очередь следа переполнилась - этих решений в ленте нет"
        )
    return None


def _session_start(rec: Mapping[str, JsonValue], stamp: str) -> str:
    """Начало показа: что играем, с какой секунды и по какому набору порогов."""
    # Профиль приёмника: по какому набору порогов играли. В записях прежних версий
    # его нет вовсе - тогда и в строке о нём молчим, а не пишем «профиль ?».
    profile = str(rec.get("profile", ""))
    head = f"{stamp}показ «{rec.get('title', '')}» с {_hms(json_number(rec.get('pos', 0.0)))}"
    if not profile:
        return head
    source = str(rec.get("profile_source", ""))
    thresholds = json_map(rec.get("thresholds"))
    origins = json_map(rec.get("threshold_sources"))
    profile_text = f" · профиль {profile}" + (f" ({source})" if source else "")
    if not thresholds:
        return f"{head}{profile_text}"
    # Всей строкой это 31 порог плюс 31 источник - тысяча с лишним символов, глазами
    # не читается. По одному порогу на строку - столбик, который читается.
    details = "\n    ".join(
        f"{key}={value} [{origins.get(key, '?')}]" for key, value in thresholds.items()
    )
    return f"{head}{profile_text} · пороги:\n    {details}"
