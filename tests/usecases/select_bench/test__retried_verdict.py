"""Зеркало итога после второго спроса: молчание, ставшее приговором, зовётся приговором."""

from __future__ import annotations

from torrcast.usecases.select_bench._retried_verdict import _retried_verdict


def test_a_verdict_won_by_the_second_ask_rewrites_the_line_about_silence() -> None:
    """Метаданные приехали, а серии в раздаче нет - обещать оживший рой было бы ложью."""
    tried, silents = _retried_verdict(
        queue=[3, 5],
        judged={3: "нужной серии в раздаче нет"},
        judged_before=set(),
        tried=["3 - не дождались за 20 с", "5 - не дождались за 20 с"],
        silents=2,
    )

    assert tried == ["3 - нужной серии в раздаче нет", "5 - не дождались за 20 с"]
    assert silents == 1, "молчащих стало на одного меньше - этот ответил"


def test_a_second_ask_that_stayed_silent_changes_nothing() -> None:
    """Рой промолчал и во второй раз - итог остаётся про молчание роя."""
    rows = ["3 - не дождались за 20 с"]

    assert _retried_verdict([3], {}, set(), rows, 1) == (rows, 1)


def test_a_verdict_that_was_there_before_is_not_a_new_one() -> None:
    """Приговор, уже вынесенный обходом, вторым спросом не считается."""
    rows = ["3 - тяжелее потолка"]

    assert _retried_verdict([3], {3: "тяжелее потолка"}, {3}, rows, 0) == (rows, 0)
