"""Строки выжимки про поиск и отбор: запрос, индексеры, очередь и взятый релиз.

Ветка отдаёт ``None``, если событие не её: разбор идёт дальше по разборщикам
(:func:`torrcast.domain.digest._event_line._event_line`).
"""

from __future__ import annotations

from collections.abc import Mapping

from torrcast.domain.digest._words import _hms
from torrcast.domain.json_map import json_map
from torrcast.domain.json_number import json_number
from torrcast.domain.json_rows import json_rows
from torrcast.domain.json_value import JsonValue


def _search_line(rec: Mapping[str, JsonValue], stamp: str) -> str | None:
    """Событие поиска и отбора одной строкой; не его событие - ``None``."""
    event = str(rec.get("event", ""))
    if event == "indexers":
        return _indexers(rec, stamp)
    if event == "query":
        # Запрос печатался только в шапке сеанса («сеанс ... · «Сталкер»»), а сколько
        # строк и картин он принёс - нигде: у события не было своей ветки, и оно молча
        # выпадало из ленты. В записях прежних версий полей может не быть - молчим о них.
        raw, pictures = rec.get("raw"), rec.get("pictures")
        tail = f": строк {raw}" if raw is not None else ""
        tail += f", картин {pictures}" if pictures is not None else ""
        return f"{stamp}запрос «{rec.get('query', '')}»{tail}"
    if event == "select":
        return (
            f"{stamp}взят релиз {rec.get('release', '?')}"
            f" · {rec.get('quality', '?')} · {rec.get('track', '?')}"
            f" · ~{rec.get('mbit', '?')} Мбит/с"
        )
    if event == "queue":
        # Отсев до очереди - свёрткой, а не событием на раздачу: их сотни на запрос.
        # Сумма очереди и причин обязана сходиться с пулом, и в строке это видно глазами.
        dropped = json_map(rec.get("dropped"))
        reasons = ", ".join(f"{name} {count}" for name, count in dropped.items())
        lost = sum(int(json_number(count)) for count in dropped.values())
        head = f"{stamp}пул {rec.get('pool', '?')}: в очереди {rec.get('queued', '?')}"
        return f"{head}, выкинуто {lost}" + (f" ({reasons})" if reasons else "")
    if event == "runtime":
        # Знаменатель битрейта отбора: чем считали и откуда взяли (TC-185).
        got = "из справки" if rec.get("src") == "facts" else "прикидка: справка молчит"
        return f"{stamp}длительность {_hms(json_number(rec.get('secs', 0.0)))} - {got}"
    if event == "drop":
        return f"{stamp}отброшен релиз {rec.get('release', '?')}: {rec.get('why', '?')}"
    if event == "mute":
        # 🔴 TC-178. Русской озвучки не нашлось ни у одного проверенного кандидата, и
        # показ пошёл запасным ходом. Это дыра КАТАЛОГА, а не осечка отбора: по этим
        # записям замер и считает, у скольких картин русской дорожки нет вовсе.
        return (
            f"{stamp}русской озвучки нет ни у кого (проверено {rec.get('checked', '?')})"
            f" - играю релиз {rec.get('release', '?')}, звук {rec.get('lang', '?')}"
        )
    if event == "switch":
        # Смена КАРТИНЫ посреди отбора (TC-203): у выбранной играть нечем, рядом живёт
        # одноимённая живая. Решение это громкое, и в ленте оно обязано быть видно так же,
        # как на экране, - иначе разбор отказа не сойдётся с тем, что человек читал.
        return (
            f"{stamp}у «{rec.get('from', '?')}» играть нечем ({rec.get('why', '?')})"
            f" - ухожу к «{rec.get('to', '?')}»"
        )
    return None


def _indexers(rec: Mapping[str, JsonValue], stamp: str) -> str:
    """Круг по индексерам: кто сколько принёс, кто молчал и кто опоздал."""
    got = json_map(rec.get("got"))
    silent = json_rows(rec.get("silent"))
    took = json_map(rec.get("ms"))

    def _took(name: object) -> str:
        # Время держим за именем: «за 0.4 с» после счётчика, у молчунов - вместо него.
        # В записях прежних версий поля ms нет вовсе - тогда строка выглядит как раньше.
        ms = took.get(str(name))
        return f" за {json_number(ms) / 1000:.1f} с" if ms is not None else ""

    parts = ", ".join(f"{name}:{count}{_took(name)}" for name, count in got.items())
    tail = f"; молчат {', '.join(str(name) + _took(name) for name in silent)}" if silent else ""
    # Опоздавшие - не молчуны: круг ушёл по кворуму, а они доезжают доливом (TC-118).
    # Разница видна только тут, и без неё выжимка врала бы про причину хвоста.
    waited = json_rows(rec.get("late"))
    if waited:
        tail += f"; опоздали {', '.join(str(name) for name in waited)}"
    return f"{stamp}индексеры {parts or '-'}{tail}"
