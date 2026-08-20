"""Общий инвентарь зеркал команды показа: план картины, запись состояния и подделки."""

from __future__ import annotations

from torrcast.domain.entry import Entry
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.select.plan import Plan

GB = 1024**3


def release(name: str = "Кино / Movie (1999) BDRip 1080p") -> Release:
    """Раздача, которой хватает на план и на запись показа."""
    return Release(
        raw_name=name,
        title="Кино",
        year=1999,
        quality="1080p",
        codec="H.264",
        voices=("Дубляж",),
        size=8 * GB,
        seeders=100,
        magnet="magnet:?xt=кино",
    )


def plan() -> Plan:
    """План по одной картине: пул из одной живой раздачи."""
    one = release()
    return Plan(
        picture=Picture(title="Кино", year=1999, releases=[one]),
        ranked=[one],
        runtime=120.0 * 60.0,
        warn_mbit=16.0,
    )


def plans(count: int = 3) -> list[Plan]:
    """Меню франшизы из ``count`` частей: у каждой части свой ключ и живая раздача."""
    menu = []
    for n in range(1, count + 1):
        one = release(f"Тачки {n} / Cars {n} ({2005 + n}) BDRip 1080p")
        menu.append(
            Plan(
                picture=Picture(title=f"Тачки {n}", year=2005 + n, releases=[one]),
                ranked=[one],
                runtime=110.0 * 60.0,
                warn_mbit=16.0,
            )
        )
    return menu


def entry(**rest: object) -> Entry:
    """Запись состояния под ключом картины: то, что читает закладка."""
    fields: dict[str, object] = {
        "title": "Кино",
        "magnet": "magnet:?xt=кино",
        "dur": 7200.0,
        "pos": 3600.0,
    }
    fields.update(rest)
    return Entry(**fields)  # type: ignore[arg-type]
