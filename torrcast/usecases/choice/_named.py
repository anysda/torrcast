"""Как меню зовёт картину человеку: название с годом."""

from __future__ import annotations

import re

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.catalogs.tongue import EN, tongue
from torrcast.domain.picture import Picture
from torrcast.domain.transliterate import transliterate

#: Отступ описания в меню: ровно под название, за номером с точкой.
_BLURB_INDENT = " " * 5
_CYRILLIC = re.compile("[А-Яа-яЁё]")


def _title(picture: Picture) -> str:
    """Имя картины для человека: оригинальное в английском интерфейсе."""
    if tongue() != EN:
        return picture.title
    if picture.original:
        return picture.original
    return picture.shown or picture.title


def _prepare_title(picture: Picture) -> None:
    """Готовит латинскую подпись живой выдачи, если её знает каталог."""
    if tongue() == EN and not picture.original and _CYRILLIC.search(picture.title):
        picture.shown = phrase("choice.english_title_unknown")


def _prepare_titles(pictures: list[Picture]) -> None:
    """Готовит подписи всей живой выдачи перед её первым сообщением."""
    for picture in pictures:
        _prepare_title(picture)


def _also(picture: Picture) -> str:
    """Второе склеенное имя тем же языком, что и основная подпись картины."""
    if tongue() != EN:
        return picture.also
    if not picture.original:
        return transliterate(picture.also) if _CYRILLIC.search(picture.also) else picture.also
    if picture.also.casefold().startswith(picture.title.casefold()):
        tail = picture.also[len(picture.title) :]
        gap = " " if tail[:1].isspace() else ""
        return f"{picture.original}{gap}{transliterate(tail)}"
    return transliterate(picture.also)


def _different_display_names(picture: Picture) -> bool:
    """Отличаются ли два склеенных имени после локализации."""
    return _also(picture).casefold() != _title(picture).casefold()


def _named(picture: Picture, aside: bool = False) -> str:
    """Название с годом; ``aside`` - картина стоит после нумерованной линейки франшизы.

    Подпись объясняет, почему пункт уехал вниз: номера части у неё нет, и в линейку по
    номерам ей вставать не с чем (:func:`~torrcast.domain.outside_numbering.outside_numbering`).
    """
    marks = phrase("choice.series_mark") if picture.kind == "tv" else ""
    if aside:
        marks += phrase("choice.no_part_mark")
    return f"{_title(picture)} ({picture.year or '?'}{marks})"
