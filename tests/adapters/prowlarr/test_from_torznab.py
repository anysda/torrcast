"""Проверяет разбор Torznab-RSS на куске живой выдачи индексера."""

from pathlib import Path

import pytest

from torrcast.adapters.prowlarr.from_torznab import from_torznab
from torrcast.adapters.prowlarr.raw_result import RawResult
from torrcast.domain.infra_error import InfraError

FIXTURES = Path(__file__).parents[2] / "fixtures"


@pytest.fixture(scope="module")
def xml_results() -> list[RawResult]:
    return from_torznab((FIXTURES / "torznab.xml").read_text(encoding="utf-8"))


def test_torznab_reads_infohash_from_attr(xml_results: list[RawResult]) -> None:
    """infohash и seeders в Torznab лежат не в тегах, а в ``torznab:attr``."""
    assert len(xml_results) == 3  # четвёртый item - без infohash
    assert all(len(r.info_hash) == 40 for r in xml_results)
    assert all(r.indexer == "Knaben" for r in xml_results)
    assert any(r.seeders > 0 for r in xml_results)


def test_torznab_rejects_broken_xml() -> None:
    with pytest.raises(InfraError, match="битый XML"):
        from_torznab("<rss><channel><item>")


def test_имя_принёсшего_читается_и_у_jackett() -> None:
    """Тот же разбор - путь совместимости с Jackett'ом, а тег имени у них разный."""
    rows = from_torznab(
        '<rss xmlns:torznab="http://torznab.com/schemas/2015/feed"><channel><item>'
        "<title>Матрица</title><size>1024</size>"
        "<jackettindexer>RuTor</jackettindexer>"
        f'<torznab:attr name="infohash" value="{"a" * 40}"/>'
        '<torznab:attr name="seeders" value="7"/>'
        "</item></channel></rss>"
    )
    assert [(r.indexer, r.seeders) for r in rows] == [("RuTor", 7)]
