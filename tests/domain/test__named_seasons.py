"""Названные в имени сезоны доходят до общего разбора раздачи."""

from __future__ import annotations

import pytest

from torrcast.domain._named_seasons import _named_episode, _named_seasons
from torrcast.domain.parse_release_name import parse_release_name


@pytest.mark.parametrize(
    ("name", "season", "seasons"),
    (
        ("Сериал / Series / Сезон: 9 / Серии: 1-10 из 10 WEB-DL 1080p", 9, ()),
        ("Сериал / Series / Сезоны: 1-5 / Серии: 1-21 WEB-DL 1080p", 1, (1, 2, 3, 4, 5)),
        ("Series S01-S05 WEB-DL 1080p", 1, (1, 2, 3, 4, 5)),
        ("Сериал / Series / 1-4 сезон WEB-DL 1080p", 1, (1, 2, 3, 4)),
        ("Сериал / Series / Сезон: 1, 2 / Серии: 1-21 WEB-DL 1080p", 1, (1, 2)),
        ("Сериал (1-2 сезоны: 1-40 серии из 40) WEB-DL 1080p", 1, (1, 2)),
        ("Сериал 1-3 сезоны 1080p", 1, (1, 2, 3)),
    ),
)
def test_named_season_forms_are_series_and_cover_every_named_season(
    name: str, season: int, seasons: tuple[int, ...]
) -> None:
    release = parse_release_name(name)

    assert release.kind == "tv"
    assert release.season == season
    assert release.seasons == seasons
    assert all(release.covers(number) for number in seasons or (season,))


@pytest.mark.parametrize(
    ("name", "season", "seasons", "episode"),
    (
        ("[SubsPlease] Oshi no Ko Season 2 - 05 (1080p) [ABCD1234].mkv", 2, (), 5),
        ("[Erai-raws] Show Season 3 - 11 [1080p]", 3, (), 11),
        ("Сериал / Сезон: 9 / 10 серий", 9, (), None),
        ("Сериал / Сезон 1 / 2019 / WEB-DL", 1, (), None),
        ("Сериал 1 сезон 5 серия", 1, (), 5),
        ("Сериал / Сезон: 1 / Серия: 5 [2020, WEB-DL]", 1, (), 5),
    ),
)
def test_numbers_beside_a_named_season_are_not_taken_for_more_seasons(
    name: str, season: int, seasons: tuple[int, ...], episode: int | None
) -> None:
    release = parse_release_name(name)

    assert (release.season, release.seasons, release.episode) == (season, seasons, episode)


@pytest.mark.parametrize("name", ("Сериал / Сезон: 2013 WEB-DL", "НБА сезон 2023-2024"))
def test_a_year_after_the_season_word_is_not_a_season(name: str) -> None:
    release = parse_release_name(name)

    assert (release.season, release.seasons) == (None, ())


# Строки из tests/test_season.py и tests/test_episodes.py PTT (коммит 88429bb9), тире в них
# заменены дефисом.
@pytest.mark.parametrize(
    ("name", "seasons"),
    (
        ("2 сезон 24 серия.avi", (2,)),
        ("3 сезон", (3,)),
        ("24 Season 1-8 Complete with Subtitles", (1, 2, 3, 4, 5, 6, 7, 8)),
        ("Coupling Season 1 - 4 Complete DVDRip - x264 - MKV by RiddlerA", (1, 2, 3, 4)),
        ("Ace of the Diamond: 2nd Season", (2,)),
        ("Adventure Time 10 th season", (10,)),
        ("Boondocks, The - Seasons 1 + 2", (1, 2)),
        (
            "Game of Thrones / Сезон: 1-8 / Серии: 1-73 из 73 [2011-2019, США, BDRip 1080p] MVO",
            (1, 2, 3, 4, 5, 6, 7, 8),
        ),
        ("[Erai-raws] Shingeki no Kyojin Season 3 - 11 (BD 1080p Hi10 FLAC) [1FA13150].mkv", (3,)),
        ("Друзья / Friends / Сезон: 1 / Серии: 1-24 из 24 [1994-1995, США, BDRip 720p]", (1,)),
        ("Друзья / Friends / Сезон: 1, 2 / Серии: 1-24 из 24 [1994-1999, США, BDRip 720p]", (1, 2)),
        ("Интерны. Сезон №9. Серия №180.avi", (9,)),
        ("Леди Баг и Супер-Кот - Сезон 3, Эпизод 21 - Кукловод 2 [1080p].mkv", (3,)),
        ("Проклятие острова ОУК_ 5-й сезон 09-я серия_ Прорыв Дэна.avi", (5,)),
        ("Разрушители легенд. MythBusters. Сезон 15. Эпизод 09. Скрытая угроза (2015).avi", (15,)),
        ("Сезон 5/Серия 11.mkv", (5,)),
        ("13-13-13 2013 DVDrip x264 AAC-MiLLENiUM", ()),
    ),
)
def test_ptt_season_strings(name: str, seasons: tuple[int, ...]) -> None:
    assert _named_seasons(name) == seasons


@pytest.mark.parametrize(
    ("name", "episode"),
    (
        ("Викинги / Vikings / Сезон: 5 / Серия: 1 [2017, WEB-DL 1080p] MVO", 1),
        ("Интерны. Сезон №9. Серия №180.avi", 180),
        ("Разрушители легенд. MythBusters. Сезон 15. Эпизод 09. Скрытая угроза (2015).avi", 9),
        ("Викинги / Vikings / Сезон: 5 / Серии: 5 из 20 [2017, WEB-DL 1080p] MVO", None),
        ("Мистер Робот / Mr. Robot / Сезон: 2 / Серии: 1-5 (12) [2016, США, WEBRip 1080p]", None),
    ),
)
def test_ptt_named_episode_strings(name: str, episode: int | None) -> None:
    assert _named_episode(name) == episode


def test_a_comma_list_of_seasons_stays_a_list() -> None:
    assert _named_seasons("Сериал [Сезон: 1, 3]") == (1, 3)


def test_a_descending_season_range_is_not_a_pack() -> None:
    assert parse_release_name("Сериал 3-1 сезоны").seasons == ()
