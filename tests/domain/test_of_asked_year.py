"""Зеркало :mod:`torrcast.domain.of_asked_year`: картины года, который назвал запрос."""

from torrcast.domain.of_asked_year import of_asked_year
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _picture(title: str, year: int) -> Picture:
    return Picture(title=title, year=year, releases=[Release(raw_name=title, title=title)])


def test_the_pictures_of_the_year_named_last_are_kept() -> None:
    film, series = _picture("Призрак в доспехах", 1995), _picture("Призрак в доспехах", 2026)
    assert of_asked_year([film, series], "Призрак в доспехах 2026") == [series]


def test_no_year_named_keeps_nothing() -> None:
    film = _picture("Призрак в доспехах", 1995)
    assert of_asked_year([film], "Призрак в доспехах") == []
    assert of_asked_year([film], "") == []


def test_a_year_that_ends_the_pictures_own_name_is_its_name() -> None:
    """«Бегуший по лезвию 2049» года 2049 - год в имени, а не картина того года."""
    line = [_picture("Бегущий по лезвию 2049", 2017), _picture("Бегуший по лезвию 2049", 2049)]
    assert of_asked_year(line, "Бегущий по лезвию 2049") == []
