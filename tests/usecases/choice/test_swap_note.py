"""Зеркало :mod:`torrcast.usecases.choice.swap_note`: строка про то, что реально пошло.

От :func:`default_note` отличается одним вопросом - а дефолт ли это. Человек, ответивший
на меню номером, ничего не подменял: он выбрал, и говорить ему «беру не то, что вы
назвали» было бы враньём.
"""

from __future__ import annotations

from dataclasses import replace

from tests.usecases.choice.world import parts
from torrcast.usecases.choice.swap_note import _is_default, swap_note


def test_a_picture_chosen_for_the_person_is_explained_out_loud() -> None:
    """Картину выбрали за человека - строка печатается, и она та же, что у дефолта."""
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    assert swap_note(mummy, mummy[0], "мумия").startswith("спросили «мумия» - беру «Мумия (1999)»")


def test_a_picture_the_person_picked_himself_gets_no_line_about_any_swap() -> None:
    """Человек ответил номером - подмены не было, и строка тут была бы враньём."""
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    assert swap_note(mummy, mummy[1], "мумия") == ""
    assert _is_default(mummy, mummy[1]) is False


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
