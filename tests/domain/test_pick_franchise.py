"""Зеркало :mod:`torrcast.domain.pick_franchise`."""

from torrcast.domain.cluster import cluster
from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.picture import Picture

_POOL = [
    "Тачки: Байки Мэтра / Cars Toon: Mater's Tall Tales (2008) BDRip 1080p",
    "Тачки: Байки Мэтра / Cars Toon: Mater's Tall Tales (2010) BDRip 1080p",
    "Тачки / Cars (2006) BDRip 1080p",
    "Тачки 2 / Cars 2 (2011) BDRip 1080p",
]


def _pictures() -> list[Picture]:
    return cluster([parse_release_name(name) for name in _POOL])


def test_pick_franchise_is_exposed() -> None:
    assert pick_franchise is not None


def test_a_subtitle_names_its_own_pictures() -> None:
    """Так работает запрос, который в карточке отвечает четырьмя картинами."""
    found = pick_franchise("Байки Мэтра", _pictures())

    assert [(p.title, p.year) for p in found] == [
        ("Тачки: Байки Мэтра", 2008),
        ("Тачки: Байки Мэтра", 2010),
    ]


def test_one_missing_letter_is_not_a_missing_picture() -> None:
    """🔴 TC-777. «Байки Мэтр» отказывал там, где «Байки Мэтра» давало картины."""
    assert [p.year for p in pick_franchise("Байки Мэтр", _pictures())] == [2008, 2010]


def test_the_year_from_our_own_menu_is_taken_back() -> None:
    """🔴 TC-777. Год мы печатаем сами - «(2008)», - и он обязан сужать, а не отказывать."""
    assert [p.year for p in pick_franchise("Байки Мэтра 2008", _pictures())] == [2008]


def test_a_year_nobody_has_leaves_the_pictures_of_the_name() -> None:
    """Год ошибиться может, а имя названо верно - отказывать по одному году не за что."""
    assert [p.year for p in pick_franchise("Байки Мэтра 1999", _pictures())] == [2008, 2010]


def test_a_name_the_catalogue_does_not_know_is_still_nothing() -> None:
    assert pick_franchise("хоббит", _pictures()) == []
