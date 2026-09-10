"""Зеркало :mod:`torrcast.domain.exactly_named`: имя каталога, равное запросу целиком."""

from torrcast.domain.cluster import cluster
from torrcast.domain.exactly_named import exactly_named
from torrcast.domain.parse_release_name import parse_release_name
from torrcast.domain.picture import Picture

_POOL = [
    "Tarung Unforgiven (2026) 1080p WEBRip 5.1 x264 -YTS",
    "Unforgiven (1992) 1080p BDRip x264",
]


def _pictures() -> list[Picture]:
    return cluster([parse_release_name(name) for name in _POOL])


def test_the_name_the_source_cannot_take_whole_is_recognized_in_the_wide_pool() -> None:
    """🔴 TC-1158. Поиск на «Tarung Unforgiven» отдаёт нуль строк, на «Tarung» - её саму."""
    assert exactly_named("Tarung Unforgiven", _pictures()) == "tarung-unforgiven"


def test_a_part_of_a_pictures_name_is_not_the_picture() -> None:
    """Совпадение по ЧАСТИ имени не считается: половина названия - не та картина."""
    assert exactly_named("Tarung", _pictures()) == ""
    assert exactly_named("Unforgiven 1992", _pictures()) == ""


def test_a_near_miss_is_not_the_exact_name() -> None:
    """Близость тут не ворота: описку прощает :func:`nearly_named`, а не эта ступень."""
    assert exactly_named("Tarung Unforgivenn", _pictures()) == ""


def test_an_unknown_name_has_no_exact_match_in_the_catalogue() -> None:
    assert exactly_named("хоббит и гоблины", _pictures()) == ""
