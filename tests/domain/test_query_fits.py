"""Checks which row of a search fits the year and the kind its query named."""

from __future__ import annotations

from torrcast.domain.query_fits import query_fits
from torrcast.domain.raw_result import RawResult

_SERIES_2026 = "Призрак в доспехах / Ghost in the Shell (2026) WEB-DL 1080p [S01, 1-10 из 12]"
_FILM_1995 = "Призрак в доспехах / Kokaku kidotai (1995) BDRip 1080p"
_FILM_2017 = "Призрак в доспехах / Ghost in the Shell (2017) BDRip 1080p"


def _row(title: str, seeders: int = 88) -> RawResult:
    return RawResult(title=title, info_hash="0" * 40, seeders=seeders)


def test_a_year_named_last_wants_a_row_of_that_year() -> None:
    fits = query_fits("Призрак в доспехах 2026")
    assert fits(_row(_SERIES_2026))
    assert not fits(_row(_FILM_1995))
    assert not fits(_row(_FILM_2017))


def test_a_query_without_a_year_or_an_episode_takes_any_row() -> None:
    fits = query_fits("Призрак в доспехах")
    assert fits(_row(_FILM_1995))
    assert fits(_row("Совсем другое имя без года"))


def test_an_episode_named_wants_a_series() -> None:
    fits = query_fits("хорошая жена s1e1")
    assert fits(_row("Хорошая жена / The Good Wife (2009) S01 WEB-DL"))
    assert not fits(_row("Хорошая жена (1987) DVDRip"))


def test_a_year_and_an_episode_want_both() -> None:
    fits = query_fits("Призрак в доспехах 2026 s1e1")  # the year is not the last word
    assert fits(_row(_FILM_2017.replace("BDRip", "S01 WEB-DL")))
    assert not fits(_row(_FILM_1995))
    fits = query_fits("Ghost in the Shell s01 2026")
    assert fits(_row(_SERIES_2026))
    assert not fits(_row("Ghost in the Shell (2026) 1080p"))


def test_a_row_of_the_year_that_cannot_lead_the_menu_does_not_fit() -> None:
    """RuTor's one 2026 row was a WEBRip-HEVC: the default cannot play it, Knaben's WEB-DL can."""
    fits = query_fits("Призрак в доспехах 2026")
    assert not fits(_row("Призрак в доспехах / Ghost in the Shell [S01] (2026) WEBRip-HEVC 1080p"))
    assert fits(_row(_SERIES_2026, seeders=5))
    assert not fits(_row(_SERIES_2026, seeders=4))


def test_a_query_without_a_year_still_takes_a_dead_row() -> None:
    assert query_fits("Призрак в доспехах")(_row(_FILM_1995, seeders=0))


def test_a_year_that_is_part_of_the_name_fits_a_row_carrying_the_whole_query() -> None:
    fits = query_fits("Бегущий по лезвию 2049")
    assert fits(_row("Бегущий по лезвию 2049 / Blade Runner 2049 (2017) BDRip 1080p"))
    assert not fits(_row("Бегущий по лезвию / Blade Runner (1982) BDRip 1080p"))
    assert not fits(_row("Бегущий по лезвию 20490 (2017) BDRip 1080p"))
