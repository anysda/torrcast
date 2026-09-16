"""Плитки каталога и находки круга в одной выдаче: раздачи догоняют картины.

Пока круг идёт, плитки каталога стоят первыми, каждая на своём месте (``slot``): находка той
же картины встаёт В её плитку, а не рядом, и выдача под курсором не прыгает ни во время
круга, ни в его конце: зритель уже навёл курсор на плитку и жмёт. Картину узнаёт то же
правило, каким карточка ищет свою картину в круге (:mod:`web.card_lookup`): имя целиком и
хотя бы одно из «род, год». Пока круг идёт, плитка без находки ждёт (``pending``), а к концу
круга остаётся обычной плиткой каталога.

🔴 Плитка БЕЗ находки не гаснет и клика не теряет. Круг этой выдачи спрошен по набранному
тексту, и его молчание о картине - не приговор ей: карточка спрашивает раздачи заново, по
собственному имени картины (``web/static/home.js``), и «Атака клонов», которой тут находки
не досталось, отвечала 57 раздачами. Серость же говорила «играть нечего» там, где нечего
было только этому кругу, и отнимала клик у всех таких плиток без исключения. Место в круге
(``pick``) с такой плитки снимается: она его не занимала, и страница по нему решает, каким
именем спрашивать раздачи.

Догадка подсказчика (:data:`~hass.catalog_tiles.GUESS`) без раздач после круга уходит
совсем: про неё мы не знаем даже того, что такая картина есть.
"""

from __future__ import annotations

from typing import Final

from hass.catalog_tiles import GUESS
from torrcast.domain.json_value import JsonValue
from torrcast.domain.picture import Picture
from web.card_lookup import _score

#: Сколько должно совпасть: имя и род или имя и год. Опечатку в имени тут не верят.
_SAME: Final = 2

#: Чего у плитки без находки быть не может: догадки подсказчика и места в круге.
_NOT_FOUND: Final = frozenset({GUESS, "pick"})

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
    landed = {key: n for n, key in slots.items()}
    return [
        *(
            {**found[landed[key]], "slot": key} if key in landed else _waiting(tile, done)
            for tile in tiles
            if (key := _text(tile, "key")) and (key in landed or not (done and tile.get(GUESS)))
        ),
        *(hit for n, hit in enumerate(found) if n not in slots),
    ]


def _waiting(tile: _Record, done: bool) -> _Record:
    """Плитка, которой находки не досталось: ждёт, пока круг идёт, и не больше того."""
    return _bare(tile) if done else {**_bare(tile), "pending": True}


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


def _bare(tile: _Record) -> _Record:
    """Плитка каталога без следов круга: места в нём (``pick``) у неё нет.

    Плитки строятся тем же ``_hit``, что и находки, и несут ``pick`` нулём
    (:mod:`hass.catalog_tiles`). Страница читает его как «раздачи уже принесены» и
    спрашивает карточку набранным текстом - тем самым, каким круг о картине промолчал.
    """
    return {name: value for name, value in tile.items() if name not in _NOT_FOUND}


def _text(record: _Record, name: str) -> str:
    value = record.get(name)
    return value if isinstance(value, str) else ""


__all__ = ["catalog_merge"]
