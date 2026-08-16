"""Проверяет запасную длительность."""

from torrcast.domain.runtime_guess import RUNTIME_GUESS


def test_series_guess_is_shorter_than_movie() -> None:
    assert RUNTIME_GUESS["tv"] < RUNTIME_GUESS["movie"]
