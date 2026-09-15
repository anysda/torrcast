"""Серия строки списка не как у раздач ищется сквозным номером («Интерны» IMDb 60, 60, 61, 98)."""

from __future__ import annotations

import pytest

from torrcast.domain._series import _Series
from torrcast.domain.episode import Episode
from torrcast.domain.episode_ordinal import EpisodeOrdinal
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.release import Release
from torrcast.domain.torr_file import TorrFile

INTERNS = EpisodeOrdinal((60, 60, 61, 98))
TAHIY = parse_release_name("Interny.XviD.[tahiy]")
FLAT = parse_release_name("Интерны [S01-14 + Фильм о фильме] (2010-2016) DVDRip, HDTV, WEB-DL")


def _tahiy(total: int) -> list[TorrFile]:
    """Пак по 20 серий в сезоне, в имени и номер сезона, и сквозной «(140)»."""
    return [
        TorrFile(
            n,
            f"Interny.XviD.[tahiy]/{(n - 1) // 20 + 1:02}/Interny."
            f"s{(n - 1) // 20 + 1:02}e{(n - 1) % 20 + 1:02}.({n:03})XviD.[tahiy].avi",
        )
        for n in range(1, total + 1)
    ]


def _flat(total: int) -> list[TorrFile]:
    """Пак, где серия в имени сквозная: «Сезон №7. Серия №140»."""
    return [
        TorrFile(
            n,
            f"Интерны/Интерны. Сезон №{(n - 1) // 20 + 1}/Интерны. "
            f"Сезон №{(n - 1) // 20 + 1}. Серия №{n:03}.avi",
        )
        for n in range(1, total + 1)
    ]


def _played(asked: Episode, release_files: list[TorrFile], release: Release = TAHIY) -> str:
    return _Series.asked(asked, INTERNS).choose(release, release_files).name


def test_the_row_s3e20_of_the_imdb_list_is_the_140th_episode_in_either_pack() -> None:
    assert _played(Episode(3, 20), _tahiy(278)).endswith("s07e20.(140)XviD.[tahiy].avi")
    assert _played(Episode(3, 20), _flat(280), FLAT).endswith("Сезон №7. Серия №140.avi")
    assert _played(Episode(1, 1), _flat(280), FLAT).endswith("Серия №001.avi")


def test_an_ordinal_past_the_pack_is_an_honest_refusal_naming_the_row() -> None:
    with pytest.raises(NotFoundError, match="s4e98"):
        _played(Episode(4, 98), _tahiy(278))
    assert _played(Episode(4, 98), _flat(280), FLAT).endswith("Серия №279.avi")


def test_a_pack_not_from_the_first_season_or_with_a_gap_plays_no_neighbour() -> None:
    later = [TorrFile(n, f"Show/Show.s03e{n:02}.avi") for n in range(1, 21)]
    gap = [f for f in _tahiy(60) if "s02e05" not in f.name]
    release = parse_release_name("Show.S03.WEB-DL")

    with pytest.raises(NotFoundError):
        _Series.asked(Episode(1, 3), EpisodeOrdinal((20, 20))).choose(release, later)
    with pytest.raises(NotFoundError):
        _played(Episode(1, 30), gap)
    assert _played(Episode(1, 24), gap).endswith("(024)XviD.[tahiy].avi"), "до пропуска серия есть"


def test_through_numbered_files_play_their_own_number_one_piece() -> None:
    pack = [TorrFile(n, f"One Piece/[Ohys] One Piece - {1060 + n}.mkv") for n in range(1, 53)]
    release = parse_release_name("Ван-Пис [TV] [1061-1112 из XX]")

    found = _Series.asked(Episode(2, 111), EpisodeOrdinal((1000, 200))).choose(release, pack)
    single = _Series.asked(Episode(1, 1061), EpisodeOrdinal((1178,))).choose(release, pack)

    assert (found.name, single.name) == (pack[50].name, pack[0].name)


def test_the_layout_flag_reads_only_season_counts() -> None:
    assert EpisodeOrdinal.read("60,60,61,98") == INTERNS
    assert EpisodeOrdinal.read("61") == EpisodeOrdinal((61,))
    assert [EpisodeOrdinal.read(bad) for bad in ("", "0,20", "20,,20", "a", "20,")] == [None] * 5
    assert INTERNS.want(Episode(5, 1)) is None
    assert INTERNS.want(Episode(2, 61)) is None
    assert _Series.asked(Episode(2, 61), INTERNS) == _Series(Episode(2, 61))
