"""Номер запроса, прочитанный сезоном сериала: «имя N» → «имя sNe1» (TC-363).

Живёт отдельной единицей потому, что читателей у прочтения двое и оба снаружи: круг
поиска (:func:`~torrcast.usecases.discover.search_circle.search_circle`) и офлайн-переигровка
щупом. Пока прочтение было переписано в щупе своей копией, он строил планы по первому
сезону там, где показ строил их по второму.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.picture import Picture
from torrcast.domain.reads_season import reads_season

if TYPE_CHECKING:
    from torrcast.domain.args import Args


def _season_asked(found: list[Picture], name: str, pictures: list[Picture]) -> bool:
    """Номер запроса просит СЕЗОН сериала, а не часть франшизы (TC-363).

    Спрашивается ровно то же, что решил разбор (:func:`~torrcast.domain.reads_season.reads_season`),
    и сверяется его ответом: номер отдан сериалам франшизы, а не картине по счёту. Двух правил тут
    нет - есть одно, и cli лишь читает, чем оно кончилось: номер должен доехать до сезонной
    машинерии, а знает про сезоны она, а не разбор.
    """
    if not found or any(picture.kind != "tv" for picture in found):
        return False
    # Голое имя: номер снят выше, поэтому пополнение меню продолжениями сюда доехало бы
    # молча и переспорило бы разбор (:func:`~torrcast.domain.pick_franchise.pick_franchise`).
    return reads_season(pick_franchise(name, pictures, join_continuations=False))


def season_reread(
    args: Args, name: str, index: int | None, found: list[Picture], pictures: list[Picture]
) -> Args | None:
    """Перечитать номер запроса сезоном: запрос «имя N» → «имя sNe1» (TC-363).

    Само правило - в :func:`_season_asked`; тут второй его половина: во что именно
    переписывается запрос, когда правило сработало. ``None`` - номер остался номером
    части, запрос не трогаем.

    Обе половины стоят рядом и зовутся ОДНОЙ функцией не для красоты. Читателей у выдачи
    двое - круг поиска (:func:`~torrcast.usecases.discover.search_circle.search_circle`)
    и офлайн-переигровка (``scripts/poolreplay.py``, TC-397), - и пока прочтение было
    переписано в щупе своей
    копией, он строил планы по первому сезону там, где показ строил их по второму. Щуп,
    который меряет собственную копию правила, не меряет ничего.
    """
    if index is None or not _season_asked(found, name, pictures):
        return None
    return replace(args, query=[*name.split(), f"s{index}e1"])
