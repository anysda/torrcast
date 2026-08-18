"""Картина, на которую однозначно указало паспортное имя прямо в первом пуле выдачи."""

from __future__ import annotations

from torrcast.domain.facts.origin import Origin
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.picture import Picture
from torrcast.usecases.discover._vouched import _vouched


def _passport_pick(
    first_pictures: list[Picture], about: Origin, found: list[Picture]
) -> list[Picture] | None:
    """Картина первого пула, названная паспортом; ``None`` - второй круг всё-таки нужен.

    Полное имя уже приехавшей картины может лежать только в паспорте. Короткий запрос
    ``lain`` сам по себе выбирает журнал ``lainzine``, хотя в том же первом пуле есть
    ``Serial Experiments Lain``. Второй круг тут ничего не находит - он лишь повторяет
    уже имеющуюся картину другим именем. Паспортное имя применяем прямо к первому пулу,
    но только когда оно однозначно указывает на одну картину и её год не спорит со
    справкой (:func:`_vouched`). Сам короткий запрос права голоса не получает.
    """
    passport_hits: dict[str, Picture] = {}
    for passport_name in (about.title, about.name):
        for picture in pick_franchise(passport_name, first_pictures):
            passport_hits[picture.key] = picture
    found_keys = {picture.key for picture in found}
    if len(passport_hits) == 1 and set(passport_hits) != found_keys:
        passport_found = list(passport_hits.values())
        if _vouched(passport_found, about, proven=True):
            return passport_found
    return None
