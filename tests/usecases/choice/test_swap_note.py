"""Зеркало :mod:`torrcast.usecases.choice.swap_note`: строка про то, что реально пошло.

От :func:`default_note` отличается одним вопросом - а дефолт ли это. Человек, ответивший
на меню номером, ничего не подменял: он выбрал, и говорить ему «беру не то, что вы
назвали» было бы враньём.
"""

from __future__ import annotations

from dataclasses import replace

from tests.usecases.choice.world import parts
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.choice.swap_note import _is_default, swap_note


def test_a_picture_chosen_for_the_person_is_explained_out_loud() -> None:
    """Картину выбрали за человека - строка печатается, и она та же, что у дефолта."""
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    assert swap_note(mummy, mummy[0], "мумия") == phrase(
        "choice.note_namesake_asked",
        asked="мумия",
        mine="Мумия (1999)",
        others=phrase("choice.quoted", it="Мумия (2017)"),
    )


def test_a_picture_the_person_picked_himself_gets_no_line_about_any_swap() -> None:
    """Человек ответил номером - подмены не было, и строка тут была бы враньём."""
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    assert swap_note(mummy, mummy[1], "мумия") == ""
    assert _is_default(mummy, mummy[1]) is False


def test_a_menu_number_stays_a_persons_choice_after_its_picture_is_recognised_as_series() -> None:
    """Распознанный вид не превращает ответ номером в назначенный программой дефолт."""
    steins_gate = parts(("Врата Штейна", 2011, 100), ("Врата Штейна", 2009, 90))
    for plan in steins_gate:
        plan.asked_series = True

    steins_gate[1].picture.kind = "tv"

    assert swap_note(steins_gate, steins_gate[1], "врата штейна s1e1") == ""


def test_a_default_keeps_its_namesake_line_after_its_picture_is_recognised_as_series() -> None:
    """Уточнённый для показа вид не прячет тёзку, которая была видна выбору."""
    steins_gate = parts(("Врата Штейна", 2011, 100), ("Врата Штейна", 2009, 90))
    for plan in steins_gate:
        plan.asked_series = True

    steins_gate[0].picture.kind = "tv"

    assert swap_note(steins_gate, steins_gate[0], "врата штейна s1e1") == phrase(
        "choice.note_namesake_asked",
        asked="врата штейна s1e1",
        mine=f"Врата Штейна (2011{phrase('choice.series_mark')})",
        others=phrase("choice.quoted", it="Врата Штейна (2009)"),
    )


def test_a_menu_of_one_picture_was_never_a_choice_and_never_a_swap() -> None:
    """Картина одна - меню не задавалось вовсе, выбора не было, и строки нет."""
    single = parts(("Мумия", 1999, 47))

    assert _is_default(single, single[0]) is False
    assert swap_note(single, single[0], "мумия") == ""


def test_the_default_is_recognised_by_the_picture_and_not_by_the_identity_of_the_plan() -> None:
    """План после меню пересобирается на настоящей длительности - это уже ДРУГОЙ объект.

    Сверяй единица сами планы - строка пропадала бы ровно на том пути, где показ и
    состоится: после пересборки плана.
    """
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))
    retimed = replace(mummy[0], runtime=5400.0)

    assert retimed is not mummy[0]
    assert _is_default(mummy, retimed) is True
