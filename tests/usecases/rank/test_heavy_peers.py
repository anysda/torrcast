"""Тяжёлый сосед по группе: знаменатель пола размена у потолка приёмника."""

from __future__ import annotations

import pytest

from tests.usecases.rank.releases import RUNTIME, rel
from torrcast.domain.release import Release
from torrcast.usecases.rank.heavy_peers import Key, heavy_peers


def _keys(*groups: tuple[Key, list[Release]]) -> tuple[list[Release], dict[int, Key]]:
    pool: list[Release] = []
    keys: dict[int, Key] = {}
    for key, members in groups:
        for member in members:
            pool.append(member)
            keys[id(member)] = key
    return pool, keys


def test_the_heaviest_release_of_the_group_is_the_denominator() -> None:
    """~16 ГБ на два часа это 19.1 Мбит/с, ~13 - 15.5: берётся больший."""
    pool, keys = _keys((("a",), [rel(name="тяжелее", size_gb=16), rel(name="тяжёлый", size_gb=13)]))
    assert heavy_peers(pool, keys, RUNTIME, 10.0)[("a",)] == pytest.approx(19.09, abs=0.01)


def test_releases_under_the_ceiling_are_not_counted() -> None:
    """Лёгкую ступень не смещает: менять её не на что, знаменателя размен не получает."""
    pool, keys = _keys((("a",), [rel(size_gb=8)]))
    assert heavy_peers(pool, keys, RUNTIME, 10.0) == {}


def test_each_group_counts_its_own_neighbours() -> None:
    """Тяжёлый из чужой группы соперником не является ни на одной ступени."""
    pool, keys = _keys(
        (("a",), [rel(name="свой", size_gb=13)]),
        (("b",), [rel(name="чужой", size_gb=30)]),
    )
    assert heavy_peers(pool, keys, RUNTIME, 10.0)[("a",)] < 16.0


def test_an_unknown_weight_is_no_denominator() -> None:
    """Вес не назван - размен считать не от чего, и раздача в знаменатель не идёт."""
    silent = rel(name="Локи [S01]", kind="tv", size_gb=30)
    pool, keys = _keys((("a",), [silent]))
    assert heavy_peers(pool, keys, RUNTIME, 10.0) == {}
