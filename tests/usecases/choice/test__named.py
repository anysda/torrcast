"""Зеркало :mod:`torrcast.usecases.choice._named`: как меню зовёт картину человеку.

Имя пункта - единственное, по чему человек отличает одну картину от другой: год в
скобках и есть тот признак, которым «Моана» 2016 отличается от «Моаны 2». Потеряй строка
любую его часть - и цифра в меню перестанет указывать на кино.
"""

from __future__ import annotations

import pytest

from tests.usecases.choice.world import Outside, film, outside, plan
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.catalogs.tongue import EN, RU, _choose_tongue
from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.origin import Origin
from torrcast.usecases.choice._named import (
    _BLURB_INDENT,
    _also,
    _different_display_names,
    _named,
    _spoken,
    _title,
)
from torrcast.usecases.choice.menu_blocks import menu_blocks


@pytest.fixture(autouse=True)
def _russian_catalog() -> None:
    """Русские ожидания этого зеркала явно выбирают русский каталог."""
    _choose_tongue(RU)


def test_a_picture_is_named_by_its_title_and_the_year_in_brackets() -> None:
    """Название и год: без года «Мумия» 1999 и «Мумия» 2017 в меню неразличимы."""
    assert _named(plan("Мумия", 1999).picture) == "Мумия (1999)"


def test_a_picture_is_named_by_its_original_title_in_english() -> None:
    """Английское меню меняет только подпись, а ключ памяти остаётся прежним."""
    picture = plan("Матрица", 1999, original="The Matrix").picture
    key = picture.key

    _choose_tongue(EN)

    assert _named(picture) == "The Matrix (1999)"
    assert picture.key == key == "movie:матрица:1999"

    _choose_tongue(RU)
    assert _named(picture) == "Матрица (1999)"


def test_the_language_changes_the_spoken_name_without_changing_the_memory_key() -> None:
    """Имя для всех строк экрана локализуется, а адрес сохранённого места остаётся русским."""
    picture = plan("Бегущий по лезвию", 1982, original="Blade Runner").picture
    key = picture.key

    _choose_tongue(EN)
    try:
        assert _title(picture) == "Blade Runner"
        assert picture.key == key == "movie:бегущий-по-лезвию:1982"
    finally:
        _choose_tongue(RU)


def test_a_glued_alias_uses_the_english_original_and_a_transliterated_tail() -> None:
    """Строка склейки не возвращает кириллицу поверх английского имени картины."""
    picture = plan("Титаник", 1997, original="Titanic").picture
    picture.also = "Титаник 3Д"

    _choose_tongue(EN)
    try:
        assert _also(picture) == "Titanic 3d"
    finally:
        _choose_tongue(RU)


def test_a_glued_line_is_silent_when_localized_names_only_differ_by_case() -> None:
    """Два одинаковых имени не объясняют склейку человеку."""
    picture = plan("Матрица", 1999, original="The Matrix").picture
    picture.also = "the matrix"

    _choose_tongue(EN)
    try:
        assert _different_display_names(picture) is False
    finally:
        _choose_tongue(RU)


def test_a_reference_name_is_spoken_from_the_language_side() -> None:
    """Имя картины из справки - с языковой стороны продукта; пустого оригинала не бывает."""
    about = Origin(title="Nine", year=2009, name="Девять")

    _choose_tongue(EN)
    try:
        assert _spoken(about) == "Nine"
        assert _spoken(Origin(name="Сваты")) == "Сваты", "выдуманного имени у картины нет"
    finally:
        _choose_tongue(RU)
    assert _spoken(about) == "Девять"


def test_an_english_menu_names_a_russian_only_picture_as_is_with_a_mark() -> None:
    """Английского имени нет вовсе: пункт меню зовётся СОБСТВЕННЫМ именем с пометкой.

    Заглушка вместо имени («English title unavailable») оставляла человека без того,
    единственного, по чему пункт выбирают: выбрать то, у чего нет имени, нельзя.
    Транслитом имя тоже не выдумывается - выдуманного имени у картины нет. Пометка же -
    только у пункта меню: в строках-рассказах хвост читался бы как часть названия.
    """
    picture = plan("Дюна: Пророчество 1", 2024).picture

    _choose_tongue(EN)
    try:
        assert _title(picture) == "Дюна: Пророчество 1"
        assert _named(picture) == "Дюна: Пророчество 1 (2024)"
        assert _named(picture, item=True) == "Дюна: Пророчество 1 (2024) - Russian title only"
    finally:
        _choose_tongue(RU)


def test_a_russian_only_mark_is_silent_in_the_russian_menu() -> None:
    """Под RU пометки нет: русское имя в русском меню - обычное дело."""
    assert _named(plan("Дюна: Пророчество 1", 2024).picture) == "Дюна: Пророчество 1 (2024)"


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
    assert (
        _named(plan("Нелюбовь", 2022, kind="tv").picture)
        == f"Нелюбовь (2022{phrase('choice.series_mark')})"
    )


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
