"""Зеркало :mod:`torrcast.domain.ending_reached`."""

from __future__ import annotations

import pytest

from torrcast.domain.ending_reached import ending_reached
from torrcast.domain.entry import Entry
from torrcast.domain.watch_ratios import ENDING_RATIO

#: Длина того самого фильма из замера: 2:46:55.
WHOLE = 10015.0


def test_a_source_that_died_under_the_show_is_not_the_credits() -> None:
    """Ноль декодера на пятой минуте - это оборванный источник, а не доигранный фильм."""
    assert not ending_reached(282.0, WHOLE)


def test_the_credits_are_the_measured_share_of_the_film() -> None:
    """Мерка та же, по которой показ отличает титры от аварии."""
    assert ending_reached(WHOLE * ENDING_RATIO, WHOLE)
    assert not ending_reached(WHOLE * ENDING_RATIO - 1.0, WHOLE)


@pytest.mark.parametrize("whole", [0.0, -1.0, -WHOLE])
def test_an_unknown_length_is_never_the_end_of_the_film(whole: float) -> None:
    """Длины нет - конца нет: доли считать не от чего, и угадывать её никто не вправе.

    Длина приезжает от пробы медиатракта и на стыке серий обнуляется вместе с местом,
    так что ноль тут - это начало показа, а не его конец. Назови показ конченым здесь -
    и запись уйдёт в «досмотрено», не показав картины, а страховка перехода выстрелит по
    стоящему указателю ещё не начавшейся серии. Отрицательная длина - тот же случай:
    у картины её не бывает.
    """
    assert not ending_reached(WHOLE, whole)
    assert not ending_reached(0.0, whole)
    assert not ending_reached(282.0, whole)


@pytest.mark.parametrize("dur", [0.0, -1.0, WHOLE])
@pytest.mark.parametrize("pos", [0.0, 282.0, WHOLE * ENDING_RATIO, WHOLE])
def test_the_record_answers_the_end_question_by_this_very_rule(pos: float, dur: float) -> None:
    """Запись состояния и правило конца обязаны отвечать одинаково, включая границу.

    Вопрос «дошло ли до конца» задают в двух местах - записи показа и приёмнику, - и оба
    ответа сходятся на этой мерке. Разъехались бы они хоть на нулевой длительности - и
    страховка перехода стала бы лотереей: какое правило спросят, такой ответ и получат.
    """
    assert Entry(title="x", magnet="m", pos=pos, dur=dur).ending is ending_reached(pos, dur)
