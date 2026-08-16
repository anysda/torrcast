"""Tests for the immutable movie-facts value."""

from torrcast.domain.movie_facts import MovieFacts


def test_keeps_optional_movie_metadata() -> None:
    assert MovieFacts("Тачки", "Cars", 2006).original_title == "Cars"
