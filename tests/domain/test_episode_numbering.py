"""Названная серия играет именно эту серию: номера в именах файлов длинных раздач.

Корпус - живые оглавления пула: «Во все тяжкие» с номерами «101 Pilot» по каталогам
сезонов, «Ван-Пис» со сквозным четырёхзначным счётом, «Футурама» с кодами «1ACV01»
без номера серии. Прежде все три отвечали на ``sNeM`` порядковым местом файла.
"""

from __future__ import annotations

import pytest

from torrcast.domain._series import _Series
from torrcast.domain.episode import Episode
from torrcast.domain.map_episodes import map_episodes
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.parse_episode import parse_episode
from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.torr_file import TorrFile


def _files(*names: str) -> list[TorrFile]:
    return [TorrFile(index, name, 1_000_000_000) for index, name in enumerate(names, start=1)]


def _picked(release_name: str, files: list[TorrFile], want: Episode) -> str:
    return _Series(want=want).choose(parse_release_name(release_name), files).base


_BREAKING_BAD = _files(
    "Breaking Bad/S01/101 Pilot -- Пилот.mkv",
    "Breaking Bad/S01/102 Cat's in the Bag...-- Кот уже в мешке....mkv",
    "Breaking Bad/S01/103 ...And the Bag's in the River -- А мешок уже в реке.mkv",
    "Breaking Bad/S02/208 Better Call Saul -- Надо звонить Солу!.mkv",
    "Breaking Bad/S02/209 4 Days Out -- 4 дня на природе.mkv",
    "Breaking Bad/S02/210 Over -- Всё.mkv",
)


def test_hundreds_of_a_season_folder_are_the_season() -> None:
    found = [(f.season, f.episode, f.name) for f in map_episodes(_BREAKING_BAD)]
    assert found[0] == (1, 1, "101 Pilot -- Пилот.mkv")
    assert [(s, e) for s, e, _ in found] == [(1, 1), (1, 2), (1, 3), (2, 8), (2, 9), (2, 10)]
    name = "Во все тяжкие / Breaking Bad [S01-05] (2008-2013) BDRip 1080p"
    assert _picked(name, _BREAKING_BAD, Episode(2, 9)) == "209 4 Days Out -- 4 дня на природе.mkv"


def test_a_running_count_laid_out_by_seasons_restarts_in_each_season() -> None:
    interns = _files(
        "Интерны/01. Интерны. История болезни (2012).avi",
        *(
            f"Интерны/Интерны. Сезон №{s}. Серии №{20 * s - 19:03d}-{20 * s:03d}/"
            f"Интерны. Сезон №{s}. Серия №{n:03d}.avi"
            for s in (1, 2, 3)
            for n in range(20 * s - 19, 20 * s + 1)
        ),
    )
    name = "Интерны [S01-14 + Фильм о фильме] (2010-2016) DVDRip, HDTV, WEB-DL"
    assert _picked(name, interns, Episode(3, 20)) == "Интерны. Сезон №3. Серия №060.avi"
    broken = [f for f in interns if "Серия №021" not in f.name]
    assert (2, 22) in {(f.season, f.episode) for f in map_episodes(broken)}


def test_absolute_anime_numbers_without_a_season_folder_stay_absolute() -> None:
    naruto = _files(*(f"Naruto/[Group] Naruto - {n} [720p].mkv" for n in range(101, 106)))
    assert [f.episode for f in map_episodes(naruto)] == [101, 102, 103, 104, 105]


def test_four_digit_running_numbers_are_episodes_and_frame_heights_are_not() -> None:
    one_piece = _files(
        *(f"One Piece/One Piece - {n} [Persona99.GSG][480p].rus.jpn.mkv" for n in (1061, 1062)),
        "One Piece/1063-One_Piece_TV_[Persona99](1280x720).mkv",
    )
    assert [f.episode for f in map_episodes(one_piece)] == [1061, 1062, 1063]
    framed = _files("Show/Show 011 1080.mkv", "Show/Show 012 1080.mkv", "Show/Show 013 1080.mkv")
    assert [f.episode for f in map_episodes(framed)] == [11, 12, 13]
    assert parse_episode("Ван-Пис s1e1178") == Episode(1, 1178)


def test_a_running_span_of_four_digits_is_named_by_the_release() -> None:
    release = parse_release_name("One Piece / Ван-Пис [1061-1112 из XX] [TV] (1999) WEBRip")
    assert release.episodes[0] == 1061 and release.episodes[-1] == 1112
    assert not release.covers_episode(Episode(1, 1))
    assert not parse_release_name("Сериал (2001-2011) BDRip").episodes


def test_a_bracketed_span_of_seasons_is_not_a_span_of_episodes() -> None:
    release = parse_release_name("Интерны (1-14 сезоны) / РУ / DVDRip")
    assert release.seasons == tuple(range(1, 15)) and not release.episodes
    assert release.covers_episode(Episode(3, 20))
    assert parse_release_name("Наруто [01-220] (2002) DVDRip").episodes[-1] == 220


def test_file_order_does_not_answer_for_a_pack_of_several_seasons() -> None:
    flat = _files(*(f"Futurama/1ACV{n:02d} «Title {n}».mkv" for n in range(1, 5)))
    with pytest.raises(NotFoundError):
        _picked("Футурама / Futurama [S01-04] (1999-2003) WEB-DL 1080p", flat, Episode(1, 1))


def test_file_order_counts_inside_each_season_folder() -> None:
    folders = _files(
        "Futurama/Futurama - Season 1 [1080p]/1ACV01 «Space Pilot 3000».mkv",
        "Futurama/Futurama - Season 1 [1080p]/1ACV02 «The Series Has Landed».mkv",
        "Futurama/Futurama - Season 2 [1080p]/2ACV01 «I Second That Emotion».mkv",
        "Futurama/Futurama - Season 2 [1080p]/2ACV02 «Brannigan, Begin Again».mkv",
    )
    name = "Футурама / Futurama [S01-02] (1999-2000) WEB-DL 1080p"
    assert _picked(name, folders, Episode(2, 1)) == "2ACV01 «I Second That Emotion».mkv"


def test_file_order_takes_the_numbers_of_the_span_only_when_the_count_matches() -> None:
    unnumbered = _files("Show/Первая.mkv", "Show/Вторая.mkv", "Show/Третья.mkv")
    name = "Сериал / Show [21-23 из 40] (2020) WEB-DL 1080p"
    assert _picked(name, unnumbered, Episode(1, 22)) == "Вторая.mkv"
    with pytest.raises(NotFoundError):
        _picked(name, unnumbered, Episode(1, 1))
    with pytest.raises(NotFoundError):
        _picked("Сериал / Show [21-30 из 40] (2020) WEB-DL 1080p", unnumbered, Episode(1, 22))
