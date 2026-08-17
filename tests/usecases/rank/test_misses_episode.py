"""Раздача сама, своим именем, признаётся, что нужной серии в ней нет."""

from __future__ import annotations

from tests.usecases.rank.releases import rel
from torrcast.domain.episode import Episode
from torrcast.usecases.rank.misses_episode import misses_episode

PACK = {"kind": "tv", "seasons": (1,), "episodes": (1, 2, 3, 4, 5, 6, 7, 8)}


def test_a_piece_that_misses_the_episode_is_named_so() -> None:
    """«Наруто»: верхом стоял [S01E01-08 of 220], а полный сезон - строкой ниже."""
    piece = rel(name="Наруто [S01E01-08 of 220]", **PACK)  # type: ignore[arg-type]
    assert not misses_episode(piece, Episode(1, 3))
    assert misses_episode(piece, Episode(1, 9))
    assert misses_episode(piece, Episode(2, 1))


def test_a_silent_name_is_never_accused() -> None:
    """Иначе у сериала, где серии не перечисляет ни одно имя, порядок бы рассыпался."""
    assert not misses_episode(rel(kind="tv"), Episode(5, 40))


def test_without_a_target_nobody_misses_anything() -> None:
    assert not misses_episode(rel(), None)
