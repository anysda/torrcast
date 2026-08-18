"""Зеркало :mod:`torrcast.usecases.choice.namesake_note`: под именем и годом картин две.

🔴 TC-371. Двусмысленность тут не наша: именем «Девять» и годом 2009 в русском прокате
подписаны мюзикл ``Nine`` и мультфильм ``9``. Развести такую пару разбору нечем, и это
ровно тот случай, когда молчать нельзя.
"""

from __future__ import annotations

from tests.usecases.choice.world import plan
from torrcast.domain.facts.origin import Origin
from torrcast.usecases.choice import namesake_note


def test_the_second_picture_is_named_the_way_the_reference_signed_it() -> None:
    """Строка называет вторую картину именем справки - по нему человек и спросит точнее.

    Своих слов у нас тут нет вовсе: имя приходит из независимого источника, который
    знает обе картины и приносит их одним ответом.
    """
    nine = plan("Девять", 2009, seeders=40)

    said = namesake_note(nine, Origin(title="Nine", year=2009, namesake="9 (мультфильм)"))

    assert said == (
        "«Девять» (2009): под этим именем и годом картин две - "
        "справка знает ещё «9 (мультфильм)», развести их по имени и году нечем"
    )


def test_without_a_namesake_in_the_reference_the_line_would_be_an_invention() -> None:
    """Тёзки того же года справка не нашла - сверять не о чем, и строка была бы выдумкой."""
    nine = plan("Девять", 2009, seeders=40)

    assert namesake_note(nine, Origin(title="Nine", year=2009)) == ""


def test_a_reference_about_another_year_is_about_another_picture_entirely() -> None:
    """Год картины разошёлся со справкой - паспорт приехал про ДРУГУЮ картину.

    Её тёзка к выбранной отношения не имеет, и про сам разъезд годов человек читает
    своей строкой. Допуск тот же ±1 год, что и у сверки года: год производства против
    года проката - это не расхождение.
    """
    nine = plan("Девять", 2009, seeders=40)
    near = Origin(title="Nine", year=2010, namesake="9 (мультфильм)")
    far = Origin(title="Nine", year=2015, namesake="9 (мультфильм)")

    assert namesake_note(nine, near) != "", "±1 год - та же картина, и тёзка её"
    assert namesake_note(nine, far) == ""


def test_nothing_is_said_when_one_of_the_two_years_is_unknown() -> None:
    """Сверять нечем - молчим: ни год картины, ни год справки выдумывать нельзя."""
    nine = plan("Девять", 2009, seeders=40)
    yearless = plan("Девять", None, seeders=40)
    about = Origin(title="Nine", year=2009, namesake="9 (мультфильм)")

    assert namesake_note(nine, Origin(namesake="9 (мультфильм)")) == ""
    assert namesake_note(yearless, about) == ""
