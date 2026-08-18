"""Проверяет, что боевой каталог раздач подходит своему порту."""

from torrcast.adapters import prowlarr
from torrcast.adapters.prowlarr.raw_result import RawResult
from torrcast.domain.release import Release
from torrcast.ports.torrent_catalogue import TorrentCatalogue


def test_search_module_fits_the_port() -> None:
    """Договор порта выполняет сам пакет каталога - переходника между ними нет."""
    port: TorrentCatalogue = prowlarr
    rows = [
        RawResult("Кино.2019.1080p", "a" * 40, size=1, seeders=2, indexer="rutor"),
        RawResult("Кино 2019 1080p", "a" * 40, size=1, seeders=9, indexer="nyaa"),
    ]
    merged = port.merge(rows[:1], rows[1:])
    assert len(merged) == 1, "одна раздача от двух индексеров - одна строка"
    releases = port.to_releases(merged)
    assert [type(item) for item in releases] == [Release]
    assert releases[0].magnet.startswith("magnet:?xt=urn:btih:")
