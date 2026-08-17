"""Проверяет контракт выгрузки оценок IMDb и поведение её фейка."""

from tests.fakes.rating_dump import FakeRatingDump
from torrcast.ports.rating_dump import RatingDump


def test_fake_gives_scores_and_votes_and_records_the_vote_lookup() -> None:
    """Голоса спрашивают редко, поэтому фейк помнит сам факт обращения к ним."""
    fake = FakeRatingDump(lambda: {"tt0317219": "7.3"}, {"tt0317219": 544373})
    port: RatingDump = fake
    assert port.scores() == {"tt0317219": "7.3"}
    assert fake.asked == [], "оценки взяты, а голоса ещё нет"
    assert port.votes() == {"tt0317219": 544373}
    assert fake.asked == ["votes"]
