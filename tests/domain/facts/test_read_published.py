"""Проверяет разбор ответа SPARQL на дату первой публикации (P577)."""

from typing import Any

from torrcast.domain.facts.read_published import read_published


def test_the_publication_year_is_the_earliest_p577_date() -> None:
    """🔴 TC-134. Год первой публикации из P577 - самая ранняя дата; ни одной - ``None``."""
    payload: dict[str, Any] = {
        "results": {
            "bindings": [
                {"date": {"value": "2016-12-02T00:00:00Z"}},  # прокат в одной стране
                {"date": {"value": "2016-11-14T00:00:00Z"}},  # премьера - раньше
            ]
        }
    }
    assert read_published(payload) == 2016
    assert read_published({"results": {"bindings": []}}) is None
    assert read_published("не словарь") is None
