"""Как меню зовёт картину человеку: название с годом."""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.picture import Picture

#: Отступ описания в меню: ровно под название, за номером с точкой.
_BLURB_INDENT = " " * 5


def _named(picture: Picture, aside: bool = False) -> str:
    """Название с годом; ``aside`` - картина стоит после нумерованной линейки франшизы.

    Подпись объясняет, почему пункт уехал вниз: номера части у неё нет, и в линейку по
    номерам ей вставать не с чем (:func:`~torrcast.domain.outside_numbering.outside_numbering`).
    """
    marks = phrase("choice.series_mark") if picture.kind == "tv" else ""
    if aside:
        marks += phrase("choice.no_part_mark")
    return f"{picture.title} ({picture.year or '?'}{marks})"
