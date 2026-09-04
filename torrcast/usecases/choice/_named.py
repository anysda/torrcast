"""Как меню зовёт картину человеку: название с годом."""

from __future__ import annotations

import re

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.catalogs.tongue import EN, tongue
from torrcast.domain.facts.origin import Origin
from torrcast.domain.picture import Picture
from torrcast.domain.spoken_title import spoken_title
from torrcast.domain.transliterate import transliterate

#: Отступ описания в меню: ровно под название, за номером с точкой.
_BLURB_INDENT = " " * 5
_CYRILLIC = re.compile("[А-Яа-яЁё]")


def _title(picture: Picture) -> str:
    """Имя картины для человека: оригинальное в английском интерфейсе.

    Английского имени нет вовсе - показывается СОБСТВЕННОЕ имя картины, а не заглушка
    и не транслит: выбрать пункт, у которого нет имени, человек не может. О том, что
    имя одно и оно по-русски, пункт говорит пометкой (:func:`_named`).

    Само правило тут не живёт: оно одно на все места, где картину зовут человеку
    (:func:`torrcast.domain.spoken_title.spoken_title`), - меню, запись показа, выдача
    в карточку Home Assistant. Списанное сюда второй раз, оно уже расходилось.
    """
    return spoken_title(picture.title, picture.original or "")


def _russian_only(picture: Picture) -> bool:
    """Имя картины показано как есть: английской подписи у неё нет вовсе."""
    return tongue() == EN and not picture.original and bool(_CYRILLIC.search(picture.title))


def _spoken(about: Origin) -> str:
    """Имя картины из справки с языковой стороны продукта: под EN - оригинал статьи.

    Оригинала у статьи нет (отечественная картина) - остаётся её русское имя: другого
    у картины нет, а выдуманное (транслит) было бы враньём наружу.
    """
    if tongue() != EN:
        return about.name
    return about.title or about.name


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


def _named(picture: Picture, aside: bool = False, item: bool = False) -> str:
    """Название с годом; ``aside`` - картина стоит после нумерованной линейки франшизы.

    Подпись объясняет, почему пункт уехал вниз: номера части у неё нет, и в линейку по
    номерам ей вставать не с чем (:func:`~torrcast.domain.outside_numbering.outside_numbering`).

    ``item`` - имя собирается для ПУНКТА МЕНЮ, и только там к имени без английской
    подписи добавляется пометка (:func:`_russian_only`): выбирают пункт по имени, и
    человек обязан видеть, что имя это одно и оно по-русски. В строках-рассказах
    (``taking ...``, ``you asked for ...``) пометки нет - там имя называется, а не
    выбирается, и хвост читался бы как часть названия.
    """
    marks = phrase("choice.series_mark") if picture.kind == "tv" else ""
    if aside:
        marks += phrase("choice.no_part_mark")
    named = f"{_title(picture)} ({picture.year or '?'}{marks})"
    if item and _russian_only(picture):
        named += phrase("choice.russian_title_only")
    return named
