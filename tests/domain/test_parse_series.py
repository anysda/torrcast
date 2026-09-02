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


def test_a_tv_number_in_the_name_marks_a_season_of_a_show() -> None:
    """«ТВ-N» хвостом имени и в квадратных скобках - форма картины: так пишут аниме."""
    assert _parse_series("Токийский Гуль ТВ-2 [12 серий]")[4]
    assert _parse_series("Атака титанов [ТВ-3] 1080p")[4]


def test_a_tv_channel_in_the_voice_credits_is_not_a_season() -> None:
    """🔴 В КРУГЛЫХ скобках за голосовым тегом стоит студия: «ТВ-3» тут телеканал.

    Полнометражный «Терминатор 2» с дубляжом ТВ-3 уезжал в сериалы целой картиной, и
    сериалом же он выходил из склейки - вместе с правом на правила вида.
    """
    name = "Терминатор 2 / Terminator 2 (1991) BDRip 1080p | Dub (ТВ-3) + DVO (Twister)"

    assert not _parse_series(name)[4]
