"""Зеркало :mod:`torrcast.usecases.choice._named`: как меню зовёт картину человеку.

Имя пункта - единственное, по чему человек отличает одну картину от другой: год в
скобках и есть тот признак, которым «Моана» 2016 отличается от «Моаны 2». Потеряй строка
любую его часть - и цифра в меню перестанет указывать на кино.
"""

from __future__ import annotations

from tests.usecases.choice.world import Outside, film, outside, plan
from torrcast.domain.facts.fact import Fact
from torrcast.usecases.choice._named import _BLURB_INDENT, _named
from torrcast.usecases.choice.menu_blocks import menu_blocks


def test_a_picture_is_named_by_its_title_and_the_year_in_brackets() -> None:
    """Название и год: без года «Мумия» 1999 и «Мумия» 2017 в меню неразличимы."""
    assert _named(plan("Мумия", 1999).picture) == "Мумия (1999)"


def test_a_picture_with_no_known_year_says_so_instead_of_dropping_the_brackets() -> None:
    """Неизвестный год печатается вопросом, а не пустым местом.

    Пропади скобки вовсе - пункт выглядел бы как картина, про год которой всё ясно, и
    человек читал бы «не знаю» как «тот самый год».
    """
    assert _named(plan("Кино", None).picture) == "Кино (?)"


def test_a_series_is_marked_as_one_so_it_is_not_taken_for_the_film_of_the_same_name() -> None:
    """Сериал назван сериалом: одноимённая полнометражка - другое кино, а не «вариант».

    Пометки нет - и «Нелюбовь» фильм и «Нелюбовь» сериал стоят в меню двумя строками,
    отличаясь одним годом: человек выбирает не то, что просил, и узнаёт об этом на ТВ.
    """
    assert _named(plan("Нелюбовь", 2022, kind="tv").picture) == "Нелюбовь (2022, сериал)"


def test_a_picture_standing_after_the_numbered_line_says_why_it_went_down() -> None:
    """Подпись объясняет, почему пункт уехал вниз: номера части у картины нет.

    Без неё «Мультачки» просто стоят последними, и порядок меню читается как ранжир по
    качеству, а не как хронология франшизы с довеском.
    """
    said = _named(plan("Тачки: Мультачки", 2008).picture, aside=True)

    assert said == "Тачки: Мультачки (2008, без номера части)"


def test_a_series_outside_the_line_carries_both_marks_and_not_just_the_last_one() -> None:
    """Две пометки складываются: тип картины и её место в линейке - разные вопросы."""
    said = _named(plan("Тачки: Байки Мэтра", 2008, kind="tv").picture, aside=True)

    assert said == "Тачки: Байки Мэтра (2008, сериал, без номера части)"


def test_the_blurb_indent_puts_the_description_exactly_under_the_title() -> None:
    """Отступ описания ровно под названием, за номером с точкой.

    Число тут не украшение, а мера чужой строки: разъедься отступ с шапкой пункта - и
    описание висело бы под номером, а меню читалось бы лесенкой вместо столбца.
    """
    world = Outside(blurb=Fact(about="Мультфильм студии Pixar."))
    picture = plan("Тачки", 2006, pool=[film(seeders=50)])

    with outside(world):
        blocks = menu_blocks([picture, plan("Тачки 2", 2011)])
        rows = [line for block in blocks for line in block]

    assert rows[0].index("Тачки") == len(_BLURB_INDENT)
    assert rows[1].startswith(_BLURB_INDENT + "Мультфильм")
