"""Зеркало :mod:`torrcast.domain.episode`: одна серия сериала как значение."""

from torrcast.domain.episode import Episode


def test_an_episode_is_written_the_way_trackers_write_it() -> None:
    """Строкой серия уходит в имя файла и в строки на экране: форма тут - договор."""
    assert str(Episode(season=2, episode=7)) == "s2e7"


def test_the_same_episode_is_the_same_value() -> None:
    """Серия - значение, а не место в памяти: её кладут в словари и множества."""
    assert Episode(season=1, episode=1) == Episode(season=1, episode=1)
    assert Episode(season=1, episode=2) != Episode(season=2, episode=1)
    assert len({Episode(season=1, episode=1), Episode(season=1, episode=1)}) == 1
