"""Зеркало каталога раздач: предмет договора считает то же, что и его соседи по пакету."""

from __future__ import annotations

from torrcast.adapters.prowlarr.merge import merge
from torrcast.adapters.prowlarr.to_releases import to_releases
from torrcast.adapters.prowlarr.torrent_catalogue import torrent_catalogue
from torrcast.domain.raw_result import RawResult

ROW = RawResult(
    title="Тачки / Cars (2006) BDRip 1080p",
    info_hash="a" * 40,
    size=8_000_000_000,
    seeders=40,
    indexer="Nyaa.si",
)


def test_the_catalogue_object_merges_exactly_like_its_neighbour_does() -> None:
    """Склейка у предмета - та же самая функция, а не однофамилец."""
    assert torrent_catalogue.merge([ROW], []) == merge([ROW], [])


def test_the_catalogue_object_parses_exactly_like_its_neighbour_does() -> None:
    """И разбор тоже: предмет договора ничего от себя не добавляет."""
    rows = torrent_catalogue.merge([ROW], [])

    assert torrent_catalogue.to_releases(rows) == to_releases(rows)
