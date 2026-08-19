"""Зеркало :mod:`torrcast.usecases.choice.understudy_note`: строка ухода к дублёру.

Уход к тёзке - это смена картины, то есть ровно то, о чём молчать нельзя. Строка
называет обе стороны с годами и причину: без причины это выглядело бы как каприз показа.
"""

from __future__ import annotations

from tests.usecases.choice.world import film, parts, plan
from torrcast.domain.not_found_error import NotFoundError
from torrcast.usecases.choice.understudy_note import _why_refused, understudy_note


def test_the_line_names_both_pictures_the_reason_and_what_the_spare_has_to_play() -> None:
    """Одна строка про уход - и в ней всё, чего человек не видит на экране."""
    failed = plan("Человек-невидимка", 1933, seeders=12)
    spare = plan("Человек-невидимка", 2020, pool=[film("a", seeders=140), film("b", seeders=90)])

    said = understudy_note(failed, spare, "годного релиза нет")

    assert said == (
        "«Человек-невидимка (1933)» - играть нечем (годного релиза нет); "
        "ухожу к «Человек-невидимка (2020)»: раздач 2"
    )


def test_the_line_is_one_line_because_it_is_read_right_before_the_show_starts() -> None:
    """Строка одна: переносов в ней нет, и на экране она не тонет в фазах поиска."""
    invisible = parts(("Человек-невидимка", 1933, 12), ("Человек-невидимка", 2020, 140))

    assert "\n" not in understudy_note(invisible[0], invisible[1], "годного релиза нет")


def test_the_reason_is_the_head_of_the_refusal_without_the_list_of_verdicts() -> None:
    """Причина - голова отказа: ни перечня приговорённых релизов, ни списка соседей."""
    refusal = NotFoundError(
        "годного релиза нет (1 - тяжёлый): выбери руками - cast releases <запрос>"
        "\nв каталоге есть Человек-невидимка (2020) - cast человек-невидимка"
    )

    assert _why_refused(refusal) == "годного релиза нет (1 - тяжёлый)"


def test_the_advice_to_choose_by_hand_never_travels_into_the_line() -> None:
    """Совет «выбери руками» после автоматического ухода - уже неправда.

    Уход состоялся сам, картина уже другая, и предлагать выбрать вручную то, что
    показ только что заменил, значит звать человека чинить сделанное за него.
    """
    refusal = NotFoundError("годного релиза нет: выбери руками - cast releases <запрос>")

    assert "cast releases" not in _why_refused(refusal)
