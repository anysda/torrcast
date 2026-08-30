"""Проверяет разбор ответа ``/api/v1/search`` на куске живой выдачи Prowlarr 2.5.2.

Фикстура - выдача индексеров Knaben и RuTor плюс дописанные вручную битые строки: без
``infoHash``, с пустым именем и с мусором вместо хэша. Все три обязаны молча отсеиваться,
а не ронять поиск.
"""

import json
from pathlib import Path

import pytest

from torrcast.adapters.prowlarr.from_json import from_json
from torrcast.domain.infra_error import InfraError
from torrcast.domain.raw_result import RawResult

FIXTURES = Path(__file__).parents[2] / "fixtures"


@pytest.fixture(scope="module")
def json_results() -> list[RawResult]:
    return from_json(json.loads((FIXTURES / "prowlarr_search.json").read_text(encoding="utf-8")))


def test_json_keeps_only_usable_rows(json_results: list[RawResult]) -> None:
    """Из пяти строк фикстуры пригодны только две: у остальных нет хэша или имени."""
    assert [r.indexer for r in json_results] == ["Knaben", "RuTor"]


def test_json_carries_size_and_seeders(json_results: list[RawResult]) -> None:
    first = json_results[0]
    assert first.size > 0
    assert first.seeders >= 0
    assert first.info_hash == "E79011C658D37DB16880EB414097920250564DC3"


def test_json_rejects_non_list() -> None:
    """Не список - значит мы разговариваем не с Prowlarr, и это отказ инфры."""
    with pytest.raises(InfraError, match="unexpected answer"):
        from_json({"error": "нет"})


def test_честный_ноль_разбирается_в_пустой_список() -> None:
    """Пустая полка каталога - полноценный ответ, а не поломка разбора."""
    assert from_json([]) == []
