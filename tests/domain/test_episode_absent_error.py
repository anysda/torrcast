"""Зеркало структурированного конца сезона."""

from torrcast.domain.episode_absent_error import EpisodeAbsentError
from torrcast.domain.not_found_error import NotFoundError


def test_the_season_ceiling_keeps_the_human_refusal_and_its_numbers() -> None:
    refusal = EpisodeAbsentError("серии s3e24 нет", season=3, last=23)

    assert isinstance(refusal, NotFoundError)
    assert str(refusal) == "серии s3e24 нет"
    assert (refusal.season, refusal.last) == (3, 23)
