"""Слова выжимки следа: время, вес и поля записи, у которой нет своей ветки.

Зовут это все ветки разбора ленты и сборка блока сеанса.
"""

from __future__ import annotations

import time
from collections.abc import Mapping
from typing import Final

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.json_value import JsonValue

#: Конверт записи (:func:`emit`): он одинаков у всех и в строке события не печатается.
_ENVELOPE: Final = frozenset({"at", "sid", "pid", "phase", "event"})


def _hms(seconds: float) -> str:
    seconds = max(0, int(seconds))
    h, rest = divmod(seconds, 3600)
    m, s = divmod(rest, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def _clock(at: float) -> str:
    return time.strftime("%d.%m %H:%M", time.localtime(at))


def _gb(size: float) -> str:
    return phrase("digest.gb", size=size / 1e9)


def _facts(rec: Mapping[str, JsonValue]) -> str:
    """Поля записи как есть, ``имя=значение``: чем печатать событие, у которого нет ветки.

    Для фазы таймлайна это не запасной вариант, а единственно верный: числа у неё разные
    у каждой метки (``слот=7 сдвиг=-1.71``), и знает их место вызова, а не этот модуль.
    """
    facts = ", ".join(f"{key}={value}" for key, value in rec.items() if key not in _ENVELOPE)
    return f" ({facts})" if facts else ""
