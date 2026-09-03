"""Просьба о постере из записи выдачи и имя её картинки; зовёт список находок."""

from __future__ import annotations

from hass.poster_name import poster_name
from torrcast.domain.facts.ask import Ask
from torrcast.domain.json_value import JsonValue


def _about(record: JsonValue) -> Ask | None:
    """Просьба о постере из записи выдачи; без названия картинку не ищут.

    Род сводится к тем же двум словам, какими его знает картинка карточки
    (:func:`hass.posters._kind`): полка у них общая, и третье слово завело бы на ней
    вторую запись про ту же картину.
    """
    if not isinstance(record, dict):
        return None
    title, year, kind = record.get("title"), record.get("year"), record.get("kind")
    original = record.get("original")
    if not isinstance(title, str) or not title.strip():
        return None
    named = year if isinstance(year, int) and not isinstance(year, bool) else None
    return Ask(
        title.strip(),
        named,
        "tv" if kind == "tv" else "movie",
        original.strip() if isinstance(original, str) else "",
    )


def _name(ask: Ask) -> str:
    """Имя картинки этой картины: оно же её имя на общей с карточкой полке."""
    return poster_name(ask.title, ask.year, ask.kind)
