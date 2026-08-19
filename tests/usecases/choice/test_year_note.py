"""Зеркало :mod:`torrcast.usecases.choice.year_note`: год дефолта против справки.

🔴 TC-199/TC-200. Год картины склеивается из ИМЕНИ раздачи, а имя врёт: «Оно» уезжает
раздачей 2014 года, «Медведь» - 2026-го, «Брат 2» - «Брат 2025». Гейт подмены сверял этот
год только вокруг добора, а у картины, вставшей дефолтом, он не сверялся нигде - и
человек молча получал не тот фильм.
"""

from __future__ import annotations

from tests.usecases.choice.world import plan
from torrcast.domain.facts.origin import Origin
from torrcast.usecases.choice.year_note import year_note


def test_a_year_that_disagrees_with_the_reference_is_said_out_loud() -> None:
    """Строка называет оба года: свой - из имени раздачи, и независимый - из справки."""
    it = plan("Оно", 2014, seeders=90)

    said = year_note(it, Origin(title="It", year=2017), "оно")

    assert said == "спросили «оно» - беру «Оно» 2014 года, но справка знает эту картину как 2017"


def test_without_the_words_of_the_person_the_line_keeps_everything_but_the_head() -> None:
    """``asked`` пуст - строка та же, только без головы «спросили X»."""
    it = plan("Оно", 2014, seeders=90)

    assert year_note(it, Origin(title="It", year=2017)) == (
        "беру «Оно» 2014 года, но справка знает эту картину как 2017"
    )


def test_a_year_apart_is_not_a_disagreement_but_production_against_release() -> None:
    """Допуск ±1 год: год производства против года проката - это не разъезд.

    Сделай сверку точной - и строка печаталась бы на каждой второй картине, то есть
    перестала бы читаться там, где она про дело.
    """
    bear = plan("Медведь", 2026, seeders=90)

    assert year_note(bear, Origin(title="The Bear", year=2025)) == ""


def test_a_remake_of_the_same_original_is_the_same_thing_however_far_the_years_are() -> None:
    """Поблажка ремейку: совпал оригинал - значит та же вещь, хоть годы и врозь.

    Без неё «Человек-невидимка» 2020 года получал бы строку про справку о 1933-м, и
    честное решение выглядело бы подменой.
    """
    invisible = plan("Человек-невидимка", 2020, original="The Invisible Man", seeders=90)

    assert year_note(invisible, Origin(title="The Invisible Man", year=1933)) == ""


def test_a_silent_reference_never_overrides_the_year_that_came_from_the_name() -> None:
    """Справка пуста или неуверенна - сверять нечем, и год из имени остаётся один.

    Латинописанное аниме, нет статьи, легла сеть: подменять единственный источник
    молчанием справки нельзя, и опровергать нечем неизвестный год картины.
    """
    it = plan("Оно", 2014, seeders=90)
    yearless = plan("Оно", None, seeders=90)

    assert year_note(it, Origin(title="It")) == ""
    assert year_note(yearless, Origin(title="It", year=2017)) == ""
