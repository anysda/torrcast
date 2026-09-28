"""Обложка родительского сериала для его именованного спецвыпуска.

Сама карточка сперва ищется всегда: чужой постер хуже пустоты. Этот ход включается
только после её промаха, когда родитель уже есть в той же выдаче с готовыми байтами.
"""

from __future__ import annotations

from collections.abc import Callable

from torrcast.domain.json_value import JsonValue
from torrcast.domain.slugify import slugify

_FIELD = "poster"


def serial_parent_posters(records: list[JsonValue], has: Callable[[str], bool]) -> list[JsonValue]:
    """Дать спецвыпуску готовую обложку его доказанного родительского сериала."""
    parents = [record for record in records if _ready_parent(record, has)]
    return [_with_parent(record, parents) for record in records]


def _ready_posters(records: list[JsonValue], has: Callable[[str], bool]) -> list[JsonValue]:
    """Оставить имя только у обложки, чьи байты уже можно отдать."""
    return [
        {name: value for name, value in record.items() if name != _FIELD}
        if isinstance(record, dict) and (name := _poster_name(record)) and not has(name)
        else record
        for record in records
    ]


def _with_parent(record: JsonValue, parents: list[JsonValue]) -> JsonValue:
    if not isinstance(record, dict) or record.get(_FIELD) or record.get("kind") != "tv":
        return record
    # Два возможных родителя - уже догадка, а чужая обложка хуже пустоты.
    found = [one for one in parents if isinstance(one, dict) and _parent_of(record, one)]
    names = {_poster_name(one) for one in found}
    return {**record, _FIELD: names.pop()} if len(names) == 1 else record


def _ready_parent(record: JsonValue, has: Callable[[str], bool]) -> bool:
    return bool(
        isinstance(record, dict)
        and record.get("kind") == "tv"
        and (name := _poster_name(record))
        and has(name)
    )


def _parent_of(special: dict[str, JsonValue], parent: JsonValue) -> bool:
    return isinstance(parent, dict) and _same_series(parent, special)


def _same_series(parent: dict[str, JsonValue], special: dict[str, JsonValue]) -> bool:
    """Одно исходное имя и год, иначе тёзка или соседний сериал не родитель."""
    parent_year, special_year = parent.get("year"), special.get("year")
    years_match = (
        isinstance(parent_year, int)
        and isinstance(special_year, int)
        and parent_year == special_year
    )
    return years_match and _original(parent) == _original(special)


def _original(record: dict[str, JsonValue]) -> str:
    original = record.get("original")
    return slugify(original) if isinstance(original, str) and original.strip() else ""


def _poster_name(record: dict[str, JsonValue]) -> str:
    value = record.get(_FIELD)
    return value if isinstance(value, str) else ""


__all__ = ["serial_parent_posters"]
