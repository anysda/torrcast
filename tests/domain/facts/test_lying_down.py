"""Зеркало :mod:`torrcast.domain.facts.lying_down`: приговор формы, общий для обоих
источников картинок."""

from __future__ import annotations

from torrcast.domain.facts.lying_down import lying_down


def test_a_wide_pair_is_lying_down() -> None:
    assert lying_down(1242, 866) is True


def test_an_upright_pair_and_a_square_one_are_not() -> None:
    assert lying_down(500, 750) is False
    assert lying_down(500, 500) is False


def test_a_missing_or_non_numeric_side_is_unknown_not_a_refusal() -> None:
    """🔴 Хоть одна сторона неизвестна - ``None``, а не ``False``/``True`` на угад.

    Зовущий у обоих источников читает ``None`` как «пропустить проверку», а не как
    готовый приговор: смена формата ответа не должна становиться отказом ВСЕМ картинам,
    и не должна тайно пропускать лежачую там, где сторону просто забыли спросить.
    """
    assert lying_down(None, 750) is None
    assert lying_down(500, None) is None
    assert lying_down(None, None) is None
    assert lying_down("500", 750) is None, "строка - не число"
    assert lying_down(True, 750) is None, "bool - подтип int, но не сторона"
