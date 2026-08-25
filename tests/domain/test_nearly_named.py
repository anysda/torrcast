"""Зеркало :mod:`torrcast.domain.nearly_named`: имя каталога в одной букве от запроса."""

from torrcast.domain.cluster import cluster
from torrcast.domain.nearly_named import nearly_named
from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.picture import Picture

_POOL = [
    "Тачки: Байки Мэтра / Cars Toon: Mater's Tall Tales (2008) BDRip 1080p",
    "Тачки / Cars (2006) BDRip 1080p",
]


def _pictures() -> list[Picture]:
    return cluster([parse_release_name(name) for name in _POOL])


def test_one_missing_letter_still_names_the_picture() -> None:
    """🔴 TC-777. «Байки Мэтр» - это «Байки Мэтра», а не отсутствие картины."""
    assert nearly_named("Байки Мэтр", _pictures()) == "байки-мэтра"
    assert nearly_named("Байки Мэтры", _pictures()) == "байки-мэтра"


def test_the_exact_name_is_not_its_own_near_miss() -> None:
    assert nearly_named("Байки Мэтра", _pictures()) == ""


def test_a_letter_inside_the_name_is_another_picture() -> None:
    """🔴 «Кольца власти» и «Кольцо власти» - разное кино, а не описка."""
    rings = cluster([parse_release_name("Кольцо власти: Мировое супергосударство (2007) WEB-DL")])

    assert nearly_named("кольца власти", rings) == ""


def test_a_short_name_is_not_forgiven_a_letter() -> None:
    """У имени из пяти букв одна буква разницы - уже другое слово."""
    assert nearly_named("тачка", _pictures()) == ""


def test_an_unknown_name_has_no_near_miss_in_the_catalogue() -> None:
    assert nearly_named("хоббит и гоблины", _pictures()) == ""
