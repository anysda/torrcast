"""Проверяет, что три исхода разбора справки друг от друга отличимы."""

from __future__ import annotations

from torrcast.domain.facts.blurb_outcome import ABSENT, BLANK, PARSED


def test_the_three_outcomes_are_three_different_words() -> None:
    """🔴 Слей их в одно «пусто» - и долю пропавшей справки нечем будет посчитать."""
    assert len({PARSED, ABSENT, BLANK}) == 3


def test_none_of_the_outcomes_is_an_empty_string() -> None:
    """Пустая строка в следе читается как «поля нет вовсе», а поле тут есть всегда."""
    assert all(word.strip() for word in (PARSED, ABSENT, BLANK))
