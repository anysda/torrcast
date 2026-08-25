"""Зеркало :mod:`torrcast.domain.parse_series`: сезоны и серии, названные именем раздачи."""

from torrcast.domain.parse_series import _parse_series


def test_a_season_and_an_episode_are_read_out_of_the_usual_form() -> None:
    season, episode, seasons, episodes, series = _parse_series("Сериал S02E05 1080p")

    assert (season, episode) == (2, 5)
    assert (seasons, episodes) == ((), ())
    assert series


def test_a_pack_of_seasons_names_them_all() -> None:
    season, _episode, seasons, _episodes, series = _parse_series("Сериал 1-3 сезоны")

    assert seasons == (1, 2, 3)
    assert season == 1
    assert series


def test_a_film_is_not_a_series_at_all() -> None:
    assert _parse_series("Брат 1997 BDRip 1080p") == (None, None, (), (), False)
