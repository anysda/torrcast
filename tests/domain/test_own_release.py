"""Зеркало своей раздачи узнанной картины: имя целиком и год, продолжение и тёзка - чужие."""

from __future__ import annotations

from tests.usecases.discover.world import releases, row
from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.own_release import own_release

_INCEPTION = MapPicture("Начало", 2010, False, "Inception", 2_867_448)
_IT = MapPicture("Оно", 2017, False, "It", 709_523)
_NARUTO = MapPicture("Наруто", 2002, True, "Naruto", 174_119)


def _own(title: str, known: MapPicture) -> bool:
    return own_release(releases([row(title)])[0], known)


def test_the_pictures_own_names_and_year_make_its_release() -> None:
    assert _own("Начало / Inception (2010) BDRip 1080p", _INCEPTION)
    assert _own("Inception.2010.1080p.BluRay.x264", _INCEPTION)
    assert _own("Оно / It (2017) WEB-DL 720p", _IT)


def test_a_longer_work_starting_with_the_name_is_not_the_picture() -> None:
    assert not _own(
        "Люди Икс: Начало. Росомаха / X-Men Origins: Wolverine (2009) BDRip", _INCEPTION
    )
    assert not _own("Оно 2 / It Chapter Two (2019) BDRip 1080p", _IT)
    assert not _own("Naruto: Shippuuden (2007) TV 1-500 WEBRip 720p", _NARUTO)


def test_a_namesake_of_another_year_is_not_the_picture() -> None:
    assert not _own("Оно / It (1990) DVDRip", _IT)
    assert _own("Оно / It (2018) WEB-DL 1080p", _IT), "премьера и прокат расходятся на год"


def test_a_season_of_a_series_is_dated_by_its_own_year() -> None:
    assert _own("Наруто / Naruto (2005) S04 WEBRip 720p", _NARUTO)
