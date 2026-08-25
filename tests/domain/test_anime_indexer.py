"""Зеркало :mod:`torrcast.domain.anime_indexer`: какой источник считается аниме-трекером."""

from torrcast.domain.anime_indexer import anime_indexer


def test_a_known_anime_tracker_is_recognised_by_a_piece_of_its_name() -> None:
    """Имя приходит от индексера как есть, поэтому сверяем подстрокой и без регистра."""
    assert anime_indexer("Nyaa")
    assert anime_indexer("nyaa.si")
    assert anime_indexer("AniDUB")


def test_an_ordinary_tracker_is_not_an_anime_one() -> None:
    assert not anime_indexer("RuTracker")
    assert not anime_indexer("")
