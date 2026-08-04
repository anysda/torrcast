"""Разбор выдачи Prowlarr: JSON ``/api/v1/search`` и Torznab-RSS.

Фикстуры — куски живой выдачи (Prowlarr 2.5.2, индексеры Knaben и RuTor),
плюс дописанные вручную битые строки: без ``infoHash``, с пустым именем и с
мусором вместо хэша. Все три обязаны молча отсеиваться, а не ронять поиск.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from torrcast import InfraError, NotFoundError
from torrcast.search import (
    PUBLIC_TRACKERS,
    Prowlarr,
    RawResult,
    from_json,
    from_torznab,
    magnet_for,
    to_releases,
)

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="module")
def json_results() -> list[RawResult]:
    return from_json(json.loads((FIXTURES / "prowlarr_search.json").read_text(encoding="utf-8")))


@pytest.fixture(scope="module")
def xml_results() -> list[RawResult]:
    return from_torznab((FIXTURES / "torznab.xml").read_text(encoding="utf-8"))


def test_json_keeps_only_usable_rows(json_results: list[RawResult]) -> None:
    """Из пяти строк фикстуры пригодны только две: у остальных нет хэша или имени."""
    assert [r.indexer for r in json_results] == ["Knaben", "RuTor"]


def test_json_carries_size_and_seeders(json_results: list[RawResult]) -> None:
    first = json_results[0]
    assert first.size > 0
    assert first.seeders >= 0
    assert first.info_hash == "E79011C658D37DB16880EB414097920250564DC3"


def test_torznab_reads_infohash_from_attr(xml_results: list[RawResult]) -> None:
    """infohash и seeders в Torznab лежат не в тегах, а в ``torznab:attr``."""
    assert len(xml_results) == 3  # четвёртый item — без infohash
    assert all(len(r.info_hash) == 40 for r in xml_results)
    assert all(r.indexer == "Knaben" for r in xml_results)
    assert any(r.seeders > 0 for r in xml_results)


def test_torznab_rejects_broken_xml() -> None:
    with pytest.raises(InfraError, match="битый XML"):
        from_torznab("<rss><channel><item>")


def test_json_rejects_non_list() -> None:
    with pytest.raises(InfraError, match="неожиданный ответ"):
        from_json({"error": "нет"})


def test_magnet_has_hash_name_and_trackers() -> None:
    """magnetUrl у Prowlarr — прокси-ссылка, поэтому magnet собираем сами."""
    magnet = magnet_for("ABCdef0123456789ABCDEF0123456789abcdef01", "Тачки 3")
    assert magnet.startswith("magnet:?xt=urn:btih:abcdef0123456789abcdef0123456789abcdef01")
    assert "dn=%D0%A2%D0%B0%D1%87%D0%BA%D0%B8%203" in magnet
    assert magnet.count("&tr=") == len(PUBLIC_TRACKERS)


def test_magnet_without_title_has_no_dn() -> None:
    assert "dn=" not in magnet_for("0" * 40)


def test_to_releases_parses_names_and_keeps_source_fields(
    json_results: list[RawResult],
) -> None:
    releases = to_releases(json_results)
    # Подзаголовок сборника отрезается парсером: «Матрица. Квадрология» → «Матрица».
    assert [r.title for r in releases] == ["Матрица", "Матрица"]
    assert releases[0].year == 1999
    assert releases[0].quality == "1080p"
    assert releases[0].magnet.startswith("magnet:?xt=urn:btih:")
    assert [r.size for r in releases] == [r.size for r in json_results]
    assert [r.indexer for r in releases] == ["Knaben", "RuTor"]


class _FakeSession:
    def __init__(self, payload: object) -> None:
        self.payload = payload
        self.url = ""

    def get(self, url: str, timeout: float) -> _FakeSession:
        self.url = url
        return self

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self.payload


def _client(payload: object) -> Prowlarr:
    client = Prowlarr("http://127.0.0.1:9696/", "KEY")
    client._session = _FakeSession(payload)  # type: ignore[assignment]
    return client


def test_search_builds_expected_url() -> None:
    """§8 ТЗ называет эндпоинт Jackett; у Prowlarr работает /api/v1/search."""
    client = _client(json.loads((FIXTURES / "prowlarr_search.json").read_text(encoding="utf-8")))
    client.search("матрица")
    url = client._session.url  # type: ignore[union-attr]
    assert url.startswith("http://127.0.0.1:9696/api/v1/search?apikey=KEY")
    assert "&type=search" in url
    assert "&categories=2000&categories=5000&categories=8000" in url


def test_search_reports_empty_result_as_not_found() -> None:
    with pytest.raises(NotFoundError, match="ничего не нашлось"):
        _client([]).search("нетакогофильма")
