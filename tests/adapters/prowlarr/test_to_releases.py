"""Проверяет перевод сырых строк в релизы: имя разобрано, поля каталога при них."""

import json
from pathlib import Path

import pytest

from torrcast.adapters.prowlarr.from_json import from_json
from torrcast.adapters.prowlarr.raw_result import RawResult
from torrcast.adapters.prowlarr.to_releases import to_releases

FIXTURES = Path(__file__).parents[2] / "fixtures"


@pytest.fixture(scope="module")
def json_results() -> list[RawResult]:
    return from_json(json.loads((FIXTURES / "prowlarr_search.json").read_text(encoding="utf-8")))


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


def test_склеенные_имена_и_индексеры_доезжают_до_релиза() -> None:
    """Признаки читаются по ВСЕМ строкам раздачи, поэтому склеенное едет целиком."""
    row = RawResult(
        title="Матрица (1999) 1080p",
        info_hash="a" * 40,
        size=1,
        seeders=2,
        indexer="Knaben",
        copies=3,
        indexers=("Knaben", "Nyaa.si"),
        names=("Матрица (1999) 1080p", "The Matrix 1999 1080p"),
    )
    (release,) = to_releases([row])
    assert release.indexers == ("Knaben", "Nyaa.si")
    assert release.names == ("Матрица (1999) 1080p", "The Matrix 1999 1080p")
    assert release.copies == 3


def test_пустая_выдача_даёт_пустой_список() -> None:
    assert to_releases([]) == []
