"""Проверяет опрос одного индексера под секундомером: выдача, время и ошибка."""

from __future__ import annotations

from typing import Any

from torrcast.adapters.prowlarr.ask_indexer import ask_indexer
from torrcast.domain.infra_error import InfraError


def _rows(count: int) -> list[dict[str, Any]]:
    return [
        {"title": f"Матрица {k}", "infoHash": f"{k:x}".ljust(40, "0"), "indexer": "Knaben"}
        for k in range(count)
    ]


def test_выдача_приезжает_разобранной_и_с_временем() -> None:
    asked: list[tuple[str, float]] = []

    def get_json(url: str, timeout: float) -> Any:
        asked.append((url, timeout))
        return _rows(2)

    rows, ms, error = ask_indexer(get_json, "http://p/api/v1/search", 3.0)
    assert rows is not None and len(rows) == 2
    assert error is None
    assert ms >= 0
    assert asked == [("http://p/api/v1/search", 3.0)]


def test_честный_ноль_это_ответ_а_не_молчание() -> None:
    """Пустой список - полноценный ответ каталога, и путать его с ``None`` нельзя."""
    rows, _ms, error = ask_indexer(lambda url, timeout: [], "http://p", 3.0)
    assert rows == []
    assert error is None


def test_отказ_возвращается_значением_чтобы_не_миновать_замер() -> None:
    """Молчун должен попасть в след со своими миллисекундами, а не улететь мимо."""

    def get_json(url: str, timeout: float) -> Any:
        raise InfraError("не отвечает")

    rows, ms, error = ask_indexer(get_json, "http://p", 3.0)
    assert rows is None
    assert isinstance(error, InfraError)
    assert isinstance(ms, int) and ms >= 0, "замер идёт и вокруг отказа"
