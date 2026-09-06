"""Оценка числом из строки справки."""

from __future__ import annotations

from web.rating_score import rating_score


def test_the_score_comes_out_of_the_english_line() -> None:
    assert rating_score("IMDb 8.7") == 8.7


def test_the_score_comes_out_of_the_russian_line_with_a_comma() -> None:
    assert rating_score("Рейтинг IMDb 7,6") == 7.6


def test_a_whole_number_stays_a_number() -> None:
    assert rating_score("IMDb 9") == 9.0


def test_a_line_without_digits_has_no_score() -> None:
    assert rating_score("IMDb") is None


def test_an_empty_line_has_no_score() -> None:
    assert rating_score("") is None
