"""Плитки каталога и находки круга в одной выдаче: раздачи догоняют картины.

Пока круг идёт, плитки каталога стоят первыми, каждая на своём месте (``slot``): находка той
же картины встаёт В её плитку, а не рядом, и выдача под курсором не прыгает. Картину
узнаёт то же правило, каким карточка ищет свою картину в круге (:mod:`web.card_lookup`):
имя целиком и хотя бы одно из «род, год». Плитка, которой после ПОЛНОГО круга раздач не
нашлось, гаснет (``dim``); до конца круга она только ждёт (``pending``).
"""

from __future__ import annotations

from typing import Final

from torrcast.domain.json_value import JsonValue
from torrcast.domain.picture import Picture
from web.card_lookup import _score

#: Сколько должно совпасть: имя и род или имя и год. Опечатку в имени тут не верят.
_SAME: Final = 2

_Record = dict[str, JsonValue]


def catalog_merge(
    catalog: list[JsonValue], hits: list[JsonValue], *, done: bool
) -> list[JsonValue]:
    """Одна выдача из плиток каталога и находок; ``done`` - круг закончен целиком."""
    tiles = [tile for tile in catalog if isinstance(tile, dict)]
    found = [hit for hit in hits if isinstance(hit, dict)]
    slots: dict[int, str] = {}
    for tile in tiles:
        at = _match(tile, found, slots)
        if at is not None:
            slots[at] = _text(tile, "key")
    if done:
        taken = set(slots.values())
        return [
            *({**hit, "slot": slots[n]} if n in slots else hit for n, hit in enumerate(found)),
            *({**tile, "dim": True} for tile in tiles if _text(tile, "key") not in taken),
        ]
    landed = {key: n for n, key in slots.items()}
    return [
        *(
            {**found[landed[key]], "slot": key} if key in landed else {**tile, "pending": True}
            for tile in tiles
            if (key := _text(tile, "key"))
        ),
        *(hit for n, hit in enumerate(found) if n not in slots),
    ]


def _match(tile: _Record, hits: list[_Record], slots: dict[int, str]) -> int | None:
    """Номер находки той же картины, ещё не занятой другой плиткой; лучшая - первой."""
    keys = [_picture(tile, name).key for name in ("title", "original") if _text(tile, name)]
    best, at = 0, None
    for n, hit in enumerate(hits):
        if n in slots:
            continue
        score = max((_score(_picture(hit, "title"), key) for key in keys), default=0)
        if score >= _SAME and score > best:
            best, at = score, n
    return at


def _picture(record: _Record, name: str) -> Picture:
    """Картина записи под одним из её имён - тем же правилом ключа, что у круга."""
    year = record.get("year")
    return Picture(
        _text(record, name),
        year if isinstance(year, int) and not isinstance(year, bool) else None,
        "tv" if record.get("kind") == "tv" else "movie",
        _text(record, "original") or None,
    )


def _text(record: _Record, name: str) -> str:
    value = record.get(name)
    return value if isinstance(value, str) else ""


__all__ = ["catalog_merge"]
