"""Список слотов кодировщика: тяжёлые по битрейту и увесистые по весу копии - вместе."""

from __future__ import annotations

from tests.adapters.recode.grids import grid, keys
from torrcast.adapters.recode.targets import _targets
from torrcast.adapters.recode.weights import Weights


def _weights(rate: float) -> Weights:
    found = Weights.of(keys(rate=rate), grid())
    assert found is not None
    return found


def test_a_heavy_bitrate_alone_is_enough() -> None:
    """16 Мбит/с при пороге 15 - приёмник такой кусок как есть не тянет."""
    lines = grid()

    assert _targets(_weights(2.0e6), lines, threshold=15.0, cap=100_000_000) == tuple(
        range(lines.count)
    )


def test_a_light_film_has_no_targets_at_all() -> None:
    """Тяжёлых кусков нет - кодировщику браться не за что, и поток он не поднимает."""
    lines = grid()

    assert _targets(_weights(0.5e6), lines, threshold=15.0, cap=100_000_000) == ()


def test_a_bulky_copy_is_taken_even_when_the_bitrate_is_modest() -> None:
    """Замер: «Моана» 2016 - тяжёлых кусков нет вовсе, а увесистых семь.

    Сегмент тяжелее потолка роняет приёмник независимо от битрейта.
    """
    lines = grid()
    modest = _weights(0.5e6)  # 4 Мбит/с - до порога далеко

    taken = _targets(modest, lines, threshold=15.0, cap=1_000_000)

    assert taken, "увесистая копия обязана попасть к кодировщику"
    assert taken == tuple(sorted(set(taken))), "список идёт по порядку и без повторов"


def test_the_two_measures_are_merged_without_duplicates() -> None:
    """Кусок, который и тяжёлый, и увесистый, - это один слот, а не два."""
    lines = grid()
    heavy = _weights(2.0e6)

    both = _targets(heavy, lines, threshold=15.0, cap=1_000_000)

    assert both == tuple(range(lines.count))
    assert len(both) == len(set(both))
