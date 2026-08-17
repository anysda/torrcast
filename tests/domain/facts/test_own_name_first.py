"""Проверяет порядок кандидатов прямой выборки: тёзка запроса идёт первой."""

from typing import Any

from torrcast.domain.facts.own_name_first import _own_name_first


def test_own_name_first_prefers_the_article_named_like_the_query() -> None:
    """Прямая выборка: тёзка запроса сильнее одноимённой подмены по алфавиту уточнений.

    Живой случай: спросили «девять», а уточнение «(мультфильм)» стоит в перечне раньше
    «(фильм)», и первая же киношная статья побеждала - справка отвечала про «9»
    (мультфильм), когда статья «Девять (фильм)» названа ровно спрошенным словом.
    """
    pages: list[Any] = [
        {"title": "9 (число)"},
        {"title": "9 (мультфильм, 2009)"},
        {"title": "Девять (фильм)"},
        None,
    ]

    out = _own_name_first(pages, "девять")

    assert out[0] == {"title": "Девять (фильм)"}, "тёзка идёт первой"
    assert out[1:] == [*pages[:2], None], "порядок остальных не тронут"


def test_own_name_first_keeps_redirected_spellings_in_the_race() -> None:
    """Перенаправленное написание («Уэнсдей» → «Уэнздей») не выбывает - оно просто следом."""
    pages: list[Any] = [{"title": "Уэнздей (телесериал)"}]

    assert _own_name_first(pages, "уэнсдей") == pages
